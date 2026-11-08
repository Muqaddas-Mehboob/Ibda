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
from .social_tokens import (
    SocialTokenEncryptionError,
    decrypt_social_token,
    encrypt_social_token,
)

logger = logging.getLogger(__name__)

STATE_LIFETIME = timedelta(minutes=10)
INSTAGRAM_CALLBACK_PATH = "/api/social/oauth/instagram/callback/"
INSTAGRAM_LOGIN_URL = "https://www.instagram.com/oauth/authorize"
INSTAGRAM_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
INSTAGRAM_GRAPH_URL = "https://graph.instagram.com"
INSTAGRAM_SCOPES = [
    "instagram_business_basic",
    "instagram_business_content_publish",
]
REQUEST_TIMEOUT = (5, 20)
GRAPH_VERSION_PATTERN = re.compile(r"v\d+\.\d+")
SUPPORTED_ACCOUNT_TYPES = frozenset({"BUSINESS", "MEDIA_CREATOR", "CREATOR"})

BUSINESS_DISCOVERY_FIELDS = "user_id,username,account_type"


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
        getattr(settings, "SOCIAL_INSTAGRAM_CLIENT_ID", ""),
        getattr(settings, "SOCIAL_INSTAGRAM_CLIENT_SECRET", ""),
        getattr(settings, "SOCIAL_INSTAGRAM_REDIRECT_URI", ""),
        getattr(settings, "SOCIAL_TOKEN_ENCRYPTION_KEY", ""),
    )
    if not all(required_settings):
        return "Instagram OAuth is not fully configured."
    if not instagram_api_version():
        return (
            "Instagram OAuth is not configured: the API version must use "
            "the vNN.N format."
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
            "client_id": settings.SOCIAL_INSTAGRAM_CLIENT_ID,
            "redirect_uri": settings.SOCIAL_INSTAGRAM_REDIRECT_URI,
            "response_type": "code",
            "scope": ",".join(INSTAGRAM_SCOPES),
            "enable_fb_login": "false",
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
            "Instagram returned an invalid response."
        ) from error
    if not isinstance(data, dict):
        raise InstagramOAuthError("Instagram returned an invalid response.")
    return data


def _exchange_code(code):
    try:
        response = requests.post(
            INSTAGRAM_TOKEN_URL,
            data={
                "client_id": settings.SOCIAL_INSTAGRAM_CLIENT_ID,
                "client_secret": settings.SOCIAL_INSTAGRAM_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "redirect_uri": settings.SOCIAL_INSTAGRAM_REDIRECT_URI,
                "code": code,
            },
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        # The exception text can embed the authorization code and secret.
        raise InstagramOAuthError(
            "Unable to exchange the Instagram authorization."
        ) from None

    if response.status_code != 200:
        raise InstagramOAuthError(
            "Instagram authorization could not be completed."
        )
    data = _response_json(response)
    if "data" in data:
        token_data = data["data"]
        if (
            not isinstance(token_data, list)
            or not token_data
            or not isinstance(token_data[0], dict)
        ):
            raise InstagramOAuthError(
                "Instagram returned invalid authorization information."
            )
        data = token_data[0]

    access_token = data.get("access_token")
    user_id = data.get("user_id")
    if not isinstance(access_token, str) or not access_token:
        raise InstagramOAuthError("Instagram did not return an access token.")
    if not isinstance(user_id, (str, int)) or not str(user_id).strip():
        raise InstagramOAuthError(
            "Instagram did not return an account identifier."
        )
    permissions = data.get("permissions")
    if not isinstance(permissions, str):
        raise InstagramOAuthError(
            "Instagram did not confirm the requested permissions."
        )
    granted_permissions = {
        permission.strip() for permission in permissions.split(",")
    }
    if not set(INSTAGRAM_SCOPES).issubset(granted_permissions):
        raise InstagramOAuthError(
            "Grant Instagram basic and content publishing permissions, then "
            "reconnect the account."
        )
    return access_token, str(user_id)


def _exchange_long_lived_token(short_lived_token):
    try:
        response = requests.get(
            f"{INSTAGRAM_GRAPH_URL}/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": settings.SOCIAL_INSTAGRAM_CLIENT_SECRET,
                "access_token": short_lived_token,
            },
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise InstagramOAuthError(
            "Unable to extend the Instagram authorization."
        ) from None

    if response.status_code != 200:
        raise InstagramOAuthError(
            "Instagram authorization could not be extended."
        )
    data = _response_json(response)
    token = data.get("access_token")
    expires_in = data.get("expires_in")
    if not isinstance(token, str) or not token:
        raise InstagramOAuthError(
            "Instagram did not return a long-lived access token."
        )
    if not isinstance(expires_in, int) or isinstance(expires_in, bool):
        raise InstagramOAuthError(
            "Instagram returned invalid token expiry information."
        )
    if expires_in <= 0:
        raise InstagramOAuthError(
            "Instagram returned invalid token expiry information."
        )
    return token, datetime.fromtimestamp(
        timezone.now().timestamp() + expires_in,
        tz=datetime_timezone.utc,
    )


def _fetch_profile(access_token):
    try:
        response = requests.get(
            f"{INSTAGRAM_GRAPH_URL}/{instagram_api_version()}/me",
            params={"fields": BUSINESS_DISCOVERY_FIELDS},
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise InstagramOAuthError(
            "Unable to retrieve the Instagram account."
        ) from None

    if response.status_code != 200:
        raise InstagramOAuthError(
            "Unable to retrieve the Instagram account."
        )
    data = _response_json(response)
    username = data.get("username")
    account_type = data.get("account_type")
    if not isinstance(username, str) or not username.strip():
        raise InstagramOAuthError(
            "Instagram did not return an account username."
        )
    if (
        not isinstance(account_type, str)
        or account_type.strip().upper() not in SUPPORTED_ACCOUNT_TYPES
    ):
        raise InstagramOAuthError(
            "An Instagram professional (Business or Creator) account is "
            "required."
        )
    return username.strip(), account_type.strip().upper()


def connect_instagram_account(owner_id, code):
    """Connect the authorized Instagram professional account for ``owner_id``."""
    if not code or len(code) > 4096:
        raise InstagramOAuthError(
            "Instagram did not return a valid authorization code."
        )

    short_lived_token, user_id = _exchange_code(code)
    access_token, expires_at = _exchange_long_lived_token(short_lived_token)
    username, _account_type = _fetch_profile(access_token)

    SocialAccount.objects.update_or_create(
        owner_id=owner_id,
        platform=SocialAccount.Platform.INSTAGRAM,
        platform_account_id=user_id,
        defaults={
            "display_name": username,
            "status": SocialAccount.Status.CONNECTED,
            "access_token_encrypted": encrypt_social_token(access_token),
            "refresh_token_encrypted": "",
            "token_expires_at": expires_at,
            "scopes": INSTAGRAM_SCOPES,
        },
    )
    logger.info(
        "instagram_oauth.connected",
        extra={
            "event": "instagram_oauth.connected",
            "platform": SocialAccount.Platform.INSTAGRAM,
            "instagram_user_id": user_id,
        },
    )
    return username


def refresh_instagram_token(account):
    """Refresh a long-lived Instagram token and persist the new one."""
    try:
        current_token = decrypt_social_token(account.access_token_encrypted)
    except SocialTokenEncryptionError:
        raise InstagramOAuthError(
            "The stored Instagram token could not be read."
        ) from None
    if not current_token:
        raise InstagramOAuthError("No Instagram access token is stored.")

    try:
        response = requests.get(
            f"{INSTAGRAM_GRAPH_URL}/refresh_access_token",
            params={
                "grant_type": "ig_refresh_token",
                "access_token": current_token,
            },
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise InstagramOAuthError(
            "Unable to refresh the Instagram authorization."
        ) from None

    if response.status_code != 200:
        raise InstagramOAuthError(
            "Unable to refresh the Instagram authorization."
        )
    data = _response_json(response)
    token = data.get("access_token")
    expires_in = data.get("expires_in")
    if not isinstance(token, str) or not token:
        raise InstagramOAuthError(
            "Instagram did not return a refreshed access token."
        )
    if not isinstance(expires_in, int) or isinstance(expires_in, bool):
        raise InstagramOAuthError(
            "Instagram returned invalid token expiry information."
        )
    if expires_in <= 0:
        raise InstagramOAuthError(
            "Instagram returned invalid token expiry information."
        )

    account.access_token_encrypted = encrypt_social_token(token)
    account.token_expires_at = datetime.fromtimestamp(
        timezone.now().timestamp() + expires_in,
        tz=datetime_timezone.utc,
    )
    account.save(
        update_fields=[
            "access_token_encrypted",
            "token_expires_at",
            "updated_at",
        ]
    )
    logger.info(
        "instagram_oauth.token_refreshed",
        extra={
            "event": "instagram_oauth.token_refreshed",
            "platform": SocialAccount.Platform.INSTAGRAM,
            "account_id": str(account.id),
        },
    )
    return token
