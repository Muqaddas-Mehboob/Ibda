import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone as datetime_timezone
from urllib.parse import urlencode, urlsplit

import requests
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import SocialAccount, SocialOAuthState
from .social_tokens import encrypt_social_token


logger = logging.getLogger(__name__)

STATE_LIFETIME = timedelta(minutes=10)
FACEBOOK_CALLBACK_PATH = "/api/social/oauth/facebook_pages/callback/"
FACEBOOK_LOGIN_URL = "https://www.facebook.com/{version}/dialog/oauth"
FACEBOOK_GRAPH_URL = "https://graph.facebook.com/{version}"
FACEBOOK_PERMISSIONS = ["pages_show_list"]
REQUEST_TIMEOUT = (5, 20)
MAX_PAGE_REQUESTS = 100


class FacebookOAuthError(Exception):
    pass


def facebook_oauth_configuration_error():
    required_settings = (
        settings.SOCIAL_FACEBOOK_CLIENT_ID,
        settings.SOCIAL_FACEBOOK_CLIENT_SECRET,
        settings.SOCIAL_FACEBOOK_CONFIG_ID,
        settings.SOCIAL_FACEBOOK_REDIRECT_URI,
        settings.SOCIAL_FACEBOOK_GRAPH_API_VERSION,
        settings.SOCIAL_TOKEN_ENCRYPTION_KEY,
    )
    if not all(required_settings):
        return "Facebook Pages OAuth is not fully configured."

    try:
        Fernet(settings.SOCIAL_TOKEN_ENCRYPTION_KEY.encode("ascii"))
    except (UnicodeEncodeError, ValueError):
        return "Social token encryption is not configured correctly."

    try:
        redirect_uri = urlsplit(settings.SOCIAL_FACEBOOK_REDIRECT_URI)
    except ValueError:
        return "Facebook OAuth redirect URI is invalid."
    if (
        redirect_uri.scheme != "https"
        or not redirect_uri.netloc
        or redirect_uri.username
        or redirect_uri.password
        or redirect_uri.path != FACEBOOK_CALLBACK_PATH
        or redirect_uri.query
        or redirect_uri.fragment
    ):
        return "Facebook OAuth redirect URI must be the configured HTTPS callback."

    if not re.fullmatch(r"v\d+\.\d+", settings.SOCIAL_FACEBOOK_GRAPH_API_VERSION):
        return "Facebook Graph API version must use the format vNN.N."

    return ""


def facebook_oauth_is_configured():
    return not facebook_oauth_configuration_error()


def _new_state(owner_id, response_mode):
    now = timezone.now()
    SocialOAuthState.objects.filter(expires_at__lte=now).delete()
    state = secrets.token_urlsafe(32)
    state_digest = hashlib.sha256(state.encode("ascii")).hexdigest()
    SocialOAuthState.objects.create(
        state_digest=state_digest,
        owner_id=owner_id,
        platform=SocialAccount.Platform.FACEBOOK_PAGES,
        response_mode=response_mode,
        expires_at=now + STATE_LIFETIME,
    )
    return state


def create_facebook_authorization_url(owner_id, response_mode="native"):
    configuration_error = facebook_oauth_configuration_error()
    if configuration_error:
        raise FacebookOAuthError(configuration_error)
    if response_mode not in {
        SocialOAuthState.ResponseMode.NATIVE,
        SocialOAuthState.ResponseMode.WEB,
    }:
        raise FacebookOAuthError("Facebook OAuth response mode is invalid.")

    state = _new_state(owner_id, response_mode)
    query = urlencode(
        {
            "client_id": settings.SOCIAL_FACEBOOK_CLIENT_ID,
            "redirect_uri": settings.SOCIAL_FACEBOOK_REDIRECT_URI,
            "config_id": settings.SOCIAL_FACEBOOK_CONFIG_ID,
            "response_type": "code",
            "override_default_response_type": "true",
            "state": state,
        }
    )
    login_url = FACEBOOK_LOGIN_URL.format(
        version=settings.SOCIAL_FACEBOOK_GRAPH_API_VERSION
    )
    return f"{login_url}?{query}"


def get_facebook_oauth_response_mode(state):
    if not state or len(state) > 256:
        return SocialOAuthState.ResponseMode.NATIVE
    state_digest = hashlib.sha256(state.encode("utf-8")).hexdigest()
    return (
        SocialOAuthState.objects.filter(
            state_digest=state_digest,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
        )
        .values_list("response_mode", flat=True)
        .first()
        or SocialOAuthState.ResponseMode.NATIVE
    )


def consume_facebook_oauth_state(state, platform):
    if not state or len(state) > 256:
        return None

    state_digest = hashlib.sha256(state.encode("utf-8")).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        consumed = SocialOAuthState.objects.filter(
            state_digest=state_digest,
            platform=platform,
            expires_at__gt=now,
            consumed_at__isnull=True,
        ).update(consumed_at=now)
        if consumed != 1:
            return None
        return SocialOAuthState.objects.get(
            state_digest=state_digest,
            platform=platform,
        )


def _response_json(response):
    try:
        data = response.json()
    except ValueError as error:
        raise FacebookOAuthError("Meta returned an invalid response.") from error
    if not isinstance(data, dict):
        raise FacebookOAuthError("Meta returned an invalid response.")
    return data


def _exchange_code(code):
    endpoint = (
        FACEBOOK_GRAPH_URL.format(
            version=settings.SOCIAL_FACEBOOK_GRAPH_API_VERSION
        )
        + "/oauth/access_token"
    )
    try:
        response = requests.get(
            endpoint,
            params={
                "client_id": settings.SOCIAL_FACEBOOK_CLIENT_ID,
                "client_secret": settings.SOCIAL_FACEBOOK_CLIENT_SECRET,
                "redirect_uri": settings.SOCIAL_FACEBOOK_REDIRECT_URI,
                "code": code,
            },
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        # Meta documents GET for this OAuth token endpoint, so the app secret
        # and authorization code necessarily travel in the query string. The
        # request exception embeds that full URL, so it is discarded instead of
        # being chained: neither the cause nor the context of the error we raise
        # can carry the secret or the code into logs or error reports.
        response = None
    if response is None:
        raise FacebookOAuthError("Unable to exchange the Facebook authorization.")

    if response.status_code != 200:
        raise FacebookOAuthError("Facebook authorization could not be completed.")
    data = _response_json(response)
    access_token = data.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise FacebookOAuthError("Meta did not return an access token.")

    return access_token


def _exchange_long_lived_token(short_lived_token):
    endpoint = (
        FACEBOOK_GRAPH_URL.format(
            version=settings.SOCIAL_FACEBOOK_GRAPH_API_VERSION
        )
        + "/oauth/access_token"
    )
    try:
        response = requests.post(
            endpoint,
            data={
                "grant_type": "fb_exchange_token",
                "client_id": settings.SOCIAL_FACEBOOK_CLIENT_ID,
                "client_secret": settings.SOCIAL_FACEBOOK_CLIENT_SECRET,
                "fb_exchange_token": short_lived_token,
            },
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException as error:
        raise FacebookOAuthError(
            "Unable to extend the Facebook authorization."
        ) from error

    if response.status_code != 200:
        raise FacebookOAuthError("Facebook authorization could not be extended.")
    data = _response_json(response)
    long_lived_token = data.get("access_token")
    if not isinstance(long_lived_token, str) or not long_lived_token:
        raise FacebookOAuthError(
            "Meta did not return a long-lived access token."
        )

    return long_lived_token


def _token_timestamp(debug_data, field):
    value = debug_data.get(field)
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value = int(value)
    if not isinstance(value, int) or value < 0:
        return None
    return value


def _page_token_expiry(page_token, page_id, user_access_token):
    """Return the Page token's real expiry, or None when Meta says it has none."""
    endpoint = (
        FACEBOOK_GRAPH_URL.format(
            version=settings.SOCIAL_FACEBOOK_GRAPH_API_VERSION
        )
        + "/debug_token"
    )
    try:
        response = requests.get(
            endpoint,
            params={
                "input_token": page_token,
                "access_token": user_access_token,
            },
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException as error:
        raise FacebookOAuthError(
            "Unable to verify the Facebook Page access token."
        ) from error

    if response.status_code != 200:
        raise FacebookOAuthError("Unable to verify the Facebook Page access token.")
    data = _response_json(response)
    debug_data = data.get("data")
    if not isinstance(debug_data, dict) or debug_data.get("is_valid") is not True:
        raise FacebookOAuthError(
            "Meta did not confirm the Facebook Page access token."
        )
    if debug_data.get("type") != "PAGE":
        raise FacebookOAuthError("Meta returned an unexpected Facebook token type.")

    app_id = debug_data.get("app_id")
    if app_id is not None and str(app_id) != str(
        settings.SOCIAL_FACEBOOK_CLIENT_ID
    ):
        raise FacebookOAuthError("The Facebook Page token belongs to another app.")
    profile_id = debug_data.get("profile_id")
    if profile_id is not None and str(profile_id) != str(page_id):
        raise FacebookOAuthError("The Facebook Page token belongs to another Page.")

    expires_at = _token_timestamp(debug_data, "expires_at")
    if expires_at is None:
        raise FacebookOAuthError(
            "Meta returned invalid Facebook Page token expiry information."
        )
    if expires_at > 0:
        return datetime.fromtimestamp(expires_at, tz=datetime_timezone.utc)

    data_access_expires_at = _token_timestamp(
        debug_data,
        "data_access_expires_at",
    )
    if data_access_expires_at is None:
        raise FacebookOAuthError(
            "Meta returned invalid Facebook Page data access expiry information."
        )
    if data_access_expires_at > 0:
        return datetime.fromtimestamp(
            data_access_expires_at,
            tz=datetime_timezone.utc,
        )

    # Meta reports no expiry for the token and no data access limit for it.
    return None


def _log_skipped_page(page_index, reason):
    logger.warning(
        "facebook_oauth.page_skipped",
        extra={
            "event": "facebook_oauth.page_skipped",
            "platform": SocialAccount.Platform.FACEBOOK_PAGES,
            "page_index": page_index,
            "reason": reason,
        },
    )


def _log_pagination_stopped(reason, pages_collected):
    logger.warning(
        "facebook_oauth.pagination_stopped",
        extra={
            "event": "facebook_oauth.pagination_stopped",
            "platform": SocialAccount.Platform.FACEBOOK_PAGES,
            "reason": reason,
            "pages_collected": pages_collected,
        },
    )

def _get_authorized_pages(user_access_token):
    endpoint = (
        FACEBOOK_GRAPH_URL.format(
            version=settings.SOCIAL_FACEBOOK_GRAPH_API_VERSION
        )
        + "/me/accounts"
    )
    pages = []
    after = None
    seen_cursors = set()

    while True:
        if len(seen_cursors) >= MAX_PAGE_REQUESTS:
            _log_pagination_stopped("request_cap", len(pages))
            break
        params = {"fields": "id,name,access_token", "limit": 100}
        if after:
            params["after"] = after
        try:
            response = requests.get(
                endpoint,
                params=params,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {user_access_token}",
                },
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
            )
        except requests.RequestException as error:
            raise FacebookOAuthError("Unable to retrieve authorized Facebook Pages.") from error

        if response.status_code != 200:
            raise FacebookOAuthError("Unable to retrieve authorized Facebook Pages.")
        data = _response_json(response)
        page_data = data.get("data")
        if not isinstance(page_data, list):
            raise FacebookOAuthError("Meta returned an invalid Pages response.")
        for page_index, page in enumerate(page_data):
            if not isinstance(page, dict):
                _log_skipped_page(page_index, "invalid_entry")
                continue
            if not isinstance(page.get("id"), str) or not page["id"]:
                _log_skipped_page(page_index, "missing_id")
                continue
            if (
                not isinstance(page.get("name"), str)
                or not page["name"].strip()
            ):
                _log_skipped_page(page_index, "missing_name")
                continue
            if (
                not isinstance(page.get("access_token"), str)
                or not page["access_token"]
            ):
                _log_skipped_page(page_index, "missing_access_token")
                continue
            pages.append(page)

        paging = data.get("paging")
        if not isinstance(paging, dict) or not paging.get("next"):
            break
        cursors = paging.get("cursors")
        if not isinstance(cursors, dict) or "after" not in cursors:
            _log_pagination_stopped("missing_cursor", len(pages))
            break
        next_after = cursors.get("after")
        if not isinstance(next_after, str) or not next_after.strip():
            # A next link without a usable cursor cannot be followed: only the
            # fixed Graph host is ever called, so keep the Pages found so far.
            _log_pagination_stopped("invalid_cursor", len(pages))
            break
        if next_after in seen_cursors:
            # A repeated cursor would loop forever; stop with what we have.
            _log_pagination_stopped("duplicate_cursor", len(pages))
            break
        seen_cursors.add(next_after)
        after = next_after

    return pages


def connect_authorized_facebook_pages(owner_id, code):
    if not code or len(code) > 4096:
        raise FacebookOAuthError("Facebook did not return a valid authorization code.")

    short_lived_token = _exchange_code(code)
    user_access_token = _exchange_long_lived_token(short_lived_token)
    pages = _get_authorized_pages(user_access_token)

    # Verify every Page token before writing anything so a failure cannot leave
    # a partially connected account behind.
    authorized_pages = []
    for page in pages:
        authorized_pages.append(
            {
                "id": page["id"],
                "name": page["name"],
                "access_token": page["access_token"],
                "token_expires_at": _page_token_expiry(
                    page["access_token"],
                    page["id"],
                    user_access_token,
                ),
            }
        )

    with transaction.atomic():
        for page in authorized_pages:
            SocialAccount.objects.update_or_create(
                owner_id=owner_id,
                platform=SocialAccount.Platform.FACEBOOK_PAGES,
                platform_account_id=page["id"],
                defaults={
                    "display_name": page["name"],
                    "status": SocialAccount.Status.CONNECTED,
                    "access_token_encrypted": encrypt_social_token(
                        page["access_token"]
                    ),
                    "refresh_token_encrypted": "",
                    "token_expires_at": page["token_expires_at"],
                    "scopes": FACEBOOK_PERMISSIONS,
                },
            )
    logger.info(
        "facebook_oauth.pages_connected",
        extra={
            "event": "facebook_oauth.pages_connected",
            "platform": SocialAccount.Platform.FACEBOOK_PAGES,
            "page_count": len(pages),
        },
    )
    return len(pages)
