from django.contrib import admin

from .models import SupportRequest


@admin.register(SupportRequest)
class SupportRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "contact_email", "subject", "status", "created_at")
    list_editable = ("status",)
    list_filter = ("status", "created_at")
    search_fields = ("contact_email", "subject", "message")
    readonly_fields = (
        "id",
        "owner_id",
        "contact_email",
        "subject",
        "message",
        "created_at",
        "updated_at",
    )
    ordering = ("status", "-created_at")
