from django.urls import path

from . import views

urlpatterns = [
    path("projects/<int:pk>/change-requests/", views.ProjectChangeListView.as_view(), name="project_change_requests"),
    path("change-requests/<int:pk>/", views.ChangeDetailView.as_view(), name="change_request_detail"),
    path("change-requests/<int:pk>/decide/", views.ChangeDecideView.as_view(), name="change_request_decide"),
    path("change-requests/<int:pk>/withdraw/", views.ChangeWithdrawView.as_view(), name="change_request_withdraw"),
]
