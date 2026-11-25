from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import SoftDeleteModel, TimeStampedModel


class Meeting(TimeStampedModel, SoftDeleteModel):
    """Acta de una reunión del proyecto: cuándo fue, quiénes estuvieron y qué se trató."""

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="meetings")
    title = models.CharField(max_length=200)
    held_at = models.DateTimeField("fecha y hora")
    location = models.CharField("lugar o enlace", max_length=300, blank=True)
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="meetings")
    summary = models.TextField("temas tratados")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-held_at", "-id"]

    def __str__(self):
        return f"{self.title} ({self.held_at:%Y-%m-%d})"


class Agreement(TimeStampedModel):
    """Acuerdo tomado en una reunión: qué se hará, quién y para cuándo."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        DONE = "done", "Cumplido"

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="agreements")
    description = models.TextField()
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="agreements")
    due_date = models.DateField("fecha de cumplimiento")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["status", "due_date", "id"]

    def __str__(self):
        return self.description[:60]

    @property
    def project(self):
        return self.meeting.project

    @property
    def is_overdue(self):
        return self.status == self.Status.PENDING and self.due_date < timezone.localdate()

    @property
    def status_chip(self):
        if self.status == self.Status.DONE:
            return "dt-chip-green"
        return "dt-chip-red" if self.is_overdue else "dt-chip-amber"

    @property
    def status_label(self):
        return "Vencido" if self.is_overdue else self.get_status_display()
