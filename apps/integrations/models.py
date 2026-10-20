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
