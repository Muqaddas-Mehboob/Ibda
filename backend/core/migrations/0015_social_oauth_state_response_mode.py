from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_facebook_pages_oauth_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="socialoauthstate",
            name="response_mode",
            field=models.CharField(
                choices=[("native", "Native app"), ("web", "Web app")],
                default="native",
                max_length=8,
            ),
        ),
    ]
