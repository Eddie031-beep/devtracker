from django.urls import path

from . import views_web

app_name = "scope"

urlpatterns = [
    path("proyectos/<int:pk>/cambios/", views_web.change_list, name="list"),
    path("cambios/<int:pk>/", views_web.change_detail, name="detail"),
    path("cambios/<int:pk>/editar/", views_web.change_edit, name="edit"),
    path("cambios/<int:pk>/retirar/", views_web.change_withdraw, name="withdraw"),
    path("cambios/<int:pk>/decidir/", views_web.change_decide, name="decide"),
]
