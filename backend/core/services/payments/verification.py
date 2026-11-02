from core.models import PaymentTransaction, UserSubscription

from .stripe_gateway import retrieve_checkout_session


STRIPE_PROVIDER = "stripe"
SUCCESS_SUBSCRIPTION_STATUSES = {
    UserSubscription.Status.ACTIVE,
    UserSubscription.Status.PAST_DUE,
    UserSubscription.Status.CANCELED,
    UserSubscription.Status.EXPIRED,
}


class CheckoutSessionNotFound(Exception):
    pass


def _value(value, key, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _identifier(value):
    if isinstance(value, str):
        return value
    return _value(value, "id")


def _metadata(value):
    result = _value(value, "metadata", {})
    if isinstance(result, dict):
        return result
    if hasattr(result, "items"):
        return dict(result.items())
    return {}


def verify_checkout_session(*, owner_id, session_id):
    session = retrieve_checkout_session(session_id)
    metadata = _metadata(session)
    local_subscription_id = metadata.get("ibda_subscription_id")

    if (
        _value(session, "mode") != "subscription"
        or metadata.get("ibda_owner_id") != str(owner_id)
        or not local_subscription_id
        or _value(session, "client_reference_id") != local_subscription_id
    ):
        raise CheckoutSessionNotFound

    subscription = UserSubscription.objects.filter(
        id=local_subscription_id,
        owner_id=owner_id,
        provider=STRIPE_PROVIDER,
    ).first()
    if (
        subscription is None
        or metadata.get("plan_id") != subscription.plan_id
        or metadata.get("billing_interval") != subscription.billing_interval
    ):
        raise CheckoutSessionNotFound

    customer_id = _identifier(_value(session, "customer"))
    if not customer_id or customer_id != subscription.provider_customer_id:
        raise CheckoutSessionNotFound

    stripe_subscription_id = _identifier(_value(session, "subscription"))
    if (
        stripe_subscription_id
        and subscription.provider_subscription_id
        and stripe_subscription_id != subscription.provider_subscription_id
    ):
        raise CheckoutSessionNotFound

    transactions = PaymentTransaction.objects.filter(
        subscription=subscription,
        provider=STRIPE_PROVIDER,
    )
    successful_payment = (
        transactions.filter(status=PaymentTransaction.Status.SUCCEEDED)
        .order_by("-occurred_at", "-created_at")
        .first()
    )
    latest_transaction = (
        transactions.order_by("-occurred_at", "-created_at").first()
    )

    session_status = _value(session, "status")
    payment_status = _value(session, "payment_status")
    if session_status == "expired":
        verification_status = "failed"
    elif (
        session_status == "complete"
        and payment_status == "paid"
        and successful_payment is not None
        and subscription.status in SUCCESS_SUBSCRIPTION_STATUSES
    ):
        verification_status = "success"
    elif (
        session_status == "complete"
        and payment_status == "no_payment_required"
        and subscription.status == UserSubscription.Status.ACTIVE
    ):
        verification_status = "success"
    elif (
        latest_transaction
        and latest_transaction.status == PaymentTransaction.Status.FAILED
    ) or (
        subscription.status
        in (UserSubscription.Status.FAILED, UserSubscription.Status.EXPIRED)
        and payment_status != "paid"
    ):
        verification_status = "failed"
    else:
        verification_status = "pending"

    payment = successful_payment if verification_status == "success" else None
    return {
        "status": verification_status,
        "plan_id": subscription.plan_id,
        "billing_interval": subscription.billing_interval,
        "payment_status": (
            "succeeded"
            if payment
            else (
                "no_payment_required"
                if verification_status == "success"
                else (
                    "failed"
                    if verification_status == "failed"
                    else "pending"
                )
            )
        ),
        "subscription_status": subscription.status,
        "amount_minor": (
            payment.amount_minor
            if payment
            else (
                _value(session, "amount_total")
                if verification_status == "success"
                else None
            )
        ),
        "currency": (
            payment.currency
            if payment
            else (
                (_value(session, "currency") or "").upper()
                if verification_status == "success"
                else ""
            )
        ),
        "paid_at": payment.occurred_at if payment else None,
        "current_period_end": subscription.current_period_end,
        "cancel_at_period_end": subscription.cancel_at_period_end,
    }
