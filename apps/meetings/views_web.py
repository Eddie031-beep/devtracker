from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.core.web import form_errors, run_action
from apps.projects.access import get_project_or_404, is_leader, project_people
from apps.projects.models import Project
from apps.projects.permissions import filter_projects_for_user
from apps.web.modules import module_context

from . import services
from .forms import AgreementFilterForm, AgreementForm, AgreementStatusForm, MeetingForm
from .models import Agreement, Meeting


def _projects(request):
    return filter_projects_for_user(Project.objects.all(), request.user)


def _meeting(request, pk):
    return get_object_or_404(Meeting.objects.select_related("project", "created_by"), pk=pk, project__in=_projects(request))


def _agreement(request, pk):
    return get_object_or_404(
        Agreement.objects.select_related("meeting__project", "responsible"),
        pk=pk, meeting__deleted_at__isnull=True, meeting__project__in=_projects(request),
    )


def _filter_agreements(agreements, data):
    today = timezone.localdate()
    status = data.get("status")
    if status == "pending":
        agreements = agreements.filter(status=Agreement.Status.PENDING)
    elif status == "overdue":
        agreements = agreements.filter(status=Agreement.Status.PENDING, due_date__lt=today)
    elif status == "done":
        agreements = agreements.filter(status=Agreement.Status.DONE)
    if data.get("responsible"):
        agreements = agreements.filter(responsible=data["responsible"])
    return agreements


@login_required
def meeting_list(request, pk):
    project = get_project_or_404(request.user, pk)
    can_create = services.can_create(request.user, project)
    form = None
    if can_create:
        form = MeetingForm(request.POST or None, people=project_people(project),
                           initial={"participants": [request.user.pk], "held_at": timezone.localtime().replace(second=0, microsecond=0)})
        if request.method == "POST" and form.is_valid():
            created = {}

            def create():
                created["meeting"] = services.create_meeting(project, request.user, **form.cleaned_data)

            if run_action(request, create, "Acta registrada. Ahora agrega los acuerdos."):
                return redirect("meetings:detail", pk=created["meeting"].pk)
    elif request.method == "POST":
        raise PermissionDenied("Solo los estudiantes del proyecto registran reuniones.")

    today = timezone.localdate()
    meetings = project.meetings.select_related("created_by").prefetch_related("participants").annotate(
        n_agreements=Count("agreements"),
        n_pending=Count("agreements", filter=Q(agreements__status=Agreement.Status.PENDING)),
        n_overdue=Count("agreements", filter=Q(agreements__status=Agreement.Status.PENDING, agreements__due_date__lt=today)),
    )
    people = services.responsible_candidates(project)
    filters = AgreementFilterForm(request.GET or None, people=people)
    agreements = services.project_agreements(project)
    if filters.is_valid():
        agreements = _filter_agreements(agreements, filters.cleaned_data)
    if request.GET.get("mios"):
        agreements = agreements.filter(responsible=request.user)
    for agreement in agreements:
        agreement.can_update = services.can_update_agreement(request.user, agreement)
    all_agreements = services.project_agreements(project)
    totals = {
        "pending": all_agreements.filter(status=Agreement.Status.PENDING).count(),
        "overdue": all_agreements.filter(status=Agreement.Status.PENDING, due_date__lt=today).count(),
        "done": all_agreements.filter(status=Agreement.Status.DONE).count(),
    }
    return render(
        request, "meetings/list.html",
        module_context(project, "meetings", form=form, meetings=meetings, agreements=agreements, filters=filters,
                       totals=totals, filtered=bool(request.GET), open_form=request.method == "POST"),
    )


@login_required
def meeting_detail(request, pk):
    meeting = _meeting(request, pk)
    user = request.user
    can_edit = services.can_edit_meeting(user, meeting)
    agreements = list(meeting.agreements.select_related("responsible", "completed_by"))
    for agreement in agreements:
        agreement.can_update = services.can_update_agreement(user, agreement)
    return render(
        request, "meetings/detail.html",
        module_context(
            meeting.project, "meetings", meeting=meeting, can_edit=can_edit, agreements=agreements,
            participants=meeting.participants.order_by("first_name", "username"),
            agreement_form=AgreementForm(people=services.responsible_candidates(meeting.project), meeting=meeting) if can_edit else None,
        ),
    )


@login_required
def meeting_edit(request, pk):
    meeting = _meeting(request, pk)
    if not services.can_edit_meeting(request.user, meeting):
        raise PermissionDenied("Solo quien registró la reunión o el líder pueden editar el acta.")
    form = MeetingForm(request.POST or None, instance=Meeting.objects.get(pk=meeting.pk), people=project_people(meeting.project))
    if request.method == "POST" and form.is_valid():
        if run_action(request, lambda: services.update_meeting(meeting, request.user, **form.cleaned_data), "Acta actualizada."):
            return redirect("meetings:detail", pk=meeting.pk)
    return render(request, "meetings/form.html", module_context(meeting.project, "meetings", meeting=meeting, form=form))


@login_required
@require_POST
def meeting_delete(request, pk):
    meeting = _meeting(request, pk)
    if not services.can_edit_meeting(request.user, meeting):
        raise PermissionDenied("Solo quien registró la reunión o el líder pueden eliminarla.")
    services.delete_meeting(meeting, request.user)
    messages.success(request, f"Reunión «{meeting.title}» eliminada. El registro se conserva en la auditoría.")
    return redirect("meetings:list", pk=meeting.project_id)


@login_required
@require_POST
def agreement_add(request, pk):
    meeting = _meeting(request, pk)
    if not services.can_edit_meeting(request.user, meeting):
        raise PermissionDenied("Solo quien registró la reunión o el líder registran sus acuerdos.")
    form = AgreementForm(request.POST, people=services.responsible_candidates(meeting.project), meeting=meeting)
    if form.is_valid():
        run_action(request, lambda: services.add_agreement(meeting, request.user, **form.cleaned_data), "Acuerdo registrado.")
    else:
        form_errors(request, form)
    return redirect("meetings:detail", pk=meeting.pk)


@login_required
@require_POST
def agreement_status(request, pk):
    agreement = _agreement(request, pk)
    if not services.can_update_agreement(request.user, agreement):
        raise PermissionDenied("Solo el responsable del acuerdo o el líder pueden actualizarlo.")
    form = AgreementStatusForm(request.POST)
    if form.is_valid():
        done = form.cleaned_data["status"] == Agreement.Status.DONE
        run_action(request, lambda: services.update_agreement(agreement, request.user, status=form.cleaned_data["status"]),
                   "Acuerdo cumplido." if done else "Acuerdo marcado como pendiente.")
    else:
        form_errors(request, form)
    # Vuelve a donde estaba (lista de acuerdos o acta), solo si es una ruta de este sitio
    back = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(back)
    return redirect("meetings:detail", pk=agreement.meeting_id)


@login_required
def agreement_edit(request, pk):
    agreement = _agreement(request, pk)
    if not services.can_update_agreement(request.user, agreement):
        raise PermissionDenied("Solo el responsable del acuerdo o el líder pueden actualizarlo.")
    meeting = agreement.meeting
    form = AgreementForm(request.POST or None, instance=Agreement.objects.get(pk=agreement.pk),
                         people=services.responsible_candidates(meeting.project), meeting=meeting)
    if not is_leader(request.user, meeting.project):
        form.fields["responsible"].disabled = True  # solo el líder reasigna
    if request.method == "POST" and form.is_valid():
        if run_action(request, lambda: services.update_agreement(agreement, request.user, **form.cleaned_data), "Acuerdo actualizado."):
            return redirect("meetings:detail", pk=meeting.pk)
    return render(request, "meetings/agreement_form.html",
                  module_context(meeting.project, "meetings", meeting=meeting, agreement=agreement, form=form))
