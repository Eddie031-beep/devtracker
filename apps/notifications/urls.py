from django.urls import path

from . import views

urlpatterns = [
    path("notifications/", views.NotificationListView.as_view(), name="notification_list"),
    path("notifications/read-all/", views.NotificationReadAllView.as_view(), name="notification_read_all"),
    path("notifications/<int:pk>/read/", views.NotificationReadView.as_view(), name="notification_read"),
]
