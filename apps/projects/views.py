from django.db import transaction
from rest_framework import generics
from rest_framework.permissions import SAFE_METHODS

from apps.audit.mixins import AuditedMixin

from .models import Deliverable, Milestone, Project, ProjectMembership
from .permissions import (
    IsProjectLeader,
    IsProjectMember,
    filter_deliverables_for_user,
    filter_milestones_for_user,
    filter_projects_for_user,
    user_is_project_leader,
)
from .serializers import DeliverableSerializer, MilestoneSerializer, ProjectSerializer

# Campos que se guardan en el antes/después de la auditoría
# (el secreto del webhook no se audita a propósito)
PROJECT_AUDIT_FIELDS = ("name", "description", "start_date", "end_date", "github_repo")
MILESTONE_AUDIT_FIELDS = ("title", "description", "due_date")
DELIVERABLE_AUDIT_FIELDS = ("title", "description", "due_at")


class ProjectPermissionMixin:
    def get_permissions(self):
        permission_class = IsProjectMember if self.request.method in SAFE_METHODS else IsProjectLeader
        return [permission_class()]


class ProjectListCreateView(AuditedMixin, ProjectPermissionMixin, generics.ListCreateAPIView):
    audit_entity = "project"
    audit_fields = PROJECT_AUDIT_FIELDS
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return filter_projects_for_user(super().get_queryset(), self.request.user)

    @transaction.atomic
    def perform_create(self, serializer):
        project = serializer.save(owner=self.request.user)
        ProjectMembership.objects.create(
            project=project,
            user=self.request.user,
            role=ProjectMembership.ProjectRole.LEADER,
        )
        self.audit_created(project)


class ProjectDetailView(AuditedMixin, ProjectPermissionMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_entity = "project"
    audit_fields = PROJECT_AUDIT_FIELDS
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return filter_projects_for_user(super().get_queryset(), self.request.user)


class MilestoneListCreateView(AuditedMixin, ProjectPermissionMixin, generics.ListCreateAPIView):
    audit_entity = "milestone"
    audit_fields = MILESTONE_AUDIT_FIELDS
    queryset = Milestone.objects.all()
    serializer_class = MilestoneSerializer

    def get_queryset(self):
        return filter_milestones_for_user(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        if not user_is_project_leader(self.request.user, project):
            self.permission_denied(self.request, message=IsProjectLeader.message)
        with transaction.atomic():
            self.audit_created(serializer.save())


class MilestoneDetailView(AuditedMixin, ProjectPermissionMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_entity = "milestone"
    audit_fields = MILESTONE_AUDIT_FIELDS
    queryset = Milestone.objects.all()
    serializer_class = MilestoneSerializer

    def get_queryset(self):
        return filter_milestones_for_user(super().get_queryset(), self.request.user)


class DeliverableListCreateView(AuditedMixin, ProjectPermissionMixin, generics.ListCreateAPIView):
    audit_entity = "deliverable"
    audit_fields = DELIVERABLE_AUDIT_FIELDS
    queryset = Deliverable.objects.all()
    serializer_class = DeliverableSerializer

    def get_queryset(self):
        return filter_deliverables_for_user(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        project = serializer.validated_data["milestone"].project
        if not user_is_project_leader(self.request.user, project):
            self.permission_denied(self.request, message=IsProjectLeader.message)
        with transaction.atomic():
            self.audit_created(serializer.save())


class DeliverableDetailView(AuditedMixin, ProjectPermissionMixin, generics.RetrieveUpdateDestroyAPIView):
    audit_entity = "deliverable"
    audit_fields = DELIVERABLE_AUDIT_FIELDS
    queryset = Deliverable.objects.all()
    serializer_class = DeliverableSerializer

    def get_queryset(self):
        return filter_deliverables_for_user(super().get_queryset(), self.request.user)