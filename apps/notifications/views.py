from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(generics.ListAPIView):
    """GET /api/notifications/ — los avisos del usuario (?unread=1 para ver solo los no leídos)."""

    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    @extend_schema(parameters=[OpenApiParameter("unread", bool, description="Solo los no leídos")])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        queryset = Notification.objects.filter(recipient=self.request.user)
        if self.request.query_params.get("unread") in ("1", "true"):
            queryset = queryset.filter(read_at__isnull=True)
        return queryset


class NotificationReadView(APIView):
    """POST /api/notifications/<id>/read/ — marca un aviso propio como leído (ajeno → 404)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=NotificationSerializer)
    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(NotificationSerializer(notification).data)


class NotificationReadAllView(APIView):
    """POST /api/notifications/read-all/ — marca todos los avisos propios como leídos."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: OpenApiResponse(description='{"marked": <cantidad>}')})
    def post(self, request):
        marked = Notification.objects.filter(recipient=request.user, read_at__isnull=True).update(read_at=timezone.now())
        return Response({"marked": marked})
