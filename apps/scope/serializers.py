from rest_framework import serializers

from apps.core.api import PersonSerializer

from .models import ChangeRequest


class ChangeRequestSerializer(serializers.ModelSerializer):
    proposed_by = PersonSerializer(read_only=True)
    decided_by = PersonSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    affected_deliverables = serializers.ListField(
        child=serializers.IntegerField(), required=False, write_only=True,
        help_text="ids de entregables del proyecto (solo referencia; no se modifican)",
    )
    affected_deliverable_ids = serializers.SerializerMethodField()

    class Meta:
        model = ChangeRequest
        fields = [
            "id", "project", "title", "description", "justification", "expected_impact", "impact_level",
            "affected_deliverables", "affected_deliverable_ids", "status", "status_display", "proposed_by",
            "decided_by", "decided_at", "decision_comment", "created_at", "updated_at",
        ]
        read_only_fields = ["project", "status", "decided_at", "decision_comment", "created_at", "updated_at"]

    def get_affected_deliverable_ids(self, change) -> list[int]:
        return sorted(change.affected_deliverables.values_list("pk", flat=True))

    def validate(self, data):
        for name, minimum in (("title", 5), ("description", 10), ("justification", 10), ("expected_impact", 10)):
            if name in data and len(data[name].strip()) < minimum:
                raise serializers.ValidationError({name: f"Escribe al menos {minimum} caracteres."})
        return data


class DecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approved", "rejected"])
    comment = serializers.CharField(min_length=5, max_length=2000)
