from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_scheduled_post_publishing"),
    ]

    operations = [
        migrations.AddField(
            model_name="providerwebhookevent",
            name="status",
            field=models.CharField(
                choices=[
                    ("processed", "Processed"),
                    ("needs_attention", "Needs attention"),
                ],
                db_index=True,
                default="processed",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="providerwebhookevent",
            name="detail",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
