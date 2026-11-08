import logging
from datetime import datetime, timedelta, timezone as datetime_timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from cryptography.fernet import Fernet
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .apps import OAuthCallbackLogFilter
from .models import Brand, ContentPost, Notification, ScheduledPost, SocialAccount
from .services.instagram_oauth import INSTAGRAM_SCOPES
from .services.instagram_publishing import build_instagram_caption
from .services.scheduling import publish_due_posts
from .services.social_tokens import decrypt_social_token, encrypt_social_token

NOW = datetime(2030, 1, 16, tzinfo=datetime_timezone.utc)
IG_ID = "17841400000000000"
TOKEN = "ig-long-lived-token-secret"
TEST_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def graph_response(status_code, payload):
    return SimpleNamespace(status_code=status_code, json=lambda: payload)


def social_settings():
    return override_settings(
        SOCIAL_INSTAGRAM_CLIENT_ID="ig-client-id",
        SOCIAL_INSTAGRAM_CLIENT_SECRET="ig-client-secret",
        SOCIAL_INSTAGRAM_REDIRECT_URI=(
            "https://social.example/api/social/oauth/instagram/callback/"
        ),
        SOCIAL_INSTAGRAM_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=TEST_KEY,
        SUPABASE_URL="https://supabase.example.invalid",
        SUPABASE_SERVICE_ROLE_KEY="service-role-test-key",
        SUPABASE_STORAGE_BUCKET="content-media",
    )


class InstagramOAuthTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.client.force_authenticate(user=self.user)

    def test_connect_reports_unconfigured_without_claiming_success(self):
        response = self.client.post(
            "/api/social/accounts/instagram/connect/", {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(response.data["configured"])
        self.assertFalse(SocialAccount.objects.exists())

    @social_settings()
    def test_connect_returns_an_instagram_login_authorization_url(self):
        response = self.client.post(
            "/api/social/accounts/instagram/connect/",
            {"response_mode": "web"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        url = response.data["authorization_url"]
        self.assertTrue(url.startswith("https://www.instagram.com/oauth/authorize?"))
        self.assertIn("instagram_business_basic", url)
        self.assertIn("instagram_business_content_publish", url)
        self.assertIn("response_type=code", url)
        self.assertIn("enable_fb_login=false", url)
        state = SocialAccount.objects.none()
        self.assertFalse(state.exists())
        from .models import SocialOAuthState

        oauth_state = SocialOAuthState.objects.get()
        self.assertEqual(oauth_state.platform, SocialAccount.Platform.INSTAGRAM)
        self.assertEqual(oauth_state.owner_id, self.user.id)
        self.assertEqual(oauth_state.response_mode, "web")

    @social_settings()
    def test_callback_connects_the_authorized_professional_account(self):
        from .models import SocialOAuthState
        import hashlib

        state = "instagram-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.INSTAGRAM,
            expires_at=NOW,
        )

        with patch(
            "core.services.instagram_oauth.requests.post"
        ) as exchange, patch(
            "core.services.instagram_oauth.requests.get"
        ) as profile:
            exchange.return_value = graph_response(
                200,
                {
                    "data": [
                        {
                            "access_token": "short-lived",
                            "user_id": IG_ID,
                            "permissions": ",".join(INSTAGRAM_SCOPES),
                        }
                    ]
                },
            )
            profile.side_effect = [
                graph_response(
                    200, {"access_token": TOKEN, "expires_in": 5184000}
                ),
                graph_response(
                    200,
                    {
                        "user_id": IG_ID,
                        "username": "ibda.studio",
                        "account_type": "BUSINESS",
                    },
                ),
            ]

            response = self.client.get(
                "/api/social/oauth/instagram/callback/",
                {"code": "authorization-code", "state": state},
            )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("status=connected", response["Location"])
        account = SocialAccount.objects.get(
            platform=SocialAccount.Platform.INSTAGRAM
        )
        self.assertEqual(account.platform_account_id, IG_ID)
        self.assertEqual(account.display_name, "ibda.studio")
        self.assertEqual(account.scopes, INSTAGRAM_SCOPES)
        self.assertEqual(decrypt_social_token(account.access_token_encrypted), TOKEN)
        self.assertIsNotNone(account.token_expires_at)

    @social_settings()
    def test_callback_rejects_a_non_professional_account(self):
        from .models import SocialOAuthState
        import hashlib

        state = "personal-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.INSTAGRAM,
            expires_at=NOW,
        )

        with patch(
            "core.services.instagram_oauth.requests.post"
        ) as exchange, patch(
            "core.services.instagram_oauth.requests.get"
        ) as profile:
            exchange.return_value = graph_response(
                200,
                {
                    "access_token": "short-lived",
                    "user_id": IG_ID,
                    "permissions": ",".join(INSTAGRAM_SCOPES),
                },
            )
            profile.side_effect = [
                graph_response(
                    200, {"access_token": TOKEN, "expires_in": 5184000}
                ),
                graph_response(
                    200,
                    {
                        "user_id": IG_ID,
                        "username": "personal",
                        "account_type": "PERSONAL",
                    },
                ),
            ]

            response = self.client.get(
                "/api/social/oauth/instagram/callback/",
                {"code": "authorization-code", "state": state},
            )

        self.assertIn("status=failed", response["Location"])
        self.assertFalse(
            SocialAccount.objects.filter(
                platform=SocialAccount.Platform.INSTAGRAM
            ).exists()
        )

    def test_instagram_callback_query_is_redacted_from_server_logs(self):
        record = logging.LogRecord(
            "django.server",
            logging.INFO,
            __file__,
            1,
            'GET /api/social/oauth/instagram/callback/?code=secret HTTP/1.1',
            (),
            None,
        )

        OAuthCallbackLogFilter().filter(record)

        self.assertNotIn("secret", record.getMessage())
        self.assertIn("[redacted]", record.getMessage())

    @social_settings()
    @patch("core.services.instagram_oauth.requests.post")
    def test_oauth_rejects_missing_content_publish_permission(self, exchange):
        from .services.instagram_oauth import (
            InstagramOAuthError,
            connect_instagram_account,
        )

        exchange.return_value = graph_response(
            200,
            {
                "data": [
                    {
                        "access_token": "short-lived",
                        "user_id": IG_ID,
                        "permissions": "instagram_business_basic",
                    }
                ]
            },
        )

        with self.assertRaises(InstagramOAuthError):
            connect_instagram_account(self.user.id, "authorization-code")

        self.assertFalse(SocialAccount.objects.exists())

@social_settings()
class InstagramPublishingTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.client.force_authenticate(user=self.user)
        self.brand = Brand.objects.create(
            owner_id=self.user.id, name="Ibda Project"
        )
        self.account = SocialAccount.objects.create(
            owner_id=self.user.id,
            platform=SocialAccount.Platform.INSTAGRAM,
            platform_account_id=IG_ID,
            display_name="ibda.studio",
            access_token_encrypted=encrypt_social_token(TOKEN),
            token_expires_at=NOW + timedelta(days=30),
        )

    def create_post(self, **overrides):
        values = {
            "brand": self.brand,
            "title": "Launch",
            "body": "Hello from IBDA",
            "hashtags": ["ibda", "launch"],
            "platform": ContentPost.Platform.INSTAGRAM,
            "status": ContentPost.Status.APPROVED,
            "image_url": "https://cdn.example/post.jpg",
        }
        values.update(overrides)
        return ContentPost.objects.create(**values)

    def due_post(self, post, account=None):
        return ScheduledPost.objects.create(
            post=post,
            platform=ContentPost.Platform.INSTAGRAM,
            social_account=self.account if account is None else account,
            scheduled_for=NOW - timedelta(minutes=2),
            timezone_name="UTC",
        )

    @patch("core.services.instagram_publishing.time.sleep")
    @patch("core.services.instagram_publishing.requests.get")
    @patch("core.services.instagram_publishing.requests.post")
    def test_due_image_post_publishes_to_instagram(
        self, graph_post, graph_get, _sleep
    ):
        graph_post.side_effect = [
            graph_response(200, {"id": "container-1"}),
            graph_response(200, {"id": "media-1"}),
        ]
        graph_get.return_value = graph_response(
            200, {"status_code": "FINISHED"}
        )
        scheduled = self.due_post(self.create_post())

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["published"], 1)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledPost.Status.PUBLISHED)
        self.assertEqual(scheduled.external_post_id, "media-1")
        self.assertEqual(scheduled.published_at, NOW)
        self.assertEqual(scheduled.error_message, "")
        scheduled.post.refresh_from_db()
        self.assertEqual(scheduled.post.status, ContentPost.Status.PUBLISHED)

        container_url = graph_post.call_args_list[0].args[0]
        self.assertEqual(
            container_url,
            f"https://graph.instagram.com/v27.0/{IG_ID}/media",
        )
        container_data = graph_post.call_args_list[0].kwargs["data"]
        self.assertEqual(
            container_data["image_url"], "https://cdn.example/post.jpg"
        )
        self.assertEqual(
            container_data["caption"], "Hello from IBDA\n\n#ibda #launch"
        )
        self.assertEqual(container_data["access_token"], TOKEN)

        publish_data = graph_post.call_args_list[1].kwargs["data"]
        self.assertEqual(publish_data["creation_id"], "container-1")
        self.assertNotIn(TOKEN, publish_data["creation_id"])
        self.assertTrue(
            Notification.objects.filter(
                related_object_id=scheduled.id,
                notification_type=Notification.Type.POST_PUBLISHED,
            ).exists()
        )

    @patch("core.services.instagram_publishing.requests.post")
    def test_post_without_an_image_fails_without_network_calls(self, graph_post):
        scheduled = self.due_post(self.create_post(image_url=""))

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["failed"], 1)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledPost.Status.FAILED)
        self.assertIn("no public image", scheduled.error_message)
        graph_post.assert_not_called()

    @patch("core.services.instagram_publishing.requests.post")
    def test_unlinked_instagram_post_is_blocked(self, graph_post):
        scheduled = self.due_post(self.create_post(), account=None)
        scheduled.social_account = None
        scheduled.save(update_fields=["social_account"])

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["blocked"], 1)
        scheduled.refresh_from_db()
        self.assertIn("not linked to an Instagram account", scheduled.error_message)
        graph_post.assert_not_called()

    @patch("core.services.instagram_publishing.time.sleep")
    @patch("core.services.instagram_publishing.requests.get")
    @patch("core.services.instagram_publishing.requests.post")
    def test_processing_containers_are_retried(
        self, graph_post, graph_get, _sleep
    ):
        graph_post.return_value = graph_response(200, {"id": "container-2"})
        graph_get.return_value = graph_response(
            200, {"status_code": "IN_PROGRESS"}
        )
        scheduled = self.due_post(self.create_post())

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["retried"], 1)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledPost.Status.PENDING)
        self.assertEqual(scheduled.attempts, 1)
        self.assertGreater(scheduled.scheduled_for, NOW)
        self.assertIn("still processing", scheduled.error_message)

    @patch("core.services.instagram_publishing.requests.post")
    def test_permanent_token_error_is_not_retried_and_redacts_the_token(
        self, graph_post
    ):
        graph_post.return_value = graph_response(
            400,
            {"error": {"code": 190, "message": f"Invalid token {TOKEN}"}},
        )
        scheduled = self.due_post(self.create_post())

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["failed"], 1)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledPost.Status.FAILED)
        self.assertEqual(scheduled.attempts, 1)
        self.assertNotIn(TOKEN, scheduled.error_message)
        self.assertIn("[redacted]", scheduled.error_message)

    def test_expired_token_requires_reconnect_without_network_calls(self):
        from django.utils import timezone

        self.account.token_expires_at = timezone.now() - timedelta(minutes=1)
        self.account.save(update_fields=["token_expires_at"])
        scheduled = self.due_post(self.create_post())

        with patch(
            "core.services.instagram_publishing.requests.post"
        ) as graph_post:
            counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["failed"], 1)
        graph_post.assert_not_called()
        scheduled.refresh_from_db()
        self.assertIn("expired", scheduled.error_message)

    def test_caption_is_capped_at_instagram_limits(self):
        post = ContentPost(
            body="x" * 3000,
        )

        caption = build_instagram_caption(post)

        self.assertLessEqual(len(caption), 2200)

    def test_caption_includes_at_most_30_hashtags(self):
        post = ContentPost(
            body="Short caption",
            hashtags=[f"tag{index}" for index in range(40)],
        )

        caption = build_instagram_caption(post)

        self.assertEqual(caption.count("#"), 30)


class InstagramSchedulingTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.client.force_authenticate(user=self.user)
        self.brand = Brand.objects.create(owner_id=self.user.id, name="Brand")
        self.post = ContentPost.objects.create(
            brand=self.brand,
            title="Caption",
            body="Hello",
            platform=ContentPost.Platform.INSTAGRAM,
            status=ContentPost.Status.APPROVED,
            image_url="https://cdn.example/post.jpg",
        )

    def schedule(self, **overrides):
        payload = {
            "post_id": str(self.post.id),
            "platforms": ["instagram"],
            "scheduled_for": "2030-01-15T09:30:00+00:00",
            "timezone_name": "UTC",
        }
        payload.update(overrides)
        return self.client.post(
            "/api/calendar/scheduled-posts/create/", payload, format="json"
        )

    def create_account(self, owner_id=None, account_id=IG_ID, name="IG"):
        return SocialAccount.objects.create(
            owner_id=owner_id or self.user.id,
            platform=SocialAccount.Platform.INSTAGRAM,
            platform_account_id=account_id,
            display_name=name,
            access_token_encrypted=encrypt_social_token(TOKEN),
        )

    @social_settings()
    def test_single_account_is_selected_automatically(self):
        account = self.create_account()

        response = self.schedule()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        scheduled = ScheduledPost.objects.get(post=self.post)
        self.assertEqual(scheduled.social_account_id, account.id)
        self.assertEqual(
            response.data[0]["social_account"]["display_name"], "IG"
        )

    @social_settings()
    def test_requires_a_connected_account(self):
        response = self.schedule()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data["code"], "instagram_account_not_connected"
        )

    @social_settings()
    def test_multiple_accounts_require_a_choice(self):
        self.create_account(account_id="111")
        second = self.create_account(account_id="222", name="Second")

        ambiguous = self.schedule()
        self.assertEqual(ambiguous.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(ambiguous.data["code"], "instagram_account_required")

        chosen = self.schedule(social_account_id=str(second.id))
        self.assertEqual(chosen.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            ScheduledPost.objects.get(post=self.post).social_account_id,
            second.id,
        )

    @social_settings()
    def test_requires_a_public_image_before_scheduling(self):
        self.create_account()
        self.post.image_url = ""
        self.post.save(update_fields=["image_url"])

        response = self.schedule()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "instagram_image_required")
        self.assertFalse(ScheduledPost.objects.filter(post=self.post).exists())

    @social_settings()
    def test_separate_accounts_can_be_selected_for_facebook_and_instagram(self):
        instagram_account = self.create_account()
        facebook_account = SocialAccount.objects.create(
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            platform_account_id="page-1",
            display_name="Page",
            access_token_encrypted=encrypt_social_token(TOKEN),
        )

        response = self.schedule(
            platforms=["facebook", "instagram"],
            social_account_ids={
                "facebook": str(facebook_account.id),
                "instagram": str(instagram_account.id),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        scheduled = {
            item.platform: item
            for item in ScheduledPost.objects.filter(post=self.post)
        }
        self.assertEqual(
            scheduled["facebook"].social_account_id, facebook_account.id
        )
        self.assertEqual(
            scheduled["instagram"].social_account_id, instagram_account.id
        )

    @social_settings()
    def test_cannot_schedule_to_another_users_account(self):
        foreign = self.create_account(owner_id=uuid4(), account_id="333")

        response = self.schedule(social_account_id=str(foreign.id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["code"], "instagram_account_not_found"
        )


@social_settings()
class ContentImageUploadTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.client.force_authenticate(user=self.user)
        self.brand = Brand.objects.create(owner_id=self.user.id, name="Brand")
        self.post = ContentPost.objects.create(
            brand=self.brand,
            title="Caption",
            body="Hello",
            platform=ContentPost.Platform.INSTAGRAM,
            status=ContentPost.Status.DRAFT,
        )

    def upload(self, content=JPEG_BYTES, content_type="image/jpeg", name="post.jpg"):
        return self.client.post(
            f"/api/content/posts/{self.post.id}/image/",
            {"image": SimpleUploadedFile(name, content, content_type=content_type)},
            format="multipart",
        )

    @patch("core.services.media_storage.requests.post")
    def test_upload_stores_a_public_url(self, storage_post):
        storage_post.return_value = graph_response(200, {"Key": "stored"})

        response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.post.refresh_from_db()
        self.assertTrue(
            self.post.image_url.startswith(
                "https://supabase.example.invalid/storage/v1/object/public/"
                "content-media/posts/"
            )
        )
        self.assertTrue(self.post.image_url.endswith(".jpg"))
        self.assertNotIn("service-role-test-key", str(response.data))
        url = storage_post.call_args.args[0]
        self.assertIn("/storage/v1/object/content-media/posts/", url)
        self.assertEqual(
            storage_post.call_args.kwargs["headers"]["Content-Type"],
            "image/jpeg",
        )

    @patch("core.services.media_storage.requests.post")
    def test_non_jpeg_uploads_are_rejected(self, storage_post):
        response = self.upload(content=b"\x89PNG\r\n", content_type="image/png")

        self.assertEqual(response.status_code, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
        storage_post.assert_not_called()

    @patch("core.services.media_storage.requests.post")
    def test_oversized_images_are_rejected(self, storage_post):
        response = self.upload(content=JPEG_BYTES + b"0" * (8 * 1024 * 1024))

        self.assertEqual(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        storage_post.assert_not_called()

    def test_upload_reports_missing_storage_configuration(self):
        with override_settings(SUPABASE_SERVICE_ROLE_KEY=""):
            response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("not configured", response.data["detail"])

    def test_upload_requires_an_explicitly_configured_bucket(self):
        with override_settings(SUPABASE_STORAGE_BUCKET=""):
            with patch("core.services.media_storage.requests.post") as storage_post:
                response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("SUPABASE_STORAGE_BUCKET", response.data["detail"])
        storage_post.assert_not_called()

    @patch("core.services.media_storage.requests.post")
    def test_other_owners_cannot_attach_images(self, storage_post):
        self.post.brand = Brand.objects.create(owner_id=uuid4(), name="Other")
        self.post.save(update_fields=["brand"])

        response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        storage_post.assert_not_called()
