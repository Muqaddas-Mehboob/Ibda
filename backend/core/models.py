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
    # Public HTTPS URL of the attached image, uploaded to Supabase Storage.
    # Instagram requires Meta to fetch the image from a public URL.
    image_url = models.URLField(max_length=500, blank=True)
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
        PUBLISHING = "publishing", "Publishing"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"
        BLOCKED = "blocked", "Publishing unavailable"
        CANCELLED = "cancelled", "Cancelled"

    ACTIVE_STATUSES = (Status.PENDING, Status.PUBLISHING)

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
    # The exact connected Page or Instagram account this schedule targets.
    social_account = models.ForeignKey(
        "SocialAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_posts",
    )
    # Stored in UTC; the user's zone is kept separately for display and auditing.
    scheduled_for = models.DateTimeField(db_index=True)
    timezone_name = models.CharField(max_length=64, default="UTC")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    attempts = models.PositiveSmallIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    publishing_started_at = models.DateTimeField(null=True, blank=True)
    external_post_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["scheduled_for"]
        constraints = [
            models.UniqueConstraint(
                fields=["post", "platform"],
                condition=models.Q(status__in=["pending", "publishing"]),
                name="unique_active_scheduled_post",
            )
        ]
        indexes = [
            models.Index(fields=["status", "scheduled_for"]),
        ]

    def __str__(self):
        return f"{self.post_id} scheduled for {self.scheduled_for}"


class Notification(TimeStampedModel):
    class Type(models.TextChoices):
        APPROVAL_APPROVED = "approval_approved", "Content approved"
        APPROVAL_REJECTED = "approval_rejected", "Content rejected"
        SCHEDULED_POST_CREATED = "scheduled_post_created", "Post scheduled"
        SCHEDULED_POST_UPDATED = "scheduled_post_updated", "Schedule updated"
        POST_PUBLISHED = "post_published", "Post published"
        POST_PUBLISH_FAILED = "post_publish_failed", "Publishing failed"
        POST_PUBLISH_BLOCKED = (
            "post_publish_blocked",
            "Publishing unavailable",
        )

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


class SupportRequest(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_id = models.UUIDField(db_index=True)
    contact_email = models.EmailField(max_length=254)
    subject = models.CharField(max_length=120)
    message = models.TextField(max_length=4000)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} ({self.get_status_display()})"


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


class SocialOAuthState(models.Model):
    class ResponseMode(models.TextChoices):
        NATIVE = "native", "Native app"
        WEB = "web", "Web app"

    state_digest = models.CharField(max_length=64, unique=True)
    owner_id = models.UUIDField(db_index=True)
    platform = models.CharField(
        max_length=24,
        choices=SocialAccount.Platform.choices,
    )
    response_mode = models.CharField(
        max_length=8,
        choices=ResponseMode.choices,
        default=ResponseMode.NATIVE,
    )
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["platform", "expires_at"],
                name="social_oauth_platform_exp_idx",
            )
        ]


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
    checkout_session_id = models.CharField(max_length=255, blank=True)
    checkout_session_expires_at = models.DateTimeField(null=True, blank=True)
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
    last_provider_event_created_at = models.DateTimeField(null=True, blank=True)
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


class StripeCheckoutAttempt(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    checkout_session_id = models.CharField(max_length=255, unique=True)
    owner_id = models.UUIDField(db_index=True)
    subscription = models.ForeignKey(
        UserSubscription,
        on_delete=models.CASCADE,
        related_name="stripe_checkout_attempts",
    )
    customer_id = models.CharField(max_length=255)
    plan_id = models.CharField(max_length=100)
    price_id = models.CharField(max_length=255)
    billing_interval = models.CharField(
        max_length=10,
        choices=UserSubscription.BillingInterval.choices,
    )
    stripe_created_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["subscription", "created_at"]),
            models.Index(fields=["owner_id", "created_at"]),
        ]

    def __str__(self):
        return f"Stripe checkout attempt {self.checkout_session_id}"


class PaymentTransaction(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    class TransactionType(models.TextChoices):
        INITIAL_PAYMENT = "initial_payment", "Initial payment"
        RENEWAL = "renewal", "Renewal"
        PLAN_CHANGE = "plan_change", "Plan change"
        REFUND = "refund", "Refund"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        UserSubscription,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    provider = models.CharField(max_length=40)
    provider_transaction_id = models.CharField(max_length=255)
    provider_customer_id = models.CharField(max_length=255, blank=True)
    checkout_session_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )
    provider_payment_intent_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )
    provider_invoice_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )
    provider_subscription_id = models.CharField(max_length=255, blank=True)
    provider_charge_id = models.CharField(max_length=255, blank=True)
    plan_id = models.CharField(max_length=100, blank=True)
    plan_name = models.CharField(max_length=100, blank=True)
    billing_interval = models.CharField(
        max_length=10,
        choices=UserSubscription.BillingInterval.choices,
        default=UserSubscription.BillingInterval.NONE,
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
        default=TransactionType.OTHER,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    amount_minor = models.PositiveBigIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_method_type = models.CharField(max_length=32, blank=True)
    payment_method_brand = models.CharField(max_length=32, blank=True)
    payment_method_last4 = models.CharField(max_length=4, blank=True)
    receipt_url = models.URLField(max_length=1000, blank=True)
    provider_event_id = models.CharField(max_length=255, blank=True)
    provider_event_created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_transaction_id"],
                name="unique_provider_payment_transaction",
            ),
            models.UniqueConstraint(
                fields=["provider", "provider_invoice_id"],
                condition=~models.Q(provider_invoice_id="")
                & ~models.Q(transaction_type="refund"),
                name="unique_provider_payment_invoice",
            ),
            models.UniqueConstraint(
                fields=["provider", "provider_payment_intent_id"],
                condition=~models.Q(provider_payment_intent_id="")
                & ~models.Q(transaction_type="refund"),
                name="unique_provider_payment_intent",
            ),
            models.UniqueConstraint(
                fields=["provider", "checkout_session_id"],
                condition=~models.Q(checkout_session_id="")
                & ~models.Q(transaction_type="refund"),
                name="unique_provider_checkout_payment",
            ),
        ]
        indexes = [models.Index(fields=["subscription", "status"])]

    def __str__(self):
        return f"{self.provider} transaction: {self.status}"


class ProviderWebhookEvent(models.Model):
    class Status(models.TextChoices):
        PROCESSED = "processed", "Processed"
        NEEDS_ATTENTION = "needs_attention", "Needs attention"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=40)
    event_id = models.CharField(max_length=255)
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PROCESSED,
        db_index=True,
    )
    detail = models.CharField(max_length=255, blank=True)

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


class AccountDeletionRequest(TimeStampedModel):
    """Progress marker for a deletion that spans several systems.

    The row exists only while a deletion is in flight. It records which steps
    already completed so a retry can resume, and ``local_data_purged_at`` marks
    an account whose local data is gone but whose Supabase identity could not be
    removed yet: authentication refuses protected endpoints for that account
    while keeping the deletion endpoint reachable for the retry.

    It contains no user content and is removed once deletion completes.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_id = models.UUIDField(unique=True)
    subscriptions_canceled_at = models.DateTimeField(null=True, blank=True)
    local_data_purged_at = models.DateTimeField(null=True, blank=True)
    supabase_identity_deleted_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Account deletion for {self.owner_id}"
