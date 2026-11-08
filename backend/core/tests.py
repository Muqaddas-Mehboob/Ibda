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
from urllib.parse import parse_qs, urlsplit

import requests
import stripe
from django.db import IntegrityError
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import status
from rest_framework.test import APIRequestFactory, APITestCase
from cryptography.fernet import Fernet

from .apps import OAuthCallbackLogFilter
from .authentication import SupabaseAuthentication
from .models import (
    Approval,
    Brand,
    BrandVoice,
    ContentPost,
    Notification,
    PaymentTransaction,
    StripeCheckoutAttempt,
    UserSubscription,
    ProviderWebhookEvent,
    ScheduledPost,
    SocialAccount,
    SocialOAuthState,
    SupportRequest,
)
from .services import facebook_oauth
from .services.brand_deletion import BrandDeletionError
from .services.payments.catalog import (
    checkout_configuration_present,
    get_checkout_redirect_urls,
)
from .services.payments.webhooks import (
    StripeWebhookProcessingError,
    reprocess_stripe_event,
)
from .services.scheduling import publish_due_posts


class CheckoutRedirectConfigurationTests(SimpleTestCase):
    @override_settings(
        DEBUG=False,
        STRIPE_CHECKOUT_SUCCESS_URL_WEB=(
            "https://ibda.example/subscription/success"
        ),
        STRIPE_CHECKOUT_CANCEL_URL_WEB=(
            "https://ibda.example/subscription/cancel"
        ),
        STRIPE_CHECKOUT_SUCCESS_URL_MOBILE="ibda://subscription/success",
        STRIPE_CHECKOUT_CANCEL_URL_MOBILE="ibda://subscription/success",
    )
    def test_valid_web_and_mobile_return_routes_are_accepted(self):
        self.assertEqual(
            get_checkout_redirect_urls("web"),
            (
                "https://ibda.example/subscription/success",
                "https://ibda.example/subscription/cancel",
            ),
        )
        self.assertEqual(
            get_checkout_redirect_urls("mobile"),
            (
                "ibda://subscription/success",
                "ibda://subscription/success",
            ),
        )

    @override_settings(
        DEBUG=True,
        STRIPE_CHECKOUT_SUCCESS_URL_WEB=(
            "http://localhost:8081/subscription/success"
        ),
        STRIPE_CHECKOUT_CANCEL_URL_WEB=(
            "http://localhost:8081/subscription/cancel"
        ),
    )
    def test_local_http_urls_are_accepted_only_for_debug(self):
        self.assertIsNotNone(get_checkout_redirect_urls("web"))
        with override_settings(DEBUG=False):
            self.assertIsNone(get_checkout_redirect_urls("web"))

    def test_web_return_rejects_missing_or_invalid_values(self):
        invalid_urls = (
            ("", "https://ibda.example/subscription/cancel"),
            ("https://ibda.example/subscription/success", ""),
            ("/subscription/success", "https://ibda.example/subscription/cancel"),
            ("javascript:alert(1)", "https://ibda.example/subscription/cancel"),
            (
                "https://ibda.example/wrong-route",
                "https://ibda.example/subscription/cancel",
            ),
            (
                "https://user:password@ibda.example/subscription/success",
                "https://ibda.example/subscription/cancel",
            ),
        )
        for success_url, cancel_url in invalid_urls:
            with self.subTest(success_url=success_url, cancel_url=cancel_url):
                with override_settings(
                    DEBUG=False,
                    STRIPE_CHECKOUT_SUCCESS_URL_WEB=success_url,
                    STRIPE_CHECKOUT_CANCEL_URL_WEB=cancel_url,
                ):
                    self.assertIsNone(get_checkout_redirect_urls("web"))

    def test_mobile_return_rejects_missing_or_non_expo_route_values(self):
        invalid_urls = (
            ("", "ibda://subscription/success"),
            ("ibda://subscription/success", ""),
            ("https://ibda.example/subscription/success",
             "ibda://subscription/success"),
            ("ibda://subscription", "ibda://subscription/success"),
            ("ibda://subscription/success", "ibda://subscription/cancel"),
        )
        for success_url, cancel_url in invalid_urls:
            with self.subTest(success_url=success_url, cancel_url=cancel_url):
                with override_settings(
                    STRIPE_CHECKOUT_SUCCESS_URL_MOBILE=success_url,
                    STRIPE_CHECKOUT_CANCEL_URL_MOBILE=cancel_url,
                ):
                    self.assertIsNone(get_checkout_redirect_urls("mobile"))

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_unit_test",
        STRIPE_WEBHOOK_SECRET="whsec_unit_test",
        STRIPE_CHECKOUT_SUCCESS_URL_WEB=(
            "https://ibda.example/subscription/success"
        ),
        STRIPE_CHECKOUT_CANCEL_URL_WEB=(
            "https://ibda.example/subscription/cancel"
        ),
        STRIPE_CHECKOUT_SUCCESS_URL_MOBILE="",
        STRIPE_CHECKOUT_CANCEL_URL_MOBILE="",
        STRIPE_PRICE_STARTER_MONTHLY="price_server_starter_monthly",
    )
    def test_readiness_accepts_any_complete_platform_pair_with_test_key_and_price(
        self,
    ):
        self.assertTrue(checkout_configuration_present())

    @override_settings(
        STRIPE_SECRET_KEY="sk_live_unit_test",
        STRIPE_WEBHOOK_SECRET="whsec_unit_test",
        STRIPE_CHECKOUT_SUCCESS_URL_WEB=(
            "https://ibda.example/subscription/success"
        ),
        STRIPE_CHECKOUT_CANCEL_URL_WEB=(
            "https://ibda.example/subscription/cancel"
        ),
        STRIPE_PRICE_STARTER_MONTHLY="price_server_starter_monthly",
    )
    def test_readiness_rejects_live_mode_key(self):
        self.assertFalse(checkout_configuration_present())

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_unit_test",
        STRIPE_WEBHOOK_SECRET="whsec_unit_test",
        STRIPE_CHECKOUT_SUCCESS_URL_WEB=(
            "https://ibda.example/subscription/success"
        ),
        STRIPE_CHECKOUT_CANCEL_URL_WEB=(
            "https://ibda.example/subscription/cancel"
        ),
        STRIPE_PRICE_STARTER_MONTHLY="price_server_starter_monthly",
    )
    def test_readiness_rejects_missing_webhook_secret(self):
        with override_settings(STRIPE_WEBHOOK_SECRET=""):
            self.assertFalse(checkout_configuration_present())

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_unit_test",
        STRIPE_WEBHOOK_SECRET="whsec_unit_test",
        STRIPE_CHECKOUT_SUCCESS_URL_WEB=(
            "https://ibda.example/subscription/success"
        ),
        STRIPE_CHECKOUT_CANCEL_URL_WEB=(
            "https://ibda.example/subscription/cancel"
        ),
    )
    def test_readiness_rejects_missing_price_ids(self):
        with override_settings(
            STRIPE_PRICE_STARTER_MONTHLY="",
            STRIPE_PRICE_STARTER_ANNUAL="",
            STRIPE_PRICE_PRO_MONTHLY="",
            STRIPE_PRICE_PRO_ANNUAL="",
            STRIPE_PRICE_ENTERPRISE_MONTHLY="",
            STRIPE_PRICE_ENTERPRISE_ANNUAL="",
        ):
            self.assertFalse(checkout_configuration_present())

    def test_unknown_platform_is_rejected(self):
        self.assertIsNone(get_checkout_redirect_urls("other"))


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


class BrandDeletionApiTests(APITestCase):
    list_path = "/api/brands/"

    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.other_user_id = uuid4()
        self.client.force_authenticate(user=self.user)

    def create_brand_records(self, owner_id, name):
        brand = Brand.objects.create(owner_id=owner_id, name=name)
        voice = BrandVoice.objects.create(brand=brand, tone="Bold")
        post = ContentPost.objects.create(
            brand=brand,
            title=f"{name} post",
            body="Brand deletion test body",
        )
        approval = Approval.objects.create(post=post)
        scheduled = ScheduledPost.objects.create(
            post=post,
            platform=ContentPost.Platform.INSTAGRAM,
            scheduled_for=(
                datetime.now(datetime_timezone.utc) + timedelta(days=1)
            ),
        )
        notification = Notification.objects.create(
            recipient_user_id=owner_id,
            notification_type=Notification.Type.APPROVAL_APPROVED,
            title=f"{name} update",
            message="Brand-specific notification",
            related_object_id=approval.id,
            event_key=f"brand-deletion-{uuid4()}",
        )
        # Creating a scheduled post also notifies the owner through a signal.
        schedule_notification = Notification.objects.get(
            related_object_id=scheduled.id
        )
        return {
            "brand": brand,
            "voice": voice,
            "post": post,
            "approval": approval,
            "scheduled": scheduled,
            "notification": notification,
            "schedule_notification": schedule_notification,
        }

    def assert_records_deleted(self, records):
        self.assertFalse(Brand.objects.filter(id=records["brand"].id).exists())
        self.assertFalse(BrandVoice.objects.filter(id=records["voice"].id).exists())
        self.assertFalse(ContentPost.objects.filter(id=records["post"].id).exists())
        self.assertFalse(
            Approval.objects.filter(id=records["approval"].id).exists()
        )
        self.assertFalse(
            ScheduledPost.objects.filter(id=records["scheduled"].id).exists()
        )
        self.assertFalse(
            Notification.objects.filter(
                id=records["notification"].id
            ).exists()
        )
        self.assertFalse(
            Notification.objects.filter(
                id=records["schedule_notification"].id
            ).exists()
        )

    def test_bulk_delete_removes_all_own_brands_and_brand_records(self):
        first = self.create_brand_records(self.user.id, "First brand")
        second = self.create_brand_records(self.user.id, "Second brand")
        foreign = self.create_brand_records(
            self.other_user_id,
            "Foreign brand",
        )

        response = self.client.delete(self.list_path)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted"], 2)
        self.assertEqual(response.data["counts"]["brands"], 2)
        self.assertEqual(response.data["counts"]["brand_voices"], 2)
        self.assertEqual(response.data["counts"]["content_posts"], 2)
        self.assertEqual(response.data["counts"]["approvals"], 2)
        self.assertEqual(response.data["counts"]["scheduled_posts"], 2)
        self.assertEqual(response.data["counts"]["notifications"], 4)

        self.assert_records_deleted(first)
        self.assert_records_deleted(second)

        # Another owner's brand and its records are untouched.
        self.assertTrue(
            Brand.objects.filter(id=foreign["brand"].id).exists()
        )
        self.assertTrue(
            BrandVoice.objects.filter(id=foreign["voice"].id).exists()
        )
        self.assertTrue(
            ContentPost.objects.filter(id=foreign["post"].id).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                id=foreign["notification"].id
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                id=foreign["schedule_notification"].id
            ).exists()
        )

    def test_bulk_delete_is_safe_when_repeated(self):
        brand = self.create_brand_records(self.user.id, "Own brand")

        first_response = self.client.delete(self.list_path)
        second_response = self.client.delete(self.list_path)

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data["deleted"], 1)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.data["deleted"], 0)
        self.assert_records_deleted(brand)

    def test_bulk_delete_without_brands_returns_zero(self):
        response = self.client.delete(self.list_path)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted"], 0)
        self.assertFalse(Brand.objects.filter(owner_id=self.user.id).exists())

    def test_single_delete_removes_only_the_selected_brand(self):
        selected = self.create_brand_records(self.user.id, "Selected brand")
        kept = self.create_brand_records(self.user.id, "Kept brand")

        response = self.client.delete(
            f"/api/brands/{selected['brand'].id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted"], 1)
        self.assert_records_deleted(selected)

        self.assertTrue(Brand.objects.filter(id=kept["brand"].id).exists())
        self.assertTrue(BrandVoice.objects.filter(id=kept["voice"].id).exists())
        self.assertTrue(ContentPost.objects.filter(id=kept["post"].id).exists())
        self.assertTrue(
            Notification.objects.filter(id=kept["notification"].id).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                id=kept["schedule_notification"].id
            ).exists()
        )

    def test_single_delete_accepts_string_supabase_user_id(self):
        self.user.id = str(self.user.id)
        selected = self.create_brand_records(self.user.id, "Selected brand")

        voice_response = self.client.get(
            f"/api/brands/{selected['brand'].id}/voice/"
        )
        delete_response = self.client.delete(
            f"/api/brands/{selected['brand'].id}/"
        )

        self.assertEqual(voice_response.status_code, status.HTTP_200_OK)
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(delete_response.data["deleted"], 1)
        self.assert_records_deleted(selected)

    def test_single_delete_rejects_another_users_brand(self):
        foreign = self.create_brand_records(
            self.other_user_id,
            "Foreign brand",
        )

        response = self.client.delete(
            f"/api/brands/{foreign['brand'].id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Brand.objects.filter(id=foreign["brand"].id).exists())
        self.assertTrue(
            BrandVoice.objects.filter(id=foreign["voice"].id).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                id=foreign["notification"].id
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                id=foreign["schedule_notification"].id
            ).exists()
        )

    def test_repeated_single_delete_is_safe(self):
        brand = self.create_brand_records(self.user.id, "Own brand")
        path = f"/api/brands/{brand['brand'].id}/"

        first_response = self.client.delete(path)
        second_response = self.client.delete(path)

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data["deleted"], 1)
        self.assertEqual(second_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assert_records_deleted(brand)

    @patch(
        "core.views.delete_brands",
        side_effect=BrandDeletionError("Deletion failed safely."),
    )
    def test_database_failure_returns_error_and_keeps_brand(self, _delete):
        brand = self.create_brand_records(self.user.id, "Own brand")

        response = self.client.delete(
            f"/api/brands/{brand['brand'].id}/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        self.assertEqual(response.data["detail"], "Deletion failed safely.")
        self.assertTrue(Brand.objects.filter(id=brand["brand"].id).exists())
        self.assertTrue(
            BrandVoice.objects.filter(id=brand["voice"].id).exists()
        )


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


class SchedulingWorkflowApiTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.client.force_authenticate(user=self.user)
        self.brand = Brand.objects.create(owner_id=self.user.id, name="Scheduling")
        SocialAccount.objects.create(
            owner_id=self.user.id,
            platform=SocialAccount.Platform.INSTAGRAM,
            platform_account_id="instagram-account",
            display_name="Instagram",
        )

    def create_post(self, status_value=ContentPost.Status.APPROVED, owner_id=None):
        brand = self.brand
        if owner_id is not None:
            brand = Brand.objects.create(owner_id=owner_id, name="Other brand")
        return ContentPost.objects.create(
            brand=brand,
            title="Launch post",
            body="Body copy",
            platform=ContentPost.Platform.INSTAGRAM,
            status=status_value,
            image_url="https://cdn.example/post.jpg",
        )

    def schedule(self, post, scheduled_for="2030-01-15T09:30:00+05:00"):
        return self.client.post(
            "/api/calendar/scheduled-posts/create/",
            {
                "post_id": str(post.id),
                "platforms": ["instagram"],
                "scheduled_for": scheduled_for,
                "timezone_name": "Asia/Karachi",
            },
            format="json",
        )

    def test_scheduling_requires_approved_content(self):
        post = self.create_post(status_value=ContentPost.Status.DRAFT)

        response = self.schedule(post)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "approval_required")
        self.assertFalse(ScheduledPost.objects.filter(post=post).exists())

    def test_schedule_stores_utc_time_and_keeps_user_timezone(self):
        post = self.create_post()

        response = self.schedule(post)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        scheduled = ScheduledPost.objects.get(post=post)
        self.assertEqual(
            scheduled.scheduled_for,
            datetime(2030, 1, 15, 4, 30, tzinfo=datetime_timezone.utc),
        )
        self.assertEqual(scheduled.timezone_name, "Asia/Karachi")
        self.assertEqual(scheduled.status, ScheduledPost.Status.PENDING)
        post.refresh_from_db()
        self.assertEqual(post.status, ContentPost.Status.SCHEDULED)

    def test_schedule_cannot_target_another_users_content(self):
        post = self.create_post(owner_id=uuid4())

        response = self.schedule(post)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(ScheduledPost.objects.filter(post=post).exists())

    def test_duplicate_active_schedule_is_rejected(self):
        post = self.create_post()
        self.assertEqual(self.schedule(post).status_code, status.HTTP_201_CREATED)

        response = self.schedule(post, "2030-01-16T09:30:00+05:00")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "already_scheduled")
        self.assertEqual(ScheduledPost.objects.filter(post=post).count(), 1)

    def test_reschedule_then_cancel_restores_post_to_approved(self):
        post = self.create_post()
        self.schedule(post)
        scheduled = ScheduledPost.objects.get(post=post)

        rescheduled = self.client.patch(
            f"/api/calendar/scheduled-posts/{scheduled.id}/",
            {"scheduled_for": "2030-02-01T12:00:00+05:00"},
            format="json",
        )
        self.assertEqual(rescheduled.status_code, status.HTTP_200_OK)
        self.assertEqual(
            rescheduled.data["scheduled_for"],
            "2030-02-01T07:00:00Z",
        )

        cancelled = self.client.delete(
            f"/api/calendar/scheduled-posts/{scheduled.id}/"
        )
        self.assertEqual(cancelled.status_code, status.HTTP_200_OK)
        self.assertEqual(cancelled.data["status"], ScheduledPost.Status.CANCELLED)
        post.refresh_from_db()
        self.assertEqual(post.status, ContentPost.Status.APPROVED)

    def test_failed_schedule_can_be_rescheduled_without_a_retry_budget(self):
        post = self.create_post()
        self.schedule(post)
        scheduled = ScheduledPost.objects.get(post=post)
        scheduled.status = ScheduledPost.Status.FAILED
        scheduled.attempts = 3
        scheduled.error_message = "Publishing failed."
        scheduled.save(update_fields=["status", "attempts", "error_message"])

        response = self.client.patch(
            f"/api/calendar/scheduled-posts/{scheduled.id}/",
            {"scheduled_for": "2030-02-01T12:00:00+05:00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], ScheduledPost.Status.PENDING)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledPost.Status.PENDING)
        self.assertEqual(scheduled.attempts, 0)
        self.assertEqual(scheduled.error_message, "")

    def test_failed_schedule_can_be_cancelled_and_restores_the_post(self):
        post = self.create_post()
        self.schedule(post)
        scheduled = ScheduledPost.objects.get(post=post)
        scheduled.status = ScheduledPost.Status.FAILED
        scheduled.error_message = "Publishing failed."
        scheduled.save(update_fields=["status", "error_message"])

        response = self.client.delete(
            f"/api/calendar/scheduled-posts/{scheduled.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], ScheduledPost.Status.CANCELLED)
        post.refresh_from_db()
        self.assertEqual(post.status, ContentPost.Status.APPROVED)

    def test_due_post_is_blocked_not_published_without_an_integration(self):
        post = self.create_post()
        scheduled = ScheduledPost.objects.create(
            post=post,
            platform=ContentPost.Platform.INSTAGRAM,
            scheduled_for=datetime(2030, 1, 15, tzinfo=datetime_timezone.utc),
            timezone_name="Asia/Karachi",
        )
        post.status = ContentPost.Status.SCHEDULED
        post.save(update_fields=["status"])

        counts = publish_due_posts(
            now=datetime(2030, 1, 16, tzinfo=datetime_timezone.utc)
        )

        self.assertEqual(counts["blocked"], 1)
        self.assertEqual(counts["published"], 0)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledPost.Status.BLOCKED)
        self.assertEqual(scheduled.attempts, 1)
        self.assertIsNone(scheduled.published_at)
        self.assertIn(
            "Instagram publishing is not configured",
            scheduled.error_message,
        )
        post.refresh_from_db()
        self.assertEqual(post.status, ContentPost.Status.SCHEDULED)
        self.assertTrue(
            Notification.objects.filter(
                related_object_id=scheduled.id,
                notification_type=Notification.Type.POST_PUBLISH_BLOCKED,
            ).exists()
        )


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


class SupportRequestApiTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(
            id=uuid4(),
            email="account@example.com",
            is_authenticated=True,
        )
        self.client.force_authenticate(user=self.user)

    def test_submits_support_request_and_uses_account_email_by_default(self):
        response = self.client.post(
            "/api/support/requests/",
            {
                "subject": "Unable to schedule a post",
                "message": "The calendar does not save my schedule.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        support_request = SupportRequest.objects.get(id=response.data["id"])
        self.assertEqual(support_request.owner_id, self.user.id)
        self.assertEqual(support_request.contact_email, self.user.email)
        self.assertEqual(support_request.subject, "Unable to schedule a post")
        self.assertEqual(
            support_request.message,
            "The calendar does not save my schedule.",
        )
        self.assertEqual(support_request.status, SupportRequest.Status.NEW)
        self.assertEqual(response.data["status"], SupportRequest.Status.NEW)

    def test_submitted_contact_email_is_saved(self):
        response = self.client.post(
            "/api/support/requests/",
            {
                "contact_email": "reply@example.com",
                "subject": "Billing question",
                "message": "Please help me understand my plan.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        support_request = SupportRequest.objects.get(id=response.data["id"])
        self.assertEqual(support_request.contact_email, "reply@example.com")

    def test_invalid_or_empty_requests_are_rejected_without_storage(self):
        for payload in (
            {"subject": "  ", "message": "A message"},
            {"subject": "A subject", "message": "  "},
            {
                "contact_email": "not-an-email",
                "subject": "A subject",
                "message": "A message",
            },
        ):
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/support/requests/",
                    payload,
                    format="json",
                )
                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
        self.assertEqual(SupportRequest.objects.count(), 0)

    def test_support_request_endpoint_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/support/requests/",
            {"subject": "A subject", "message": "A message"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(SupportRequest.objects.count(), 0)


class SocialAccountApiTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.other_user_id = uuid4()
        self.client.force_authenticate(user=self.user)

    def test_django_server_log_filter_redacts_oauth_callback_query(self):
        import logging

        record = logging.LogRecord(
            "django.server",
            logging.INFO,
            __file__,
            1,
            '"GET /api/social/oauth/facebook_pages/callback/'
            '?code=private-code&state=private-state HTTP/1.1" 302',
            (),
            None,
        )

        self.assertTrue(OAuthCallbackLogFilter().filter(record))
        redacted_message = record.getMessage()
        self.assertIn(
            "/api/social/oauth/facebook_pages/callback/?[redacted]",
            redacted_message,
        )
        self.assertNotIn("private-code", redacted_message)
        self.assertNotIn("private-state", redacted_message)

    def create_account(self, owner_id, platform_id):
        return SocialAccount.objects.create(
            owner_id=owner_id,
            platform=SocialAccount.Platform.LINKEDIN,
            platform_account_id=platform_id,
            display_name="Ibda Page",
            access_token_encrypted="encrypted-access-token",
            refresh_token_encrypted="encrypted-refresh-token",
        )

    def facebook_token_response(self, token, expires_in=None):
        payload = {"access_token": token}
        if expires_in is not None:
            payload["expires_in"] = expires_in
        return SimpleNamespace(status_code=200, json=lambda: payload)

    def facebook_debug_response(
        self,
        *,
        expires_at=0,
        data_access_expires_at=0,
        **overrides
    ):
        data = {
            "app_id": "test-app-id",
            "type": "PAGE",
            "is_valid": True,
            "expires_at": expires_at,
            "data_access_expires_at": data_access_expires_at,
        }
        data.update(overrides)
        return SimpleNamespace(status_code=200, json=lambda: {"data": data})

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_callback_saves_encrypted_owner_scoped_page_tokens(
        self,
        mock_post,
        mock_get,
    ):
        state = "valid-facebook-state"
        state_hash = hashlib.sha256(state.encode("ascii")).hexdigest()
        SocialOAuthState.objects.create(
            state_digest=state_hash,
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        foreign_page = SocialAccount.objects.create(
            owner_id=self.other_user_id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            platform_account_id="page-1",
            display_name="Other user's page",
            access_token_encrypted="foreign-encrypted-token",
        )
        page_one_expires_at = int(time.time()) + 3600
        page_two_data_access_expires_at = int(time.time()) + 90 * 24 * 3600
        mock_post.return_value = self.facebook_token_response(
            "long-lived-user-token",
            expires_in=5184000,
        )
        mock_get.side_effect = [
            self.facebook_token_response("short-lived-user-token"),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": "page-1",
                            "name": "Customer page",
                            "access_token": "customer-page-token",
                        },
                        {
                            "id": "page-2",
                            "name": "Second page",
                            "access_token": "second-page-token",
                        },
                    ]
                },
            ),
            self.facebook_debug_response(
                expires_at=page_one_expires_at,
                profile_id="page-1",
            ),
            self.facebook_debug_response(
                data_access_expires_at=page_two_data_access_expires_at,
                profile_id="page-2",
            ),
        ]

        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": state, "code": "one-time-authorization-code"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=connected",
        )
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertNotIn("one-time-authorization-code", response["Location"])
        self.assertNotIn("customer-page-token", response["Location"])

        mock_post.assert_called_once()
        self.assertEqual(
            mock_post.call_args.args[0],
            "https://graph.facebook.com/v27.0/oauth/access_token",
        )
        self.assertNotIn("?", mock_post.call_args.args[0])
        self.assertEqual(
            mock_post.call_args.kwargs["data"]["grant_type"],
            "fb_exchange_token",
        )
        self.assertEqual(
            mock_post.call_args.kwargs["data"]["fb_exchange_token"],
            "short-lived-user-token",
        )
        self.assertEqual(
            mock_post.call_args.kwargs["data"]["client_id"],
            "test-app-id",
        )

        self.assertEqual(mock_get.call_count, 4)
        accounts_call = mock_get.call_args_list[1]
        self.assertEqual(
            accounts_call.args[0],
            "https://graph.facebook.com/v27.0/me/accounts",
        )
        self.assertEqual(
            accounts_call.kwargs["headers"]["Authorization"],
            "Bearer long-lived-user-token",
        )
        for call in mock_get.call_args_list:
            self.assertNotEqual(
                call.kwargs.get("headers", {}).get("Authorization"),
                "Bearer short-lived-user-token",
            )

        from core.services.social_tokens import decrypt_social_token

        connected_pages = SocialAccount.objects.filter(
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
        ).order_by("platform_account_id")
        self.assertEqual(connected_pages.count(), 2)
        page_one = connected_pages.get(platform_account_id="page-1")
        page_two = connected_pages.get(platform_account_id="page-2")
        self.assertEqual(
            decrypt_social_token(page_one.access_token_encrypted),
            "customer-page-token",
        )
        self.assertEqual(page_one.display_name, "Customer page")
        self.assertEqual(page_one.scopes, ["pages_show_list"])
        self.assertEqual(
            page_one.token_expires_at,
            datetime.fromtimestamp(page_one_expires_at, tz=datetime_timezone.utc),
        )
        self.assertEqual(
            page_two.token_expires_at,
            datetime.fromtimestamp(
                page_two_data_access_expires_at,
                tz=datetime_timezone.utc,
            ),
        )

        debug_call = mock_get.call_args_list[2]
        self.assertEqual(
            debug_call.args[0],
            "https://graph.facebook.com/v27.0/debug_token",
        )
        self.assertEqual(
            debug_call.kwargs["params"]["input_token"],
            "customer-page-token",
        )
        self.assertEqual(
            mock_get.call_args_list[3].kwargs["params"]["input_token"],
            "second-page-token",
        )

        self.assertEqual(
            SocialAccount.objects.get(id=foreign_page.id).display_name,
            "Other user's page",
        )
        self.assertNotEqual(
            SocialAccount.objects.get(id=foreign_page.id).access_token_encrypted,
            page_one.access_token_encrypted,
        )
        self.assertTrue(
            SocialOAuthState.objects.get(state_digest=state_hash).consumed_at
        )

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_callback_handles_pagination_and_no_pages(
        self,
        mock_post,
        mock_get,
    ):
        state = "empty-pages-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        mock_post.return_value = self.facebook_token_response(
            "long-lived-user-token",
            expires_in=5184000,
        )
        mock_get.side_effect = [
            self.facebook_token_response("short-lived-user-token"),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [],
                    "paging": {
                        "next": "https://graph.facebook.com/untrusted-url",
                        "cursors": {"after": "next-cursor"},
                    },
                },
            ),
            SimpleNamespace(
                status_code=200,
                json=lambda: {"data": []},
            ),
        ]

        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": state, "code": "one-time-authorization-code"},
        )

        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=no_pages",
        )
        self.assertFalse(SocialAccount.objects.exists())
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(
            mock_get.call_args_list[2].kwargs["params"]["after"],
            "next-cursor",
        )
        self.assertEqual(
            mock_get.call_args_list[2].args[0],
            "https://graph.facebook.com/v27.0/me/accounts",
        )

    def test_facebook_callback_rejects_missing_expired_wrong_platform_and_replayed_state(
        self,
    ):
        expired_state = "expired-state"
        wrong_platform_state = "wrong-platform-state"
        valid_state = "single-use-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(expired_state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(
                wrong_platform_state.encode("ascii")
            ).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.INSTAGRAM,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(valid_state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        for invalid_state in ("", "unknown-state", expired_state, wrong_platform_state):
            with self.subTest(state=invalid_state):
                response = self.client.get(
                    "/api/social/oauth/facebook_pages/callback/",
                    {"state": invalid_state, "code": "untrusted-code"},
                )
                self.assertEqual(
                    response["Location"],
                    "ibda://social-accounts?status=failed",
                )
        self.assertIsNone(
            SocialOAuthState.objects.get(
                state_digest=hashlib.sha256(
                    wrong_platform_state.encode("ascii")
                ).hexdigest()
            ).consumed_at
        )

        first_response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": valid_state, "error": "access_denied"},
        )
        replay_response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": valid_state, "code": "untrusted-code"},
        )
        self.assertEqual(
            first_response["Location"],
            "ibda://social-accounts?status=cancelled",
        )
        self.assertEqual(
            replay_response["Location"],
            "ibda://social-accounts?status=failed",
        )
        self.assertFalse(SocialAccount.objects.exists())

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    def test_facebook_callback_meta_failures_do_not_leak_codes_or_tokens(
        self,
        mock_get,
    ):
        state = "failed-meta-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        mock_get.return_value = SimpleNamespace(
            status_code=400,
            json=lambda: {
                "error": {
                    "message": "Sensitive provider error text",
                    "access_token": "must-not-leak",
                }
            },
        )

        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": state, "code": "private-authorization-code"},
        )

        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=failed",
        )
        self.assertNotIn("private-authorization-code", response["Location"])
        self.assertNotIn("must-not-leak", response["Location"])
        self.assertNotIn("Sensitive provider error text", response["Location"])
        self.assertFalse(SocialAccount.objects.exists())

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_callback_handles_non_expiring_page_token(
        self,
        mock_post,
        mock_get,
    ):
        state = "non-expiring-page-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        mock_post.return_value = self.facebook_token_response(
            "long-lived-user-token",
            expires_in=5184000,
        )
        mock_get.side_effect = [
            self.facebook_token_response("short-lived-user-token"),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": "page-1",
                            "name": "Never expiring",
                            "access_token": "page-token",
                        }
                    ]
                },
            ),
            self.facebook_debug_response(
                expires_at=0,
                data_access_expires_at=0,
                profile_id="page-1",
            ),
        ]

        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": state, "code": "one-time-authorization-code"},
        )

        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=connected",
        )
        account = SocialAccount.objects.get(
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
        )
        self.assertEqual(account.status, SocialAccount.Status.CONNECTED)
        self.assertIsNone(account.token_expires_at)

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_callback_fails_when_long_lived_exchange_fails(
        self,
        mock_post,
        mock_get,
    ):
        cases = (
            (
                "http-error",
                SimpleNamespace(
                    status_code=400,
                    json=lambda: {"error": {"message": "denied"}},
                ),
            ),
            (
                "missing-token",
                SimpleNamespace(
                    status_code=200,
                    json=lambda: {"expires_in": 5184000},
                ),
            ),
        )
        for label, post_response in cases:
            with self.subTest(response=label):
                mock_get.reset_mock()
                mock_post.reset_mock()
                mock_get.return_value = self.facebook_token_response(
                    "short-lived-user-token"
                )
                mock_post.return_value = post_response
                state = "long-lived-failure-" + label
                SocialOAuthState.objects.create(
                    state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
                    owner_id=self.user.id,
                    platform=SocialAccount.Platform.FACEBOOK_PAGES,
                    expires_at=timezone.now() + timedelta(minutes=5),
                )

                response = self.client.get(
                    "/api/social/oauth/facebook_pages/callback/",
                    {"state": state, "code": "one-time-authorization-code"},
                )

                self.assertEqual(
                    response["Location"],
                    "ibda://social-accounts?status=failed",
                )
                self.assertFalse(SocialAccount.objects.exists())
                self.assertEqual(mock_get.call_count, 1)
                self.assertEqual(mock_post.call_count, 1)

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_callback_fails_when_token_debug_is_invalid(
        self,
        mock_post,
        mock_get,
    ):
        state = "invalid-debug-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        mock_post.return_value = self.facebook_token_response(
            "long-lived-user-token",
            expires_in=5184000,
        )
        mock_get.side_effect = [
            self.facebook_token_response("short-lived-user-token"),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": "page-1",
                            "name": "Valid page",
                            "access_token": "valid-page-token",
                        },
                        {
                            "id": "page-2",
                            "name": "Invalid page",
                            "access_token": "invalid-page-token",
                        },
                    ]
                },
            ),
            self.facebook_debug_response(
                expires_at=int(time.time()) + 3600,
                profile_id="page-1",
            ),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": {
                        "app_id": "test-app-id",
                        "type": "PAGE",
                        "is_valid": False,
                        "expires_at": int(time.time()) + 3600,
                        "data_access_expires_at": 0,
                    }
                },
            ),
        ]

        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": state, "code": "one-time-authorization-code"},
        )

        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=failed",
        )
        # The first Page validated correctly, but nothing may be saved.
        self.assertFalse(SocialAccount.objects.exists())

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_callback_fails_when_token_debug_expiry_is_missing(
        self,
        mock_post,
        mock_get,
    ):
        cases = (
            (
                "missing-expires-at",
                {
                    "app_id": "test-app-id",
                    "type": "PAGE",
                    "is_valid": True,
                    "data_access_expires_at": 0,
                },
            ),
            (
                "unknown-data-access",
                {
                    "app_id": "test-app-id",
                    "type": "PAGE",
                    "is_valid": True,
                    "expires_at": 0,
                },
            ),
        )
        for label, debug_data in cases:
            with self.subTest(response=label):
                mock_get.reset_mock()
                mock_post.reset_mock()
                mock_post.return_value = self.facebook_token_response(
                    "long-lived-user-token",
                    expires_in=5184000,
                )
                mock_get.side_effect = [
                    self.facebook_token_response("short-lived-user-token"),
                    SimpleNamespace(
                        status_code=200,
                        json=lambda: {
                            "data": [
                                {
                                    "id": "page-1",
                                    "name": "Unverified page",
                                    "access_token": "page-token",
                                }
                            ]
                        },
                    ),
                    SimpleNamespace(
                        status_code=200,
                        json=lambda: {"data": debug_data},
                    ),
                ]
                state = "missing-expiry-" + label
                SocialOAuthState.objects.create(
                    state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
                    owner_id=self.user.id,
                    platform=SocialAccount.Platform.FACEBOOK_PAGES,
                    expires_at=timezone.now() + timedelta(minutes=5),
                )

                response = self.client.get(
                    "/api/social/oauth/facebook_pages/callback/",
                    {"state": state, "code": "one-time-authorization-code"},
                )

                self.assertEqual(
                    response["Location"],
                    "ibda://social-accounts?status=failed",
                )
                self.assertFalse(SocialAccount.objects.exists())


    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    def test_facebook_code_exchange_keeps_documented_get_parameters(
        self,
        mock_get,
    ):
        mock_get.return_value = self.facebook_token_response(
            "short-lived-user-token"
        )

        token = facebook_oauth._exchange_code("one-time-authorization-code")

        self.assertEqual(token, "short-lived-user-token")
        mock_get.assert_called_once()
        self.assertEqual(
            mock_get.call_args.args[0],
            "https://graph.facebook.com/v27.0/oauth/access_token",
        )
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["client_id"], "test-app-id")
        self.assertEqual(
            params["redirect_uri"],
            "https://social.example/api/social/oauth/facebook_pages/callback/",
        )
        self.assertEqual(params["code"], "one-time-authorization-code")
        # Meta requires the app secret on this documented GET request.
        self.assertIn("client_secret", params)
        self.assertEqual(mock_get.call_args.kwargs["timeout"], (5, 20))
        self.assertFalse(mock_get.call_args.kwargs["allow_redirects"])

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    def test_facebook_code_exchange_failure_does_not_expose_request_url(
        self,
        mock_get,
    ):
        mock_get.side_effect = requests.ConnectionError(
            "https://graph.facebook.com/v27.0/oauth/access_token"
            "?client_id=test-app-id&client_secret=test-app-secret"
            "&code=private-authorization-code"
        )

        with self.assertRaisesMessage(
            facebook_oauth.FacebookOAuthError,
            "Unable to exchange the Facebook authorization.",
        ) as raised:
            facebook_oauth._exchange_code("private-authorization-code")

        error = raised.exception
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        message = str(error)
        self.assertNotIn("test-app-secret", message)
        self.assertNotIn("private-authorization-code", message)
        self.assertNotIn("graph.facebook.com", message)

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_callback_skips_malformed_pages_and_keeps_valid_ones(
        self,
        mock_post,
        mock_get,
    ):
        state = "mixed-pages-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        mock_post.return_value = self.facebook_token_response(
            "long-lived-user-token",
            expires_in=5184000,
        )
        mock_get.side_effect = [
            self.facebook_token_response("short-lived-user-token"),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": "page-1",
                            "name": "Valid page",
                            "access_token": "valid-page-token",
                        },
                        {"id": "page-2", "name": "Missing token"},
                        {"name": "Missing id", "access_token": "orphan-token"},
                        {"id": "page-3", "access_token": "nameless-token"},
                        "not-a-page",
                        {
                            "id": "page-4",
                            "name": "   ",
                            "access_token": "blank-name-token",
                        },
                        {
                            "id": "page-5",
                            "name": "Second valid page",
                            "access_token": "second-valid-token",
                        },
                    ]
                },
            ),
            self.facebook_debug_response(
                expires_at=int(time.time()) + 3600,
                profile_id="page-1",
            ),
            self.facebook_debug_response(
                expires_at=int(time.time()) + 7200,
                profile_id="page-5",
            ),
        ]

        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": state, "code": "one-time-authorization-code"},
        )

        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=connected",
        )
        self.assertEqual(mock_get.call_count, 4)
        self.assertEqual(mock_post.call_count, 1)
        debug_tokens = [
            call.kwargs["params"]["input_token"]
            for call in mock_get.call_args_list[2:]
        ]
        self.assertEqual(debug_tokens, ["valid-page-token", "second-valid-token"])

        accounts = SocialAccount.objects.filter(owner_id=self.user.id)
        self.assertEqual(
            sorted(
                accounts.values_list("platform_account_id", flat=True)
            ),
            ["page-1", "page-5"],
        )
        for account in accounts:
            self.assertTrue(account.display_name.strip())
            self.assertTrue(account.access_token_encrypted)
            self.assertNotIn(
                account.access_token_encrypted,
                {"valid-page-token", "second-valid-token"},
            )

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_callback_returns_no_pages_when_all_entries_are_malformed(
        self,
        mock_post,
        mock_get,
    ):
        state = "malformed-pages-state"
        state_hash = hashlib.sha256(state.encode("ascii")).hexdigest()
        SocialOAuthState.objects.create(
            state_digest=state_hash,
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        mock_post.return_value = self.facebook_token_response(
            "long-lived-user-token",
            expires_in=5184000,
        )
        mock_get.side_effect = [
            self.facebook_token_response("short-lived-user-token"),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {"id": "page-1"},
                        {"name": "Missing id", "access_token": "orphan-token"},
                        {"id": "page-2", "name": "Missing token"},
                        {
                            "id": "page-3",
                            "name": "   ",
                            "access_token": "blank-name-token",
                        },
                        "not-a-page",
                        None,
                    ]
                },
            ),
        ]

        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": state, "code": "one-time-authorization-code"},
        )

        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=no_pages",
        )
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(mock_post.call_count, 1)
        self.assertFalse(SocialAccount.objects.exists())
        self.assertTrue(
            SocialOAuthState.objects.get(state_digest=state_hash).consumed_at
        )

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_callback_stops_pagination_when_cursor_is_missing(
        self,
        mock_post,
        mock_get,
    ):
        state = "missing-cursor-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        mock_post.return_value = self.facebook_token_response(
            "long-lived-user-token",
            expires_in=5184000,
        )
        mock_get.side_effect = [
            self.facebook_token_response("short-lived-user-token"),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": "page-1",
                            "name": "First page",
                            "access_token": "first-page-token",
                        }
                    ],
                    "paging": {
                        "next": "https://graph.facebook.com/v27.0/me/accounts?after=opaque"
                    },
                },
            ),
            self.facebook_debug_response(
                expires_at=int(time.time()) + 3600,
                profile_id="page-1",
            ),
        ]

        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": state, "code": "one-time-authorization-code"},
        )

        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=connected",
        )
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_post.call_count, 1)
        for call in mock_get.call_args_list:
            self.assertTrue(
                call.args[0].startswith("https://graph.facebook.com/v27.0/")
            )
        self.assertNotIn("after", mock_get.call_args_list[1].kwargs["params"])
        self.assertTrue(
            SocialAccount.objects.filter(
                owner_id=self.user.id,
                platform_account_id="page-1",
            ).exists()
        )

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_callback_stops_pagination_when_cursor_is_empty(
        self,
        mock_post,
        mock_get,
    ):
        state = "empty-cursor-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        mock_post.return_value = self.facebook_token_response(
            "long-lived-user-token",
            expires_in=5184000,
        )
        mock_get.side_effect = [
            self.facebook_token_response("short-lived-user-token"),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": "page-1",
                            "name": "First page",
                            "access_token": "first-page-token",
                        }
                    ],
                    "paging": {
                        "next": "https://graph.facebook.com/v27.0/me/accounts?after=",
                        "cursors": {"after": ""},
                    },
                },
            ),
            self.facebook_debug_response(
                expires_at=int(time.time()) + 3600,
                profile_id="page-1",
            ),
        ]

        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": state, "code": "one-time-authorization-code"},
        )

        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=connected",
        )
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_post.call_count, 1)
        self.assertNotIn("after", mock_get.call_args_list[1].kwargs["params"])
        self.assertTrue(
            SocialAccount.objects.filter(
                owner_id=self.user.id,
                platform_account_id="page-1",
            ).exists()
        )

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_callback_stops_pagination_on_repeated_cursor(
        self,
        mock_post,
        mock_get,
    ):
        state = "repeated-cursor-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        mock_post.return_value = self.facebook_token_response(
            "long-lived-user-token",
            expires_in=5184000,
        )
        mock_get.side_effect = [
            self.facebook_token_response("short-lived-user-token"),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": "page-1",
                            "name": "First page",
                            "access_token": "first-page-token",
                        }
                    ],
                    "paging": {
                        "next": "https://graph.facebook.com/v27.0/me/accounts?after=cursor-1",
                        "cursors": {"after": "cursor-1"},
                    },
                },
            ),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": "page-2",
                            "name": "Second page",
                            "access_token": "second-page-token",
                        }
                    ],
                    "paging": {
                        "next": "https://graph.facebook.com/v27.0/me/accounts?after=cursor-1",
                        "cursors": {"after": "cursor-1"},
                    },
                },
            ),
            self.facebook_debug_response(
                expires_at=int(time.time()) + 3600,
                profile_id="page-1",
            ),
            self.facebook_debug_response(
                expires_at=int(time.time()) + 7200,
                profile_id="page-2",
            ),
        ]

        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": state, "code": "one-time-authorization-code"},
        )

        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=connected",
        )
        self.assertEqual(mock_get.call_count, 5)
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(
            mock_get.call_args_list[2].kwargs["params"]["after"],
            "cursor-1",
        )
        self.assertEqual(
            mock_get.call_args_list[2].args[0],
            "https://graph.facebook.com/v27.0/me/accounts",
        )
        self.assertEqual(
            sorted(
                SocialAccount.objects.filter(
                    owner_id=self.user.id
                ).values_list("platform_account_id", flat=True)
            ),
            ["page-1", "page-2"],
        )

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_callback_follows_pagination_until_last_page(
        self,
        mock_post,
        mock_get,
    ):
        state = "multi-page-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        mock_post.return_value = self.facebook_token_response(
            "long-lived-user-token",
            expires_in=5184000,
        )
        mock_get.side_effect = [
            self.facebook_token_response("short-lived-user-token"),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": "page-1",
                            "name": "First page",
                            "access_token": "first-page-token",
                        }
                    ],
                    "paging": {
                        "next": "https://graph.facebook.com/v27.0/me/accounts?after=cursor-1",
                        "cursors": {"after": "cursor-1"},
                    },
                },
            ),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": "page-2",
                            "name": "Second page",
                            "access_token": "second-page-token",
                        }
                    ]
                },
            ),
            self.facebook_debug_response(
                expires_at=int(time.time()) + 3600,
                profile_id="page-1",
            ),
            self.facebook_debug_response(
                expires_at=int(time.time()) + 7200,
                profile_id="page-2",
            ),
        ]

        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": state, "code": "one-time-authorization-code"},
        )

        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=connected",
        )
        self.assertEqual(mock_get.call_count, 5)
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(
            mock_get.call_args_list[2].kwargs["params"]["after"],
            "cursor-1",
        )
        self.assertEqual(
            sorted(
                SocialAccount.objects.filter(
                    owner_id=self.user.id
                ).values_list("platform_account_id", flat=True)
            ),
            ["page-1", "page-2"],
        )

    @patch("core.services.facebook_oauth.MAX_PAGE_REQUESTS", 2)
    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_callback_stops_pagination_at_request_cap(
        self,
        mock_post,
        mock_get,
    ):
        state = "pagination-cap-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        mock_post.return_value = self.facebook_token_response(
            "long-lived-user-token",
            expires_in=5184000,
        )
        mock_get.side_effect = [
            self.facebook_token_response("short-lived-user-token"),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": "page-1",
                            "name": "First page",
                            "access_token": "first-page-token",
                        }
                    ],
                    "paging": {
                        "next": "https://graph.facebook.com/v27.0/me/accounts?after=cursor-1",
                        "cursors": {"after": "cursor-1"},
                    },
                },
            ),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": "page-2",
                            "name": "Second page",
                            "access_token": "second-page-token",
                        }
                    ],
                    "paging": {
                        "next": "https://graph.facebook.com/v27.0/me/accounts?after=cursor-2",
                        "cursors": {"after": "cursor-2"},
                    },
                },
            ),
            self.facebook_debug_response(
                expires_at=int(time.time()) + 3600,
                profile_id="page-1",
            ),
            self.facebook_debug_response(
                expires_at=int(time.time()) + 7200,
                profile_id="page-2",
            ),
        ]

        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": state, "code": "one-time-authorization-code"},
        )

        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=connected",
        )
        self.assertEqual(mock_get.call_count, 5)
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(
            sorted(
                SocialAccount.objects.filter(
                    owner_id=self.user.id
                ).values_list("platform_account_id", flat=True)
            ),
            ["page-1", "page-2"],
        )

    @patch(
        "core.views.connect_authorized_facebook_pages",
        side_effect=RuntimeError("unexpected internal failure"),
    )
    def test_facebook_callback_redirects_on_unexpected_error(
        self,
        mock_connect,
    ):
        state = "unexpected-error-state"
        state_hash = hashlib.sha256(state.encode("ascii")).hexdigest()
        SocialOAuthState.objects.create(
            state_digest=state_hash,
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": state, "code": "one-time-authorization-code"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=failed",
        )
        body = response.content.decode("utf-8")
        self.assertNotIn("unexpected internal failure", body)
        self.assertNotIn("Traceback", body)
        self.assertFalse(SocialAccount.objects.exists())
        self.assertIsNotNone(
            SocialOAuthState.objects.get(state_digest=state_hash).consumed_at
        )
        mock_connect.assert_called_once()

    @patch(
        "core.views.connect_authorized_facebook_pages",
        side_effect=IntegrityError(
            "duplicate key value violates unique constraint"
        ),
    )
    def test_facebook_callback_redirects_on_database_integrity_error(
        self,
        mock_connect,
    ):
        state = "integrity-error-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": state, "code": "one-time-authorization-code"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=failed",
        )
        body = response.content.decode("utf-8")
        self.assertNotIn("duplicate key", body)
        self.assertNotIn("IntegrityError", body)
        self.assertFalse(SocialAccount.objects.exists())
        mock_connect.assert_called_once()

    @patch(
        "core.views.consume_facebook_oauth_state",
        side_effect=IntegrityError("state lookup failed"),
    )
    def test_facebook_callback_redirects_when_state_lookup_fails(
        self,
        mock_consume,
    ):
        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": "any-state", "code": "one-time-authorization-code"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=failed",
        )
        body = response.content.decode("utf-8")
        self.assertNotIn("state lookup failed", body)
        self.assertNotIn("Traceback", body)
        self.assertFalse(SocialAccount.objects.exists())
        mock_consume.assert_called_once()

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_callback_rolls_back_pages_when_save_fails(
        self,
        mock_post,
        mock_get,
    ):
        state = "rollback-state"
        state_hash = hashlib.sha256(state.encode("ascii")).hexdigest()
        SocialOAuthState.objects.create(
            state_digest=state_hash,
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        mock_post.return_value = self.facebook_token_response(
            "long-lived-user-token",
            expires_in=5184000,
        )
        mock_get.side_effect = [
            self.facebook_token_response("short-lived-user-token"),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": "page-1",
                            "name": "First page",
                            "access_token": "first-page-token",
                        },
                        {
                            "id": "page-2",
                            "name": "Second page",
                            "access_token": "second-page-token",
                        },
                    ]
                },
            ),
            self.facebook_debug_response(
                expires_at=int(time.time()) + 3600,
                profile_id="page-1",
            ),
            self.facebook_debug_response(
                expires_at=int(time.time()) + 7200,
                profile_id="page-2",
            ),
        ]
        original_update = SocialAccount.objects.update_or_create
        saved = {"count": 0}

        def update_then_fail(*args, **kwargs):
            saved["count"] += 1
            if saved["count"] > 1:
                raise IntegrityError(
                    "duplicate key value violates unique constraint"
                )
            return original_update(*args, **kwargs)

        with patch(
            "core.services.facebook_oauth.SocialAccount.objects.update_or_create",
            side_effect=update_then_fail,
        ):
            response = self.client.get(
                "/api/social/oauth/facebook_pages/callback/",
                {"state": state, "code": "one-time-authorization-code"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=failed",
        )
        # The first Page was written inside the atomic block, so it must be
        # rolled back together with the failure.
        self.assertEqual(saved["count"], 2)
        self.assertFalse(
            SocialAccount.objects.filter(owner_id=self.user.id).exists()
        )
        self.assertIsNotNone(
            SocialOAuthState.objects.get(state_digest=state_hash).consumed_at
        )

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_oauth_logs_skipped_pages_without_page_data(
        self,
        mock_post,
        mock_get,
    ):
        state = "log-skipped-pages-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        mock_post.return_value = self.facebook_token_response(
            "long-lived-user-token",
            expires_in=5184000,
        )
        mock_get.side_effect = [
            self.facebook_token_response("short-lived-user-token"),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": "page-1",
                            "name": "Valid page",
                            "access_token": "valid-page-token",
                        },
                        {"id": "page-2", "name": "Missing token"},
                        {"id": "page-3", "access_token": "nameless-token"},
                        {"name": "Missing id", "access_token": "orphan-token"},
                    ]
                },
            ),
            self.facebook_debug_response(
                expires_at=int(time.time()) + 3600,
                profile_id="page-1",
            ),
        ]

        with self.assertLogs(level="WARNING") as captured:
            response = self.client.get(
                "/api/social/oauth/facebook_pages/callback/",
                {"state": state, "code": "private-authorization-code"},
            )

        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=connected",
        )
        skipped = [
            record
            for record in captured.records
            if getattr(record, "event", "") == "facebook_oauth.page_skipped"
        ]
        self.assertEqual(
            [record.reason for record in skipped],
            ["missing_access_token", "missing_name", "missing_id"],
        )
        payload = " ".join(str(record.__dict__) for record in captured.records)
        self.assertNotIn("valid-page-token", payload)
        self.assertNotIn("nameless-token", payload)
        self.assertNotIn("orphan-token", payload)
        self.assertNotIn("private-authorization-code", payload)
        self.assertNotIn("test-app-secret", payload)
        for record in captured.records:
            self.assertIsNone(record.exc_info)

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    @patch("core.services.facebook_oauth.requests.get")
    @patch("core.services.facebook_oauth.requests.post")
    def test_facebook_oauth_logs_pagination_stop_reasons(
        self,
        mock_post,
        mock_get,
    ):
        def accounts_page(*, page_id, cursor, next_cursor=None):
            paging = {"next": "https://graph.facebook.com/v27.0/me/accounts"}
            if next_cursor is None:
                paging["cursors"] = {"after": cursor}
            else:
                paging["cursors"] = {"after": next_cursor}
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": page_id,
                            "name": "Logged page",
                            "access_token": page_id + "-token",
                        }
                    ],
                    "paging": paging,
                },
            )

        scenarios = {
            "missing_cursor": [
                self.facebook_token_response("short-lived-user-token"),
                SimpleNamespace(
                    status_code=200,
                    json=lambda: {
                        "data": [
                            {
                                "id": "page-1",
                                "name": "Logged page",
                                "access_token": "page-1-token",
                            }
                        ],
                        "paging": {
                            "next": "https://graph.facebook.com/v27.0/me/accounts"
                        },
                    },
                ),
                self.facebook_debug_response(
                    expires_at=int(time.time()) + 3600,
                    profile_id="page-1",
                ),
            ],
            "invalid_cursor": [
                self.facebook_token_response("short-lived-user-token"),
                SimpleNamespace(
                    status_code=200,
                    json=lambda: {
                        "data": [
                            {
                                "id": "page-1",
                                "name": "Logged page",
                                "access_token": "page-1-token",
                            }
                        ],
                        "paging": {
                            "next": "https://graph.facebook.com/v27.0/me/accounts",
                            "cursors": {"after": "   "},
                        },
                    },
                ),
                self.facebook_debug_response(
                    expires_at=int(time.time()) + 3600,
                    profile_id="page-1",
                ),
            ],
            "duplicate_cursor": [
                self.facebook_token_response("short-lived-user-token"),
                accounts_page(page_id="page-1", cursor=None, next_cursor="cursor-1"),
                accounts_page(page_id="page-2", cursor=None, next_cursor="cursor-1"),
                self.facebook_debug_response(
                    expires_at=int(time.time()) + 3600,
                    profile_id="page-1",
                ),
                self.facebook_debug_response(
                    expires_at=int(time.time()) + 7200,
                    profile_id="page-2",
                ),
            ],
            "request_cap": [
                self.facebook_token_response("short-lived-user-token"),
                accounts_page(page_id="page-1", cursor=None, next_cursor="cursor-1"),
                self.facebook_debug_response(
                    expires_at=int(time.time()) + 3600,
                    profile_id="page-1",
                ),
            ],
        }

        for reason, responses in scenarios.items():
            with self.subTest(reason=reason):
                mock_get.reset_mock()
                mock_post.reset_mock()
                mock_post.return_value = self.facebook_token_response(
                    "long-lived-user-token",
                    expires_in=5184000,
                )
                mock_get.side_effect = responses
                state = "pagination-log-" + reason
                SocialOAuthState.objects.create(
                    state_digest=hashlib.sha256(
                        state.encode("ascii")
                    ).hexdigest(),
                    owner_id=self.user.id,
                    platform=SocialAccount.Platform.FACEBOOK_PAGES,
                    expires_at=timezone.now() + timedelta(minutes=5),
                )
                cap = 1 if reason == "request_cap" else 100
                with patch("core.services.facebook_oauth.MAX_PAGE_REQUESTS", cap):
                    with self.assertLogs(level="WARNING") as captured:
                        response = self.client.get(
                            "/api/social/oauth/facebook_pages/callback/",
                            {"state": state, "code": "one-time-authorization-code"},
                        )

                self.assertEqual(
                    response["Location"],
                    "ibda://social-accounts?status=connected",
                )
                stopped = [
                    record
                    for record in captured.records
                    if getattr(record, "event", "")
                    == "facebook_oauth.pagination_stopped"
                ]
                self.assertEqual([record.reason for record in stopped], [reason])
                self.assertIsNone(stopped[0].exc_info)

    @patch(
        "core.views.connect_authorized_facebook_pages",
        side_effect=RuntimeError(
            "boom code=private-code access_token=secret-page-token"
        ),
    )
    def test_facebook_oauth_logs_unexpected_failure_without_sensitive_values(
        self,
        mock_connect,
    ):
        state = "log-unexpected-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        with self.assertLogs(level="WARNING") as captured:
            response = self.client.get(
                "/api/social/oauth/facebook_pages/callback/",
                {"state": state, "code": "private-code"},
            )

        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=failed",
        )
        failures = [
            record
            for record in captured.records
            if getattr(record, "event", "") == "facebook_oauth.callback_failed"
        ]
        self.assertEqual(len(failures), 1)
        record = failures[0]
        self.assertEqual(record.failure_category, "unexpected")
        self.assertEqual(record.error_type, "RuntimeError")
        self.assertIsNone(record.exc_info)
        payload = str(record.__dict__)
        self.assertNotIn("private-code", payload)
        self.assertNotIn("secret-page-token", payload)
        self.assertNotIn("boom", payload)
        self.assertNotIn("graph.facebook.com", payload)
        mock_connect.assert_called_once()

    @patch(
        "core.views.connect_authorized_facebook_pages",
        side_effect=facebook_oauth.FacebookOAuthError(
            "Unable to retrieve authorized Facebook Pages."
        ),
    )
    def test_facebook_oauth_logs_facebook_error_category(
        self,
        mock_connect,
    ):
        state = "log-facebook-error-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        with self.assertLogs(level="WARNING") as captured:
            response = self.client.get(
                "/api/social/oauth/facebook_pages/callback/",
                {"state": state, "code": "private-code"},
            )

        self.assertEqual(
            response["Location"],
            "ibda://social-accounts?status=failed",
        )
        failures = [
            record
            for record in captured.records
            if getattr(record, "event", "") == "facebook_oauth.callback_failed"
        ]
        self.assertEqual(len(failures), 1)
        record = failures[0]
        self.assertEqual(record.failure_category, "facebook_oauth_error")
        self.assertEqual(record.error_type, "FacebookOAuthError")
        self.assertEqual(
            record.detail,
            "Unable to retrieve authorized Facebook Pages.",
        )
        self.assertIsNone(record.exc_info)
        payload = str(record.__dict__)
        self.assertNotIn("private-code", payload)
        self.assertNotIn("graph.facebook.com", payload)
        mock_connect.assert_called_once()

    def test_account_purge_deletes_only_that_users_oauth_states(self):
        from .services.account_deletion import purge_owner_data

        own_state = SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(b"own-state").hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        other_state = SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(b"other-state").hexdigest(),
            owner_id=self.other_user_id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        counts = purge_owner_data(self.user.id)

        self.assertEqual(counts["social_oauth_states"], 1)
        self.assertFalse(
            SocialOAuthState.objects.filter(id=own_state.id).exists()
        )
        self.assertTrue(
            SocialOAuthState.objects.filter(id=other_state.id).exists()
        )

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
        response = self.client.post(
            "/api/social/accounts/facebook_pages/connect/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(SocialOAuthState.objects.exists())

    @override_settings(
        SOCIAL_FACEBOOK_CLIENT_ID="test-app-id",
        SOCIAL_FACEBOOK_CLIENT_SECRET="test-app-secret",
        SOCIAL_FACEBOOK_CONFIG_ID="test-config-id",
        SOCIAL_FACEBOOK_REDIRECT_URI=(
            "https://social.example/api/social/oauth/facebook_pages/callback/"
        ),
        SOCIAL_FACEBOOK_GRAPH_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    def test_facebook_connect_persists_web_response_mode(self):
        response = self.client.post(
            "/api/social/accounts/facebook_pages/connect/",
            {"response_mode": "web"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        oauth_state = SocialOAuthState.objects.get()
        self.assertEqual(oauth_state.owner_id, self.user.id)
        self.assertEqual(
            oauth_state.response_mode,
            SocialOAuthState.ResponseMode.WEB,
        )
        self.assertIn("authorization_url", response.data)

    def test_facebook_connect_rejects_unknown_response_mode(self):
        response = self.client.post(
            "/api/social/accounts/facebook_pages/connect/",
            {"response_mode": "redirect"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(SocialOAuthState.objects.exists())

    def test_web_facebook_callback_posts_status_to_opener(self):
        state = "web-facebook-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            response_mode=SocialOAuthState.ResponseMode.WEB,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        response = self.client.get(
            "/api/social/oauth/facebook_pages/callback/",
            {"state": state, "error": "access_denied"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertIn("window.opener.postMessage", response.content.decode())
        self.assertIn("status:'cancelled'", response.content.decode())
        self.assertNotIn("access_denied", response.content.decode())

    def test_callback_rejects_missing_or_unrecognized_oauth_state(self):
        missing_state = self.client.get(
            "/api/social/oauth/instagram/callback/?code=untrusted-code"
        )
        self.assertEqual(
            missing_state.status_code,
            status.HTTP_302_FOUND,
        )
        self.assertIn("status=failed", missing_state["Location"])
        self.assertNotIn("untrusted-code", missing_state["Location"])

        invalid_state = self.client.get(
            "/api/social/oauth/instagram/callback/"
            "?state=unrecognized&code=untrusted-code"
        )
        self.assertEqual(invalid_state.status_code, status.HTTP_302_FOUND)
        self.assertIn("status=failed", invalid_state["Location"])
        self.assertNotIn(b"untrusted-code", invalid_state.content)
        self.assertNotIn("untrusted-code", invalid_state["Location"])
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

    def create_stripe_subscription(self, owner_id=None, status_value="pending"):
        return UserSubscription.objects.create(
            owner_id=owner_id or self.user.id,
            provider="stripe",
            provider_customer_id="cus_checkout_test",
            plan_id="pro",
            billing_interval=UserSubscription.BillingInterval.ANNUAL,
            status=status_value,
        )

    def checkout_session(self, local_subscription, **overrides):
        values = {
            "id": "cs_test_checkout",
            "mode": "subscription",
            "status": "complete",
            "payment_status": "paid",
            "client_reference_id": str(local_subscription.id),
            "customer": local_subscription.provider_customer_id,
            "subscription": local_subscription.provider_subscription_id,
            "amount_total": 24000,
            "currency": "usd",
            "created": 1_800_000_000,
            "metadata": {
                "ibda_owner_id": str(local_subscription.owner_id),
                "ibda_subscription_id": str(local_subscription.id),
                "plan_id": local_subscription.plan_id,
                "billing_interval": local_subscription.billing_interval,
            },
        }
        values.update(overrides)
        return SimpleNamespace(**values)

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
        STRIPE_CHECKOUT_SUCCESS_URL_WEB="https://ibda.example/subscription/success",
        STRIPE_CHECKOUT_CANCEL_URL_WEB="https://ibda.example/subscription/cancel",
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

    def test_empty_payment_history_is_returned_as_an_empty_list(self):
        response = self.client.get("/api/subscription/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["transactions"], [])

    def test_payment_history_is_ordered_by_payment_time_not_insert_time(self):
        subscription = self.create_stripe_subscription(
            status_value=UserSubscription.Status.ACTIVE,
        )
        older = PaymentTransaction.objects.create(
            subscription=subscription,
            provider="stripe",
            provider_transaction_id="in_history_older",
            status=PaymentTransaction.Status.SUCCEEDED,
            occurred_at=datetime(2026, 1, 1, tzinfo=datetime_timezone.utc),
        )
        newer = PaymentTransaction.objects.create(
            subscription=subscription,
            provider="stripe",
            provider_transaction_id="in_history_newer",
            status=PaymentTransaction.Status.FAILED,
            occurred_at=datetime(2026, 2, 1, tzinfo=datetime_timezone.utc),
        )

        response = self.client.get("/api/subscription/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["transaction_id"] for item in response.data["transactions"]],
            [newer.provider_transaction_id, older.provider_transaction_id],
        )

    def test_billing_api_returns_actual_subscription_plan_interval_and_payment(self):
        subscription = self.create_stripe_subscription(
            status_value=UserSubscription.Status.ACTIVE,
        )
        PaymentTransaction.objects.create(
            subscription=subscription,
            provider="stripe",
            provider_transaction_id="in_billing_api",
            status=PaymentTransaction.Status.SUCCEEDED,
            amount_minor=24000,
            currency="USD",
        )

        response = self.client.get("/api/subscription/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["subscription"]["plan_id"], "pro")
        self.assertEqual(response.data["subscription"]["billing_interval"], "annual")
        self.assertEqual(response.data["transactions"][0]["plan_id"], "pro")
        self.assertEqual(response.data["transactions"][0]["billing_interval"], "annual")
        self.assertEqual(response.data["transactions"][0]["amount_minor"], 24000)
        self.assertEqual(response.data["transactions"][0]["status"], "succeeded")

    @override_settings(STRIPE_SECRET_KEY="sk_test_unit_test")
    def test_checkout_session_verification_returns_confirmed_payment(self):
        subscription = self.create_stripe_subscription(
            status_value=UserSubscription.Status.ACTIVE,
        )
        subscription.provider_subscription_id = "sub_checkout_test"
        subscription.save(update_fields=["provider_subscription_id", "updated_at"])
        PaymentTransaction.objects.create(
            subscription=subscription,
            provider="stripe",
            provider_transaction_id="in_checkout_test",
            status=PaymentTransaction.Status.SUCCEEDED,
            amount_minor=24000,
            currency="USD",
        )
        session = self.checkout_session(subscription)
        self.client.force_authenticate(user=None)
        with self.settings(
            SUPABASE_URL="https://supabase.example.invalid",
            SUPABASE_PUBLISHABLE_KEY="publishable-test-key",
        ):
            with (
                patch("core.authentication.requests.get") as verify_user,
                patch(
                    "core.services.payments.verification.retrieve_checkout_session",
                    return_value=session,
                ) as retrieve_session,
            ):
                verify_user.return_value.status_code = 200
                verify_user.return_value.json.return_value = {
                    "id": str(self.user.id),
                    "email": "creator@example.invalid",
                }
                response = self.client.get(
                    "/api/subscription/checkout/verify/",
                    {"session_id": "cs_test_checkout"},
                    HTTP_AUTHORIZATION="Bearer valid-test-access-token",
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["plan_id"], "pro")
        self.assertEqual(response.data["billing_interval"], "annual")
        self.assertEqual(response.data["amount_minor"], 24000)
        self.assertEqual(response.data["currency"], "USD")
        self.assertEqual(response.data["payment_status"], "succeeded")
        self.assertEqual(PaymentTransaction.objects.count(), 2)
        self.assertNotIn("provider_customer_id", response.data)
        self.assertNotIn("stripe_secret_key", response.data)
        retrieve_session.assert_called_once_with("cs_test_checkout")
        verify_user.assert_called_once()

    @override_settings(STRIPE_SECRET_KEY="sk_test_unit_test")
    def test_verified_paid_checkout_creates_one_transaction_on_repeated_verification(
        self,
    ):
        subscription = self.create_stripe_subscription()
        subscription.checkout_session_id = "cs_verified_initial"
        subscription.save(update_fields=["checkout_session_id", "updated_at"])
        session = self.checkout_session(
            subscription,
            id="cs_verified_initial",
            invoice="in_verified_initial",
            payment_intent="pi_verified_initial",
        )
        with patch(
            "core.services.payments.verification.retrieve_checkout_session",
            return_value=session,
        ):
            first = self.client.get(
                "/api/subscription/checkout/verify/",
                {"session_id": "cs_verified_initial"},
            )
            repeated = self.client.get(
                "/api/subscription/checkout/verify/",
                {"session_id": "cs_verified_initial"},
            )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["status"], "success")
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        payment = PaymentTransaction.objects.get(
            provider_invoice_id="in_verified_initial"
        )
        self.assertEqual(PaymentTransaction.objects.count(), 1)
        self.assertEqual(payment.provider_payment_intent_id, "pi_verified_initial")
        self.assertEqual(payment.checkout_session_id, "cs_verified_initial")
        self.assertEqual(payment.status, PaymentTransaction.Status.SUCCEEDED)

    @override_settings(STRIPE_SECRET_KEY="sk_test_unit_test")
    def test_checkout_verification_rejects_a_session_other_than_saved_session(
        self,
    ):
        subscription = self.create_stripe_subscription()
        subscription.checkout_session_id = "cs_saved_checkout"
        subscription.save(update_fields=["checkout_session_id", "updated_at"])
        session = self.checkout_session(subscription)
        with patch(
            "core.services.payments.verification.retrieve_checkout_session",
            return_value=session,
        ):
            response = self.client.get(
                "/api/subscription/checkout/verify/",
                {"session_id": "cs_test_checkout"},
            )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(PaymentTransaction.objects.exists())

    @override_settings(STRIPE_SECRET_KEY="sk_test_unit_test")
    def test_stripe_verification_api_failure_does_not_create_payment(self):
        subscription = self.create_stripe_subscription()
        session = self.checkout_session(subscription)
        with patch(
            "core.services.payments.verification.retrieve_checkout_session",
            side_effect=stripe.APIConnectionError("offline"),
        ):
            response = self.client.get(
                "/api/subscription/checkout/verify/",
                {"session_id": "cs_test_checkout"},
            )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertFalse(PaymentTransaction.objects.exists())

    @override_settings(STRIPE_SECRET_KEY="sk_test_unit_test")
    def test_checkout_session_verification_rejects_another_users_session(self):
        foreign = self.create_stripe_subscription(
            owner_id=self.other_user_id,
            status_value=UserSubscription.Status.ACTIVE,
        )
        session = self.checkout_session(foreign, id="cs_test_foreign")
        with patch(
            "core.services.payments.verification.retrieve_checkout_session",
            return_value=session,
        ):
            response = self.client.get(
                "/api/subscription/checkout/verify/",
                {"session_id": "cs_test_foreign"},
            )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(STRIPE_SECRET_KEY="sk_test_unit_test")
    def test_unpaid_checkout_session_remains_pending_until_webhook_records_payment(
        self,
    ):
        subscription = self.create_stripe_subscription()
        session = self.checkout_session(
            subscription,
            id="cs_test_delayed",
            status="complete",
            payment_status="unpaid",
            subscription=None,
        )
        with patch(
            "core.services.payments.verification.retrieve_checkout_session",
            return_value=session,
        ):
            response = self.client.get(
                "/api/subscription/checkout/verify/",
                {"session_id": "cs_test_delayed"},
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(response.data["payment_status"], "pending")
        self.assertIsNone(response.data["amount_minor"])

    @override_settings(STRIPE_SECRET_KEY="sk_test_unit_test")
    def test_verification_stays_pending_until_webhook_records_successful_invoice(
        self,
    ):
        subscription = self.create_stripe_subscription()
        subscription.provider_subscription_id = "sub_delayed_checkout"
        subscription.save(update_fields=["provider_subscription_id", "updated_at"])
        session = self.checkout_session(subscription, id="cs_test_delayed")
        with patch(
            "core.services.payments.verification.retrieve_checkout_session",
            return_value=session,
        ):
            pending = self.client.get(
                "/api/subscription/checkout/verify/",
                {"session_id": "cs_test_delayed"},
            )

        self.assertEqual(pending.status_code, status.HTTP_200_OK)
        self.assertEqual(pending.data["status"], "pending")

        subscription.status = UserSubscription.Status.ACTIVE
        subscription.save(update_fields=["status", "updated_at"])
        payment = PaymentTransaction.objects.get(
            checkout_session_id="cs_test_delayed"
        )
        payment.provider_invoice_id = "in_delayed_checkout"
        payment.status = PaymentTransaction.Status.SUCCEEDED
        payment.amount_minor = 24000
        payment.currency = "USD"
        payment.save()
        with patch(
            "core.services.payments.verification.retrieve_checkout_session",
            return_value=session,
        ):
            confirmed = self.client.get(
                "/api/subscription/checkout/verify/",
                {"session_id": "cs_test_delayed"},
            )

        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
        self.assertEqual(confirmed.data["status"], "success")
        self.assertEqual(confirmed.data["payment_status"], "succeeded")

    @override_settings(STRIPE_SECRET_KEY="sk_test_unit_test")
    def test_verification_reports_an_async_payment_failure(self):
        subscription = self.create_stripe_subscription()
        PaymentTransaction.objects.create(
            subscription=subscription,
            provider="stripe",
            provider_transaction_id="cs_failed_checkout",
            status=PaymentTransaction.Status.FAILED,
            amount_minor=24000,
            currency="USD",
        )
        session = self.checkout_session(
            subscription,
            id="cs_failed_checkout",
            payment_status="unpaid",
            subscription=None,
        )
        with patch(
            "core.services.payments.verification.retrieve_checkout_session",
            return_value=session,
        ):
            response = self.client.get(
                "/api/subscription/checkout/verify/",
                {"session_id": "cs_failed_checkout"},
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "failed")
        self.assertEqual(response.data["payment_status"], "failed")

    def test_checkout_session_verification_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(
            "/api/subscription/checkout/verify/",
            {"session_id": "cs_test_checkout"},
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

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
            STRIPE_CHECKOUT_SUCCESS_URL_WEB="https://ibda.example/subscription/success",
            STRIPE_CHECKOUT_CANCEL_URL_WEB="https://ibda.example/subscription/cancel",
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
            STRIPE_CHECKOUT_SUCCESS_URL_WEB="https://ibda.example/subscription/success",
            STRIPE_CHECKOUT_CANCEL_URL_WEB="https://ibda.example/subscription/cancel",
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
            STRIPE_CHECKOUT_SUCCESS_URL_WEB=(
                "https://ibda.example/subscription/success"
            ),
            STRIPE_CHECKOUT_CANCEL_URL_WEB=(
                "https://ibda.example/subscription/cancel"
            ),
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
            create_session.call_args.kwargs["success_url"],
            "https://ibda.example/subscription/success?"
            "checkout=success&session_id={CHECKOUT_SESSION_ID}",
        )
        self.assertEqual(
            create_session.call_args.kwargs["cancel_url"],
            "https://ibda.example/subscription/cancel?checkout=cancelled",
        )
        self.assertEqual(
            UserSubscription.objects.get().status,
            UserSubscription.Status.PENDING,
        )
        self.assertEqual(
            UserSubscription.objects.get().plan_id,
            "pro",
        )
        self.assertEqual(
            StripeCheckoutAttempt.objects.get().checkout_session_id,
            session.id,
        )

    def test_mobile_checkout_uses_configured_expo_return_url(self):
        session = SimpleNamespace(
            id="cs_test_mobile",
            url="https://checkout.stripe.test/mobile",
        )
        with self.settings(
            STRIPE_SECRET_KEY="sk_test_unit_test",
            STRIPE_WEBHOOK_SECRET="whsec_unit_test",
            STRIPE_CHECKOUT_SUCCESS_URL_MOBILE="ibda://subscription/success",
            STRIPE_CHECKOUT_CANCEL_URL_MOBILE="ibda://subscription/success",
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
                    return_value=SimpleNamespace(id="cus_test_mobile"),
                ),
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
                        "platform": "mobile",
                    },
                    format="json",
                    HTTP_IDEMPOTENCY_KEY=str(uuid4()),
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            create_session.call_args.kwargs["success_url"],
            "ibda://subscription/success?"
            "checkout=success&session_id={CHECKOUT_SESSION_ID}",
        )
        self.assertEqual(
            create_session.call_args.kwargs["cancel_url"],
            "ibda://subscription/success?checkout=cancelled",
        )

    def test_checkout_stripe_errors_are_safe_and_leave_no_pending_record(self):
        with self.settings(
            STRIPE_SECRET_KEY="sk_test_unit_test",
            STRIPE_WEBHOOK_SECRET="whsec_unit_test",
            STRIPE_CHECKOUT_SUCCESS_URL_WEB="https://ibda.example/subscription/success",
            STRIPE_CHECKOUT_CANCEL_URL_WEB="https://ibda.example/subscription/cancel",
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
            expires_at=int(time.time()) + 3600,
        )
        idempotency_key = str(uuid4())
        with self.settings(
            STRIPE_SECRET_KEY="sk_test_unit_test",
            STRIPE_WEBHOOK_SECRET="whsec_unit_test",
            STRIPE_CHECKOUT_SUCCESS_URL_WEB="https://ibda.example/subscription/success",
            STRIPE_CHECKOUT_CANCEL_URL_WEB="https://ibda.example/subscription/cancel",
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
                patch(
                    "core.services.payments.checkout.retrieve_checkout_session",
                    side_effect=lambda _session_id: SimpleNamespace(
                        id=session.id,
                        status="open",
                        expires_at=int(time.time()) + 3600,
                        url=session.url,
                        customer="cus_test_retry",
                        metadata={
                            "ibda_owner_id": str(self.user.id),
                            "ibda_subscription_id": str(
                                UserSubscription.objects.get().id
                            ),
                        },
                    ),
                ) as retrieve_session,
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
        create_session.assert_called_once()
        self.assertEqual(
            create_session.call_args.kwargs["idempotency_key"],
            f"ibda-checkout-{self.user.id}-{idempotency_key}",
        )
        create_customer.assert_called_once()
        retrieve_session.assert_called_once_with(session.id)

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

    def test_active_stripe_subscription_returns_structured_checkout_conflict(self):
        subscription = UserSubscription.objects.create(
            owner_id=self.user.id,
            provider="stripe",
            provider_customer_id="cus_checkout_test",
            provider_subscription_id="sub_existing_active",
            plan_id="starter",
            billing_interval="monthly",
            status=UserSubscription.Status.ACTIVE,
        )
        remote = SimpleNamespace(
            status="active",
            customer="cus_checkout_test",
        )
        with self.settings(
            STRIPE_SECRET_KEY="sk_test_unit_test",
            STRIPE_WEBHOOK_SECRET="whsec_unit_test",
            STRIPE_CHECKOUT_SUCCESS_URL_WEB="https://ibda.example/subscription/success",
            STRIPE_CHECKOUT_CANCEL_URL_WEB="https://ibda.example/subscription/cancel",
            STRIPE_PRICE_STARTER_ANNUAL="price_server_starter_annual",
        ):
            with (
                patch(
                    "core.services.payments.checkout.retrieve_price_details",
                    return_value={
                        "price_minor": 12500,
                        "currency": "USD",
                        "active": True,
                        "recurring_interval": "year",
                        "recurring_interval_count": 1,
                    },
                ),
                patch(
                    "core.services.payments.checkout.retrieve_subscription",
                    return_value=remote,
                ) as retrieve_subscription,
                patch(
                    "core.services.payments.checkout.create_checkout_session"
                ) as create_session,
            ):
                response = self.client.post(
                    "/api/subscription/checkout/",
                    {"plan_id": "starter", "billing_interval": "annual"},
                    format="json",
                    HTTP_IDEMPOTENCY_KEY=str(uuid4()),
                )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "subscription_conflict")
        self.assertEqual(response.data["reason"], "active_subscription")
        self.assertEqual(response.data["current_subscription"]["id"], str(subscription.id))
        self.assertIn("Manage or switch", response.data["detail"])
        self.assertEqual(UserSubscription.objects.filter(owner_id=self.user.id).count(), 1)
        retrieve_subscription.assert_called_once_with("sub_existing_active")
        create_session.assert_not_called()

    def test_expired_checkout_session_can_be_retried_without_duplicate_row(self):
        subscription = UserSubscription.objects.create(
            owner_id=self.user.id,
            provider="stripe",
            provider_customer_id="cus_checkout_test",
            plan_id="starter",
            billing_interval="annual",
            status=UserSubscription.Status.PENDING,
            checkout_session_id="cs_expired",
        )
        expired_session = SimpleNamespace(
            status="expired",
            customer="cus_checkout_test",
            metadata={
                "ibda_owner_id": str(self.user.id),
                "ibda_subscription_id": str(subscription.id),
            },
        )
        replacement = SimpleNamespace(
            id="cs_replacement",
            url="https://checkout.stripe.test/replacement",
            expires_at=int(time.time()) + 3600,
        )
        with self.settings(
            STRIPE_SECRET_KEY="sk_test_unit_test",
            STRIPE_WEBHOOK_SECRET="whsec_unit_test",
            STRIPE_CHECKOUT_SUCCESS_URL_WEB="https://ibda.example/subscription/success",
            STRIPE_CHECKOUT_CANCEL_URL_WEB="https://ibda.example/subscription/cancel",
            STRIPE_PRICE_STARTER_ANNUAL="price_server_starter_annual",
        ):
            with (
                patch(
                    "core.services.payments.checkout.retrieve_price_details",
                    return_value={
                        "price_minor": 12500,
                        "currency": "USD",
                        "active": True,
                        "recurring_interval": "year",
                        "recurring_interval_count": 1,
                    },
                ),
                patch(
                    "core.services.payments.checkout.retrieve_checkout_session",
                    return_value=expired_session,
                ),
                patch(
                    "core.services.payments.checkout.create_checkout_session",
                    return_value=replacement,
                ) as create_session,
            ):
                response = self.client.post(
                    "/api/subscription/checkout/",
                    {"plan_id": "starter", "billing_interval": "annual"},
                    format="json",
                    HTTP_IDEMPOTENCY_KEY=str(uuid4()),
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["session_id"], "cs_replacement")
        self.assertEqual(UserSubscription.objects.filter(owner_id=self.user.id).count(), 1)
        subscription.refresh_from_db()
        self.assertEqual(subscription.checkout_session_id, "cs_replacement")
        create_session.assert_called_once()

    def test_open_checkout_session_is_reused_on_duplicate_request(self):
        subscription = UserSubscription.objects.create(
            owner_id=self.user.id,
            provider="stripe",
            provider_customer_id="cus_checkout_test",
            plan_id="starter",
            billing_interval="annual",
            status=UserSubscription.Status.PENDING,
            checkout_session_id="cs_open",
        )
        open_session = SimpleNamespace(
            id="cs_open",
            url="https://checkout.stripe.test/open",
            status="open",
            expires_at=int(time.time()) + 3600,
            customer="cus_checkout_test",
            metadata={
                "ibda_owner_id": str(self.user.id),
                "ibda_subscription_id": str(subscription.id),
            },
        )
        with self.settings(
            STRIPE_SECRET_KEY="sk_test_unit_test",
            STRIPE_WEBHOOK_SECRET="whsec_unit_test",
            STRIPE_CHECKOUT_SUCCESS_URL_WEB="https://ibda.example/subscription/success",
            STRIPE_CHECKOUT_CANCEL_URL_WEB="https://ibda.example/subscription/cancel",
            STRIPE_PRICE_STARTER_ANNUAL="price_server_starter_annual",
        ):
            with (
                patch(
                    "core.services.payments.checkout.retrieve_price_details",
                    return_value={
                        "price_minor": 12500,
                        "currency": "USD",
                        "active": True,
                        "recurring_interval": "year",
                        "recurring_interval_count": 1,
                    },
                ),
                patch(
                    "core.services.payments.checkout.retrieve_checkout_session",
                    return_value=open_session,
                ),
                patch(
                    "core.services.payments.checkout.create_checkout_session"
                ) as create_session,
            ):
                response = self.client.post(
                    "/api/subscription/checkout/",
                    {"plan_id": "starter", "billing_interval": "annual"},
                    format="json",
                    HTTP_IDEMPOTENCY_KEY=str(uuid4()),
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["session_id"], "cs_open")
        self.assertEqual(response.data["checkout_url"], open_session.url)
        self.assertEqual(UserSubscription.objects.filter(owner_id=self.user.id).count(), 1)
        create_session.assert_not_called()

    @override_settings(STRIPE_SECRET_KEY="sk_test_unit_test")
    def test_cancel_endpoint_schedules_cancellation_and_preserves_active_period(self):
        subscription = UserSubscription.objects.create(
            owner_id=self.user.id,
            provider="stripe",
            provider_customer_id="cus_checkout_test",
            provider_subscription_id="sub_cancel_test",
            plan_id="pro",
            billing_interval="annual",
            status=UserSubscription.Status.ACTIVE,
        )
        period_end = int(time.time()) + 86400
        remote_before = SimpleNamespace(
            status="active",
            customer="cus_checkout_test",
            cancel_at_period_end=False,
        )
        remote_after = SimpleNamespace(
            status="active",
            customer="cus_checkout_test",
            cancel_at_period_end=True,
            current_period_end=period_end,
            canceled_at=None,
        )
        with (
            patch(
                "core.views.retrieve_subscription",
                return_value=remote_before,
            ),
            patch(
                "core.views.update_stripe_subscription",
                return_value=remote_after,
            ) as update_subscription,
        ):
            response = self.client.post(
                "/api/subscription/cancel/",
                {"cancel_at_period_end": True},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["cancel_at_period_end"])
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.Status.ACTIVE)
        self.assertTrue(subscription.cancel_at_period_end)
        self.assertEqual(
            response.data["effective_at"],
            subscription.current_period_end,
        )
        update_subscription.assert_called_once_with(
            "sub_cancel_test",
            {"cancel_at_period_end": True},
        )

    @override_settings(STRIPE_SECRET_KEY="sk_test_unit_test")
    def test_cancel_endpoint_supports_immediate_cancellation(self):
        subscription = UserSubscription.objects.create(
            owner_id=self.user.id,
            provider="stripe",
            provider_customer_id="cus_checkout_test",
            provider_subscription_id="sub_cancel_now",
            plan_id="pro",
            billing_interval="annual",
            status=UserSubscription.Status.ACTIVE,
        )
        remote_before = SimpleNamespace(
            status="active",
            customer="cus_checkout_test",
            cancel_at_period_end=False,
        )
        remote_after = SimpleNamespace(
            status="canceled",
            customer="cus_checkout_test",
            cancel_at_period_end=False,
            canceled_at=int(time.time()),
        )
        with (
            patch("core.views.retrieve_subscription", return_value=remote_before),
            patch(
                "core.views.cancel_stripe_subscription",
                return_value=remote_after,
            ) as cancel_remote,
        ):
            response = self.client.post(
                "/api/subscription/cancel/",
                {"cancel_at_period_end": False},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.Status.CANCELED)
        self.assertFalse(subscription.cancel_at_period_end)
        self.assertIsNotNone(subscription.canceled_at)
        cancel_remote.assert_called_once_with("sub_cancel_now")

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_unit_test",
        STRIPE_PRICE_STARTER_MONTHLY="price_starter_monthly",
        STRIPE_PRICE_PRO_MONTHLY="price_pro_monthly",
    )
    def test_plan_switch_updates_existing_stripe_item_for_upgrade_or_downgrade(self):
        subscription = UserSubscription.objects.create(
            owner_id=self.user.id,
            provider="stripe",
            provider_customer_id="cus_checkout_test",
            provider_subscription_id="sub_switch_test",
            plan_id="starter",
            billing_interval="monthly",
            status=UserSubscription.Status.ACTIVE,
        )
        remote = SimpleNamespace(
            status="active",
            customer="cus_checkout_test",
            cancel_at_period_end=False,
            metadata={
                "ibda_owner_id": str(self.user.id),
                "ibda_subscription_id": str(subscription.id),
            },
            items=SimpleNamespace(
                data=[
                    SimpleNamespace(
                        id="si_existing",
                        price=SimpleNamespace(id="price_starter_monthly"),
                    )
                ]
            ),
        )
        updated = SimpleNamespace(
            status="active",
            current_period_end=int(time.time()) + 86400,
        )
        with (
            patch("core.views.retrieve_price_details", return_value={
                "price_minor": 2500,
                "currency": "USD",
                "active": True,
                "recurring_interval": "month",
                "recurring_interval_count": 1,
            }),
            patch("core.views.retrieve_subscription", return_value=remote),
            patch(
                "core.views.update_stripe_subscription",
                return_value=updated,
            ) as update_subscription,
        ):
            response = self.client.post(
                "/api/subscription/plan-switch/",
                {"plan_id": "pro", "billing_interval": "monthly"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["plan_id"], "pro")
        self.assertEqual(response.data["billing_interval"], "monthly")
        self.assertIn("prorated", response.data["proration_disclosure"])
        self.assertEqual(
            update_subscription.call_args.args[1]["items"],
            [{"id": "si_existing", "price": "price_pro_monthly"}],
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan_id, "pro")

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_unit_test",
        STRIPE_PRICE_STARTER_MONTHLY="price_starter_monthly",
        STRIPE_PRICE_PRO_MONTHLY="price_pro_monthly",
    )
    def test_plan_switch_supports_downgrade(self):
        subscription = UserSubscription.objects.create(
            owner_id=self.user.id,
            provider="stripe",
            provider_customer_id="cus_checkout_test",
            provider_subscription_id="sub_downgrade_test",
            plan_id="pro",
            billing_interval="monthly",
            status=UserSubscription.Status.ACTIVE,
        )
        remote = SimpleNamespace(
            status="active",
            customer="cus_checkout_test",
            cancel_at_period_end=False,
            metadata={
                "ibda_owner_id": str(self.user.id),
                "ibda_subscription_id": str(subscription.id),
            },
            items=SimpleNamespace(
                data=[
                    SimpleNamespace(
                        id="si_pro",
                        price=SimpleNamespace(id="price_pro_monthly"),
                    )
                ]
            ),
        )
        with (
            patch("core.views.retrieve_price_details", return_value={
                "price_minor": 1250,
                "currency": "USD",
                "active": True,
                "recurring_interval": "month",
                "recurring_interval_count": 1,
            }),
            patch("core.views.retrieve_subscription", return_value=remote),
            patch(
                "core.views.update_stripe_subscription",
                return_value=SimpleNamespace(status="active"),
            ) as update_subscription,
        ):
            response = self.client.post(
                "/api/subscription/plan-switch/",
                {"plan_id": "starter", "billing_interval": "monthly"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["plan_id"], "starter")
        self.assertEqual(
            update_subscription.call_args.args[1]["items"],
            [{"id": "si_pro", "price": "price_starter_monthly"}],
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan_id, "starter")

    def test_subscription_management_endpoints_do_not_modify_another_users_plan(self):
        foreign = UserSubscription.objects.create(
            owner_id=self.other_user_id,
            provider="stripe",
            provider_customer_id="cus_foreign",
            provider_subscription_id="sub_foreign",
            plan_id="starter",
            billing_interval="monthly",
            status=UserSubscription.Status.ACTIVE,
        )
        with self.settings(
            STRIPE_SECRET_KEY="sk_test_unit_test",
            STRIPE_PRICE_PRO_MONTHLY="price_pro_monthly",
        ):
            with (
                patch("core.views.retrieve_price_details", return_value={
                    "price_minor": 2500,
                    "currency": "USD",
                    "active": True,
                    "recurring_interval": "month",
                    "recurring_interval_count": 1,
                }),
                patch("core.views.retrieve_subscription") as retrieve_subscription,
                patch("core.views.update_stripe_subscription") as update_subscription,
            ):
                cancel_response = self.client.post(
                    "/api/subscription/cancel/",
                    {"cancel_at_period_end": True},
                    format="json",
                )
                switch_response = self.client.post(
                    "/api/subscription/plan-switch/",
                    {"plan_id": "pro", "billing_interval": "monthly"},
                    format="json",
                )

        self.assertEqual(cancel_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(switch_response.status_code, status.HTTP_404_NOT_FOUND)
        retrieve_subscription.assert_not_called()
        update_subscription.assert_not_called()
        foreign.refresh_from_db()
        self.assertEqual(foreign.plan_id, "starter")

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
                        "plan_id": subscription.plan_id,
                        "billing_interval": subscription.billing_interval,
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

    def test_unknown_price_event_is_recorded_for_recovery_without_changes(self):
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

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["duplicate"])
        self.assertTrue(response.data["needs_attention"])
        record = ProviderWebhookEvent.objects.get(
            event_id="evt_subscription_created"
        )
        self.assertEqual(
            record.status,
            ProviderWebhookEvent.Status.NEEDS_ATTENTION,
        )
        self.assertIn("price_not_configured", record.detail)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.Status.PENDING)
        self.assertEqual(subscription.plan_id, "starter")
        self.assertIsNone(subscription.provider_subscription_id)

    def test_unknown_price_event_is_reprocessed_after_configuration_fix(self):
        subscription = self.create_stripe_subscription()
        event = self.subscription_event(
            subscription,
            event_id="evt_recover_price",
            price_id="price_recoverable",
        )
        with self.settings(
            STRIPE_WEBHOOK_SECRET=self.signing_secret,
            STRIPE_PRICE_STARTER_MONTHLY="price_starter_monthly",
        ):
            first = self.post_stripe_event(event)

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(
            ProviderWebhookEvent.objects.get(
                event_id="evt_recover_price"
            ).status,
            ProviderWebhookEvent.Status.NEEDS_ATTENTION,
        )

        with self.settings(
            STRIPE_WEBHOOK_SECRET=self.signing_secret,
            STRIPE_PRICE_PRO_MONTHLY="price_recoverable",
        ):
            recovered = self.post_stripe_event(event)

        self.assertEqual(recovered.status_code, status.HTTP_200_OK)
        self.assertFalse(recovered.data["duplicate"])
        self.assertEqual(recovered.data["processing_status"], "processed")
        record = ProviderWebhookEvent.objects.get(event_id="evt_recover_price")
        self.assertEqual(record.status, ProviderWebhookEvent.Status.PROCESSED)
        self.assertEqual(record.detail, "")
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.Status.ACTIVE)
        self.assertEqual(subscription.plan_id, "pro")
        self.assertEqual(
            subscription.billing_interval,
            UserSubscription.BillingInterval.MONTHLY,
        )

    def test_reprocess_stripe_event_retrieves_the_recorded_event_read_only(self):
        subscription = self.create_stripe_subscription()
        event = self.subscription_event(
            subscription,
            event_id="evt_reprocess_me",
            price_id="price_reprocess_me",
        )
        with self.settings(
            STRIPE_WEBHOOK_SECRET=self.signing_secret,
            STRIPE_PRICE_STARTER_MONTHLY="price_starter_monthly",
        ):
            first = self.post_stripe_event(event)

        self.assertEqual(first.status_code, status.HTTP_200_OK)

        with self.settings(STRIPE_PRICE_PRO_ANNUAL="price_reprocess_me"):
            with patch(
                "core.services.payments.webhooks.retrieve_event",
                return_value=event,
            ) as retrieve_event_mock:
                result = reprocess_stripe_event("evt_reprocess_me")

        self.assertTrue(result["reprocessed"])
        self.assertEqual(result["processing_status"], "processed")
        retrieve_event_mock.assert_called_once_with("evt_reprocess_me")
        record = ProviderWebhookEvent.objects.get(event_id="evt_reprocess_me")
        self.assertEqual(record.status, ProviderWebhookEvent.Status.PROCESSED)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.Status.ACTIVE)
        self.assertEqual(subscription.plan_id, "pro")
        self.assertEqual(
            subscription.billing_interval,
            UserSubscription.BillingInterval.ANNUAL,
        )

    def test_reprocess_rejects_an_unrecorded_event(self):
        with self.assertRaises(StripeWebhookProcessingError):
            reprocess_stripe_event("evt_never_recorded")

        self.assertFalse(ProviderWebhookEvent.objects.exists())

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
                        "plan_id": subscription.plan_id,
                        "billing_interval": subscription.billing_interval,
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
        payment = PaymentTransaction.objects.get(
            checkout_session_id="cs_completed_test"
        )
        self.assertEqual(payment.status, PaymentTransaction.Status.SUCCEEDED)
        self.assertEqual(
            payment.transaction_type,
            PaymentTransaction.TransactionType.INITIAL_PAYMENT,
        )
        self.assertEqual(payment.subscription_id, subscription.id)

    def test_unpaid_checkout_completion_is_pending_and_does_not_activate(self):
        subscription = self.create_stripe_subscription()
        event = {
            "id": "evt_checkout_unpaid",
            "type": "checkout.session.completed",
            "created": int(time.time()),
            "data": {
                "object": {
                    "id": "cs_checkout_unpaid",
                    "mode": "subscription",
                    "status": "complete",
                    "payment_status": "unpaid",
                    "customer": "cus_webhook_test",
                    "subscription": "sub_checkout_unpaid",
                    "client_reference_id": str(subscription.id),
                    "metadata": {
                        "ibda_subscription_id": str(subscription.id),
                        "ibda_owner_id": str(subscription.owner_id),
                        "plan_id": subscription.plan_id,
                        "billing_interval": subscription.billing_interval,
                    },
                }
            },
        }
        with self.settings(STRIPE_WEBHOOK_SECRET=self.signing_secret):
            response = self.post_stripe_event(event)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.Status.PENDING)
        self.assertEqual(
            subscription.provider_subscription_id,
            "sub_checkout_unpaid",
        )
        payment = PaymentTransaction.objects.get(
            checkout_session_id="cs_checkout_unpaid"
        )
        self.assertEqual(payment.status, PaymentTransaction.Status.PENDING)

    def test_async_checkout_failure_records_failed_payment_without_activation(self):
        subscription = self.create_stripe_subscription()
        event = {
            "id": "evt_checkout_async_failed",
            "type": "checkout.session.async_payment_failed",
            "created": int(time.time()),
            "data": {
                "object": {
                    "id": "cs_checkout_async_failed",
                    "mode": "subscription",
                    "status": "complete",
                    "payment_status": "unpaid",
                    "customer": "cus_webhook_test",
                    "subscription": "sub_checkout_async_failed",
                    "client_reference_id": str(subscription.id),
                    "amount_total": 24000,
                    "currency": "usd",
                    "metadata": {
                        "ibda_subscription_id": str(subscription.id),
                        "ibda_owner_id": str(subscription.owner_id),
                        "plan_id": subscription.plan_id,
                        "billing_interval": subscription.billing_interval,
                    },
                }
            },
        }
        with self.settings(STRIPE_WEBHOOK_SECRET=self.signing_secret):
            response = self.post_stripe_event(event)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.Status.PENDING)
        payment = PaymentTransaction.objects.get(
            provider_transaction_id="cs_checkout_async_failed"
        )
        self.assertEqual(payment.status, PaymentTransaction.Status.FAILED)
        self.assertEqual(payment.amount_minor, 24000)
        self.assertEqual(payment.currency, "USD")

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

    def test_out_of_order_invoice_event_cannot_overwrite_success(self):
        subscription = self.create_stripe_subscription(
            status_value=UserSubscription.Status.ACTIVE,
        )
        subscription.provider_subscription_id = "sub_invoice_order_test"
        subscription.save(update_fields=["provider_subscription_id", "updated_at"])
        invoice_data = {
            "id": "in_invoice_order_test",
            "subscription": "sub_invoice_order_test",
            "customer": "cus_webhook_test",
            "amount_paid": 1250,
            "amount_due": 1250,
            "currency": "usd",
        }
        with self.settings(STRIPE_WEBHOOK_SECRET=self.signing_secret):
            self.post_stripe_event(
                {
                    "id": "evt_invoice_order_paid",
                    "type": "invoice.paid",
                    "created": 2_000_000_010,
                    "data": {"object": invoice_data},
                }
            )
            stale_failure = self.post_stripe_event(
                {
                    "id": "evt_invoice_order_failed",
                    "type": "invoice.payment_failed",
                    "created": 2_000_000_000,
                    "data": {"object": invoice_data},
                }
            )

        self.assertEqual(stale_failure.status_code, status.HTTP_200_OK)
        payment = PaymentTransaction.objects.get(
            provider_invoice_id="in_invoice_order_test"
        )
        self.assertEqual(payment.status, PaymentTransaction.Status.SUCCEEDED)

    def test_duplicate_invoice_webhook_does_not_duplicate_payment(self):
        subscription = self.create_stripe_subscription(
            status_value=UserSubscription.Status.ACTIVE,
        )
        subscription.provider_subscription_id = "sub_invoice_duplicate_test"
        subscription.save(update_fields=["provider_subscription_id", "updated_at"])
        event = {
            "id": "evt_invoice_duplicate_test",
            "type": "invoice.paid",
            "created": int(time.time()),
            "data": {
                "object": {
                    "id": "in_invoice_duplicate_test",
                    "subscription": "sub_invoice_duplicate_test",
                    "customer": "cus_webhook_test",
                    "amount_paid": 1200,
                    "currency": "usd",
                }
            },
        }
        with self.settings(STRIPE_WEBHOOK_SECRET=self.signing_secret):
            first = self.post_stripe_event(event)
            duplicate = self.post_stripe_event(event)

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(duplicate.status_code, status.HTTP_200_OK)
        self.assertTrue(duplicate.data["duplicate"])
        self.assertEqual(PaymentTransaction.objects.count(), 1)

    def test_refund_webhook_records_refund_without_overwriting_partial_payment(self):
        subscription = self.create_stripe_subscription(
            status_value=UserSubscription.Status.ACTIVE,
        )
        original = PaymentTransaction.objects.create(
            subscription=subscription,
            provider="stripe",
            provider_transaction_id="in_refund_test",
            provider_customer_id="cus_webhook_test",
            provider_payment_intent_id="pi_refund_test",
            provider_charge_id="ch_refund_test",
            status=PaymentTransaction.Status.SUCCEEDED,
            amount_minor=5000,
            currency="USD",
        )
        event = {
            "id": "evt_refund_test",
            "type": "charge.refunded",
            "created": int(time.time()),
            "data": {
                "object": {
                    "id": "ch_refund_test",
                    "customer": "cus_webhook_test",
                    "payment_intent": "pi_refund_test",
                    "amount": 5000,
                    "amount_refunded": 1000,
                    "refunds": {
                        "data": [
                            {
                                "id": "re_refund_test",
                                "status": "succeeded",
                                "amount": 1000,
                                "currency": "usd",
                                "created": int(time.time()),
                            }
                        ]
                    },
                }
            },
        }
        with self.settings(STRIPE_WEBHOOK_SECRET=self.signing_secret):
            response = self.post_stripe_event(event)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        original.refresh_from_db()
        refund = PaymentTransaction.objects.get(
            provider_transaction_id="re_refund_test"
        )
        self.assertEqual(original.status, PaymentTransaction.Status.SUCCEEDED)
        self.assertEqual(refund.status, PaymentTransaction.Status.REFUNDED)
        self.assertEqual(refund.transaction_type, PaymentTransaction.TransactionType.REFUND)

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


class AccountDeletionApiTests(APITestCase):
    deletion_path = "/api/me/delete-account/"
    supabase_url = "https://supabase.example.invalid"

    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.other_user_id = uuid4()
        self.client.force_authenticate(user=self.user)

    def create_owner_records(self, owner_id):
        brand = Brand.objects.create(owner_id=owner_id, name="Deletion test brand")
        post = ContentPost.objects.create(brand=brand, body="Deletion test body")
        subscription = UserSubscription.objects.create(
            owner_id=owner_id,
            provider="stripe",
            provider_customer_id="cus_deletion_test",
            provider_subscription_id=f"sub_{uuid4()}",
            plan_id="pro",
            billing_interval=UserSubscription.BillingInterval.ANNUAL,
            status=UserSubscription.Status.ACTIVE,
        )
        return brand, post, subscription

    def remote_subscriptions(self):
        return [
            SimpleNamespace(
                owner_id=self.user.id,
                provider="stripe",
                provider_subscription_id="sub_first_required",
                status=UserSubscription.Status.ACTIVE,
            ),
            SimpleNamespace(
                owner_id=self.user.id,
                provider="stripe",
                provider_subscription_id="sub_second_required",
                status=UserSubscription.Status.PAST_DUE,
            ),
        ]

    @override_settings(
        SUPABASE_URL="https://supabase.example.invalid",
        SUPABASE_SERVICE_ROLE_KEY="",
        STRIPE_SECRET_KEY="sk_test_unit_test",
    )
    def test_missing_service_role_key_blocks_deletion_before_stripe_calls(self):
        brand, _, subscription = self.create_owner_records(self.user.id)

        with patch(
            "core.views.cancel_stripe_subscription"
        ) as cancel_subscription, patch(
            "core.views.requests.delete"
        ) as admin_delete:
            response = self.client.post(self.deletion_path)

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(response.data["code"], "account_deletion_unavailable")
        cancel_subscription.assert_not_called()
        admin_delete.assert_not_called()
        self.assertTrue(Brand.objects.filter(id=brand.id).exists())
        self.assertTrue(
            UserSubscription.objects.filter(id=subscription.id).exists()
        )

    @override_settings(
        SUPABASE_URL="https://supabase.example.invalid",
        SUPABASE_SERVICE_ROLE_KEY="service-role-test-key",
        STRIPE_SECRET_KEY="sk_test_unit_test",
    )
    def test_stripe_cancellation_failure_prevents_supabase_deletion(self):
        brand, _, subscription = self.create_owner_records(self.user.id)

        with patch(
            "core.views.cancel_stripe_subscription",
            side_effect=stripe.APIConnectionError("test connection failure"),
        ) as cancel_subscription, patch(
            "core.views.requests.delete"
        ) as admin_delete:
            response = self.client.post(self.deletion_path)

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data["code"], "stripe_cancellation_failed")
        self.assertNotIn("connection failure", response.data["detail"])
        cancel_subscription.assert_called_once_with(
            subscription.provider_subscription_id
        )
        admin_delete.assert_not_called()
        self.assertTrue(Brand.objects.filter(id=brand.id).exists())
        self.assertTrue(
            UserSubscription.objects.filter(id=subscription.id).exists()
        )

    @override_settings(
        SUPABASE_URL="https://supabase.example.invalid",
        SUPABASE_SERVICE_ROLE_KEY="service-role-test-key",
        STRIPE_SECRET_KEY="sk_test_unit_test",
    )
    def test_successful_cancellation_deletes_remote_and_local_records(self):
        brand, post, subscription = self.create_owner_records(self.user.id)
        support_request = SupportRequest.objects.create(
            owner_id=self.user.id,
            contact_email="supporter@example.com",
            subject="Account question",
            message="Please help with my account.",
        )

        with patch(
            "core.views.cancel_stripe_subscription"
        ) as cancel_subscription, patch(
            "core.views.requests.delete"
        ) as admin_delete:
            admin_delete.return_value.status_code = 200
            response = self.client.post(self.deletion_path)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["deleted"])
        cancel_subscription.assert_called_once_with(
            subscription.provider_subscription_id
        )
        admin_delete.assert_called_once()
        self.assertEqual(
            admin_delete.call_args.args[0],
            f"{self.supabase_url}/auth/v1/admin/users/{self.user.id}",
        )
        self.assertFalse(Brand.objects.filter(id=brand.id).exists())
        self.assertFalse(ContentPost.objects.filter(id=post.id).exists())
        self.assertFalse(
            UserSubscription.objects.filter(owner_id=self.user.id).exists()
        )
        self.assertFalse(
            SupportRequest.objects.filter(id=support_request.id).exists()
        )

    @override_settings(
        SUPABASE_URL="https://supabase.example.invalid",
        SUPABASE_SERVICE_ROLE_KEY="service-role-test-key",
        STRIPE_SECRET_KEY="sk_test_unit_test",
    )
    def test_all_required_cancellations_run_before_deletion(self):
        subscriptions = self.remote_subscriptions()

        with patch(
            "core.views.UserSubscription.objects.filter"
        ) as subscription_filter, patch(
            "core.views.cancel_stripe_subscription"
        ) as cancel_subscription, patch(
            "core.views.requests.delete"
        ) as admin_delete:
            subscription_filter.return_value.order_by.return_value = subscriptions
            admin_delete.return_value.status_code = 200
            response = self.client.post(self.deletion_path)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [call.args for call in cancel_subscription.call_args_list],
            [("sub_first_required",), ("sub_second_required",)],
        )
        admin_delete.assert_called_once()

    @override_settings(
        SUPABASE_URL="https://supabase.example.invalid",
        SUPABASE_SERVICE_ROLE_KEY="service-role-test-key",
        STRIPE_SECRET_KEY="sk_test_unit_test",
    )
    def test_any_failed_cancellation_stops_deletion(self):
        subscriptions = self.remote_subscriptions()

        def cancel(subscription_id):
            if subscription_id == "sub_second_required":
                raise stripe.APIConnectionError("test connection failure")

        with patch(
            "core.views.UserSubscription.objects.filter"
        ) as subscription_filter, patch(
            "core.views.cancel_stripe_subscription",
            side_effect=cancel,
        ) as cancel_subscription, patch(
            "core.views.requests.delete"
        ) as admin_delete:
            subscription_filter.return_value.order_by.return_value = subscriptions
            response = self.client.post(self.deletion_path)

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data["code"], "stripe_cancellation_failed")
        self.assertEqual(cancel_subscription.call_count, 2)
        admin_delete.assert_not_called()

    @override_settings(
        SUPABASE_URL="https://supabase.example.invalid",
        SUPABASE_SERVICE_ROLE_KEY="service-role-test-key",
        STRIPE_SECRET_KEY="sk_live_unit_test",
    )
    def test_deletion_is_scoped_to_the_authenticated_user_only(self):
        brand, _, subscription = self.create_owner_records(self.user.id)
        other_brand, _, other_subscription = self.create_owner_records(
            self.other_user_id
        )

        with patch(
            "core.views.cancel_stripe_subscription"
        ) as cancel_subscription, patch(
            "core.views.requests.delete"
        ) as admin_delete:
            admin_delete.return_value.status_code = 204
            response = self.client.post(self.deletion_path)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cancel_subscription.assert_called_once_with(
            subscription.provider_subscription_id
        )
        self.assertEqual(
            admin_delete.call_args.args[0],
            f"{self.supabase_url}/auth/v1/admin/users/{self.user.id}",
        )
        self.assertNotIn(str(self.other_user_id), admin_delete.call_args.args[0])
        self.assertFalse(Brand.objects.filter(id=brand.id).exists())
        self.assertTrue(Brand.objects.filter(id=other_brand.id).exists())
        self.assertTrue(
            UserSubscription.objects.filter(id=other_subscription.id).exists()
        )


class SubscriptionPortalApiTests(APITestCase):
    portal_path = "/api/subscription/portal/"
    web_return_url = "https://ibda.example/subscription"

    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.other_user_id = uuid4()
        self.client.force_authenticate(user=self.user)

    def create_past_due_subscription(
        self, owner_id=None, customer_id="cus_portal_test"
    ):
        return UserSubscription.objects.create(
            owner_id=owner_id or self.user.id,
            provider="stripe",
            provider_customer_id=customer_id,
            provider_subscription_id=f"sub_{uuid4()}",
            plan_id="pro",
            billing_interval=UserSubscription.BillingInterval.MONTHLY,
            status=UserSubscription.Status.PAST_DUE,
        )

    def portal_settings(self, **overrides):
        values = {
            "STRIPE_SECRET_KEY": "sk_test_unit_test",
            "STRIPE_PORTAL_RETURN_URL": "",
            "STRIPE_PORTAL_RETURN_URL_WEB": self.web_return_url,
            "STRIPE_PORTAL_RETURN_URL_MOBILE": "",
        }
        values.update(overrides)
        return self.settings(**values)

    def test_authenticated_owner_can_create_a_portal_session(self):
        subscription = self.create_past_due_subscription(
            customer_id="cus_owner_test"
        )
        session = SimpleNamespace(
            id="bps_owner_test",
            url="https://billing.stripe.test/session",
        )

        with self.portal_settings():
            with patch(
                "core.services.payments.portal.create_billing_portal_session",
                return_value=session,
            ) as create_portal:
                response = self.client.post(
                    self.portal_path,
                    {},
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"url": session.url})
        create_portal.assert_called_once_with(
            customer_id="cus_owner_test",
            return_url=self.web_return_url,
        )
        subscription.refresh_from_db()
        self.assertEqual(
            subscription.status,
            UserSubscription.Status.PAST_DUE,
        )

    def test_another_users_subscription_cannot_open_a_portal_session(self):
        self.create_past_due_subscription(
            owner_id=self.other_user_id,
            customer_id="cus_foreign_test",
        )

        with self.portal_settings():
            with patch(
                "core.services.payments.portal.create_billing_portal_session"
            ) as create_portal:
                response = self.client.post(
                    self.portal_path,
                    {},
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["code"],
            "portal_subscription_not_found",
        )
        create_portal.assert_not_called()

    def test_missing_customer_id_is_handled_safely(self):
        self.create_past_due_subscription(customer_id="")

        with self.portal_settings():
            with patch(
                "core.services.payments.portal.create_billing_portal_session"
            ) as create_portal:
                response = self.client.post(
                    self.portal_path,
                    {},
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data["code"],
            "portal_customer_unavailable",
        )
        self.assertIn("Stripe customer", response.data["detail"])
        create_portal.assert_not_called()

    def test_missing_portal_return_url_returns_configuration_error(self):
        self.create_past_due_subscription()

        with self.portal_settings(
            STRIPE_PORTAL_RETURN_URL_WEB="",
            STRIPE_PORTAL_RETURN_URL="",
            STRIPE_PORTAL_RETURN_URL_MOBILE="",
        ):
            with patch(
                "core.services.payments.portal.create_billing_portal_session"
            ) as create_portal:
                response = self.client.post(
                    self.portal_path,
                    {},
                    format="json",
                )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(response.data["code"], "portal_not_configured")
        self.assertIn("return URL", response.data["detail"])
        create_portal.assert_not_called()

    def test_invalid_portal_return_url_is_rejected(self):
        self.create_past_due_subscription()

        with self.portal_settings(
            STRIPE_PORTAL_RETURN_URL_WEB="javascript:alert(1)"
        ):
            with patch(
                "core.services.payments.portal.create_billing_portal_session"
            ) as create_portal:
                response = self.client.post(
                    self.portal_path,
                    {},
                    format="json",
                )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(response.data["code"], "portal_not_configured")
        create_portal.assert_not_called()

    def test_mobile_portal_uses_the_app_scheme_return_url(self):
        self.create_past_due_subscription()
        session = SimpleNamespace(url="https://billing.stripe.test/mobile")

        with self.portal_settings(
            STRIPE_PORTAL_RETURN_URL_MOBILE="ibda://subscription"
        ):
            with patch(
                "core.services.payments.portal.create_billing_portal_session",
                return_value=session,
            ) as create_portal:
                response = self.client.post(
                    self.portal_path,
                    {"platform": "mobile"},
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        create_portal.assert_called_once_with(
            customer_id="cus_portal_test",
            return_url="ibda://subscription",
        )
