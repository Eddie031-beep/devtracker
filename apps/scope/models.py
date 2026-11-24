from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class ImmutableChangeRequestError(Exception):
    """Se intentó modificar una solicitud ya decidida o borrar cualquier solicitud."""


class ChangeRequestQuerySet(models.QuerySet):
    def delete(self):
        raise ImmutableChangeRequestError("Las solicitudes de cambio se conservan: no se pueden borrar.")


class ChangeRequest(TimeStampedModel):
    """Propuesta de cambio de alcance. Se conserva siempre: no hay borrado y, una vez decidida, no se edita.

    Aprobarla NO cambia los entregables: `affected_deliverables` es solo una referencia de lo que tocaría.
    Si el cambio se aprueba, el líder ajusta los entregables a mano y eso queda en la auditoría.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"
        WITHDRAWN = "withdrawn", "Retirada"

    class ImpactLevel(models.TextChoices):
        LOW = "low", "Bajo"
        MEDIUM = "medium", "Medio"
        HIGH = "high", "Alto"

    STATUS_CHIPS = {"pending": "dt-chip-amber", "approved": "dt-chip-green", "rejected": "dt-chip-red", "withdrawn": "dt-chip-gray"}
    IMPACT_CHIPS = {"low": "dt-chip-gray", "medium": "dt-chip-blue", "high": "dt-chip-violet"}

    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT, related_name="change_requests")
    title = models.CharField(max_length=200)
    description = models.TextField(help_text="Qué se quiere cambiar del alcance")
    justification = models.TextField()
    expected_impact = models.TextField(help_text="Efecto en tiempo, entregables, calidad o equipo")
    impact_level = models.CharField(max_length=10, choices=ImpactLevel.choices, default=ImpactLevel.MEDIUM)
    affected_deliverables = models.ManyToManyField("projects.Deliverable", blank=True, related_name="change_requests")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    proposed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="proposed_changes")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="decided_changes"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_comment = models.TextField(blank=True)

    objects = ChangeRequestQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"#C{self.pk} {self.title}"

    @property
    def code(self):
        return f"#C{self.pk}"

    @property
    def is_pending(self):
        return self.status == self.Status.PENDING

    @property
    def status_chip(self):
        return self.STATUS_CHIPS[self.status]

    @property
    def impact_chip(self):
        return self.IMPACT_CHIPS[self.impact_level]

    def save(self, *args, **kwargs):
        # Una solicitud cerrada (decidida o retirada) queda tal cual: el registro no se reescribe
        if not self._state.adding:
            stored = ChangeRequest.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if stored and stored != self.Status.PENDING:
                raise ImmutableChangeRequestError("La solicitud ya fue cerrada y no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableChangeRequestError("Las solicitudes de cambio se conservan: no se pueden borrar.")
