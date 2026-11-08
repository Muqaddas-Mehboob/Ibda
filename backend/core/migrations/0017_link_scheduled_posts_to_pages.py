from django.db import migrations


def link_unambiguous_pages(apps, schema_editor):
    """Link pre-existing Facebook schedules to the owner's only connected Page.

    Schedules created before Page targeting existed have no social account. When
    an owner has exactly one connected Page the target is unambiguous, so the
    schedule can publish instead of being blocked. Owners with several Pages
    must pick one explicitly by rescheduling.
    """
    ScheduledPost = apps.get_model("core", "ScheduledPost")
    SocialAccount = apps.get_model("core", "SocialAccount")

    schedules = ScheduledPost.objects.filter(
        platform="facebook",
        social_account__isnull=True,
        status__in=["pending", "blocked", "failed"],
    ).select_related("post__brand")

    for scheduled in schedules:
        accounts = SocialAccount.objects.filter(
            owner_id=scheduled.post.brand.owner_id,
            platform="facebook_pages",
            status="connected",
        )
        if accounts.count() == 1:
            scheduled.social_account_id = accounts.first().id
            scheduled.save(update_fields=["social_account"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_scheduled_post_social_account"),
    ]

    operations = [
        migrations.RunPython(link_unambiguous_pages, migrations.RunPython.noop),
    ]
