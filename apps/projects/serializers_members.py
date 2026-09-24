from rest_framework import serializers

from .models import ProjectMembership

Role = ProjectMembership.ProjectRole


class MembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = ProjectMembership
        fields = ("id", "user", "username", "email", "role", "responsibilities", "created_at")
        read_only_fields = fields


class AddMemberSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Role.choices, default=Role.MEMBER)
    responsibilities = serializers.CharField(required=False, allow_blank=True, default="")


class UpdateMemberSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Role.choices, required=False)
    responsibilities = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Envía al menos «role» o «responsibilities».")
        return attrs


class AssigneesSerializer(serializers.Serializer):
    assignees = serializers.ListField(child=serializers.IntegerField(), allow_empty=True)
