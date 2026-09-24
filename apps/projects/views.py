from django.db import transaction
from rest_framework import generics
from rest_framework.permissions import SAFE_METHODS

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


class ProjectPermissionMixin:
    def get_permissions(self):
        permission_class = IsProjectMember if self.request.method in SAFE_METHODS else IsProjectLeader
        return [permission_class()]


class ProjectListCreateView(ProjectPermissionMixin, generics.ListCreateAPIView):
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


class ProjectDetailView(ProjectPermissionMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return filter_projects_for_user(super().get_queryset(), self.request.user)


class MilestoneListCreateView(ProjectPermissionMixin, generics.ListCreateAPIView):
    queryset = Milestone.objects.all()
    serializer_class = MilestoneSerializer

    def get_queryset(self):
        return filter_milestones_for_user(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        if not user_is_project_leader(self.request.user, project):
            self.permission_denied(self.request, message=IsProjectLeader.message)
        serializer.save()


class MilestoneDetailView(ProjectPermissionMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Milestone.objects.all()
    serializer_class = MilestoneSerializer

    def get_queryset(self):
        return filter_milestones_for_user(super().get_queryset(), self.request.user)


class DeliverableListCreateView(ProjectPermissionMixin, generics.ListCreateAPIView):
    queryset = Deliverable.objects.all()
    serializer_class = DeliverableSerializer

    def get_queryset(self):
        return filter_deliverables_for_user(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        project = serializer.validated_data["milestone"].project
        if not user_is_project_leader(self.request.user, project):
            self.permission_denied(self.request, message=IsProjectLeader.message)
        serializer.save()


class DeliverableDetailView(ProjectPermissionMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Deliverable.objects.all()
    serializer_class = DeliverableSerializer

    def get_queryset(self):
        return filter_deliverables_for_user(super().get_queryset(), self.request.user)