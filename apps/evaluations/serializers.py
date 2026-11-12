from rest_framework import serializers

from apps.projects.serializers import DeliverableVersionAuthorSerializer

from .models import Evaluation


class EvaluationSerializer(serializers.ModelSerializer):
    evaluator = DeliverableVersionAuthorSerializer(read_only=True)
    decision_display = serializers.CharField(source="get_decision_display", read_only=True)

    class Meta:
        model = Evaluation
        fields = ("id", "deliverable", "evaluator", "decision", "decision_display", "score", "feedback", "created_at")
        read_only_fields = fields


class EvaluateSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=Evaluation.Decision.choices)
    score = serializers.IntegerField(min_value=0, max_value=100)
    feedback = serializers.CharField(required=False, allow_blank=True, default="")
