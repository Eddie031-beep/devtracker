from .models import Notification


def unread_notifications(request):
    """Cantidad de avisos sin leer, para la campana del menú de la interfaz web."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return {}
    return {"unread_notifications": Notification.objects.filter(recipient=user, read_at__isnull=True).count()}
