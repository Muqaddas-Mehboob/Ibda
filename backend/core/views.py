from django.http import JsonResponse
from rest_framework.permissions import IsAuthenticated

from rest_framework import generics, permissions
from .authentication import SupabaseAuthentication
from .models import Brand
from .serializers import BrandSerializer

def health_check(request):
    return JsonResponse({
        "status": "ok",
        "service": "Ibda API",
        "message": "Django backend is running.",
    })


class BrandListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = BrandSerializer
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Brand.objects.filter(owner_id=self.request.user.id)

    def perform_create(self, serializer):
        serializer.save(owner_id=self.request.user.id)

class BrandListCreateView(generics.ListCreateAPIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BrandSerializer

    def get_queryset(self):
        return Brand.objects.filter(
            owner_id=self.request.user.id
        )

    def perform_create(self, serializer):
        serializer.save(owner_id=self.request.user.id)


class BrandDetailView(generics.RetrieveUpdateDestroyAPIView):
    authentication_classes = [SupabaseAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BrandSerializer
    lookup_field = "id"

    def get_queryset(self):
        return Brand.objects.filter(
            owner_id=self.request.user.id
        )