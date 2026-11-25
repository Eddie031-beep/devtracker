from django.contrib import admin

from .models import Mitigation, Risk


class MitigationInline(admin.TabularInline):
    model = Mitigation
    extra = 0
    fields = ("description", "responsible", "due_date", "done", "done_at")
    # Cumplir una medida guarda la fecha y la auditoría: se hace desde la web o la API
    readonly_fields = ("done", "done_at")


@admin.register(Risk)
class RiskAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "project", "probability", "impact", "score", "status", "owner")
    list_filter = ("status", "project")
    search_fields = ("title", "description")
    # El estado cambia desde la web o la API para que quede en la auditoría (y exija comentario al cerrar)
    readonly_fields = ("score", "status", "created_by", "deleted_at")
    inlines = [MitigationInline]
