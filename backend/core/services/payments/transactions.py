from django.db import IntegrityError, transaction

from core.models import PaymentTransaction


STRIPE_PROVIDER = "stripe"
IDENTIFIER_FIELDS = (
    "provider_invoice_id",
    "provider_payment_intent_id",
    "checkout_session_id",
    "provider_charge_id",
)


class StripeTransactionConflict(Exception):
    pass


def upsert_stripe_transaction(
    *,
    subscription,
    transaction_id,
    values,
    event_id="",
    event_created_at=None,
    match_identifiers=True,
):
    if not transaction_id:
        raise StripeTransactionConflict("Stripe transaction ID is missing.")

    identifiers = {
        field: values.get(field)
        for field in IDENTIFIER_FIELDS
        if values.get(field)
    }
    with transaction.atomic():
        existing = None
        queryset = PaymentTransaction.objects.select_for_update().filter(
            provider=STRIPE_PROVIDER
        )
        existing = queryset.filter(
            provider_transaction_id=transaction_id
        ).first()
        if existing is None and match_identifiers:
            identifier_queryset = queryset.exclude(
                transaction_type=PaymentTransaction.TransactionType.REFUND
            )
            for field, identifier in identifiers.items():
                existing = identifier_queryset.filter(**{field: identifier}).first()
                if existing is not None:
                    break

        if existing is not None:
            if existing.subscription_id != subscription.id:
                raise StripeTransactionConflict(
                    "Stripe payment does not match its local subscription."
                )
            if (
                event_created_at
                and existing.provider_event_created_at
                and event_created_at < existing.provider_event_created_at
            ):
                return existing, False
            if existing.status == PaymentTransaction.Status.REFUNDED and values.get(
                "status"
            ) != PaymentTransaction.Status.REFUNDED:
                return existing, False
            if (
                existing.status == PaymentTransaction.Status.FAILED
                and values.get("status") == PaymentTransaction.Status.PENDING
            ):
                return existing, False
            if (
                existing.status == PaymentTransaction.Status.SUCCEEDED
                and values.get("status")
                in (PaymentTransaction.Status.PENDING, PaymentTransaction.Status.FAILED)
            ):
                return existing, False

            changed_fields = []
            for field, value in values.items():
                if value is None or value == "":
                    continue
                if getattr(existing, field) != value:
                    setattr(existing, field, value)
                    changed_fields.append(field)
            if event_id and existing.provider_event_id != event_id:
                existing.provider_event_id = event_id
                changed_fields.append("provider_event_id")
            if event_created_at and (
                existing.provider_event_created_at != event_created_at
            ):
                existing.provider_event_created_at = event_created_at
                changed_fields.append("provider_event_created_at")
            if changed_fields:
                existing.save(update_fields=[*set(changed_fields), "updated_at"])
            return existing, False

        defaults = {
            "subscription": subscription,
            "provider": STRIPE_PROVIDER,
            **values,
            "provider_event_id": event_id,
            "provider_event_created_at": event_created_at,
        }
        try:
            with transaction.atomic():
                record = PaymentTransaction.objects.create(
                    provider_transaction_id=transaction_id,
                    **defaults,
                )
        except IntegrityError:
            conflict_query = queryset.filter(
                provider_transaction_id=transaction_id
            )
            for field, identifier in identifiers.items():
                conflict_query = conflict_query | queryset.filter(
                    **{field: identifier}
                )
            record = conflict_query.first()
            if record is None or record.subscription_id != subscription.id:
                raise StripeTransactionConflict(
                    "Stripe transaction conflicts with existing billing data."
                )
            return record, False
        return record, True