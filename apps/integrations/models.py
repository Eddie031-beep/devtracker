from django.db import models


class Commit(models.Model):
    """Commit recibido desde el webhook de GitHub (evento push)."""

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="commits")
    sha = models.CharField(max_length=40)
    author_name = models.CharField(max_length=255, blank=True)
    author_email = models.CharField(max_length=254, blank=True)
    # Puede venir vacío si el correo del commit no está ligado a una cuenta de GitHub
    github_username = models.CharField(max_length=100, blank=True)
    message = models.TextField(blank=True)
    committed_at = models.DateTimeField()
    url = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-committed_at"]
        constraints = [models.UniqueConstraint(fields=["project", "sha"], name="unique_project_commit")]

    def __str__(self):
        return f"{self.sha[:7]} {self.message.splitlines()[0] if self.message else ''}"
