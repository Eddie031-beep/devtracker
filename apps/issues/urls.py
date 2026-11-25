from django.urls import path

from . import views

urlpatterns = [
    path("projects/<int:pk>/issues/", views.ProjectIssueListView.as_view(), name="project_issues"),
    path("issues/<int:pk>/", views.IssueDetailView.as_view(), name="issue_detail"),
    path("issues/<int:pk>/assign/", views.IssueAssignView.as_view(), name="issue_assign"),
    path("issues/<int:pk>/transition/", views.IssueTransitionView.as_view(), name="issue_transition"),
    path("issues/<int:pk>/history/", views.IssueHistoryView.as_view(), name="issue_history"),
]
