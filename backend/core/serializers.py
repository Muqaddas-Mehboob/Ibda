from rest_framework import serializers
from .models import (
    Approval,
    Brand,
    BrandVoice,
    ContentPost,
    Notification,
    PaymentTransaction,
    ScheduledPost,
    SocialAccount,
    SupportRequest,
    UserSubscription,
)
from .services.social_platforms import publishing_available
from .services.payments.catalog import PLAN_DEFINITIONS


class BrandVoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandVoice
        fields = [
            "id",
            "brand",
            "tone",
            "target_audience",
            "language",
            "writing_guidelines",
            "example_content",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "brand", "created_at", "updated_at"]


class BrandSerializer(serializers.ModelSerializer):
    voice = BrandVoiceSerializer(
        source="brand_voice",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Brand
        fields = [
            "id",
            "name",
            "description",
            "website",
            "industry",
            "voice",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Brand name is required."
            )

        return value

    def validate_website(self, value):
        return value.strip() if value else ""

    def create(self, validated_data):
        validated_data["owner_id"] = self.context["request"].user.id
        return super().create(validated_data)


class ApprovalPostSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    brand_id = serializers.UUIDField(source="brand.id", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    title = serializers.CharField(read_only=True)
    body = serializers.CharField(read_only=True)
    platform = serializers.CharField(read_only=True)
    post_status = serializers.CharField(source="status", read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class ApprovalSerializer(serializers.ModelSerializer):
    post = ApprovalPostSerializer(read_only=True)

    class Meta:
        model = Approval
        fields = [
            "id",
            "post",
            "status",
            "feedback",
            "reviewer_id",
            "reviewed_at",
            "created_at",
        ]
        read_only_fields = fields


class ContentGenerationSerializer(serializers.Serializer):
    brand_id = serializers.UUIDField()
    platform = serializers.ChoiceField(choices=ContentPost.Platform.choices)
    content_type = serializers.ChoiceField(
        choices=ContentPost.ContentType.choices
    )
    topic = serializers.CharField(max_length=300, trim_whitespace=True)
    tone = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    language = serializers.CharField(
        max_length=50,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    keywords = serializers.ListField(
        child=serializers.CharField(max_length=60, trim_whitespace=True),
        required=False,
        allow_empty=True,
        max_length=12,
    )
    call_to_action = serializers.CharField(
        max_length=300,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )

    def validate_topic(self, value):
        if not value:
            raise serializers.ValidationError("A topic is required.")
        return value

    def validate_keywords(self, values):
        return [value for value in values if value]

class GEOOptimizationSerializer(serializers.Serializer):
    brand_id = serializers.UUIDField()

    platform = serializers.ChoiceField(
        choices=ContentPost.Platform.choices
    )

    content = serializers.CharField(
        max_length=10000,
        trim_whitespace=True,
    )

    def validate_content(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                "Content is required for GEO optimization."
            )
        return value
class ContentPostSerializer(serializers.ModelSerializer):
    brand_id = serializers.PrimaryKeyRelatedField(
        source="brand",
        queryset=Brand.objects.none(),
        write_only=True,
        required=False,
    )
    brand_name = serializers.CharField(source="brand.name", read_only=True)

    class Meta:
        model = ContentPost
        fields = [
            "id",
            "brand_id",
            "brand_name",
            "title",
            "body",
            "platform",
            "content_type",
            "status",
            "ai_generated",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "brand_name",
            "status",
            "ai_generated",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None:
            self.fields["brand_id"].queryset = Brand.objects.filter(
                owner_id=request.user.id
            )

    def validate_body(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Content text is required.")
        if len(value) > 10000:
            raise serializers.ValidationError(
                "Content must be 10,000 characters or fewer."
            )
        return value

    def validate(self, attrs):
        if self.instance is None and "brand" not in attrs:
            raise serializers.ValidationError(
                {"brand_id": "A brand is required to save content."}
            )
        return attrs


class ScheduledPostContentSerializer(serializers.ModelSerializer):
    brand_id = serializers.UUIDField(source="brand.id", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True)

    class Meta:
        model = ContentPost
        fields = [
            "id",
            "brand_id",
            "brand_name",
            "title",
            "body",
            "platform",
            "status",
        ]
        read_only_fields = fields


class ScheduledPostSerializer(serializers.ModelSerializer):
    post = ScheduledPostContentSerializer(read_only=True)
    publishing_available = serializers.SerializerMethodField()

    class Meta:
        model = ScheduledPost
        fields = [
            "id",
            "post",
            "platform",
            "scheduled_for",
            "timezone_name",
            "status",
            "attempts",
            "last_attempt_at",
            "error_message",
            "external_post_id",
            "published_at",
            "publishing_available",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_publishing_available(self, scheduled_post):
        return publishing_available(scheduled_post.platform)


class ScheduledPostCreateSerializer(serializers.Serializer):
    post_id = serializers.UUIDField()
    platforms = serializers.ListField(
        child=serializers.ChoiceField(choices=ContentPost.Platform.choices),
        allow_empty=False,
        max_length=len(ContentPost.Platform.choices),
    )
    scheduled_for = serializers.DateTimeField()
    timezone_name = serializers.CharField(
        max_length=64,
        required=False,
        default="UTC",
        allow_blank=False,
        trim_whitespace=True,
    )


class ScheduledPostUpdateSerializer(serializers.Serializer):
    scheduled_for = serializers.DateTimeField(required=False)
    timezone_name = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=False,
        trim_whitespace=True,
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "Provide a new scheduled time or timezone."
            )
        return attrs


class PublishingCapabilitySerializer(serializers.Serializer):
    platform = serializers.CharField()
    label = serializers.CharField()
    available = serializers.BooleanField()
    reason = serializers.CharField()


class ScheduledPostRangeSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()

    def validate(self, attrs):
        if attrs["end"] <= attrs["start"]:
            raise serializers.ValidationError(
                {"end": "End must be later than start."}
            )
        return attrs


class AnalyticsRangeSerializer(serializers.Serializer):
    days = serializers.ChoiceField(
        choices=(7, 30, 90),
        default=30,
    )


class AnalyticsSummarySerializer(serializers.Serializer):
    content_posts = serializers.IntegerField()
    pending_approvals = serializers.IntegerField()
    approved_content = serializers.IntegerField()
    rejected_content = serializers.IntegerField()
    scheduled_posts = serializers.IntegerField()


class AnalyticsActivitySerializer(serializers.Serializer):
    date = serializers.DateField()
    content_posts = serializers.IntegerField()


class AnalyticsBrandSerializer(serializers.Serializer):
    brand_id = serializers.UUIDField()
    brand_name = serializers.CharField()
    content_posts = serializers.IntegerField()


class AnalyticsPeriodSerializer(serializers.Serializer):
    days = serializers.IntegerField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()


class AnalyticsResponseSerializer(serializers.Serializer):
    range = AnalyticsPeriodSerializer()
    summary = AnalyticsSummarySerializer()
    activity_granularity = serializers.ChoiceField(choices=("day", "week"))
    activity = AnalyticsActivitySerializer(many=True)
    brands = AnalyticsBrandSerializer(many=True)


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "title",
            "message",
            "related_object_id",
            "destination",
            "is_read",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_is_read(self, notification):
        return notification.read_at is not None


class SupportRequestCreateSerializer(serializers.ModelSerializer):
    contact_email = serializers.EmailField(
        max_length=254,
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = SupportRequest
        fields = ["contact_email", "subject", "message"]

    def validate_subject(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A subject is required.")
        return value

    def validate_message(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A message is required.")
        return value


class SocialAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialAccount
        fields = [
            "id",
            "platform",
            "platform_account_id",
            "display_name",
            "status",
            "token_expires_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ConnectedAccountsResponseSerializer(serializers.Serializer):
    providers = serializers.ListField(child=serializers.DictField())
    accounts = SocialAccountSerializer(many=True)


class UserSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSubscription
        fields = [
            "id",
            "provider",
            "plan_id",
            "billing_interval",
            "status",
            "current_period_start",
            "current_period_end",
            "cancel_at_period_end",
            "canceled_at",
            "created_at",
        ]
        read_only_fields = fields


class PaymentTransactionSerializer(serializers.ModelSerializer):
    transaction_id = serializers.CharField(
        source="provider_transaction_id",
        read_only=True,
    )
    subscription_id = serializers.UUIDField(read_only=True)
    plan_id = serializers.SerializerMethodField()
    plan_name = serializers.SerializerMethodField()
    billing_interval = serializers.SerializerMethodField()
    subscription_status = serializers.CharField(
        source="subscription.status",
        read_only=True,
    )

    def get_plan_id(self, obj):
        return obj.plan_id or obj.subscription.plan_id

    def get_plan_name(self, obj):
        if obj.plan_name:
            return obj.plan_name
        plan_id = self.get_plan_id(obj)
        return next(
            (name for configured_id, name in PLAN_DEFINITIONS if configured_id == plan_id),
            plan_id,
        )

    def get_billing_interval(self, obj):
        return obj.billing_interval or obj.subscription.billing_interval

    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "transaction_id",
            "subscription_id",
            "plan_id",
            "plan_name",
            "billing_interval",
            "transaction_type",
            "subscription_status",
            "status",
            "amount_minor",
            "currency",
            "checkout_session_id",
            "payment_intent_id",
            "invoice_id",
            "payment_method_type",
            "payment_method_brand",
            "payment_method_last4",
            "receipt_url",
            "occurred_at",
            "paid_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    payment_intent_id = serializers.CharField(
        source="provider_payment_intent_id",
        read_only=True,
    )
    invoice_id = serializers.CharField(
        source="provider_invoice_id",
        read_only=True,
    )


class CheckoutRequestSerializer(serializers.Serializer):
    plan_id = serializers.ChoiceField(
        choices=(
            "starter",
            "pro",
            "enterprise",
            "premium_monthly",
            "premium_annual",
        )
    )
    billing_interval = serializers.ChoiceField(
        choices=("monthly", "annual"),
        required=False,
    )
    platform = serializers.ChoiceField(
        choices=("web", "mobile"),
        default="web",
    )

    def validate(self, attrs):
        legacy_plan = attrs["plan_id"]
        if legacy_plan in ("premium_monthly", "premium_annual"):
            if "billing_interval" in attrs:
                raise serializers.ValidationError(
                    {"billing_interval": "Do not send this with a legacy plan ID."}
                )
            attrs["plan_id"] = "pro"
            attrs["billing_interval"] = (
                "monthly" if legacy_plan.endswith("monthly") else "annual"
            )
        elif "billing_interval" not in attrs:
            raise serializers.ValidationError(
                {"billing_interval": "This field is required."}
            )
        return attrs


class CheckoutSessionVerificationSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=255)


class SubscriptionCancelRequestSerializer(serializers.Serializer):
    cancel_at_period_end = serializers.BooleanField(default=True)


class SubscriptionPortalRequestSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(
        choices=("web", "mobile"),
        default="web",
    )


class SubscriptionPlanSwitchRequestSerializer(serializers.Serializer):
    plan_id = serializers.ChoiceField(choices=("starter", "pro", "enterprise"))
    billing_interval = serializers.ChoiceField(choices=("monthly", "annual"))


class SubscriptionPlansRequestSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(
        choices=("web", "mobile"),
        default="web",
    )


class PaymentWebhookSerializer(serializers.Serializer):
    event_id = serializers.CharField(max_length=255)
    event_type = serializers.ChoiceField(
        choices=("subscription.updated", "transaction.updated")
    )
    subscription_id = serializers.CharField(max_length=255)
    status = serializers.CharField(max_length=20)
    plan_id = serializers.CharField(max_length=100, required=False)
    billing_interval = serializers.ChoiceField(
        choices=UserSubscription.BillingInterval.choices,
        required=False,
    )
    current_period_start = serializers.DateTimeField(required=False, allow_null=True)
    current_period_end = serializers.DateTimeField(required=False, allow_null=True)
    cancel_at_period_end = serializers.BooleanField(required=False)
    canceled_at = serializers.DateTimeField(required=False, allow_null=True)
    transaction_id = serializers.CharField(max_length=255, required=False)
    amount_minor = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    currency = serializers.RegexField(r"^[A-Z]{3}$", required=False, allow_blank=True)
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs["event_type"] == "subscription.updated":
            if attrs["status"] not in UserSubscription.Status.values:
                raise serializers.ValidationError(
                    {"status": "Unsupported subscription status."}
                )
        else:
            if "transaction_id" not in attrs:
                raise serializers.ValidationError(
                    {"transaction_id": "This field is required for transactions."}
                )
            if attrs["status"] not in PaymentTransaction.Status.values:
                raise serializers.ValidationError(
                    {"status": "Unsupported transaction status."}
                )
        return attrs