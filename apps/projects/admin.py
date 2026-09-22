from django.contrib import admin

from .models import Deliverable, Milestone, Project, ProjectMembership


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
