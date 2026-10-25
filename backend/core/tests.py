from types import SimpleNamespace
from datetime import datetime, timedelta, timezone as datetime_timezone
import hashlib
import hmac
import json
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4
from urllib.error import HTTPError

from rest_framework import status
from rest_framework.test import APITestCase
from django.test import override_settings
from cryptography.fernet import Fernet

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

    def test_plans_do_not_publish_prices_or_enable_unconfigured_checkout(self):
        response = self.client.get("/api/subscription/plans/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["provider_configured"])
        premium = next(
            plan for plan in response.data["plans"] if plan["id"] == "premium"
        )
        self.assertIsNone(premium["price_minor"])
        self.assertEqual(premium["billing_intervals"], [])
        self.assertFalse(premium["checkout_available"])

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

    def test_checkout_never_marks_subscription_paid_when_unconfigured(self):
        response = self.client.post(
            "/api/subscription/checkout/",
            {"plan_id": "premium_monthly"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertFalse(UserSubscription.objects.exists())

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
