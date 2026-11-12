from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("proyectos/<int:pk>/reporte/", views.project_report, name="project"),
    path("proyectos/<int:pk>/reporte/entregables.csv", views.deliverables_csv, name="deliverables_csv"),
    path("proyectos/<int:pk>/reporte/integrantes.csv", views.members_csv, name="members_csv"),
    path("proyectos/<int:pk>/reporte/auditoria.csv", views.audit_csv, name="audit_csv"),
]
