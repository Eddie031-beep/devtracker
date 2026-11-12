from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project
from apps.projects.permissions import filter_projects_for_user

from .services import project_metrics


class ProjectMetricsView(APIView):
    """GET /api/projects/<id>/metrics/ — métricas del proyecto y por integrante (cualquier integrante o admin)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiResponse(description="Métricas del proyecto, de commits y por integrante")})
    def get(self, request, pk):
        # Proyecto ajeno → 404, como en el resto de la API
        project = get_object_or_404(filter_projects_for_user(Project.objects.all(), request.user), pk=pk)
        return Response(project_metrics(project))
