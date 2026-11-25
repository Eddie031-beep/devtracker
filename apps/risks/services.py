"""Reglas de los riesgos del proyecto.

Quién hace qué:
- Registrar: los estudiantes del proyecto (líder o integrante). El evaluador los consulta.
- Editar, cambiar el estado y registrar medidas de mitigación: el líder o el responsable del riesgo.
- Marcar una medida como cumplida: su responsable, el responsable del riesgo o el líder.
- Eliminar (lógico): el líder.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import Action
from apps.audit.services import diff, log_action, snapshot
from apps.notifications.models import Notification
from apps.notifications.services import notify, reviewers_of
from apps.projects.access import is_leader, is_student, project_people
from apps.projects.models import ProjectMembership

from . import matrix
from .models import Mitigation, Risk

Status = Risk.Status
FIELDS = ["title", "description", "probability", "impact", "owner_id"]

# Estado → estados a los que puede pasar
TRANSITIONS = {
    Status.IDENTIFIED: {Status.MITIGATING, Status.OCCURRED, Status.CLOSED},
    Status.MITIGATING: {Status.IDENTIFIED, Status.OCCURRED, Status.CLOSED},
    Status.OCCURRED: {Status.MITIGATING, Status.CLOSED},
    Status.CLOSED: {Status.IDENTIFIED},  # reabrir si vuelve a aparecer
}


def _name(user):
    return user.get_full_name() or user.username


def _url(risk):
    return reverse("risks:detail", args=[risk.pk])


def _locked(risk):
    return Risk.objects.select_for_update().select_related("project", "owner").get(pk=risk.pk)


def owner_candidates(project):
    """Responsables posibles: estudiantes del proyecto (líder o integrante)."""
    return project_people(project, roles=[ProjectMembership.ProjectRole.LEADER, ProjectMembership.ProjectRole.MEMBER])


def _check_owner(project, owner):
    if owner is None or not owner_candidates(project).filter(pk=owner.pk).exists():
        raise ValidationError("El responsable debe ser integrante o líder del proyecto.")


def _check_scale(probability, impact):
    if probability not in (1, 2, 3):
        raise ValidationError("La probabilidad debe ser 1, 2 o 3.")
    if impact not in (1, 2, 3):
        raise ValidationError("El impacto debe ser 1, 2 o 3.")


# ---------- Permisos ----------

def can_manage(user, risk):
    return is_leader(user, risk.project) or risk.owner_id == user.pk


def can_complete(user, mitigation):
    return mitigation.responsible_id == user.pk or can_manage(user, mitigation.risk)


def next_statuses(risk):
    return [(value, label) for value, label in Status.choices if value in TRANSITIONS[risk.status]]


# ---------- Operaciones ----------

@transaction.atomic
def create_risk(project, actor, *, title, description, probability, impact, owner):
    if not (is_student(actor, project) or is_leader(actor, project)):  # is_leader incluye al admin global
        raise PermissionDenied("Solo los estudiantes del proyecto registran riesgos.")
    _check_scale(probability, impact)
    _check_owner(project, owner)
    risk = Risk.objects.create(
        project=project, title=title.strip(), description=description.strip(), probability=probability,
        impact=impact, owner=owner, created_by=actor,
    )
    log_action(actor, Action.RISK_CREATED, risk, changes=diff({}, snapshot(risk, [*FIELDS, "score"])))
    _notify_new(risk, actor)
    return risk


@transaction.atomic
def update_risk(risk, actor, **fields):
    risk = _locked(risk)
    if not can_manage(actor, risk):
        raise PermissionDenied("Solo el líder o el responsable del riesgo pueden editarlo.")
    _check_scale(fields.get("probability", risk.probability), fields.get("impact", risk.impact))
    if "owner" in fields:
        _check_owner(risk.project, fields["owner"])
    before = snapshot(risk, [*FIELDS, "score"])
    old_level, old_owner = risk.level, risk.owner_id
    for field in ("title", "description", "probability", "impact", "owner"):
        if field in fields:
            value = fields[field]
            setattr(risk, field, value.strip() if isinstance(value, str) else value)
    risk.score = matrix.score(risk.probability, risk.impact)
    changes = diff(before, snapshot(risk, [*FIELDS, "score"]))
    if changes:
        risk.save()
        log_action(actor, Action.RISK_UPDATED, risk, changes=changes)
        if risk.owner_id != old_owner:
            _notify_owner(risk, actor)
        if risk.level == matrix.HIGH and old_level != matrix.HIGH:
            _notify_reviewers(risk, actor, f"Riesgo alto: {risk.title}", f"{risk.code} subió a nivel alto ({risk.score}/9).")
    return risk


@transaction.atomic
def change_status(risk, actor, status, comment=""):
    risk = _locked(risk)
    if not can_manage(actor, risk):
        raise PermissionDenied("Solo el líder o el responsable del riesgo cambian su estado.")
    if status not in Status.values:
        raise ValidationError("Estado no válido.")
    if status not in TRANSITIONS[risk.status]:
        raise ValidationError(
            f"Un riesgo «{risk.get_status_display()}» no puede pasar a «{Status(status).label}»."
        )
    if status in (Status.OCCURRED, Status.CLOSED) and not (comment or "").strip():
        raise ValidationError("Explica qué pasó (es obligatorio al materializarse o cerrarse).")
    previous = risk.status
    risk.status = status
    risk.save(update_fields=["status", "updated_at"])
    changes = {"status": {"before": previous, "after": status}}
    if comment:
        changes["comment"] = {"before": None, "after": comment.strip()}
    log_action(actor, Action.RISK_STATUS_CHANGED, risk, changes=changes)
    if status == Status.OCCURRED:
        _notify_reviewers(risk, actor, f"Riesgo materializado: {risk.title}", f"{_name(actor)}: {comment.strip()}")
    return risk


@transaction.atomic
def add_mitigation(risk, actor, *, description, responsible=None, due_date=None):
    risk = _locked(risk)
    if not can_manage(actor, risk):
        raise PermissionDenied("Solo el líder o el responsable del riesgo registran medidas de mitigación.")
    if not risk.is_open:
        raise ValidationError("El riesgo está cerrado: reábrelo para agregar medidas.")
    description = (description or "").strip()
    if len(description) < 5:
        raise ValidationError("Describe la medida (al menos 5 caracteres).")
    if responsible is not None:
        _check_owner(risk.project, responsible)
    if due_date and due_date < timezone.localdate():
        raise ValidationError("La fecha de la medida no puede estar en el pasado.")
    mitigation = Mitigation.objects.create(
        risk=risk, description=description, responsible=responsible, due_date=due_date, created_by=actor
    )
    log_action(
        actor, Action.MITIGATION_ADDED, mitigation, project=risk.project,
        changes={"risk_id": {"before": None, "after": risk.pk}, "description": {"before": None, "after": description}},
    )
    # Registrar la primera medida pone el riesgo «En mitigación»
    if risk.status == Status.IDENTIFIED:
        risk.status = Status.MITIGATING
        risk.save(update_fields=["status", "updated_at"])
        log_action(actor, Action.RISK_STATUS_CHANGED, risk, changes={"status": {"before": Status.IDENTIFIED, "after": Status.MITIGATING}})
    if responsible and responsible.pk != actor.pk:
        notify(
            [responsible], Notification.Kind.RISK, f"Medida de mitigación a tu cargo: {risk.title}",
            description, _url(risk), risk.project, exclude=actor,
        )
    return mitigation


@transaction.atomic
def set_mitigation_done(mitigation, actor, done=True):
    mitigation = Mitigation.objects.select_for_update().select_related("risk__project").get(pk=mitigation.pk)
    if not can_complete(actor, mitigation):
        raise PermissionDenied("Solo el responsable de la medida, el del riesgo o el líder pueden marcarla.")
    if mitigation.done == done:
        return mitigation
    mitigation.done = done
    mitigation.done_at = timezone.now() if done else None
    mitigation.save(update_fields=["done", "done_at", "updated_at"])
    log_action(actor, Action.MITIGATION_UPDATED, mitigation, project=mitigation.risk.project,
               changes={"done": {"before": not done, "after": done}})
    return mitigation


@transaction.atomic
def delete_risk(risk, actor):
    risk = _locked(risk)
    if not is_leader(actor, risk.project):
        raise PermissionDenied("Solo el líder puede eliminar un riesgo.")
    before = snapshot(risk, [*FIELDS, "status"])
    risk.delete()
    log_action(actor, Action.RISK_DELETED, risk, changes=diff(before, {}))


def _notify_new(risk, actor):
    _notify_owner(risk, actor)
    if risk.level == matrix.HIGH:
        _notify_reviewers(risk, actor, f"Nuevo riesgo alto: {risk.title}",
                          f"{_name(actor)} registró {risk.code} con nivel alto ({risk.score}/9).")


def _notify_owner(risk, actor):
    notify([risk.owner], Notification.Kind.RISK, f"Eres responsable de un riesgo: {risk.title}",
           f"{risk.code} · nivel {risk.level_label.lower()} ({risk.score}/9) en {risk.project.name}.",
           _url(risk), risk.project, exclude=actor)


def _notify_reviewers(risk, actor, title, message):
    notify(reviewers_of(risk.project), Notification.Kind.RISK, title, message, _url(risk), risk.project, exclude=actor)
