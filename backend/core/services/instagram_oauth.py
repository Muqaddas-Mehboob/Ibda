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
INSTAGRAM_DIAGNOSTIC_PERMISSIONS = {
    "instagram_basic",
    "instagram_manage_messages",
    "instagram_content_publish",
    "instagram_manage_comments",
    "instagram_manage_insights",
    "pages_show_list",
    "pages_read_engagement",
    "business_management",
}
DIAGNOSTIC_URL_PATTERN = re.compile(
    r"\b(?:[a-z][a-z0-9+.-]*://|www\.)\S+",
    re.IGNORECASE,
)
DIAGNOSTIC_SECRET_PATTERN = re.compile(
    r"(?i)\b(?:access_token|authorization|code|client_secret|app_secret|"
    r"encryption_key|secret|token)\b\s*[:=]\s*(['\"]?)[^\s,;'\"]+\1"
)
DIAGNOSTIC_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+\S+")
DIAGNOSTIC_OPAQUE_PATTERN = re.compile(r"\b[A-Za-z0-9_~+/=-]{32,}\b")


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


def sanitize_instagram_diagnostic(value, sensitive_values=()):
    message = str(value)
    secrets_to_redact = (
        getattr(settings, "SOCIAL_INSTAGRAM_META_APP_SECRET", ""),
        getattr(settings, "SOCIAL_TOKEN_ENCRYPTION_KEY", ""),
        *sensitive_values,
    )
    for secret in secrets_to_redact:
        if isinstance(secret, str) and secret:
            message = message.replace(secret, "[redacted]")
    message = DIAGNOSTIC_URL_PATTERN.sub("[redacted-url]", message)
    message = DIAGNOSTIC_BEARER_PATTERN.sub("Bearer [redacted]", message)
    message = DIAGNOSTIC_SECRET_PATTERN.sub(
        "[redacted-credential]",
        message,
    )
    message = DIAGNOSTIC_OPAQUE_PATTERN.sub("[redacted-value]", message)
    message = "".join(
        character if character.isprintable() else " " for character in message
    )
    return message[:300]


def format_instagram_diagnostic(event, **fields):
    """Render sanitized diagnostics into the log message itself.

    The default console handler prints only ``%(message)s``, so the same
    already-sanitized values attached through ``extra`` are also rendered
    here to stay visible in the terminal.
    """
    parts = [event]
    for name, value in fields.items():
        if value is None:
            rendered = "-"
        elif isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, int):
            rendered = str(value)
        else:
            text = str(value).replace("\r", " ").replace("\n", " ")
            text = text.replace('"', "'")
            rendered = f'"{text}"' if any(ch.isspace() for ch in text) else text
        parts.append(f"{name}={rendered}")
    return " ".join(parts)


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


def _graph_error_diagnostics(data, sensitive_values=()):
    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        error = {}
    code = error.get("code")
    subcode = error.get("error_subcode")
    error_type = error.get("type")
    message = error.get("message")
    return {
        "graph_error_code": code if isinstance(code, int) and not isinstance(code, bool) else None,
        "graph_error_type": (
            sanitize_instagram_diagnostic(error_type, sensitive_values)
            if isinstance(error_type, str)
            else None
        ),
        "graph_error_subcode": (
            subcode
            if isinstance(subcode, int) and not isinstance(subcode, bool)
            else None
        ),
        "graph_error_message": (
            sanitize_instagram_diagnostic(message, sensitive_values)
            if isinstance(message, str)
            else None
        ),
    }


def _log_instagram_diagnostic(level, event, **fields):
    message = format_instagram_diagnostic(event, **fields)
    logger.log(level, message, extra={"event": event, **fields})


def _exchange_failure_diagnostics(response, code):
    """Return sanitized diagnostics for a failed token-exchange response.

    Temporary instrumentation for the Unified Login authorization-code
    exchange. Only the provider's error code, type, subcode and a scrubbed
    message are kept; the authorization code, credentials, request
    parameters, headers and the request URL are never logged.
    """
    status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int) or isinstance(status_code, bool):
        status_code = None

    body = None
    try:
        body = response.json()
    except (ValueError, TypeError, AttributeError):
        body = None
    graph_error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(graph_error, dict):
        graph_error = None

    graph_error_code = None
    graph_error_type = None
    graph_error_subcode = None
    graph_error_message = None
    if graph_error is not None:
        error_code = graph_error.get("code")
        if isinstance(error_code, int) and not isinstance(error_code, bool):
            graph_error_code = error_code
        error_type = graph_error.get("type")
        if isinstance(error_type, str) and error_type:
            graph_error_type = sanitize_instagram_diagnostic(
                error_type,
                sensitive_values=(code,),
            )
        error_subcode = graph_error.get("error_subcode")
        if isinstance(error_subcode, int) and not isinstance(error_subcode, bool):
            graph_error_subcode = error_subcode
        error_message = graph_error.get("message")
        if isinstance(error_message, str) and error_message:
            graph_error_message = sanitize_instagram_diagnostic(
                error_message,
                sensitive_values=(code,),
            )

    return {
        "http_status_code": status_code,
        "graph_error_code": graph_error_code,
        "graph_error_type": graph_error_type,
        "graph_error_subcode": graph_error_subcode,
        "graph_error_message": graph_error_message,
    }


def _exchange_code(code):
    try:
        response = requests.get(
            f"{INSTAGRAM_GRAPH_URL}/{instagram_api_version()}/oauth/access_token",
            params={
                "client_id": settings.SOCIAL_INSTAGRAM_META_APP_ID,
                "client_secret": settings.SOCIAL_INSTAGRAM_META_APP_SECRET,
                "redirect_uri": settings.SOCIAL_INSTAGRAM_REDIRECT_URI,
                "code": code,
            },
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        _log_instagram_diagnostic(
            logging.WARNING,
            "instagram_oauth.code_exchange",
            http_status_code=None,
            request_succeeded=False,
            graph_error_code=None,
            graph_error_type=None,
            graph_error_subcode=None,
            graph_error_message=None,
        )
        raise InstagramOAuthError(
            "Unable to exchange the Meta authorization."
        ) from None

    if response.status_code != 200:
        diagnostics = _exchange_failure_diagnostics(response, code)
        diagnostics["request_succeeded"] = False
        redirect = urlsplit(settings.SOCIAL_INSTAGRAM_REDIRECT_URI)
        diagnostics["redirect_host"] = redirect.netloc
        diagnostics["redirect_path"] = redirect.path
        logger.warning(
            format_instagram_diagnostic(
                "instagram_oauth.code_exchange", **diagnostics
            ),
            extra={
                "event": "instagram_oauth.code_exchange",
                **diagnostics,
            },
        )
        raise InstagramOAuthError(
            "Meta authorization could not be completed."
        )
    _log_instagram_diagnostic(
        logging.INFO,
        "instagram_oauth.code_exchange",
        http_status_code=response.status_code,
        request_succeeded=True,
        graph_error_code=None,
        graph_error_type=None,
        graph_error_subcode=None,
        graph_error_message=None,
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


def _graph_request(path, access_token, params):
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
    return response


def _graph_get(path, access_token, params):
    response = _graph_request(path, access_token, params)
    if response.status_code != 200:
        raise InstagramOAuthError(
            "Unable to retrieve the authorized Instagram business assets."
        )
    return _response_json(response)


def _fetch_client_business_id(access_token):
    try:
        response = _graph_request(
            "me", access_token, {"fields": "client_business_id"}
        )
    except InstagramOAuthError:
        _log_instagram_diagnostic(
            logging.WARNING,
            "instagram_oauth.business_portfolio",
            http_status_code=None,
            request_succeeded=False,
            portfolio_found=False,
            graph_error_code=None,
            graph_error_type=None,
            graph_error_subcode=None,
            graph_error_message=None,
        )
        raise
    try:
        data = _response_json(response)
    except InstagramOAuthError:
        _log_instagram_diagnostic(
            logging.WARNING,
            "instagram_oauth.business_portfolio",
            http_status_code=response.status_code,
            request_succeeded=False,
            portfolio_found=False,
            graph_error_code=None,
            graph_error_type=None,
            graph_error_subcode=None,
            graph_error_message=None,
        )
        raise
    graph_error = _graph_error_diagnostics(data, (access_token,))
    request_succeeded = (
        response.status_code == 200
        and not isinstance(data.get("error"), dict)
    )
    if response.status_code != 200:
        _log_instagram_diagnostic(
            logging.WARNING,
            "instagram_oauth.business_portfolio",
            http_status_code=response.status_code,
            request_succeeded=False,
            portfolio_found=False,
            **graph_error,
        )
        raise InstagramOAuthError(
            "Unable to retrieve the authorized Instagram business assets."
        )
    business_id = data.get("client_business_id")
    portfolio_found = (
        request_succeeded
        and isinstance(business_id, (str, int))
        and bool(str(business_id).strip())
    )
    _log_instagram_diagnostic(
        logging.INFO if portfolio_found else logging.WARNING,
        "instagram_oauth.business_portfolio",
        http_status_code=response.status_code,
        request_succeeded=request_succeeded,
        portfolio_found=portfolio_found,
        **graph_error,
    )
    if not portfolio_found:
        raise InstagramOAuthError(
            "Meta did not return the connected business portfolio."
        )
    return str(business_id)


def _fetch_assigned_instagram_accounts(access_token, sensitive_values=()):
    path = "me/assigned_instagram_accounts"
    params = {"fields": "id,username", "limit": 100}
    accounts = {}
    seen_cursors = set()
    has_next_page = True
    while has_next_page:
        try:
            response = _graph_request(path, access_token, params)
        except InstagramOAuthError:
            diagnostics = {
                "http_status_code": None,
                "request_succeeded": False,
                "account_count": 0,
                "graph_error_code": None,
                "graph_error_type": None,
                "graph_error_subcode": None,
                "graph_error_message": None,
            }
            _log_instagram_diagnostic(
                logging.WARNING,
                "instagram_oauth.assigned_accounts_lookup",
                **diagnostics,
            )
            raise

        status_code = response.status_code
        try:
            data = _response_json(response)
        except InstagramOAuthError:
            diagnostics = {
                "http_status_code": status_code,
                "request_succeeded": status_code == 200,
                "account_count": 0,
                "graph_error_code": None,
                "graph_error_type": None,
                "graph_error_subcode": None,
                "graph_error_message": None,
            }
            _log_instagram_diagnostic(
                logging.WARNING,
                "instagram_oauth.assigned_accounts_lookup",
                **diagnostics,
            )
            raise

        graph_error = data.get("error")
        graph_diagnostics = _graph_error_diagnostics(
            data,
            (access_token, *sensitive_values),
        )
        request_succeeded = (
            status_code == 200 and not isinstance(graph_error, dict)
        )

        if status_code != 200:
            diagnostics = {
                "http_status_code": status_code,
                "request_succeeded": False,
                "account_count": 0,
                **graph_diagnostics,
            }
            _log_instagram_diagnostic(
                logging.WARNING,
                "instagram_oauth.assigned_accounts_lookup",
                **diagnostics,
            )
            raise InstagramOAuthError(
                "Unable to retrieve the authorized Instagram business assets."
            )

        page = data.get("data")
        diagnostics = {
            "http_status_code": status_code,
            "request_succeeded": request_succeeded,
            "account_count": len(page) if isinstance(page, list) else 0,
            **graph_diagnostics,
        }
        _log_instagram_diagnostic(
            logging.INFO
            if request_succeeded and diagnostics["account_count"]
            else logging.WARNING,
            "instagram_oauth.assigned_accounts_lookup",
            **diagnostics,
        )
        if not isinstance(page, list):
            _log_instagram_diagnostic(
                logging.WARNING,
                "instagram_oauth.account_validation",
                returned_accounts=0,
                accepted_accounts=0,
                rejected_accounts=1,
                rejection_reason="invalid_structure",
            )
            raise InstagramOAuthError(
                "Meta returned invalid Instagram account information."
            )
        for item in page:
            if not isinstance(item, dict):
                _log_instagram_diagnostic(
                    logging.WARNING,
                    "instagram_oauth.account_validation",
                    returned_accounts=len(page),
                    accepted_accounts=len(accounts),
                    rejected_accounts=1,
                    rejection_reason="invalid_structure",
                )
                raise InstagramOAuthError(
                    "Meta returned invalid Instagram account information."
                )
            account_id = item.get("id")
            username = item.get("username", "")
            if (
                not isinstance(account_id, (str, int))
                or not str(account_id).strip()
            ):
                _log_instagram_diagnostic(
                    logging.WARNING,
                    "instagram_oauth.account_validation",
                    returned_accounts=len(page),
                    accepted_accounts=len(accounts),
                    rejected_accounts=1,
                    rejection_reason="invalid_id",
                )
                raise InstagramOAuthError(
                    "Meta returned an invalid Instagram account identifier."
                )
            if not isinstance(username, str):
                _log_instagram_diagnostic(
                    logging.WARNING,
                    "instagram_oauth.account_validation",
                    returned_accounts=len(page),
                    accepted_accounts=len(accounts),
                    rejected_accounts=1,
                    rejection_reason="invalid_username",
                )
                raise InstagramOAuthError(
                    "Meta returned an invalid Instagram account name."
                )
            account_id = str(account_id)
            accounts[account_id] = (
                username.strip() or f"Instagram account {account_id}"
            )

        _log_instagram_diagnostic(
            logging.INFO,
            "instagram_oauth.account_validation",
            returned_accounts=len(page),
            accepted_accounts=len(page),
            rejected_accounts=0,
            rejection_reason="none",
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


def _log_instagram_permissions(access_token):
    try:
        response = _graph_request("me/permissions", access_token, {})
    except InstagramOAuthError:
        _log_instagram_diagnostic(
            logging.WARNING,
            "instagram_oauth.permissions",
            http_status_code=None,
            request_succeeded=False,
            permissions="unavailable",
            graph_error_code=None,
            graph_error_type=None,
            graph_error_subcode=None,
            graph_error_message=None,
        )
        return
    try:
        data = _response_json(response)
    except InstagramOAuthError:
        data = {}
    graph_diagnostics = _graph_error_diagnostics(data, (access_token,))
    request_succeeded = (
        response.status_code == 200 and not isinstance(data.get("error"), dict)
    )
    entries = data.get("data")
    permission_states = []
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = entry.get("permission")
            if name not in INSTAGRAM_DIAGNOSTIC_PERMISSIONS:
                continue
            state = entry.get("status")
            if state not in {"granted", "declined", "expired"}:
                state = "unknown"
            permission_states.append(f"{name}:{state}")
    _log_instagram_diagnostic(
        logging.INFO if request_succeeded else logging.WARNING,
        "instagram_oauth.permissions",
        http_status_code=response.status_code,
        request_succeeded=request_succeeded,
        permissions=",".join(permission_states) or "none",
        **graph_diagnostics,
    )


def _log_instagram_token_debug(access_token, business_context_present):
    """Inspect token metadata without logging token or identifier values."""
    endpoint = (
        f"{INSTAGRAM_GRAPH_URL}/{instagram_api_version()}/debug_token"
    )
    try:
        response = requests.get(
            endpoint,
            params={
                "input_token": access_token,
                "access_token": (
                    f"{settings.SOCIAL_INSTAGRAM_META_APP_ID}|"
                    f"{settings.SOCIAL_INSTAGRAM_META_APP_SECRET}"
                ),
            },
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        _log_instagram_diagnostic(
            logging.WARNING,
            "instagram_oauth.token_debug",
            http_status_code=None,
            request_succeeded=False,
            token_type="unknown",
            token_valid=None,
            app_matches=None,
            business_context_present=business_context_present,
            scope_names="unavailable",
            granular_scope_count=None,
            granular_scope_target_count=None,
            profile_id_present=None,
            **_graph_error_diagnostics({}, (access_token,)),
        )
        return

    try:
        body = _response_json(response)
    except InstagramOAuthError:
        body = {}
    token_data = body.get("data")
    if not isinstance(token_data, dict):
        token_data = {}
    graph_diagnostics = _graph_error_diagnostics(body, (access_token,))
    raw_token_type = token_data.get("type")
    token_type = (
        raw_token_type
        if raw_token_type in {"USER", "SYSTEM_USER", "PAGE", "APP"}
        else "unknown"
    )
    token_valid = token_data.get("is_valid")
    if not isinstance(token_valid, bool):
        token_valid = None
    token_app_id = token_data.get("app_id")
    app_matches = (
        str(token_app_id) == str(settings.SOCIAL_INSTAGRAM_META_APP_ID)
        if token_app_id is not None
        else None
    )
    scopes = token_data.get("scopes")
    scope_names = (
        sorted(
            {
                scope
                for scope in scopes
                if isinstance(scope, str)
                and scope in INSTAGRAM_DIAGNOSTIC_PERMISSIONS
            }
        )
        if isinstance(scopes, list)
        else []
    )
    granular_scopes = token_data.get("granular_scopes")
    if isinstance(granular_scopes, list):
        relevant_scopes = [
            entry
            for entry in granular_scopes
            if isinstance(entry, dict)
            and entry.get("scope") in INSTAGRAM_DIAGNOSTIC_PERMISSIONS
        ]
        granular_scope_count = len(relevant_scopes)
        granular_scope_target_count = sum(
            len(entry.get("target_ids", []))
            for entry in relevant_scopes
            if isinstance(entry.get("target_ids", []), list)
        )
    else:
        granular_scope_count = None
        granular_scope_target_count = None
    profile_id_present = bool(
        token_data.get("profile_id") or token_data.get("user_id")
    )
    request_succeeded = response.status_code == 200 and bool(token_data)
    _log_instagram_diagnostic(
        logging.INFO if request_succeeded else logging.WARNING,
        "instagram_oauth.token_debug",
        http_status_code=response.status_code,
        request_succeeded=request_succeeded,
        token_type=token_type,
        token_valid=token_valid,
        app_matches=app_matches,
        business_context_present=business_context_present,
        scope_names=",".join(scope_names) or "none",
        granular_scope_count=granular_scope_count,
        granular_scope_target_count=granular_scope_target_count,
        profile_id_present=profile_id_present,
        **graph_diagnostics,
    )


def connect_instagram_account(owner_id, code):
    """Connect the Instagram professional accounts authorized for an owner."""
    code_valid = bool(code) and len(code) <= 4096
    _log_instagram_diagnostic(
        logging.INFO if code_valid else logging.WARNING,
        "instagram_oauth.authorization_code_validation",
        code_present=bool(code),
        code_valid=code_valid,
    )
    if not code_valid:
        raise InstagramOAuthError(
            "Meta did not return a valid authorization code."
        )

    access_token, expires_at = _exchange_code(code)
    business_id = _fetch_client_business_id(access_token)
    _log_instagram_permissions(access_token)
    try:
        accounts = _fetch_assigned_instagram_accounts(
            access_token,
            sensitive_values=(code,),
        )
    except InstagramOAuthError:
        _log_instagram_token_debug(access_token, bool(business_id))
        raise
    try:
        encrypted_token = encrypt_social_token(access_token)
    except Exception as error:
        _log_instagram_diagnostic(
            logging.ERROR,
            "instagram_oauth.token_encryption",
            encryption_succeeded=False,
            error_type=type(error).__name__,
            account_count=len(accounts),
        )
        raise
    _log_instagram_diagnostic(
        logging.INFO,
        "instagram_oauth.token_encryption",
        encryption_succeeded=True,
        account_count=len(accounts),
    )
    config_id = settings.SOCIAL_INSTAGRAM_CONFIG_ID

    try:
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
    except Exception as error:
        _log_instagram_diagnostic(
            logging.ERROR,
            "instagram_oauth.database_save",
            save_succeeded=False,
            error_type=type(error).__name__,
            account_count=len(accounts),
        )
        raise

    _log_instagram_diagnostic(
        logging.INFO,
        "instagram_oauth.database_save",
        save_succeeded=True,
        account_count=len(accounts),
    )
    return len(accounts)
