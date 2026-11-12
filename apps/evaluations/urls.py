from django.urls import path

from . import views

urlpatterns = [
    path("deliverables/<int:pk>/evaluate/", views.DeliverableEvaluateView.as_view(), name="deliverable_evaluate"),
    path(
        "deliverables/<int:pk>/evaluations/",
        views.DeliverableEvaluationListView.as_view(),
        name="deliverable_evaluations",
    ),
]
