from rest_framework import serializers

from .models import Deliverable, Milestone, Project
from .permissions import (
    filter_deliverables_for_user,
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
        read_only_fields = ("id", "is_late", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            self.fields["milestone"].queryset = filter_milestones_for_user(
                Milestone.objects.all(), request.user
            )