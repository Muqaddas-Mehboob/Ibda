import logging
import re

import requests
from cryptography.fernet import Fernet
from django.conf import settings

from ..models import SocialAccount
from .publishing_errors import PublishingError
from .social_tokens import SocialTokenEncryptionError, decrypt_social_token

logger = logging.getLogger(__name__)

FACEBOOK_FEED_URL = "https://graph.facebook.com/{version}/{page_id}/feed"
REQUEST_TIMEOUT = (5, 30)
MAX_MESSAGE_LENGTH = 63206

# Meta error codes that a retry cannot fix: bad permissions, invalid or
# expired tokens, malformed parameters and blocked Pages.
PERMANENT_ERROR_CODES = frozenset({10, 100, 102, 104, 190, 200, 368, 803})
# Rate limiting and unknown server-side failures are worth retrying.
TRANSIENT_ERROR_CODES = frozenset({1, 2, 4, 17, 32, 341, 613})
GRAPH_VERSION_PATTERN = re.compile(r"v\d+\.\d+")


def _valid_graph_version(value):
    return bool(isinstance(value, str) and GRAPH_VERSION_PATTERN.fullmatch(value))


def facebook_publishing_configuration_error():
    version = settings.SOCIAL_FACEBOOK_GRAPH_API_VERSION
    if not _valid_graph_version(version):
        return (
            "Facebook publishing is not configured: "
            "SOCIAL_FACEBOOK_GRAPH_API_VERSION must use the vNN.N format."
        )

    key = settings.SOCIAL_TOKEN_ENCRYPTION_KEY
    if not key:
        return (
            "Facebook publishing is not configured: "
            "SOCIAL_TOKEN_ENCRYPTION_KEY is missing."
        )
    try:
        Fernet(key.encode("ascii"))
    except (UnicodeEncodeError, ValueError):
        return (
            "Facebook publishing is not configured: "
            "SOCIAL_TOKEN_ENCRYPTION_KEY is not a valid Fernet key."
        )
    return ""


def facebook_publishing_configured():
    return not facebook_publishing_configuration_error()


def build_post_message(post):
    """Combine the post body with its hashtags, within Facebook's limit."""
    parts = [(post.body or "").strip()]
    tags = []
    for value in post.hashtags or []:
        if not isinstance(value, str):
            continue
        cleaned = value.strip().lstrip("#").strip()
        if not cleaned or any(character.isspace() for character in cleaned):
            continue
        tags.append(f"#{cleaned}")
    if tags:
        parts.append(" ".join(tags))
    message = "\n\n".join(part for part in parts if part)
    return message[:MAX_MESSAGE_LENGTH]


def _response_payload(response):
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _graph_error(payload):
    error = payload.get("error")
    if not isinstance(error, dict):
        return "", None
    message = error.get("message")
    code = error.get("code")
    detail = message.strip() if isinstance(message, str) else ""
    return detail, code if isinstance(code, int) else None


def _is_permanent(status_code, code):
    if code in PERMANENT_ERROR_CODES:
        return True
    if code in TRANSIENT_ERROR_CODES:
        return False
    if status_code == 429 or status_code >= 500:
        return False
    return 400 <= status_code < 500


def _redact(text, secret):
    if secret and text and secret in text:
        return text.replace(secret, "[redacted]")
    return text


def publish_facebook_post(scheduled):
    """Publish one scheduled post to its Facebook Page and return the post ID.

    The Page access token is sent in the request body, never in a URL, and is
    never included in error messages, logs or stored error text.
    """
    post = scheduled.post
    account = scheduled.social_account

    if account is None:
        raise PublishingError(
            "No Facebook Page is linked to this scheduled post. "
            "Reschedule it and choose a Page.",
            transient=False,
        )
    if account.platform != SocialAccount.Platform.FACEBOOK_PAGES:
        raise PublishingError(
            "The linked social account is not a Facebook Page.",
            transient=False,
        )
    if account.owner_id != post.brand.owner_id:
        raise PublishingError(
            "The linked Facebook Page does not belong to this content's owner.",
            transient=False,
        )
    if account.status != SocialAccount.Status.CONNECTED:
        raise PublishingError(
            "The Facebook Page connection is no longer active. "
            "Reconnect the Page before publishing.",
            transient=False,
        )

    try:
        access_token = decrypt_social_token(account.access_token_encrypted)
    except SocialTokenEncryptionError:
        raise PublishingError(
            "The stored Facebook Page token could not be read. "
            "Reconnect the Page before publishing.",
            transient=False,
        ) from None
    if not access_token:
        raise PublishingError(
            "No Facebook Page access token is stored. Reconnect the Page.",
            transient=False,
        )

    message = build_post_message(post)
    if not message.strip():
        raise PublishingError(
            "This post has no text to publish to Facebook.",
            transient=False,
        )

    url = FACEBOOK_FEED_URL.format(
        version=settings.SOCIAL_FACEBOOK_GRAPH_API_VERSION,
        page_id=account.platform_account_id,
    )
    try:
        response = requests.post(
            url,
            data={"message": message, "access_token": access_token},
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        # The exception text can embed request details, so it is discarded
        # rather than chained into the stored error message.
        raise PublishingError(
            "Facebook could not be reached. This post will be retried.",
            transient=True,
        ) from None

    payload = _response_payload(response)
    if response.status_code != 200:
        detail, code = _graph_error(payload)
        detail = _redact(detail, access_token)
        reason = (
            f"Facebook rejected the post: {detail}"
            if detail
            else f"Facebook rejected the post (HTTP {response.status_code})."
        )
        raise PublishingError(reason[:1000], transient=not _is_permanent(
            response.status_code,
            code,
        ))

    external_post_id = payload.get("id")
    if not isinstance(external_post_id, str) or not external_post_id:
        raise PublishingError(
            "Facebook did not confirm a published post ID.",
            transient=False,
        )

    logger.info(
        "facebook_publishing.published",
        extra={
            "event": "facebook_publishing.published",
            "platform": account.platform,
            "page_id": account.platform_account_id,
            "scheduled_post_id": str(scheduled.id),
            "external_post_id": external_post_id,
        },
    )
    return external_post_id
