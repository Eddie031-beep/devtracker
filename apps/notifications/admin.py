from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "recipient", "kind", "title", "read_at")
    list_filter = ("kind",)
    search_fields = ("recipient__username", "title")
    raw_id_fields = ("recipient", "project")
    date_hierarchy = "created_at"
