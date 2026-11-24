"""Reglas de las reuniones y sus acuerdos.

- Consultar actas y acuerdos: todos los integrantes del proyecto (también el evaluador). Ajenos: 404.
- Registrar una reunión: los estudiantes del proyecto (líder o integrante).
- Editar el acta, eliminarla (lógico) y registrar acuerdos: quien la registró o el líder.
- Actualizar un acuerdo (cumplirlo, reabrirlo, cambiar fecha o texto): su responsable o el líder.
  Nadie más: así solo los integrantes autorizados cambian los acuerdos.
"""

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import Action
from apps.audit.services import diff, log_action, snapshot
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.projects.access import is_leader, is_student, project_people
from apps.projects.models import ProjectMembership

from .models import Agreement, Meeting

Status = Agreement.Status
MEETING_FIELDS = ["title", "held_at", "location", "summary"]
AGREEMENT_FIELDS = ["description", "responsible_id", "due_date", "status"]


def _name(user):
    return user.get_full_name() or user.username


def _url(meeting):
    return reverse("meetings:detail", args=[meeting.pk])


def responsible_candidates(project):
    """Responsables de un acuerdo: estudiantes del proyecto (líder o integrante)."""
    return project_people(project, roles=[ProjectMembership.ProjectRole.LEADER, ProjectMembership.ProjectRole.MEMBER])


def _check_participants(project, participants):
    participants = list(participants or [])
    if not participants:
        raise ValidationError("Indica quiénes participaron.")
    allowed = set(project_people(project).values_list("pk", flat=True))
    if any(p.pk not in allowed for p in participants):
        raise ValidationError("Los participantes deben ser integrantes del proyecto.")
    return participants


def _check_meeting(title, held_at, summary):
    if len((title or "").strip()) < 3:
        raise ValidationError("El título debe tener al menos 3 caracteres.")
    if held_at is None:
        raise ValidationError("Indica la fecha y hora de la reunión.")
    if held_at > timezone.now() + timedelta(hours=1):
        raise ValidationError("El acta es de una reunión que ya ocurrió: la fecha no puede ser futura.")
    if len((summary or "").strip()) < 10:
        raise ValidationError("Resume los temas tratados (al menos 10 caracteres).")


def _check_agreement(meeting, description, responsible, due_date):
    if len((description or "").strip()) < 5:
        raise ValidationError("Describe el acuerdo (al menos 5 caracteres).")
    if responsible is None or not responsible_candidates(meeting.project).filter(pk=responsible.pk).exists():
        raise ValidationError("El responsable debe ser integrante o líder del proyecto.")
    if due_date is None:
        raise ValidationError("Indica la fecha de cumplimiento.")
    if due_date < timezone.localdate(meeting.held_at):
        raise ValidationError("La fecha de cumplimiento no puede ser anterior a la reunión.")


# ---------- Permisos ----------

def can_create(user, project):
    return is_student(user, project) or is_leader(user, project)


def can_edit_meeting(user, meeting):
    return meeting.created_by_id == user.pk or is_leader(user, meeting.project)


def can_update_agreement(user, agreement):
    return agreement.responsible_id == user.pk or is_leader(user, agreement.meeting.project)


# ---------- Reuniones ----------

@transaction.atomic
def create_meeting(project, actor, *, title, held_at, summary, participants, location=""):
    if not can_create(actor, project):
        raise PermissionDenied("Solo los estudiantes del proyecto registran reuniones.")
    _check_meeting(title, held_at, summary)
    participants = _check_participants(project, participants)
    meeting = Meeting.objects.create(
        project=project, title=title.strip(), held_at=held_at, location=(location or "").strip(),
        summary=summary.strip(), created_by=actor,
    )
    meeting.participants.set(participants)
    log_action(actor, Action.MEETING_CREATED, meeting, changes={
        **diff({}, snapshot(meeting, MEETING_FIELDS)),
        "participants": {"before": None, "after": sorted(p.pk for p in participants)},
    })
    notify(participants, Notification.Kind.MEETING, f"Nueva acta: {meeting.title}",
           f"{_name(actor)} registró el acta de la reunión del {timezone.localtime(meeting.held_at):%d/%m/%Y}.",
           _url(meeting), project, exclude=actor)
    return meeting


@transaction.atomic
def update_meeting(meeting, actor, participants=None, **fields):
    meeting = Meeting.objects.select_for_update().select_related("project").get(pk=meeting.pk)
    if not can_edit_meeting(actor, meeting):
        raise PermissionDenied("Solo quien registró la reunión o el líder pueden editar el acta.")
    values = {f: fields.get(f, getattr(meeting, f)) for f in MEETING_FIELDS}
    _check_meeting(values["title"], values["held_at"], values["summary"])
    before = snapshot(meeting, MEETING_FIELDS)
    before_people = sorted(meeting.participants.values_list("pk", flat=True))
    for field, value in values.items():
        setattr(meeting, field, value.strip() if isinstance(value, str) else value)
    changes = diff(before, snapshot(meeting, MEETING_FIELDS))
    if participants is not None:
        participants = _check_participants(meeting.project, participants)
        after = sorted(p.pk for p in participants)
        if after != before_people:
            meeting.participants.set(participants)
            changes["participants"] = {"before": before_people, "after": after}
    if changes:
        meeting.save()
        log_action(actor, Action.MEETING_UPDATED, meeting, changes=changes)
    return meeting


@transaction.atomic
def delete_meeting(meeting, actor):
    if not can_edit_meeting(actor, meeting):
        raise PermissionDenied("Solo quien registró la reunión o el líder pueden eliminarla.")
    before = snapshot(meeting, MEETING_FIELDS)
    meeting.delete()  # lógico: el acta y sus acuerdos se conservan
    log_action(actor, Action.MEETING_DELETED, meeting, changes=diff(before, {}))


# ---------- Acuerdos ----------

@transaction.atomic
def add_agreement(meeting, actor, *, description, responsible, due_date):
    if not can_edit_meeting(actor, meeting):
        raise PermissionDenied("Solo quien registró la reunión o el líder registran sus acuerdos.")
    _check_agreement(meeting, description, responsible, due_date)
    agreement = Agreement.objects.create(meeting=meeting, description=description.strip(), responsible=responsible, due_date=due_date)
    log_action(actor, Action.AGREEMENT_CREATED, agreement, project=meeting.project,
               changes={**diff({}, snapshot(agreement, AGREEMENT_FIELDS)), "meeting_id": {"before": None, "after": meeting.pk}})
    notify([responsible], Notification.Kind.MEETING, "Tienes un acuerdo a tu cargo",
           f"{agreement.description} — para el {due_date:%d/%m/%Y} (reunión «{meeting.title}»).",
           _url(meeting), meeting.project, exclude=actor)
    return agreement


@transaction.atomic
def update_agreement(agreement, actor, **fields):
    """Cambia el estado (pendiente/cumplido) y, si hace falta, el texto, el responsable o la fecha."""
    agreement = Agreement.objects.select_for_update().select_related("meeting__project").get(pk=agreement.pk)
    if not can_update_agreement(actor, agreement):
        raise PermissionDenied("Solo el responsable del acuerdo o el líder pueden actualizarlo.")
    if "status" in fields and fields["status"] not in Status.values:
        raise ValidationError("Estado no válido: usa pending o done.")
    if "responsible" in fields and not is_leader(actor, agreement.meeting.project) and fields["responsible"].pk != agreement.responsible_id:
        raise PermissionDenied("Solo el líder reasigna un acuerdo.")
    _check_agreement(
        agreement.meeting, fields.get("description", agreement.description),
        fields.get("responsible", agreement.responsible), fields.get("due_date", agreement.due_date),
    )
    before = snapshot(agreement, AGREEMENT_FIELDS)
    for field in ("description", "responsible", "due_date", "status"):
        if field in fields:
            value = fields[field]
            setattr(agreement, field, value.strip() if isinstance(value, str) else value)
    if agreement.status == Status.DONE and before["status"] != Status.DONE:
        agreement.completed_at, agreement.completed_by = timezone.now(), actor
    elif agreement.status == Status.PENDING:
        agreement.completed_at = agreement.completed_by = None
    changes = diff(before, snapshot(agreement, AGREEMENT_FIELDS))
    if changes:
        agreement.save()
        action = Action.AGREEMENT_STATUS_CHANGED if set(changes) == {"status"} else Action.AGREEMENT_UPDATED
        log_action(actor, action, agreement, project=agreement.meeting.project, changes=changes)
        if "responsible_id" in changes:
            notify([agreement.responsible], Notification.Kind.MEETING, "Tienes un acuerdo a tu cargo",
                   f"{agreement.description} — para el {agreement.due_date:%d/%m/%Y}.",
                   _url(agreement.meeting), agreement.meeting.project, exclude=actor)
    return agreement


def project_agreements(project):
    return Agreement.objects.filter(meeting__project=project, meeting__deleted_at__isnull=True).select_related(
        "meeting", "responsible", "completed_by"
    )
