from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Case, Count, IntegerField, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.web import form_errors, run_action
from apps.projects.access import get_project_or_404, is_leader
from apps.projects.models import Project
from apps.projects.permissions import filter_projects_for_user
from apps.web.modules import module_context

from . import services
from .forms import AssignForm, CommentForm, IssueFilterForm, IssueForm, TransitionForm
from .models import Issue

Status = Issue.Status
PRIORITY_ORDER = Case(
    *(When(priority=p, then=Value(i)) for i, p in enumerate(["critical", "high", "medium", "low"])),
    output_field=IntegerField(),
)
# Etiqueta y color de cada acción del flujo (botones de la página de detalle)
ACTIONS = {
    "start": ("Empezar a resolver", "Pasa a «En resolución».", False),
    "resolve": ("Marcar como resuelta", "Explica cómo se resolvió.", True),
    "verify": ("Verificar solución", "Confirma que el error ya no ocurre.", False),
    "reopen": ("Reabrir", "Indica por qué sigue fallando.", True),
}


def _issue(request, pk):
    """Incidencia de un proyecto al que el usuario tiene acceso; si no, 404."""
    projects = filter_projects_for_user(Project.objects.all(), request.user)
    return get_object_or_404(
        Issue.objects.select_related("project", "reported_by", "assignee"), pk=pk, project__in=projects
    )


@login_required
def issue_list(request, pk):
    project = get_project_or_404(request.user, pk)
    leader = is_leader(request.user, project)
    assignees = services.assignable_users(project)

    if request.method == "POST":
        form = IssueForm(request.POST, assignees=assignees if leader else None)
        if form.is_valid():
            data = form.cleaned_data
            created = {}

            def create():
                created["issue"] = services.create_issue(
                    project, request.user, title=data["title"], description=data["description"],
                    steps_to_reproduce=data["steps_to_reproduce"], priority=data["priority"],
                    assignee=data.get("assignee"),
                )

            if run_action(request, create, "Incidencia registrada."):
                return redirect("issues:detail", pk=created["issue"].pk)
    else:
        form = IssueForm(assignees=assignees if leader else None)

    issues = project.issues.select_related("assignee", "reported_by")
    filters = IssueFilterForm(request.GET or None, assignees=assignees)
    if filters.is_valid():
        data = filters.cleaned_data
        if data["status"]:
            issues = issues.filter(status=data["status"])
        if data["priority"]:
            issues = issues.filter(priority=data["priority"])
        if data["assignee"]:
            issues = issues.filter(assignee=data["assignee"])
    if request.GET.get("mias"):
        issues = issues.filter(assignee=request.user)
    issues = issues.annotate(priority_rank=PRIORITY_ORDER).order_by("priority_rank", "-created_at")

    counts = dict(project.issues.values_list("status").annotate(n=Count("pk")))
    summary = [(value, label, counts.get(value, 0)) for value, label in Status.choices]
    return render(
        request, "issues/list.html",
        module_context(project, "issues", issues=issues, form=form, filters=filters, summary=summary,
                       filtered=bool(request.GET), open_form=request.method == "POST"),
    )


@login_required
def issue_detail(request, pk):
    issue = _issue(request, pk)
    user = request.user
    actions = [
        {"key": key, "label": ACTIONS[key][0], "help": ACTIONS[key][1], "needs_comment": ACTIONS[key][2]}
        for key in services.allowed_actions(user, issue)
    ]
    return render(
        request, "issues/detail.html",
        module_context(
            issue.project, "issues", issue=issue,
            events=issue.events.select_related("actor"),
            actions=actions,
            flow=Status.choices,
            can_edit=services.can_edit(user, issue),
            can_assign=services.can_assign(user, issue),
            can_delete=is_leader(user, issue.project),
            assign_form=AssignForm(initial={"assignee": issue.assignee_id}, assignees=services.assignable_users(issue.project)),
            comment_form=CommentForm(),
        ),
    )


@login_required
def issue_edit(request, pk):
    issue = _issue(request, pk)
    if not services.can_edit(request.user, issue):
        raise PermissionDenied("Solo quien la reportó o el líder puede editarla, y no después de verificada.")
    form = IssueForm(request.POST or None, instance=Issue.objects.get(pk=issue.pk))
    if request.method == "POST" and form.is_valid():
        if run_action(request, lambda: services.update_issue(issue, request.user, **form.cleaned_data), "Incidencia actualizada."):
            return redirect("issues:detail", pk=issue.pk)
    return render(request, "issues/form.html", module_context(issue.project, "issues", issue=issue, form=form))


@login_required
@require_POST
def issue_assign(request, pk):
    issue = _issue(request, pk)
    if not services.can_assign(request.user, issue):
        raise PermissionDenied("Solo el líder asigna el responsable.")
    form = AssignForm(request.POST, assignees=services.assignable_users(issue.project))
    if form.is_valid():
        assignee = form.cleaned_data["assignee"]
        run_action(
            request, lambda: services.assign_issue(issue, request.user, assignee),
            f"Responsable: {assignee.get_full_name() or assignee.username}." if assignee else "Incidencia sin responsable.",
        )
    else:
        form_errors(request, form)
    return redirect("issues:detail", pk=issue.pk)


@login_required
@require_POST
def issue_transition(request, pk):
    issue = _issue(request, pk)
    form = TransitionForm(request.POST)
    if not form.is_valid():
        form_errors(request, form)
        return redirect("issues:detail", pk=issue.pk)
    action = form.cleaned_data["action"]
    if not services.can_transition(request.user, issue, action) and issue.status in services.TRANSITIONS[action][0]:
        raise PermissionDenied("No puedes hacer esta acción con la incidencia.")
    done = {"start": "Incidencia en resolución.", "resolve": "Incidencia marcada como resuelta.",
            "verify": "Solución verificada.", "reopen": "Incidencia reabierta."}
    run_action(request, lambda: services.transition_issue(issue, request.user, action, form.cleaned_data["comment"]), done[action])
    return redirect("issues:detail", pk=issue.pk)


@login_required
@require_POST
def issue_comment(request, pk):
    issue = _issue(request, pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        run_action(request, lambda: services.comment_issue(issue, request.user, form.cleaned_data["comment"]), "Comentario agregado.")
    else:
        form_errors(request, form)
    return redirect("issues:detail", pk=issue.pk)


@login_required
@require_POST
def issue_delete(request, pk):
    issue = _issue(request, pk)
    if not is_leader(request.user, issue.project):
        raise PermissionDenied("Solo el líder puede eliminar una incidencia.")
    services.delete_issue(issue, request.user)
    messages.success(request, f"Incidencia {issue.code} eliminada. Su historial se conserva.")
    return redirect("issues:list", pk=issue.project_id)
