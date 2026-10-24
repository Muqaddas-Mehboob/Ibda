from django.urls import path

from .views import (
    BrandDetailView,
    BrandListCreateView,
    ApprovalActionView,
    ApprovalDetailView,
    ApprovalListView,
    ContentGenerateView,
    ContentPostDetailView,
    ContentPostListCreateView,
    ContentPostSubmitApprovalView,
    health_check,
    BrandVoiceView
)

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("brands/", BrandListCreateView.as_view(), name="brand-list-create"),
    path(
        "brands/<uuid:id>/",
        BrandDetailView.as_view(),
        name="brand-detail",
    ),
    path(
    "brands/<uuid:brand_id>/voice/",
    BrandVoiceView.as_view(),
    name="brand-voice",
),
    path("approvals/", ApprovalListView.as_view(), name="approval-list"),
    path(
        "approvals/<uuid:id>/",
        ApprovalDetailView.as_view(),
        name="approval-detail",
    ),
    path(
        "approvals/<uuid:approval_id>/<str:action>/",
        ApprovalActionView.as_view(),
        name="approval-action",
    ),
    path(
        "content/generate/",
        ContentGenerateView.as_view(),
        name="content-generate",
    ),
    path(
        "content/posts/",
        ContentPostListCreateView.as_view(),
        name="content-post-list-create",
    ),
    path(
        "content/posts/<uuid:id>/",
        ContentPostDetailView.as_view(),
        name="content-post-detail",
    ),
    path(
        "content/posts/<uuid:post_id>/submit-for-approval/",
        ContentPostSubmitApprovalView.as_view(),
        name="content-post-submit-for-approval",
    ),
]