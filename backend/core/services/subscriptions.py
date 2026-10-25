import json

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.utils import timezone

from core.models import UserSubscription


def get_user_entitlements(owner_id):
    subscription = (
        UserSubscription.objects.filter(
            owner_id=owner_id,
            status=UserSubscription.Status.ACTIVE,
        )
        .filter(
            Q(current_period_end__isnull=True)
            | Q(current_period_end__gt=timezone.now())
        )
        .order_by("-created_at")
        .first()
    )
    plan_id = subscription.plan_id if subscription else "free"
    try:
        configured_limits = json.loads(
            settings.SUBSCRIPTION_ENTITLEMENT_LIMITS
        )
    except (TypeError, json.JSONDecodeError) as error:
        raise ImproperlyConfigured(
            "SUBSCRIPTION_ENTITLEMENT_LIMITS must be a JSON object."
        ) from error

    if not isinstance(configured_limits, dict):
        raise ImproperlyConfigured(
            "SUBSCRIPTION_ENTITLEMENT_LIMITS must be a JSON object."
        )
    limits = configured_limits.get(plan_id, {})
    if not isinstance(limits, dict):
        raise ImproperlyConfigured(
            f"Entitlement limits for {plan_id!r} must be a JSON object."
        )
    for feature, limit in limits.items():
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit < 0
        ):
            raise ImproperlyConfigured(
                f"The {feature!r} entitlement limit must be a "
                "non-negative integer or null."
            )
    return {"plan_id": plan_id, "limits": limits}


def is_within_entitlement_limit(owner_id, feature, current_usage):
    entitlement = get_user_entitlements(owner_id)
    limit = entitlement["limits"].get(feature)
    if limit is None:
        return True
    return current_usage < limit
