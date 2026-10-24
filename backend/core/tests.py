from types import SimpleNamespace
from uuid import uuid4

from rest_framework import status
from rest_framework.test import APITestCase

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
