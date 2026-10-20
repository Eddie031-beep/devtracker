from django.urls import path

from . import views_commits

urlpatterns = [
    path("projects/<int:pk>/commits/", views_commits.ProjectCommitListView.as_view(), name="project_commits"),
    path(
        "projects/<int:pk>/commits/sync/", views_commits.ProjectCommitSyncView.as_view(), name="project_commits_sync"
    ),
]
