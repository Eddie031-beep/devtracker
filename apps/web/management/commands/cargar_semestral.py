"""Datos de ejemplo de los módulos del examen semestral, creados con las mismas reglas que la web.

    python manage.py cargar_semestral --proyecto 1

Necesita el equipo de `crear_equipo` (líder, integrantes y el evaluador «profesor»). Se puede correr
más de una vez: si el proyecto ya tiene datos de un módulo, ese módulo no se vuelve a cargar.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test.utils import override_settings

from apps.projects.models import Project, ProjectMembership

User = get_user_model()
Role = ProjectMembership.ProjectRole


class Command(BaseCommand):
    help = "Carga incidencias, riesgos, cambios de alcance y reuniones de ejemplo en un proyecto."

    def add_arguments(self, parser):
        parser.add_argument("--proyecto", type=int, default=1, help="id del proyecto (por defecto 1)")

    @transaction.atomic
    @override_settings(NOTIFICATIONS_SEND_EMAIL=False)
    def handle(self, *args, **options):
        project = Project.objects.filter(pk=options["proyecto"]).first()
        if project is None:
            raise CommandError(f"No existe el proyecto {options['proyecto']}.")
        people = self._people(project)
        for name, loader in self.loaders():
            if loader(self, project, people):
                self.stdout.write(self.style.SUCCESS(f"✓ {name}"))
            else:
                self.stdout.write(f"· {name}: el proyecto ya tenía datos, no se tocó.")

    def _people(self, project):
        memberships = list(ProjectMembership.objects.filter(project=project).select_related("user").order_by("user__username"))
        leader = next((m.user for m in memberships if m.role == Role.LEADER), None)
        members = [m.user for m in memberships if m.role == Role.MEMBER]
        evaluator = next((m.user for m in memberships if m.role == Role.EVALUATOR), None)
        if not (leader and len(members) >= 2 and evaluator):
            raise CommandError("El proyecto necesita líder, al menos 2 integrantes y un evaluador (corre crear_equipo).")
        return {"leader": leader, "members": members, "evaluator": evaluator}

    @staticmethod
    def loaders():
        return [("Incidencias", load_issues)]


def load_issues(command, project, people):
    from apps.issues.services import assign_issue, comment_issue, create_issue, transition_issue

    if project.issues.exists():
        return False
    leader, evaluator = people["leader"], people["evaluator"]
    a, b = people["members"][0], people["members"][1]
    c = people["members"][2] if len(people["members"]) > 2 else a

    def issue(reporter, title, priority, description, steps):
        return create_issue(project, reporter, title=title, priority=priority, description=description, steps_to_reproduce=steps)

    one = issue(a, "El webhook duplica commits si GitHub reintenta", "critical",
                "Cuando GitHub reenvía el mismo push aparecen commits repetidos en el historial.",
                "1. Enviar un push al webhook\n2. Reenviar la misma entrega desde GitHub\n3. Ver el historial")
    one = assign_issue(one, leader, b)
    one = transition_issue(one, b, "start")
    one = transition_issue(one, b, "resolve", "Se usa get_or_create por (proyecto, sha).")
    transition_issue(one, evaluator, "verify", "Probado reenviando la entrega: no se duplica.")

    two = issue(b, "La tabla de entregables se corta en el teléfono", "medium",
                "En pantallas de 390 px la tabla del proyecto genera scroll horizontal en toda la página.",
                "1. Abrir el proyecto en un teléfono\n2. Bajar a «Hitos y entregables»")
    two = assign_issue(two, leader, c)
    two = transition_issue(two, c, "start")
    two = transition_issue(two, c, "resolve", "La tabla ahora desplaza dentro de su tarjeta.")
    two = transition_issue(two, evaluator, "reopen", "En el detalle del entregable todavía desborda.")
    comment_issue(two, c, "Reviso la página del entregable.")

    three = issue(c, "El correo de recuperación apunta a localhost", "high",
                  "El enlace del correo para recuperar la contraseña usa http://localhost:8000.",
                  "1. Ir a /recuperar/\n2. Escribir el correo\n3. Abrir el enlace del correo")
    three = assign_issue(three, leader, a)
    transition_issue(three, a, "start")

    issue(a, "El nombre del proyecto largo rompe la migaja de pan", "low",
          "Con nombres de más de 60 caracteres la ruta de navegación se sale de la pantalla.",
          "1. Crear un proyecto con un nombre muy largo\n2. Entrar a una incidencia")
    return True
