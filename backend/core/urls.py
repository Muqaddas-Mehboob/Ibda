from django.urls import include, path

from .views import BrandDetailView, BrandListCreateAPIView, BrandListCreateView, health_check

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("brands/", BrandListCreateView.as_view(), name="brand-list-create"),
    path(
        "brands/<uuid:id>/",
        BrandDetailView.as_view(),
        name="brand-detail",
    ),
]
