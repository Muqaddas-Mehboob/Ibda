from django.urls import path

from .views import BrandListCreateAPIView, health_check

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("brands/", BrandListCreateAPIView.as_view(), name="brand-list-create"),
]
