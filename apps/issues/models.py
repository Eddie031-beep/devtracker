from django.conf import settings
from django.db import models

from apps.core.models import SoftDeleteModel, TimeStampedModel


class ImmutableHistoryError(Exception):
    """Se intentó modificar o borrar un evento del historial de una incidencia."""


class Issue(TimeStampedModel, SoftDeleteModel):
    """Error de software reportado por un integrante del proyecto."""

    class Priority(models.TextChoices):
        LOW = "low", "Baja"
        MEDIUM = "medium", "Media"
        HIGH = "high", "Alta"
        CRITICAL = "critical", "Crítica"

    class Status(models.TextChoices):
        OPEN = "open", "Abierta"
        IN_PROGRESS = "in_progress", "En resolución"
        RESOLVED = "resolved", "Resuelta"
        VERIFIED = "verified", "Verificada"

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="issues")
    title = models.CharField(max_length=200)
    description = models.TextField()
    steps_to_reproduce = models.TextField()
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reported_issues")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="assigned_issues"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["project", "status"])]

    # Color de la etiqueta en la interfaz (clases de tailwind/input.css)
    STATUS_CHIPS = {"open": "dt-chip-red", "in_progress": "dt-chip-amber", "resolved": "dt-chip-blue", "verified": "dt-chip-green"}
    PRIORITY_CHIPS = {"low": "dt-chip-gray", "medium": "dt-chip-blue", "high": "dt-chip-amber", "critical": "dt-chip-red"}

    def __str__(self):
        return f"#I{self.pk} {self.title}"

    @property
    def code(self):
        return f"#I{self.pk}"

    @property
    def status_chip(self):
        return self.STATUS_CHIPS[self.status]

    @property
    def priority_chip(self):
        return self.PRIORITY_CHIPS[self.priority]


class IssueEventQuerySet(models.QuerySet):
    """El historial solo crece: sin `.update()` ni `.delete()` masivos."""

    def update(self, **kwargs):
        raise ImmutableHistoryError("El historial de una incidencia no se puede modificar.")

    def delete(self):
        raise ImmutableHistoryError("El historial de una incidencia no se puede borrar.")


class IssueEvent(models.Model):
    """Un paso en la vida de una incidencia. Append-only: se conserva todo, también al reabrir."""

    class Kind(models.TextChoices):
        CREATED = "created", "Registró la incidencia"
        UPDATED = "updated", "Editó la incidencia"
        ASSIGNED = "assigned", "Asignó responsable"
        STARTED = "started", "Empezó a resolverla"
        RESOLVED = "resolved", "Marcó como resuelta"
        VERIFIED = "verified", "Verificó la solución"
        REOPENED = "reopened", "Reabrió la incidencia"
        COMMENTED = "commented", "Comentó"

    issue = models.ForeignKey(Issue, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="issue_events")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    from_status = models.CharField(max_length=20, choices=Issue.Status.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=Issue.Status.choices, blank=True)
    comment = models.TextField(blank=True)
    # Detalle extra, p. ej. {"assignee": "Ana Pérez"} o los campos editados
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = IssueEventQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.issue.code} · {self.get_kind_display()}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableHistoryError("El historial de una incidencia no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableHistoryError("El historial de una incidencia no se puede borrar.")
