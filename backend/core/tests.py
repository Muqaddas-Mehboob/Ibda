from types import SimpleNamespace
from datetime import datetime, timedelta, timezone as datetime_timezone
import hashlib
import hmac
import json
import time
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4
from urllib.error import HTTPError

import requests
import stripe
from django.test import override_settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import status
from rest_framework.test import APIRequestFactory, APITestCase
from cryptography.fernet import Fernet

from .authentication import SupabaseAuthentication
from .models import (
    Approval,
    Brand,
    BrandVoice,
    ContentPost,
    Notification,
    PaymentTransaction,
    UserSubscription,
    ProviderWebhookEvent,
    ScheduledPost,
    SocialAccount,
)


class SupabaseAuthenticationTests(APITestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.authentication = SupabaseAuthentication()
        self.token = "supabase-access-token"
        self.user_id = str(uuid4())

    @override_settings(
        SUPABASE_URL="https://supabase.example.invalid",
        SUPABASE_PUBLISHABLE_KEY="publishable-test-key",
    )
    @patch("core.authentication.requests.get")
    def test_valid_token_is_forwarded_and_creates_supabase_user(
        self, mock_get
    ):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "id": self.user_id,
            "email": "creator@example.invalid",
        }
        request = self.factory.get(
            "/api/subscription/me/",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        user, auth_token = self.authentication.authenticate(request)

        self.assertEqual(user.id, self.user_id)
        self.assertEqual(user.email, "creator@example.invalid")
        self.assertTrue(user.is_authenticated)
        self.assertEqual(auth_token, self.token)
        self.assertEqual(
            mock_get.call_args.kwargs["headers"],
            {
                "apikey": "publishable-test-key",
                "Authorization": f"Bearer {self.token}",
            },
        )
        self.assertEqual(mock_get.call_args.kwargs["timeout"], 10)

    @patch("core.authentication.requests.get")
    def test_missing_bearer_token_does_not_authenticate(self, mock_get):
        request = self.factory.get("/api/subscription/me/")

        self.assertIsNone(self.authentication.authenticate(request))
        mock_get.assert_not_called()

    @patch("core.authentication.requests.get")
    def test_malformed_bearer_header_is_rejected(self, mock_get):
        request = self.factory.get(
            "/api/subscription/me/",
            HTTP_AUTHORIZATION="Basic invalid",
        )

        with self.assertRaises(AuthenticationFailed):
            self.authentication.authenticate(request)
        mock_get.assert_not_called()

    @override_settings(
        SUPABASE_URL="https://supabase.example.invalid",
        SUPABASE_PUBLISHABLE_KEY="publishable-test-key",
    )
    @patch("core.authentication.requests.get")
    def test_invalid_and_expired_tokens_are_rejected(self, mock_get):
        request = self.factory.get(
            "/api/subscription/me/",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        for response_status in (401, 403):
            with self.subTest(response_status=response_status):
                mock_get.return_value.status_code = response_status
                with self.assertRaises(AuthenticationFailed):
                    self.authentication.authenticate(request)

    @override_settings(
        SUPABASE_URL="https://supabase.example.invalid",
        SUPABASE_PUBLISHABLE_KEY="publishable-test-key",
    )
    @patch("core.authentication.requests.get")
    def test_upstream_http_and_network_failures_fail_closed(self, mock_get):
        request = self.factory.get(
            "/api/subscription/me/",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        mock_get.return_value.status_code = 503
        with self.assertRaises(AuthenticationFailed):
            self.authentication.authenticate(request)

        mock_get.side_effect = requests.ConnectionError("unavailable")
        with self.assertRaises(AuthenticationFailed):
            self.authentication.authenticate(request)

    @override_settings(
        SUPABASE_URL="https://supabase.example.invalid",
        SUPABASE_PUBLISHABLE_KEY="publishable-test-key",
    )
    @patch("core.authentication.requests.get")
    def test_malformed_supabase_user_response_is_rejected(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"id": "not-a-uuid"}
        request = self.factory.get(
            "/api/subscription/me/",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        with self.assertRaises(AuthenticationFailed):
            self.authentication.authenticate(request)


class BrandVoiceApiTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.other_user_id = uuid4()
        self.client.force_authenticate(user=self.user)

    def test_brand_list_includes_voice_and_only_returns_owned_brands(self):
        brand = Brand.objects.create(
            owner_id=self.user.id,
            name="My brand",
            industry="Education",
        )
        BrandVoice.objects.create(
            brand=brand,
            tone="Playful",
            target_audience="Students",
            language="English",
        )
        Brand.objects.create(owner_id=self.other_user_id, name="Other brand")

        response = self.client.get("/api/brands/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], str(brand.id))
        self.assertEqual(response.data[0]["voice"]["tone"], "Playful")
        self.assertEqual(
            response.data[0]["voice"]["target_audience"],
            "Students",
        )

    def test_brand_creation_assigns_authenticated_owner(self):
        response = self.client.post(
            "/api/brands/",
            {
                "name": "New brand",
                "industry": "",
                "description": "",
                "website": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        brand = Brand.objects.get(id=response.data["id"])
        self.assertEqual(brand.owner_id, self.user.id)
        self.assertIsNone(response.data["voice"])

    def test_voice_api_does_not_allow_access_to_another_users_brand(self):
        brand = Brand.objects.create(
            owner_id=self.other_user_id,
            name="Private brand",
        )

        response = self.client.put(
            f"/api/brands/{brand.id}/voice/",
            {"tone": "Bold"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(BrandVoice.objects.filter(brand=brand).exists())


class ApprovalApiTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.other_user_id = uuid4()
        self.client.force_authenticate(user=self.user)

    def create_approval(self, owner_id=None, status_value=Approval.Status.PENDING):
        brand = Brand.objects.create(
            owner_id=owner_id or self.user.id,
            name="Approval test brand",
        )
        post = ContentPost.objects.create(
            brand=brand,
            title="Review this post",
            body="A complete social post for review.",
            platform=ContentPost.Platform.INSTAGRAM,
            status=ContentPost.Status.IN_REVIEW,
        )
        approval = Approval.objects.create(post=post, status=status_value)
        return approval

    def test_list_filters_by_status_and_only_includes_owned_approvals(self):
        pending = self.create_approval()
        approved = self.create_approval(status_value=Approval.Status.APPROVED)
        self.create_approval(owner_id=self.other_user_id)

        response = self.client.get("/api/approvals/?status=pending")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [str(pending.id)])

        response = self.client.get("/api/approvals/?status=approved")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [str(approved.id)])

    def test_invalid_status_filter_returns_bad_request(self):
        response = self.client.get("/api/approvals/?status=published")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_detail_hides_another_users_approval(self):
        approval = self.create_approval(owner_id=self.other_user_id)

        response = self.client.get(f"/api/approvals/{approval.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_approve_updates_approval_and_post_without_publishing(self):
        approval = self.create_approval()

        response = self.client.post(
            f"/api/approvals/{approval.id}/approve/",
            {},
            format="json",
        )

        approval.refresh_from_db()
        approval.post.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(approval.status, Approval.Status.APPROVED)
        self.assertEqual(approval.reviewer_id, self.user.id)
        self.assertIsNotNone(approval.reviewed_at)
        self.assertEqual(approval.post.status, ContentPost.Status.APPROVED)
        self.assertFalse(approval.post.scheduled_posts.exists())
        notification = Notification.objects.get(
            recipient_user_id=self.user.id,
            related_object_id=approval.id,
        )
        self.assertEqual(
            notification.notification_type,
            Notification.Type.APPROVAL_APPROVED,
        )
        self.assertEqual(notification.destination, Notification.Destination.APPROVAL)

    def test_reject_updates_status_and_cannot_be_repeated(self):
        approval = self.create_approval()

        response = self.client.post(
            f"/api/approvals/{approval.id}/reject/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        approval.refresh_from_db()
        approval.post.refresh_from_db()
        self.assertEqual(approval.status, Approval.Status.REJECTED)
        self.assertEqual(approval.post.status, ContentPost.Status.REJECTED)
        self.assertIsNotNone(approval.reviewed_at)

        response = self.client.post(
            f"/api/approvals/{approval.id}/approve/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        approval.refresh_from_db()
        self.assertEqual(approval.status, Approval.Status.REJECTED)
        self.assertEqual(
            Notification.objects.filter(
                recipient_user_id=self.user.id,
                related_object_id=approval.id,
            ).count(),
            1,
        )

    def test_action_cannot_review_another_users_approval(self):
        approval = self.create_approval(owner_id=self.other_user_id)

        response = self.client.post(
            f"/api/approvals/{approval.id}/approve/",
            {},
            format="json",
        )

        approval.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(approval.status, Approval.Status.PENDING)
        self.assertIsNone(approval.reviewer_id)


class ContentStudioApiTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.other_user_id = uuid4()
        self.client.force_authenticate(user=self.user)
        self.brand = Brand.objects.create(
            owner_id=self.user.id,
            name="Studio brand",
            description="Thoughtful learning tools.",
            industry="Education",
        )
        BrandVoice.objects.create(
            brand=self.brand,
            tone="Warm",
            target_audience="Independent learners",
            language="English",
            writing_guidelines="Use plain language.",
        )

    @override_settings(AI_API_KEY="", AI_MODEL="")
    def test_generation_requires_provider_configuration(self):
        response = self.client.post(
            "/api/content/generate/",
            {
                "brand_id": str(self.brand.id),
                "platform": "instagram",
                "content_type": "educational",
                "topic": "Building a daily learning habit",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertIn("AI_API_KEY", response.data["detail"])

    def test_generation_rejects_invalid_platform(self):
        response = self.client.post(
            "/api/content/generate/",
            {
                "brand_id": str(self.brand.id),
                "platform": "unsupported",
                "content_type": "caption",
                "topic": "A topic",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("platform", response.data)

    def test_generation_hides_brands_owned_by_another_user(self):
        foreign_brand = Brand.objects.create(
            owner_id=self.other_user_id,
            name="Foreign brand",
        )

        response = self.client.post(
            "/api/content/generate/",
            {
                "brand_id": str(foreign_brand.id),
                "platform": "instagram",
                "content_type": "caption",
                "topic": "A topic",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(AI_API_KEY="configured", AI_MODEL="configured-model")
    @patch(
        "core.services.content_generation.urlopen",
        side_effect=TimeoutError(),
    )
    def test_generation_reports_provider_timeout(self, _urlopen):
        response = self.client.post(
            "/api/content/generate/",
            {
                "brand_id": str(self.brand.id),
                "platform": "instagram",
                "content_type": "caption",
                "topic": "A topic",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_504_GATEWAY_TIMEOUT)
        self.assertIn("timed out", response.data["detail"])

    @override_settings(AI_API_KEY="configured", AI_MODEL="configured-model")
    @patch(
        "core.services.content_generation.urlopen",
        side_effect=HTTPError(
            "https://provider.invalid",
            429,
            "Rate limited",
            None,
            BytesIO(b""),
        ),
    )
    def test_generation_reports_provider_rate_limit(self, _urlopen):
        response = self.client.post(
            "/api/content/generate/",
            {
                "brand_id": str(self.brand.id),
                "platform": "instagram",
                "content_type": "caption",
                "topic": "A topic",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("rate limiting", response.data["detail"])

    def test_save_edit_and_submit_content_for_approval(self):
        response = self.client.post(
            "/api/content/posts/",
            {
                "brand_id": str(self.brand.id),
                "title": "Educational post",
                "body": "First draft",
                "platform": "instagram",
                "content_type": "educational",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        post_id = response.data["id"]
        post = ContentPost.objects.get(id=post_id)
        self.assertEqual(post.brand_id, self.brand.id)
        self.assertTrue(post.ai_generated)
        self.assertEqual(post.status, ContentPost.Status.DRAFT)

        response = self.client.patch(
            f"/api/content/posts/{post_id}/",
            {"body": "Edited final draft"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        post.refresh_from_db()
        self.assertEqual(post.body, "Edited final draft")

        response = self.client.post(
            f"/api/content/posts/{post_id}/submit-for-approval/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Approval.Status.PENDING)
        post.refresh_from_db()
        self.assertEqual(post.status, ContentPost.Status.IN_REVIEW)
        self.assertEqual(Approval.objects.filter(post=post).count(), 1)

        response = self.client.post(
            f"/api/content/posts/{post_id}/submit-for-approval/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Approval.objects.filter(post=post).count(), 1)

    def test_cannot_save_content_to_another_users_brand(self):
        foreign_brand = Brand.objects.create(
            owner_id=self.other_user_id,
            name="Other user's brand",
        )

        response = self.client.post(
            "/api/content/posts/",
            {
                "brand_id": str(foreign_brand.id),
                "title": "Post",
                "body": "Content",
                "platform": "instagram",
                "content_type": "caption",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("brand_id", response.data)

    def test_cannot_read_edit_or_submit_another_users_post(self):
        foreign_brand = Brand.objects.create(
            owner_id=self.other_user_id,
            name="Private brand",
        )
        post = ContentPost.objects.create(
            brand=foreign_brand,
            title="Private post",
            body="Private content",
            status=ContentPost.Status.DRAFT,
        )

        response = self.client.get(f"/api/content/posts/{post.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.patch(
            f"/api/content/posts/{post.id}/",
            {"body": "Modified"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.post(
            f"/api/content/posts/{post.id}/submit-for-approval/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(Approval.objects.filter(post=post).exists())


class ScheduledPostApiTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.other_user_id = uuid4()
        self.client.force_authenticate(user=self.user)

    def create_scheduled_post(self, owner_id, scheduled_for, title):
        brand = Brand.objects.create(owner_id=owner_id, name=f"{title} brand")
        post = ContentPost.objects.create(
            brand=brand,
            title=title,
            body=f"{title} body",
            platform=ContentPost.Platform.INSTAGRAM,
        )
        return ScheduledPost.objects.create(
            post=post,
            scheduled_for=scheduled_for,
            platform=ContentPost.Platform.INSTAGRAM,
        )

    def test_list_filters_by_range_and_only_includes_owned_posts_in_order(self):
        first = self.create_scheduled_post(
            self.user.id,
            datetime(2030, 1, 15, 0, tzinfo=datetime_timezone.utc),
            "First",
        )
        second = self.create_scheduled_post(
            self.user.id,
            datetime(2030, 1, 20, 12, tzinfo=datetime_timezone.utc),
            "Second",
        )
        self.create_scheduled_post(
            self.user.id,
            datetime(2030, 2, 1, 0, tzinfo=datetime_timezone.utc),
            "Outside range",
        )
        self.create_scheduled_post(
            self.other_user_id,
            datetime(2030, 1, 17, 12, tzinfo=datetime_timezone.utc),
            "Other user",
        )

        response = self.client.get(
            "/api/calendar/scheduled-posts/"
            "?start=2030-01-15T00:00:00Z&end=2030-02-01T00:00:00Z"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in response.data],
            [str(first.id), str(second.id)],
        )
        self.assertEqual(response.data[0]["post"]["title"], "First")
        self.assertEqual(response.data[0]["post"]["brand_name"], "First brand")

    def test_list_requires_valid_start_and_end_range(self):
        response = self.client.get(
            "/api/calendar/scheduled-posts/?start=2030-02-01T00:00:00Z"
            "&end=2030-01-01T00:00:00Z"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("end", response.data)

    def test_schedule_creation_and_date_change_create_deduplicated_notifications(self):
        scheduled_for = datetime(2030, 1, 15, 12, tzinfo=datetime_timezone.utc)
        scheduled = self.create_scheduled_post(
            self.user.id,
            scheduled_for,
            "Scheduled content",
        )

        notifications = Notification.objects.filter(
            recipient_user_id=self.user.id,
            related_object_id=scheduled.id,
        )
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(
            notifications.first().notification_type,
            Notification.Type.SCHEDULED_POST_CREATED,
        )
        self.assertEqual(
            notifications.first().destination,
            Notification.Destination.CALENDAR,
        )

        scheduled.scheduled_for += timedelta(days=1)
        scheduled.save(update_fields=["scheduled_for"])
        self.assertEqual(notifications.count(), 2)
        self.assertEqual(
            set(notifications.values_list("notification_type", flat=True)),
            {
                Notification.Type.SCHEDULED_POST_CREATED,
                Notification.Type.SCHEDULED_POST_UPDATED,
            },
        )

        scheduled.status = ScheduledPost.Status.PUBLISHED
        scheduled.save(update_fields=["status"])
        self.assertEqual(notifications.count(), 2)


class AnalyticsApiTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.other_user_id = uuid4()
        self.client.force_authenticate(user=self.user)

    def create_post(self, brand, title, status_value, created_at):
        post = ContentPost.objects.create(
            brand=brand,
            title=title,
            body=f"{title} body",
            platform=ContentPost.Platform.INSTAGRAM,
            status=status_value,
        )
        ContentPost.objects.filter(id=post.id).update(created_at=created_at)
        return post

    @patch("core.views.timezone.now")
    def test_analytics_aggregates_owned_records_within_selected_period(self, mock_now):
        now = datetime(2030, 3, 31, 12, tzinfo=datetime_timezone.utc)
        mock_now.return_value = now
        brand = Brand.objects.create(owner_id=self.user.id, name="My brand")
        approved = self.create_post(
            brand,
            "Approved",
            ContentPost.Status.APPROVED,
            now - timedelta(days=2),
        )
        self.create_post(
            brand,
            "Rejected",
            ContentPost.Status.REJECTED,
            now - timedelta(days=3),
        )
        pending = self.create_post(
            brand,
            "Pending",
            ContentPost.Status.IN_REVIEW,
            now - timedelta(days=4),
        )
        start_boundary_post = self.create_post(
            brand,
            "At range start",
            ContentPost.Status.DRAFT,
            now - timedelta(days=7),
        )
        Approval.objects.create(post=pending, status=Approval.Status.PENDING)
        Approval.objects.filter(post=pending).update(
            created_at=now - timedelta(days=4)
        )
        old_post = self.create_post(
            brand,
            "Old post",
            ContentPost.Status.APPROVED,
            now - timedelta(days=20),
        )
        foreign_post = self.create_post(
            Brand.objects.create(owner_id=self.other_user_id, name="Other"),
            "Private post",
            ContentPost.Status.APPROVED,
            now - timedelta(days=1),
        )
        foreign_approval = Approval.objects.create(
            post=foreign_post,
            status=Approval.Status.PENDING,
        )
        Approval.objects.filter(id=foreign_approval.id).update(
            created_at=now - timedelta(days=1)
        )
        ScheduledPost.objects.create(
            post=approved,
            scheduled_for=now - timedelta(days=1),
            platform=ContentPost.Platform.INSTAGRAM,
        )
        ScheduledPost.objects.create(
            post=start_boundary_post,
            scheduled_for=now - timedelta(days=7),
            platform=ContentPost.Platform.INSTAGRAM,
        )
        ScheduledPost.objects.create(
            post=old_post,
            scheduled_for=now - timedelta(days=20),
            platform=ContentPost.Platform.INSTAGRAM,
        )
        ScheduledPost.objects.create(
            post=approved,
            scheduled_for=now,
            platform=ContentPost.Platform.INSTAGRAM,
        )
        ScheduledPost.objects.create(
            post=foreign_post,
            scheduled_for=now - timedelta(days=1),
            platform=ContentPost.Platform.INSTAGRAM,
        )

        response = self.client.get("/api/analytics/?days=7")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["range"]["days"], 7)
        self.assertEqual(
            response.data["summary"],
            {
                "content_posts": 4,
                "pending_approvals": 1,
                "approved_content": 1,
                "rejected_content": 1,
                "scheduled_posts": 2,
            },
        )
        self.assertEqual(response.data["activity_granularity"], "day")
        self.assertEqual(
            sum(item["content_posts"] for item in response.data["activity"]),
            4,
        )
        self.assertEqual(
            response.data["brands"],
            [
                {
                    "brand_id": str(brand.id),
                    "brand_name": "My brand",
                    "content_posts": 4,
                }
            ],
        )

    def test_analytics_returns_zeroes_for_empty_period_and_validates_days(self):
        response = self.client.get("/api/analytics/?days=30")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["summary"],
            {
                "content_posts": 0,
                "pending_approvals": 0,
                "approved_content": 0,
                "rejected_content": 0,
                "scheduled_posts": 0,
            },
        )
        self.assertEqual(response.data["brands"], [])
        self.assertEqual(response.data["activity_granularity"], "week")
        self.assertTrue(
            all(item["content_posts"] == 0 for item in response.data["activity"])
        )

        long_range = self.client.get("/api/analytics/?days=90")
        self.assertEqual(long_range.status_code, status.HTTP_200_OK)
        self.assertEqual(long_range.data["range"]["days"], 90)
        self.assertEqual(long_range.data["activity_granularity"], "week")

        invalid = self.client.get("/api/analytics/?days=14")
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("days", invalid.data)


class NotificationApiTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.other_user_id = uuid4()
        self.client.force_authenticate(user=self.user)

    def create_notification(self, recipient, event_key, read_at=None):
        return Notification.objects.create(
            recipient_user_id=recipient,
            notification_type=Notification.Type.APPROVAL_APPROVED,
            title="Content approved",
            message="A post was approved.",
            related_object_id=uuid4(),
            destination=Notification.Destination.APPROVAL,
            event_key=event_key,
            read_at=read_at,
        )

    def test_list_and_unread_count_are_scoped_to_authenticated_user(self):
        unread = self.create_notification(self.user.id, "current-unread")
        read = self.create_notification(
            self.user.id,
            "current-read",
            read_at=datetime.now(datetime_timezone.utc),
        )
        self.create_notification(self.other_user_id, "other-unread")

        response = self.client.get("/api/notifications/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unread_count"], 1)
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(read.id), str(unread.id)],
        )
        self.assertTrue(response.data["results"][0]["is_read"])
        self.assertFalse(response.data["results"][1]["is_read"])

        response = self.client.get("/api/notifications/unread-count/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"unread_count": 1})

    def test_mark_read_and_mark_all_only_update_owned_notifications(self):
        unread = self.create_notification(self.user.id, "current-unread")
        foreign = self.create_notification(self.other_user_id, "other-unread")

        response = self.client.patch(
            f"/api/notifications/{unread.id}/read/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_read"])
        self.assertIsNotNone(response.data["read_at"])

        response = self.client.patch(
            f"/api/notifications/{foreign.id}/read/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        own_unread = self.create_notification(self.user.id, "current-second")
        response = self.client.post(
            "/api/notifications/read-all/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"updated_count": 1, "unread_count": 0})
        own_unread.refresh_from_db()
        foreign.refresh_from_db()
        self.assertIsNotNone(own_unread.read_at)
        self.assertIsNone(foreign.read_at)

    def test_notification_endpoints_require_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/notifications/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class SocialAccountApiTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.other_user_id = uuid4()
        self.client.force_authenticate(user=self.user)

    def create_account(self, owner_id, platform_id):
        return SocialAccount.objects.create(
            owner_id=owner_id,
            platform=SocialAccount.Platform.LINKEDIN,
            platform_account_id=platform_id,
            display_name="Ibda Page",
            access_token_encrypted="encrypted-access-token",
            refresh_token_encrypted="encrypted-refresh-token",
        )

    def test_account_list_reports_unconfigured_platforms_and_hides_tokens(self):
        account = self.create_account(self.user.id, "own-page")
        self.create_account(self.other_user_id, "private-page")

        response = self.client.get("/api/social/accounts/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {provider["platform"] for provider in response.data["providers"]},
            {
                SocialAccount.Platform.INSTAGRAM,
                SocialAccount.Platform.FACEBOOK_PAGES,
                SocialAccount.Platform.LINKEDIN,
                SocialAccount.Platform.TIKTOK,
            },
        )
        self.assertTrue(
            all(not provider["configured"] for provider in response.data["providers"])
        )
        self.assertEqual(
            [item["id"] for item in response.data["accounts"]],
            [str(account.id)],
        )
        self.assertNotIn("access_token_encrypted", response.data["accounts"][0])
        self.assertNotIn("refresh_token_encrypted", response.data["accounts"][0])

    def test_connect_requires_auth_and_does_not_claim_unconfigured_success(self):
        response = self.client.post(
            "/api/social/accounts/instagram/connect/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(response.data["configured"])
        self.assertFalse(SocialAccount.objects.exists())

        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/social/accounts/instagram/connect/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_callback_rejects_missing_or_unrecognized_oauth_state(self):
        missing_state = self.client.get(
            "/api/social/oauth/instagram/callback/?code=untrusted-code"
        )
        self.assertEqual(
            missing_state.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        invalid_state = self.client.get(
            "/api/social/oauth/instagram/callback/"
            "?state=unrecognized&code=untrusted-code"
        )
        self.assertEqual(invalid_state.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("untrusted-code", str(invalid_state.data))
        self.assertFalse(SocialAccount.objects.exists())

    def test_disconnect_is_owner_scoped_and_clears_encrypted_tokens(self):
        account = self.create_account(self.user.id, "owned-page")
        foreign = self.create_account(self.other_user_id, "foreign-page")

        response = self.client.delete(f"/api/social/accounts/{account.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        account.refresh_from_db()
        self.assertEqual(account.status, SocialAccount.Status.DISCONNECTED)
        self.assertEqual(account.access_token_encrypted, "")
        self.assertEqual(account.refresh_token_encrypted, "")

        response = self.client.delete(f"/api/social/accounts/{foreign.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, SocialAccount.Status.CONNECTED)

    @override_settings(SOCIAL_TOKEN_ENCRYPTION_KEY="")
    def test_token_encryption_requires_a_server_side_key(self):
        from core.services.social_tokens import (
            SocialTokenEncryptionError,
            encrypt_social_token,
        )

        with self.assertRaises(SocialTokenEncryptionError):
            encrypt_social_token("private-token")

    def test_token_encryption_round_trip(self):
        from core.services.social_tokens import (
            decrypt_social_token,
            encrypt_social_token,
        )

        key = Fernet.generate_key().decode("ascii")
        with self.settings(SOCIAL_TOKEN_ENCRYPTION_KEY=key):
            encrypted = encrypt_social_token("private-token-value")
            self.assertNotEqual(encrypted, "private-token-value")
            self.assertEqual(decrypt_social_token(encrypted), "private-token-value")


class SubscriptionApiTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.other_user_id = uuid4()
        self.client.force_authenticate(user=self.user)

    def create_subscription(self, owner_id=None):
        return UserSubscription.objects.create(
            owner_id=owner_id or self.user.id,
            provider="test-adapter",
            provider_subscription_id=f"sub_{uuid4()}",
            plan_id="premium_monthly",
            billing_interval=UserSubscription.BillingInterval.MONTHLY,
            status=UserSubscription.Status.ACTIVE,
        )

    def test_checkout_cors_preflight_allows_idempotency_header_for_web_origin(
        self,
    ):
        with self.settings(CORS_ALLOWED_ORIGINS=["http://localhost:8081"]):
            response = self.client.options(
                "/api/subscription/checkout/",
                HTTP_ORIGIN="http://localhost:8081",
                HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
                HTTP_ACCESS_CONTROL_REQUEST_HEADERS=(
                    "authorization,content-type,idempotency-key"
                ),
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response["Access-Control-Allow-Origin"],
            "http://localhost:8081",
        )
        self.assertIn(
            "idempotency-key",
            response["Access-Control-Allow-Headers"].lower(),
        )
        self.assertIn("POST", response["Access-Control-Allow-Methods"])

    @override_settings(
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
        STRIPE_CHECKOUT_SUCCESS_URL="",
        STRIPE_CHECKOUT_CANCEL_URL="",
        STRIPE_PRICE_STARTER_MONTHLY="",
        STRIPE_PRICE_STARTER_ANNUAL="",
        STRIPE_PRICE_PRO_MONTHLY="",
        STRIPE_PRICE_PRO_ANNUAL="",
        STRIPE_PRICE_ENTERPRISE_MONTHLY="",
        STRIPE_PRICE_ENTERPRISE_ANNUAL="",
    )
    def test_plan_catalog_lists_all_plans_and_unconfigured_intervals(self):
        response = self.client.get("/api/subscription/plans/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["provider_configured"])
        self.assertEqual(
            [plan["id"] for plan in response.data["plans"]],
            ["starter", "pro", "enterprise"],
        )
        for plan in response.data["plans"]:
            self.assertEqual(plan["billing_intervals"], ["monthly", "annual"])
            self.assertFalse(plan["features_configured"])
            self.assertEqual(plan["features"], [])
            for interval in ("monthly", "annual"):
                self.assertFalse(
                    plan["prices"][interval]["checkout_available"]
                )
                self.assertIsNone(plan["prices"][interval]["price_minor"])
        self.assertIn("plan_features", response.data["missing_configuration"])
        self.assertIn(
            "starter_monthly_stripe_price",
            response.data["missing_configuration"],
        )

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_unit_test",
        STRIPE_WEBHOOK_SECRET="whsec_unit_test",
        STRIPE_CHECKOUT_SUCCESS_URL="ibda://subscription/success",
        STRIPE_CHECKOUT_CANCEL_URL="ibda://subscription/cancel",
        STRIPE_PRICE_STARTER_MONTHLY="price_server_starter_monthly",
        STRIPE_PRICE_STARTER_ANNUAL="",
        STRIPE_PRICE_PRO_MONTHLY="",
        STRIPE_PRICE_PRO_ANNUAL="",
        STRIPE_PRICE_ENTERPRISE_MONTHLY="",
        STRIPE_PRICE_ENTERPRISE_ANNUAL="",
    )
    @patch(
        "core.services.payments.catalog.retrieve_price_details",
        return_value={
            "price_minor": 1250,
            "currency": "USD",
            "active": True,
            "recurring_interval": "month",
            "recurring_interval_count": 1,
        },
    )
    def test_catalog_uses_configured_stripe_price_without_exposing_price_id(
        self,
        retrieve_price,
    ):
        response = self.client.get("/api/subscription/plans/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        starter = response.data["plans"][0]
        self.assertEqual(
            starter["prices"]["monthly"]["price_minor"],
            1250,
        )
        self.assertEqual(starter["prices"]["monthly"]["currency"], "USD")
        self.assertTrue(starter["prices"]["monthly"]["checkout_available"])
        self.assertNotIn("price_id", starter["prices"]["monthly"])
        retrieve_price.assert_called_once_with("price_server_starter_monthly")

    def test_subscription_endpoints_require_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/subscription/me/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_subscription_and_history_are_scoped_to_authenticated_user(self):
        owned = self.create_subscription()
        foreign = self.create_subscription(self.other_user_id)
        PaymentTransaction.objects.create(
            subscription=owned,
            provider="test-adapter",
            provider_transaction_id="owned-payment",
            status=PaymentTransaction.Status.SUCCEEDED,
            amount_minor=1000,
            currency="USD",
        )
        PaymentTransaction.objects.create(
            subscription=foreign,
            provider="test-adapter",
            provider_transaction_id="foreign-payment",
            status=PaymentTransaction.Status.SUCCEEDED,
        )

        response = self.client.get("/api/subscription/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["subscription"]["id"], str(owned.id))
        self.assertEqual(len(response.data["transactions"]), 1)
        self.assertEqual(
            response.data["transactions"][0]["id"],
            str(PaymentTransaction.objects.get(
                provider_transaction_id="owned-payment"
            ).id),
        )

    @override_settings(
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
        STRIPE_CHECKOUT_SUCCESS_URL="",
        STRIPE_CHECKOUT_CANCEL_URL="",
        STRIPE_PRICE_PRO_MONTHLY="",
    )
    def test_checkout_reports_missing_price_without_creating_subscription(self):
        response = self.client.post(
            "/api/subscription/checkout/",
            {"plan_id": "pro", "billing_interval": "monthly"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertFalse(UserSubscription.objects.exists())

    def test_checkout_rejects_price_with_wrong_billing_interval(self):
        with self.settings(
            STRIPE_SECRET_KEY="sk_test_unit_test",
            STRIPE_WEBHOOK_SECRET="whsec_unit_test",
            STRIPE_CHECKOUT_SUCCESS_URL="ibda://subscription/success",
            STRIPE_CHECKOUT_CANCEL_URL="ibda://subscription/cancel",
            STRIPE_PRICE_PRO_MONTHLY="price_server_pro_monthly",
        ):
            with patch(
                "core.services.payments.checkout.retrieve_price_details",
                return_value={
                    "price_minor": 2500,
                    "currency": "USD",
                    "active": True,
                    "recurring_interval": "year",
                    "recurring_interval_count": 1,
                },
            ) as retrieve_price:
                response = self.client.post(
                    "/api/subscription/checkout/",
                    {"plan_id": "pro", "billing_interval": "monthly"},
                    format="json",
                    HTTP_IDEMPOTENCY_KEY=str(uuid4()),
                )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        retrieve_price.assert_called_once_with("price_server_pro_monthly")
        self.assertFalse(UserSubscription.objects.exists())

    def test_checkout_requires_authenticated_user(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/subscription/checkout/",
            {"plan_id": "pro", "billing_interval": "monthly"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_checkout_get_requires_auth_then_rejects_method(self):
        self.client.force_authenticate(user=None)
        unauthenticated = self.client.get("/api/subscription/checkout/")
        self.assertEqual(
            unauthenticated.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        self.client.force_authenticate(user=self.user)
        authenticated = self.client.get("/api/subscription/checkout/")
        self.assertEqual(
            authenticated.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_checkout_authenticates_supabase_bearer_before_creating_session(
        self,
    ):
        token = "test-access-token"
        session = SimpleNamespace(
            id="cs_test_authenticated",
            url="https://checkout.stripe.test/authenticated",
        )
        self.client.force_authenticate(user=None)
        with self.settings(
            SUPABASE_URL="https://supabase.example.invalid",
            SUPABASE_PUBLISHABLE_KEY="publishable-test-key",
            STRIPE_SECRET_KEY="sk_test_unit_test",
            STRIPE_WEBHOOK_SECRET="whsec_unit_test",
            STRIPE_CHECKOUT_SUCCESS_URL="ibda://subscription/success",
            STRIPE_CHECKOUT_CANCEL_URL="ibda://subscription/cancel",
            STRIPE_PRICE_PRO_MONTHLY="price_server_pro_monthly",
        ):
            with (
                patch("core.authentication.requests.get") as verify_user,
                patch(
                    "core.services.payments.checkout.retrieve_price_details",
                    return_value={
                        "price_minor": 1250,
                        "currency": "USD",
                        "active": True,
                        "recurring_interval": "month",
                        "recurring_interval_count": 1,
                    },
                ),
                patch(
                    "core.services.payments.checkout.create_customer",
                    return_value=SimpleNamespace(id="cus_test_authenticated"),
                ),
                patch(
                    "core.services.payments.checkout.create_checkout_session",
                    return_value=session,
                ),
            ):
                verify_user.return_value.status_code = 200
                verify_user.return_value.json.return_value = {
                    "id": str(self.user.id),
                    "email": "creator@example.invalid",
                }
                response = self.client.post(
                    "/api/subscription/checkout/",
                    {"plan_id": "pro", "billing_interval": "monthly"},
                    format="json",
                    HTTP_AUTHORIZATION=f"Bearer {token}",
                    HTTP_IDEMPOTENCY_KEY=str(uuid4()),
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["checkout_url"], session.url)
        self.assertEqual(response.data["session_id"], session.id)
        verify_user.assert_called_once()
        self.assertEqual(
            verify_user.call_args.kwargs["headers"]["Authorization"],
            f"Bearer {token}",
        )
        self.assertEqual(
            verify_user.call_args.kwargs["headers"]["apikey"],
            "publishable-test-key",
        )

    def test_checkout_creates_pending_stripe_session_with_server_configuration(
        self,
    ):
        session = SimpleNamespace(
            id="cs_test_123",
            url="https://checkout.stripe.test/session",
        )
        with self.settings(
            STRIPE_SECRET_KEY="sk_test_unit_test",
            STRIPE_WEBHOOK_SECRET="whsec_unit_test",
            STRIPE_CHECKOUT_SUCCESS_URL=(
                "ibda://subscription/success?session_id={CHECKOUT_SESSION_ID}"
            ),
            STRIPE_CHECKOUT_CANCEL_URL="ibda://subscription/cancel",
            STRIPE_PRICE_PRO_MONTHLY="price_server_pro_monthly",
        ):
            with (
                patch(
                    "core.services.payments.checkout.retrieve_price_details",
                    return_value={
                        "price_minor": 1250,
                        "currency": "USD",
                        "active": True,
                        "recurring_interval": "month",
                        "recurring_interval_count": 1,
                    },
                ),
                patch(
                    "core.services.payments.checkout.create_customer",
                    return_value=SimpleNamespace(id="cus_test_123"),
                ) as create_customer,
                patch(
                    "core.services.payments.checkout.create_checkout_session",
                    return_value=session,
                ) as create_session,
            ):
                response = self.client.post(
                    "/api/subscription/checkout/",
                    {
                        "plan_id": "pro",
                        "billing_interval": "monthly",
                        "price_id": "price_attacker_supplied",
                        "success_url": "https://attacker.invalid",
                        "cancel_url": "https://attacker.invalid",
                    },
                    format="json",
                    HTTP_IDEMPOTENCY_KEY=str(uuid4()),
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "checkout_url": session.url,
                "session_id": session.id,
            },
        )
        create_customer.assert_called_once_with(self.user.id, None)
        self.assertEqual(
            create_session.call_args.kwargs["price_id"],
            "price_server_pro_monthly",
        )
        self.assertEqual(
            UserSubscription.objects.get().status,
            UserSubscription.Status.PENDING,
        )
        self.assertEqual(
            UserSubscription.objects.get().plan_id,
            "pro",
        )

    def test_checkout_stripe_errors_are_safe_and_leave_no_pending_record(self):
        with self.settings(
            STRIPE_SECRET_KEY="sk_test_unit_test",
            STRIPE_WEBHOOK_SECRET="whsec_unit_test",
            STRIPE_CHECKOUT_SUCCESS_URL="ibda://subscription/success",
            STRIPE_CHECKOUT_CANCEL_URL="ibda://subscription/cancel",
            STRIPE_PRICE_STARTER_ANNUAL="price_server_starter_annual",
        ):
            with (
                patch(
                    "core.services.payments.checkout.retrieve_price_details",
                    return_value={
                        "price_minor": 2500,
                        "currency": "USD",
                        "active": True,
                        "recurring_interval": "year",
                        "recurring_interval_count": 1,
                    },
                ),
                patch(
                    "core.services.payments.checkout.create_customer",
                    side_effect=stripe.APIConnectionError("test connection failure"),
                ),
            ):
                response = self.client.post(
                    "/api/subscription/checkout/",
                    {"plan_id": "starter", "billing_interval": "annual"},
                    format="json",
                    HTTP_IDEMPOTENCY_KEY=str(uuid4()),
                )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(
            response.data["detail"],
            "Unable to start checkout. Please try again later.",
        )
        self.assertFalse(UserSubscription.objects.exists())

    def test_checkout_retry_reuses_one_local_subscription_and_idempotency_key(
        self,
    ):
        session = SimpleNamespace(
            id="cs_test_retry",
            url="https://checkout.stripe.test/retry",
        )
        idempotency_key = str(uuid4())
        with self.settings(
            STRIPE_SECRET_KEY="sk_test_unit_test",
            STRIPE_WEBHOOK_SECRET="whsec_unit_test",
            STRIPE_CHECKOUT_SUCCESS_URL="ibda://subscription/success",
            STRIPE_CHECKOUT_CANCEL_URL="ibda://subscription/cancel",
            STRIPE_PRICE_ENTERPRISE_ANNUAL="price_server_enterprise_annual",
        ):
            with (
                patch(
                    "core.services.payments.checkout.retrieve_price_details",
                    return_value={
                        "price_minor": 5000,
                        "currency": "USD",
                        "active": True,
                        "recurring_interval": "year",
                        "recurring_interval_count": 1,
                    },
                ),
                patch(
                    "core.services.payments.checkout.create_customer",
                    return_value=SimpleNamespace(id="cus_test_retry"),
                ) as create_customer,
                patch(
                    "core.services.payments.checkout.create_checkout_session",
                    return_value=session,
                ) as create_session,
            ):
                responses = [
                    self.client.post(
                        "/api/subscription/checkout/",
                        {
                            "plan_id": "enterprise",
                            "billing_interval": "annual",
                        },
                        format="json",
                        HTTP_IDEMPOTENCY_KEY=idempotency_key,
                    )
                    for _ in range(2)
                ]

        self.assertEqual(
            [response.status_code for response in responses],
            [status.HTTP_200_OK, status.HTTP_200_OK],
        )
        self.assertEqual(UserSubscription.objects.count(), 1)
        self.assertEqual(
            create_session.call_args_list[0].kwargs["idempotency_key"],
            create_session.call_args_list[1].kwargs["idempotency_key"],
        )
        create_customer.assert_called_once()

    def test_checkout_rejects_invalid_plan_interval_and_idempotency_key(self):
        invalid_plan = self.client.post(
            "/api/subscription/checkout/",
            {"plan_id": "custom", "billing_interval": "monthly"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        invalid_interval = self.client.post(
            "/api/subscription/checkout/",
            {"plan_id": "pro", "billing_interval": "weekly"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        invalid_idempotency = self.client.post(
            "/api/subscription/checkout/",
            {"plan_id": "pro", "billing_interval": "monthly"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="not-a-uuid",
        )

        self.assertEqual(invalid_plan.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            invalid_interval.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            invalid_idempotency.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_webhook_rejects_invalid_signature(self):
        payload = json.dumps(
            {
                "event_id": "evt-invalid",
                "event_type": "subscription.updated",
                "subscription_id": "provider-sub",
                "status": "active",
            },
            separators=(",", ":"),
        ).encode("utf-8")
        with self.settings(
            PAYMENT_PROVIDER="test-adapter",
            PAYMENT_WEBHOOK_SECRET="webhook-secret",
        ):
            response = self.client.generic(
                "POST",
                "/api/payments/webhook/",
                payload,
                content_type="application/json",
                HTTP_X_IBDA_SIGNATURE="0" * 64,
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ProviderWebhookEvent.objects.exists())

    def test_signed_webhook_updates_subscription_and_is_idempotent(self):
        subscription = self.create_subscription()
        payload = json.dumps(
            {
                "event_id": "evt-subscription-update",
                "event_type": "subscription.updated",
                "subscription_id": subscription.provider_subscription_id,
                "status": "active",
                "plan_id": "premium",
                "billing_interval": "annual",
            },
            separators=(",", ":"),
        ).encode("utf-8")
        signature = hmac.new(
            b"webhook-secret",
            payload,
            hashlib.sha256,
        ).hexdigest()

        with self.settings(
            PAYMENT_PROVIDER="test-adapter",
            PAYMENT_WEBHOOK_SECRET="webhook-secret",
        ):
            response = self.client.generic(
                "POST",
                "/api/payments/webhook/",
                payload,
                content_type="application/json",
                HTTP_X_IBDA_SIGNATURE=signature,
            )
            duplicate = self.client.generic(
                "POST",
                "/api/payments/webhook/",
                payload,
                content_type="application/json",
                HTTP_X_IBDA_SIGNATURE=signature,
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["duplicate"])
        self.assertEqual(duplicate.status_code, status.HTTP_200_OK)
        self.assertTrue(duplicate.data["duplicate"])
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan_id, "premium")
        self.assertEqual(subscription.billing_interval, "annual")
        self.assertEqual(ProviderWebhookEvent.objects.count(), 1)

    def test_webhook_records_only_signed_transactions_once(self):
        subscription = self.create_subscription()
        payload = json.dumps(
            {
                "event_id": "evt-transaction",
                "event_type": "transaction.updated",
                "subscription_id": subscription.provider_subscription_id,
                "transaction_id": "provider-payment-1",
                "status": "refunded",
                "amount_minor": 2450,
                "currency": "USD",
            },
            separators=(",", ":"),
        ).encode("utf-8")
        signature = hmac.new(
            b"webhook-secret",
            payload,
            hashlib.sha256,
        ).hexdigest()

        with self.settings(
            PAYMENT_PROVIDER="test-adapter",
            PAYMENT_WEBHOOK_SECRET="webhook-secret",
        ):
            response = self.client.generic(
                "POST",
                "/api/payments/webhook/",
                payload,
                content_type="application/json",
                HTTP_X_IBDA_SIGNATURE=signature,
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment = PaymentTransaction.objects.get(
            provider_transaction_id="provider-payment-1"
        )
        self.assertEqual(payment.status, PaymentTransaction.Status.REFUNDED)
        self.assertEqual(payment.amount_minor, 2450)
        self.assertEqual(payment.subscription_id, subscription.id)

    def test_invalid_subscription_status_is_rejected(self):
        subscription = self.create_subscription()
        payload = json.dumps(
            {
                "event_id": "evt-invalid-status",
                "event_type": "subscription.updated",
                "subscription_id": subscription.provider_subscription_id,
                "status": "paid",
            },
            separators=(",", ":"),
        ).encode("utf-8")
        signature = hmac.new(
            b"webhook-secret",
            payload,
            hashlib.sha256,
        ).hexdigest()

        with self.settings(
            PAYMENT_PROVIDER="test-adapter",
            PAYMENT_WEBHOOK_SECRET="webhook-secret",
        ):
            response = self.client.generic(
                "POST",
                "/api/payments/webhook/",
                payload,
                content_type="application/json",
                HTTP_X_IBDA_SIGNATURE=signature,
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ProviderWebhookEvent.objects.exists())

    def test_configured_entitlements_are_centralized_and_optional(self):
        with self.settings(
            SUBSCRIPTION_ENTITLEMENT_LIMITS=(
                '{"free":{"saved_brands":1},"premium":{"saved_brands":null}}'
            )
        ):
            response = self.client.get("/api/subscription/me/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["entitlements"]["saved_brands"], 1)

    def test_configured_saved_brand_limit_is_enforced(self):
        Brand.objects.create(owner_id=self.user.id, name="Existing brand")
        with self.settings(
            SUBSCRIPTION_ENTITLEMENT_LIMITS='{"free":{"saved_brands":1}}'
        ):
            response = self.client.post(
                "/api/brands/",
                {"name": "Over limit"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Brand.objects.filter(owner_id=self.user.id).count(), 1)


@override_settings(STRIPE_SECRET_KEY="sk_test_unit_test")
class StripeWebhookApiTests(APITestCase):
    signing_secret = "whsec_unit_test"

    def post_stripe_event(self, event, *, raw_payload=None, signature=None):
        event.setdefault("livemode", False)
        payload = raw_payload or json.dumps(
            event,
            separators=(",", ":"),
        ).encode("utf-8")
        if signature is None:
            signature = stripe.WebhookSignature.generate_signature_header(
                payload.decode("utf-8"),
                self.signing_secret,
                timestamp=int(time.time()),
            )
        return self.client.generic(
            "POST",
            "/api/payments/stripe/webhook/",
            payload,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=signature,
        )

    def create_stripe_subscription(self, *, status_value="pending"):
        return UserSubscription.objects.create(
            owner_id=uuid4(),
            provider="stripe",
            provider_customer_id="cus_webhook_test",
            plan_id="starter",
            billing_interval=UserSubscription.BillingInterval.MONTHLY,
            status=status_value,
        )

    def subscription_event(
        self,
        subscription,
        *,
        event_id="evt_subscription_created",
        event_type="customer.subscription.created",
        created=None,
        status_value="active",
        price_id="price_starter_monthly",
    ):
        return {
            "id": event_id,
            "type": event_type,
            "created": created or int(time.time()),
            "data": {
                "object": {
                    "id": "sub_webhook_test",
                    "object": "subscription",
                    "customer": "cus_webhook_test",
                    "status": status_value,
                    "metadata": {
                        "ibda_subscription_id": str(subscription.id),
                        "ibda_owner_id": str(subscription.owner_id),
                    },
                    "items": {
                        "data": [{"price": {"id": price_id}}],
                    },
                    "current_period_start": 1_800_000_000,
                    "current_period_end": 1_802_592_000,
                    "cancel_at_period_end": False,
                    "canceled_at": None,
                }
            },
        }

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_unit_test")
    def test_stripe_webhook_rejects_bad_signatures_and_malformed_payloads(self):
        event = {
            "id": "evt_bad_signature",
            "type": "future.event",
            "created": int(time.time()),
            "data": {"object": {}},
        }
        invalid_signature = self.post_stripe_event(
            event,
            signature="t=1,v1=invalid",
        )
        malformed = self.post_stripe_event(
            {},
            raw_payload=b"not-json",
        )

        self.assertEqual(
            invalid_signature.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(malformed.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ProviderWebhookEvent.objects.exists())

    @override_settings(STRIPE_WEBHOOK_SECRET="")
    def test_stripe_webhook_requires_server_side_signing_secret(self):
        response = self.client.post(
            "/api/payments/stripe/webhook/",
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def test_live_mode_events_are_rejected(self):
        event = {
            "id": "evt_live_mode",
            "type": "future.unknown_event",
            "created": int(time.time()),
            "livemode": True,
            "data": {"object": {}},
        }
        with self.settings(STRIPE_WEBHOOK_SECRET=self.signing_secret):
            response = self.post_stripe_event(event)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ProviderWebhookEvent.objects.exists())

    def test_subscription_created_event_grants_entitlement_after_verification(
        self,
    ):
        subscription = self.create_stripe_subscription()
        event = self.subscription_event(subscription)
        with self.settings(
            STRIPE_WEBHOOK_SECRET=self.signing_secret,
            STRIPE_PRICE_STARTER_MONTHLY="price_starter_monthly",
        ):
            response = self.post_stripe_event(event)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.Status.ACTIVE)
        self.assertEqual(subscription.provider_subscription_id, "sub_webhook_test")
        self.assertIsNotNone(subscription.last_provider_event_created_at)
        self.assertEqual(ProviderWebhookEvent.objects.count(), 1)

    def test_trialing_subscription_maps_to_existing_active_status(self):
        subscription = self.create_stripe_subscription()
        event = self.subscription_event(
            subscription,
            event_type="customer.subscription.updated",
            status_value="trialing",
        )
        with self.settings(
            STRIPE_WEBHOOK_SECRET=self.signing_secret,
            STRIPE_PRICE_STARTER_MONTHLY="price_starter_monthly",
        ):
            response = self.post_stripe_event(event)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.Status.ACTIVE)

    def test_unpaid_subscription_does_not_grant_paid_entitlement(self):
        subscription = self.create_stripe_subscription()
        event = self.subscription_event(
            subscription,
            event_type="customer.subscription.updated",
            status_value="unpaid",
        )
        with self.settings(
            STRIPE_WEBHOOK_SECRET=self.signing_secret,
            STRIPE_PRICE_STARTER_MONTHLY="price_starter_monthly",
        ):
            response = self.post_stripe_event(event)
            self.client.force_authenticate(
                user=SimpleNamespace(
                    id=subscription.owner_id,
                    is_authenticated=True,
                )
            )
            account = self.client.get("/api/subscription/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.Status.FAILED)
        self.assertEqual(account.status_code, status.HTTP_200_OK)
        self.assertEqual(account.data["plan_id"], "free")

    def test_duplicate_stripe_event_is_processed_once(self):
        subscription = self.create_stripe_subscription()
        event = self.subscription_event(subscription)
        with self.settings(
            STRIPE_WEBHOOK_SECRET=self.signing_secret,
            STRIPE_PRICE_STARTER_MONTHLY="price_starter_monthly",
        ):
            first = self.post_stripe_event(event)
            duplicate = self.post_stripe_event(event)

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertFalse(first.data["duplicate"])
        self.assertEqual(duplicate.status_code, status.HTTP_200_OK)
        self.assertTrue(duplicate.data["duplicate"])
        self.assertEqual(ProviderWebhookEvent.objects.count(), 1)

    def test_failed_stripe_event_is_not_marked_processed(self):
        subscription = self.create_stripe_subscription()
        event = self.subscription_event(
            subscription,
            price_id="price_not_configured",
        )
        with self.settings(
            STRIPE_WEBHOOK_SECRET=self.signing_secret,
            STRIPE_PRICE_STARTER_MONTHLY="price_starter_monthly",
        ):
            response = self.post_stripe_event(event)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ProviderWebhookEvent.objects.exists())
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.Status.PENDING)

    def test_checkout_completed_does_not_activate_a_subscription(self):
        subscription = self.create_stripe_subscription()
        event = {
            "id": "evt_checkout_completed",
            "type": "checkout.session.completed",
            "created": int(time.time()),
            "data": {
                "object": {
                    "id": "cs_completed_test",
                    "mode": "subscription",
                    "payment_status": "paid",
                    "customer": "cus_webhook_test",
                    "subscription": "sub_webhook_test",
                    "client_reference_id": str(subscription.id),
                    "metadata": {
                        "ibda_subscription_id": str(subscription.id),
                        "ibda_owner_id": str(subscription.owner_id),
                    },
                }
            },
        }
        with self.settings(STRIPE_WEBHOOK_SECRET=self.signing_secret):
            response = self.post_stripe_event(event)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.Status.PENDING)
        self.assertEqual(subscription.provider_subscription_id, "sub_webhook_test")

    def test_invoice_paid_and_failed_update_the_existing_transaction(self):
        subscription = self.create_stripe_subscription(
            status_value=UserSubscription.Status.ACTIVE,
        )
        subscription.provider_subscription_id = "sub_invoice_test"
        subscription.save(update_fields=["provider_subscription_id", "updated_at"])
        invoice_data = {
            "id": "in_retryable_test",
            "subscription": "sub_invoice_test",
            "amount_paid": 1250,
            "amount_due": 1250,
            "currency": "usd",
        }
        with self.settings(STRIPE_WEBHOOK_SECRET=self.signing_secret):
            failed = self.post_stripe_event(
                {
                    "id": "evt_invoice_failed",
                    "type": "invoice.payment_failed",
                    "created": int(time.time()),
                    "data": {"object": invoice_data},
                }
            )
            paid = self.post_stripe_event(
                {
                    "id": "evt_invoice_paid",
                    "type": "invoice.paid",
                    "created": int(time.time()),
                    "data": {"object": invoice_data},
                }
            )

        self.assertEqual(failed.status_code, status.HTTP_200_OK)
        self.assertEqual(paid.status_code, status.HTTP_200_OK)
        payment = PaymentTransaction.objects.get(
            provider_transaction_id="in_retryable_test"
        )
        self.assertEqual(payment.status, PaymentTransaction.Status.SUCCEEDED)
        self.assertEqual(payment.amount_minor, 1250)
        self.assertEqual(payment.currency, "USD")
        self.assertEqual(PaymentTransaction.objects.count(), 1)
        subscription.refresh_from_db()
        self.assertEqual(
            subscription.status,
            UserSubscription.Status.PAST_DUE,
        )

    def test_old_subscription_event_cannot_reactivate_a_canceled_subscription(
        self,
    ):
        subscription = self.create_stripe_subscription(
            status_value=UserSubscription.Status.PENDING,
        )
        now = int(time.time())
        canceled = self.subscription_event(
            subscription,
            event_id="evt_subscription_deleted",
            event_type="customer.subscription.deleted",
            created=now,
            status_value="canceled",
        )
        older_update = self.subscription_event(
            subscription,
            event_id="evt_subscription_older_update",
            event_type="customer.subscription.updated",
            created=now - 10,
            status_value="active",
        )
        with self.settings(
            STRIPE_WEBHOOK_SECRET=self.signing_secret,
            STRIPE_PRICE_STARTER_MONTHLY="price_starter_monthly",
        ):
            deleted_response = self.post_stripe_event(canceled)
            older_response = self.post_stripe_event(older_update)

        self.assertEqual(deleted_response.status_code, status.HTTP_200_OK)
        self.assertEqual(older_response.status_code, status.HTTP_200_OK)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.Status.CANCELED)

    def test_unknown_valid_stripe_events_are_acknowledged_and_deduplicated(self):
        event = {
            "id": "evt_future_type",
            "type": "future.unknown_event",
            "created": int(time.time()),
            "data": {"object": {}},
        }
        with self.settings(STRIPE_WEBHOOK_SECRET=self.signing_secret):
            response = self.post_stripe_event(event)
            duplicate = self.post_stripe_event(event)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(duplicate.status_code, status.HTTP_200_OK)
        self.assertTrue(duplicate.data["duplicate"])
        self.assertEqual(ProviderWebhookEvent.objects.count(), 1)
