from ..models import Approval, Notification, ScheduledPost


def notify_approval_decision(approval):
    decision = approval.status
    if decision not in (
        Approval.Status.APPROVED,
        Approval.Status.REJECTED,
    ):
        raise ValueError("Only completed approval decisions can be notified.")

    brand_name = approval.post.brand.name
    post_name = approval.post.title or brand_name
    approved = decision == Approval.Status.APPROVED
    Notification.objects.get_or_create(
        event_key=f"approval:{approval.id}:{decision}",
        defaults={
            "recipient_user_id": approval.post.brand.owner_id,
            "notification_type": (
                Notification.Type.APPROVAL_APPROVED
                if approved
                else Notification.Type.APPROVAL_REJECTED
            ),
            "title": "Content approved" if approved else "Content rejected",
            "message": (
                f'"{post_name}" for {brand_name} was '
                f'{"approved" if approved else "rejected"}.'
            ),
            "related_object_id": approval.id,
            "destination": Notification.Destination.APPROVAL,
        },
    )


def notify_schedule_change(scheduled_post, *, created):
    scheduled_post = ScheduledPost.objects.select_related(
        "post",
        "post__brand",
    ).get(id=scheduled_post.id)
    brand = scheduled_post.post.brand
    post_name = scheduled_post.post.title or brand.name
    event = "created" if created else "updated"
    Notification.objects.get_or_create(
        event_key=f"scheduled-post:{scheduled_post.id}:{event}:"
        f"{scheduled_post.scheduled_for.isoformat()}",
        defaults={
            "recipient_user_id": brand.owner_id,
            "notification_type": (
                Notification.Type.SCHEDULED_POST_CREATED
                if created
                else Notification.Type.SCHEDULED_POST_UPDATED
            ),
            "title": "Post scheduled" if created else "Schedule updated",
            "message": (
                f'"{post_name}" is {event} for '
                f"{scheduled_post.scheduled_for.isoformat()}."
            ),
            "related_object_id": scheduled_post.id,
            "destination": Notification.Destination.CALENDAR,
        },
    )
