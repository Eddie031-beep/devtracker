from django.urls import path

from . import views, views_workflow

urlpatterns = [
    path("projects/", views.ProjectListCreateView.as_view(), name="project_list_create"),
    path("projects/<int:pk>/", views.ProjectDetailView.as_view(), name="project_detail"),
    path("milestones/", views.MilestoneListCreateView.as_view(), name="milestone_list_create"),
    path("milestones/<int:pk>/", views.MilestoneDetailView.as_view(), name="milestone_detail"),
    path("deliverables/", views.DeliverableListCreateView.as_view(), name="deliverable_list_create"),
    path("deliverables/<int:pk>/", views.DeliverableDetailView.as_view(), name="deliverable_detail"),
        path("deliverables/<int:pk>/submit/", views_workflow.DeliverableSubmitView.as_view(), name="deliverable_submit"),
    path("deliverables/<int:pk>/status/", views_workflow.DeliverableStatusView.as_view(), name="deliverable_status"),
]
