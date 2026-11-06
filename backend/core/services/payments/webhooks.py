from datetime import datetime, timezone as datetime_timezone
import logging
import uuid
from urllib.parse import urlsplit

import stripe
from django.db import IntegrityError, transaction

from core.models import (
    PaymentTransaction,
    ProviderWebhookEvent,
    StripeCheckoutAttempt,
    UserSubscription,
)

from .catalog import PLAN_DEFINITIONS, get_plan_for_price
from .stripe_gateway import construct_webhook_event, retrieve_event
from .transactions import StripeTransactionConflict, upsert_stripe_transaction


logger = logging.getLogger(__name__)


STRIPE_PROVIDER = "stripe"
HANDLED_EVENTS = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
    "charge.refunded",
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


class UnknownStripePrice(StripeWebhookProcessingError):
    """A recognized configuration gap: the event is durable but not applied."""

    def __init__(self, price_id):
        super().__init__(
            "Stripe subscription price is not in the configured plan catalog."
        )
        self.price_id = price_id


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


def _plan_name(plan_id):
    return next(
        (name for configured_id, name in PLAN_DEFINITIONS if configured_id == plan_id),
        "",
    )


def _safe_receipt_url(value):
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
    except (TypeError, ValueError):
        return ""
    return value if parsed.scheme == "https" and parsed.netloc else ""


def _transaction_values(subscription, **values):
    values.setdefault("provider_customer_id", subscription.provider_customer_id)
    values.setdefault("provider_subscription_id", subscription.provider_subscription_id or "")
    values.setdefault("plan_id", subscription.plan_id)
    values.setdefault("plan_name", _plan_name(subscription.plan_id))
    values.setdefault("billing_interval", subscription.billing_interval)
    return values


def _persist_transaction(**kwargs):
    try:
        return upsert_stripe_transaction(**kwargs)
    except StripeTransactionConflict as error:
        raise StripeWebhookProcessingError(str(error), status_code=409) from error


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

    price_id = _first_subscription_price(data)
    plan = get_plan_for_price(price_id)
    if plan is None:
        raise UnknownStripePrice(price_id)
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


def _checkout_completed(event_type, event, data):
    if _value(data, "mode") != "subscription":
        raise StripeWebhookProcessingError(
            "Stripe checkout session is not a subscription."
        )

    metadata = _metadata(data)
    local_reference = metadata.get("ibda_subscription_id")
    client_reference = _value(data, "client_reference_id")
    if not local_reference or str(local_reference) != str(client_reference):
        raise StripeWebhookProcessingError(
            "Stripe checkout references do not match."
        )
    if not metadata.get("ibda_owner_id"):
        raise StripeWebhookProcessingError(
            "Stripe checkout owner metadata is missing."
        )

    local_metadata = {
        "ibda_subscription_id": local_reference,
        "ibda_owner_id": metadata.get("ibda_owner_id"),
    }
    customer_id = _identifier(_value(data, "customer"))
    if not customer_id:
        raise StripeWebhookProcessingError(
            "Stripe checkout customer is missing."
        )
    subscription = _local_subscription_from_metadata(
        local_metadata,
        customer_id,
    )
    session_id = _identifier(data)
    if not session_id:
        raise StripeWebhookProcessingError(
            "Stripe checkout session ID is missing."
        )
    if (
        metadata.get("plan_id") != subscription.plan_id
        or metadata.get("billing_interval") != subscription.billing_interval
    ):
        raise StripeWebhookProcessingError(
            "Stripe checkout plan does not match the local subscription."
        )
    attempt = StripeCheckoutAttempt.objects.select_for_update().filter(
        checkout_session_id=session_id
    ).first()
    if attempt and (
        attempt.owner_id != subscription.owner_id
        or attempt.subscription_id != subscription.id
        or attempt.customer_id != customer_id
    ):
        raise StripeWebhookProcessingError(
            "Stripe checkout session does not match its saved subscription.",
            status_code=409,
        )
    if (
        not attempt
        and subscription.checkout_session_id
        and subscription.checkout_session_id != session_id
    ):
        raise StripeWebhookProcessingError(
            "Stripe checkout session does not match its saved subscription.",
            status_code=409,
        )

    provider_subscription_id = _identifier(_value(data, "subscription"))
    if provider_subscription_id:
        _set_provider_subscription_id(subscription, provider_subscription_id)
    if customer_id:
        subscription.provider_customer_id = customer_id
    event_created_at = _event_time(event)
    if not attempt:
        StripeCheckoutAttempt.objects.create(
            checkout_session_id=session_id,
            owner_id=subscription.owner_id,
            subscription=subscription,
            customer_id=customer_id,
            plan_id=subscription.plan_id,
            price_id="",
            billing_interval=subscription.billing_interval,
            stripe_created_at=_stripe_datetime(_value(data, "created")),
            expires_at=_stripe_datetime(_value(data, "expires_at")),
        )

    payment_status = _value(data, "payment_status")
    if event_type == "checkout.session.async_payment_failed":
        status_value = PaymentTransaction.Status.FAILED
    elif payment_status == "paid":
        status_value = PaymentTransaction.Status.SUCCEEDED
    elif payment_status == "unpaid":
        status_value = PaymentTransaction.Status.PENDING
    else:
        status_value = None

    if status_value:
        invoice_id = _identifier(_value(data, "invoice"))
        payment_intent_id = _identifier(_value(data, "payment_intent"))
        transaction_id = invoice_id or payment_intent_id or session_id
        transaction_values = _transaction_values(
            subscription,
            checkout_session_id=session_id,
            provider_invoice_id=invoice_id or "",
            provider_payment_intent_id=payment_intent_id or "",
            transaction_type=PaymentTransaction.TransactionType.INITIAL_PAYMENT,
            status=status_value,
            amount_minor=_value(data, "amount_total"),
            currency=(_value(data, "currency") or "").upper(),
            occurred_at=event_created_at,
        )
        _persist_transaction(
            subscription=subscription,
            transaction_id=transaction_id,
            values=transaction_values,
            event_id=_value(event, "id", ""),
            event_created_at=event_created_at,
        )

    if not subscription.checkout_session_id:
        subscription.checkout_session_id = session_id
    if subscription.status != UserSubscription.Status.PENDING:
        subscription.save(
            update_fields=[
                "provider_customer_id",
                "provider_subscription_id",
                "checkout_session_id",
                "updated_at",
            ]
        )
        return
    subscription.save(
        update_fields=[
            "provider_customer_id",
            "provider_subscription_id",
            "checkout_session_id",
            "updated_at",
        ]
    )


def _record_invoice(invoice, event_type, event):
    provider_subscription_id = _subscription_id_from_invoice(invoice)
    if not provider_subscription_id:
        raise StripeWebhookProcessingError(
            "Stripe invoice does not reference a subscription."
        )
    customer_id = _identifier(_value(invoice, "customer"))
    subscription_query = (
        UserSubscription.objects.select_for_update()
        .filter(
            provider=STRIPE_PROVIDER,
            provider_subscription_id=provider_subscription_id,
        )
    )
    if customer_id:
        subscription_query = subscription_query.filter(
            provider_customer_id=customer_id
        )
    subscription = subscription_query.first()
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
    payment_intent_id = _identifier(_value(invoice, "payment_intent"))
    billing_reason = _value(invoice, "billing_reason")
    invoice_plan = None
    lines = _value(_value(invoice, "lines"), "data", []) or []
    for line in lines:
        price = _identifier(_value(line, "price"))
        invoice_plan = get_plan_for_price(price)
        if invoice_plan:
            break
    plan_id, billing_interval = invoice_plan or (
        subscription.plan_id,
        subscription.billing_interval,
    )
    plan_name = _plan_name(plan_id)
    transaction_type = {
        "subscription_create": PaymentTransaction.TransactionType.INITIAL_PAYMENT,
        "subscription_cycle": PaymentTransaction.TransactionType.RENEWAL,
        "subscription_update": PaymentTransaction.TransactionType.PLAN_CHANGE,
    }.get(billing_reason, PaymentTransaction.TransactionType.OTHER)
    existing_checkout_payment = None
    if (
        transaction_type == PaymentTransaction.TransactionType.INITIAL_PAYMENT
        and subscription.checkout_session_id
    ):
        existing_checkout_payment = PaymentTransaction.objects.filter(
            provider=STRIPE_PROVIDER,
            subscription=subscription,
            checkout_session_id=subscription.checkout_session_id,
            transaction_type=PaymentTransaction.TransactionType.INITIAL_PAYMENT,
        ).first()
    if existing_checkout_payment:
        transaction_id = existing_checkout_payment.provider_transaction_id
    status_transitions = _value(invoice, "status_transitions")
    paid_at = (
        _stripe_datetime(_value(status_transitions, "paid_at"))
        if status_value == PaymentTransaction.Status.SUCCEEDED
        else None
    )
    transaction_values = {
        "provider_customer_id": customer_id or subscription.provider_customer_id,
        "provider_invoice_id": invoice_id,
        "provider_payment_intent_id": payment_intent_id or "",
        "provider_subscription_id": provider_subscription_id,
        "plan_id": plan_id,
        "plan_name": plan_name,
        "billing_interval": billing_interval,
        "transaction_type": transaction_type,
        "status": status_value,
        "amount_minor": amount,
        "currency": (_value(invoice, "currency") or "").upper(),
        "occurred_at": occurred_at,
        "paid_at": paid_at,
        "receipt_url": _safe_receipt_url(
            _value(invoice, "hosted_invoice_url")
        ),
    }
    _persist_transaction(
        subscription=subscription,
        transaction_id=transaction_id,
        values=transaction_values,
        event_id=_value(event, "id", ""),
        event_created_at=occurred_at,
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
def _record_refunded_charge(charge, event):
    payment_intent_id = _identifier(_value(charge, "payment_intent"))
    charge_id = _identifier(charge)
    original = PaymentTransaction.objects.select_for_update().filter(
        provider=STRIPE_PROVIDER,
    )
    if payment_intent_id:
        original = original.filter(provider_payment_intent_id=payment_intent_id)
    elif charge_id:
        original = original.filter(provider_charge_id=charge_id)
    else:
        raise StripeWebhookProcessingError(
            "Stripe refund does not reference a known payment."
        )
    original = original.exclude(
        transaction_type=PaymentTransaction.TransactionType.REFUND
    ).first()
    customer_id = _identifier(_value(charge, "customer"))
    if (
        original is None
        or (customer_id and customer_id != original.provider_customer_id)
    ):
        raise StripeWebhookProcessingError(
            "Stripe refund does not match a known customer payment.",
            status_code=404,
        )

    event_created_at = _event_time(event)
    refunds = _value(_value(charge, "refunds"), "data", []) or []
    for refund in refunds:
        refund_id = _identifier(refund)
        if not refund_id:
            raise StripeWebhookProcessingError("Stripe refund ID is missing.")
        refund_status = _value(refund, "status")
        status_value = {
            "succeeded": PaymentTransaction.Status.REFUNDED,
            "pending": PaymentTransaction.Status.PENDING,
            "failed": PaymentTransaction.Status.FAILED,
            "canceled": PaymentTransaction.Status.FAILED,
        }.get(refund_status)
        if status_value is None:
            raise StripeWebhookProcessingError(
                "Stripe refund status is not supported."
            )
        _persist_transaction(
            subscription=original.subscription,
            transaction_id=refund_id,
            values={
                "provider_customer_id": original.provider_customer_id,
                "provider_payment_intent_id": payment_intent_id or "",
                "provider_charge_id": charge_id or "",
                "plan_id": original.plan_id,
                "plan_name": original.plan_name,
                "billing_interval": original.billing_interval,
                "transaction_type": PaymentTransaction.TransactionType.REFUND,
                "status": status_value,
                "amount_minor": _value(refund, "amount"),
                "currency": (_value(refund, "currency") or "").upper(),
                "occurred_at": event_created_at,
                "paid_at": (
                    _stripe_datetime(_value(refund, "created"))
                    if status_value == PaymentTransaction.Status.REFUNDED
                    else None
                ),
            },
            event_id=_value(event, "id", ""),
            event_created_at=event_created_at,
            match_identifiers=False,
        )

    amount = _value(charge, "amount")
    amount_refunded = _value(charge, "amount_refunded")
    if amount is not None and amount_refunded is not None and amount_refunded >= amount:
        _persist_transaction(
            subscription=original.subscription,
            transaction_id=original.provider_transaction_id,
            values={"status": PaymentTransaction.Status.REFUNDED},
            event_id=_value(event, "id", ""),
            event_created_at=event_created_at,
        )


def process_stripe_event(payload, signature):
    event = construct_webhook_event(payload, signature)
    return _process_event(event)


def _process_event(event):
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
            record, created = ProviderWebhookEvent.objects.get_or_create(
                provider=STRIPE_PROVIDER,
                event_id=event_id,
                defaults={"event_type": event_type},
            )
            if not created:
                if record.status == ProviderWebhookEvent.Status.PROCESSED:
                    return {
                        "received": True,
                        "duplicate": True,
                        "processing_status": record.status,
                    }
                # A durably recorded event that needed configuration can be
                # reprocessed by re-delivery or by an administrator.
                record.event_type = event_type

            try:
                if event_type in (
                    "checkout.session.completed",
                    "checkout.session.async_payment_succeeded",
                    "checkout.session.async_payment_failed",
                ):
                    _checkout_completed(event_type, event, data)
                elif event_type in (
                    "customer.subscription.created",
                    "customer.subscription.updated",
                    "customer.subscription.deleted",
                ):
                    _sync_subscription(event_type, event, data)
                elif event_type in ("invoice.paid", "invoice.payment_failed"):
                    _record_invoice(data, event_type, event)
                elif event_type == "charge.refunded":
                    _record_refunded_charge(data, event)
            except UnknownStripePrice as error:
                record.status = ProviderWebhookEvent.Status.NEEDS_ATTENTION
                record.detail = f"unknown_price:{error.price_id}"[:255]
                record.save(update_fields=["event_type", "status", "detail"])
                logger.error(
                    "Stripe webhook needs attention: event_id=%s "
                    "event_type=%s reason=unknown_price price_id=%s owner=%s",
                    event_id,
                    event_type,
                    error.price_id,
                    _metadata(data).get("ibda_owner_id", "unknown"),
                )
                return {
                    "received": True,
                    "duplicate": False,
                    "needs_attention": True,
                    "reason": "unknown_price",
                    "processing_status": record.status,
                }

            record.status = ProviderWebhookEvent.Status.PROCESSED
            record.detail = ""
            record.save(update_fields=["event_type", "status", "detail"])
    except IntegrityError as error:
        raise StripeWebhookProcessingError(
            "Stripe event conflicts with existing billing data.",
            status_code=409,
        ) from error

    return {
        "received": True,
        "duplicate": False,
        "processing_status": ProviderWebhookEvent.Status.PROCESSED,
    }


def reprocess_stripe_event(event_id):
    """Re-runs a recorded event that is waiting on configuration.

    Read-only against Stripe: the event is retrieved with GET /v1/events and
    nothing is cancelled, updated, or deleted remotely. Local billing data is
    only written through the normal, idempotent event processor.
    """
    record = ProviderWebhookEvent.objects.filter(
        provider=STRIPE_PROVIDER,
        event_id=event_id,
    ).first()
    if record is None:
        raise StripeWebhookProcessingError(
            "Webhook event was not recorded locally.",
            status_code=404,
        )
    if record.status == ProviderWebhookEvent.Status.PROCESSED:
        return {
            "received": True,
            "duplicate": True,
            "reprocessed": False,
            "processing_status": record.status,
        }

    event = retrieve_event(event_id)
    result = _process_event(event)
    record.refresh_from_db()
    result.update(
        {
            "reprocessed": True,
            "processing_status": record.status,
        }
    )
    return result
