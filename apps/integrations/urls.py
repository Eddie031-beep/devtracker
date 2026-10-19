from django.urls import path

from . import views

urlpatterns = [
    path("github/webhook/<int:project_id>/", views.GitHubWebhookView.as_view(), name="github_webhook"),
]
