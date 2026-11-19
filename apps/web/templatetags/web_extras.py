from django import template

register = template.Library()


@register.filter
def initials(user):
    """«Eddie Man» → «EM»; sin nombre, las dos primeras letras del usuario."""
    if not user:
        return "?"
    parts = [p for p in (user.first_name, user.last_name) if p]
    if parts:
        return "".join(p[0] for p in parts[:2]).upper()
    return (user.username or "?")[:2].upper()


@register.filter
def percent(part, total):
    """Porcentaje entero para las barras de progreso (0 si no hay total)."""
    try:
        return round(100 * part / total) if total else 0
    except (TypeError, ZeroDivisionError):
        return 0


@register.filter
def get_item(mapping, key):
    """`{{ labels|get_item:log.action }}`: busca una clave en un diccionario."""
    return mapping.get(key) if hasattr(mapping, "get") else None
