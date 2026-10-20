from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

# Reglas de GitHub: letras, números y guiones simples; sin guion al inicio ni al final; máx. 39
github_username_validator = RegexValidator(
    r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$",
    "Usuario de GitHub inválido (letras, números y guiones simples, máx. 39 caracteres).",
)


class User(AbstractUser):
    """Usuario del sistema. El rol global define el RBAC; el rol por proyecto vive en ProjectMembership."""

    class GlobalRole(models.TextChoices):
        STUDENT = "student", "Estudiante"
        EVALUATOR = "evaluator", "Evaluador"
        ADMIN = "admin", "Administrador"

    email = models.EmailField(unique=True)
    global_role = models.CharField(max_length=20, choices=GlobalRole.choices, default=GlobalRole.STUDENT)
    # Integración GitHub (#21): sirve para saber qué integrante hizo cada commit
    github_username = models.CharField(max_length=39, blank=True, validators=[github_username_validator])

    class Meta(AbstractUser.Meta):
        constraints = [
            # GitHub no distingue mayúsculas: «Ana» y «ana» son la misma cuenta
            models.UniqueConstraint(
                Lower("github_username"),
                condition=~models.Q(github_username=""),
                name="unique_github_username_ci",
            )
        ]

    def __str__(self):
        return self.get_full_name() or self.username
