from rest_framework import serializers

from apps.core.api import PersonSerializer

from .models import Mitigation, Risk


class MitigationSerializer(serializers.ModelSerializer):
    responsible = PersonSerializer(read_only=True)
    responsible_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Mitigation
        fields = ["id", "description", "responsible", "responsible_id", "due_date", "done", "done_at", "created_at"]
        read_only_fields = ["done", "done_at", "created_at"]


class RiskSerializer(serializers.ModelSerializer):
    owner = PersonSerializer(read_only=True)
    owner_id = serializers.IntegerField(write_only=True)
    probability = serializers.IntegerField(min_value=1, max_value=3)
    impact = serializers.IntegerField(min_value=1, max_value=3)
    level = serializers.CharField(read_only=True)
    level_display = serializers.CharField(source="level_label", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    mitigations = MitigationSerializer(many=True, read_only=True)

    class Meta:
        model = Risk
        fields = [
            "id", "project", "title", "description", "probability", "impact", "score", "level", "level_display",
            "status", "status_display", "owner", "owner_id", "mitigations", "created_at", "updated_at",
        ]
        read_only_fields = ["project", "score", "status", "created_at", "updated_at"]

    def validate_title(self, value):
        if len(value.strip()) < 5:
            raise serializers.ValidationError("El riesgo debe tener al menos 5 caracteres.")
        return value

    def validate_description(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Describe el riesgo con al menos 10 caracteres.")
        return value


class RiskStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Risk.Status.choices)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class MitigationDoneSerializer(serializers.Serializer):
    done = serializers.BooleanField()
