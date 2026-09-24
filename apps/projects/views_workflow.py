from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Deliverable
from .permissions import filter_deliverables_for_user
from .serializers import DeliverableSerializer
from .services import change_status, submit_deliverable


class DeliverableActionView(APIView):
    """Base: busca el entregable solo entre los proyectos del usuario (ajeno → 404)."""

    permission_classes = [IsAuthenticated]

    def get_deliverable(self, pk):
        queryset = filter_deliverables_for_user(Deliverable.objects.all(), self.request.user)
        return get_object_or_404(queryset, pk=pk)

    def run(self, action, *args):
        try:
            deliverable = action(*args)
        except DjangoValidationError as exc:
            # DRF no convierte la ValidationError de Django: la traducimos a un 400
            raise serializers.ValidationError({"detail": exc.messages})
        return Response(DeliverableSerializer(deliverable, context={"request": self.request}).data)


class DeliverableSubmitView(DeliverableActionView):
    """POST /api/deliverables/{id}/submit/ — el integrante asignado entrega."""

    def post(self, request, pk):
        deliverable = self.get_deliverable(pk)
        return self.run(submit_deliverable, deliverable, request.user)


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.CharField()


class DeliverableStatusView(DeliverableActionView):
    """POST /api/deliverables/{id}/status/ — evaluador o líder revisa: {"status": "in_review"}."""

    def post(self, request, pk):
        deliverable = self.get_deliverable(pk)
        data = StatusChangeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self.run(change_status, deliverable, request.user, data.validated_data["status"])
