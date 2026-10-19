from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import SoftDeleteModel, TimeStampedModel


class Project(TimeStampedModel, SoftDeleteModel):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_projects")
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="ProjectMembership", related_name="projects"
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.name


class ProjectMembership(TimeStampedModel):
    """Rol de un usuario dentro de un proyecto concreto (permisos a nivel de proyecto)."""

    class ProjectRole(models.TextChoices):
        LEADER = "leader", "Líder"
        MEMBER = "member", "Integrante"
        EVALUATOR = "evaluator", "Evaluador"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=ProjectRole.choices, default=ProjectRole.MEMBER)
    responsibilities = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "user"], name="unique_project_member")]

    def __str__(self):
        return f"{self.user} en {self.project} ({self.role})"


class Milestone(TimeStampedModel, SoftDeleteModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField()

    class Meta:
        ordering = ["due_date"]

    def __str__(self):
        return self.title


class Deliverable(TimeStampedModel, SoftDeleteModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        SUBMITTED = "submitted", "Entregado"
        LATE = "late", "Entregado tarde"
        IN_REVIEW = "in_review", "En revisión"
        APPROVED = "approved", "Aprobado"
        REJECTED = "rejected", "Rechazado"

    milestone = models.ForeignKey(Milestone, on_delete=models.CASCADE, related_name="deliverables")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    assignees = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="deliverables")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # Una vez marcado como tardío no se puede ocultar (regla de negocio #4)
    is_late = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ["due_at"]

    def __str__(self):
        return self.title

    @property
    def project(self):
        return self.milestone.project

    def is_past_due(self, at=None):
        return (at or timezone.now()) > self.due_at


class ImmutableVersionError(Exception):
    """Se intentó modificar o borrar una versión de entregable."""


class DeliverableVersionQuerySet(models.QuerySet):
    """Bloquea las vías masivas de modificación: `.update()`, `.delete()`, `.bulk_update()`."""

    def update(self, **kwargs):
        raise ImmutableVersionError("Las versiones de entregables no se pueden modificar.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ImmutableVersionError("Las versiones de entregables no se pueden modificar.")

    def delete(self):
        raise ImmutableVersionError("Las versiones de entregables no se pueden borrar.")

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        raise ImmutableVersionError("Las versiones de entregables no se pueden modificar.")


class DeliverableVersion(models.Model):
    deliverable = models.ForeignKey(Deliverable, on_delete=models.PROTECT, related_name="versions")
    number = models.PositiveIntegerField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="deliverable_versions"
    )
    url = models.URLField(max_length=2000)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = DeliverableVersionQuerySet.as_manager()

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["deliverable", "number"], name="unique_deliverable_version")
        ]

    def __str__(self):
        return f"{self.deliverable.title} v{self.number}"

    @property
    def project(self):
        return self.deliverable.project

    def save(self, *args, **kwargs):
        if self.pk is not None or not self._state.adding:
            raise ImmutableVersionError("Las versiones de entregables no se pueden modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableVersionError("Las versiones de entregables no se pueden borrar.")
