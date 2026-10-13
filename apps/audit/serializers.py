from rest_framework import serializers

from .models import Action, AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    action_display = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "actor",
            "actor_name",
            "action",
            "action_display",
            "project",
            "target_type",
            "target_id",
            "changes",
            "created_at",
        )
        read_only_fields = fields

    def get_actor_name(self, obj):
        return str(obj.actor) if obj.actor else "Sistema"

    def get_action_display(self, obj):
        return Action(obj.action).label if obj.action in Action.values else obj.action
