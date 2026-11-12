from django.contrib.auth import views as auth_views
from django.urls import path

from . import oauth, views

app_name = "web"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("login/github/", oauth.github_login, name="github_login"),
    path("login/github/callback/", oauth.github_callback, name="github_callback"),
    path("perfil/", views.profile, name="profile"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("proyectos/<int:pk>/", views.project_detail, name="project"),
    path("entregables/<int:pk>/", views.deliverable_detail, name="deliverable"),
    path("entregables/<int:pk>/entregar/", views.deliverable_submit, name="deliverable_submit"),
    path("entregables/<int:pk>/evaluar/", views.deliverable_evaluate, name="deliverable_evaluate"),
    path("notificaciones/", views.notifications, name="notifications"),
    path("notificaciones/<int:pk>/", views.notification_open, name="notification_open"),
]
