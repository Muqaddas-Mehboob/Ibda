from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0017_link_scheduled_posts_to_pages"),
    ]

    operations = [
        migrations.AddField(
            model_name="contentpost",
            name="image_url",
            field=models.URLField(blank=True, max_length=500),
        ),
    ]
