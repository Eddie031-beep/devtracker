from django.urls import path

from . import views

urlpatterns = [
    path("projects/<int:pk>/risks/", views.ProjectRiskListView.as_view(), name="project_risks"),
    path("projects/<int:pk>/risks/matrix/", views.ProjectRiskMatrixView.as_view(), name="project_risk_matrix"),
    path("risks/<int:pk>/", views.RiskDetailView.as_view(), name="risk_detail"),
    path("risks/<int:pk>/status/", views.RiskStatusView.as_view(), name="risk_status"),
    path("risks/<int:pk>/mitigations/", views.RiskMitigationListView.as_view(), name="risk_mitigations"),
    path("mitigations/<int:pk>/done/", views.MitigationDoneView.as_view(), name="mitigation_done"),
]
