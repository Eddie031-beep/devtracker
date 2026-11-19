from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import ical, oauth, views, views_manage

app_name = "web"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("login/github/", oauth.github_login, name="github_login"),
    path("login/github/callback/", oauth.github_callback, name="github_callback"),
    path("perfil/", views.profile, name="profile"),
    path("calendario.ics", ical.calendar_download, name="calendar_download"),
    path("calendario/<str:token>/devtracker.ics", ical.calendar_feed, name="calendar_feed"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Recuperar contraseña (Must Have #1): mismo token de Django que usa la API
    path("recuperar/", views.PasswordResetView.as_view(), name="password_reset"),
    path(
        "recuperar/enviado/",
        auth_views.PasswordResetDoneView.as_view(template_name="web/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "recuperar/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="web/password_reset_confirm.html", success_url=reverse_lazy("web:password_reset_complete")
        ),
        name="password_reset_confirm",
    ),
    path(
        "recuperar/listo/",
        auth_views.PasswordResetCompleteView.as_view(template_name="web/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    path("mis-entregables/", views.my_deliverables, name="my_deliverables"),
    path("proyectos/nuevo/", views_manage.project_create, name="project_create"),
    path("proyectos/<int:pk>/", views.project_detail, name="project"),
    path("proyectos/<int:pk>/editar/", views_manage.project_edit, name="project_edit"),
    path("proyectos/<int:pk>/eliminar/", views_manage.project_delete, name="project_delete"),
    path("proyectos/<int:pk>/integrantes/", views_manage.members, name="members"),
    path("proyectos/<int:pk>/integrantes/<int:member_pk>/", views_manage.member_update, name="member_update"),
    path("proyectos/<int:pk>/integrantes/<int:member_pk>/quitar/", views_manage.member_remove, name="member_remove"),
    path("hitos/<int:pk>/editar/", views_manage.milestone_edit, name="milestone_edit"),
    path("hitos/<int:pk>/eliminar/", views_manage.milestone_delete, name="milestone_delete"),
    path("entregables/<int:pk>/editar/", views_manage.deliverable_edit, name="deliverable_edit"),
    path("entregables/<int:pk>/eliminar/", views_manage.deliverable_delete, name="deliverable_delete"),
    path("proyectos/<int:pk>/hitos/nuevo/", views.milestone_create, name="milestone_create"),
    path("proyectos/<int:pk>/entregables/nuevo/", views.deliverable_create, name="deliverable_create"),
    path("proyectos/<int:pk>/historial/", views.project_history, name="project_history"),
    path("proyectos/<int:pk>/historial/sincronizar/", views.project_history_sync, name="project_history_sync"),
    path("proyectos/<int:pk>/auditoria/", views.project_audit, name="project_audit"),
    path("entregables/<int:pk>/", views.deliverable_detail, name="deliverable"),
    path("entregables/<int:pk>/entregar/", views.deliverable_submit, name="deliverable_submit"),
    path("entregables/<int:pk>/evaluar/", views.deliverable_evaluate, name="deliverable_evaluate"),
    path("entregables/<int:pk>/gemini/", views.deliverable_gemini, name="deliverable_gemini"),
    path("notificaciones/", views.notifications, name="notifications"),
    path("notificaciones/<int:pk>/", views.notification_open, name="notification_open"),
]
