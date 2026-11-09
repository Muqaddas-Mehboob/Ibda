from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_content_post_image_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="socialaccount",
            name="client_business_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="socialaccount",
            name="oauth_config_id",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
