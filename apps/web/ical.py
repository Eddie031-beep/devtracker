"""Calendario iCal (Could Have #18): fechas de entrega para Google Calendar, Outlook o el celular.

Google Calendar se suscribe a una URL y la vuelve a leer cada tantas horas, sin la sesión del
navegador; por eso cada usuario tiene un enlace firmado propio (`/calendario/<token>/devtracker.ics`).
La firma depende de SECRET_KEY: si se rota, los enlaces viejos dejan de funcionar.
"""

from datetime import timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.utils import timezone

from apps.projects.models import Deliverable, Milestone, ProjectMembership

SALT = "devtracker.calendar"
Role = ProjectMembership.ProjectRole


def calendar_token(user):
    return signing.Signer(salt=SALT).sign(str(user.pk))


def feed_url(user):
    return settings.SITE_URL.rstrip("/") + reverse("web:calendar_feed", args=[calendar_token(user)])


def _escape(text):
    return str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line):
    """RFC 5545: líneas de máximo 75 octetos; las que siguen empiezan con un espacio."""
    raw = line.encode()
    if len(raw) <= 75:
        return line
    parts, current = [], b""
    for char in line:
        encoded = char.encode()
        if len(current) + len(encoded) > (75 if not parts else 74):
            parts.append(current.decode())
            current = b""
        current += encoded
    parts.append(current.decode())
    return "\r\n ".join(parts)


def _stamp(moment):
    return moment.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_calendar(user):
    """Entregables asignados al usuario y, si revisa un proyecto, todos los de ese proyecto; más los hitos."""
    reviewed = ProjectMembership.objects.filter(user=user, role__in=[Role.LEADER, Role.EVALUATOR]).values("project_id")
    deliverables = (
        Deliverable.objects.filter(
            milestone__deleted_at__isnull=True,
            milestone__project__deleted_at__isnull=True,
            milestone__project__memberships__user=user,
        )
        .filter(Q(assignees=user) | Q(milestone__project_id__in=reviewed))
        .select_related("milestone__project")
        .distinct()
    )
    milestones = Milestone.objects.filter(project__deleted_at__isnull=True, project__memberships__user=user).select_related("project").distinct()
    site = settings.SITE_URL.rstrip("/")
    now = _stamp(timezone.now())
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DevTracker//Entregas//ES", "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH", "X-WR-CALNAME:DevTracker", "X-WR-TIMEZONE:" + settings.TIME_ZONE,
    ]
    for d in deliverables:
        url = site + reverse("web:deliverable", args=[d.pk])
        lines += [
            "BEGIN:VEVENT",
            f"UID:deliverable-{d.pk}@devtracker",
            f"DTSTAMP:{now}",
            f"DTSTART:{_stamp(d.due_at - timedelta(minutes=30))}",
            f"DTEND:{_stamp(d.due_at)}",
            f"SUMMARY:{_escape(f'#D{d.pk} {d.title} ({d.milestone.project.name})')}",
            f"DESCRIPTION:{_escape(f'Estado: {d.get_status_display()}. Hito: {d.milestone.title}. {url}')}",
            f"URL:{url}",
            "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:-PT24H", f"DESCRIPTION:{_escape(f'Vence mañana: {d.title}')}", "END:VALARM",
            "END:VEVENT",
        ]
    for m in milestones:
        lines += [
            "BEGIN:VEVENT",
            f"UID:milestone-{m.pk}@devtracker",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{m.due_date:%Y%m%d}",
            f"DTEND;VALUE=DATE:{m.due_date + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape(f'Cierre de hito: {m.title} ({m.project.name})')}",
            f"URL:{site + reverse('web:project', args=[m.project_id])}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def _ics_response(user, download):
    response = HttpResponse(build_calendar(user), content_type="text/calendar; charset=utf-8")
    disposition = "attachment" if download else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="devtracker.ics"'
    return response


@login_required
def calendar_download(request):
    return _ics_response(request.user, download=True)


def calendar_feed(request, token):
    try:
        pk = signing.Signer(salt=SALT).unsign(token)
    except signing.BadSignature:
        raise Http404
    user = get_user_model().objects.filter(pk=pk, is_active=True).first()
    if user is None:
        raise Http404
    return _ics_response(user, download=False)
