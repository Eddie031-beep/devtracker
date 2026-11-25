from django.contrib import admin

from .models import Agreement, Meeting


class AgreementInline(admin.TabularInline):
    model = Agreement
    extra = 0
    fields = ("description", "responsible", "due_date", "status", "completed_at", "completed_by")
    # Cumplir un acuerdo guarda quién y cuándo y va a la auditoría: se hace desde la web o la API
    readonly_fields = ("status", "completed_at", "completed_by")


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "held_at", "created_by")
    list_filter = ("project",)
    search_fields = ("title", "summary")
    filter_horizontal = ("participants",)
    readonly_fields = ("created_by", "deleted_at")
    inlines = [AgreementInline]
