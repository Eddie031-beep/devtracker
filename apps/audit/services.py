import json

from django.core.serializers.json import DjangoJSONEncoder

from .models import Action, AuditLog


def _json_safe(value):
    """Convierte fechas, decimales, etc. a algo que JSON entienda (y que se compare igual antes/después)."""
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def snapshot(instance, fields):
    """Foto de los campos indicados de un modelo: {campo: valor_json}."""
    return {field: _json_safe(getattr(instance, field)) for field in fields}


def diff(before, after):
    """Solo los campos que cambiaron: {campo: {"before": x, "after": y}}."""
    before, after = before or {}, after or {}
    return {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in before.keys() | after.keys()
        if before.get(key) != after.get(key)
    }


def log_action(actor, action, target, *, project=None, changes=None):
    """Registra una acción relevante. Es el único punto de entrada para escribir auditoría.

    - `actor`: usuario que la hizo (None si fue el sistema).
    - `action`: un valor de `Action`.
    - `target`: instancia afectada. De ahí salen `target_type` y `target_id`; el proyecto
      se deduce solo (el propio proyecto, o el atributo `.project` del objeto).
    - `changes`: dict con el antes/después, ver `diff()` y `snapshot()`.

    Llámalo DENTRO de la misma transacción que el cambio, para que se guarden juntos o ninguno.
    """
    if action not in Action.values:
        raise ValueError(f"«{action}» no es una acción de auditoría conocida (ver apps/audit/models.py).")

    if project is None:
        project = target if target._meta.model_name == "project" else getattr(target, "project", None)

    if actor is not None and not actor.is_authenticated:
        actor = None

    return AuditLog.objects.create(
        actor=actor,
        action=action,
        project=project,
        target_type=target._meta.model_name,
        target_id=target.pk,
        changes=_json_safe(changes or {}),
    )
