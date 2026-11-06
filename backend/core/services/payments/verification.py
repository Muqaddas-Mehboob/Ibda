from datetime import datetime, timezone as datetime_timezone

from django.db.models import Q

from core.models import PaymentTransaction, UserSubscription
from core.models import StripeCheckoutAttempt

from .catalog import PLAN_DEFINITIONS
from .stripe_gateway import retrieve_checkout_session
from .transactions import StripeTransactionConflict, upsert_stripe_transaction


STRIPE_PROVIDER = "stripe"


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


def _plan_name(plan_id):
    return next(
        (name for configured_id, name in PLAN_DEFINITIONS if configured_id == plan_id),
        "",
    )


def verify_checkout_session(*, owner_id, session_id):
    session = retrieve_checkout_session(session_id)
    if _identifier(session) != session_id:
        raise CheckoutSessionNotFound
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

    attempt = StripeCheckoutAttempt.objects.filter(
        checkout_session_id=session_id,
        owner_id=owner_id,
        subscription=subscription,
    ).first()
    if attempt is None:
        if subscription.checkout_session_id and subscription.checkout_session_id != session_id:
            raise CheckoutSessionNotFound
        attempt, _ = StripeCheckoutAttempt.objects.get_or_create(
            checkout_session_id=session_id,
            defaults={
                "owner_id": owner_id,
                "subscription": subscription,
                "customer_id": subscription.provider_customer_id,
                "plan_id": subscription.plan_id,
                "price_id": "",
                "billing_interval": subscription.billing_interval,
                "stripe_created_at": (
                    datetime.fromtimestamp(
                        _value(session, "created"),
                        tz=datetime_timezone.utc,
                    )
                    if _value(session, "created")
                    else None
                ),
                "expires_at": (
                    datetime.fromtimestamp(
                        _value(session, "expires_at"),
                        tz=datetime_timezone.utc,
                    )
                    if _value(session, "expires_at")
                    else None
                ),
            },
        )
        if (
            attempt.owner_id != owner_id
            or attempt.subscription_id != subscription.id
            or attempt.customer_id != subscription.provider_customer_id
            or attempt.plan_id != subscription.plan_id
            or attempt.billing_interval != subscription.billing_interval
        ):
            raise CheckoutSessionNotFound
    elif (
        attempt.customer_id != subscription.provider_customer_id
        or attempt.plan_id != subscription.plan_id
        or attempt.billing_interval != subscription.billing_interval
    ):
        raise CheckoutSessionNotFound

    if stripe_subscription_id and not subscription.provider_subscription_id:
        subscription.provider_subscription_id = stripe_subscription_id
        if not subscription.checkout_session_id:
            subscription.checkout_session_id = session_id
        subscription.save(
            update_fields=[
                "provider_subscription_id",
                "checkout_session_id",
                "updated_at",
            ]
        )

    session_status = _value(session, "status")
    payment_status = _value(session, "payment_status")
    invoice_id = _identifier(_value(session, "invoice"))
    payment_intent_id = _identifier(_value(session, "payment_intent"))
    if session_status == "expired" or (
        session_status == "complete" and payment_status in ("paid", "unpaid")
    ):
        transaction_id = invoice_id or payment_intent_id or session_id
        transaction_status = (
            PaymentTransaction.Status.FAILED
            if session_status == "expired"
            else (
                PaymentTransaction.Status.SUCCEEDED
                if payment_status == "paid"
                else PaymentTransaction.Status.PENDING
            )
        )
        try:
            upsert_stripe_transaction(
                subscription=subscription,
                transaction_id=transaction_id,
                values={
                    "provider_customer_id": customer_id,
                    "checkout_session_id": session_id,
                    "provider_payment_intent_id": payment_intent_id or "",
                    "provider_invoice_id": invoice_id or "",
                    "provider_subscription_id": stripe_subscription_id or "",
                    "plan_id": subscription.plan_id,
                    "plan_name": _plan_name(subscription.plan_id),
                    "billing_interval": subscription.billing_interval,
                    "transaction_type": PaymentTransaction.TransactionType.INITIAL_PAYMENT,
                    "status": transaction_status,
                    "amount_minor": _value(session, "amount_total"),
                    "currency": (_value(session, "currency") or "").upper(),
                    "occurred_at": (
                        datetime.fromtimestamp(
                            _value(session, "created"),
                            tz=datetime_timezone.utc,
                        )
                        if _value(session, "created")
                        else None
                    ),
                },
            )
        except StripeTransactionConflict as error:
            raise CheckoutSessionNotFound from error

    transactions = PaymentTransaction.objects.filter(
        subscription=subscription,
        provider=STRIPE_PROVIDER,
    )
    matching_transactions = transactions.filter(
        Q(checkout_session_id=session_id)
        | Q(provider_transaction_id=session_id)
    )
    if invoice_id:
        matching_transactions = matching_transactions | transactions.filter(
            provider_invoice_id=invoice_id
        )
    if payment_intent_id:
        matching_transactions = matching_transactions | transactions.filter(
            provider_payment_intent_id=payment_intent_id
        )
    successful_payment = matching_transactions.filter(
        status=PaymentTransaction.Status.SUCCEEDED
    ).order_by("-occurred_at", "-created_at").first()
    latest_transaction = (
        matching_transactions.order_by("-occurred_at", "-created_at").first()
    )

    if session_status == "expired":
        verification_status = "failed"
    elif (
        session_status == "complete"
        and payment_status == "paid"
        and successful_payment is not None
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
