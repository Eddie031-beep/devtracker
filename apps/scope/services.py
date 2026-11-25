"""Reglas de las solicitudes de cambio de alcance.

- Proponer: los estudiantes del proyecto (líder o integrante).
- Editar o retirar: quien la propuso, solo mientras está pendiente.
- Aprobar o rechazar: el evaluador del proyecto (o un admin), con un comentario que explique la decisión.
- Nada de esto modifica los entregables: la solicitud solo los referencia. Si se aprueba, el líder los
  ajusta a mano (y eso queda en la auditoría como cualquier otra edición).
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import Action
from apps.audit.services import diff, log_action, snapshot
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.projects.access import is_evaluator, is_leader, is_student, project_people
from apps.projects.models import Deliverable, ProjectMembership

from .models import ChangeRequest

Status = ChangeRequest.Status
FIELDS = ["title", "description", "justification", "expected_impact", "impact_level"]
DECISIONS = {"approved": Status.APPROVED, "rejected": Status.REJECTED}


def _name(user):
    return user.get_full_name() or user.username


def _url(change):
    return reverse("scope:detail", args=[change.pk])


def _locked(change):
    return ChangeRequest.objects.select_for_update().select_related("project", "proposed_by").get(pk=change.pk)


def project_deliverables(project):
    """Entregables vivos del proyecto (los que se pueden mencionar en una solicitud)."""
    return Deliverable.objects.filter(
        milestone__project=project, milestone__deleted_at__isnull=True
    ).select_related("milestone").order_by("milestone__due_date", "due_at")


def _check_deliverables(project, deliverables):
    deliverables = list(deliverables or [])
    allowed = set(project_deliverables(project).values_list("pk", flat=True))
    if any(d.pk not in allowed for d in deliverables):
        raise ValidationError("Solo puedes referenciar entregables de este proyecto.")
    return deliverables


def _check_text(title, description, justification, expected_impact, impact_level):
    if len((title or "").strip()) < 5:
        raise ValidationError("El título debe tener al menos 5 caracteres.")
    for label, text in (("la descripción", description), ("la justificación", justification), ("el impacto esperado", expected_impact)):
        if len((text or "").strip()) < 10:
            raise ValidationError(f"Completa {label} (al menos 10 caracteres).")
    if impact_level not in ChangeRequest.ImpactLevel.values:
        raise ValidationError("Nivel de impacto no válido.")


# ---------- Permisos ----------

def can_propose(user, project):
    return is_student(user, project) or is_leader(user, project)


def can_edit(user, change):
    return change.is_pending and change.proposed_by_id == user.pk


def can_decide(user, change):
    return change.is_pending and is_evaluator(user, change.project)


# ---------- Operaciones ----------

@transaction.atomic
def propose_change(project, actor, *, title, description, justification, expected_impact,
                   impact_level=ChangeRequest.ImpactLevel.MEDIUM, affected_deliverables=()):
    if not can_propose(actor, project):
        raise PermissionDenied("Solo los estudiantes del proyecto proponen cambios de alcance.")
    _check_text(title, description, justification, expected_impact, impact_level)
    deliverables = _check_deliverables(project, affected_deliverables)
    change = ChangeRequest.objects.create(
        project=project, title=title.strip(), description=description.strip(), justification=justification.strip(),
        expected_impact=expected_impact.strip(), impact_level=impact_level, proposed_by=actor,
    )
    change.affected_deliverables.set(deliverables)
    log_action(actor, Action.CHANGE_REQUESTED, change, changes={
        **diff({}, snapshot(change, FIELDS)),
        "affected_deliverables": {"before": None, "after": sorted(d.pk for d in deliverables)},
    })
    evaluators = project_people(project, roles=[ProjectMembership.ProjectRole.EVALUATOR])
    leaders = project_people(project, roles=[ProjectMembership.ProjectRole.LEADER])
    notify(
        [*evaluators, *leaders], Notification.Kind.CHANGE_REQUEST, f"Cambio de alcance por decidir: {change.title}",
        f"{_name(actor)} propone {change.code} (impacto {change.get_impact_level_display().lower()}) en {project.name}.",
        _url(change), project, exclude=actor,
    )
    return change


@transaction.atomic
def update_change(change, actor, affected_deliverables=None, **fields):
    change = _locked(change)
    if not can_edit(actor, change):
        raise PermissionDenied("Solo quien la propuso puede editarla, y solo mientras está pendiente.")
    values = {f: fields.get(f, getattr(change, f)) for f in FIELDS}
    _check_text(**values)
    before = snapshot(change, FIELDS)
    before_deliverables = sorted(change.affected_deliverables.values_list("pk", flat=True))
    for field, value in values.items():
        setattr(change, field, value.strip() if isinstance(value, str) else value)
    changes = diff(before, snapshot(change, FIELDS))
    if affected_deliverables is not None:
        deliverables = _check_deliverables(change.project, affected_deliverables)
        after = sorted(d.pk for d in deliverables)
        if after != before_deliverables:
            change.affected_deliverables.set(deliverables)
            changes["affected_deliverables"] = {"before": before_deliverables, "after": after}
    if changes:
        change.save()
        log_action(actor, Action.CHANGE_UPDATED, change, changes=changes)
    return change


@transaction.atomic
def withdraw_change(change, actor):
    change = _locked(change)
    if not can_edit(actor, change):
        raise PermissionDenied("Solo quien la propuso puede retirarla, y solo mientras está pendiente.")
    change.status = Status.WITHDRAWN
    change.save(update_fields=["status", "updated_at"])
    log_action(actor, Action.CHANGE_WITHDRAWN, change, changes={"status": {"before": Status.PENDING, "after": Status.WITHDRAWN}})
    return change


@transaction.atomic
def decide_change(change, actor, decision, comment):
    """El evaluador aprueba o rechaza. La decisión queda registrada y la solicitud ya no cambia."""
    if decision not in DECISIONS:
        raise ValidationError("La decisión debe ser «approved» o «rejected».")
    change = _locked(change)
    if not change.is_pending:
        raise ValidationError(f"La solicitud ya está «{change.get_status_display()}»: no se puede decidir de nuevo.")
    if not is_evaluator(actor, change.project):
        raise PermissionDenied("Solo el evaluador del proyecto aprueba o rechaza cambios de alcance.")
    comment = (comment or "").strip()
    if len(comment) < 5:
        raise ValidationError("Explica la decisión (al menos 5 caracteres).")
    change.status = DECISIONS[decision]
    change.decided_by = actor
    change.decided_at = timezone.now()
    change.decision_comment = comment
    change.save(update_fields=["status", "decided_by", "decided_at", "decision_comment", "updated_at"])
    log_action(actor, Action.CHANGE_DECIDED, change, changes={
        "status": {"before": Status.PENDING, "after": change.status},
        "decision_comment": {"before": None, "after": comment},
    })
    leaders = project_people(change.project, roles=[ProjectMembership.ProjectRole.LEADER])
    verb = "aprobó" if change.status == Status.APPROVED else "rechazó"
    notify(
        [change.proposed_by, *leaders], Notification.Kind.CHANGE_REQUEST,
        f"Solicitud de cambio {change.get_status_display().lower()}: {change.title}",
        f"{_name(actor)} {verb} {change.code}: {comment}",
        _url(change), change.project, exclude=actor,
    )
    return change
