from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from .models import Deliverable, ProjectMembership

from .models import ProjectMembership

User = get_user_model()
Role = ProjectMembership.ProjectRole


def can_manage_members(user, project):
    """Admin global, o líder de ESE proyecto."""
    if user.is_superuser or user.global_role == user.GlobalRole.ADMIN:
        return True
    return ProjectMembership.objects.filter(project=project, user=user, role=Role.LEADER).exists()


def _check_can_manage(user, project):
    if not can_manage_members(user, project):
        raise PermissionDenied("Solo el líder del proyecto o un administrador puede gestionar integrantes.")


@transaction.atomic
def add_member(project, actor, email, role=Role.MEMBER, responsibilities=""):
    """Agrega a un usuario (buscado por correo) como integrante del proyecto."""
    _check_can_manage(actor, project)

    if role not in Role.values:
        raise ValidationError(f"«{role}» no es un rol válido.")

    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if user is None:
        raise ValidationError("No existe un usuario activo con ese correo.")

    if ProjectMembership.objects.filter(project=project, user=user).exists():
        raise ValidationError(f"{user} ya es integrante de este proyecto.")

    return ProjectMembership.objects.create(
        project=project, user=user, role=role, responsibilities=responsibilities
    )

def _is_last_leader(membership):
    """True si esta membresía es el único líder del proyecto."""
    if membership.role != Role.LEADER:
        return False
    # Bloquea las filas de líderes: dos cambios simultáneos no pueden dejar el proyecto sin líder
    leaders = list(
        ProjectMembership.objects.select_for_update().filter(
            project_id=membership.project_id, role=Role.LEADER
        )
    )
    return len(leaders) == 1


@transaction.atomic
def change_role(membership, actor, new_role):
    """Cambia el rol de un integrante dentro del proyecto."""
    membership = ProjectMembership.objects.select_for_update().select_related("project").get(pk=membership.pk)
    _check_can_manage(actor, membership.project)

    if new_role not in Role.values:
        raise ValidationError(f"«{new_role}» no es un rol válido.")

    if new_role != Role.LEADER and _is_last_leader(membership):
        raise ValidationError("El proyecto debe tener al menos un líder. Nombra otro líder antes de cambiar este rol.")

    membership.role = new_role
    membership.save(update_fields=["role", "updated_at"])
    return membership


@transaction.atomic
def remove_member(membership, actor):
    """Quita a un integrante del proyecto y de los entregables que tenía asignados."""
    membership = ProjectMembership.objects.select_for_update().select_related("project", "user").get(pk=membership.pk)
    _check_can_manage(actor, membership.project)

    if _is_last_leader(membership):
        raise ValidationError("No se puede quitar al único líder del proyecto.")

    # Ya no es miembro: deja de estar asignado a los entregables de este proyecto
    deliverables = Deliverable.objects.filter(milestone__project=membership.project, assignees=membership.user)
    for deliverable in deliverables:
        deliverable.assignees.remove(membership.user)

    membership.delete()

def update_responsibilities(membership, actor, text):
    """El líder define qué le toca a cada integrante."""
    membership = ProjectMembership.objects.select_related("project").get(pk=membership.pk)
    _check_can_manage(actor, membership.project)

    membership.responsibilities = text.strip()
    membership.save(update_fields=["responsibilities", "updated_at"])
    return membership


@transaction.atomic
def set_deliverable_assignees(deliverable, actor, users):
    """Define quiénes están a cargo de un entregable. Deben ser integrantes del proyecto."""
    deliverable = (
        Deliverable.objects.select_for_update()
        .select_related("milestone__project")
        .get(pk=deliverable.pk)
    )
    project = deliverable.project
    _check_can_manage(actor, project)

    user_ids = {user.pk for user in users}
    member_ids = set(
        ProjectMembership.objects.filter(project=project, user_id__in=user_ids)
        .values_list("user_id", flat=True)
    )
    if user_ids - member_ids:
        raise ValidationError("Solo se puede asignar el entregable a integrantes del proyecto.")

    deliverable.assignees.set(user_ids)
    return deliverable