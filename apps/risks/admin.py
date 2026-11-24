from django.contrib import admin

from .models import Mitigation, Risk


class MitigationInline(admin.TabularInline):
    model = Mitigation
    extra = 0
    fields = ("description", "responsible", "due_date", "done")


@admin.register(Risk)
class RiskAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "project", "probability", "impact", "score", "status", "owner")
    list_filter = ("status", "project")
    search_fields = ("title", "description")
    readonly_fields = ("score", "created_by", "deleted_at")
    inlines = [MitigationInline]
