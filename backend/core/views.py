from django.http import JsonResponse
from datetime import datetime, timedelta
import hashlib
import hmac
import logging
import uuid

import requests

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncWeek
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
import stripe

from .authentication import SupabaseAuthentication
from .models import (
    Approval,
    Brand,
    BrandVoice,
    ContentPost,
    Notification,
    PaymentTransaction,
    ProviderWebhookEvent,
    ScheduledPost,
    SocialAccount,
    SupportRequest,
    UserSubscription,
)
from .serializers import (
    ApprovalSerializer,
    AnalyticsRangeSerializer,
    AnalyticsResponseSerializer,
    BrandSerializer,
    BrandVoiceSerializer,
    ContentGenerationSerializer,
    ContentPostSerializer,
    NotificationSerializer,
    CheckoutRequestSerializer,
    CheckoutSessionVerificationSerializer,
    SubscriptionCancelRequestSerializer,
    SubscriptionPlanSwitchRequestSerializer,
    SubscriptionPortalRequestSerializer,
    SubscriptionPlansRequestSerializer,
    PaymentTransactionSerializer,
    PaymentWebhookSerializer,
    ScheduledPostCreateSerializer,
    ScheduledPostRangeSerializer,
    ScheduledPostSerializer,
    ScheduledPostUpdateSerializer,
    ConnectedAccountsResponseSerializer,
    SocialAccountSerializer,
    SupportRequestCreateSerializer,
    UserSubscriptionSerializer,
    GEOOptimizationSerializer,
)
from .services.content_generation import (
    ContentGenerationError,
    generate_content,
)
from .services.geo_analysis import analyze_geo_content
from .services.notifications import notify_approval_decision
from .services.subscriptions import (
    get_user_entitlements,
    is_within_entitlement_limit,
)
from .services.payments.catalog import (
    checkout_configuration_present,
    get_plan_for_price,
    get_plan_catalog,
    get_price_id,
)
from .services.payments.checkout import (
    CheckoutUnavailable,
    SubscriptionAlreadyExists,
    start_stripe_checkout,
)
from .services.payments.verification import (
    CheckoutSessionNotFound,
    verify_checkout_session,
)
from .services.payments.portal import (
    PortalUnavailable,
    start_billing_portal,
)
from .services.payments.webhooks import (
    StripeWebhookProcessingError,
    process_stripe_event,
)
from .services.scheduling import (
    SchedulingError,
    cancel_scheduled_post,
    reschedule_scheduled_post,
    schedule_post,
)
from .services.social_platforms import (
    SOCIAL_PROVIDERS,
    get_publishing_capabilities,
)
from .services.payments.stripe_gateway import (
    cancel_subscription as cancel_stripe_subscription,
    retrieve_price_details,
    retrieve_subscription,
    update_subscription as update_stripe_subscription,
)

logger = logging.getLogger(__name__)


def _stripe_value(value, key, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _stripe_identifier(value):
    return value if isinstance(value, str) else _stripe_value(value, "id")


def _stripe_datetime(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(
            value,
            tz=timezone.get_current_timezone(),
        )
    return None


def _stripe_period_end(subscription):
    period_end = _stripe_value(subscription, "current_period_end")
    if period_end:
        return _stripe_datetime(period_end)
    items = _stripe_value(_stripe_value(subscription, "items", {}), "data", [])
    if items:
        return _stripe_datetime(_stripe_value(items[0], "current_period_end"))
    return None


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
        current_brands = Brand.objects.filter(owner_id=self.request.user.id).count()
        if not is_within_entitlement_limit(
            self.request.user.id,
            "saved_brands",
            current_brands,
        ):
            raise PermissionDenied(
                "Your current plan has reached its saved-brand limit."
            )
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
            notify_approval_decision(approval)

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
class GEOOptimizeView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = GEOOptimizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        values = serializer.validated_data

        brand = get_object_or_404(
            Brand,
            id=values["brand_id"],
            owner_id=request.user.id,
        )

        try:
            result = analyze_geo_content(
                content=values["content"],
                platform=values["platform"],
                brand=brand,
            )

        except ContentGenerationError as error:
            return Response(
                {"detail": str(error)},
                status=error.status_code,
            )

        improvements = [
            issue["suggestion"]
            for issue in result["issues"]
            if isinstance(issue, dict)
            and isinstance(issue.get("suggestion"), str)
            and issue["suggestion"].strip()
        ]

        return Response(
            {
                "improvements": improvements,
                "optimized_content": result["optimized_content"],
            },
            status=status.HTTP_200_OK,
        )


class ContentPostListCreateView(generics.ListCreateAPIView):
    serializer_class = ContentPostSerializer
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ContentPost.objects.filter(
            brand__owner_id=self.request.user.id
        ).select_related("brand")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            if status_filter not in ContentPost.Status.values:
                raise ValidationError(
                    {"status": "Unsupported content status."}
                )
            queryset = queryset.filter(status=status_filter)
        return queryset

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


class ScheduledPostListView(generics.ListAPIView):
    serializer_class = ScheduledPostSerializer
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        range_serializer = ScheduledPostRangeSerializer(
            data=self.request.query_params
        )
        range_serializer.is_valid(raise_exception=True)
        values = range_serializer.validated_data

        return (
            ScheduledPost.objects.filter(
                post__brand__owner_id=self.request.user.id,
                scheduled_for__gte=values["start"],
                scheduled_for__lt=values["end"],
            )
            .select_related("post", "post__brand")
            .order_by("scheduled_for")
        )


class ScheduledPostCreateView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ScheduledPostCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            created = schedule_post(
                owner_id=request.user.id,
                post_id=serializer.validated_data["post_id"],
                platforms=serializer.validated_data["platforms"],
                scheduled_for=serializer.validated_data["scheduled_for"],
                timezone_name=serializer.validated_data["timezone_name"],
            )
        except SchedulingError as error:
            logger.warning(
                "Scheduling rejected: code=%s status=%s",
                error.code,
                error.status_code,
            )
            return Response(
                {"code": error.code, "detail": error.message},
                status=error.status_code,
            )

        return Response(
            ScheduledPostSerializer(created, many=True).data,
            status=status.HTTP_201_CREATED,
        )


class ScheduledPostDetailView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        scheduled = get_object_or_404(
            ScheduledPost.objects.select_related("post", "post__brand"),
            id=id,
            post__brand__owner_id=request.user.id,
        )
        return Response(ScheduledPostSerializer(scheduled).data)

    def patch(self, request, id):
        serializer = ScheduledPostUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            scheduled = reschedule_scheduled_post(
                owner_id=request.user.id,
                scheduled_id=id,
                scheduled_for=serializer.validated_data.get("scheduled_for"),
                timezone_name=serializer.validated_data.get("timezone_name"),
            )
        except SchedulingError as error:
            return Response(
                {"code": error.code, "detail": error.message},
                status=error.status_code,
            )

        scheduled = ScheduledPost.objects.select_related(
            "post",
            "post__brand",
        ).get(id=scheduled.id)
        return Response(ScheduledPostSerializer(scheduled).data)

    def delete(self, request, id):
        try:
            scheduled = cancel_scheduled_post(
                owner_id=request.user.id,
                scheduled_id=id,
            )
        except SchedulingError as error:
            return Response(
                {"code": error.code, "detail": error.message},
                status=error.status_code,
            )

        scheduled = ScheduledPost.objects.select_related(
            "post",
            "post__brand",
        ).get(id=scheduled.id)
        return Response(ScheduledPostSerializer(scheduled).data)


class SchedulingPlatformsView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"platforms": get_publishing_capabilities()})


class AnalyticsView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        range_serializer = AnalyticsRangeSerializer(data=request.query_params)
        range_serializer.is_valid(raise_exception=True)
        days = int(range_serializer.validated_data["days"])
        end = timezone.now()
        start = end - timedelta(days=days)

        owned_posts = ContentPost.objects.filter(
            brand__owner_id=request.user.id,
            created_at__gte=start,
            created_at__lt=end,
        )
        post_counts = owned_posts.aggregate(
            content_posts=Count("id"),
            approved_content=Count(
                "id",
                filter=Q(status=ContentPost.Status.APPROVED),
            ),
            rejected_content=Count(
                "id",
                filter=Q(status=ContentPost.Status.REJECTED),
            ),
        )
        summary = {
            **post_counts,
            "pending_approvals": Approval.objects.filter(
                post__brand__owner_id=request.user.id,
                created_at__gte=start,
                created_at__lt=end,
                status=Approval.Status.PENDING,
            ).count(),
            "scheduled_posts": ScheduledPost.objects.filter(
                post__brand__owner_id=request.user.id,
                scheduled_for__gte=start,
                scheduled_for__lt=end,
            ).count(),
        }

        activity_granularity = "day" if days == 7 else "week"
        truncation = TruncDate if activity_granularity == "day" else TruncWeek
        activity_counts = {
            row["bucket"].date().isoformat()
            if hasattr(row["bucket"], "date")
            else row["bucket"].isoformat(): row["content_posts"]
            for row in owned_posts.annotate(
                bucket=truncation("created_at")
            )
            .values("bucket")
            .annotate(content_posts=Count("id"))
        }

        start_date = timezone.localtime(start).date()
        end_date = timezone.localtime(end).date()
        bucket_date = (
            start_date
            if activity_granularity == "day"
            else start_date - timedelta(days=start_date.weekday())
        )
        activity = []
        while bucket_date <= end_date:
            activity.append(
                {
                    "date": bucket_date,
                    "content_posts": activity_counts.get(
                        bucket_date.isoformat(), 0
                    ),
                }
            )
            bucket_date += timedelta(
                days=1 if activity_granularity == "day" else 7
            )

        brands = list(
            owned_posts.values("brand_id", "brand__name")
            .annotate(content_posts=Count("id"))
            .order_by("-content_posts", "brand__name")[:10]
        )
        response_data = {
            "range": {
                "days": days,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
            "summary": summary,
            "activity_granularity": activity_granularity,
            "activity": activity,
            "brands": [
                {
                    "brand_id": brand["brand_id"],
                    "brand_name": brand["brand__name"],
                    "content_posts": brand["content_posts"],
                }
                for brand in brands
            ],
        }
        response_serializer = AnalyticsResponseSerializer(data=response_data)
        response_serializer.is_valid(raise_exception=True)
        return Response(response_serializer.data)


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(
            recipient_user_id=self.request.user.id
        )

    def list(self, request, *args, **kwargs):
        notifications = self.get_queryset()
        unread_count = notifications.filter(read_at__isnull=True).count()
        serializer = self.get_serializer(notifications, many=True)
        return Response(
            {"results": serializer.data, "unread_count": unread_count}
        )


class NotificationUnreadCountView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        unread_count = Notification.objects.filter(
            recipient_user_id=request.user.id,
            read_at__isnull=True,
        ).count()
        return Response({"unread_count": unread_count})


class NotificationMarkReadView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, notification_id):
        notification = get_object_or_404(
            Notification,
            id=notification_id,
            recipient_user_id=request.user.id,
        )
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at", "updated_at"])
        return Response(NotificationSerializer(notification).data)


class NotificationMarkAllReadView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        now = timezone.now()
        updated_count = Notification.objects.filter(
            recipient_user_id=request.user.id,
            read_at__isnull=True,
        ).update(read_at=now, updated_at=now)
        return Response({"updated_count": updated_count, "unread_count": 0})


class SupportRequestCreateView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SupportRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contact_email = (
            serializer.validated_data.get("contact_email", "").strip()
            or (getattr(request.user, "email", "") or "").strip()
        )
        if not contact_email:
            return Response(
                {
                    "contact_email": [
                        "Provide a contact email or add one to your account."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        support_request = serializer.save(
            owner_id=request.user.id,
            contact_email=contact_email,
        )
        return Response(
            {
                "id": str(support_request.id),
                "status": support_request.status,
                "created_at": support_request.created_at,
            },
            status=status.HTTP_201_CREATED,
        )


class SocialAccountListView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        accounts = SocialAccount.objects.filter(owner_id=request.user.id)
        response_data = {
            "providers": [
                {
                    "platform": provider["platform"],
                    "name": provider["name"],
                    "configured": False,
                    "reason": provider["reason"],
                }
                for provider in SOCIAL_PROVIDERS
            ],
            "accounts": SocialAccountSerializer(accounts, many=True).data,
        }
        serializer = ConnectedAccountsResponseSerializer(instance=response_data)
        return Response(serializer.data)


class SocialAccountConnectView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, platform):
        provider = next(
            (item for item in SOCIAL_PROVIDERS if item["platform"] == platform),
            None,
        )
        if provider is None:
            return Response(
                {"detail": "Unsupported social platform."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "detail": provider["reason"],
                "platform": platform,
                "configured": False,
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class SocialOAuthCallbackView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, platform):
        if not any(item["platform"] == platform for item in SOCIAL_PROVIDERS):
            return Response(
                {"detail": "Unsupported social platform."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not request.query_params.get("state"):
            return Response(
                {"detail": "Missing OAuth state."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "detail": (
                    "No OAuth flow is active for this provider. "
                    "The authorization response was not accepted."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class SocialAccountDisconnectView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, account_id):
        account = get_object_or_404(
            SocialAccount,
            id=account_id,
            owner_id=request.user.id,
        )
        account.status = SocialAccount.Status.DISCONNECTED
        account.access_token_encrypted = ""
        account.refresh_token_encrypted = ""
        account.token_expires_at = None
        account.save(
            update_fields=[
                "status",
                "access_token_encrypted",
                "refresh_token_encrypted",
                "token_expires_at",
                "updated_at",
            ]
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubscriptionPlansView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = SubscriptionPlansRequestSerializer(
            data={"platform": request.query_params.get("platform", "web")}
        )
        serializer.is_valid(raise_exception=True)
        catalog = get_plan_catalog(serializer.validated_data["platform"])
        logger.info(
            "Subscription plans API response: status=200 checkout_available=%s",
            catalog["checkout_available"],
        )
        return Response(catalog)


class UserSubscriptionView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        owned_subscriptions = UserSubscription.objects.filter(
            owner_id=request.user.id,
        )
        current_subscription = (
            owned_subscriptions.filter(
                status__in=(
                    UserSubscription.Status.PENDING,
                    UserSubscription.Status.ACTIVE,
                    UserSubscription.Status.PAST_DUE,
                )
            ).first()
            or owned_subscriptions.first()
        )
        transactions = PaymentTransaction.objects.filter(
            subscription__owner_id=request.user.id
        ).select_related("subscription")[:100]
        entitlement = get_user_entitlements(request.user.id)
        manage_available = bool(
            getattr(settings, "STRIPE_SECRET_KEY", "").startswith("sk_test_")
            and current_subscription
            and current_subscription.provider == "stripe"
            and current_subscription.provider_subscription_id
            and current_subscription.status
            in (
                UserSubscription.Status.ACTIVE,
                UserSubscription.Status.PAST_DUE,
            )
        )

        return Response(
            {
                "subscription": (
                    UserSubscriptionSerializer(current_subscription).data
                    if current_subscription
                    else None
                ),
                "plan_id": entitlement["plan_id"],
                "entitlements": entitlement["limits"],
                "transactions": PaymentTransactionSerializer(
                    transactions,
                    many=True,
                ).data,
                "checkout_available": checkout_configuration_present(),
                "checkout_eligible": not bool(
                    current_subscription
                    and current_subscription.status
                    in (
                        UserSubscription.Status.PENDING,
                        UserSubscription.Status.ACTIVE,
                        UserSubscription.Status.PAST_DUE,
                    )
                ),
                "manage_available": manage_available,
            }
        )


class UserDeleteAccountView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    # Local statuses that imply a subscription may still be billable remotely.
    CANCELLATION_STATUSES = (
        UserSubscription.Status.PENDING,
        UserSubscription.Status.ACTIVE,
        UserSubscription.Status.PAST_DUE,
    )

    @classmethod
    def _subscriptions_requiring_cancellation(cls, subscriptions):
        return [
            subscription
            for subscription in subscriptions
            if subscription.provider == "stripe"
            and subscription.provider_subscription_id
            and subscription.status in cls.CANCELLATION_STATUSES
        ]

    @staticmethod
    def _cancel_stripe_subscription(subscription):
        """Cancel through the shared Stripe gateway configuration."""
        cancel_stripe_subscription(subscription.provider_subscription_id)

    def post(self, request):
        # Ownership is derived only from the authenticated Supabase identity.
        user_id = request.user.id

        # Validate required configuration before any destructive operation.
        supabase_url = getattr(settings, "SUPABASE_URL", "").rstrip("/")
        service_role_key = getattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not supabase_url or not service_role_key:
            logger.error(
                "Account deletion is unavailable: Supabase admin configuration is missing."
            )
            return Response(
                {
                    "code": "account_deletion_unavailable",
                    "detail": (
                        "Account deletion is not available right now. "
                        "No data was removed. Please try again later or contact support."
                    ),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        subscriptions = list(
            UserSubscription.objects.filter(owner_id=user_id)
            .order_by("-created_at")
        )
        cancellations = self._subscriptions_requiring_cancellation(subscriptions)
        if cancellations and not getattr(
            settings, "STRIPE_SECRET_KEY", ""
        ).strip():
            logger.error(
                "Account deletion is unavailable: Stripe is not configured "
                "for a subscription owner=%s",
                user_id,
            )
            return Response(
                {
                    "code": "stripe_cancellation_unavailable",
                    "detail": (
                        "Your subscription could not be cancelled, so your "
                        "account was not deleted. No data was removed. Please "
                        "try again later or contact support."
                    ),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        for subscription in cancellations:
            try:
                self._cancel_stripe_subscription(subscription)
            except stripe.StripeError as error:
                logger.error(
                    "Stripe cancellation failed for user account deletion: "
                    "owner=%s subscription=%s error_type=%s",
                    user_id,
                    subscription.provider_subscription_id,
                    type(error).__name__,
                )
                return Response(
                    {
                        "code": "stripe_cancellation_failed",
                        "detail": (
                            "Your subscription could not be cancelled, so your "
                            "account was not deleted. No data was removed. "
                            "Please try again later or contact support."
                        ),
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        try:
            response = requests.delete(
                f"{supabase_url}/auth/v1/admin/users/{user_id}",
                headers={
                    "apikey": service_role_key,
                    "Authorization": f"Bearer {service_role_key}",
                },
                timeout=10,
            )
        except requests.RequestException:
            logger.exception(
                "Supabase user deletion failed for owner=%s",
                user_id,
            )
            return Response(
                {"detail": "Could not delete the authenticated account."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if response.status_code not in (200, 202, 204):
            logger.error(
                "Supabase admin deletion rejected for owner=%s status=%s body=%s",
                user_id,
                response.status_code,
                response.text[:500],
            )
            return Response(
                {"detail": "Could not delete the authenticated account."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        with transaction.atomic():
            Notification.objects.filter(recipient_user_id=user_id).delete()
            Approval.objects.filter(post__brand__owner_id=user_id).delete()
            ScheduledPost.objects.filter(post__brand__owner_id=user_id).delete()
            ContentPost.objects.filter(brand__owner_id=user_id).delete()
            Brand.objects.filter(owner_id=user_id).delete()
            SocialAccount.objects.filter(owner_id=user_id).delete()
            SupportRequest.objects.filter(owner_id=user_id).delete()
            PaymentTransaction.objects.filter(subscription__owner_id=user_id).delete()
            UserSubscription.objects.filter(owner_id=user_id).delete()

        return Response({"deleted": True, "user_id": str(user_id)})


class SubscriptionCancelView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SubscriptionCancelRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancel_at_period_end = serializer.validated_data["cancel_at_period_end"]
        subscription = (
            UserSubscription.objects.filter(
                owner_id=request.user.id,
                provider="stripe",
                status__in=(
                    UserSubscription.Status.ACTIVE,
                    UserSubscription.Status.PAST_DUE,
                ),
            )
            .order_by("-created_at")
            .first()
        )
        if subscription is None:
            return Response(
                {"detail": "No Stripe subscription was found for this account."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if (
            not settings.STRIPE_SECRET_KEY.startswith("sk_test_")
            or not subscription.provider_subscription_id
        ):
            return Response(
                {"detail": "Stripe subscription management is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            remote_subscription = retrieve_subscription(
                subscription.provider_subscription_id
            )
            remote_customer_id = _stripe_identifier(
                _stripe_value(remote_subscription, "customer")
            )
            if (
                remote_customer_id
                and remote_customer_id != subscription.provider_customer_id
            ):
                return Response(
                    {
                        "code": "subscription_customer_mismatch",
                        "detail": "The Stripe subscription does not match this account.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            remote_status = _stripe_value(remote_subscription, "status")
            if remote_status == "canceled":
                updated_subscription = remote_subscription
            elif cancel_at_period_end:
                updated_subscription = update_stripe_subscription(
                    subscription.provider_subscription_id,
                    {"cancel_at_period_end": True},
                )
            else:
                updated_subscription = cancel_stripe_subscription(
                    subscription.provider_subscription_id
                )
        except stripe.StripeError as error:
            logger.error(
                "Stripe cancellation failed: owner=%s error_type=%s",
                request.user.id,
                type(error).__name__,
            )
            return Response(
                {"detail": "Unable to update your subscription with Stripe."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        updated_status = _stripe_value(updated_subscription, "status")
        status_map = {
            "active": UserSubscription.Status.ACTIVE,
            "trialing": UserSubscription.Status.ACTIVE,
            "past_due": UserSubscription.Status.PAST_DUE,
            "canceled": UserSubscription.Status.CANCELED,
            "incomplete": UserSubscription.Status.PENDING,
            "incomplete_expired": UserSubscription.Status.EXPIRED,
            "unpaid": UserSubscription.Status.FAILED,
        }
        subscription.status = status_map.get(updated_status, subscription.status)
        subscription.cancel_at_period_end = bool(
            _stripe_value(
                updated_subscription,
                "cancel_at_period_end",
                cancel_at_period_end,
            )
        )
        period_end = _stripe_period_end(updated_subscription)
        if period_end:
            subscription.current_period_end = period_end
        canceled_at = _stripe_datetime(
            _stripe_value(updated_subscription, "canceled_at")
        )
        if subscription.status == UserSubscription.Status.CANCELED:
            subscription.canceled_at = canceled_at or timezone.now()
        else:
            subscription.canceled_at = None
        subscription.save(
            update_fields=[
                "status",
                "cancel_at_period_end",
                "canceled_at",
                "current_period_end",
                "updated_at",
            ]
        )
        effective_at = (
            subscription.current_period_end
            if subscription.cancel_at_period_end
            else subscription.canceled_at
        )
        return Response(
            {
                "id": str(subscription.id),
                "status": subscription.status,
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "canceled_at": subscription.canceled_at,
                "current_period_end": subscription.current_period_end,
                "effective_at": effective_at,
                "message": (
                    "Your subscription will remain active until the end of the current billing period."
                    if subscription.cancel_at_period_end
                    else "Your subscription has been canceled immediately and access ends now."
                ),
            }
        )


class SubscriptionPortalView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    PORTAL_ERRORS = {
        "not_configured": (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "portal_not_configured",
            "Billing portal is not configured on the backend.",
        ),
        "return_url": (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "portal_not_configured",
            "Billing portal return URL is not configured on the backend.",
        ),
        "no_subscription": (
            status.HTTP_404_NOT_FOUND,
            "portal_subscription_not_found",
            "No Stripe subscription was found for this account.",
        ),
        "customer_missing": (
            status.HTTP_409_CONFLICT,
            "portal_customer_unavailable",
            "This subscription has no Stripe customer record. Contact support.",
        ),
        "session_missing": (
            status.HTTP_502_BAD_GATEWAY,
            "portal_unavailable",
            "Stripe did not return a billing portal link. Please try again.",
        ),
    }

    def post(self, request):
        serializer = SubscriptionPortalRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            portal_url = start_billing_portal(
                owner_id=request.user.id,
                platform=serializer.validated_data["platform"],
            )
        except PortalUnavailable as error:
            status_code, code, detail = self.PORTAL_ERRORS.get(
                error.reason,
                (
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "portal_unavailable",
                    "Billing portal is unavailable right now.",
                ),
            )
            logger.warning(
                "Billing portal rejected: category=%s status=%s",
                error.reason,
                status_code,
            )
            return Response(
                {"code": code, "detail": detail},
                status=status_code,
            )
        except stripe.StripeError as error:
            logger.error(
                "Stripe billing portal failed: category=stripe_api "
                "status=502 error_type=%s",
                type(error).__name__,
            )
            return Response(
                {
                    "code": "portal_unavailable",
                    "detail": (
                        "Unable to open the billing portal right now. "
                        "Please try again later."
                    ),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({"url": portal_url})


class SubscriptionPlanSwitchView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SubscriptionPlanSwitchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan_id = serializer.validated_data["plan_id"]
        billing_interval = serializer.validated_data["billing_interval"]
        price_id = get_price_id(plan_id, billing_interval)
        price_details = (
            retrieve_price_details(price_id)
            if settings.STRIPE_SECRET_KEY.startswith("sk_test_") and price_id
            else None
        )
        expected_interval = "month" if billing_interval == "monthly" else "year"
        if not (
            price_id
            and get_plan_for_price(price_id) == (plan_id, billing_interval)
            and price_details
            and price_details["active"]
            and price_details["recurring_interval"] == expected_interval
            and price_details["recurring_interval_count"] == 1
        ):
            return Response(
                {
                    "detail": (
                        "The selected plan and billing interval are not "
                        "available in the Stripe catalog."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        subscription = (
            UserSubscription.objects.filter(
                owner_id=request.user.id,
                provider="stripe",
                status=UserSubscription.Status.ACTIVE,
                cancel_at_period_end=False,
            )
            .order_by("-created_at")
            .first()
        )
        if subscription is None:
            return Response(
                {"detail": "No Stripe subscription was found for this account."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if (
            not settings.STRIPE_SECRET_KEY.startswith("sk_test_")
            or not subscription.provider_subscription_id
        ):
            return Response(
                {"detail": "Stripe subscription management is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            remote_subscription = retrieve_subscription(
                subscription.provider_subscription_id,
            )
            remote_customer_id = _stripe_identifier(
                _stripe_value(remote_subscription, "customer")
            )
            if (
                remote_customer_id
                and remote_customer_id != subscription.provider_customer_id
            ):
                return Response(
                    {
                        "code": "subscription_customer_mismatch",
                        "detail": "The Stripe subscription does not match this account.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            remote_status = _stripe_value(remote_subscription, "status")
            if (
                remote_status not in ("active", "trialing")
                or _stripe_value(remote_subscription, "cancel_at_period_end", False)
            ):
                return Response(
                    {
                        "code": "subscription_not_switchable",
                        "detail": (
                            "Only an active subscription that is not scheduled "
                            "for cancellation can be changed."
                        ),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            remote_items = _stripe_value(
                _stripe_value(remote_subscription, "items", {}),
                "data",
                [],
            )
            if not remote_items:
                return Response(
                    {
                        "code": "subscription_items_missing",
                        "detail": "Stripe did not return a subscription item to update.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            current_item = remote_items[0]
            current_item_id = _stripe_value(current_item, "id")
            current_price_id = _stripe_identifier(
                _stripe_value(current_item, "price")
            )
            if current_price_id == price_id:
                return Response(
                    {
                        "code": "plan_already_selected",
                        "detail": "This plan and billing interval are already active.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            metadata = _stripe_value(remote_subscription, "metadata", {})
            if hasattr(metadata, "to_dict"):
                metadata = metadata.to_dict()
            else:
                metadata = dict(metadata) if hasattr(metadata, "items") else {}
            metadata.update(
                {
                    "ibda_owner_id": str(request.user.id),
                    "ibda_subscription_id": str(subscription.id),
                    "plan_id": plan_id,
                    "billing_interval": billing_interval,
                }
            )
            updated_subscription = update_stripe_subscription(
                subscription.provider_subscription_id,
                {
                    "items": [{"id": current_item_id, "price": price_id}],
                    "proration_behavior": "create_prorations",
                    "metadata": metadata,
                },
            )
        except stripe.StripeError as error:
            logger.error(
                "Stripe plan change failed: owner=%s error_type=%s",
                request.user.id,
                type(error).__name__,
            )
            return Response(
                {"detail": "Unable to update your plan with Stripe."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        subscription.plan_id = plan_id
        subscription.billing_interval = billing_interval
        period_end = _stripe_period_end(updated_subscription)
        update_fields = ["plan_id", "billing_interval", "updated_at"]
        if period_end:
            subscription.current_period_end = period_end
            update_fields.append("current_period_end")
        subscription.save(update_fields=update_fields)
        return Response(
            {
                "id": str(subscription.id),
                "plan_id": subscription.plan_id,
                "billing_interval": subscription.billing_interval,
                "amount_minor": price_details["price_minor"],
                "currency": price_details["currency"],
                "current_period_end": subscription.current_period_end,
                "proration_disclosure": (
                    "Stripe will calculate prorated charges or credits and "
                    "apply them to the upcoming invoice."
                ),
                "status": subscription.status,
            }
        )


class SubscriptionCheckoutView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        idempotency_key = request.headers.get("Idempotency-Key", "")
        try:
            idempotency_key = str(uuid.UUID(idempotency_key))
        except (ValueError, TypeError, AttributeError):
            return Response(
                {"detail": "A valid Idempotency-Key UUID header is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan_id = serializer.validated_data["plan_id"]
        billing_interval = serializer.validated_data["billing_interval"]
        if not get_price_id(plan_id, billing_interval):
            logger.warning(
                "Stripe checkout rejected: category=price_id_missing "
                "status=503 plan=%s interval=%s",
                plan_id,
                billing_interval,
            )
            return Response(
                {
                    "detail": (
                        "Checkout is unavailable for this plan and billing "
                        "interval because its Stripe Price ID is not configured."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            session = start_stripe_checkout(
                owner_id=request.user.id,
                email=getattr(request.user, "email", None),
                plan_id=plan_id,
                billing_interval=billing_interval,
                idempotency_key=idempotency_key,
                platform=serializer.validated_data["platform"],
            )
        except CheckoutUnavailable as error:
            logger.warning(
                "Stripe checkout rejected: category=%s status=503 "
                "owner=%s plan=%s interval=%s",
                error.reason,
                request.user.id,
                plan_id,
                billing_interval,
            )
            return Response(
                {"detail": "Stripe checkout is not fully configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except SubscriptionAlreadyExists as error:
            logger.warning(
                "Stripe checkout rejected: category=subscription_conflict "
                "reason=%s status=409 owner=%s plan=%s interval=%s",
                error.reason,
                request.user.id,
                plan_id,
                billing_interval,
            )
            reason_messages = {
                "active_subscription": (
                    "You already have an active subscription. Manage or switch "
                    "your plan from Billing instead of starting another checkout."
                ),
                "payment_past_due": (
                    "Your existing subscription has a payment issue. Update its "
                    "payment method before starting another subscription."
                ),
                "pending_checkout": (
                    "A checkout for a different plan is still pending. Complete "
                    "or let that checkout expire before starting another."
                ),
                "subscription_incomplete": (
                    "Stripe has an incomplete subscription for this account. "
                    "Complete or resolve that payment before retrying."
                ),
                "checkout_processing": (
                    "This checkout has completed and is awaiting webhook "
                    "confirmation. Refresh Billing or verify the checkout session."
                ),
                "checkout_session_unavailable": (
                    "An existing checkout session could not be safely resumed. "
                    "Refresh Billing or contact support."
                ),
                "checkout_session_mismatch": (
                    "The stored checkout session does not match this account. "
                    "Contact support before retrying."
                ),
                "stripe_customer_mismatch": (
                    "The Stripe customer record does not match this account. "
                    "Contact support before retrying."
                ),
                "subscription_unavailable": (
                    "The existing Stripe subscription cannot be safely resumed. "
                    "Refresh Billing or contact support."
                ),
            }
            response_data = {
                "code": "subscription_conflict",
                "reason": error.reason,
                "detail": reason_messages.get(
                    error.reason,
                    "An existing subscription prevents a duplicate checkout.",
                ),
            }
            if error.subscription is not None:
                response_data["current_subscription"] = (
                    UserSubscriptionSerializer(error.subscription).data
                )
            if error.checkout_session_id:
                response_data["checkout_session_id"] = (
                    error.checkout_session_id
                )
            return Response(response_data, status=status.HTTP_409_CONFLICT)
        except stripe.StripeError as error:
            logger.error(
                "Stripe checkout failed: category=stripe_api "
                "status=502 owner=%s error_type=%s",
                request.user.id,
                type(error).__name__,
            )
            return Response(
                {"detail": "Unable to start checkout. Please try again later."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        logger.info(
            "Stripe checkout created: status=200 plan=%s interval=%s",
            plan_id,
            billing_interval,
        )
        return Response(
            {
                "checkout_url": session.url,
                "session_id": session.id,
            }
        )


class CheckoutSessionVerificationView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not settings.STRIPE_SECRET_KEY.startswith("sk_test_"):
            return Response(
                {"detail": "Stripe session verification is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = CheckoutSessionVerificationSerializer(
            data={"session_id": request.query_params.get("session_id", "")}
        )
        serializer.is_valid(raise_exception=True)
        try:
            result = verify_checkout_session(
                owner_id=request.user.id,
                session_id=serializer.validated_data["session_id"],
            )
        except CheckoutSessionNotFound:
            return Response(
                {"detail": "Checkout session could not be verified."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except stripe.InvalidRequestError:
            return Response(
                {"detail": "Checkout session could not be verified."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except stripe.StripeError as error:
            logger.error(
                "Stripe checkout verification failed: category=stripe_api "
                "error_type=%s",
                type(error).__name__,
            )
            return Response(
                {"detail": "Unable to verify checkout right now."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(result, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        if (
            not settings.STRIPE_SECRET_KEY.startswith("sk_test_")
            or not settings.STRIPE_WEBHOOK_SECRET
        ):
            return Response(
                {"detail": "Stripe webhook processing is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        signature = request.headers.get("Stripe-Signature", "")
        try:
            result = process_stripe_event(request.body, signature)
        except stripe.SignatureVerificationError:
            return Response(
                {"detail": "Invalid Stripe webhook signature."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError:
            return Response(
                {"detail": "Malformed Stripe webhook payload."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except StripeWebhookProcessingError as error:
            logger.warning(
                "Stripe webhook event could not be processed: %s",
                error,
            )
            return Response(
                {"detail": str(error)},
                status=error.status_code,
            )

        return Response(result, status=status.HTTP_200_OK)


class PaymentWebhookView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        secret = settings.PAYMENT_WEBHOOK_SECRET
        if not secret:
            return Response(
                {"detail": "Payment webhook processing is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        supplied_signature = request.headers.get("X-Ibda-Signature", "")
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            request.body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return Response(
                {"detail": "Invalid webhook signature."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PaymentWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = serializer.validated_data
        provider = settings.PAYMENT_PROVIDER
        if not provider:
            return Response(
                {"detail": "Payment webhook processing is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        with transaction.atomic():
            if ProviderWebhookEvent.objects.filter(
                provider=provider,
                event_id=event["event_id"],
            ).exists():
                return Response({"received": True, "duplicate": True})

            subscription = (
                UserSubscription.objects.select_for_update()
                .filter(
                    provider=provider,
                    provider_subscription_id=event["subscription_id"],
                )
                .first()
            )
            if subscription is None:
                return Response(
                    {"detail": "Subscription not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if event["event_type"] == "transaction.updated":
                existing_transaction = PaymentTransaction.objects.filter(
                    provider=provider,
                    provider_transaction_id=event["transaction_id"],
                ).first()
                if (
                    existing_transaction
                    and existing_transaction.subscription_id != subscription.id
                ):
                    return Response(
                        {"detail": "Transaction does not match the subscription."},
                        status=status.HTTP_409_CONFLICT,
                    )

            webhook_event, created = ProviderWebhookEvent.objects.get_or_create(
                provider=provider,
                event_id=event["event_id"],
                defaults={"event_type": event["event_type"]},
            )
            if not created:
                return Response({"received": True, "duplicate": True})

            if event["event_type"] == "subscription.updated":
                subscription.status = event["status"]
                for field in (
                    "plan_id",
                    "billing_interval",
                    "current_period_start",
                    "current_period_end",
                    "cancel_at_period_end",
                    "canceled_at",
                ):
                    if field in event:
                        setattr(subscription, field, event[field])
                subscription.save()
            else:
                defaults = {
                    "subscription": subscription,
                    "status": event["status"],
                }
                for field in ("amount_minor", "currency", "occurred_at"):
                    if field in event:
                        defaults[field] = event[field]
                PaymentTransaction.objects.update_or_create(
                    provider=provider,
                    provider_transaction_id=event["transaction_id"],
                    defaults=defaults,
                )
        return Response({"received": True, "duplicate": False})
