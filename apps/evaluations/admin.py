from django.contrib import admin

from .models import Evaluation


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    """Solo lectura: las evaluaciones son inmutables."""

    list_display = ("deliverable", "decision", "score", "evaluator", "created_at")
    list_filter = ("decision",)
    search_fields = ("deliverable__title", "evaluator__username", "feedback")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]
