"""API de solicitudes de cambio de alcance. Mismas reglas que la web (apps/scope/services.py)."""

from django.shortcuts import get_object_or_404
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
from .models import ChangeRequest
from .serializers import ChangeRequestSerializer, DecisionSerializer


def get_change(user, pk):
    return get_object_or_404(
        ChangeRequest.objects.select_related("project", "proposed_by", "decided_by"),
        pk=pk, project__in=filter_projects_for_user(Project.objects.all(), user),
    )


def deliverables_from_ids(project, ids):
    if ids is None:
        return None
    found = list(services.project_deliverables(project).filter(pk__in=ids))
    if len(found) != len(set(ids)):
        raise exceptions.ValidationError({"affected_deliverables": "Solo puedes referenciar entregables de este proyecto."})
    return found


class ProjectChangeListView(generics.ListCreateAPIView):
    """GET/POST /api/projects/<id>/change-requests/ — solicitudes del proyecto (filtro: status)."""

    permission_classes = [IsAuthenticated]
    serializer_class = ChangeRequestSerializer
    queryset = ChangeRequest.objects.none()

    @extend_schema(parameters=[OpenApiParameter("status", str, enum=ChangeRequest.Status.values)])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        project = get_project_or_404(self.request.user, self.kwargs["pk"])
        changes = project.change_requests.select_related("proposed_by", "decided_by")
        if value := self.request.query_params.get("status"):
            changes = changes.filter(status=value)
        return changes

    def create(self, request, *args, **kwargs):
        project = get_project_or_404(request.user, kwargs["pk"])
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data["affected_deliverables"] = deliverables_from_ids(project, data.pop("affected_deliverables", [])) or []
        change = run(lambda: services.propose_change(project, request.user, **data))
        return Response(ChangeRequestSerializer(change).data, status=status.HTTP_201_CREATED)


class ChangeDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/change-requests/<id>/ — editar: quien la propuso, mientras está pendiente. No se borran."""

    permission_classes = [IsAuthenticated]
    serializer_class = ChangeRequestSerializer
    queryset = ChangeRequest.objects.none()
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return get_change(self.request.user, self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        change = self.get_object()
        serializer = self.get_serializer(change, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        deliverables = deliverables_from_ids(change.project, data.pop("affected_deliverables", None))
        change = run(lambda: services.update_change(change, request.user, affected_deliverables=deliverables, **data))
        return Response(ChangeRequestSerializer(change).data)


class ChangeDecideView(APIView):
    """POST /api/change-requests/<id>/decide/ — el evaluador aprueba o rechaza (`decision`, `comment`)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=DecisionSerializer, responses={200: ChangeRequestSerializer})
    def post(self, request, pk):
        change = get_change(request.user, pk)
        data = DecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        change = run(lambda: services.decide_change(change, request.user, data.validated_data["decision"], data.validated_data["comment"]))
        return Response(ChangeRequestSerializer(change).data)


class ChangeWithdrawView(APIView):
    """POST /api/change-requests/<id>/withdraw/ — quien la propuso la retira (queda registrada)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: ChangeRequestSerializer})
    def post(self, request, pk):
        change = get_change(request.user, pk)
        change = run(lambda: services.withdraw_change(change, request.user))
        return Response(ChangeRequestSerializer(change).data)
