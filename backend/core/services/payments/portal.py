import logging
from urllib.parse import urlsplit

from django.conf import settings

from core.models import UserSubscription

from .stripe_gateway import create_billing_portal_session

logger = logging.getLogger(__name__)


class PortalUnavailable(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def get_portal_return_url(platform):
    fallback = getattr(settings, "STRIPE_PORTAL_RETURN_URL", "").strip()
    if platform == "web":
        url = (
            getattr(settings, "STRIPE_PORTAL_RETURN_URL_WEB", "").strip()
            or fallback
        )
    elif platform == "mobile":
        url = (
            getattr(settings, "STRIPE_PORTAL_RETURN_URL_MOBILE", "").strip()
            or fallback
        )
    else:
        return None

    return url if _is_valid_portal_return_url(url, platform) else None


def _is_valid_portal_return_url(url, platform):
    if not url:
        return False

    parts = urlsplit(url)
    if parts.username or parts.password:
        return False

    if platform == "web":
        allowed_schemes = {"https"}
        if settings.DEBUG:
            allowed_schemes.add("http")
        return parts.scheme in allowed_schemes and bool(parts.netloc)

    # Mobile builds return through the app scheme on the billing screen; an
    # https fallback is accepted so the browser session still closes back into
    # the app's refresh flow.
    route_path = (
        f"/{parts.netloc}{parts.path}".rstrip("/")
        if parts.netloc
        else parts.path.rstrip("/")
    )
    if parts.scheme == "ibda":
        return route_path == "/subscription"
    return parts.scheme == "https" and bool(parts.netloc)


def start_billing_portal(*, owner_id, platform):
    """Creates a Stripe Customer Portal session for the owner's subscription.

    The customer ID comes only from the authenticated owner's local
    subscription record; the client never supplies it.
    """
    if not getattr(settings, "STRIPE_SECRET_KEY", "").strip():
        raise PortalUnavailable("not_configured")

    return_url = get_portal_return_url(platform)
    if not return_url:
        raise PortalUnavailable("return_url")

    subscription = (
        UserSubscription.objects.filter(
            owner_id=owner_id,
            provider="stripe",
            status__in=(
                UserSubscription.Status.ACTIVE,
                UserSubscription.Status.PAST_DUE,
            ),
        )
        .order_by("-created_at")
        .first()
    )
    if subscription is None:
        raise PortalUnavailable("no_subscription")

    customer_id = (subscription.provider_customer_id or "").strip()
    if not customer_id:
        raise PortalUnavailable("customer_missing")

    session = create_billing_portal_session(
        customer_id=customer_id,
        return_url=return_url,
    )
    url = getattr(session, "url", None)
    if not url:
        raise PortalUnavailable("session_missing")

    logger.info(
        "Stripe billing portal session created: platform=%s provider=stripe",
        platform,
    )
    return url
