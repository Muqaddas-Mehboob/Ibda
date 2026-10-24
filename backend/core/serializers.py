from rest_framework import serializers
from .models import Approval, Brand, BrandVoice


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