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
