"""Acceso a un proyecto desde las vistas de los módulos (incidencias, riesgos, cambios de alcance, reuniones).

Mismas reglas que el resto de DevTracker: un proyecto ajeno da 404 (no se revela que existe)
y una acción sin permiso da 403.
"""

from django.shortcuts import get_object_or_404

from .models import Project, ProjectMembership
from .permissions import filter_projects_for_user, is_global_admin

Role = ProjectMembership.ProjectRole
ADMIN = "admin"


def get_project_or_404(user, pk):
    return get_object_or_404(filter_projects_for_user(Project.objects.all(), user), pk=pk)


def project_role(user, project):
    """«admin», «leader», «member», «evaluator» o None si no participa."""
    if is_global_admin(user):
        return ADMIN
    return ProjectMembership.objects.filter(project=project, user=user).values_list("role", flat=True).first()


def is_project_member(user, project):
    return project_role(user, project) is not None


def is_leader(user, project):
    return project_role(user, project) in (ADMIN, Role.LEADER)


def is_evaluator(user, project):
    """Evaluador de ESE proyecto (o admin global). El líder no cuenta: es un estudiante."""
    return project_role(user, project) in (ADMIN, Role.EVALUATOR)


def is_student(user, project):
    """Integrante que trabaja en el proyecto: líder o integrante (no el evaluador)."""
    return project_role(user, project) in (Role.LEADER, Role.MEMBER)


def project_people(project, roles=None):
    """Usuarios del proyecto (opcionalmente filtrados por rol), ordenados por nombre."""
    from django.contrib.auth import get_user_model

    memberships = ProjectMembership.objects.filter(project=project)
    if roles:
        memberships = memberships.filter(role__in=roles)
    return get_user_model().objects.filter(pk__in=memberships.values("user_id")).order_by("first_name", "username")
