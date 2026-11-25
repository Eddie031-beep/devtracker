from django.contrib import admin

from .models import Issue, IssueEvent


class IssueEventInline(admin.TabularInline):
    model = IssueEvent
    extra = 0
    can_delete = False
    readonly_fields = ("created_at", "actor", "kind", "from_status", "to_status", "comment")
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    """El flujo (estados, verificación) se maneja desde la web o la API para que quede en el historial."""

    list_display = ("code", "title", "project", "priority", "status", "assignee", "created_at")
    list_filter = ("status", "priority", "project")
    search_fields = ("title", "description")
    readonly_fields = ("status", "resolved_at", "verified_at", "reported_by", "deleted_at")
    inlines = [IssueEventInline]
