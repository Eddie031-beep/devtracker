from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class ImmutableAuditError(Exception):
    """Se intentó modificar o borrar un registro de auditoría."""


class Action(models.TextChoices):
    """Catálogo de acciones auditables.

    Vive en código (no en `choices` del campo) a propósito: agregar una acción nueva,
    por ejemplo desde el issue de Versiones, NO requiere una migración.
    """

    PROJECT_CREATED = "project.created", "Proyecto creado"
    PROJECT_UPDATED = "project.updated", "Proyecto editado"
    PROJECT_DELETED = "project.deleted", "Proyecto eliminado"
    MILESTONE_CREATED = "milestone.created", "Hito creado"
    MILESTONE_UPDATED = "milestone.updated", "Hito editado"
    MILESTONE_DELETED = "milestone.deleted", "Hito eliminado"
    DELIVERABLE_CREATED = "deliverable.created", "Entregable creado"
    DELIVERABLE_UPDATED = "deliverable.updated", "Entregable editado"
    DELIVERABLE_DELETED = "deliverable.deleted", "Entregable eliminado"
    DELIVERABLE_SUBMITTED = "deliverable.submitted", "Entrega realizada"
    DELIVERABLE_STATUS_CHANGED = "deliverable.status_changed", "Cambio de estado de entregable"
    DELIVERABLE_ASSIGNEES_CHANGED = "deliverable.assignees_changed", "Cambio de asignados"
    MEMBER_ADDED = "member.added", "Integrante agregado"
    MEMBER_ROLE_CHANGED = "member.role_changed", "Cambio de rol de integrante"
    MEMBER_RESPONSIBILITIES_CHANGED = "member.responsibilities_changed", "Cambio de responsabilidades"
    MEMBER_REMOVED = "member.removed", "Integrante removido"
    # Reservada para el issue #19 (Historial de versiones)
    VERSION_CREATED = "version.created", "Nueva versión de entregable"
    # Etapa 3: evaluación con nota
    DELIVERABLE_EVALUATED = "deliverable.evaluated", "Entregable evaluado"
    # Examen semestral: incidencias de software
    ISSUE_CREATED = "issue.created", "Incidencia registrada"
    ISSUE_UPDATED = "issue.updated", "Incidencia editada"
    ISSUE_ASSIGNED = "issue.assigned", "Responsable de incidencia"
    ISSUE_STATUS_CHANGED = "issue.status_changed", "Cambio de estado de incidencia"
    ISSUE_DELETED = "issue.deleted", "Incidencia eliminada"
    # Examen semestral: riesgos del proyecto
    RISK_CREATED = "risk.created", "Riesgo registrado"
    RISK_UPDATED = "risk.updated", "Riesgo editado"
    RISK_STATUS_CHANGED = "risk.status_changed", "Cambio de estado de riesgo"
    RISK_DELETED = "risk.deleted", "Riesgo eliminado"
    MITIGATION_ADDED = "mitigation.added", "Medida de mitigación registrada"
    MITIGATION_UPDATED = "mitigation.updated", "Medida de mitigación actualizada"
    # Examen semestral: solicitudes de cambio de alcance
    CHANGE_REQUESTED = "change.requested", "Cambio de alcance propuesto"
    CHANGE_UPDATED = "change.updated", "Cambio de alcance editado"
    CHANGE_WITHDRAWN = "change.withdrawn", "Cambio de alcance retirado"
    CHANGE_DECIDED = "change.decided", "Cambio de alcance decidido"
    # Examen semestral: reuniones y acuerdos
    MEETING_CREATED = "meeting.created", "Reunión registrada"
    MEETING_UPDATED = "meeting.updated", "Acta editada"
    MEETING_DELETED = "meeting.deleted", "Reunión eliminada"
    AGREEMENT_CREATED = "agreement.created", "Acuerdo registrado"
    AGREEMENT_UPDATED = "agreement.updated", "Acuerdo editado"
    AGREEMENT_STATUS_CHANGED = "agreement.status_changed", "Cambio de estado de acuerdo"


class AuditQuerySet(models.QuerySet):
    """Bloquea las vías masivas de modificación: `.update()`, `.delete()`, `.bulk_update()`."""

    def update(self, **kwargs):
        raise ImmutableAuditError("Los registros de auditoría no se pueden modificar.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ImmutableAuditError("Los registros de auditoría no se pueden modificar.")

    def delete(self):
        raise ImmutableAuditError("Los registros de auditoría no se pueden borrar.")

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        raise ImmutableAuditError("Los registros de auditoría no se pueden modificar.")


class AuditLog(models.Model):
    """Registro append-only de lo que pasa en un proyecto.

    Solo se agregan filas: `save()` falla si el registro ya existe y `delete()` siempre falla.
    No hereda de TimeStampedModel ni de SoftDeleteModel: un `updated_at` o un `deleted_at`
    contradirían la idea de que nada cambia.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,  # null = acción del sistema (p. ej. una tarea de Celery o un webhook)
        blank=True,
        on_delete=models.PROTECT,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=50, db_index=True)
    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="audit_logs",
    )
    target_type = models.CharField(max_length=50)
    target_id = models.PositiveBigIntegerField(null=True, blank=True)
    # {"campo": {"before": ..., "after": ...}}
    changes = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["project", "-created_at"]),
            models.Index(fields=["target_type", "target_id"]),
        ]

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.action} {self.target_type}#{self.target_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableAuditError("Los registros de auditoría no se pueden modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableAuditError("Los registros de auditoría no se pueden borrar.")
