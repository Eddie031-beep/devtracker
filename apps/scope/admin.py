from django.contrib import admin

from .models import ChangeRequest


@admin.register(ChangeRequest)
class ChangeRequestAdmin(admin.ModelAdmin):
    """Solo lectura: las solicitudes se proponen y deciden desde la web o la API para dejar rastro."""

    list_display = ("code", "title", "project", "status", "proposed_by", "decided_by", "created_at")
    list_filter = ("status", "impact_level", "project")
    search_fields = ("title", "description", "justification")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
