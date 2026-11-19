"""Lo que el líder administra desde la web: proyecto, hitos, entregables e integrantes.

Mismas reglas que la API: solo el líder del proyecto (o un admin) cambia algo, todo queda en la
auditoría y borrar es lógico (el registro sigue en la base con `deleted_at`).
"""

import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.audit.models import Action
from apps.audit.services import diff, log_action, snapshot
from apps.projects.models import Deliverable, Milestone, Project, ProjectMembership
from apps.projects.permissions import filter_projects_for_user
from apps.projects.services_members import (
    add_member, can_manage_members, change_role, remove_member, set_deliverable_assignees, update_responsibilities,
)

from .forms import DeliverableForm, MemberAddForm, MemberEditForm, MilestoneForm, ProjectForm

PROJECT_FIELDS = ("name", "description", "start_date", "end_date", "github_repo")
MILESTONE_FIELDS = ("title", "description", "due_date")
DELIVERABLE_FIELDS = ("title", "description", "due_at", "milestone_id")


def _managed_project(request, pk):
    # Proyecto ajeno → 404; propio pero sin ser líder → 403
    project = get_object_or_404(filter_projects_for_user(Project.objects.all(), request.user), pk=pk)
    if not can_manage_members(request.user, project):
        raise PermissionDenied("Solo el líder del proyecto o un administrador puede hacer esto.")
    return project


def _deleted(before):
    return {field: {"before": value, "after": None} for field, value in before.items()}


def _webhook_url(project):
    return settings.SITE_URL.rstrip("/") + reverse("github_webhook", args=[project.pk])


# --- Proyecto ----------------------------------------------------------------------------------


@login_required
def project_create(request):
    form = ProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            project = form.save(commit=False)
            project.owner = request.user
            project.save()
            ProjectMembership.objects.create(project=project, user=request.user, role=ProjectMembership.ProjectRole.LEADER)
            log_action(request.user, Action.PROJECT_CREATED, project, changes=diff({}, snapshot(project, PROJECT_FIELDS)))
        messages.success(request, f"Proyecto «{project.name}» creado. Eres su líder.")
        return redirect("web:project", pk=project.pk)
    return render(request, "web/project_form.html", {"form": form, "project": None, "nav": "home"})


@login_required
def project_edit(request, pk):
    project = _managed_project(request, pk)
    form = ProjectForm(request.POST or None, instance=project)
    new_secret = None
    if request.method == "POST" and form.is_valid():
        before = snapshot(Project.objects.get(pk=project.pk), PROJECT_FIELDS)
        with transaction.atomic():
            project = form.save(commit=False)
            changes = diff(before, snapshot(project, PROJECT_FIELDS))
            if form.cleaned_data["new_secret"]:
                new_secret = secrets.token_hex(32)
                project.github_webhook_secret = new_secret
                # El secreto nunca se guarda en la auditoría: solo que cambió
                changes["github_webhook_secret"] = {"before": "(oculto)", "after": "(nuevo, oculto)"}
            project.save()
            if changes:
                log_action(request.user, Action.PROJECT_UPDATED, project, changes=changes)
        if not new_secret:
            messages.success(request, "Proyecto actualizado.")
            return redirect("web:project", pk=project.pk)
        # Se muestra en esta misma respuesta y no se vuelve a mostrar
        form = ProjectForm(instance=project)
    return render(
        request,
        "web/project_form.html",
        {
            "form": form, "project": project, "new_secret": new_secret, "webhook_url": _webhook_url(project),
            "nav": "home",
        },
    )


@login_required
@require_POST
def project_delete(request, pk):
    project = _managed_project(request, pk)
    with transaction.atomic():
        before = snapshot(project, PROJECT_FIELDS)
        project.delete()  # lógico
        log_action(request.user, Action.PROJECT_DELETED, project, changes=_deleted(before))
    messages.success(request, f"Proyecto «{project.name}» eliminado. Su historial y su auditoría se conservan.")
    return redirect("web:dashboard")


# --- Hitos -------------------------------------------------------------------------------------


def _managed_milestone(request, pk):
    milestone = get_object_or_404(Milestone.objects.select_related("project"), pk=pk, project__deleted_at__isnull=True)
    _managed_project(request, milestone.project_id)
    return milestone


@login_required
def milestone_edit(request, pk):
    milestone = _managed_milestone(request, pk)
    initial = {f: getattr(milestone, f) for f in MILESTONE_FIELDS}
    form = MilestoneForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        before = snapshot(milestone, MILESTONE_FIELDS)
        with transaction.atomic():
            for field, value in form.cleaned_data.items():
                setattr(milestone, field, value)
            milestone.save()
            changes = diff(before, snapshot(milestone, MILESTONE_FIELDS))
            if changes:
                log_action(request.user, Action.MILESTONE_UPDATED, milestone, changes=changes)
        messages.success(request, f"Hito «{milestone.title}» actualizado.")
        return redirect("web:project", pk=milestone.project_id)
    return render(
        request, "web/milestone_form.html",
        {"form": form, "milestone": milestone, "project": milestone.project, "nav": "home"},
    )


@login_required
@require_POST
def milestone_delete(request, pk):
    milestone = _managed_milestone(request, pk)
    with transaction.atomic():
        before = snapshot(milestone, MILESTONE_FIELDS)
        milestone.delete()  # lógico: sus entregables dejan de verse, pero no se pierden
        log_action(request.user, Action.MILESTONE_DELETED, milestone, changes=_deleted(before))
    messages.success(request, f"Hito «{milestone.title}» eliminado.")
    return redirect("web:project", pk=milestone.project_id)


# --- Entregables -------------------------------------------------------------------------------


def _managed_deliverable(request, pk):
    deliverable = get_object_or_404(
        Deliverable.objects.select_related("milestone__project"),
        pk=pk, milestone__deleted_at__isnull=True, milestone__project__deleted_at__isnull=True,
    )
    _managed_project(request, deliverable.milestone.project_id)
    return deliverable


@login_required
def deliverable_edit(request, pk):
    deliverable = _managed_deliverable(request, pk)
    project = deliverable.project
    initial = {
        "milestone": deliverable.milestone_id, "title": deliverable.title, "description": deliverable.description,
        "due_at": deliverable.due_at, "assignees": list(deliverable.assignees.all()),
    }
    form = DeliverableForm(request.POST or None, initial=initial, project=project)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        before = snapshot(deliverable, DELIVERABLE_FIELDS)
        try:
            with transaction.atomic():
                deliverable.milestone = data["milestone"]
                deliverable.title = data["title"]
                deliverable.description = data["description"]
                # Cambiar la fecha no borra la marca de «tarde» (regla de negocio #4)
                deliverable.due_at = data["due_at"]
                deliverable.save()
                changes = diff(before, snapshot(deliverable, DELIVERABLE_FIELDS))
                if changes:
                    log_action(request.user, Action.DELIVERABLE_UPDATED, deliverable, changes=changes)
                set_deliverable_assignees(deliverable, request.user, list(data["assignees"]))
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, f"Entregable «{deliverable.title}» actualizado.")
            return redirect("web:deliverable", pk=deliverable.pk)
    return render(
        request, "web/deliverable_form.html",
        {"form": form, "deliverable": deliverable, "project": project, "nav": "home"},
    )


@login_required
@require_POST
def deliverable_delete(request, pk):
    deliverable = _managed_deliverable(request, pk)
    project_id = deliverable.milestone.project_id
    with transaction.atomic():
        before = snapshot(deliverable, DELIVERABLE_FIELDS)
        deliverable.delete()  # lógico: versiones y evaluaciones siguen guardadas
        log_action(request.user, Action.DELIVERABLE_DELETED, deliverable, changes=_deleted(before))
    messages.success(request, f"Entregable «{deliverable.title}» eliminado. Sus versiones y evaluaciones se conservan.")
    return redirect("web:project", pk=project_id)


# --- Integrantes -------------------------------------------------------------------------------


def _run(request, action, success):
    try:
        action()
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    except PermissionDenied as error:
        messages.error(request, str(error) or "No tienes permiso para esta acción.")
    else:
        messages.success(request, success)


@login_required
def members(request, pk):
    project = _managed_project(request, pk)
    add_form = MemberAddForm(request.POST or None, project=project)
    if request.method == "POST" and add_form.is_valid():
        data = add_form.cleaned_data
        user = data["user"]
        if not user.email:
            messages.error(request, "Ese usuario no tiene correo registrado; complétalo en su perfil primero.")
        else:
            _run(
                request,
                lambda: add_member(project, request.user, user.email, data["role"], data["responsibilities"]),
                f"{user.get_full_name() or user.username} agregado al proyecto.",
            )
            return redirect("web:members", pk=pk)
    memberships = sorted(
        project.memberships.select_related("user"),
        key=lambda m: ({ProjectMembership.ProjectRole.LEADER: 0, ProjectMembership.ProjectRole.MEMBER: 1}.get(m.role, 2), m.user.username.lower()),
    )
    rows = [
        (m, MemberEditForm(initial={"role": m.role, "responsibilities": m.responsibilities}, prefix=f"m{m.pk}"))
        for m in memberships
    ]
    return render(
        request, "web/members.html", {"project": project, "rows": rows, "add_form": add_form, "nav": "home"}
    )


def _membership(request, pk, member_pk):
    project = _managed_project(request, pk)
    return get_object_or_404(ProjectMembership.objects.select_related("user"), pk=member_pk, project=project)


@login_required
@require_POST
def member_update(request, pk, member_pk):
    membership = _membership(request, pk, member_pk)
    form = MemberEditForm(request.POST, prefix=f"m{membership.pk}")
    if form.is_valid():
        data = form.cleaned_data

        def apply():
            with transaction.atomic():
                if data["role"] != membership.role:
                    change_role(membership, request.user, data["role"])
                update_responsibilities(membership, request.user, data["responsibilities"])

        _run(request, apply, f"Cambios de {membership.user.get_full_name() or membership.user.username} guardados.")
    return redirect("web:members", pk=pk)


@login_required
@require_POST
def member_remove(request, pk, member_pk):
    membership = _membership(request, pk, member_pk)
    name = membership.user.get_full_name() or membership.user.username
    _run(request, lambda: remove_member(membership, request.user), f"{name} ya no es parte del proyecto.")
    return redirect("web:members", pk=pk)
