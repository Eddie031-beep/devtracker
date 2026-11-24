from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import SoftDeleteModel, TimeStampedModel

from . import matrix

ONE_TO_THREE = [MinValueValidator(1), MaxValueValidator(3)]


class Risk(TimeStampedModel, SoftDeleteModel):
    """Riesgo del proyecto. Su nivel sale de la matriz probabilidad × impacto (ver matrix.py)."""

    class Status(models.TextChoices):
        IDENTIFIED = "identified", "Identificado"
        MITIGATING = "mitigating", "En mitigación"
        OCCURRED = "occurred", "Materializado"
        CLOSED = "closed", "Cerrado"

    STATUS_CHIPS = {"identified": "dt-chip-gray", "mitigating": "dt-chip-blue", "occurred": "dt-chip-red", "closed": "dt-chip-green"}

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="risks")
    title = models.CharField(max_length=200)
    description = models.TextField()
    probability = models.PositiveSmallIntegerField(choices=matrix.SCALE, validators=ONE_TO_THREE)
    impact = models.PositiveSmallIntegerField(choices=matrix.IMPACT_SCALE, validators=ONE_TO_THREE)
    # Se guarda para ordenar y filtrar en la base; siempre = probabilidad × impacto (ver save)
    score = models.PositiveSmallIntegerField(editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_risks")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IDENTIFIED, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_risks")

    class Meta:
        ordering = ["-score", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(probability__gte=1, probability__lte=3, impact__gte=1, impact__lte=3),
                name="risk_scale_1_to_3",
            ),
        ]

    def __str__(self):
        return f"#R{self.pk} {self.title}"

    def save(self, *args, **kwargs):
        self.score = matrix.score(self.probability, self.impact)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], "score"}
        super().save(*args, **kwargs)

    @property
    def code(self):
        return f"#R{self.pk}"

    @property
    def level(self):
        return matrix.level_for_score(self.score)

    @property
    def level_label(self):
        return matrix.LEVEL_LABELS[self.level]

    @property
    def level_chip(self):
        return matrix.LEVEL_CHIPS[self.level]

    @property
    def status_chip(self):
        return self.STATUS_CHIPS[self.status]

    @property
    def is_open(self):
        return self.status != self.Status.CLOSED


class Mitigation(TimeStampedModel):
    """Medida para reducir un riesgo: qué se hará, quién y para cuándo."""

    risk = models.ForeignKey(Risk, on_delete=models.CASCADE, related_name="mitigations")
    description = models.TextField()
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="risk_mitigations"
    )
    due_date = models.DateField(null=True, blank=True)
    done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["done", "due_date", "created_at"]

    def __str__(self):
        return self.description[:60]

    @property
    def project(self):
        return self.risk.project
