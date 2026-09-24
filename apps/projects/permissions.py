from django.db.models import QuerySet
from rest_framework.permissions import BasePermission

from apps.accounts.models import User

from .models import Deliverable, Milestone, Project


def is_global_admin(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.global_role == User.GlobalRole.ADMIN)
    )


def project_for_object(obj):
    if isinstance(obj, Project):
        return obj
    if isinstance(obj, Milestone):
        return obj.project
    if isinstance(obj, Deliverable):
        return obj.milestone.project
    return getattr(obj, "project", None)


def user_is_project_member(user, project):
    return bool(
        user
        and user.is_authenticated
        and project
        and project.memberships.filter(user=user).exists()
    )


def user_is_project_leader(user, project):
    return bool(
        user
        and user.is_authenticated
        and project
        and project.memberships.filter(
            user=user, role=project.memberships.model.ProjectRole.LEADER
        ).exists()
    )


class IsProjectMember(BasePermission):
    """Permite operar sobre proyectos y recursos de proyectos propios."""

    message = "Debes ser integrante del proyecto."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if is_global_admin(request.user):
            return True
        return user_is_project_member(request.user, project_for_object(obj))


class IsProjectLeader(IsProjectMember):
    """Permite operar sobre un proyecto solo a sus líderes o al admin global."""

    message = "Debes ser líder del proyecto."

    def has_object_permission(self, request, view, obj):
        if is_global_admin(request.user):
            return True
        return user_is_project_leader(request.user, project_for_object(obj))


def filter_projects_for_user(queryset: QuerySet, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if is_global_admin(user):
        return queryset
    return queryset.filter(memberships__user=user).distinct()


def filter_milestones_for_user(queryset: QuerySet, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if is_global_admin(user):
        return queryset
    return queryset.filter(project__memberships__user=user).distinct()


def filter_deliverables_for_user(queryset: QuerySet, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if is_global_admin(user):
        return queryset
    return queryset.filter(milestone__project__memberships__user=user).distinct()