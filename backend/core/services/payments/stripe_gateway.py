import logging

import stripe
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def _client():
    return stripe.StripeClient(
        settings.STRIPE_SECRET_KEY,
        http_client=stripe.RequestsClient(timeout=10),
        max_network_retries=2,
    )


def create_customer(owner_id, email):
    return _client().v1.customers.create(
        {
            "email": email or None,
            "metadata": {"ibda_owner_id": str(owner_id)},
        },
        options={"idempotency_key": f"ibda-customer-{owner_id}"},
    )


def create_checkout_session(
    *,
    customer_id,
    price_id,
    plan_id,
    billing_interval,
    local_subscription_id,
    owner_id,
    idempotency_key,
    success_url,
    cancel_url,
):
    metadata = {
        "ibda_owner_id": str(owner_id),
        "ibda_subscription_id": str(local_subscription_id),
        "plan_id": plan_id,
        "billing_interval": billing_interval,
    }
    return _client().v1.checkout.sessions.create(
        {
            "mode": "subscription",
            "customer": customer_id,
            "client_reference_id": str(local_subscription_id),
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": metadata,
            "subscription_data": {"metadata": metadata},
        },
        options={"idempotency_key": idempotency_key},
    )


def retrieve_checkout_session(session_id):
    return _client().v1.checkout.sessions.retrieve(session_id)


def retrieve_subscription(subscription_id):
    return _client().v1.subscriptions.retrieve(subscription_id)


def list_customer_subscriptions(customer_id):
    """Read-only: lists every Stripe subscription for a customer."""
    subscriptions = []
    starting_after = None
    while True:
        params = {
            "customer": customer_id,
            "status": "all",
            "limit": 100,
        }
        if starting_after:
            params["starting_after"] = starting_after
        page = _client().v1.subscriptions.list(params)
        data = getattr(page, "data", []) or []
        subscriptions.extend(data)
        if not getattr(page, "has_more", False) or not data:
            break
        starting_after = getattr(data[-1], "id", None)
        if not starting_after:
            break
    return subscriptions


def retrieve_event(event_id):
    """Read-only: retrieves a Stripe event for administrative reprocessing."""
    return _client().v1.events.retrieve(event_id)


def update_subscription(subscription_id, params):
    return _client().v1.subscriptions.update(subscription_id, params)


def cancel_subscription(subscription_id):
    return _client().v1.subscriptions.cancel(subscription_id)


def create_billing_portal_session(*, customer_id, return_url):
    return _client().v1.billing_portal.sessions.create(
        {
            "customer": customer_id,
            "return_url": return_url,
        }
    )


def retrieve_price_details(price_id):
    cache_key = f"stripe-price-catalog:{price_id}"
    cached = cache.get(cache_key, None)
    if cached is not None:
        return cached
    try:
        price = _client().v1.prices.retrieve(price_id)
    except stripe.StripeError as error:
        logger.warning(
            "Stripe Price lookup failed: category=stripe_api error_type=%s",
            type(error).__name__,
        )
        cache.set(cache_key, False, timeout=30)
        return None

    details = {
        "price_minor": price.unit_amount,
        "currency": price.currency.upper() if price.currency else None,
        "active": bool(price.active and not price.livemode),
        "recurring_interval": (
            price.recurring.interval if price.recurring else None
        ),
        "recurring_interval_count": (
            price.recurring.interval_count if price.recurring else None
        ),
    }
    cache.set(cache_key, details, timeout=300)
    return details


def construct_webhook_event(payload, signature):
    return stripe.Webhook.construct_event(
        payload,
        signature,
        settings.STRIPE_WEBHOOK_SECRET,
    )
