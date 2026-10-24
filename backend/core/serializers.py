from rest_framework import serializers
from .models import Approval, Brand, BrandVoice, ContentPost, ScheduledPost


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