from datetime import datetime, timezone as datetime_timezone
import uuid

import stripe
from django.db import IntegrityError, transaction

from core.models import PaymentTransaction, ProviderWebhookEvent, UserSubscription

from .catalog import get_plan_for_price
from .stripe_gateway import construct_webhook_event


STRIPE_PROVIDER = "stripe"
HANDLED_EVENTS = {
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
}

SUBSCRIPTION_STATUSES = {
    "active": UserSubscription.Status.ACTIVE,
    "trialing": UserSubscription.Status.ACTIVE,
    "past_due": UserSubscription.Status.PAST_DUE,
    "canceled": UserSubscription.Status.CANCELED,
    "unpaid": UserSubscription.Status.FAILED,
    "incomplete": UserSubscription.Status.PENDING,
    "incomplete_expired": UserSubscription.Status.EXPIRED,
    "paused": UserSubscription.Status.FAILED,
}
STATUS_RESTRICTIVENESS = {
    UserSubscription.Status.PENDING: 0,
    UserSubscription.Status.ACTIVE: 1,
    UserSubscription.Status.PAST_DUE: 2,
    UserSubscription.Status.CANCELED: 3,
    UserSubscription.Status.EXPIRED: 3,
    UserSubscription.Status.FAILED: 3,
}


class StripeWebhookProcessingError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


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
    if hasattr(result, "to_dict"):
        return result.to_dict()
    if hasattr(result, "to_dict_recursive"):
        return result.to_dict_recursive()
    return {}


def _subscription_id_from_invoice(invoice):
    direct_id = _identifier(_value(invoice, "subscription"))
    if direct_id:
        return direct_id
    parent = _value(invoice, "parent")
    details = _value(parent, "subscription_details")
    return _identifier(_value(details, "subscription"))


def _event_time(event):
    created = _value(event, "created")
    if isinstance(created, bool) or not isinstance(created, (int, float)):
        raise StripeWebhookProcessingError("Stripe event timestamp is missing.")
    return datetime.fromtimestamp(created, tz=datetime_timezone.utc)


def _local_subscription_from_metadata(metadata, customer_id=None):
    local_id = metadata.get("ibda_subscription_id")
    if local_id:
        try:
            local_id = uuid.UUID(str(local_id))
        except (ValueError, TypeError, AttributeError) as error:
            raise StripeWebhookProcessingError(
                "Invalid local subscription metadata."
            ) from error
        subscription = (
            UserSubscription.objects.select_for_update()
            .filter(id=local_id, provider=STRIPE_PROVIDER)
            .first()
        )
        if subscription is None:
            raise StripeWebhookProcessingError(
                "Checkout subscription was not found.",
                status_code=404,
            )
        owner_id = metadata.get("ibda_owner_id")
        if owner_id and str(subscription.owner_id) != str(owner_id):
            raise StripeWebhookProcessingError(
                "Checkout owner does not match the subscription."
            )
        if (
            customer_id
            and subscription.provider_customer_id
            and subscription.provider_customer_id != customer_id
        ):
            raise StripeWebhookProcessingError(
                "Stripe customer does not match the subscription."
            )
        return subscription

    if customer_id:
        subscription = (
            UserSubscription.objects.select_for_update()
            .filter(
                provider=STRIPE_PROVIDER,
                provider_customer_id=customer_id,
                status=UserSubscription.Status.PENDING,
            )
            .order_by("-created_at")
            .first()
        )
        if subscription:
            return subscription

    raise StripeWebhookProcessingError(
        "Local subscription metadata is missing.",
        status_code=404,
    )


def _set_provider_subscription_id(subscription, provider_subscription_id):
    if not provider_subscription_id:
        raise StripeWebhookProcessingError(
            "Stripe event does not include a subscription ID."
        )
    existing = subscription.provider_subscription_id
    if existing and existing != provider_subscription_id:
        raise StripeWebhookProcessingError(
            "Stripe subscription does not match the local subscription."
        )
    subscription.provider_subscription_id = provider_subscription_id


def _first_subscription_price(subscription_data):
    items = _value(_value(subscription_data, "items"), "data", [])
    if not items:
        return None
    return _identifier(_value(items[0], "price"))


def _period_value(subscription_data, item_key):
    value = _value(subscription_data, item_key)
    if value is not None:
        return value
    items = _value(_value(subscription_data, "items"), "data", [])
    return _value(items[0], item_key) if items else None


def _stripe_datetime(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StripeWebhookProcessingError("Invalid Stripe period timestamp.")
    return datetime.fromtimestamp(value, tz=datetime_timezone.utc)


def _should_apply_status(subscription, status_value, created_at):
    previous_event_at = subscription.last_provider_event_created_at
    if previous_event_at is None or created_at > previous_event_at:
        return True
    if created_at == previous_event_at:
        return STATUS_RESTRICTIVENESS[status_value] > STATUS_RESTRICTIVENESS.get(
            subscription.status,
            3,
        )
    return False


def _sync_subscription(event_type, event, data):
    metadata = _metadata(data)
    customer_id = _identifier(_value(data, "customer"))
    subscription = _local_subscription_from_metadata(metadata, customer_id)
    provider_subscription_id = _identifier(data)
    _set_provider_subscription_id(subscription, provider_subscription_id)

    plan = get_plan_for_price(_first_subscription_price(data))
    if plan is None:
        raise StripeWebhookProcessingError(
            "Stripe subscription price is not in the configured plan catalog."
        )
    subscription.plan_id, subscription.billing_interval = plan

    stripe_status = (
        "canceled"
        if event_type == "customer.subscription.deleted"
        else _value(data, "status")
    )
    mapped_status = SUBSCRIPTION_STATUSES.get(stripe_status)
    if mapped_status is None:
        raise StripeWebhookProcessingError(
            "Stripe subscription status is not supported."
        )

    created_at = _event_time(event)
    if _should_apply_status(subscription, mapped_status, created_at):
        subscription.status = mapped_status
        subscription.current_period_start = _stripe_datetime(
            _period_value(data, "current_period_start")
        )
        subscription.current_period_end = _stripe_datetime(
            _period_value(data, "current_period_end")
        )
        subscription.cancel_at_period_end = bool(
            _value(data, "cancel_at_period_end", False)
        )
        subscription.canceled_at = _stripe_datetime(
            _value(data, "canceled_at")
        )
        subscription.last_provider_event_created_at = created_at
        if customer_id:
            subscription.provider_customer_id = customer_id
        subscription.save()


def _checkout_completed(data):
    metadata = _metadata(data)
    local_reference = metadata.get("ibda_subscription_id") or _value(
        data, "client_reference_id"
    )
    if not local_reference:
        return
    local_metadata = {
        "ibda_subscription_id": local_reference,
        "ibda_owner_id": metadata.get("ibda_owner_id"),
    }
    customer_id = _identifier(_value(data, "customer"))
    subscription = _local_subscription_from_metadata(
        local_metadata,
        customer_id,
    )
    provider_subscription_id = _identifier(_value(data, "subscription"))
    if provider_subscription_id:
        _set_provider_subscription_id(subscription, provider_subscription_id)
    if customer_id:
        subscription.provider_customer_id = customer_id
    if subscription.status != UserSubscription.Status.PENDING:
        return
    subscription.save(
        update_fields=[
            "provider_customer_id",
            "provider_subscription_id",
            "updated_at",
        ]
    )


def _record_invoice(invoice, event_type, event):
    provider_subscription_id = _subscription_id_from_invoice(invoice)
    if not provider_subscription_id:
        raise StripeWebhookProcessingError(
            "Stripe invoice does not reference a subscription."
        )
    subscription = (
        UserSubscription.objects.select_for_update()
        .filter(
            provider=STRIPE_PROVIDER,
            provider_subscription_id=provider_subscription_id,
        )
        .first()
    )
    if subscription is None:
        raise StripeWebhookProcessingError(
            "Local subscription for invoice was not found.",
            status_code=404,
        )

    invoice_id = _identifier(invoice)
    if not invoice_id:
        raise StripeWebhookProcessingError("Stripe invoice ID is missing.")
    transaction_id = invoice_id
    amount = (
        _value(invoice, "amount_paid")
        if event_type == "invoice.paid"
        else _value(invoice, "amount_due")
    )
    status_value = (
        PaymentTransaction.Status.SUCCEEDED
        if event_type == "invoice.paid"
        else PaymentTransaction.Status.FAILED
    )
    occurred_at = _event_time(event)
    existing = PaymentTransaction.objects.filter(
        provider=STRIPE_PROVIDER,
        provider_transaction_id=transaction_id,
    ).first()
    if existing and existing.subscription_id != subscription.id:
        raise StripeWebhookProcessingError(
            "Stripe invoice does not match its existing transaction."
        )
    if existing and existing.occurred_at and occurred_at < existing.occurred_at:
        return
    if (
        existing
        and existing.occurred_at == occurred_at
        and existing.status == PaymentTransaction.Status.SUCCEEDED
        and status_value == PaymentTransaction.Status.FAILED
    ):
        return
    PaymentTransaction.objects.update_or_create(
        provider=STRIPE_PROVIDER,
        provider_transaction_id=transaction_id,
        defaults={
            "subscription": subscription,
            "status": status_value,
            "amount_minor": amount,
            "currency": (_value(invoice, "currency") or "").upper(),
            "occurred_at": occurred_at,
        },
    )
    if (
        event_type == "invoice.payment_failed"
        and subscription.status == UserSubscription.Status.ACTIVE
        and _should_apply_status(
            subscription,
            UserSubscription.Status.PAST_DUE,
            occurred_at,
        )
    ):
        subscription.status = UserSubscription.Status.PAST_DUE
        subscription.last_provider_event_created_at = occurred_at
        subscription.save(
            update_fields=[
                "status",
                "last_provider_event_created_at",
                "updated_at",
            ]
        )


def process_stripe_event(payload, signature):
    event = construct_webhook_event(payload, signature)
    if _value(event, "livemode") is not False:
        raise StripeWebhookProcessingError(
            "Live-mode Stripe events are disabled.",
            status_code=400,
        )
    event_id = _value(event, "id")
    event_type = _value(event, "type")
    if not event_id or not event_type:
        raise StripeWebhookProcessingError("Malformed Stripe event.")
    _event_time(event)
    data = _value(_value(event, "data"), "object")
    if event_type in HANDLED_EVENTS and data is None:
        raise StripeWebhookProcessingError("Stripe event data is missing.")

    try:
        with transaction.atomic():
            _, created = ProviderWebhookEvent.objects.get_or_create(
                provider=STRIPE_PROVIDER,
                event_id=event_id,
                defaults={"event_type": event_type},
            )
            if not created:
                return {"received": True, "duplicate": True}

            if event_type == "checkout.session.completed":
                _checkout_completed(data)
            elif event_type.startswith("customer.subscription."):
                _sync_subscription(event_type, event, data)
            elif event_type in ("invoice.paid", "invoice.payment_failed"):
                _record_invoice(data, event_type, event)
    except IntegrityError as error:
        raise StripeWebhookProcessingError(
            "Stripe event conflicts with existing billing data.",
            status_code=409,
        ) from error

    return {"received": True, "duplicate": False}
