from rest_framework import serializers
from .models import Brand


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = [
            "id",
            "name",
            "description",
            "website",
            "industry",
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