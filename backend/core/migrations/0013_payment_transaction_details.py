from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_account_deletion_request"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymenttransaction",
            name="billing_interval",
            field=models.CharField(
                choices=[("monthly", "Monthly"), ("annual", "Annual"), ("none", "No billing interval")],
                default="none",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="checkout_session_id",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="paid_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="payment_method_brand",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="payment_method_last4",
            field=models.CharField(blank=True, max_length=4),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="payment_method_type",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="plan_id",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="plan_name",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="provider_charge_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="provider_customer_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="provider_event_created_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="provider_event_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="provider_invoice_id",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="provider_payment_intent_id",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="provider_subscription_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="receipt_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="transaction_type",
            field=models.CharField(
                choices=[
                    ("initial_payment", "Initial payment"),
                    ("renewal", "Renewal"),
                    ("plan_change", "Plan change"),
                    ("refund", "Refund"),
                    ("other", "Other"),
                ],
                default="other",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="paymenttransaction",
            constraint=models.UniqueConstraint(
                fields=("provider", "provider_invoice_id"),
                condition=~models.Q(provider_invoice_id="")
                & ~models.Q(transaction_type="refund"),
                name="unique_provider_payment_invoice",
            ),
        ),
        migrations.AddConstraint(
            model_name="paymenttransaction",
            constraint=models.UniqueConstraint(
                fields=("provider", "provider_payment_intent_id"),
                condition=~models.Q(provider_payment_intent_id="")
                & ~models.Q(transaction_type="refund"),
                name="unique_provider_payment_intent",
            ),
        ),
        migrations.AddConstraint(
            model_name="paymenttransaction",
            constraint=models.UniqueConstraint(
                fields=("provider", "checkout_session_id"),
                condition=~models.Q(checkout_session_id="")
                & ~models.Q(transaction_type="refund"),
                name="unique_provider_checkout_payment",
            ),
        ),
    ]