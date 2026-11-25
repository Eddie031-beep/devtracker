"""Reglas de las incidencias de software. Las vistas (web y API) solo llaman a estas funciones.

Quién hace qué:
- Registrar y comentar: cualquier integrante del proyecto (también el evaluador).
- Editar: quien la reportó o el líder, mientras no esté verificada.
- Asignar responsable y eliminar: el líder (o un admin). El responsable es un estudiante del proyecto.
- Empezar y marcar resuelta: el responsable o el líder.
- Verificar o reabrir: el evaluador del proyecto (o un admin). Reabrir exige el motivo.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import Action
from apps.audit.services import diff, log_action, snapshot
from apps.notifications.models import Notification
from apps.notifications.services import notify, reviewers_of
from apps.projects.access import is_evaluator, is_leader, is_project_member, project_people
from apps.projects.models import ProjectMembership

from .models import Issue, IssueEvent

Status = Issue.Status
Kind = IssueEvent.Kind
EDITABLE_FIELDS = ["title", "description", "steps_to_reproduce", "priority"]

# Transiciones permitidas: acción → (estados de origen, estado destino)
TRANSITIONS = {
    "start": ({Status.OPEN}, Status.IN_PROGRESS),
    "resolve": ({Status.IN_PROGRESS}, Status.RESOLVED),
    "verify": ({Status.RESOLVED}, Status.VERIFIED),
    "reopen": ({Status.RESOLVED, Status.VERIFIED}, Status.OPEN),
}
EVENT_OF = {"start": Kind.STARTED, "resolve": Kind.RESOLVED, "verify": Kind.VERIFIED, "reopen": Kind.REOPENED}


def _name(user):
    return user.get_full_name() or user.username


def _url(issue):
    return reverse("issues:detail", args=[issue.pk])


def _record(issue, actor, kind, comment="", from_status="", to_status="", **data):
    return IssueEvent.objects.create(
        issue=issue, actor=actor, kind=kind, comment=comment or "", from_status=from_status, to_status=to_status, data=data
    )


def _locked(issue):
    """Relee la incidencia bloqueando la fila: las reglas se validan contra el estado actual, no uno viejo."""
    return Issue.objects.select_for_update().select_related("project").get(pk=issue.pk)


def _check_assignee(project, assignee):
    if assignee is None:
        return
    if not ProjectMembership.objects.filter(
        project=project, user=assignee, role__in=[ProjectMembership.ProjectRole.LEADER, ProjectMembership.ProjectRole.MEMBER]
    ).exists():
        raise ValidationError("El responsable debe ser integrante o líder del proyecto.")


# ---------- Permisos (también los usa la interfaz para mostrar u ocultar botones) ----------

def can_edit(user, issue):
    return issue.status != Status.VERIFIED and (issue.reported_by_id == user.pk or is_leader(user, issue.project))


def can_assign(user, issue):
    return issue.status != Status.VERIFIED and is_leader(user, issue.project)


def can_transition(user, issue, action):
    if action not in TRANSITIONS or issue.status not in TRANSITIONS[action][0]:
        return False
    if action in ("start", "resolve"):
        return issue.assignee_id is not None and (issue.assignee_id == user.pk or is_leader(user, issue.project))
    return is_evaluator(user, issue.project)


def allowed_actions(user, issue):
    return [action for action in TRANSITIONS if can_transition(user, issue, action)]


# ---------- Operaciones ----------

@transaction.atomic
def create_issue(project, actor, *, title, description, steps_to_reproduce, priority=Issue.Priority.MEDIUM, assignee=None):
    if not is_project_member(actor, project):
        raise PermissionDenied("Solo los integrantes del proyecto pueden registrar incidencias.")
    if assignee is not None and not is_leader(actor, project):
        raise PermissionDenied("Solo el líder asigna el responsable de una incidencia.")
    if priority not in Issue.Priority.values:
        raise ValidationError("Prioridad no válida.")
    _check_assignee(project, assignee)
    issue = Issue.objects.create(
        project=project, title=title.strip(), description=description.strip(),
        steps_to_reproduce=steps_to_reproduce.strip(), priority=priority, reported_by=actor, assignee=assignee,
    )
    _record(issue, actor, Kind.CREATED, to_status=Status.OPEN)
    log_action(actor, Action.ISSUE_CREATED, issue, changes=diff({}, snapshot(issue, [*EDITABLE_FIELDS, "assignee_id"])))
    if assignee:
        _record(issue, actor, Kind.ASSIGNED, assignee=_name(assignee))
        _notify_assigned(issue, actor)
    # El líder y el evaluador se enteran de cada error nuevo
    notify(
        reviewers_of(project), Notification.Kind.ISSUE, f"Nueva incidencia: {issue.title}",
        f"{_name(actor)} registró {issue.code} ({issue.get_priority_display()}) en {project.name}.",
        _url(issue), project, exclude=actor,
    )
    return issue


@transaction.atomic
def update_issue(issue, actor, **fields):
    issue = _locked(issue)
    if not can_edit(actor, issue):
        raise PermissionDenied("Solo quien la reportó o el líder puede editarla, y no después de verificada.")
    if "priority" in fields and fields["priority"] not in Issue.Priority.values:
        raise ValidationError("Prioridad no válida.")
    before = snapshot(issue, EDITABLE_FIELDS)
    for field in EDITABLE_FIELDS:
        if field in fields:
            value = fields[field]
            setattr(issue, field, value.strip() if isinstance(value, str) else value)
    changes = diff(before, snapshot(issue, EDITABLE_FIELDS))
    if changes:
        issue.save()
        _record(issue, actor, Kind.UPDATED, fields=sorted(changes))
        log_action(actor, Action.ISSUE_UPDATED, issue, changes=changes)
    return issue


@transaction.atomic
def assign_issue(issue, actor, assignee):
    issue = _locked(issue)
    if not can_assign(actor, issue):
        raise PermissionDenied("Solo el líder asigna el responsable, y no después de verificada.")
    _check_assignee(issue.project, assignee)
    if issue.assignee_id == (assignee.pk if assignee else None):
        return issue
    before = {"assignee_id": issue.assignee_id}
    issue.assignee = assignee
    issue.save(update_fields=["assignee", "updated_at"])
    _record(issue, actor, Kind.ASSIGNED, assignee=_name(assignee) if assignee else "")
    log_action(actor, Action.ISSUE_ASSIGNED, issue, changes=diff(before, {"assignee_id": issue.assignee_id}))
    if assignee:
        _notify_assigned(issue, actor)
    return issue


@transaction.atomic
def transition_issue(issue, actor, action, comment=""):
    """Mueve la incidencia por su flujo: start, resolve, verify o reopen."""
    if action not in TRANSITIONS:
        raise ValidationError(f"«{action}» no es una acción válida: usa start, resolve, verify o reopen.")
    issue = _locked(issue)
    sources, target = TRANSITIONS[action]
    if issue.status not in sources:
        raise ValidationError(f"No se puede hacer eso con una incidencia «{issue.get_status_display()}».")
    if not can_transition(actor, issue, action):
        if action in ("start", "resolve"):
            raise PermissionDenied("Solo el responsable de la incidencia o el líder puede hacer esto.")
        raise PermissionDenied("Solo el evaluador del proyecto puede verificar o reabrir una incidencia.")
    comment = (comment or "").strip()
    if action == "resolve" and not comment:
        raise ValidationError("Describe cómo se resolvió.")
    if action == "reopen" and not comment:
        raise ValidationError("Indica por qué se reabre.")

    previous = issue.status
    now = timezone.now()
    issue.status = target
    if action == "resolve":
        issue.resolved_at = now
    elif action == "verify":
        issue.verified_at = now
    elif action == "reopen":
        issue.resolved_at = issue.verified_at = None
    issue.save(update_fields=["status", "resolved_at", "verified_at", "updated_at"])
    _record(issue, actor, EVENT_OF[action], comment, from_status=previous, to_status=target)
    log_action(actor, Action.ISSUE_STATUS_CHANGED, issue, changes={"status": {"before": previous, "after": target}})

    if action == "resolve":
        notify(
            [issue.reported_by, *reviewers_of(issue.project)], Notification.Kind.ISSUE,
            f"Incidencia resuelta: {issue.title}", f"{_name(actor)} marcó {issue.code} como resuelta. Falta verificarla.",
            _url(issue), issue.project, exclude=actor,
        )
    elif action in ("verify", "reopen"):
        verb = "verificó la solución de" if action == "verify" else "reabrió"
        notify(
            [issue.assignee, issue.reported_by], Notification.Kind.ISSUE,
            f"Incidencia {'verificada' if action == 'verify' else 'reabierta'}: {issue.title}",
            f"{_name(actor)} {verb} {issue.code}." + (f" Motivo: {comment}" if action == "reopen" else ""),
            _url(issue), issue.project, exclude=actor,
        )
    return issue


@transaction.atomic
def comment_issue(issue, actor, comment):
    if not is_project_member(actor, issue.project):
        raise PermissionDenied("Solo los integrantes del proyecto pueden comentar.")
    comment = (comment or "").strip()
    if not comment:
        raise ValidationError("El comentario no puede estar vacío.")
    return _record(issue, actor, Kind.COMMENTED, comment)


@transaction.atomic
def delete_issue(issue, actor):
    issue = _locked(issue)
    if not is_leader(actor, issue.project):
        raise PermissionDenied("Solo el líder puede eliminar una incidencia.")
    before = snapshot(issue, [*EDITABLE_FIELDS, "status"])
    issue.delete()  # borrado lógico: el historial se conserva
    log_action(actor, Action.ISSUE_DELETED, issue, changes=diff(before, {}))


def _notify_assigned(issue, actor):
    notify(
        [issue.assignee], Notification.Kind.ISSUE, f"Te asignaron una incidencia: {issue.title}",
        f"{_name(actor)} te asignó {issue.code} ({issue.get_priority_display()}) en {issue.project.name}.",
        _url(issue), issue.project, exclude=actor,
    )


def assignable_users(project):
    """Quienes pueden ser responsables: estudiantes del proyecto (líder o integrante)."""
    return project_people(project, roles=[ProjectMembership.ProjectRole.LEADER, ProjectMembership.ProjectRole.MEMBER])

