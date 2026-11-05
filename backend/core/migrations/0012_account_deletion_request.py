import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_stripe_checkout_attempt"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountDeletionRequest",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("owner_id", models.UUIDField(unique=True)),
                (
                    "subscriptions_canceled_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "local_data_purged_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "supabase_identity_deleted_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                ("last_error", models.CharField(blank=True, max_length=64)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
