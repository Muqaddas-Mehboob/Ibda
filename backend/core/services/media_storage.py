import logging
import re
import uuid

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SUPABASE_STORAGE_TIMEOUT = (5, 30)
MAX_IMAGE_BYTES = 8 * 1024 * 1024
JPEG_SIGNATURE = b"\xff\xd8\xff"
JPEG_CONTENT_TYPES = frozenset({"image/jpeg", "image/jpg"})
BUCKET_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


class MediaStorageError(Exception):
    """A user-safe media storage failure."""

    def __init__(self, message, status_code=502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def media_storage_bucket():
    return getattr(settings, "SUPABASE_STORAGE_BUCKET", "")


def media_storage_configuration_error():
    url = getattr(settings, "SUPABASE_URL", "")
    key = getattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "")
    bucket = media_storage_bucket()
    if not url or not url.startswith("https://"):
        return (
            "Image uploads are not configured: SUPABASE_URL is missing or "
            "not an HTTPS URL."
        )
    if not key:
        return (
            "Image uploads are not configured: SUPABASE_SERVICE_ROLE_KEY is "
            "missing."
        )
    if not bucket or not BUCKET_NAME_PATTERN.fullmatch(bucket):
        return (
            "Image uploads are not configured: SUPABASE_STORAGE_BUCKET "
            "must be a valid bucket name."
        )
    return ""


def media_storage_configured():
    return not media_storage_configuration_error()


def _public_url(path):
    url = getattr(settings, "SUPABASE_URL", "").rstrip("/")
    return (
        f"{url}/storage/v1/object/public/"
        f"{media_storage_bucket()}/{path}"
    )


def upload_public_image(*, owner_id, image_bytes, content_type):
    """Upload one JPEG and return its public HTTPS URL.

    Instagram fetches the image itself, so the object must live in a public
    bucket. The service-role key stays server-side and is never logged.
    """
    configuration_error = media_storage_configuration_error()
    if configuration_error:
        raise MediaStorageError(configuration_error, status_code=503)

    normalized_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_type not in JPEG_CONTENT_TYPES:
        raise MediaStorageError(
            "Instagram requires a JPEG image. Choose a .jpg or .jpeg file.",
            status_code=415,
        )

    image_bytes = image_bytes or b""
    if not image_bytes:
        raise MediaStorageError("The selected image is empty.", status_code=400)
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise MediaStorageError(
            "The image must be 8 MB or smaller.", status_code=413
        )
    if not image_bytes.startswith(JPEG_SIGNATURE):
        raise MediaStorageError(
            "The selected file is not a valid JPEG image.", status_code=415
        )

    url = getattr(settings, "SUPABASE_URL", "").rstrip("/")
    key = settings.SUPABASE_SERVICE_ROLE_KEY
    path = f"posts/{owner_id}/{uuid.uuid4().hex}.jpg"
    endpoint = (
        f"{url}/storage/v1/object/{media_storage_bucket()}/{path}"
    )
    try:
        response = requests.post(
            endpoint,
            data=image_bytes,
            headers={
                "Authorization": f"Bearer {key}",
                "apikey": key,
                "Content-Type": "image/jpeg",
                "x-upsert": "false",
                "Accept": "application/json",
                "Cache-Control": "max-age=31536000",
            },
            timeout=SUPABASE_STORAGE_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        # The exception text can embed request details, so it is discarded.
        raise MediaStorageError(
            "The image could not be uploaded. Please try again."
        ) from None

    if response.status_code not in (200, 201):
        logger.warning(
            "media_storage.upload_rejected",
            extra={
                "event": "media_storage.upload_rejected",
                "status_code": response.status_code,
            },
        )
        raise MediaStorageError(
            "The image could not be uploaded. Please try again."
        )

    logger.info(
        "media_storage.image_uploaded",
        extra={
            "event": "media_storage.image_uploaded",
            "bucket": media_storage_bucket(),
            "bytes": len(image_bytes),
        },
    )
    return _public_url(path)
