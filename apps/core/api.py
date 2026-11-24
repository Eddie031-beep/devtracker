"""Ayudas para las APIs de los módulos: las reglas de negocio lanzan errores de Django y aquí se traducen a DRF."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import exceptions, serializers


def run(operation):
    """Corre `operation()`: una regla rota → 400 con el motivo; sin permiso → 403."""
    try:
        return operation()
    except DjangoValidationError as exc:
        raise exceptions.ValidationError({"detail": exc.messages})
    except DjangoPermissionDenied as exc:
        raise exceptions.PermissionDenied(str(exc) or None)


class PersonSerializer(serializers.ModelSerializer):
    """Una persona en las respuestas de los módulos: id, usuario y nombre para mostrar."""

    name = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = ["id", "username", "name"]

    def get_name(self, user):
        return user.get_full_name() or user.username
