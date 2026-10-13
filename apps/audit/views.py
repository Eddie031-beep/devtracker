from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.projects.models import Project
from apps.projects.permissions import filter_projects_for_user
from apps.projects.services import can_review

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class ProjectAuditView(APIView):
    """GET /api/projects/<id>/audit/ — solo lectura.

    Quién puede verla: el líder, el evaluador de ESE proyecto o un admin global.
    Un integrante normal recibe 403; alguien ajeno al proyecto recibe 404 (como el resto de la API).

    Filtros opcionales: ?action=deliverable.submitted &date_from=2026-10-01 &date_to=2026-10-31
    """

    permission_classes = [IsAuthenticated]
    pagination_class = AuditPagination

    def get_project(self, pk):
        # all_objects: la auditoría de un proyecto eliminado lógicamente sigue siendo consultable
        return get_object_or_404(filter_projects_for_user(Project.all_objects.all(), self.request.user), pk=pk)

    @staticmethod
    def _parse_date(params, name):
        raw = params.get(name)
        if not raw:
            return None
        try:
            parsed = parse_date(raw)
        except ValueError:
            parsed = None
        if parsed is None:
            raise serializers.ValidationError({name: "Usa el formato AAAA-MM-DD."})
        return parsed

    def get(self, request, pk):
        project = self.get_project(pk)
        if not can_review(request.user, project):
            raise PermissionDenied("Solo el líder, el evaluador del proyecto o un administrador puede ver la auditoría.")

        logs = AuditLog.objects.filter(project=project).select_related("actor")

        action = request.query_params.get("action")
        if action:
            logs = logs.filter(action=action)
        date_from = self._parse_date(request.query_params, "date_from")
        if date_from:
            logs = logs.filter(created_at__date__gte=date_from)
        date_to = self._parse_date(request.query_params, "date_to")
        if date_to:
            logs = logs.filter(created_at__date__lte=date_to)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(logs, request, view=self)
        return paginator.get_paginated_response(AuditLogSerializer(page, many=True).data)
