from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import ScheduledPost
from .services.notifications import notify_schedule_change


@receiver(pre_save, sender=ScheduledPost)
def capture_previous_schedule(sender, instance, **kwargs):
    if instance._state.adding:
        instance._previous_scheduled_for = None
        return

    instance._previous_scheduled_for = (
        sender.objects.filter(id=instance.id)
        .values_list("scheduled_for", flat=True)
        .first()
    )


@receiver(post_save, sender=ScheduledPost)
def create_schedule_notification(sender, instance, created, update_fields, **kwargs):
    if created:
        notify_schedule_change(instance, created=True)
    elif (
        (update_fields is None or "scheduled_for" in update_fields)
        and instance._previous_scheduled_for != instance.scheduled_for
    ):
        notify_schedule_change(instance, created=False)
