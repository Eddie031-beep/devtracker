from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.evaluations.services import EVALUABLE_STATES, evaluate_deliverable
from apps.metrics.services import project_metrics
from apps.projects.models import Deliverable, Project, ProjectMembership
from apps.projects.permissions import filter_deliverables_for_user, filter_projects_for_user, is_global_admin
from apps.projects.services import SUBMITTABLE_STATES, can_review, submit_deliverable

from .forms import EvaluateForm, SubmitForm

User = get_user_model()
Status = Deliverable.Status
Role = ProjectMembership.ProjectRole

# Entregables vivos: ni ellos, ni su hito, ni su proyecto con borrado lógico
LIVE = {"milestone__deleted_at__isnull": True, "milestone__project__deleted_at__isnull": True}


def _reviewable_project_ids(user):
    """Proyectos donde el usuario puede revisar: admin global, o líder/evaluador de ese proyecto."""
    if is_global_admin(user):
        return Project.objects.values_list("pk", flat=True)
    return ProjectMembership.objects.filter(user=user, role__in=[Role.LEADER, Role.EVALUATOR]).values_list(
        "project_id", flat=True
    )


@login_required
def dashboard(request):
    """Inicio según el rol: el estudiante ve lo que debe entregar; el evaluador y el líder, lo que deben revisar;
    el administrador, además, un resumen de toda la plataforma."""
    user = request.user
    now = timezone.now()
    projects = (
        filter_projects_for_user(Project.objects.all(), user)
        .annotate(
            total=Count("milestones__deliverables", filter=Q(milestones__deleted_at__isnull=True, milestones__deliverables__deleted_at__isnull=True), distinct=True),
            approved=Count(
                "milestones__deliverables",
                filter=Q(
                    milestones__deleted_at__isnull=True,
                    milestones__deliverables__deleted_at__isnull=True,
                    milestones__deliverables__status=Status.APPROVED,
                ),
                distinct=True,
            ),
        )
        .order_by("name")
    )
    roles = dict(ProjectMembership.objects.filter(user=user).values_list("project_id", "role"))
    for project in projects:
        project.my_role = Role(roles[project.pk]).label if project.pk in roles else "Administrador"

    pending = (
        Deliverable.objects.filter(assignees=user, status__in=SUBMITTABLE_STATES, **LIVE)
        .select_related("milestone__project")
        .order_by("due_at")
    )
    to_review = (
        Deliverable.objects.filter(milestone__project_id__in=_reviewable_project_ids(user), status__in=EVALUABLE_STATES, **LIVE)
        .select_related("milestone__project")
        .order_by("submitted_at")
    )
    is_reviewer = is_global_admin(user) or ProjectMembership.objects.filter(
        user=user, role__in=[Role.LEADER, Role.EVALUATOR]
    ).exists()

    overview = None
    if is_global_admin(user):
        live = Deliverable.objects.filter(**LIVE)
        by_status = dict(live.values_list("status").annotate(n=Count("pk")))
        overview = {
            "projects": Project.objects.count(),
            "users": User.objects.filter(is_active=True).count(),
            "deliverables": live.count(),
            "chart": {
                "labels": [label for _, label in Status.choices],
                "values": [by_status.get(value, 0) for value in Status.values],
            },
        }

    return render(
        request,
        "web/dashboard.html",
        {
            "projects": projects,
            "pending": pending,
            "to_review": to_review,
            "is_reviewer": is_reviewer,
            "overview": overview,
            "now": now,
        },
    )


@login_required
def project_detail(request, pk):
    # Proyecto ajeno → 404, igual que en la API
    project = get_object_or_404(filter_projects_for_user(Project.objects.all(), request.user), pk=pk)
    metrics = project_metrics(project)
    milestones = project.milestones.prefetch_related("deliverables__assignees").order_by("due_date")
    status_labels = dict(Status.choices)
    chart = {
        "status_labels": [status_labels[s] for s in Status.values],
        "status_values": [metrics["deliverables"]["by_status"][s] for s in Status.values],
        "weeks": [w["week"] for w in metrics["commits"]["by_week"]],
        "commits": [w["count"] for w in metrics["commits"]["by_week"]],
        "members": [m["name"] for m in metrics["members"]],
        "member_commits": [m["commits"] for m in metrics["members"]],
    }
    return render(
        request,
        "web/project_detail.html",
        {
            "project": project,
            "metrics": metrics,
            "milestones": milestones,
            "chart": chart,
            "can_review": can_review(request.user, project),
            "now": timezone.now(),
        },
    )


def _get_deliverable(request, pk):
    queryset = filter_deliverables_for_user(Deliverable.objects.select_related("milestone__project"), request.user)
    return get_object_or_404(queryset, pk=pk)


@login_required
def deliverable_detail(request, pk):
    deliverable = _get_deliverable(request, pk)
    project = deliverable.project
    is_assignee = deliverable.assignees.filter(pk=request.user.pk).exists()
    reviewer = can_review(request.user, project)
    return render(
        request,
        "web/deliverable_detail.html",
        {
            "deliverable": deliverable,
            "project": project,
            "versions": deliverable.versions.select_related("author").order_by("-number"),
            "evaluations": deliverable.evaluations.select_related("evaluator"),
            "commits": deliverable.commits.select_related("author")[:20],
            "can_submit": is_assignee and deliverable.status in SUBMITTABLE_STATES,
            "can_evaluate": reviewer and deliverable.status in EVALUABLE_STATES,
            "submit_form": SubmitForm(),
            "evaluate_form": EvaluateForm(),
        },
    )


def _run(request, action, success):
    try:
        action()
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except PermissionDenied as exc:
        messages.error(request, str(exc) or "No tienes permiso para esta acción.")
    else:
        messages.success(request, success)


@login_required
@require_POST
def deliverable_submit(request, pk):
    deliverable = _get_deliverable(request, pk)
    form = SubmitForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revisa el enlace: debe ser una URL válida con http o https.")
    else:
        _run(
            request,
            lambda: submit_deliverable(deliverable, request.user, url=form.cleaned_data["url"], comment=form.cleaned_data["comment"]),
            "Entrega registrada. Se guardó una nueva versión.",
        )
    return redirect("web:deliverable", pk=pk)


@login_required
@require_POST
def deliverable_evaluate(request, pk):
    deliverable = _get_deliverable(request, pk)
    form = EvaluateForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revisa la evaluación: la nota debe estar entre 0 y 100.")
    else:
        _run(
            request,
            lambda: evaluate_deliverable(deliverable, request.user, **form.cleaned_data),
            "Evaluación registrada.",
        )
    return redirect("web:deliverable", pk=pk)
