import logging
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from ..models import SocialAccount
from .instagram_oauth import (
    INSTAGRAM_GRAPH_URL,
    InstagramOAuthError,
    instagram_api_version,
    instagram_oauth_configuration_error,
    refresh_instagram_token,
)
from .media_storage import media_storage_configuration_error
from .publishing_errors import PublishingError
from .social_tokens import SocialTokenEncryptionError, decrypt_social_token

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = (5, 30)
MAX_CAPTION_LENGTH = 2200
MAX_HASHTAGS = 30
CONTAINER_POLL_ATTEMPTS = 10
CONTAINER_POLL_SECONDS = 2
TOKEN_REFRESH_WINDOW = timedelta(days=7)
READY_CONTAINER_STATES = frozenset({"FINISHED", "PUBLISHED"})
FAILED_CONTAINER_STATES = frozenset({"ERROR", "EXPIRED"})

PERMANENT_ERROR_CODES = frozenset({10, 100, 102, 104, 190, 200, 368, 803})
TRANSIENT_ERROR_CODES = frozenset({1, 2, 4, 17, 32, 341, 613})


def instagram_publishing_configuration_error():
    oauth_error = instagram_oauth_configuration_error()
    if oauth_error:
        return f"Instagram publishing is not configured: {oauth_error}"
    storage_error = media_storage_configuration_error()
    if storage_error:
        return f"Instagram publishing is not configured: {storage_error}"
    return ""


def instagram_publishing_configured():
    return not instagram_publishing_configuration_error()


def build_instagram_caption(post):
    """Combine the post body with its hashtags within Instagram's limits."""
    parts = [(post.body or "").strip()]
    tags = []
    for value in post.hashtags or []:
        if not isinstance(value, str):
            continue
        cleaned = value.strip().lstrip("#").strip()
        if not cleaned or any(character.isspace() for character in cleaned):
            continue
        tags.append(f"#{cleaned}")
        if len(tags) >= MAX_HASHTAGS:
            break
    if tags:
        parts.append(" ".join(tags))
    caption = "\n\n".join(part for part in parts if part)
    return caption[:MAX_CAPTION_LENGTH]


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


def _rejection(response, access_token):
    detail, code = _graph_error(_response_payload(response))
    detail = _redact(detail, access_token)
    reason = (
        f"Instagram rejected the post: {detail}"
        if detail
        else f"Instagram rejected the post (HTTP {response.status_code})."
    )
    return PublishingError(
        reason[:1000],
        transient=not _is_permanent(response.status_code, code),
    )


def _account_access_token(account):
    if account.status != SocialAccount.Status.CONNECTED:
        raise PublishingError(
            "The Instagram connection is no longer active. "
            "Reconnect the account before publishing.",
            transient=False,
        )
    try:
        token = decrypt_social_token(account.access_token_encrypted)
    except SocialTokenEncryptionError:
        raise PublishingError(
            "The stored Instagram token could not be read. "
            "Reconnect the account before publishing.",
            transient=False,
        ) from None
    if not token:
        raise PublishingError(
            "No Instagram access token is stored. Reconnect the account.",
            transient=False,
        )

    expires_at = account.token_expires_at
    if expires_at and expires_at <= timezone.now():
        raise PublishingError(
            "The Instagram authorization has expired. Reconnect the account "
            "before publishing.",
            transient=False,
        )
    if expires_at and expires_at <= timezone.now() + TOKEN_REFRESH_WINDOW:
        try:
            return refresh_instagram_token(account)
        except InstagramOAuthError:
            # The current token may still be valid; let Meta decide.
            logger.warning(
                "instagram_publishing.token_refresh_failed",
                extra={
                    "event": "instagram_publishing.token_refresh_failed",
                    "account_id": str(account.id),
                },
            )
    return token


def _create_container(version, account_id, image_url, caption, access_token):
    endpoint = f"{INSTAGRAM_GRAPH_URL}/{version}/{account_id}/media"
    try:
        response = requests.post(
            endpoint,
            data={
                "image_url": image_url,
                "caption": caption,
                "access_token": access_token,
            },
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise PublishingError(
            "Instagram could not be reached. This post will be retried.",
            transient=True,
        ) from None

    if response.status_code != 200:
        raise _rejection(response, access_token)

    container_id = _response_payload(response).get("id")
    if not isinstance(container_id, str) or not container_id:
        raise PublishingError(
            "Instagram did not confirm a media container.",
            transient=False,
        )
    return container_id


def _wait_for_container(version, container_id, access_token):
    endpoint = f"{INSTAGRAM_GRAPH_URL}/{version}/{container_id}"
    for attempt in range(CONTAINER_POLL_ATTEMPTS):
        try:
            response = requests.get(
                endpoint,
                params={"fields": "status_code"},
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
            )
        except requests.RequestException:
            raise PublishingError(
                "Instagram could not be reached. This post will be retried.",
                transient=True,
            ) from None

        if response.status_code != 200:
            raise _rejection(response, access_token)

        status_code = _response_payload(response).get("status_code")
        if isinstance(status_code, str) and status_code in READY_CONTAINER_STATES:
            return
        if (
            isinstance(status_code, str)
            and status_code in FAILED_CONTAINER_STATES
        ):
            raise PublishingError(
                "Instagram could not process the image. "
                "Check that it is a public JPEG and try again.",
                transient=False,
            )
        if attempt < CONTAINER_POLL_ATTEMPTS - 1:
            time.sleep(CONTAINER_POLL_SECONDS)

    raise PublishingError(
        "Instagram is still processing the image. This post will be retried.",
        transient=True,
    )


def _publish_container(version, account_id, container_id, access_token):
    endpoint = (
        f"{INSTAGRAM_GRAPH_URL}/{version}/{account_id}/media_publish"
    )
    try:
        response = requests.post(
            endpoint,
            data={
                "creation_id": container_id,
                "access_token": access_token,
            },
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise PublishingError(
            "Instagram could not be reached. This post will be retried.",
            transient=True,
        ) from None

    if response.status_code != 200:
        raise _rejection(response, access_token)

    media_id = _response_payload(response).get("id")
    if not isinstance(media_id, str) or not media_id:
        raise PublishingError(
            "Instagram did not confirm a published post ID.",
            transient=False,
        )
    return media_id


def publish_instagram_post(scheduled):
    """Publish one scheduled image post to its Instagram account.

    The image must already be a public HTTPS JPEG. The access token is sent in
    request bodies (or an Authorization header for reads), never in a URL, and
    is redacted from any stored error text.
    """
    post = scheduled.post
    account = scheduled.social_account

    if account is None:
        raise PublishingError(
            "No Instagram account is linked to this scheduled post. "
            "Reschedule it and choose an account.",
            transient=False,
        )
    if account.platform != SocialAccount.Platform.INSTAGRAM:
        raise PublishingError(
            "The linked social account is not an Instagram account.",
            transient=False,
        )
    if account.owner_id != post.brand.owner_id:
        raise PublishingError(
            "The linked Instagram account does not belong to this content's "
            "owner.",
            transient=False,
        )

    image_url = (post.image_url or "").strip()
    if not image_url or not image_url.startswith("https://"):
        raise PublishingError(
            "This post has no public image. Attach a JPEG image in Studio "
            "before publishing to Instagram.",
            transient=False,
        )

    caption = build_instagram_caption(post)
    if not caption.strip():
        raise PublishingError(
            "This post has no caption to publish to Instagram.",
            transient=False,
        )

    access_token = _account_access_token(account)
    version = instagram_api_version()
    if not version:
        raise PublishingError(
            "Instagram publishing is not configured correctly.",
            transient=False,
        )

    container_id = _create_container(
        version,
        account.platform_account_id,
        image_url,
        caption,
        access_token,
    )
    _wait_for_container(version, container_id, access_token)
    media_id = _publish_container(
        version,
        account.platform_account_id,
        container_id,
        access_token,
    )

    logger.info(
        "instagram_publishing.published",
        extra={
            "event": "instagram_publishing.published",
            "platform": account.platform,
            "instagram_account_id": account.platform_account_id,
            "scheduled_post_id": str(scheduled.id),
            "external_post_id": media_id,
        },
    )
    return media_id
