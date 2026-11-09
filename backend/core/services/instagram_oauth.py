import hashlib
import logging
import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

import requests
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ..models import SocialAccount, SocialOAuthState
from .social_tokens import (
    SocialTokenEncryptionError,
    encrypt_social_token,
)

logger = logging.getLogger(__name__)

STATE_LIFETIME = timedelta(minutes=10)
INSTAGRAM_CALLBACK_PATH = "/api/social/oauth/instagram/callback/"
INSTAGRAM_LOGIN_URL = "https://www.facebook.com/dialog/oauth"
INSTAGRAM_GRAPH_URL = "https://graph.facebook.com"
INSTAGRAM_SCOPES = [
    "instagram_basic",
    "instagram_manage_messages",
    "instagram_content_publish",
]
REQUEST_TIMEOUT = (5, 20)
GRAPH_VERSION_PATTERN = re.compile(r"v\d+\.\d+")


class InstagramOAuthError(Exception):
    pass


def instagram_api_version():
    """Return the configured Instagram Graph version, or "" when invalid."""
    version = getattr(settings, "SOCIAL_INSTAGRAM_API_VERSION", "")
    if not isinstance(version, str) or not GRAPH_VERSION_PATTERN.fullmatch(
        version
    ):
        return ""
    return version


def instagram_oauth_configuration_error():
    required_settings = (
        getattr(settings, "SOCIAL_INSTAGRAM_META_APP_ID", ""),
        getattr(settings, "SOCIAL_INSTAGRAM_META_APP_SECRET", ""),
        getattr(settings, "SOCIAL_INSTAGRAM_CONFIG_ID", ""),
        getattr(settings, "SOCIAL_INSTAGRAM_REDIRECT_URI", ""),
        getattr(settings, "SOCIAL_TOKEN_ENCRYPTION_KEY", ""),
    )
    if not all(required_settings):
        return "Instagram Unified Login is not fully configured."
    if not instagram_api_version():
        return (
            "Instagram Unified Login is not configured: the API version "
            "must use the vNN.N format."
        )

    try:
        Fernet(settings.SOCIAL_TOKEN_ENCRYPTION_KEY.encode("ascii"))
    except (UnicodeEncodeError, ValueError):
        return "Social token encryption is not configured correctly."

    try:
        redirect_uri = urlsplit(settings.SOCIAL_INSTAGRAM_REDIRECT_URI)
    except ValueError:
        return "Instagram OAuth redirect URI is invalid."
    if (
        redirect_uri.scheme != "https"
        or not redirect_uri.netloc
        or redirect_uri.username
        or redirect_uri.password
        or redirect_uri.path != INSTAGRAM_CALLBACK_PATH
        or redirect_uri.query
        or redirect_uri.fragment
    ):
        return (
            "Instagram OAuth redirect URI must be the configured HTTPS "
            "callback."
        )
    return ""


def instagram_oauth_is_configured():
    return not instagram_oauth_configuration_error()


def _new_state(owner_id, response_mode):
    now = timezone.now()
    SocialOAuthState.objects.filter(expires_at__lte=now).delete()
    state = secrets.token_urlsafe(32)
    SocialOAuthState.objects.create(
        state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
        owner_id=owner_id,
        platform=SocialAccount.Platform.INSTAGRAM,
        response_mode=response_mode,
        expires_at=now + STATE_LIFETIME,
    )
    return state


def create_instagram_authorization_url(owner_id, response_mode="native"):
    configuration_error = instagram_oauth_configuration_error()
    if configuration_error:
        raise InstagramOAuthError(configuration_error)
    if response_mode not in SocialOAuthState.ResponseMode.values:
        raise InstagramOAuthError("Instagram OAuth response mode is invalid.")

    state = _new_state(owner_id, response_mode)
    query = urlencode(
        {
            "client_id": settings.SOCIAL_INSTAGRAM_META_APP_ID,
            "config_id": settings.SOCIAL_INSTAGRAM_CONFIG_ID,
            "redirect_uri": settings.SOCIAL_INSTAGRAM_REDIRECT_URI,
            "response_type": "code",
            "display": "popup",
            "prompt": "login",
            "state": state,
        }
    )
    return f"{INSTAGRAM_LOGIN_URL}?{query}"


def get_instagram_oauth_response_mode(state):
    if not state or len(state) > 256:
        return SocialOAuthState.ResponseMode.NATIVE
    state_digest = hashlib.sha256(state.encode("utf-8")).hexdigest()
    return (
        SocialOAuthState.objects.filter(
            state_digest=state_digest,
            platform=SocialAccount.Platform.INSTAGRAM,
        )
        .values_list("response_mode", flat=True)
        .first()
        or SocialOAuthState.ResponseMode.NATIVE
    )


def consume_instagram_oauth_state(state):
    if not state or len(state) > 256:
        return None

    state_digest = hashlib.sha256(state.encode("utf-8")).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        consumed = SocialOAuthState.objects.filter(
            state_digest=state_digest,
            platform=SocialAccount.Platform.INSTAGRAM,
            expires_at__gt=now,
            consumed_at__isnull=True,
        ).update(consumed_at=now)
        if consumed != 1:
            return None
        return SocialOAuthState.objects.get(
            state_digest=state_digest,
            platform=SocialAccount.Platform.INSTAGRAM,
        )


def _response_json(response):
    try:
        data = response.json()
    except ValueError as error:
        raise InstagramOAuthError(
            "Meta returned an invalid response."
        ) from error
    if not isinstance(data, dict):
        raise InstagramOAuthError("Meta returned an invalid response.")
    return data


def _exchange_code(code):
    try:
        response = requests.get(
            f"{INSTAGRAM_GRAPH_URL}/{instagram_api_version()}/oauth/access_token",
            params={
                "client_id": settings.SOCIAL_INSTAGRAM_META_APP_ID,
                "client_secret": settings.SOCIAL_INSTAGRAM_META_APP_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise InstagramOAuthError(
            "Unable to exchange the Meta authorization."
        ) from None

    if response.status_code != 200:
        raise InstagramOAuthError(
            "Meta authorization could not be completed."
        )
    data = _response_json(response)
    access_token = data.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise InstagramOAuthError("Meta did not return an access token.")

    expires_in = data.get("expires_in")
    expires_at = None
    if expires_in is not None:
        if (
            not isinstance(expires_in, int)
            or isinstance(expires_in, bool)
            or expires_in <= 0
        ):
            raise InstagramOAuthError(
                "Meta returned invalid token expiry information."
            )
        expires_at = timezone.now() + timedelta(seconds=expires_in)
    return access_token, expires_at


def _graph_get(path, access_token, params):
    try:
        response = requests.get(
            f"{INSTAGRAM_GRAPH_URL}/{instagram_api_version()}/{path}",
            params=params,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise InstagramOAuthError(
            "Unable to retrieve the authorized Instagram business assets."
        ) from None

    if response.status_code != 200:
        raise InstagramOAuthError(
            "Unable to retrieve the authorized Instagram business assets."
        )
    return _response_json(response)


def _fetch_client_business_id(access_token):
    data = _graph_get("me", access_token, {"fields": "client_business_id"})
    business_id = data.get("client_business_id")
    if not isinstance(business_id, (str, int)) or not str(business_id).strip():
        raise InstagramOAuthError(
            "Meta did not return the connected business portfolio."
        )
    return str(business_id)


def _fetch_assigned_instagram_accounts(access_token):
    path = "me/assigned_instagram_accounts"
    params = {"fields": "id,username", "limit": 100}
    accounts = {}
    seen_cursors = set()
    has_next_page = True
    while has_next_page:
        data = _graph_get(path, access_token, params)
        page = data.get("data")
        if not isinstance(page, list):
            raise InstagramOAuthError(
                "Meta returned invalid Instagram account information."
            )
        for item in page:
            if not isinstance(item, dict):
                raise InstagramOAuthError(
                    "Meta returned invalid Instagram account information."
                )
            account_id = item.get("id")
            username = item.get("username", "")
            if (
                not isinstance(account_id, (str, int))
                or not str(account_id).strip()
            ):
                raise InstagramOAuthError(
                    "Meta returned an invalid Instagram account identifier."
                )
            if not isinstance(username, str):
                raise InstagramOAuthError(
                    "Meta returned an invalid Instagram account name."
                )
            account_id = str(account_id)
            accounts[account_id] = (
                username.strip() or f"Instagram account {account_id}"
            )

        paging = data.get("paging")
        has_next_page = isinstance(paging, dict) and bool(paging.get("next"))
        if not has_next_page:
            break
        cursors = paging.get("cursors")
        cursor = cursors.get("after") if isinstance(cursors, dict) else None
        if not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
            raise InstagramOAuthError(
                "Meta returned invalid Instagram account pagination."
            )
        seen_cursors.add(cursor)
        params["after"] = cursor
        if len(seen_cursors) >= 100:
            raise InstagramOAuthError(
                "Meta returned too many Instagram account pages."
            )

    if not accounts:
        raise InstagramOAuthError(
            "No Instagram professional accounts were shared with IBDA."
        )
    return accounts


def connect_instagram_account(owner_id, code):
    """Connect the Instagram professional accounts authorized for an owner."""
    if not code or len(code) > 4096:
        raise InstagramOAuthError(
            "Meta did not return a valid authorization code."
        )

    access_token, expires_at = _exchange_code(code)
    business_id = _fetch_client_business_id(access_token)
    accounts = _fetch_assigned_instagram_accounts(access_token)
    encrypted_token = encrypt_social_token(access_token)
    config_id = settings.SOCIAL_INSTAGRAM_CONFIG_ID

    with transaction.atomic():
        stale_accounts = SocialAccount.objects.filter(
            owner_id=owner_id,
            platform=SocialAccount.Platform.INSTAGRAM,
            status=SocialAccount.Status.CONNECTED,
        ).exclude(platform_account_id__in=accounts)
        stale_accounts.filter(
            Q(client_business_id=business_id, oauth_config_id=config_id)
            | Q(client_business_id="", oauth_config_id="")
        ).update(status=SocialAccount.Status.DISCONNECTED)

        for account_id, username in accounts.items():
            SocialAccount.objects.update_or_create(
                owner_id=owner_id,
                platform=SocialAccount.Platform.INSTAGRAM,
                platform_account_id=account_id,
                defaults={
                    "display_name": username,
                    "status": SocialAccount.Status.CONNECTED,
                    "access_token_encrypted": encrypted_token,
                    "refresh_token_encrypted": "",
                    "token_expires_at": expires_at,
                    "scopes": INSTAGRAM_SCOPES,
                    "client_business_id": business_id,
                    "oauth_config_id": config_id,
                },
            )

    logger.info(
        "instagram_oauth.connected",
        extra={
            "event": "instagram_oauth.connected",
            "platform": SocialAccount.Platform.INSTAGRAM,
            "account_count": len(accounts),
        },
    )
    return len(accounts)
