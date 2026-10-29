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
    UserSubscription,
)


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
    brand_name = serializers.CharField(source="brand.name", read_only=True)

    class Meta:
        model = ContentPost
        fields = ["id", "brand_name", "title", "body", "platform"]
        read_only_fields = fields


class ScheduledPostSerializer(serializers.ModelSerializer):
    post = ScheduledPostContentSerializer(read_only=True)

    class Meta:
        model = ScheduledPost
        fields = [
            "id",
            "post",
            "platform",
            "scheduled_for",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


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
    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "status",
            "amount_minor",
            "currency",
            "occurred_at",
            "created_at",
        ]
        read_only_fields = fields


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