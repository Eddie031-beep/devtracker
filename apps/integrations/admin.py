from django.contrib import admin

from .models import Commit, PullRequest


@admin.register(Commit)
class CommitAdmin(admin.ModelAdmin):
    list_display = ("short_sha", "project", "author_name", "github_username", "author", "deliverable", "committed_at")
    list_filter = ("project",)
    raw_id_fields = ("author", "deliverable")
    search_fields = ("sha", "message", "author_name", "author_email", "github_username")
    date_hierarchy = "committed_at"

    @admin.display(description="SHA")
    def short_sha(self, obj):
        return obj.sha[:7]


@admin.register(PullRequest)
class PullRequestAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "project", "state", "author_login", "author", "deliverable", "opened_at")
    list_filter = ("project", "state")
    raw_id_fields = ("author", "deliverable")
    search_fields = ("title", "body", "author_login", "head_ref")
