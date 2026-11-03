from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import ContentPost, ScheduledPost
from .notifications import notify_publishing_result
from .social_platforms import (
    SCHEDULING_PLATFORM_LABELS,
    publishing_available,
    publishing_unavailable_reason,
)

# A publisher must only be registered here once it really publishes to the
# platform and returns the remote post identifier. Until then posts reach the
# BLOCKED state instead of being reported as published.
PUBLISHERS = {}

MAX_PUBLISH_ATTEMPTS = 3
RETRY_BACKOFF_MINUTES = 5
STUCK_PUBLISHING_MINUTES = 15


class SchedulingError(Exception):
    def __init__(self, code, message, status_code=400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class PublishingError(Exception):
    def __init__(self, message, transient=True):
        self.transient = transient
        super().__init__(message)


def resolve_timezone(timezone_name):
    name = (timezone_name or "UTC").strip() or "UTC"
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise SchedulingError(
            "invalid_timezone",
            "The selected timezone is not recognised.",
        ) from error
    return name


def validate_scheduled_for(scheduled_for, *, now=None):
    now = now or timezone.now()
    if scheduled_for is None:
        raise SchedulingError(
            "scheduled_for_required",
            "A scheduled date and time is required.",
        )
    if timezone.is_naive(scheduled_for):
        raise SchedulingError(
            "scheduled_for_naive",
            "The scheduled time must include a timezone offset or be UTC.",
        )
    if scheduled_for <= now + timedelta(seconds=30):
        raise SchedulingError(
            "scheduled_for_past",
            "Choose a scheduled time in the future.",
        )
    return scheduled_for


def _owned_post(owner_id, post_id):
    try:
        return (
            ContentPost.objects.select_for_update()
            .select_related("brand")
            .get(id=post_id, brand__owner_id=owner_id)
        )
    except ContentPost.DoesNotExist as error:
        raise SchedulingError(
            "post_not_found",
            "Content post not found.",
            status_code=404,
        ) from error


def _validate_platforms(platforms):
    if not platforms:
        raise SchedulingError(
            "platforms_required",
            "Select at least one platform to publish to.",
        )
    unique = list(dict.fromkeys(platforms))
    invalid = [
        platform
        for platform in unique
        if platform not in SCHEDULING_PLATFORM_LABELS
    ]
    if invalid:
        raise SchedulingError(
            "unsupported_platform",
            f"Unsupported platform: {', '.join(invalid)}.",
        )
    return unique


def schedule_post(*, owner_id, post_id, platforms, scheduled_for, timezone_name):
    platforms = _validate_platforms(platforms)
    timezone_name = resolve_timezone(timezone_name)
    scheduled_for = validate_scheduled_for(scheduled_for)

    with transaction.atomic():
        post = _owned_post(owner_id, post_id)

        if post.status not in (
            ContentPost.Status.APPROVED,
            ContentPost.Status.SCHEDULED,
        ):
            raise SchedulingError(
                "approval_required",
                (
                    "Only approved content can be scheduled. Submit this post "
                    "for approval and wait for the decision first."
                ),
                status_code=409,
            )

        existing = list(
            ScheduledPost.objects.filter(
                post=post,
                platform__in=platforms,
                status__in=ScheduledPost.ACTIVE_STATUSES,
            ).values_list("platform", flat=True)
        )
        if existing:
            labels = ", ".join(
                SCHEDULING_PLATFORM_LABELS[platform] for platform in existing
            )
            raise SchedulingError(
                "already_scheduled",
                f"This content is already scheduled for {labels}.",
                status_code=409,
            )

        try:
            with transaction.atomic():
                created = [
                    ScheduledPost.objects.create(
                        post=post,
                        platform=platform,
                        scheduled_for=scheduled_for,
                        timezone_name=timezone_name,
                    )
                    for platform in platforms
                ]
        except IntegrityError as error:
            raise SchedulingError(
                "already_scheduled",
                "This content is already scheduled for one of the selected "
                "platforms.",
                status_code=409,
            ) from error

        if post.status != ContentPost.Status.SCHEDULED:
            post.status = ContentPost.Status.SCHEDULED
            post.save(update_fields=["status", "updated_at"])

    return created


def reschedule_scheduled_post(
    *, owner_id, scheduled_id, scheduled_for=None, timezone_name=None
):
    with transaction.atomic():
        try:
            scheduled = (
                ScheduledPost.objects.select_for_update()
                .select_related("post")
                .get(id=scheduled_id, post__brand__owner_id=owner_id)
            )
        except ScheduledPost.DoesNotExist as error:
            raise SchedulingError(
                "scheduled_post_not_found",
                "Scheduled post not found.",
                status_code=404,
            ) from error

        if scheduled.status not in (
            ScheduledPost.Status.PENDING,
            ScheduledPost.Status.BLOCKED,
            ScheduledPost.Status.FAILED,
        ):
            raise SchedulingError(
                "not_reschedulable",
                "Only posts that have not been published can be rescheduled.",
                status_code=409,
            )

        if scheduled_for is not None:
            scheduled.scheduled_for = validate_scheduled_for(scheduled_for)
        if timezone_name is not None:
            scheduled.timezone_name = resolve_timezone(timezone_name)

        # Blocked or failed schedules are revived when the user reschedules.
        # A failed schedule gets a fresh retry budget only after a human edit.
        if scheduled.status in (
            ScheduledPost.Status.BLOCKED,
            ScheduledPost.Status.FAILED,
        ):
            if scheduled.status == ScheduledPost.Status.FAILED:
                scheduled.attempts = 0
            scheduled.status = ScheduledPost.Status.PENDING
            scheduled.error_message = ""

        scheduled.save(
            update_fields=[
                "scheduled_for",
                "timezone_name",
                "status",
                "error_message",
                "attempts",
                "updated_at",
            ]
        )

    return scheduled


def cancel_scheduled_post(*, owner_id, scheduled_id):
    with transaction.atomic():
        try:
            scheduled = (
                ScheduledPost.objects.select_for_update()
                .select_related("post")
                .get(id=scheduled_id, post__brand__owner_id=owner_id)
            )
        except ScheduledPost.DoesNotExist as error:
            raise SchedulingError(
                "scheduled_post_not_found",
                "Scheduled post not found.",
                status_code=404,
            ) from error

        if scheduled.status not in (
            ScheduledPost.Status.PENDING,
            ScheduledPost.Status.BLOCKED,
            ScheduledPost.Status.FAILED,
        ):
            raise SchedulingError(
                "not_cancellable",
                (
                    "This post is already publishing or has finished, so it "
                    "cannot be cancelled."
                ),
                status_code=409,
            )

        scheduled.status = ScheduledPost.Status.CANCELLED
        scheduled.publishing_started_at = None
        scheduled.save(
            update_fields=[
                "status",
                "publishing_started_at",
                "updated_at",
            ]
        )

        still_scheduled = ScheduledPost.objects.filter(
            post=scheduled.post,
            status__in=ScheduledPost.ACTIVE_STATUSES,
        ).exists()
        if (
            not still_scheduled
            and scheduled.post.status == ContentPost.Status.SCHEDULED
        ):
            scheduled.post.status = ContentPost.Status.APPROVED
            scheduled.post.save(update_fields=["status", "updated_at"])

    return scheduled


def _recover_stuck_publishing(now):
    cutoff = now - timedelta(minutes=STUCK_PUBLISHING_MINUTES)
    return ScheduledPost.objects.filter(
        status=ScheduledPost.Status.PUBLISHING,
        publishing_started_at__lt=cutoff,
    ).update(
        status=ScheduledPost.Status.PENDING,
        publishing_started_at=None,
        error_message=(
            "The previous publishing attempt was interrupted and will be "
            "retried."
        ),
    )


def _publish_blocked(scheduled, reason):
    scheduled.status = ScheduledPost.Status.BLOCKED
    scheduled.publishing_started_at = None
    scheduled.error_message = reason
    scheduled.save(
        update_fields=[
            "status",
            "error_message",
            "attempts",
            "last_attempt_at",
            "publishing_started_at",
            "updated_at",
        ]
    )
    notify_publishing_result(scheduled, "blocked", reason)


def _publish_failed(scheduled, reason):
    scheduled.status = ScheduledPost.Status.FAILED
    scheduled.publishing_started_at = None
    scheduled.error_message = reason
    scheduled.save(
        update_fields=[
            "status",
            "error_message",
            "attempts",
            "last_attempt_at",
            "publishing_started_at",
            "updated_at",
        ]
    )
    notify_publishing_result(scheduled, "failed", reason)


def _publish_one(scheduled, now):
    """Attempt one due post. Returns the outcome name."""
    scheduled.attempts += 1
    scheduled.last_attempt_at = now

    if not publishing_available(scheduled.platform):
        _publish_blocked(
            scheduled,
            publishing_unavailable_reason(scheduled.platform),
        )
        return "blocked"

    publisher = PUBLISHERS.get(scheduled.platform)
    if publisher is None:
        _publish_blocked(
            scheduled,
            publishing_unavailable_reason(scheduled.platform),
        )
        return "blocked"

    scheduled.status = ScheduledPost.Status.PUBLISHING
    scheduled.publishing_started_at = now
    scheduled.error_message = ""
    scheduled.save(
        update_fields=[
            "status",
            "publishing_started_at",
            "error_message",
            "attempts",
            "last_attempt_at",
            "updated_at",
        ]
    )

    try:
        external_post_id = publisher(scheduled)
    except PublishingError as error:
        if error.transient and scheduled.attempts < MAX_PUBLISH_ATTEMPTS:
            scheduled.status = ScheduledPost.Status.PENDING
            scheduled.publishing_started_at = None
            scheduled.error_message = str(error)
            scheduled.scheduled_for = now + timedelta(
                minutes=RETRY_BACKOFF_MINUTES * scheduled.attempts
            )
            scheduled.save(
                update_fields=[
                    "status",
                    "publishing_started_at",
                    "error_message",
                    "scheduled_for",
                    "updated_at",
                ]
            )
            return "retried"
        _publish_failed(scheduled, str(error))
        return "failed"
    except Exception as error:  # pragma: no cover - defensive worker guard
        _publish_failed(
            scheduled,
            f"Unexpected publishing error: {type(error).__name__}.",
        )
        return "failed"

    if not external_post_id:
        _publish_failed(
            scheduled,
            "The platform did not confirm a published post ID.",
        )
        return "failed"

    scheduled.status = ScheduledPost.Status.PUBLISHED
    scheduled.publishing_started_at = None
    scheduled.external_post_id = str(external_post_id)
    scheduled.published_at = now
    scheduled.save(
        update_fields=[
            "status",
            "external_post_id",
            "published_at",
            "publishing_started_at",
            "attempts",
            "last_attempt_at",
            "updated_at",
        ]
    )
    post = scheduled.post
    post.status = ContentPost.Status.PUBLISHED
    post.save(update_fields=["status", "updated_at"])
    notify_publishing_result(
        scheduled,
        "published",
        "The platform confirmed this post was published.",
    )
    return "published"


def publish_due_posts(*, now=None, limit=25):
    """Publish posts whose scheduled time has passed.

    Safe to run from cron or a long-lived process: rows are claimed with
    ``SELECT ... FOR UPDATE SKIP LOCKED`` so two workers cannot process the
    same post, and interrupted attempts are returned to the queue.
    """
    now = now or timezone.now()
    recovered = _recover_stuck_publishing(now)
    counts = {
        "processed": 0,
        "published": 0,
        "blocked": 0,
        "failed": 0,
        "retried": 0,
        "recovered": recovered,
    }

    with transaction.atomic():
        due = list(
            ScheduledPost.objects.select_for_update(skip_locked=True)
            .select_related("post", "post__brand")
            .filter(
                status=ScheduledPost.Status.PENDING,
                scheduled_for__lte=now,
            )
            .order_by("scheduled_for")[:limit]
        )
        for scheduled in due:
            counts["processed"] += 1
            counts[_publish_one(scheduled, now)] += 1

    return counts
