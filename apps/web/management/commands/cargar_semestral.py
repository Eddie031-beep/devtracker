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
        return [("Incidencias", load_issues), ("Riesgos", load_risks), ("Cambios de alcance", load_changes),
                ("Reuniones y acuerdos", load_meetings)]


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


def load_risks(command, project, people):
    from datetime import timedelta

    from django.utils import timezone

    from apps.risks.services import add_mitigation, change_status, create_risk, set_mitigation_done

    if project.risks.exists():
        return False
    leader = people["leader"]
    a, b = people["members"][0], people["members"][1]
    c = people["members"][2] if len(people["members"]) > 2 else a
    soon = timezone.localdate() + timedelta(days=5)

    def risk(title, description, probability, impact, owner):
        return create_risk(project, leader, title=title, description=description,
                           probability=probability, impact=impact, owner=owner)

    one = risk("Railway suspende el plan gratuito antes de la presentación",
               "Si se agotan los créditos, la demo en línea deja de responder el día del examen.", 2, 3, leader)
    first = add_mitigation(one, leader, description="Tener la app corriendo en local como respaldo.", responsible=a, due_date=soon)
    set_mitigation_done(first, a)
    add_mitigation(one, leader, description="Revisar el consumo de créditos cada semana.", responsible=leader)

    two = risk("Un integrante no puede seguir en el curso",
               "Sus módulos quedarían sin responsable y habría que repartirlos.", 1, 3, b)
    add_mitigation(two, b, description="Documentar cada módulo en el README y en los PR.", responsible=b, due_date=soon)

    three = risk("Conflicto de horarios para las reuniones",
                 "No coincidimos todos para revisar avances.", 3, 1, c)
    change_status(three, c, "occurred", "La reunión del martes se canceló por falta de quórum.")
    add_mitigation(three, c, description="Reuniones cortas en línea los domingos.", responsible=c)

    four = risk("Cambios en la API de GitHub", "GitHub cambia el formato del webhook y deja de entregar los PR.", 1, 2, a)
    change_status(four, a, "closed", "Se fijó la versión de la API y hay pruebas del webhook.")

    risk("Retraso en las evaluaciones del profesor",
         "Si las revisiones llegan tarde no da tiempo de corregir antes del cierre.", 2, 2, b)
    return True


def load_changes(command, project, people):
    from apps.scope.services import decide_change, propose_change, project_deliverables, withdraw_change

    if project.change_requests.exists():
        return False
    evaluator = people["evaluator"]
    a, b = people["members"][0], people["members"][1]
    deliverables = list(project_deliverables(project))
    last = deliverables[-2:] if len(deliverables) >= 2 else deliverables

    def propose(actor, title, description, justification, impact, level, refs=()):
        return propose_change(project, actor, title=title, description=description, justification=justification,
                              expected_impact=impact, impact_level=level, affected_deliverables=refs)

    one = propose(a, "Exportar el reporte también en Excel",
                  "Agregar una descarga .xlsx con las hojas de entregables, integrantes y auditoría.",
                  "El profesor revisa las notas en hojas de cálculo y el CSV pierde los acentos en Excel.",
                  "Un día de trabajo; no cambia fechas de entrega.", "low", last[:1])
    decide_change(one, evaluator, "approved", "Aprobado: no afecta el cronograma.")

    two = propose(b, "Quitar la integración con Gemini",
                  "No incluir las sugerencias automáticas con Gemini en la entrega final.",
                  "La clave de la API tiene límite diario y falla en la demo.",
                  "Se libera tiempo para pruebas; se pierde una función opcional.", "medium", last)
    decide_change(two, evaluator, "rejected", "Se mantiene como opcional: basta con ocultarla si no hay clave.")

    propose(a, "Mover la presentación final una semana",
            "Pasar la presentación final al viernes siguiente.",
            "Coincide con el parcial de otra materia de todo el grupo.",
            "Una semana más para pulir; el evaluador tendría que reprogramar.", "high", last[-1:])

    three = propose(b, "Agregar modo sin conexión", "Que la app funcione sin internet.",
                    "Algunas aulas no tienen buena señal.", "Demasiado trabajo para el tiempo que queda.", "high")
    withdraw_change(three, b)
    return True


def load_meetings(command, project, people):
    from datetime import timedelta

    from django.utils import timezone

    from apps.meetings.services import add_agreement, create_meeting, update_agreement

    if project.meetings.exists():
        return False
    leader, evaluator = people["leader"], people["evaluator"]
    members = people["members"]
    a, b = members[0], members[1]
    c = members[2] if len(members) > 2 else a
    now, today = timezone.now(), timezone.localdate()

    first = create_meeting(
        project, leader, title="Arranque del examen semestral", held_at=now - timedelta(days=12),
        location="Aula 3-205", participants=[leader, *members, evaluator],
        summary="Se leyó el enunciado del semestral y se acordó un PR por módulo.\n"
                "Tailwind se compila sin Node para no complicar Railway.\n"
                "El profesor pidió que cada decisión quede en la auditoría.",
    )
    done = add_agreement(first, leader, description="Preparar la base con Tailwind y el registro de módulos.",
                         responsible=leader, due_date=today - timedelta(days=9))
    update_agreement(done, leader, status="done")
    # Queda pendiente con la fecha vencida, para ver el aviso «Vencido» en la lista
    add_agreement(first, leader, description="Escribir las pruebas del flujo de incidencias.",
                  responsible=a, due_date=today - timedelta(days=2))
    add_agreement(first, leader, description="Revisar la matriz de riesgos con datos reales.",
                  responsible=b, due_date=today + timedelta(days=3))

    second = create_meeting(
        project, a, title="Revisión de avance", held_at=now - timedelta(days=3), location="Google Meet",
        participants=[leader, *members],
        summary="Incidencias y riesgos ya funcionan. Falta probar cambios de alcance en el teléfono.",
    )
    ok = add_agreement(second, a, description="Probar todas las pantallas a 390 px en modo oscuro.",
                       responsible=c, due_date=today + timedelta(days=1))
    update_agreement(ok, c, status="done")
    add_agreement(second, leader, description="Ensayar la demostración del examen.", responsible=leader,
                  due_date=today + timedelta(days=4))
    return True
