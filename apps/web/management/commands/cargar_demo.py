from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import Action
from apps.audit.services import diff, log_action, snapshot
from apps.evaluations.services import evaluate_deliverable
from apps.projects.models import Deliverable, Milestone, Project, ProjectMembership
from apps.projects.services import submit_deliverable

User = get_user_model()
Role = ProjectMembership.ProjectRole
REPO = "https://github.com/Eddie031-beep/devtracker"
MARK = "Etapa 3: Métricas y evaluación"

# (hito, días hasta el vencimiento del hito, [(entregable, días de vencimiento, qué pasa)])
# Qué pasa: None = pendiente; "on_time"/"late" = entregado; con nota y decisión = evaluado
PLAN = [
    ("Etapa 1: Seguridad y base", -50, [
        ("Autenticación y RBAC", -52, ("on_time", "approved", 95)),
        ("Permisos por proyecto", -52, ("on_time", "approved", 90)),
        ("CRUD de proyectos", -51, ("on_time", "approved", 88)),
        ("Integrantes y responsabilidades", -51, ("late", "approved", 78)),
        ("Flujo de estados", -50, ("on_time", "approved", 92)),
    ]),
    ("Etapa 2: Trazabilidad", -20, [
        ("Despliegue en Railway", -22, ("on_time", "approved", 94)),
        ("Auditoría inmutable", -21, ("on_time", "rejected", 65)),
        ("Historial de versiones", -21, ("on_time", "approved", 89)),
        ("Webhook de GitHub", -20, ("late", "approved", 80)),
        ("Sincronización de commits", -20, ("on_time", None, None)),
    ]),
    (MARK, 10, [
        ("Métricas por integrante", 8, ("on_time", None, None)),
        ("Dashboard por rol", 9, None),
        ("Evaluación de entregables", 10, None),
        ("Documentación de la API", 10, None),
        ("Presentación final", -1, None),
    ]),
]


class Command(BaseCommand):
    help = (
        "Carga hitos, entregables, entregas y evaluaciones de ejemplo en un proyecto existente para la demo. "
        "Usa el flujo real, así que también llena la auditoría y el historial de versiones. Si ya se cargó, no hace nada."
    )

    def add_arguments(self, parser):
        parser.add_argument("--proyecto", type=int, default=1, help="id del proyecto (por defecto 1)")

    @transaction.atomic
    def handle(self, *args, **options):
        project = Project.objects.filter(pk=options["proyecto"]).first()
        if project is None:
            raise CommandError(f"No existe el proyecto {options['proyecto']}.")
        if project.milestones.filter(title=MARK).exists():
            self.stdout.write("Los datos de ejemplo ya estaban cargados: no se creó nada.")
            return

        memberships = ProjectMembership.objects.filter(project=project).select_related("user")
        leaders = [m.user for m in memberships if m.role == Role.LEADER]
        members = [m.user for m in memberships if m.role == Role.MEMBER] or leaders
        if not leaders or not members:
            raise CommandError("El proyecto necesita al menos un líder y un integrante.")
        reviewer = next((m.user for m in memberships if m.role == Role.EVALUATOR), leaders[0])
        now = timezone.now()

        created = 0
        turn = 0
        for title, milestone_days, deliverables in PLAN:
            milestone = Milestone.objects.create(project=project, title=title, due_date=(now + timedelta(days=milestone_days)).date())
            log_action(leaders[0], Action.MILESTONE_CREATED, milestone, changes=diff({}, snapshot(milestone, ("title", "due_date"))))
            for name, due_days, outcome in deliverables:
                assignee = members[turn % len(members)]
                turn += 1
                deliverable = Deliverable.objects.create(milestone=milestone, title=name, due_at=now + timedelta(days=due_days))
                deliverable.assignees.set([assignee])
                log_action(leaders[0], Action.DELIVERABLE_CREATED, deliverable, changes=diff({}, snapshot(deliverable, ("title", "due_at"))))
                created += 1
                if outcome is None:
                    continue
                timing, decision, score = outcome
                submitted_at = deliverable.due_at + (timedelta(hours=6) if timing == "late" else -timedelta(days=1))
                slug = name.lower().replace(" ", "-")
                submit_deliverable(deliverable, assignee, at=submitted_at, url=f"{REPO}/tree/develop#{slug}", comment="Entrega")
                if decision is None:
                    continue
                if decision == "rejected":
                    # Rechazada y corregida: queda con dos versiones y dos evaluaciones
                    evaluate_deliverable(deliverable, reviewer, "rejected", score, "Faltan pruebas de los casos de error.")
                    submit_deliverable(deliverable, assignee, at=submitted_at + timedelta(hours=12), url=f"{REPO}/tree/develop#{slug}-v2", comment="Corrige observaciones")
                    evaluate_deliverable(deliverable, reviewer, "approved", 87, "Corregido.")
                else:
                    evaluate_deliverable(deliverable, reviewer, decision, score, "Buen trabajo.")

        self.stdout.write(self.style.SUCCESS(f"✓ {project.name}: {len(PLAN)} hitos y {created} entregables de ejemplo."))
