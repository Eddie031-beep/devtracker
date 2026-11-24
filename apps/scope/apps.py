from django.apps import AppConfig


class ScopeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.scope"
    verbose_name = "Cambios de alcance"

    def ready(self):
        from apps.web.modules import PROJECT_MODULES, ProjectModule

        PROJECT_MODULES.append(
            ProjectModule("scope", "scope:list", "Cambios de alcance", "Propuestas de los estudiantes y decisión del evaluador.")
        )
