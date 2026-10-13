from django.urls import path

from . import views

urlpatterns = [
    path("projects/<int:pk>/audit/", views.ProjectAuditView.as_view(), name="project_audit"),
]
