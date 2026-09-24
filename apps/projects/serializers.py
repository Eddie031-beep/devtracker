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

    def validate(self, attrs):
        # En un PATCH parcial, usa el valor guardado si no viene en la petición
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": "La fecha de fin no puede ser anterior a la fecha de inicio."}
            )
        return attrs


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

    def validate(self, attrs):
        project = attrs.get("project", getattr(self.instance, "project", None))
        due = attrs.get("due_date", getattr(self.instance, "due_date", None))
        if project and due:
            if project.start_date and due < project.start_date:
                raise serializers.ValidationError(
                    {"due_date": "La fecha del hito no puede ser anterior al inicio del proyecto."}
                )
            if project.end_date and due > project.end_date:
                raise serializers.ValidationError(
                    {"due_date": "La fecha del hito no puede ser posterior al fin del proyecto."}
                )
        return attrs


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