"""Ayudas para las vistas web de los módulos: ejecutar una operación y mostrar el resultado como mensaje."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError


def run_action(request, action, success):
    """Corre `action()`. Si una regla de negocio la rechaza, el motivo se muestra como mensaje de error.

    Devuelve True si salió bien. Un PermissionDenied se convierte en mensaje solo cuando el usuario
    sí puede ver la página (las vistas ya cortaron antes con 403/404 lo que no le corresponde).
    """
    try:
        action()
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return False
    except PermissionDenied as error:
        messages.error(request, str(error) or "No tienes permiso para esta acción.")
        return False
    messages.success(request, success)
    return True


def form_errors(request, form):
    """Pasa los errores de un formulario a mensajes (para formularios que redirigen)."""
    for field, errors in form.errors.items():
        label = form.fields[field].label if field in form.fields else ""
        for error in errors:
            messages.error(request, f"{label}: {error}" if label else error)
