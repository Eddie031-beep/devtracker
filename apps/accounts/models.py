from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Usuario del sistema. El rol global define el RBAC; el rol por proyecto vive en ProjectMembership."""

    class GlobalRole(models.TextChoices):
        STUDENT = "student", "Estudiante"
        EVALUATOR = "evaluator", "Evaluador"
        ADMIN = "admin", "Administrador"

    email = models.EmailField(unique=True)
    global_role = models.CharField(max_length=20, choices=GlobalRole.choices, default=GlobalRole.STUDENT)

    def __str__(self):
        return self.get_full_name() or self.username
