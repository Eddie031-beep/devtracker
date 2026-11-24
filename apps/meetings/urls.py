from django.urls import path

from . import views

urlpatterns = [
    path("projects/<int:pk>/meetings/", views.ProjectMeetingListView.as_view(), name="project_meetings"),
    path("projects/<int:pk>/agreements/", views.ProjectAgreementListView.as_view(), name="project_agreements"),
    path("meetings/<int:pk>/", views.MeetingDetailView.as_view(), name="meeting_detail"),
    path("meetings/<int:pk>/agreements/", views.MeetingAgreementListView.as_view(), name="meeting_agreements"),
    path("agreements/<int:pk>/", views.AgreementDetailView.as_view(), name="agreement_detail"),
]
