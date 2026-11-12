from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Notification
        fields = ("id", "kind", "kind_display", "title", "message", "url", "project", "read_at", "created_at")
        read_only_fields = fields
