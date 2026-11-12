from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models


class ImmutableEvaluationError(Exception):
    """Se intentó modificar o borrar una evaluación."""


class EvaluationQuerySet(models.QuerySet):
    """Bloquea las vías masivas de modificación: `.update()`, `.delete()`, `.bulk_update()`."""

    def update(self, **kwargs):
        raise ImmutableEvaluationError("Las evaluaciones no se pueden modificar.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ImmutableEvaluationError("Las evaluaciones no se pueden modificar.")

    def delete(self):
        raise ImmutableEvaluationError("Las evaluaciones no se pueden borrar.")

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        raise ImmutableEvaluationError("Las evaluaciones no se pueden modificar.")


class Evaluation(models.Model):
    """Revisión de un entregable por el evaluador o el líder: decisión, nota de 0 a 100 y comentarios.

    Igual que las versiones, no se edita ni se borra: si se reentrega, la nueva revisión es otra fila.
    """

    class Decision(models.TextChoices):
        APPROVED = "approved", "Aprobado"
        REJECTED = "rejected", "Rechazado"

    deliverable = models.ForeignKey("projects.Deliverable", on_delete=models.PROTECT, related_name="evaluations")
    evaluator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="evaluations")
    decision = models.CharField(max_length=20, choices=Decision.choices)
    score = models.PositiveSmallIntegerField(validators=[MaxValueValidator(100)])
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = EvaluationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=models.Q(score__lte=100), name="evaluation_score_max_100")]

    def __str__(self):
        return f"{self.deliverable} · {self.get_decision_display()} ({self.score})"

    @property
    def project(self):
        return self.deliverable.project

    def save(self, *args, **kwargs):
        if self.pk is not None or not self._state.adding:
            raise ImmutableEvaluationError("Las evaluaciones no se pueden modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableEvaluationError("Las evaluaciones no se pueden borrar.")
