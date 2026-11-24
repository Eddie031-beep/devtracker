from django.apps import AppConfig


class MeetingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.meetings"
    verbose_name = "Reuniones y acuerdos"

    def ready(self):
        from apps.web.modules import PROJECT_MODULES, ProjectModule

        PROJECT_MODULES.append(
            ProjectModule("meetings", "meetings:list", "Reuniones", "Actas con participantes y acuerdos con responsable.")
        )
