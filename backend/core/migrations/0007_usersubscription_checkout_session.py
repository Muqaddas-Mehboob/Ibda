from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_usersubscription_last_provider_event_created_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="usersubscription",
            name="checkout_session_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="usersubscription",
            name="checkout_session_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
