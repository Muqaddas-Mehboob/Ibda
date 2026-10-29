from django.http import JsonResponse
from datetime import timedelta
import hashlib
import hmac

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncWeek
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

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
    PaymentTransactionSerializer,
    PaymentWebhookSerializer,
    ScheduledPostRangeSerializer,
    ScheduledPostSerializer,
    ConnectedAccountsResponseSerializer,
    SocialAccountSerializer,
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


SOCIAL_PROVIDERS = (
    {
        "platform": SocialAccount.Platform.INSTAGRAM,
        "name": "Instagram",
        "reason": "Instagram OAuth is not configured for this deployment.",
    },
    {
        "platform": SocialAccount.Platform.FACEBOOK_PAGES,
        "name": "Facebook Pages",
        "reason": "Facebook OAuth is not configured for this deployment.",
    },
    {
        "platform": SocialAccount.Platform.LINKEDIN,
        "name": "LinkedIn",
        "reason": "LinkedIn OAuth is not configured for this deployment.",
    },
    {
        "platform": SocialAccount.Platform.TIKTOK,
        "name": "TikTok",
        "reason": "TikTok OAuth is not configured for this deployment.",
    },
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
        return Response(
            {
                "plans": [
                    {
                        "id": "free",
                        "name": "Free",
                        "price_minor": None,
                        "currency": None,
                        "billing_intervals": [],
                        "checkout_available": False,
                    },
                    {
                        "id": "premium",
                        "name": "Premium",
                        "price_minor": None,
                        "currency": None,
                        "billing_intervals": [],
                        "checkout_available": False,
                    },
                ],
                "provider_configured": False,
                "message": (
                    "Checkout is unavailable until a billing provider, "
                    "merchant configuration, and verified mobile billing flow "
                    "are implemented."
                ),
            }
        )


class UserSubscriptionView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        current_subscription = (
            UserSubscription.objects.filter(
                owner_id=request.user.id,
                status__in=(
                    UserSubscription.Status.PENDING,
                    UserSubscription.Status.ACTIVE,
                    UserSubscription.Status.PAST_DUE,
                ),
            )
            .filter(
                Q(current_period_end__isnull=True)
                | Q(current_period_end__gt=timezone.now())
            )
            .order_by("-created_at")
            .first()
        )
        transactions = PaymentTransaction.objects.filter(
            subscription__owner_id=request.user.id
        ).select_related("subscription")[:100]
        entitlement = get_user_entitlements(request.user.id)

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
                "checkout_available": False,
                "manage_available": False,
            }
        )


class SubscriptionCheckoutView(APIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {
                "detail": (
                    "Checkout is not configured. No payment was started and "
                    "your subscription was not changed."
                )
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


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
