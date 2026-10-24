from django.urls import path

from .views import (
    BrandDetailView,
    BrandListCreateView,
    ApprovalActionView,
    ApprovalDetailView,
    ApprovalListView,
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
]