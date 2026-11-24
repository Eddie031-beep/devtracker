"""API de reuniones y acuerdos. Mismas reglas que la web (apps/meetings/services.py)."""

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api import run
from apps.projects.access import get_project_or_404
from apps.projects.models import Project
from apps.projects.permissions import filter_projects_for_user

from . import services
from .models import Agreement, Meeting
from .serializers import AgreementSerializer, MeetingSerializer

User = get_user_model()


def _projects(user):
    return filter_projects_for_user(Project.objects.all(), user)


def get_meeting(user, pk):
    return get_object_or_404(
        Meeting.objects.select_related("project", "created_by").prefetch_related("participants", "agreements__responsible"),
        pk=pk, project__in=_projects(user),
    )


def users_from_ids(ids, field):
    found = list(User.objects.filter(pk__in=ids))
    if len(found) != len(set(ids)):
        raise exceptions.ValidationError({field: "Hay usuarios que no existen."})
    return found


class ProjectMeetingListView(generics.ListCreateAPIView):
    """GET/POST /api/projects/<id>/meetings/ — actas del proyecto (crear: estudiantes, con `participant_ids`)."""

    permission_classes = [IsAuthenticated]
    serializer_class = MeetingSerializer
    queryset = Meeting.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        project = get_project_or_404(self.request.user, self.kwargs["pk"])
        return project.meetings.select_related("created_by").prefetch_related("participants", "agreements__responsible")

    def create(self, request, *args, **kwargs):
        project = get_project_or_404(request.user, kwargs["pk"])
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data["participants"] = users_from_ids(data.pop("participant_ids", []), "participant_ids")
        meeting = run(lambda: services.create_meeting(project, request.user, **data))
        return Response(MeetingSerializer(get_meeting(request.user, meeting.pk)).data, status=status.HTTP_201_CREATED)


class MeetingDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/meetings/<id>/ — editar o borrar (lógico): quien la registró o el líder."""

    permission_classes = [IsAuthenticated]
    serializer_class = MeetingSerializer
    queryset = Meeting.objects.none()
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_object(self):
        return get_meeting(self.request.user, self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        meeting = self.get_object()
        serializer = self.get_serializer(meeting, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if "participant_ids" in data:
            data["participants"] = users_from_ids(data.pop("participant_ids"), "participant_ids")
        run(lambda: services.update_meeting(meeting, request.user, **data))
        return Response(MeetingSerializer(get_meeting(request.user, meeting.pk)).data)

    def destroy(self, request, *args, **kwargs):
        meeting = self.get_object()
        run(lambda: services.delete_meeting(meeting, request.user))
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeetingAgreementListView(APIView):
    """POST /api/meetings/<id>/agreements/ — registrar un acuerdo (`description`, `responsible_id`, `due_date`)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=AgreementSerializer, responses={201: AgreementSerializer})
    def post(self, request, pk):
        meeting = get_meeting(request.user, pk)
        data = AgreementSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        if "responsible_id" not in values:
            raise exceptions.ValidationError({"responsible_id": "Indica el responsable."})
        values["responsible"] = users_from_ids([values.pop("responsible_id")], "responsible_id")[0]
        values.pop("status", None)
        agreement = run(lambda: services.add_agreement(meeting, request.user, **values))
        return Response(AgreementSerializer(agreement).data, status=status.HTTP_201_CREATED)


class ProjectAgreementListView(generics.ListAPIView):
    """GET /api/projects/<id>/agreements/ — acuerdos del proyecto (filtros: status pending/done/overdue, responsible)."""

    permission_classes = [IsAuthenticated]
    serializer_class = AgreementSerializer
    queryset = Agreement.objects.none()

    @extend_schema(parameters=[
        OpenApiParameter("status", str, enum=["pending", "done", "overdue"]),
        OpenApiParameter("responsible", int),
    ])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        project = get_project_or_404(self.request.user, self.kwargs["pk"])
        agreements = services.project_agreements(project)
        value = self.request.query_params.get("status")
        if value == "overdue":
            agreements = agreements.filter(status=Agreement.Status.PENDING, due_date__lt=timezone.localdate())
        elif value in Agreement.Status.values:
            agreements = agreements.filter(status=value)
        if (responsible := self.request.query_params.get("responsible", "")).isdigit():
            agreements = agreements.filter(responsible_id=responsible)
        return agreements


class AgreementDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/agreements/<id>/ — actualizar: su responsable o el líder (reasignar: solo el líder)."""

    permission_classes = [IsAuthenticated]
    serializer_class = AgreementSerializer
    queryset = Agreement.objects.none()
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return get_object_or_404(
            Agreement.objects.select_related("meeting__project", "responsible", "completed_by"),
            pk=self.kwargs["pk"], meeting__deleted_at__isnull=True, meeting__project__in=_projects(self.request.user),
        )

    def update(self, request, *args, **kwargs):
        agreement = self.get_object()
        serializer = self.get_serializer(agreement, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        if "responsible_id" in values:
            values["responsible"] = users_from_ids([values.pop("responsible_id")], "responsible_id")[0]
        agreement = run(lambda: services.update_agreement(agreement, request.user, **values))
        return Response(AgreementSerializer(agreement).data)
