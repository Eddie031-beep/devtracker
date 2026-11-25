from rest_framework import serializers

from apps.core.api import PersonSerializer

from .models import Agreement, Meeting


class AgreementSerializer(serializers.ModelSerializer):
    responsible = PersonSerializer(read_only=True)
    responsible_id = serializers.IntegerField(write_only=True, required=False)
    completed_by = PersonSerializer(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    meeting_title = serializers.CharField(source="meeting.title", read_only=True)

    class Meta:
        model = Agreement
        fields = [
            "id", "meeting", "meeting_title", "description", "responsible", "responsible_id", "due_date", "status",
            "is_overdue", "completed_at", "completed_by", "created_at",
        ]
        read_only_fields = ["meeting", "completed_at", "created_at"]

    def validate_description(self, value):
        if len(value.strip()) < 5:
            raise serializers.ValidationError("Describe el acuerdo (al menos 5 caracteres).")
        return value


class MeetingSerializer(serializers.ModelSerializer):
    participants = PersonSerializer(many=True, read_only=True)
    participant_ids = serializers.ListField(child=serializers.IntegerField(), write_only=True, required=False)
    created_by = PersonSerializer(read_only=True)
    agreements = AgreementSerializer(many=True, read_only=True)

    class Meta:
        model = Meeting
        fields = [
            "id", "project", "title", "held_at", "location", "summary", "participants", "participant_ids",
            "created_by", "agreements", "created_at", "updated_at",
        ]
        read_only_fields = ["project", "created_at", "updated_at"]

    def validate_summary(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Resume los temas tratados (al menos 10 caracteres).")
        return value
