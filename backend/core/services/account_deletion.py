"""Permanent deletion of a user's Ibda account.

Supabase Auth, Stripe, file storage and the local database cannot share one
transaction, so the deletion runs in a fixed order where the only step that can
make a retry impossible comes last:

1. Configuration is validated before anything is destroyed.
2. The owner's Stripe subscriptions are cancelled (in the view). Cancelling an
   already-cancelled subscription is accepted, so a retry is safe.
3. Every local row owned by the owner is deleted in one database transaction,
   together with the marker that records the purge. If this fails, nothing was
   removed and the account can still be retried normally.
4. The Supabase Auth identity is deleted. Because the local purge already
   committed, a failure here can be retried without losing any cleanup, and a
   success here can no longer strand undeleted rows.
5. The progress marker is removed.

The service-role key is only ever used here, on the backend.
"""

import logging

import requests
from django.db import transaction
from django.utils import timezone

from core.models import (
    AccountDeletionRequest,
    Approval,
    Brand,
    ContentPost,
    Notification,
    PaymentTransaction,
    ScheduledPost,
    SocialAccount,
    SocialOAuthState,
    StripeCheckoutAttempt,
    SupportRequest,
    UserSubscription,
)

logger = logging.getLogger(__name__)

SUPABASE_ADMIN_TIMEOUT_SECONDS = 10
SUPABASE_SUCCESS_STATUS_CODES = (200, 202, 204)

# The deletion endpoint must stay reachable for an account that is only partly
# deleted, otherwise the owner could not finish the cleanup.
ACCOUNT_DELETION_ENDPOINT_SUFFIXES = (
    "/me/delete-account",
    "/profile/delete-account",
    "/account/delete",
)


class AccountDeletionError(Exception):
    """A required remote step failed; ``detail`` is safe to show to users."""

    def __init__(self, code, detail, *, status_code=502, retryable=True):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code
        self.retryable = retryable


def is_account_deletion_endpoint(path):
    """True when ``path`` is one of the account-deletion routes."""
    normalized = (path or "").split("?")[0].rstrip("/")
    return any(
        normalized.endswith(suffix)
        for suffix in ACCOUNT_DELETION_ENDPOINT_SUFFIXES
    )


def delete_supabase_user(*, user_id, supabase_url, service_role_key):
    """Permanently delete the Supabase Auth identity for ``user_id``.

    Only the authenticated user's own id is ever passed in. A 404 means the
    identity is already gone, which is the state a retry wants, so it counts as
    success; every other non-2xx response and any network failure raises.
    """
    try:
        response = requests.delete(
            f"{supabase_url}/auth/v1/admin/users/{user_id}",
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
            },
            timeout=SUPABASE_ADMIN_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        logger.exception("Supabase admin user deletion request failed")
        raise AccountDeletionError(
            "supabase_deletion_failed",
            (
                "Your Ibda data was removed, but your sign-in account could "
                "not be deleted yet. Repeat the deletion request to finish."
            ),
        )

    if response.status_code == 404:
        logger.info("Supabase Auth identity was already deleted")
        return

    if response.status_code not in SUPABASE_SUCCESS_STATUS_CODES:
        logger.error(
            "Supabase admin user deletion rejected: status=%s body=%s",
            response.status_code,
            response.text[:500],
        )
        raise AccountDeletionError(
            "supabase_deletion_failed",
            (
                "Your Ibda data was removed, but your sign-in account could "
                "not be deleted yet. Repeat the deletion request to finish."
            ),
        )


def start_account_deletion(owner_id):
    """Create (or reuse) the progress marker for an owner's deletion."""
    request, created = AccountDeletionRequest.objects.get_or_create(
        owner_id=owner_id
    )
    if created:
        logger.info("Account deletion started: owner=%s", owner_id)
    return request


def record_deletion_failure(owner_id, code):
    """Remember why a deletion stopped without exposing it to the client."""
    AccountDeletionRequest.objects.filter(owner_id=owner_id).update(
        last_error=str(code)[:64],
        updated_at=timezone.now(),
    )


def mark_subscriptions_canceled(owner_id):
    AccountDeletionRequest.objects.filter(owner_id=owner_id).update(
        subscriptions_canceled_at=timezone.now(),
        last_error="",
        updated_at=timezone.now(),
    )


def purge_local_account_data(owner_id):
    """Delete all local owner data and record the purge atomically.

    The marker update commits with the rows, so a crash cannot leave local data
    gone while the account is still treated as active.
    """
    with transaction.atomic():
        counts = purge_owner_data(owner_id)
        AccountDeletionRequest.objects.filter(owner_id=owner_id).update(
            local_data_purged_at=timezone.now(),
            last_error="",
            updated_at=timezone.now(),
        )
    return counts


def mark_supabase_identity_deleted(owner_id):
    AccountDeletionRequest.objects.filter(owner_id=owner_id).update(
        supabase_identity_deleted_at=timezone.now(),
        updated_at=timezone.now(),
    )


def finish_account_deletion(owner_id):
    """Remove the progress marker; the marker holds no user content."""
    AccountDeletionRequest.objects.filter(owner_id=owner_id).delete()


def is_partially_deleted_account(owner_id):
    """True once local data is gone but the Supabase identity still exists."""
    return AccountDeletionRequest.objects.filter(
        owner_id=owner_id,
        local_data_purged_at__isnull=False,
    ).exists()


def purge_owner_data(owner_id):
    """Delete every local record owned by ``owner_id`` and return the counts.

    Idempotent: repeating it for an owner with no rows left is a no-op. Records
    owned by another user are never deleted; the only cross-owner change is
    clearing a review reference that points at the deleted account.

    Every user-owned table is listed explicitly, even where a cascade would
    cover it, so a row that has outlived its parent cannot be orphaned.
    """
    with transaction.atomic():
        counts = {
            # Approvals of our own posts are deleted with those posts. An
            # approval of another owner's post belongs to that owner, so only
            # the reference to the deleted account is cleared.
            "reviews_detached": (
                Approval.objects.filter(reviewer_id=owner_id)
                .exclude(post__brand__owner_id=owner_id)
                .update(reviewer_id=None, updated_at=timezone.now())
            ),
        }

        owned_querysets = (
            (
                "notifications",
                Notification.objects.filter(recipient_user_id=owner_id),
            ),
            (
                "scheduled_posts",
                ScheduledPost.objects.filter(post__brand__owner_id=owner_id),
            ),
            (
                "approvals",
                Approval.objects.filter(post__brand__owner_id=owner_id),
            ),
            (
                "content_posts",
                ContentPost.objects.filter(brand__owner_id=owner_id),
            ),
            # Cascades to the brand voice and any remaining brand content.
            ("brands", Brand.objects.filter(owner_id=owner_id)),
            (
                "social_accounts",
                SocialAccount.objects.filter(owner_id=owner_id),
            ),
            (
                "social_oauth_states",
                SocialOAuthState.objects.filter(owner_id=owner_id),
            ),
            (
                "support_requests",
                SupportRequest.objects.filter(owner_id=owner_id),
            ),
            (
                "stripe_checkout_attempts",
                StripeCheckoutAttempt.objects.filter(owner_id=owner_id),
            ),
            (
                "payment_transactions",
                PaymentTransaction.objects.filter(subscription__owner_id=owner_id),
            ),
            (
                "subscriptions",
                UserSubscription.objects.filter(owner_id=owner_id),
            ),
        )
        for label, queryset in owned_querysets:
            counts[label] = queryset.delete()[0]

        return counts
