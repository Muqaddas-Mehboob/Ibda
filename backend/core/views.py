from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from .authentication import SupabaseAuthentication
from .models import Approval, Brand, BrandVoice, ContentPost
from .serializers import (
    ApprovalSerializer,
    BrandSerializer,
    BrandVoiceSerializer,
    ContentGenerationSerializer,
    ContentPostSerializer,
)
from .services.content_generation import (
    ContentGenerationError,
    generate_content,
)

def health_check(request):
    return JsonResponse({
        "status": "ok",
        "service": "Ibda API",
        "message": "Django backend is running.",
    })


class BrandListCreateView(generics.ListCreateAPIView):
    serializer_class = BrandSerializer
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Brand.objects.filter(
            owner_id=self.request.user.id
        ).select_related("brand_voice")

    def perform_create(self, serializer):
        serializer.save(owner_id=self.request.user.id)


class BrandDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BrandSerializer
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        return Brand.objects.filter(owner_id=self.request.user.id)

class BrandVoiceView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get_brand(self, request, brand_id):
        return Brand.objects.filter(
            id=brand_id,
            owner_id=request.user.id,
        ).first()

    def get(self, request, brand_id):
        brand = self.get_brand(request, brand_id)
        if not brand:
            return Response(
                {"detail": "Brand not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        voice, _ = BrandVoice.objects.get_or_create(brand=brand)
        return Response(BrandVoiceSerializer(voice).data)

    def put(self, request, brand_id):
        brand = self.get_brand(request, brand_id)
        if not brand:
            return Response(
                {"detail": "Brand not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        voice, _ = BrandVoice.objects.get_or_create(brand=brand)
        serializer = BrandVoiceSerializer(
            voice,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ApprovalListView(generics.ListAPIView):
    serializer_class = ApprovalSerializer
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Approval.objects.filter(
            post__brand__owner_id=self.request.user.id
        ).select_related("post", "post__brand")
        approval_status = self.request.query_params.get("status", "pending")

        if approval_status not in Approval.Status.values:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                {"status": "Choose pending, approved, or rejected."}
            )

        return queryset.filter(status=approval_status)


class ApprovalDetailView(generics.RetrieveAPIView):
    serializer_class = ApprovalSerializer
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        return Approval.objects.filter(
            post__brand__owner_id=self.request.user.id
        ).select_related("post", "post__brand")


class ApprovalActionView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, approval_id, action):
        if action not in ("approve", "reject"):
            return Response(
                {"detail": "Choose approve or reject."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            try:
                approval = (
                    Approval.objects.select_for_update()
                    .select_related("post", "post__brand")
                    .get(
                        id=approval_id,
                        post__brand__owner_id=request.user.id,
                    )
                )
            except Approval.DoesNotExist:
                return Response(
                    {"detail": "Approval not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if (
                approval.status != Approval.Status.PENDING
                or approval.post.status != ContentPost.Status.IN_REVIEW
            ):
                return Response(
                    {"detail": "Only pending content can be reviewed."},
                    status=status.HTTP_409_CONFLICT,
                )

            decision = (
                Approval.Status.APPROVED
                if action == "approve"
                else Approval.Status.REJECTED
            )
            approval.status = decision
            approval.reviewer_id = request.user.id
            approval.reviewed_at = timezone.now()
            approval.save(
                update_fields=[
                    "status",
                    "reviewer_id",
                    "reviewed_at",
                    "updated_at",
                ]
            )

            approval.post.status = (
                ContentPost.Status.APPROVED
                if action == "approve"
                else ContentPost.Status.REJECTED
            )
            approval.post.save(update_fields=["status", "updated_at"])

        return Response(ApprovalSerializer(approval).data)


class ContentGenerateView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ContentGenerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        brand = get_object_or_404(
            Brand,
            id=values["brand_id"],
            owner_id=request.user.id,
        )
        voice = BrandVoice.objects.filter(brand=brand).first()

        try:
            content = generate_content(
                brand=brand,
                voice=voice,
                platform=values["platform"],
                content_type=values["content_type"],
                topic=values["topic"],
                keywords=values.get("keywords", []),
                call_to_action=values.get("call_to_action", ""),
                tone=values.get("tone", ""),
                language=values.get("language", ""),
            )
        except ContentGenerationError as error:
            return Response(
                {"detail": str(error)},
                status=error.status_code,
            )

        return Response(
            {
                "content": content,
                "brand_id": str(brand.id),
                "platform": values["platform"],
                "content_type": values["content_type"],
            },
            status=status.HTTP_200_OK,
        )


class ContentPostListCreateView(generics.ListCreateAPIView):
    serializer_class = ContentPostSerializer
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ContentPost.objects.filter(
            brand__owner_id=self.request.user.id
        ).select_related("brand")

    def perform_create(self, serializer):
        serializer.save(
            status=ContentPost.Status.DRAFT,
            ai_generated=True,
        )


class ContentPostDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ContentPostSerializer
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        return ContentPost.objects.filter(
            brand__owner_id=self.request.user.id
        ).select_related("brand")

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != ContentPost.Status.DRAFT:
            return Response(
                {"detail": "Only draft content can be edited."},
                status=status.HTTP_409_CONFLICT,
            )
        return super().update(request, *args, **kwargs)


class ContentPostSubmitApprovalView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, post_id):
        with transaction.atomic():
            try:
                post = (
                    ContentPost.objects.select_for_update()
                    .select_related("brand")
                    .get(id=post_id, brand__owner_id=request.user.id)
                )
            except ContentPost.DoesNotExist:
                return Response(
                    {"detail": "Content post not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            existing = (
                Approval.objects.filter(
                    post=post,
                    status=Approval.Status.PENDING,
                )
                .select_related("post", "post__brand")
                .first()
            )
            if existing:
                return Response(
                    ApprovalSerializer(existing).data,
                    status=status.HTTP_200_OK,
                )

            if post.status not in (
                ContentPost.Status.DRAFT,
                ContentPost.Status.REJECTED,
            ):
                return Response(
                    {"detail": "Only draft or rejected content can be submitted for review."},
                    status=status.HTTP_409_CONFLICT,
                )

            approval = Approval.objects.create(
                post=post,
                status=Approval.Status.PENDING,
            )
            post.status = ContentPost.Status.IN_REVIEW
            post.save(update_fields=["status", "updated_at"])

        approval = Approval.objects.select_related(
            "post",
            "post__brand",
        ).get(id=approval.id)
        return Response(
            ApprovalSerializer(approval).data,
            status=status.HTTP_201_CREATED,
        )
