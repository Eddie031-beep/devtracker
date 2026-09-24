from django.urls import path

from . import views_members

urlpatterns = [
    path("projects/<int:pk>/members/", views_members.ProjectMembersView.as_view(), name="project_members"),
    path(
        "projects/<int:pk>/members/<int:membership_id>/",
        views_members.ProjectMemberDetailView.as_view(),
        name="project_member_detail",
    ),
    path(
        "deliverables/<int:pk>/assignees/",
        views_members.DeliverableAssigneesView.as_view(),
        name="deliverable_assignees",
    ),
]
