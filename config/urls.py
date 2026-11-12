from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    # Interfaz web: dashboard por rol, proyectos y entregables (Etapa 3)
    path("", include("apps.web.urls")),
    path("admin/", admin.site.urls),
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.projects.urls")),
    path("api/", include("apps.projects.urls_members")),
    path("api/", include("apps.audit.urls")),
    path("api/", include("apps.integrations.urls_projects")),
    path("api/", include("apps.evaluations.urls")),
    path("api/", include("apps.metrics.urls")),
    path("api/", include("apps.notifications.urls")),
    path("api/integrations/", include("apps.integrations.urls")),
    # Documentación de la API: esquema OpenAPI y Swagger UI (públicos, solo describen los endpoints)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api_docs"),
]
