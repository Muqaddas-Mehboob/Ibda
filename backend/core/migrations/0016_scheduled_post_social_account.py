import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_social_oauth_state_response_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduledpost",
            name="social_account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="scheduled_posts",
                to="core.socialaccount",
            ),
        ),
    ]
