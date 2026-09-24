from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Deliverable, ProjectMembership

Status = Deliverable.Status

# Estados desde los que un estudiante puede entregar (o reentregar)
SUBMITTABLE_STATES = {Status.PENDING, Status.REJECTED}

# Transiciones de revisión: solo evaluador o líder del proyecto
REVIEW_TRANSITIONS = {
    Status.SUBMITTED: {Status.IN_REVIEW},
    Status.LATE: {Status.IN_REVIEW},
    Status.IN_REVIEW: {Status.APPROVED, Status.REJECTED},
}


@transaction.atomic
def submit_deliverable(deliverable, user, at=None):
    """Registra la entrega. El sistema decide si es a tiempo (SUBMITTED) o tardía (LATE)."""
    # Bloquea la fila para que dos entregas simultáneas no se pisen
    deliverable = Deliverable.objects.select_for_update().get(pk=deliverable.pk)

    if not deliverable.assignees.filter(pk=user.pk).exists():
        raise PermissionDenied("Solo un integrante asignado puede entregar este entregable.")

    if deliverable.status not in SUBMITTABLE_STATES:
        raise ValidationError(
            f"No se puede entregar un entregable en estado «{deliverable.get_status_display()}»."
        )

    now = at or timezone.now()
    deliverable.submitted_at = now
    if deliverable.is_past_due(now):
        deliverable.status = Status.LATE
        deliverable.is_late = True  # Solo se enciende; nunca vuelve a False
    else:
        deliverable.status = Status.SUBMITTED

    deliverable.save(update_fields=["status", "submitted_at", "is_late", "updated_at"])
    return deliverable


def can_review(user, project):
    """Admin global, o líder/evaluador de ESE proyecto (no basta el rol global de evaluador)."""
    if user.is_superuser or user.global_role == user.GlobalRole.ADMIN:
        return True
    return ProjectMembership.objects.filter(
        project=project,
        user=user,
        role__in=[ProjectMembership.ProjectRole.LEADER, ProjectMembership.ProjectRole.EVALUATOR],
    ).exists()


@transaction.atomic
def change_status(deliverable, user, new_status):
    """Mueve el entregable por el flujo de revisión: IN_REVIEW, APPROVED o REJECTED."""
    deliverable = (
        Deliverable.objects.select_for_update()
        .select_related("milestone__project")
        .get(pk=deliverable.pk)
    )

    if not can_review(user, deliverable.project):
        raise PermissionDenied("Solo un evaluador o el líder del proyecto puede revisar entregables.")

    if new_status not in Status.values:
        raise ValidationError(f"«{new_status}» no es un estado válido.")

    allowed = REVIEW_TRANSITIONS.get(deliverable.status, set())
    if new_status not in allowed:
        raise ValidationError(
            f"Transición inválida: de «{deliverable.get_status_display()}» a «{Status(new_status).label}»."
        )

    deliverable.status = new_status
    deliverable.save(update_fields=["status", "updated_at"])
    return deliverable