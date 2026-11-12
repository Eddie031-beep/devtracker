import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mass_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.projects.models import Deliverable, ProjectMembership

from .models import Notification

logger = logging.getLogger(__name__)
Kind = Notification.Kind
Role = ProjectMembership.ProjectRole


def notify(users, kind, title, message="", url="", project=None, exclude=None):
    """Crea un aviso por usuario y, cuando la transacción se confirma, lo manda por correo.

    `exclude` es quien hizo la acción: no tiene sentido avisarle de lo que él mismo hizo.
    El correo nunca rompe la acción principal: si falla, queda en el log y el aviso sigue en la app.
    """
    recipients = {u.pk: u for u in users if u and u.is_active and (exclude is None or u.pk != exclude.pk)}
    notifications = Notification.objects.bulk_create(
        [
            Notification(recipient=u, kind=kind, title=title, message=message, url=url, project=project)
            for u in recipients.values()
        ]
    )
    emails = [u.email for u in recipients.values() if u.email]
    if emails and getattr(settings, "NOTIFICATIONS_SEND_EMAIL", True):
        body = f"{message}\n\n{settings.SITE_URL.rstrip('/')}{url}" if settings.SITE_URL else message
        transaction.on_commit(lambda: _send(title, body, emails))
    return notifications


def _send(title, body, emails):
    try:
        # Un mensaje por destinatario: nadie ve los correos de los demás
        send_mass_mail([(f"[DevTracker] {title}", body, None, [email]) for email in emails])
    except Exception:  # noqa: BLE001 - el correo es un extra; la app no debe caerse por él
        logger.exception("No se pudo enviar el correo de notificación «%s»", title)


def _deliverable_url(deliverable):
    return reverse("web:deliverable", args=[deliverable.pk])


def reviewers_of(project):
    return [
        m.user
        for m in ProjectMembership.objects.filter(project=project, role__in=[Role.LEADER, Role.EVALUATOR]).select_related(
            "user"
        )
    ]


def notify_submitted(deliverable, actor):
    """Una entrega nueva: avisa al líder y a los evaluadores del proyecto."""
    project = deliverable.project
    late = " (tarde)" if deliverable.is_late else ""
    return notify(
        reviewers_of(project),
        Kind.SUBMITTED,
        f"Nueva entrega{late}: {deliverable.title}",
        f"{actor.get_full_name() or actor.username} entregó «{deliverable.title}» en {project.name}. Está lista para revisar.",
        _deliverable_url(deliverable),
        project,
        exclude=actor,
    )


def notify_evaluated(evaluation):
    """Una evaluación: avisa a los asignados del entregable con la decisión y la nota."""
    deliverable = evaluation.deliverable
    return notify(
        deliverable.assignees.all(),
        Kind.EVALUATED,
        f"{evaluation.get_decision_display()}: {deliverable.title} ({evaluation.score}/100)",
        evaluation.feedback or f"Tu entrega «{deliverable.title}» fue evaluada.",
        _deliverable_url(deliverable),
        deliverable.project,
        exclude=evaluation.evaluator,
    )


def notify_assigned(deliverable, users, actor):
    """Asignación: avisa solo a quienes se agregaron, no a los que ya estaban."""
    return notify(
        users,
        Kind.ASSIGNED,
        f"Nuevo entregable: {deliverable.title}",
        f"Te asignaron «{deliverable.title}» en {deliverable.project.name}. Vence el "
        f"{timezone.localtime(deliverable.due_at):%d/%m/%Y %H:%M}.",
        _deliverable_url(deliverable),
        deliverable.project,
        exclude=actor,
    )


def send_due_reminders(hours=48, now=None):
    """Recuerda a los asignados los entregables pendientes (o rechazados) que vencen en las próximas `hours`.

    No repite el aviso del mismo entregable a la misma persona dentro de un día. Devuelve cuántos avisos creó.
    """
    now = now or timezone.now()
    due = Deliverable.objects.filter(
        status__in=[Deliverable.Status.PENDING, Deliverable.Status.REJECTED],
        due_at__gt=now,
        due_at__lte=now + timedelta(hours=hours),
        milestone__deleted_at__isnull=True,
        milestone__project__deleted_at__isnull=True,
    ).select_related("milestone__project")
    created = 0
    for deliverable in due:
        url = _deliverable_url(deliverable)
        already = set(
            Notification.objects.filter(kind=Kind.DUE_SOON, url=url, created_at__gte=now - timedelta(days=1)).values_list(
                "recipient_id", flat=True
            )
        )
        users = [u for u in deliverable.assignees.all() if u.pk not in already]
        created += len(
            notify(
                users,
                Kind.DUE_SOON,
                f"Por vencer: {deliverable.title}",
                f"«{deliverable.title}» ({deliverable.project.name}) vence el "
                f"{timezone.localtime(deliverable.due_at):%d/%m/%Y %H:%M} y todavía no se entregó.",
                url,
                deliverable.project,
            )
        )
    return created
