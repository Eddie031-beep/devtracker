from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.audit.models import Action, AuditLog
from apps.audit.services import diff, log_action, snapshot
from apps.evaluations.services import EVALUABLE_STATES, evaluate_deliverable
from apps.integrations.models import Commit
from apps.integrations.services import link_user_commits
from apps.metrics.services import project_metrics
from apps.notifications.models import Notification
from apps.projects.models import Deliverable, Milestone, Project, ProjectMembership
from apps.projects.permissions import filter_deliverables_for_user, filter_projects_for_user, is_global_admin
from apps.projects.services import SUBMITTABLE_STATES, can_review, submit_deliverable
from apps.projects.services_members import can_manage_members, set_deliverable_assignees

from . import oauth
from .forms import AuditFilterForm, DeliverableForm, EvaluateForm, MilestoneForm, ProfileForm, SubmitForm

User = get_user_model()
Status = Deliverable.Status
Role = ProjectMembership.ProjectRole

# Entregables vivos: ni ellos, ni su hito, ni su proyecto con borrado lógico
LIVE = {"milestone__deleted_at__isnull": True, "milestone__project__deleted_at__isnull": True}
# Nombre en español del objeto auditado (AuditLog.target_type es el nombre del modelo)
TARGET_LABELS = {
    "project": "Proyecto", "milestone": "Hito", "deliverable": "Entregable", "projectmembership": "Integrante",
    "deliverableversion": "Versión", "evaluation": "Evaluación",
}


def _reviewable_project_ids(user):
    """Proyectos donde el usuario puede revisar: admin global, o líder/evaluador de ese proyecto."""
    if is_global_admin(user):
        return Project.objects.values_list("pk", flat=True)
    return ProjectMembership.objects.filter(user=user, role__in=[Role.LEADER, Role.EVALUATOR]).values_list(
        "project_id", flat=True
    )


def _role_of(user):
    """Rol que guía el inicio: admin, líder, evaluador o estudiante."""
    if is_global_admin(user):
        return "admin"
    roles = set(ProjectMembership.objects.filter(user=user).values_list("role", flat=True))
    if Role.LEADER in roles:
        return "leader"
    if Role.EVALUATOR in roles or user.global_role == user.GlobalRole.EVALUATOR:
        return "evaluator"
    return "student"


@login_required
def dashboard(request):
    """Inicio según el rol: el estudiante ve lo que debe entregar; el evaluador y el líder, lo que deben revisar;
    el administrador, además, un resumen de toda la plataforma."""
    user = request.user
    now = timezone.now()
    live_deliverables = Q(milestones__deleted_at__isnull=True, milestones__deliverables__deleted_at__isnull=True)
    projects = (
        filter_projects_for_user(Project.objects.all(), user)
        .annotate(
            total=Count("milestones__deliverables", filter=live_deliverables, distinct=True),
            approved=Count(
                "milestones__deliverables",
                filter=live_deliverables & Q(milestones__deliverables__status=Status.APPROVED),
                distinct=True,
            ),
        )
        .prefetch_related(Prefetch("memberships", queryset=ProjectMembership.objects.select_related("user")))
        .order_by("name")
    )
    roles = dict(ProjectMembership.objects.filter(user=user).values_list("project_id", "role"))
    for project in projects:
        project.my_role = roles.get(project.pk, "admin")
        project.my_role_label = Role(roles[project.pk]).label if project.pk in roles else "Administrador"

    pending = (
        Deliverable.objects.filter(assignees=user, status__in=SUBMITTABLE_STATES, **LIVE)
        .select_related("milestone__project")
        .order_by("due_at")
    )
    to_review = (
        Deliverable.objects.filter(milestone__project_id__in=_reviewable_project_ids(user), status__in=EVALUABLE_STATES, **LIVE)
        .select_related("milestone__project")
        .prefetch_related("assignees")
        .order_by("submitted_at")
    )
    role = _role_of(user)
    is_reviewer = role in ("admin", "leader", "evaluator")

    # Indicadores: los propios del estudiante; los de sus proyectos para quien revisa
    scope = Deliverable.objects.filter(**LIVE)
    scope = scope.filter(milestone__project_id__in=_reviewable_project_ids(user)) if is_reviewer else scope.filter(assignees=user)
    counts = dict(scope.values_list("status").annotate(n=Count("pk", distinct=True)))
    kpis = {
        "pending": counts.get(Status.PENDING, 0) + counts.get(Status.REJECTED, 0),
        "in_review": counts.get(Status.SUBMITTED, 0) + counts.get(Status.IN_REVIEW, 0),
        "late": scope.filter(is_late=True).count(),
        "approved": counts.get(Status.APPROVED, 0),
    }

    overview = None
    if role == "admin":
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
            "role": role,
            "kpis": kpis,
            "overview": overview,
            "now": now,
            "nav": "home",
        },
    )


@login_required
def my_deliverables(request):
    deliverables = (
        Deliverable.objects.filter(assignees=request.user, **LIVE)
        .select_related("milestone__project")
        .annotate(version_count=Count("versions", distinct=True))
        .order_by("due_at")
    )
    return render(
        request, "web/my_deliverables.html", {"deliverables": deliverables, "now": timezone.now(), "nav": "mine"}
    )


def _get_project(request, pk):
    # Proyecto ajeno → 404, igual que en la API
    return get_object_or_404(filter_projects_for_user(Project.objects.all(), request.user), pk=pk)


@login_required
def project_detail(request, pk):
    project = _get_project(request, pk)
    metrics = project_metrics(project)
    milestones = project.milestones.prefetch_related("deliverables__assignees").order_by("due_date")
    memberships = sorted(
        project.memberships.select_related("user"),
        key=lambda m: ({Role.LEADER: 0, Role.MEMBER: 1}.get(m.role, 2), m.user.username.lower()),
    )
    status_labels = dict(Status.choices)
    chart = {
        "status_labels": [status_labels[s] for s in Status.values],
        "status_values": [metrics["deliverables"]["by_status"][s] for s in Status.values],
        "weeks": [w["week"] for w in metrics["commits"]["by_week"]],
        "commits": [w["count"] for w in metrics["commits"]["by_week"]],
        "members": [m["name"] for m in metrics["members"]],
        "member_commits": [m["commits"] for m in metrics["members"]],
    }
    can_manage = can_manage_members(request.user, project)
    return render(
        request,
        "web/project_detail.html",
        {
            "project": project,
            "metrics": metrics,
            "milestones": milestones,
            "memberships": memberships,
            "commits": Commit.objects.filter(project=project).select_related("author", "deliverable")[:8],
            "chart": chart,
            "can_review": can_review(request.user, project),
            "can_manage": can_manage,
            "milestone_form": MilestoneForm() if can_manage else None,
            "deliverable_form": DeliverableForm(project=project) if can_manage else None,
            "now": timezone.now(),
            "nav": "home",
        },
    )


@login_required
@require_POST
def milestone_create(request, pk):
    project = _get_project(request, pk)
    if not can_manage_members(request.user, project):
        raise PermissionDenied("Solo el líder del proyecto puede crear hitos.")
    form = MilestoneForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            milestone = Milestone.objects.create(project=project, **form.cleaned_data)
            log_action(
                request.user,
                Action.MILESTONE_CREATED,
                milestone,
                changes=diff({}, snapshot(milestone, ("title", "description", "due_date"))),
            )
        messages.success(request, f"Hito «{milestone.title}» creado.")
    else:
        messages.error(request, "Revisa el hito: el título y la fecha son obligatorios.")
    return redirect("web:project", pk=pk)


@login_required
@require_POST
def deliverable_create(request, pk):
    project = _get_project(request, pk)
    if not can_manage_members(request.user, project):
        raise PermissionDenied("Solo el líder del proyecto puede crear entregables.")
    form = DeliverableForm(request.POST, project=project)
    if not form.is_valid():
        messages.error(request, "Revisa el entregable: hito, título y fecha de entrega son obligatorios.")
        return redirect("web:project", pk=pk)
    data = form.cleaned_data
    with transaction.atomic():
        deliverable = Deliverable.objects.create(
            milestone=data["milestone"], title=data["title"], description=data["description"], due_at=data["due_at"]
        )
        log_action(
            request.user,
            Action.DELIVERABLE_CREATED,
            deliverable,
            changes=diff({}, snapshot(deliverable, ("title", "description", "due_at"))),
        )
        # Asigna, audita y avisa a cada asignado (Etapa 4)
        set_deliverable_assignees(deliverable, request.user, list(data["assignees"]))
    messages.success(request, f"Entregable «{deliverable.title}» creado y asignado.")
    return redirect("web:deliverable", pk=deliverable.pk)


@login_required
def project_audit(request, pk):
    """La auditoría del proyecto en la web, con filtros: solo líder, evaluador del proyecto o admin."""
    project = _get_project(request, pk)
    if not can_review(request.user, project):
        raise PermissionDenied("Solo el líder, el evaluador del proyecto o un administrador puede ver la auditoría.")
    actors = User.objects.filter(memberships__project=project).order_by("first_name", "username").distinct()
    form = AuditFilterForm(request.GET or None, actors=actors)
    logs = AuditLog.objects.filter(project=project).select_related("actor")
    if form.is_valid():
        data = form.cleaned_data
        if data["action"]:
            logs = logs.filter(action=data["action"])
        if data["actor"]:
            logs = logs.filter(actor=data["actor"])
        if data["date_from"]:
            logs = logs.filter(created_at__date__gte=data["date_from"])
        if data["date_to"]:
            logs = logs.filter(created_at__date__lte=data["date_to"])
    page = Paginator(logs, 25).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(
        request,
        "web/audit.html",
        {
            "project": project,
            "form": form,
            "page": page,
            "labels": dict(Action.choices),
            "targets": TARGET_LABELS,
            "query": query.urlencode(),
            "nav": "home",
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

    # Cada versión con la evaluación que recibió (la primera hecha después de entregarla)
    evaluations = list(deliverable.evaluations.select_related("evaluator").order_by("created_at"))
    versions = list(deliverable.versions.select_related("author").order_by("number"))
    for i, version in enumerate(versions):
        until = versions[i + 1].created_at if i + 1 < len(versions) else None
        version.evaluation = next(
            (e for e in evaluations if e.created_at >= version.created_at and (until is None or e.created_at < until)), None
        )
    versions.reverse()

    status = deliverable.status
    reached = {
        Status.PENDING: 0, Status.REJECTED: 0, Status.SUBMITTED: 1, Status.LATE: 1, Status.IN_REVIEW: 2, Status.APPROVED: 3,
    }[status]
    flow = [
        {"label": "Pendiente", "state": "done" if reached > 0 else "current"},
        {"label": "Entregado", "state": "done" if reached > 1 else ("current" if reached == 1 else "")},
        {"label": "En revisión", "state": "done" if reached > 2 else ("current" if reached == 2 else "")},
        {"label": "Aprobado o rechazado", "state": "current" if reached == 3 else ""},
    ]
    history = AuditLog.objects.filter(target_type="deliverable", target_id=deliverable.pk).select_related("actor")[:12]
    return render(
        request,
        "web/deliverable_detail.html",
        {
            "deliverable": deliverable,
            "project": project,
            "versions": versions,
            "evaluations": evaluations,
            "commits": deliverable.commits.select_related("author")[:20],
            "history": history,
            "labels": dict(Action.choices),
            "flow": flow,
            "can_submit": is_assignee and status in SUBMITTABLE_STATES,
            "can_evaluate": reviewer and status in EVALUABLE_STATES,
            "can_review": reviewer,
            "next_version": len(versions) + 1,
            "submit_form": SubmitForm(),
            "evaluate_form": EvaluateForm(),
            "nav": "home",
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
            "Entrega registrada. Se guardó una nueva versión y se avisó al líder y al evaluador.",
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
            "Evaluación registrada. Se avisó a los asignados.",
        )
    return redirect("web:deliverable", pk=pk)


@login_required
def notifications(request):
    if request.method == "POST":
        Notification.objects.filter(recipient=request.user, read_at__isnull=True).update(read_at=timezone.now())
        messages.success(request, "Todos los avisos quedaron como leídos.")
        return redirect("web:notifications")
    items = Notification.objects.filter(recipient=request.user).select_related("project")[:50]
    return render(request, "web/notifications.html", {"items": items, "nav": "notifications"})


@login_required
def notification_open(request, pk):
    """Marca el aviso como leído y lleva a su página. Solo redirige a rutas de este mismo sitio."""
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    if notification.url and url_has_allowed_host_and_scheme(notification.url, allowed_hosts={request.get_host()}):
        return redirect(notification.url)
    return redirect("web:notifications")


class LoginView(auth_views.LoginView):
    template_name = "web/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "github_oauth": oauth.is_configured()}


@login_required
def profile(request):
    previous = request.user.github_username
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        if user.github_username and user.github_username != previous:
            # Igual que en PATCH /api/auth/me/: los commits anteriores sin dueño pasan a ser suyos
            link_user_commits(user)
        messages.success(request, "Perfil actualizado.")
        return redirect("web:profile")
    return render(request, "web/profile.html", {"form": form, "nav": "profile"})
