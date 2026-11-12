import csv
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.text import slugify

from apps.audit.models import Action, AuditLog
from apps.metrics.services import latest_scores, project_metrics
from apps.projects.models import Deliverable, Project
from apps.projects.permissions import filter_projects_for_user
from apps.projects.services import can_review


def _project(request, pk):
    # Proyecto ajeno → 404, igual que en la API y en el dashboard
    return get_object_or_404(filter_projects_for_user(Project.objects.all(), request.user), pk=pk)


def _deliverable_rows(project):
    deliverables = list(
        Deliverable.objects.filter(milestone__project=project, milestone__deleted_at__isnull=True)
        .select_related("milestone")
        .prefetch_related("assignees")
        .annotate(version_count=Count("versions", distinct=True))
        .order_by("milestone__due_date", "due_at")
    )
    scores = latest_scores([d.pk for d in deliverables])
    for d in deliverables:
        d.score = scores.get(d.pk)
        d.assignee_names = ", ".join(a.get_full_name() or a.username for a in d.assignees.all())
    return deliverables


def _local(moment):
    return timezone.localtime(moment).strftime("%d/%m/%Y %H:%M") if moment else ""


def _csv_response(project, name, header, rows):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"devtracker-{slugify(project.name)}-{name}-{timezone.localdate():%Y%m%d}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")  # BOM: Excel abre bien las tildes
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response


@login_required
def project_report(request, pk):
    """Reporte imprimible del proyecto (desde el navegador se guarda como PDF)."""
    project = _project(request, pk)
    return render(
        request,
        "reports/project_report.html",
        {
            "project": project,
            "metrics": project_metrics(project),
            "deliverables": _deliverable_rows(project),
            "generated_at": timezone.now(),
        },
    )


@login_required
def deliverables_csv(request, pk):
    project = _project(request, pk)
    rows = [
        [
            d.milestone.title,
            d.title,
            d.assignee_names,
            d.get_status_display(),
            _local(d.due_at),
            _local(d.submitted_at),
            "sí" if d.is_late else "no",
            d.version_count,
            "" if d.score is None else d.score,
        ]
        for d in _deliverable_rows(project)
    ]
    header = ["Hito", "Entregable", "Asignados", "Estado", "Vence", "Entregado", "Tarde", "Versiones", "Nota vigente"]
    return _csv_response(project, "entregables", header, rows)


@login_required
def members_csv(request, pk):
    project = _project(request, pk)
    rows = [
        [
            m["name"],
            m["username"],
            m["role_display"],
            m["assigned"],
            m["delivered"],
            m["late"],
            "" if m["on_time_rate"] is None else m["on_time_rate"],
            m["approved"],
            "" if m["average_score"] is None else m["average_score"],
            m["versions"],
            m["commits"],
        ]
        for m in project_metrics(project)["members"]
    ]
    header = [
        "Integrante", "Usuario", "Rol", "Asignados", "Entregados", "Tarde", "% a tiempo",
        "Aprobados", "Nota promedio", "Versiones", "Commits",
    ]
    return _csv_response(project, "integrantes", header, rows)


@login_required
def audit_csv(request, pk):
    """La auditoría completa: solo quien puede verla en la API (líder, evaluador del proyecto o admin)."""
    project = _project(request, pk)
    if not can_review(request.user, project):
        raise PermissionDenied("Solo el líder, el evaluador del proyecto o un administrador puede ver la auditoría.")
    labels = dict(Action.choices)
    rows = [
        [
            _local(log.created_at),
            str(log.actor) if log.actor else "Sistema",
            labels.get(log.action, log.action),
            log.target_type,
            log.target_id or "",
            json.dumps(log.changes, ensure_ascii=False, default=str),
        ]
        for log in AuditLog.objects.filter(project=project).select_related("actor").order_by("created_at")
    ]
    return _csv_response(project, "auditoria", ["Fecha", "Actor", "Acción", "Objeto", "Id", "Cambios"], rows)
