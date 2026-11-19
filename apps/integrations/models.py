from django.conf import settings
from django.db import models


class Commit(models.Model):
    """Commit del repo vinculado: llega por el webhook (push) o por la sincronización con la API."""

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="commits")
    sha = models.CharField(max_length=40)
    author_name = models.CharField(max_length=255, blank=True)
    author_email = models.CharField(max_length=254, blank=True)
    # Puede venir vacío si el correo del commit no está ligado a una cuenta de GitHub
    github_username = models.CharField(max_length=100, blank=True)
    message = models.TextField(blank=True)
    committed_at = models.DateTimeField()
    url = models.URLField(max_length=500, blank=True)
    # Para dibujar el historial: rama donde se vio por primera vez y los SHA de sus padres
    branch = models.CharField(max_length=255, blank=True)
    parents = models.JSONField(default=list, blank=True)
    # Vínculos (#21): integrante que lo hizo (por github_username o email) y entregable (#D<id> en el mensaje)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="commits"
    )
    deliverable = models.ForeignKey(
        "projects.Deliverable", null=True, blank=True, on_delete=models.SET_NULL, related_name="commits"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-committed_at"]
        constraints = [models.UniqueConstraint(fields=["project", "sha"], name="unique_project_commit")]

    def __str__(self):
        return f"{self.sha[:7]} {self.message.splitlines()[0] if self.message else ''}"


class PullRequest(models.Model):
    """Pull request del repo vinculado: llega por el webhook (`pull_request`) o por la sincronización."""

    class State(models.TextChoices):
        OPEN = "open", "Abierta"
        MERGED = "merged", "Fusionada"
        CLOSED = "closed", "Cerrada sin fusionar"

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="pull_requests")
    number = models.PositiveIntegerField()
    title = models.CharField(max_length=500)
    body = models.TextField(blank=True)
    state = models.CharField(max_length=10, choices=State.choices, default=State.OPEN)
    draft = models.BooleanField(default=False)
    author_login = models.CharField(max_length=100, blank=True)
    url = models.URLField(max_length=500, blank=True)
    head_ref = models.CharField(max_length=255, blank=True)
    base_ref = models.CharField(max_length=255, blank=True)
    head_sha = models.CharField(max_length=40, blank=True)
    merge_sha = models.CharField(max_length=40, blank=True)
    opened_at = models.DateTimeField()
    merged_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    # Mismos vínculos que los commits: integrante por su cuenta de GitHub y entregable por #D<id>
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="pull_requests"
    )
    deliverable = models.ForeignKey(
        "projects.Deliverable", null=True, blank=True, on_delete=models.SET_NULL, related_name="pull_requests"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-number"]
        constraints = [models.UniqueConstraint(fields=["project", "number"], name="unique_project_pull_request")]

    def __str__(self):
        return f"#{self.number} {self.title}"
