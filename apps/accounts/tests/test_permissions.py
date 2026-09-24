from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.accounts.models import User
from apps.accounts.permissions import IsAdmin, IsEvaluator, IsStudent


class RolePermissionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def check(self, permission, user):
        request = self.factory.get("/")
        request.user = user
        return permission().has_permission(request, None)

    def test_cada_permiso_acepta_solo_su_rol(self):
        casos = {
            IsAdmin: User.GlobalRole.ADMIN,
            IsEvaluator: User.GlobalRole.EVALUATOR,
            IsStudent: User.GlobalRole.STUDENT,
        }
        for permission, rol_permitido in casos.items():
            for rol in User.GlobalRole.values:
                with self.subTest(permission=permission.__name__, rol=rol):
                    user = User(username=rol, global_role=rol)
                    self.assertEqual(self.check(permission, user), rol == rol_permitido)

    def test_anonimo_es_rechazado(self):
        for permission in (IsAdmin, IsEvaluator, IsStudent):
            with self.subTest(permission=permission.__name__):
                self.assertFalse(self.check(permission, AnonymousUser()))

    def test_superusuario_pasa_como_admin(self):
        user = User(username="root", is_superuser=True)
        self.assertTrue(self.check(IsAdmin, user))
