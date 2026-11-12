from django.conf import settings
from django.db import models


class Notification(models.Model):
    """Aviso para un usuario dentro de la app (y, si tiene correo, también por email)."""

    class Kind(models.TextChoices):
        SUBMITTED = "submitted", "Nueva entrega"
        EVALUATED = "evaluated", "Entrega evaluada"
        ASSIGNED = "assigned", "Nuevo entregable asignado"
        DUE_SOON = "due_soon", "Entregable por vencer"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    # Ruta de la interfaz web a la que lleva el aviso, p. ej. /entregables/12/
    url = models.CharField(max_length=300, blank=True)
    project = models.ForeignKey(
        "projects.Project", null=True, blank=True, on_delete=models.CASCADE, related_name="notifications"
    )
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "read_at"])]

    def __str__(self):
        return f"{self.recipient}: {self.title}"

    @property
    def is_read(self):
        return self.read_at is not None
