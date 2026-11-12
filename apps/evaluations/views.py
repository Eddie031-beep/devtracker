from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Deliverable
from apps.projects.permissions import filter_deliverables_for_user

from .serializers import EvaluateSerializer, EvaluationSerializer
from .services import evaluate_deliverable


def get_deliverable_for_user(user, pk):
    # Entregable ajeno → 404, como en el resto de la API
    return get_object_or_404(filter_deliverables_for_user(Deliverable.objects.all(), user), pk=pk)


class DeliverableEvaluateView(APIView):
    """POST /api/deliverables/<id>/evaluate/ — el evaluador o el líder aprueba o rechaza con nota."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=EvaluateSerializer, responses={201: EvaluationSerializer})
    def post(self, request, pk):
        deliverable = get_deliverable_for_user(request.user, pk)
        data = EvaluateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            evaluation = evaluate_deliverable(deliverable, request.user, **data.validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages})
        return Response(EvaluationSerializer(evaluation).data, status=status.HTTP_201_CREATED)


class DeliverableEvaluationListView(generics.ListAPIView):
    """GET /api/deliverables/<id>/evaluations/ — historial de evaluaciones (la más reciente primero)."""

    permission_classes = [IsAuthenticated]
    serializer_class = EvaluationSerializer
    queryset = Deliverable.objects.none()  # para la documentación; get_queryset filtra por usuario

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        deliverable = get_deliverable_for_user(self.request.user, self.kwargs["pk"])
        return deliverable.evaluations.select_related("evaluator")
