from rest_framework.permissions import BasePermission

from .models import User


class HasGlobalRole(BasePermission):
    """Permite el acceso solo a usuarios autenticados con alguno de los roles globales indicados."""

    allowed_roles = ()

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        # El superusuario de Django se trata como administrador
        if user.is_superuser:
            return True
        return user.global_role in self.allowed_roles


class IsAdmin(HasGlobalRole):
    message = "Solo un administrador puede realizar esta acción."
    allowed_roles = (User.GlobalRole.ADMIN,)


class IsEvaluator(HasGlobalRole):
    message = "Solo un evaluador puede realizar esta acción."
    allowed_roles = (User.GlobalRole.EVALUATOR,)


class IsStudent(HasGlobalRole):
    message = "Solo un estudiante puede realizar esta acción."
    allowed_roles = (User.GlobalRole.STUDENT,)
