from django.urls import path

from . import views

urlpatterns = [
    path("projects/<int:pk>/metrics/", views.ProjectMetricsView.as_view(), name="project_metrics"),
]
