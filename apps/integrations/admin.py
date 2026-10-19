from django.contrib import admin

from .models import Commit


@admin.register(Commit)
class CommitAdmin(admin.ModelAdmin):
    list_display = ("short_sha", "project", "author_name", "github_username", "committed_at")
    list_filter = ("project",)
    search_fields = ("sha", "message", "author_name", "author_email", "github_username")
    date_hierarchy = "committed_at"

    @admin.display(description="SHA")
    def short_sha(self, obj):
        return obj.sha[:7]
