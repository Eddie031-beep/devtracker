from rest_framework import serializers

from apps.core.api import PersonSerializer

from .models import Issue, IssueEvent


class IssueSerializer(serializers.ModelSerializer):
    """Lectura y alta/edición de los campos libres. El estado y el responsable cambian con sus endpoints."""

    reported_by = PersonSerializer(read_only=True)
    assignee = PersonSerializer(read_only=True)
    assignee_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)

    class Meta:
        model = Issue
        fields = [
            "id", "project", "title", "description", "steps_to_reproduce", "priority", "priority_display",
            "status", "status_display", "reported_by", "assignee", "assignee_id", "resolved_at", "verified_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["project", "status", "resolved_at", "verified_at", "created_at", "updated_at"]

    def validate_title(self, value):
        if len(value.strip()) < 5:
            raise serializers.ValidationError("El título debe tener al menos 5 caracteres.")
        return value

    def validate_description(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Describe el error con al menos 10 caracteres.")
        return value


class IssueEventSerializer(serializers.ModelSerializer):
    actor = PersonSerializer(read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = IssueEvent
        fields = ["id", "kind", "kind_display", "actor", "from_status", "to_status", "comment", "data", "created_at"]


class AssignSerializer(serializers.Serializer):
    assignee_id = serializers.IntegerField(allow_null=True)


class TransitionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["start", "resolve", "verify", "reopen"])
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class CommentSerializer(serializers.Serializer):
    comment = serializers.CharField(max_length=2000)
