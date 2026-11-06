"""Permanent deletion of a user's brands and their brand-specific records.

Brands have no files in Supabase Storage or any other storage provider, so a
deletion only touches the local database. Every delete runs in one transaction
and is always scoped to the authenticated owner, which makes a repeated request
a harmless no-op instead of an error.

Dependent records are listed explicitly even where a database cascade already
covers them, so a row can never outlive the brand it belongs to. Notifications
have no foreign key to a brand: they point at an approval or scheduled post by
UUID, so they are removed here before their parents disappear.
"""

import logging

from django.db import transaction

from core.models import (
    Approval,
    Brand,
    BrandVoice,
    ContentPost,
    Notification,
    ScheduledPost,
)

logger = logging.getLogger(__name__)

DELETION_FAILED_DETAIL = (
    "We couldn't delete your brand data. Nothing was removed, so you can try "
    "again."
)


class BrandDeletionError(Exception):
    """A brand deletion failed; ``detail`` is safe to show to users."""

    def __init__(self, detail=DELETION_FAILED_DETAIL):
        super().__init__(detail)
        self.detail = detail


def delete_brands(*, owner_id, brand_ids=None):
    """Delete ``owner_id``'s brands and their brand-specific records.

    ``brand_ids`` limits the deletion to specific brands, which are still
    filtered by owner. ``None`` means every brand the owner has. Brands owned
    by anyone else are never touched.

    Returns a mapping of deleted record counts. Repeating the call after the
    brands are gone returns zero counts.
    """
    counts = {
        "brands": 0,
        "brand_voices": 0,
        "content_posts": 0,
        "approvals": 0,
        "scheduled_posts": 0,
        "notifications": 0,
    }

    try:
        with transaction.atomic():
            owned_brands = Brand.objects.select_for_update().filter(
                owner_id=owner_id
            )
            if brand_ids is not None:
                owned_brands = owned_brands.filter(id__in=brand_ids)

            selected_brand_ids = list(
                owned_brands.values_list("id", flat=True)
            )
            if not selected_brand_ids:
                return counts

            posts = ContentPost.objects.filter(
                brand_id__in=selected_brand_ids
            )
            post_ids = list(posts.values_list("id", flat=True))
            approval_ids = list(
                Approval.objects.filter(post_id__in=post_ids).values_list(
                    "id", flat=True
                )
            )
            scheduled_post_ids = list(
                ScheduledPost.objects.filter(post_id__in=post_ids).values_list(
                    "id", flat=True
                )
            )

            counts["notifications"] = Notification.objects.filter(
                related_object_id__in=approval_ids + scheduled_post_ids
            ).delete()[0]

            counts["scheduled_posts"] = ScheduledPost.objects.filter(
                post_id__in=post_ids
            ).delete()[0]
            counts["approvals"] = Approval.objects.filter(
                post_id__in=post_ids
            ).delete()[0]
            counts["content_posts"] = posts.delete()[0]
            counts["brand_voices"] = BrandVoice.objects.filter(
                brand_id__in=selected_brand_ids
            ).delete()[0]
            counts["brands"] = owned_brands.delete()[0]
    except Exception as error:
        logger.exception(
            "Brand deletion failed for owner=%s brands=%s",
            owner_id,
            brand_ids,
        )
        raise BrandDeletionError() from error

    return counts
