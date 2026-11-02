import logging
from urllib.parse import urlsplit

from django.conf import settings

from .stripe_gateway import retrieve_price_details

logger = logging.getLogger(__name__)


PLAN_DEFINITIONS = (
    ("starter", "Starter"),
    ("pro", "Pro"),
    ("enterprise", "Enterprise"),
)

BILLING_INTERVALS = ("monthly", "annual")

PRICE_SETTINGS = {
    ("starter", "monthly"): "STRIPE_PRICE_STARTER_MONTHLY",
    ("starter", "annual"): "STRIPE_PRICE_STARTER_ANNUAL",
    ("pro", "monthly"): "STRIPE_PRICE_PRO_MONTHLY",
    ("pro", "annual"): "STRIPE_PRICE_PRO_ANNUAL",
    ("enterprise", "monthly"): "STRIPE_PRICE_ENTERPRISE_MONTHLY",
    ("enterprise", "annual"): "STRIPE_PRICE_ENTERPRISE_ANNUAL",
}


def get_price_id(plan_id, billing_interval):
    setting_name = PRICE_SETTINGS[(plan_id, billing_interval)]
    return getattr(settings, setting_name, "").strip()


def get_plan_for_price(price_id):
    if not price_id:
        return None

    matches = []
    for (plan_id, billing_interval), setting_name in PRICE_SETTINGS.items():
        if getattr(settings, setting_name, "").strip() == price_id:
            matches.append((plan_id, billing_interval))
    return matches[0] if len(matches) == 1 else None


def checkout_configuration_present():
    return bool(
        getattr(settings, "STRIPE_SECRET_KEY", "").startswith("sk_test_")
        and getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
        and any(
            get_checkout_redirect_urls(platform) is not None
            for platform in ("web", "mobile")
        )
        and any(
            get_price_id(plan_id, interval)
            for plan_id, interval in PRICE_SETTINGS
        )
    )


def get_checkout_redirect_urls(platform):
    if platform == "web":
        success_url = (
            getattr(settings, "STRIPE_CHECKOUT_SUCCESS_URL_WEB", "")
            or getattr(settings, "STRIPE_CHECKOUT_SUCCESS_URL", "")
        )
        cancel_url = (
            getattr(settings, "STRIPE_CHECKOUT_CANCEL_URL_WEB", "")
            or getattr(settings, "STRIPE_CHECKOUT_CANCEL_URL", "")
        )
        if not (
            _is_web_return_url(success_url, "/subscription/success")
            and _is_web_return_url(cancel_url, "/subscription/cancel")
        ):
            return None
    elif platform == "mobile":
        success_url = getattr(settings, "STRIPE_CHECKOUT_SUCCESS_URL_MOBILE", "")
        cancel_url = getattr(settings, "STRIPE_CHECKOUT_CANCEL_URL_MOBILE", "")
        if not (
            _is_mobile_return_url(success_url)
            and _is_mobile_return_url(cancel_url)
        ):
            return None
    else:
        return None

    return (success_url, cancel_url) if success_url and cancel_url else None


def _is_web_return_url(url, expected_path):
    if not url:
        return False
    parts = urlsplit(url)
    allowed_schemes = {"https"}
    if settings.DEBUG:
        allowed_schemes.add("http")
    return bool(
        parts.scheme in allowed_schemes
        and parts.netloc
        and not parts.username
        and not parts.password
        and parts.path.rstrip("/") == expected_path
    )


def _is_mobile_return_url(url):
    if not url:
        return False
    parts = urlsplit(url)
    route_path = (
        f"/{parts.netloc}{parts.path}".rstrip("/")
        if parts.netloc
        else parts.path.rstrip("/")
    )
    return bool(parts.scheme == "ibda" and route_path == "/subscription/success")


def get_plan_catalog(platform="web"):
    stripe_configured = getattr(
        settings, "STRIPE_SECRET_KEY", ""
    ).startswith("sk_test_")
    webhook_configured = bool(getattr(settings, "STRIPE_WEBHOOK_SECRET", ""))
    redirect_urls_configured = get_checkout_redirect_urls(platform) is not None
    plans = []
    missing_configuration = []

    for plan_id, name in PLAN_DEFINITIONS:
        prices = {}
        for billing_interval in BILLING_INTERVALS:
            price_id = get_price_id(plan_id, billing_interval)
            price_details = (
                retrieve_price_details(price_id)
                if stripe_configured and price_id
                else None
            )
            price_id_configured = bool(price_id)
            expected_stripe_interval = (
                "month" if billing_interval == "monthly" else "year"
            )
            price_interval_matches = bool(
                price_details
                and price_details["recurring_interval"] == expected_stripe_interval
                and price_details["recurring_interval_count"] == 1
            )
            price_configured = bool(
                price_id_configured
                and price_details
                and price_details["active"]
                and price_interval_matches
                and get_plan_for_price(price_id) == (plan_id, billing_interval)
            )
            checkout_available = (
                stripe_configured
                and webhook_configured
                and price_configured
                and redirect_urls_configured
            )
            prices[billing_interval] = {
                "price_minor": (
                    price_details["price_minor"] if price_details else None
                ),
                "currency": price_details["currency"] if price_details else None,
                "checkout_available": checkout_available,
            }
            if not price_id_configured:
                missing_configuration.append(
                    f"{plan_id}_{billing_interval}_stripe_price"
                )
            elif stripe_configured and not price_details:
                missing_configuration.append(
                    f"{plan_id}_{billing_interval}_stripe_price_unavailable"
                )
            elif price_details and not price_details["active"]:
                missing_configuration.append(
                    f"{plan_id}_{billing_interval}_stripe_price_inactive"
                )
            elif price_details and not price_interval_matches:
                missing_configuration.append(
                    f"{plan_id}_{billing_interval}_stripe_price_interval_mismatch"
                )
            elif price_id_configured and get_plan_for_price(price_id) is None:
                missing_configuration.append(
                    f"{plan_id}_{billing_interval}_stripe_price_id_duplicated"
                )

        plans.append(
            {
                "id": plan_id,
                "name": name,
                "description": None,
                "features": [],
                "features_configured": False,
                "prices": prices,
                "billing_intervals": list(BILLING_INTERVALS),
                "checkout_available": any(
                    price["checkout_available"] for price in prices.values()
                ),
            }
        )

    if not stripe_configured:
        missing_configuration.append("stripe_test_secret_key")
    if not webhook_configured:
        missing_configuration.append("stripe_webhook_secret")
    if not redirect_urls_configured:
        missing_configuration.append("stripe_checkout_return_urls")
    missing_configuration.append("plan_features")

    available_price_count = sum(
        price["checkout_available"]
        for plan in plans
        for price in plan["prices"].values()
    )
    configured_price_count = sum(
        bool(get_price_id(plan_id, interval))
        for plan_id, interval in PRICE_SETTINGS
    )
    logger.info(
        "Stripe catalog readiness: test_secret=%s webhook_secret=%s "
        "platform=%s return_urls=%s configured_prices=%d available_prices=%d",
        stripe_configured,
        webhook_configured,
        platform,
        redirect_urls_configured,
        configured_price_count,
        available_price_count,
    )

    return {
        "plans": plans,
        "provider_configured": stripe_configured,
        "checkout_available": any(
            plan["checkout_available"] for plan in plans
        ),
        "missing_configuration": missing_configuration,
        "message": (
            "Plan features and prices are not included until explicitly "
            "configured. Checkout is available only for configured prices."
        ),
    }
