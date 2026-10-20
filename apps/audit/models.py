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
