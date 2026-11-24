from django.urls import path

from . import views_web

app_name = "issues"

urlpatterns = [
    path("proyectos/<int:pk>/incidencias/", views_web.issue_list, name="list"),
    path("incidencias/<int:pk>/", views_web.issue_detail, name="detail"),
    path("incidencias/<int:pk>/editar/", views_web.issue_edit, name="edit"),
    path("incidencias/<int:pk>/asignar/", views_web.issue_assign, name="assign"),
    path("incidencias/<int:pk>/estado/", views_web.issue_transition, name="transition"),
    path("incidencias/<int:pk>/comentar/", views_web.issue_comment, name="comment"),
    path("incidencias/<int:pk>/eliminar/", views_web.issue_delete, name="delete"),
]
