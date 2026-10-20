from django.contrib import admin

from .models import Deliverable, DeliverableVersion, Milestone, Project, ProjectMembership


class MembershipInline(admin.TabularInline):
    model = ProjectMembership
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "start_date", "end_date", "deleted_at")
    inlines = [MembershipInline]


@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "due_date")


@admin.register(Deliverable)
class DeliverableAdmin(admin.ModelAdmin):
    list_display = ("title", "milestone", "due_at", "status", "is_late")
    list_filter = ("status", "is_late")


@admin.register(DeliverableVersion)
class DeliverableVersionAdmin(admin.ModelAdmin):
    """Solo lectura: las versiones de entregables son inmutables."""

    list_display = ("deliverable", "number", "author", "created_at", "url")
    list_filter = ("created_at",)
    search_fields = ("deliverable__title", "author__username", "author__email", "comment")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]
