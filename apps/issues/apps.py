from django.apps import AppConfig


class IssuesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.issues"
    verbose_name = "Incidencias de software"

    def ready(self):
        from apps.web.modules import PROJECT_MODULES, ProjectModule

        PROJECT_MODULES.append(
            ProjectModule("issues", "issues:list", "Incidencias", "Errores reportados, responsables y verificación.")
        )
