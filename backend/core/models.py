from django.db import models
import uuid

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Brand(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # UUID of the authenticated user in Supabase Auth
    owner_id = models.UUIDField(db_index=True)

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    website = models.URLField(blank=True)
    industry = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class BrandVoice(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    brand = models.OneToOneField(
        Brand,
        on_delete=models.CASCADE,
        related_name="brand_voice",
    )

    tone = models.CharField(max_length=100, default="Friendly")
    target_audience = models.TextField(blank=True)
    language = models.CharField(max_length=50, default="English")
    writing_guidelines = models.TextField(blank=True)
    example_content = models.TextField(blank=True)

    def __str__(self):
        return f"Brand voice: {self.brand.name}"


class ContentPost(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        IN_REVIEW = "in_review", "In Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SCHEDULED = "scheduled", "Scheduled"
        PUBLISHED = "published", "Published"

    class Platform(models.TextChoices):
        INSTAGRAM = "instagram", "Instagram"
        FACEBOOK = "facebook", "Facebook"
        LINKEDIN = "linkedin", "LinkedIn"
        TIKTOK = "tiktok", "TikTok"
        X = "x", "X"
        OTHER = "other", "Other"

    class ContentType(models.TextChoices):
        CAPTION = "caption", "Caption"
        PROMOTIONAL = "promotional", "Promotional post"
        EDUCATIONAL = "educational", "Educational post"
        ANNOUNCEMENT = "announcement", "Announcement"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        related_name="content_posts",
    )

    title = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    content_type = models.CharField(
        max_length=30,
        choices=ContentType.choices,
        default=ContentType.CAPTION,
    )
    platform = models.CharField(
        max_length=20,
        choices=Platform.choices,
        default=Platform.INSTAGRAM,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    ai_generated = models.BooleanField(default=False)
    hashtags = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or f"Post {self.id}"


class Approval(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(
        ContentPost,
        on_delete=models.CASCADE,
        related_name="approvals",
    )

    # Supabase Auth UUID of the reviewer; optional until assigned
    reviewer_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    feedback = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Approval for {self.post_id}: {self.status}"


class ScheduledPost(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(
        ContentPost,
        on_delete=models.CASCADE,
        related_name="scheduled_posts",
    )

    platform = models.CharField(
        max_length=20,
        choices=ContentPost.Platform.choices,
        default=ContentPost.Platform.INSTAGRAM,
    )
    scheduled_for = models.DateTimeField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    external_post_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["scheduled_for"]

    def __str__(self):
        return f"{self.post_id} scheduled for {self.scheduled_for}"


class Notification(TimeStampedModel):
    class Type(models.TextChoices):
        APPROVAL_APPROVED = "approval_approved", "Content approved"
        APPROVAL_REJECTED = "approval_rejected", "Content rejected"
        SCHEDULED_POST_CREATED = "scheduled_post_created", "Post scheduled"
        SCHEDULED_POST_UPDATED = "scheduled_post_updated", "Schedule updated"

    class Destination(models.TextChoices):
        APPROVAL = "approval", "Approval"
        CALENDAR = "calendar", "Calendar"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient_user_id = models.UUIDField(db_index=True)
    notification_type = models.CharField(max_length=40, choices=Type.choices)
    title = models.CharField(max_length=160)
    message = models.TextField()
    related_object_id = models.UUIDField(null=True, blank=True)
    destination = models.CharField(
        max_length=20,
        choices=Destination.choices,
        blank=True,
    )
    event_key = models.CharField(max_length=120, unique=True)
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} for {self.recipient_user_id}"


class SocialAccount(TimeStampedModel):
    class Platform(models.TextChoices):
        INSTAGRAM = "instagram", "Instagram"
        FACEBOOK_PAGES = "facebook_pages", "Facebook Pages"
        LINKEDIN = "linkedin", "LinkedIn"
        TIKTOK = "tiktok", "TikTok"

    class Status(models.TextChoices):
        CONNECTED = "connected", "Connected"
        EXPIRED = "expired", "Expired"
        DISCONNECTED = "disconnected", "Disconnected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_id = models.UUIDField(db_index=True)
    platform = models.CharField(max_length=24, choices=Platform.choices)
    platform_account_id = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CONNECTED,
        db_index=True,
    )
    access_token_encrypted = models.TextField(blank=True)
    refresh_token_encrypted = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    scopes = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["platform", "display_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner_id", "platform", "platform_account_id"],
                name="unique_owner_social_platform_account",
            )
        ]

    def __str__(self):
        return f"{self.platform} account for {self.owner_id}"


class UserSubscription(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"
        EXPIRED = "expired", "Expired"
        FAILED = "failed", "Failed"

    class BillingInterval(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        ANNUAL = "annual", "Annual"
        NONE = "none", "No billing interval"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_id = models.UUIDField(db_index=True)
    provider = models.CharField(max_length=40, blank=True)
    provider_customer_id = models.CharField(max_length=255, blank=True)
    provider_subscription_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )
    plan_id = models.CharField(max_length=100, default="free")
    billing_interval = models.CharField(
        max_length=10,
        choices=BillingInterval.choices,
        default=BillingInterval.NONE,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner_id"],
                condition=models.Q(status__in=["pending", "active", "past_due"]),
                name="unique_current_user_subscription",
            ),
            models.UniqueConstraint(
                fields=["provider", "provider_subscription_id"],
                condition=models.Q(provider_subscription_id__isnull=False),
                name="unique_provider_subscription",
            ),
        ]
        indexes = [
            models.Index(fields=["owner_id", "status"]),
            models.Index(fields=["provider", "provider_customer_id"]),
        ]

    def __str__(self):
        return f"{self.plan_id} subscription for {self.owner_id}"


class PaymentTransaction(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        UserSubscription,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    provider = models.CharField(max_length=40)
    provider_transaction_id = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    amount_minor = models.PositiveBigIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_transaction_id"],
                name="unique_provider_payment_transaction",
            )
        ]
        indexes = [models.Index(fields=["subscription", "status"])]

    def __str__(self):
        return f"{self.provider} transaction: {self.status}"


class ProviderWebhookEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=40)
    event_id = models.CharField(max_length=255)
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "event_id"],
                name="unique_provider_webhook_event",
            )
        ]
        indexes = [models.Index(fields=["provider", "processed_at"])]

    def __str__(self):
        return f"{self.provider} event {self.event_id}"
