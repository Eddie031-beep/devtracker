"""API de incidencias. Mismas reglas que la web: todo pasa por apps/issues/services.py."""

from django.contrib.auth import get_user_model
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
from .models import Issue
from .serializers import AssignSerializer, CommentSerializer, IssueEventSerializer, IssueSerializer, TransitionSerializer

User = get_user_model()


def get_issue(user, pk):
    # Incidencia de un proyecto ajeno → 404
    return get_object_or_404(
        Issue.objects.select_related("project", "reported_by", "assignee"),
        pk=pk, project__in=filter_projects_for_user(Project.objects.all(), user),
    )


def get_user_or_400(pk):
    if pk is None:
        return None
    user = User.objects.filter(pk=pk).first()
    if user is None:
        raise exceptions.ValidationError({"assignee_id": "No existe ese usuario."})
    return user


class ProjectIssueListView(generics.ListCreateAPIView):
    """GET/POST /api/projects/<id>/issues/ — incidencias del proyecto (filtros: status, priority, assignee)."""

    permission_classes = [IsAuthenticated]
    serializer_class = IssueSerializer
    queryset = Issue.objects.none()

    @extend_schema(parameters=[
        OpenApiParameter("status", str, enum=Issue.Status.values),
        OpenApiParameter("priority", str, enum=Issue.Priority.values),
        OpenApiParameter("assignee", int),
    ])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        project = get_project_or_404(self.request.user, self.kwargs["pk"])
        issues = project.issues.select_related("reported_by", "assignee")
        for field in ("status", "priority"):
            if value := self.request.query_params.get(field):
                issues = issues.filter(**{field: value})
        if (assignee := self.request.query_params.get("assignee", "")).isdigit():
            issues = issues.filter(assignee_id=assignee)
        return issues

    def create(self, request, *args, **kwargs):
        project = get_project_or_404(request.user, kwargs["pk"])
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        assignee = get_user_or_400(data.pop("assignee_id", None))
        issue = run(lambda: services.create_issue(project, request.user, assignee=assignee, **data))
        return Response(IssueSerializer(issue).data, status=status.HTTP_201_CREATED)


class IssueDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/issues/<id>/ — editar: quien la reportó o el líder · borrar: el líder (lógico)."""

    permission_classes = [IsAuthenticated]
    serializer_class = IssueSerializer
    queryset = Issue.objects.none()
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_object(self):
        return get_issue(self.request.user, self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        issue = self.get_object()
        serializer = self.get_serializer(issue, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = {k: v for k, v in serializer.validated_data.items() if k in services.EDITABLE_FIELDS}
        issue = run(lambda: services.update_issue(issue, request.user, **data))
        return Response(IssueSerializer(issue).data)

    def destroy(self, request, *args, **kwargs):
        issue = self.get_object()
        run(lambda: services.delete_issue(issue, request.user))
        return Response(status=status.HTTP_204_NO_CONTENT)


class IssueAssignView(APIView):
    """POST /api/issues/<id>/assign/ — el líder asigna el responsable (`assignee_id`, o null para quitarlo)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=AssignSerializer, responses={200: IssueSerializer})
    def post(self, request, pk):
        issue = get_issue(request.user, pk)
        data = AssignSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        assignee = get_user_or_400(data.validated_data["assignee_id"])
        issue = run(lambda: services.assign_issue(issue, request.user, assignee))
        return Response(IssueSerializer(issue).data)


class IssueTransitionView(APIView):
    """POST /api/issues/<id>/transition/ — `start`, `resolve` (con comentario), `verify` o `reopen` (con motivo)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=TransitionSerializer, responses={200: IssueSerializer})
    def post(self, request, pk):
        issue = get_issue(request.user, pk)
        data = TransitionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        issue = run(lambda: services.transition_issue(
            issue, request.user, data.validated_data["action"], data.validated_data.get("comment", "")
        ))
        return Response(IssueSerializer(issue).data)


class IssueHistoryView(APIView):
    """GET /api/issues/<id>/history/ — historial completo · POST: agregar un comentario."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: IssueEventSerializer(many=True)})
    def get(self, request, pk):
        issue = get_issue(request.user, pk)
        return Response(IssueEventSerializer(issue.events.select_related("actor"), many=True).data)

    @extend_schema(request=CommentSerializer, responses={201: IssueEventSerializer})
    def post(self, request, pk):
        issue = get_issue(request.user, pk)
        data = CommentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        event = run(lambda: services.comment_issue(issue, request.user, data.validated_data["comment"]))
        return Response(IssueEventSerializer(event).data, status=status.HTTP_201_CREATED)
