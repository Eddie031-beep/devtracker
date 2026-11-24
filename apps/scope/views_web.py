from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.web import form_errors, run_action
from apps.projects.access import get_project_or_404, is_evaluator
from apps.projects.models import Project
from apps.projects.permissions import filter_projects_for_user
from apps.web.modules import module_context

from . import services
from .forms import ChangeFilterForm, ChangeRequestForm, DecisionForm
from .models import ChangeRequest

Status = ChangeRequest.Status


def _change(request, pk):
    projects = filter_projects_for_user(Project.objects.all(), request.user)
    return get_object_or_404(
        ChangeRequest.objects.select_related("project", "proposed_by", "decided_by"), pk=pk, project__in=projects
    )


@login_required
def change_list(request, pk):
    project = get_project_or_404(request.user, pk)
    deliverables = services.project_deliverables(project)
    can_propose = services.can_propose(request.user, project)
    form = None
    if can_propose:
        form = ChangeRequestForm(request.POST or None, deliverables=deliverables)
        if request.method == "POST" and form.is_valid():
            created = {}

            def propose():
                created["change"] = services.propose_change(project, request.user, **form.cleaned_data)

            if run_action(request, propose, "Solicitud enviada al evaluador."):
                return redirect("scope:detail", pk=created["change"].pk)
    elif request.method == "POST":
        raise PermissionDenied("Solo los estudiantes del proyecto proponen cambios de alcance.")

    changes = project.change_requests.select_related("proposed_by", "decided_by").annotate(n_deliverables=Count("affected_deliverables"))
    filters = ChangeFilterForm(request.GET or None)
    if filters.is_valid() and filters.cleaned_data["status"]:
        changes = changes.filter(status=filters.cleaned_data["status"])
    counts = dict(project.change_requests.values_list("status").annotate(n=Count("pk")))
    return render(
        request, "scope/list.html",
        module_context(
            project, "scope", form=form, changes=changes, filters=filters,
            summary=[(value, label, counts.get(value, 0)) for value, label in Status.choices],
            is_evaluator=is_evaluator(request.user, project), open_form=request.method == "POST",
        ),
    )


@login_required
def change_detail(request, pk):
    change = _change(request, pk)
    return render(
        request, "scope/detail.html",
        module_context(
            change.project, "scope", change=change,
            deliverables=change.affected_deliverables.select_related("milestone"),
            can_edit=services.can_edit(request.user, change),
            can_decide=services.can_decide(request.user, change),
            decision_form=DecisionForm(),
        ),
    )


@login_required
def change_edit(request, pk):
    change = _change(request, pk)
    if not services.can_edit(request.user, change):
        raise PermissionDenied("Solo quien la propuso puede editarla, y solo mientras está pendiente.")
    form = ChangeRequestForm(
        request.POST or None, instance=ChangeRequest.objects.get(pk=change.pk),
        deliverables=services.project_deliverables(change.project),
    )
    if request.method == "POST" and form.is_valid():
        if run_action(request, lambda: services.update_change(change, request.user, **form.cleaned_data), "Solicitud actualizada."):
            return redirect("scope:detail", pk=change.pk)
    return render(request, "scope/form.html", module_context(change.project, "scope", change=change, form=form))


@login_required
@require_POST
def change_withdraw(request, pk):
    change = _change(request, pk)
    if not services.can_edit(request.user, change):
        raise PermissionDenied("Solo quien la propuso puede retirarla.")
    run_action(request, lambda: services.withdraw_change(change, request.user), "Solicitud retirada. Se conserva en el historial.")
    return redirect("scope:detail", pk=change.pk)


@login_required
@require_POST
def change_decide(request, pk):
    change = _change(request, pk)
    if not is_evaluator(request.user, change.project):
        raise PermissionDenied("Solo el evaluador del proyecto aprueba o rechaza cambios de alcance.")
    form = DecisionForm(request.POST)
    if form.is_valid():
        decision = form.cleaned_data["decision"]
        run_action(
            request, lambda: services.decide_change(change, request.user, decision, form.cleaned_data["comment"]),
            "Cambio aprobado." if decision == "approved" else "Cambio rechazado.",
        )
    else:
        form_errors(request, form)
    return redirect("scope:detail", pk=change.pk)
