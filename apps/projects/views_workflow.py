from urllib.parse import urlparse

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Deliverable
from .permissions import filter_deliverables_for_user
from .serializers import DeliverableSerializer, DeliverableVersionSerializer
from .services import change_status, submit_deliverable


class DeliverableActionView(APIView):
    """Base: busca el entregable solo entre los proyectos del usuario (ajeno → 404)."""

    permission_classes = [IsAuthenticated]

    def get_deliverable(self, pk):
        queryset = filter_deliverables_for_user(Deliverable.objects.all(), self.request.user)
        return get_object_or_404(queryset, pk=pk)

    def run(self, action, *args, **kwargs):
        try:
            deliverable = action(*args, **kwargs)
        except DjangoValidationError as exc:
            # DRF no convierte la ValidationError de Django: la traducimos a un 400
            raise serializers.ValidationError({"detail": exc.messages})
        return Response(DeliverableSerializer(deliverable, context={"request": self.request}).data)


class DeliverableSubmitSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=2000)
    comment = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_url(self, value):
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise serializers.ValidationError("La URL debe ser válida y usar el protocolo http o https.")
        return value


class DeliverableSubmitView(DeliverableActionView):
    """POST /api/deliverables/{id}/submit/ — el integrante asignado entrega."""

    def post(self, request, pk):
        deliverable = self.get_deliverable(pk)
        data = DeliverableSubmitSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self.run(
            submit_deliverable,
            deliverable,
            request.user,
            url=data.validated_data["url"],
            comment=data.validated_data.get("comment", ""),
        )


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.CharField()


class DeliverableStatusView(DeliverableActionView):
    """POST /api/deliverables/{id}/status/ — evaluador o líder revisa: {"status": "in_review"}."""

    def post(self, request, pk):
        deliverable = self.get_deliverable(pk)
        data = StatusChangeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self.run(change_status, deliverable, request.user, data.validated_data["status"])


class DeliverableVersionListView(generics.ListAPIView):
    """GET /api/deliverables/{id}/versions/ — historial de versiones del entregable (solo lectura)."""

    permission_classes = [IsAuthenticated]
    serializer_class = DeliverableVersionSerializer

    def get_queryset(self):
        deliverable = get_object_or_404(
            filter_deliverables_for_user(Deliverable.objects.all(), self.request.user),
            pk=self.kwargs["pk"],
        )
        return deliverable.versions.select_related("author").order_by("number")
