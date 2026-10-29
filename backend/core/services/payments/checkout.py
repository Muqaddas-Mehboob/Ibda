import stripe
from django.conf import settings
from django.db import IntegrityError, transaction

from core.models import UserSubscription

from .catalog import get_plan_for_price, get_price_id
from .stripe_gateway import (
    create_checkout_session,
    create_customer,
    retrieve_price_details,
)


class CheckoutUnavailable(Exception):
    def __init__(self, reason="configuration"):
        self.reason = reason
        super().__init__(reason)


class SubscriptionAlreadyExists(Exception):
    pass


def start_stripe_checkout(
    *,
    owner_id,
    email,
    plan_id,
    billing_interval,
    idempotency_key,
):
    price_id = get_price_id(plan_id, billing_interval)
    price_details = (
        retrieve_price_details(price_id)
        if settings.STRIPE_SECRET_KEY.startswith("sk_test_") and price_id
        else None
    )
    expected_stripe_interval = (
        "month" if billing_interval == "monthly" else "year"
    )
    validation_failures = (
        (
            settings.STRIPE_SECRET_KEY.startswith("sk_test_"),
            "stripe_test_secret",
        ),
        (bool(settings.STRIPE_WEBHOOK_SECRET), "webhook_secret"),
        (bool(settings.STRIPE_CHECKOUT_SUCCESS_URL), "success_url"),
        (bool(settings.STRIPE_CHECKOUT_CANCEL_URL), "cancel_url"),
        (bool(price_id), "price_id"),
        (
            bool(price_id)
            and get_plan_for_price(price_id) == (plan_id, billing_interval),
            "price_mapping",
        ),
        (bool(price_details), "price_lookup"),
        (bool(price_details and price_details["active"]), "price_inactive"),
        (
            bool(
                price_details
                and price_details["recurring_interval"]
                == expected_stripe_interval
            ),
            "price_interval",
        ),
        (
            bool(price_details and price_details["recurring_interval_count"] == 1),
            "price_interval_count",
        ),
    )
    failure = next(
        (reason for passed, reason in validation_failures if not passed),
        None,
    )
    if failure:
        raise CheckoutUnavailable(failure)

    subscription = (
        UserSubscription.objects.filter(
            owner_id=owner_id,
            status__in=(
                UserSubscription.Status.PENDING,
                UserSubscription.Status.ACTIVE,
                UserSubscription.Status.PAST_DUE,
            ),
        )
        .order_by("-created_at")
        .first()
    )
    created_subscription = subscription is None
    if subscription and not (
        subscription.provider == "stripe"
        and subscription.status == UserSubscription.Status.PENDING
        and subscription.plan_id == plan_id
        and subscription.billing_interval == billing_interval
        and subscription.provider_subscription_id is None
    ):
        raise SubscriptionAlreadyExists

    if created_subscription:
        try:
            with transaction.atomic():
                subscription = UserSubscription.objects.create(
                    owner_id=owner_id,
                    provider="stripe",
                    plan_id=plan_id,
                    billing_interval=billing_interval,
                    status=UserSubscription.Status.PENDING,
                )
        except IntegrityError as error:
            subscription = (
                UserSubscription.objects.filter(
                    owner_id=owner_id,
                    status=UserSubscription.Status.PENDING,
                    provider="stripe",
                    plan_id=plan_id,
                    billing_interval=billing_interval,
                    provider_subscription_id__isnull=True,
                )
                .order_by("-created_at")
                .first()
            )
            if subscription is None:
                raise SubscriptionAlreadyExists from error
            created_subscription = False

    try:
        existing_customer = (
            UserSubscription.objects.filter(
                owner_id=owner_id,
                provider="stripe",
            )
            .exclude(id=subscription.id)
            .exclude(provider_customer_id="")
            .order_by("-created_at")
            .first()
        )
        customer_id = subscription.provider_customer_id or (
            existing_customer.provider_customer_id if existing_customer else ""
        )
        if not customer_id:
            customer = create_customer(owner_id, email)
            customer_id = customer.id
        subscription.provider_customer_id = customer_id
        subscription.save(update_fields=["provider_customer_id", "updated_at"])

        session = create_checkout_session(
            customer_id=customer_id,
            price_id=price_id,
            plan_id=plan_id,
            billing_interval=billing_interval,
            local_subscription_id=subscription.id,
            owner_id=owner_id,
            idempotency_key=f"ibda-checkout-{owner_id}-{idempotency_key}",
        )
    except stripe.StripeError:
        if created_subscription:
            UserSubscription.objects.filter(
                id=subscription.id,
                provider_subscription_id__isnull=True,
            ).delete()
        raise

    if not session.url or not session.id:
        if created_subscription:
            UserSubscription.objects.filter(
                id=subscription.id,
                provider_subscription_id__isnull=True,
            ).delete()
        raise CheckoutUnavailable

    return session
