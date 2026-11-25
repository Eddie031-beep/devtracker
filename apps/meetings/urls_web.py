from django.urls import path

from . import views_web

app_name = "meetings"

urlpatterns = [
    path("proyectos/<int:pk>/reuniones/", views_web.meeting_list, name="list"),
    path("reuniones/<int:pk>/", views_web.meeting_detail, name="detail"),
    path("reuniones/<int:pk>/editar/", views_web.meeting_edit, name="edit"),
    path("reuniones/<int:pk>/eliminar/", views_web.meeting_delete, name="delete"),
    path("reuniones/<int:pk>/acuerdos/", views_web.agreement_add, name="agreement_add"),
    path("acuerdos/<int:pk>/estado/", views_web.agreement_status, name="agreement_status"),
    path("acuerdos/<int:pk>/editar/", views_web.agreement_edit, name="agreement_edit"),
]
