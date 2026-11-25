from django.apps import AppConfig


class RisksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.risks"
    verbose_name = "Riesgos del proyecto"

    def ready(self):
        from apps.web.modules import PROJECT_MODULES, ProjectModule

        PROJECT_MODULES.append(
            ProjectModule("risks", "risks:list", "Riesgos", "Matriz de probabilidad e impacto y mitigación.")
        )
