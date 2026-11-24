"""API de riesgos. Mismas reglas que la web: todo pasa por apps/risks/services.py."""

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api import run
from apps.projects.access import get_project_or_404
from apps.projects.models import Project
from apps.projects.permissions import filter_projects_for_user

from . import matrix, services
from .models import Mitigation, Risk
from .serializers import MitigationDoneSerializer, MitigationSerializer, RiskSerializer, RiskStatusSerializer

User = get_user_model()


def get_risk(user, pk):
    return get_object_or_404(
        Risk.objects.select_related("project", "owner").prefetch_related("mitigations__responsible"),
        pk=pk, project__in=filter_projects_for_user(Project.objects.all(), user),
    )


def get_user_or_400(pk, field):
    if pk is None:
        return None
    user = User.objects.filter(pk=pk).first()
    if user is None:
        raise exceptions.ValidationError({field: "No existe ese usuario."})
    return user


class ProjectRiskListView(generics.ListCreateAPIView):
    """GET/POST /api/projects/<id>/risks/ — riesgos del proyecto (filtros: status, level)."""

    permission_classes = [IsAuthenticated]
    serializer_class = RiskSerializer
    queryset = Risk.objects.none()

    @extend_schema(parameters=[
        OpenApiParameter("status", str, enum=Risk.Status.values),
        OpenApiParameter("level", str, enum=list(matrix.LEVEL_LABELS)),
    ])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        project = get_project_or_404(self.request.user, self.kwargs["pk"])
        risks = project.risks.select_related("owner").prefetch_related("mitigations__responsible")
        if value := self.request.query_params.get("status"):
            risks = risks.filter(status=value)
        if value := self.request.query_params.get("level"):
            risks = risks.filter(score__in=[s for s in range(1, 10) if matrix.level_for_score(s) == value])
        return risks

    def create(self, request, *args, **kwargs):
        project = get_project_or_404(request.user, kwargs["pk"])
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        owner = get_user_or_400(data.pop("owner_id"), "owner_id")
        risk = run(lambda: services.create_risk(project, request.user, owner=owner, **data))
        return Response(RiskSerializer(risk).data, status=status.HTTP_201_CREATED)


class ProjectRiskMatrixView(APIView):
    """GET /api/projects/<id>/risks/matrix/ — matriz 3×3 con los riesgos abiertos de cada celda."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiResponse(description="Filas de probabilidad 3→1 con celdas de impacto 1→3")})
    def get(self, request, pk):
        project = get_project_or_404(request.user, pk)
        risks = [r for r in project.risks.all() if r.is_open]
        grid = matrix.build_matrix(risks)
        return Response({
            "rows": [
                {"probability": row["probability"], "cells": [
                    {"impact": c["impact"], "score": c["score"], "level": c["level"], "risks": [r.pk for r in c["risks"]]}
                    for c in row["cells"]
                ]}
                for row in grid["rows"]
            ],
        })


class RiskDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/risks/<id>/ — editar: líder o responsable · borrar: líder (lógico)."""

    permission_classes = [IsAuthenticated]
    serializer_class = RiskSerializer
    queryset = Risk.objects.none()
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_object(self):
        return get_risk(self.request.user, self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        risk = self.get_object()
        serializer = self.get_serializer(risk, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if "owner_id" in data:
            data["owner"] = get_user_or_400(data.pop("owner_id"), "owner_id")
        risk = run(lambda: services.update_risk(risk, request.user, **data))
        return Response(RiskSerializer(get_risk(request.user, risk.pk)).data)

    def destroy(self, request, *args, **kwargs):
        risk = self.get_object()
        run(lambda: services.delete_risk(risk, request.user))
        return Response(status=status.HTTP_204_NO_CONTENT)


class RiskStatusView(APIView):
    """POST /api/risks/<id>/status/ — cambia el estado (comentario obligatorio al materializarse o cerrarse)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=RiskStatusSerializer, responses={200: RiskSerializer})
    def post(self, request, pk):
        risk = get_risk(request.user, pk)
        data = RiskStatusSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        run(lambda: services.change_status(risk, request.user, data.validated_data["status"], data.validated_data.get("comment", "")))
        return Response(RiskSerializer(get_risk(request.user, pk)).data)


class RiskMitigationListView(APIView):
    """GET/POST /api/risks/<id>/mitigations/ — medidas de mitigación del riesgo."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: MitigationSerializer(many=True)})
    def get(self, request, pk):
        risk = get_risk(request.user, pk)
        return Response(MitigationSerializer(risk.mitigations.all(), many=True).data)

    @extend_schema(request=MitigationSerializer, responses={201: MitigationSerializer})
    def post(self, request, pk):
        risk = get_risk(request.user, pk)
        data = MitigationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        responsible = get_user_or_400(values.pop("responsible_id", None), "responsible_id")
        mitigation = run(lambda: services.add_mitigation(risk, request.user, responsible=responsible, **values))
        return Response(MitigationSerializer(mitigation).data, status=status.HTTP_201_CREATED)


class MitigationDoneView(APIView):
    """POST /api/mitigations/<id>/done/ — marca la medida como cumplida (`done: true`) o pendiente."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=MitigationDoneSerializer, responses={200: MitigationSerializer})
    def post(self, request, pk):
        mitigation = get_object_or_404(
            Mitigation.objects.select_related("risk__project"), pk=pk,
            risk__project__in=filter_projects_for_user(Project.objects.all(), request.user),
        )
        data = MitigationDoneSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        mitigation = run(lambda: services.set_mitigation_done(mitigation, request.user, data.validated_data["done"]))
        return Response(MitigationSerializer(mitigation).data)
