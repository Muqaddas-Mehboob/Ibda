from types import SimpleNamespace
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4
from urllib.error import HTTPError

from rest_framework import status
from rest_framework.test import APITestCase
from django.test import override_settings

from .models import Approval, Brand, BrandVoice, ContentPost


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
