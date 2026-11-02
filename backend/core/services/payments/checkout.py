from datetime import datetime, timezone as datetime_timezone

import stripe
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core.models import UserSubscription

from .catalog import (
    get_checkout_redirect_urls,
    get_plan_for_price,
    get_price_id,
)
from .stripe_gateway import (
    create_checkout_session,
    create_customer,
    retrieve_price_details,
    retrieve_checkout_session,
    retrieve_subscription,
)


class CheckoutUnavailable(Exception):
    def __init__(self, reason="configuration"):
        self.reason = reason
        super().__init__(reason)


class SubscriptionAlreadyExists(Exception):
    def __init__(self, reason, subscription=None, checkout_session_id=""):
        self.reason = reason
        self.subscription = subscription
        self.checkout_session_id = checkout_session_id
        super().__init__(reason)


def start_stripe_checkout(
    *,
    owner_id,
    email,
    plan_id,
    billing_interval,
    idempotency_key,
    platform="web",
):
    redirect_urls = get_checkout_redirect_urls(platform)
    if redirect_urls is None:
        raise CheckoutUnavailable("return_urls")
    success_url, cancel_url = redirect_urls
    success_url = _checkout_return_url(success_url, checkout="success")
    cancel_url = _checkout_return_url(cancel_url, checkout="cancelled")

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
    provider_subscription = None
    provider_status = None
    if subscription:
        if subscription.provider == "stripe" and subscription.provider_subscription_id:
            try:
                provider_subscription = retrieve_subscription(
                    subscription.provider_subscription_id
                )
            except stripe.InvalidRequestError as error:
                if getattr(error, "code", None) != "resource_missing":
                    raise
                subscription.status = UserSubscription.Status.EXPIRED
                subscription.checkout_session_id = ""
                subscription.checkout_session_expires_at = None
                subscription.save(
                    update_fields=[
                        "status",
                        "checkout_session_id",
                        "checkout_session_expires_at",
                        "updated_at",
                    ]
                )
            else:
                provider_status = getattr(provider_subscription, "status", "")
                remote_customer_id = getattr(provider_subscription, "customer", None)
                remote_customer_id = getattr(remote_customer_id, "id", remote_customer_id)
                if (
                    remote_customer_id
                    and subscription.provider_customer_id
                    and remote_customer_id != subscription.provider_customer_id
                ):
                    raise SubscriptionAlreadyExists(
                        "stripe_customer_mismatch",
                        subscription,
                    )
                if provider_status in ("active", "trialing"):
                    subscription.status = UserSubscription.Status.ACTIVE
                    subscription.save(update_fields=["status", "updated_at"])
                if provider_status == "past_due":
                    subscription.status = UserSubscription.Status.PAST_DUE
                    subscription.save(update_fields=["status", "updated_at"])
                elif provider_status == "canceled":
                    subscription.status = UserSubscription.Status.CANCELED
                    subscription.save(update_fields=["status", "updated_at"])
                elif provider_status == "incomplete_expired":
                    subscription.status = UserSubscription.Status.EXPIRED
                    subscription.save(update_fields=["status", "updated_at"])
                elif provider_status == "incomplete":
                    subscription.status = UserSubscription.Status.PENDING
                    subscription.save(update_fields=["status", "updated_at"])
                elif provider_status == "unpaid":
                    subscription.status = UserSubscription.Status.FAILED
                    subscription.save(update_fields=["status", "updated_at"])
                elif provider_status not in ("active", "trialing"):
                    raise SubscriptionAlreadyExists(
                        "subscription_unavailable",
                        subscription,
                    )

        if subscription.status == UserSubscription.Status.ACTIVE:
            raise SubscriptionAlreadyExists("active_subscription", subscription)
        if subscription.status == UserSubscription.Status.PAST_DUE:
            raise SubscriptionAlreadyExists("payment_past_due", subscription)
        if subscription.provider != "stripe":
            raise SubscriptionAlreadyExists("subscription_exists", subscription)
        if (
            subscription.status == UserSubscription.Status.PENDING
            and (
                subscription.plan_id != plan_id
                or subscription.billing_interval != billing_interval
            )
        ):
            raise SubscriptionAlreadyExists("pending_checkout", subscription)
        if (
            subscription.provider_subscription_id
            and provider_status == "incomplete"
            and not subscription.checkout_session_id
        ):
            raise SubscriptionAlreadyExists(
                "subscription_incomplete",
                subscription,
            )

        if subscription.checkout_session_id and subscription.status == UserSubscription.Status.PENDING:
            try:
                checkout_session = retrieve_checkout_session(
                    subscription.checkout_session_id
                )
            except stripe.InvalidRequestError as error:
                if getattr(error, "code", None) != "resource_missing":
                    raise
                checkout_session = None

            if checkout_session is not None:
                metadata = getattr(checkout_session, "metadata", {}) or {}
                session_owner = (
                    metadata.get("ibda_owner_id")
                    if hasattr(metadata, "get")
                    else getattr(metadata, "ibda_owner_id", None)
                )
                session_subscription = (
                    metadata.get("ibda_subscription_id")
                    if hasattr(metadata, "get")
                    else getattr(metadata, "ibda_subscription_id", None)
                )
                if (
                    session_owner != str(owner_id)
                    or session_subscription != str(subscription.id)
                    or getattr(checkout_session, "customer", None)
                    != subscription.provider_customer_id
                ):
                    raise SubscriptionAlreadyExists(
                        "checkout_session_mismatch",
                        subscription,
                    )

                if getattr(checkout_session, "status", None) == "open":
                    expires_at = getattr(checkout_session, "expires_at", None)
                    if not expires_at:
                        raise SubscriptionAlreadyExists(
                            "checkout_session_unavailable",
                            subscription,
                        )
                    if expires_at > int(timezone.now().timestamp()):
                        if not getattr(checkout_session, "url", None):
                            raise SubscriptionAlreadyExists(
                                "checkout_session_unavailable",
                                subscription,
                            )
                        return checkout_session
                elif getattr(checkout_session, "status", None) == "complete":
                    raise SubscriptionAlreadyExists(
                        "checkout_processing",
                        subscription,
                        subscription.checkout_session_id,
                    )

            subscription.checkout_session_id = ""
            subscription.checkout_session_expires_at = None
            if (
                subscription.provider_subscription_id
                and subscription.status == UserSubscription.Status.PENDING
            ):
                raise SubscriptionAlreadyExists(
                    "subscription_incomplete",
                    subscription,
                )
            subscription.save(
                update_fields=[
                    "checkout_session_id",
                    "checkout_session_expires_at",
                    "updated_at",
                ]
            )

    created_subscription = subscription is None or (
        subscription.status
        in (
            UserSubscription.Status.CANCELED,
            UserSubscription.Status.EXPIRED,
            UserSubscription.Status.FAILED,
        )
    )

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
                raise SubscriptionAlreadyExists("subscription_exists") from error
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
            success_url=success_url,
            cancel_url=cancel_url,
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

    subscription.checkout_session_id = session.id
    expires_at = getattr(session, "expires_at", None)
    subscription.checkout_session_expires_at = (
        datetime.fromtimestamp(expires_at, tz=datetime_timezone.utc)
        if expires_at
        else None
    )
    subscription.save(
        update_fields=[
            "checkout_session_id",
            "checkout_session_expires_at",
            "updated_at",
        ]
    )
    return session


def _checkout_return_url(url, *, checkout):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["checkout"] = checkout
    if checkout == "success":
        query["session_id"] = "{CHECKOUT_SESSION_ID}"
    else:
        query.pop("session_id", None)
    return urlunsplit(
        parts._replace(query=urlencode(query, safe="{}"))
    )
