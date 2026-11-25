from django.urls import path

from . import views_web

app_name = "risks"

urlpatterns = [
    path("proyectos/<int:pk>/riesgos/", views_web.risk_list, name="list"),
    path("riesgos/<int:pk>/", views_web.risk_detail, name="detail"),
    path("riesgos/<int:pk>/editar/", views_web.risk_edit, name="edit"),
    path("riesgos/<int:pk>/estado/", views_web.risk_status, name="status"),
    path("riesgos/<int:pk>/mitigacion/", views_web.mitigation_add, name="mitigation_add"),
    path("mitigaciones/<int:pk>/", views_web.mitigation_toggle, name="mitigation_toggle"),
    path("riesgos/<int:pk>/eliminar/", views_web.risk_delete, name="delete"),
]
