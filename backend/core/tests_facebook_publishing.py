from datetime import datetime, timedelta, timezone as datetime_timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    Brand,
    ContentPost,
    Notification,
    ScheduledPost,
    SocialAccount,
)
from .services.scheduling import publish_due_posts
from .services.social_tokens import encrypt_social_token

PAGE_ID = "1420648971139874"
PAGE_TOKEN = "page-token-secret-123"
TEST_FERNET_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
NOW = datetime(2030, 1, 16, tzinfo=datetime_timezone.utc)


def graph_response(status_code, payload):
    return SimpleNamespace(status_code=status_code, json=lambda: payload)


@override_settings(
    SOCIAL_TOKEN_ENCRYPTION_KEY=TEST_FERNET_KEY,
    SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
)
class FacebookPagePublishingTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.client.force_authenticate(user=self.user)
        self.brand = Brand.objects.create(
            owner_id=self.user.id,
            name="Ibda Project",
        )
        self.post = ContentPost.objects.create(
            brand=self.brand,
            title="Launch",
            body="Hello from IBDA",
            hashtags=["ibda", "launch"],
            platform=ContentPost.Platform.FACEBOOK,
            status=ContentPost.Status.APPROVED,
        )
        self.account = SocialAccount.objects.create(
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            platform_account_id=PAGE_ID,
            display_name="Ibda Project",
            access_token_encrypted=encrypt_social_token(PAGE_TOKEN),
        )

    def schedule(self, **overrides):
        payload = {
            "post_id": str(self.post.id),
            "platforms": ["facebook"],
            "scheduled_for": "2030-01-15T09:30:00+05:00",
            "timezone_name": "Asia/Karachi",
        }
        payload.update(overrides)
        return self.client.post(
            "/api/calendar/scheduled-posts/create/",
            payload,
            format="json",
        )

    def due_post(self, **overrides):
        values = {
            "post": self.post,
            "platform": ContentPost.Platform.FACEBOOK,
            "social_account": self.account,
            "scheduled_for": NOW - timedelta(minutes=2),
            "timezone_name": "Asia/Karachi",
        }
        values.update(overrides)
        return ScheduledPost.objects.create(**values)

    @patch("core.services.facebook_publishing.requests.post")
    def test_schedule_links_the_single_connected_page(self, graph_post):
        response = self.schedule()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        scheduled = ScheduledPost.objects.get(post=self.post)
        self.assertEqual(scheduled.social_account_id, self.account.id)
        self.assertEqual(
            response.data[0]["social_account"]["display_name"],
            "Ibda Project",
        )

    def test_schedule_requires_a_connected_page(self):
        SocialAccount.objects.all().delete()

        response = self.schedule()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "facebook_page_not_connected")
        self.assertFalse(ScheduledPost.objects.filter(post=self.post).exists())

    def test_multiple_pages_require_an_explicit_page(self):
        second = SocialAccount.objects.create(
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            platform_account_id="9876543210",
            display_name="Second Page",
            access_token_encrypted=encrypt_social_token("second-token"),
        )

        ambiguous = self.schedule()
        self.assertEqual(ambiguous.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(ambiguous.data["code"], "facebook_page_required")

        chosen = self.schedule(social_account_id=str(second.id))
        self.assertEqual(chosen.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            ScheduledPost.objects.get(post=self.post).social_account_id,
            second.id,
        )

    def test_cannot_schedule_to_another_users_page(self):
        foreign = SocialAccount.objects.create(
            owner_id=uuid4(),
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            platform_account_id="5555555555",
            display_name="Foreign Page",
            access_token_encrypted=encrypt_social_token("foreign-token"),
        )

        response = self.schedule(social_account_id=str(foreign.id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], "facebook_page_not_found")

    @patch("core.services.facebook_publishing.requests.post")
    def test_due_post_publishes_to_the_selected_page(self, graph_post):
        graph_post.return_value = graph_response(
            200,
            {"id": f"{PAGE_ID}_101" },
        )
        scheduled = self.due_post()

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["published"], 1)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledPost.Status.PUBLISHED)
        self.assertEqual(scheduled.external_post_id, f"{PAGE_ID}_101")
        self.assertEqual(scheduled.published_at, NOW)
        self.assertEqual(scheduled.error_message, "")
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, ContentPost.Status.PUBLISHED)
        self.assertTrue(
            Notification.objects.filter(
                related_object_id=scheduled.id,
                notification_type=Notification.Type.POST_PUBLISHED,
            ).exists()
        )

        url, = graph_post.call_args.args
        self.assertEqual(
            url,
            f"https://graph.facebook.com/v27.0/{PAGE_ID}/feed",
        )
        self.assertEqual(
            graph_post.call_args.kwargs["data"],
            {
                "message": "Hello from IBDA\n\n#ibda #launch",
                "access_token": PAGE_TOKEN,
            },
        )
        self.assertNotIn(PAGE_TOKEN, url)

    @patch("core.services.facebook_publishing.requests.post")
    def test_a_post_scheduled_two_minutes_ahead_publishes_when_due(
        self,
        graph_post,
    ):
        graph_post.return_value = graph_response(200, {"id": f"{PAGE_ID}_102"})
        scheduled_for = NOW + timedelta(minutes=2)
        self.schedule(scheduled_for=scheduled_for.isoformat())

        too_early = publish_due_posts(now=NOW)
        self.assertEqual(too_early["processed"], 0)
        graph_post.assert_not_called()

        counts = publish_due_posts(now=scheduled_for + timedelta(seconds=1))

        self.assertEqual(counts["published"], 1)
        self.assertEqual(
            ScheduledPost.objects.get(post=self.post).status,
            ScheduledPost.Status.PUBLISHED,
        )

    @patch("core.services.facebook_publishing.requests.post")
    def test_second_worker_pass_does_not_publish_twice(self, graph_post):
        graph_post.return_value = graph_response(200, {"id": f"{PAGE_ID}_103"})
        self.due_post()

        publish_due_posts(now=NOW)
        counts = publish_due_posts(now=NOW + timedelta(minutes=5))

        self.assertEqual(counts["processed"], 0)
        self.assertEqual(graph_post.call_count, 1)

    @patch("core.services.facebook_publishing.requests.post")
    def test_rate_limit_is_retried_with_backoff(self, graph_post):
        graph_post.return_value = graph_response(
            400,
            {
                "error": {
                    "code": 4,
                    "message": "Application request limit reached",
                }
            },
        )
        scheduled = self.due_post()

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["retried"], 1)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledPost.Status.PENDING)
        self.assertEqual(scheduled.attempts, 1)
        self.assertGreater(scheduled.scheduled_for, NOW)
        self.assertIn(
            "Application request limit reached",
            scheduled.error_message,
        )

    @patch("core.services.facebook_publishing.requests.post")
    def test_permanent_token_error_is_not_retried(self, graph_post):
        graph_post.return_value = graph_response(
            400,
            {
                "error": {
                    "code": 190,
                    "message": f"Invalid token {PAGE_TOKEN}",
                }
            },
        )
        scheduled = self.due_post()
        original_time = scheduled.scheduled_for

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["failed"], 1)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledPost.Status.FAILED)
        self.assertEqual(scheduled.attempts, 1)
        self.assertEqual(scheduled.scheduled_for, original_time)
        self.assertNotIn(PAGE_TOKEN, scheduled.error_message)
        self.assertIn("[redacted]", scheduled.error_message)
        self.assertTrue(
            Notification.objects.filter(
                related_object_id=scheduled.id,
                notification_type=Notification.Type.POST_PUBLISH_FAILED,
            ).exists()
        )

    @patch("core.services.facebook_publishing.requests.post")
    def test_transient_failures_stop_after_the_retry_budget(self, graph_post):
        graph_post.return_value = graph_response(503, {})
        scheduled = self.due_post()
        scheduled.attempts = 2
        scheduled.save(update_fields=["attempts"])

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["failed"], 1)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledPost.Status.FAILED)
        self.assertEqual(scheduled.attempts, 3)

    @patch("core.services.facebook_publishing.requests.post")
    def test_unlinked_facebook_post_is_blocked_not_sent(self, graph_post):
        scheduled = self.due_post(social_account=None)

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["blocked"], 1)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledPost.Status.BLOCKED)
        self.assertIn("not linked to a Facebook Page", scheduled.error_message)
        graph_post.assert_not_called()

    @patch("core.services.facebook_publishing.requests.post")
    def test_revoked_page_token_is_not_retried(self, graph_post):
        self.account.status = SocialAccount.Status.EXPIRED
        self.account.save(update_fields=["status"])
        scheduled = self.due_post()

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["failed"], 1)
        scheduled.refresh_from_db()
        self.assertIn("connection is no longer active", scheduled.error_message)
        graph_post.assert_not_called()
