from rest_framework import serializers

from .models import Deliverable, Milestone, Project
from .permissions import (
    filter_milestones_for_user,
    filter_projects_for_user,
)


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ("id", "name", "description", "owner", "start_date", "end_date", "created_at", "updated_at")
        read_only_fields = ("id", "owner", "created_at", "updated_at")


class MilestoneSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.none())

    class Meta:
        model = Milestone
        fields = ("id", "project", "title", "description", "due_date", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            self.fields["project"].queryset = filter_projects_for_user(Project.objects.all(), request.user)

    def validate_project(self, value):
        if self.instance and value != self.instance.project:
            raise serializers.ValidationError("No se puede mover un hito a otro proyecto.")
        return value


class DeliverableSerializer(serializers.ModelSerializer):
    milestone = serializers.PrimaryKeyRelatedField(queryset=Milestone.objects.none())
    assignees = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Deliverable
        fields = (
            "id",
            "milestone",
            "title",
            "description",
            "due_at",
            "submitted_at",
            "assignees",
            "status",
            "is_late",
            "created_at",
            "updated_at",
        )
        # El estado y la fecha de entrega solo cambian con apps/projects/services.py
        read_only_fields = ("id", "status", "submitted_at", "is_late", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            self.fields["milestone"].queryset = filter_milestones_for_user(
                Milestone.objects.all(), request.user
            )

    def validate_milestone(self, value):
        if self.instance and value.project_id != self.instance.milestone.project_id:
            raise serializers.ValidationError("No se puede mover un entregable a otro proyecto.")
        return value