from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.audit.models import Action, AuditLog
from apps.core.web import form_errors, run_action
from apps.projects.access import get_project_or_404, is_leader, is_student
from apps.projects.models import Project
from apps.projects.permissions import filter_projects_for_user
from apps.web.modules import module_context

from . import matrix, services
from .forms import MitigationForm, RiskFilterForm, RiskForm, StatusForm
from .models import Mitigation, Risk

LEVEL_SCORES = {matrix.LOW: (1, 2), matrix.MEDIUM: (3, 4), matrix.HIGH: (6, 9)}


def _risk(request, pk):
    projects = filter_projects_for_user(Project.objects.all(), request.user)
    return get_object_or_404(Risk.objects.select_related("project", "owner", "created_by"), pk=pk, project__in=projects)


@login_required
def risk_list(request, pk):
    project = get_project_or_404(request.user, pk)
    people = services.owner_candidates(project)
    can_create = is_student(request.user, project) or is_leader(request.user, project)

    form = None
    if can_create:
        form = RiskForm(request.POST or None, people=people, initial={"probability": 2, "impact": 2})
        if request.method == "POST" and form.is_valid():
            created = {}

            def create():
                created["risk"] = services.create_risk(project, request.user, **form.cleaned_data)

            if run_action(request, create, "Riesgo registrado."):
                return redirect("risks:detail", pk=created["risk"].pk)
    elif request.method == "POST":
        raise PermissionDenied("Solo los estudiantes del proyecto registran riesgos.")

    all_risks = list(project.risks.select_related("owner"))
    risks = project.risks.select_related("owner")
    filters = RiskFilterForm(request.GET or None, people=people)
    selected = None
    if filters.is_valid():
        data = filters.cleaned_data
        if data["status"]:
            risks = risks.filter(status=data["status"])
        if data["level"]:
            risks = risks.filter(score__in=[s for s in range(1, 10) if matrix.level_for_score(s) == data["level"]])
        if data["owner"]:
            risks = risks.filter(owner=data["owner"])
        if data["p"] and data["i"]:
            selected = (data["p"], data["i"])
            risks = risks.filter(probability=data["p"], impact=data["i"])

    # La matriz muestra los riesgos abiertos (los cerrados ya no amenazan al proyecto)
    open_risks = [r for r in all_risks if r.is_open]
    levels = {lvl: sum(1 for r in open_risks if r.level == lvl) for lvl in matrix.LEVEL_LABELS}
    return render(
        request, "risks/list.html",
        module_context(
            project, "risks", form=form, risks=risks, filters=filters, filtered=bool(request.GET),
            grid=matrix.build_matrix(open_risks, selected), levels=levels, level_labels=matrix.LEVEL_LABELS,
            level_chips=matrix.LEVEL_CHIPS, open_form=request.method == "POST",
        ),
    )


@login_required
def risk_detail(request, pk):
    risk = _risk(request, pk)
    user = request.user
    manage = services.can_manage(user, risk)
    people = services.owner_candidates(risk.project)
    mitigations = risk.mitigations.select_related("responsible")
    for mitigation in mitigations:
        mitigation.can_toggle = services.can_complete(user, mitigation)
    # Historial del riesgo y de sus medidas, tomado de la auditoría (inmutable)
    history = AuditLog.objects.filter(
        Q(target_type="risk", target_id=risk.pk)
        | Q(target_type="mitigation", target_id__in=[m.pk for m in mitigations]),
        project=risk.project,
    ).select_related("actor")
    labels = dict(Action.choices)
    status_labels = dict(Risk.Status.choices)
    return render(
        request, "risks/detail.html",
        module_context(
            risk.project, "risks", risk=risk, can_manage=manage, can_delete=is_leader(user, risk.project),
            mitigations=mitigations,
            mitigation_form=MitigationForm(people=people) if manage and risk.is_open else None,
            status_form=StatusForm(choices=services.next_statuses(risk)) if manage else None,
            grid=matrix.build_matrix([risk], (risk.probability, risk.impact)),
            history=[
                {"log": log, "label": labels.get(log.action, log.action),
                 "status": status_labels.get((log.changes.get("status") or {}).get("after")),
                 "comment": (log.changes.get("comment") or {}).get("after")
                 or (log.changes.get("description") or {}).get("after")}
                for log in history.order_by("-created_at", "-id")
            ],
        ),
    )


@login_required
def risk_edit(request, pk):
    risk = _risk(request, pk)
    if not services.can_manage(request.user, risk):
        raise PermissionDenied("Solo el líder o el responsable del riesgo pueden editarlo.")
    form = RiskForm(request.POST or None, instance=Risk.objects.get(pk=risk.pk), people=services.owner_candidates(risk.project))
    if request.method == "POST" and form.is_valid():
        if run_action(request, lambda: services.update_risk(risk, request.user, **form.cleaned_data), "Riesgo actualizado."):
            return redirect("risks:detail", pk=risk.pk)
    return render(request, "risks/form.html", module_context(risk.project, "risks", risk=risk, form=form))


@login_required
@require_POST
def risk_status(request, pk):
    risk = _risk(request, pk)
    if not services.can_manage(request.user, risk):
        raise PermissionDenied("Solo el líder o el responsable del riesgo cambian su estado.")
    form = StatusForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        run_action(request, lambda: services.change_status(risk, request.user, data["status"], data["comment"]),
                   f"Estado: {Risk.Status(data['status']).label}.")
    else:
        form_errors(request, form)
    return redirect("risks:detail", pk=risk.pk)


@login_required
@require_POST
def mitigation_add(request, pk):
    risk = _risk(request, pk)
    if not services.can_manage(request.user, risk):
        raise PermissionDenied("Solo el líder o el responsable del riesgo registran medidas.")
    form = MitigationForm(request.POST, people=services.owner_candidates(risk.project))
    if form.is_valid():
        run_action(request, lambda: services.add_mitigation(risk, request.user, **form.cleaned_data), "Medida de mitigación registrada.")
    else:
        form_errors(request, form)
    return redirect("risks:detail", pk=risk.pk)


@login_required
@require_POST
def mitigation_toggle(request, pk):
    projects = filter_projects_for_user(Project.objects.all(), request.user)
    mitigation = get_object_or_404(Mitigation.objects.select_related("risk__project"), pk=pk, risk__project__in=projects)
    if not services.can_complete(request.user, mitigation):
        raise PermissionDenied("No puedes marcar esta medida.")
    done = request.POST.get("done") == "1"
    run_action(request, lambda: services.set_mitigation_done(mitigation, request.user, done),
               "Medida cumplida." if done else "Medida marcada como pendiente.")
    return redirect("risks:detail", pk=mitigation.risk_id)


@login_required
@require_POST
def risk_delete(request, pk):
    risk = _risk(request, pk)
    if not is_leader(request.user, risk.project):
        raise PermissionDenied("Solo el líder puede eliminar un riesgo.")
    services.delete_risk(risk, request.user)
    messages.success(request, f"Riesgo {risk.code} eliminado. Su historial se conserva en la auditoría.")
    return redirect("risks:list", pk=risk.project_id)
