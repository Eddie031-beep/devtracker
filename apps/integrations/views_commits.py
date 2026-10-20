from django.shortcuts import get_object_or_404
from kombu.exceptions import OperationalError
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project
from apps.projects.permissions import filter_projects_for_user, is_global_admin, user_is_project_leader

from .models import Commit
from .serializers import CommitSerializer
from .tasks import sync_project_commits


class CommitPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def get_project_for_user(request, pk):
    # Proyecto ajeno → 404, como en el resto de la API
    return get_object_or_404(filter_projects_for_user(Project.objects.all(), request.user), pk=pk)


class ProjectCommitListView(generics.ListAPIView):
    """GET /api/projects/<id>/commits/ — cualquier integrante del proyecto (o admin).

    Filtros opcionales: ?author=<user_id> (o `none` para los sin vincular) &deliverable=<id> (o `none`)
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CommitSerializer
    pagination_class = CommitPagination

    @staticmethod
    def _filter_fk(commits, params, name):
        raw = params.get(name)
        if not raw:
            return commits
        if raw == "none":
            return commits.filter(**{f"{name}__isnull": True})
        if not raw.isdigit():
            raise serializers.ValidationError({name: "Usa un id numérico o `none`."})
        return commits.filter(**{f"{name}_id": int(raw)})

    def get_queryset(self):
        project = get_project_for_user(self.request, self.kwargs["pk"])
        commits = Commit.objects.filter(project=project).select_related("author", "deliverable")
        commits = self._filter_fk(commits, self.request.query_params, "author")
        return self._filter_fk(commits, self.request.query_params, "deliverable")


class ProjectCommitSyncView(APIView):
    """POST /api/projects/<id>/commits/sync/ — el líder (o admin) pide traer el historial desde GitHub."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        project = get_project_for_user(request, pk)
        if not (is_global_admin(request.user) or user_is_project_leader(request.user, project)):
            raise PermissionDenied("Solo el líder del proyecto puede sincronizar los commits.")
        if not project.github_repo:
            raise serializers.ValidationError({"github_repo": "El proyecto no tiene un repo de GitHub vinculado."})
        try:
            sync_project_commits.delay(project.pk)
        except OperationalError:
            # Redis caído o dormido (Railway plan gratis): no se pudo encolar
            return Response(
                {"detail": "No se pudo encolar la sincronización. Intenta de nuevo en un momento."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Sincronización en cola."}, status=status.HTTP_202_ACCEPTED)
