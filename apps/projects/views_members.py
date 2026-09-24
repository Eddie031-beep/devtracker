from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Deliverable, Project, ProjectMembership
from .permissions import filter_deliverables_for_user, filter_projects_for_user
from .serializers import DeliverableSerializer
from .serializers_members import (
    AddMemberSerializer,
    AssigneesSerializer,
    MembershipSerializer,
    UpdateMemberSerializer,
)
from .services_members import (
    add_member,
    change_role,
    remove_member,
    set_deliverable_assignees,
    update_responsibilities,
)

User = get_user_model()


def run_service(action, *args):
    """Ejecuta un servicio y traduce la ValidationError de Django a un 400 de DRF."""
    try:
        return action(*args)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"detail": exc.messages})


class ProjectMembersView(APIView):
    """GET: integrantes del proyecto · POST: agregar por correo (solo líder o admin)."""

    permission_classes = [IsAuthenticated]

    def get_project(self, pk):
        # Proyecto ajeno → 404
        return get_object_or_404(filter_projects_for_user(Project.objects.all(), self.request.user), pk=pk)

    def get(self, request, pk):
        project = self.get_project(pk)
        memberships = project.memberships.select_related("user").order_by("created_at")
        return Response(MembershipSerializer(memberships, many=True).data)

    def post(self, request, pk):
        project = self.get_project(pk)
        data = AddMemberSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        membership = run_service(
            add_member, project, request.user, values["email"], values["role"], values["responsibilities"]
        )
        return Response(MembershipSerializer(membership).data, status=status.HTTP_201_CREATED)


class ProjectMemberDetailView(APIView):
    """PATCH: cambiar rol y/o responsabilidades · DELETE: quitar del proyecto."""

    permission_classes = [IsAuthenticated]

    def get_membership(self, pk, membership_id):
        project = get_object_or_404(filter_projects_for_user(Project.objects.all(), self.request.user), pk=pk)
        return get_object_or_404(ProjectMembership, pk=membership_id, project=project)

    def patch(self, request, pk, membership_id):
        membership = self.get_membership(pk, membership_id)
        data = UpdateMemberSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if "role" in data.validated_data:
            membership = run_service(change_role, membership, request.user, data.validated_data["role"])
        if "responsibilities" in data.validated_data:
            membership = run_service(
                update_responsibilities, membership, request.user, data.validated_data["responsibilities"]
            )
        return Response(MembershipSerializer(membership).data)

    def delete(self, request, pk, membership_id):
        membership = self.get_membership(pk, membership_id)
        run_service(remove_member, membership, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeliverableAssigneesView(APIView):
    """PUT: reemplaza la lista de asignados de un entregable: {"assignees": [ids]}."""

    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        queryset = filter_deliverables_for_user(Deliverable.objects.all(), request.user)
        deliverable = get_object_or_404(queryset, pk=pk)
        data = AssigneesSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        users = User.objects.filter(pk__in=data.validated_data["assignees"])
        if users.count() != len(set(data.validated_data["assignees"])):
            raise serializers.ValidationError({"assignees": "Algún usuario no existe."})
        deliverable = run_service(set_deliverable_assignees, deliverable, request.user, users)
        return Response(DeliverableSerializer(deliverable, context={"request": request}).data)
