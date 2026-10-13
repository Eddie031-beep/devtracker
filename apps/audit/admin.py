from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Solo lectura: ni siquiera un superusuario puede agregar, editar o borrar registros."""

    list_display = ("created_at", "actor", "action", "project", "target_type", "target_id")
    list_filter = ("action", "target_type")
    search_fields = ("actor__username", "actor__email", "project__name")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]
