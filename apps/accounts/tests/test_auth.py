import re

from django.core import mail
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User

PASSWORD = "Clave-Segura-2026"


def create_user(username, role=User.GlobalRole.STUDENT, **extra):
    return User.objects.create_user(
        username=username, email=f"{username}@example.com", password=PASSWORD, global_role=role, **extra
    )


class LoginTests(APITestCase):
    def setUp(self):
        self.user = create_user("estudiante")

    def login(self, password):
        return self.client.post(reverse("token_obtain_pair"), {"username": "estudiante", "password": password})

    def test_login_correcto_devuelve_tokens(self):
        response = self.login(PASSWORD)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_incorrecto_es_rechazado(self):
        response = self.login("otra-clave")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("access", response.data)

    def test_me_devuelve_datos_y_rol(self):
        access = self.login(PASSWORD).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = self.client.get(reverse("me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "estudiante")
        self.assertEqual(response.data["global_role"], User.GlobalRole.STUDENT)

    def test_me_sin_token_es_rechazado(self):
        response = self.client.get(reverse("me"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_invalida_el_refresh_token(self):
        tokens = self.login(PASSWORD).data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = self.client.post(reverse("logout"), {"refresh": tokens["refresh"]})
        self.assertEqual(response.status_code, status.HTTP_205_RESET_CONTENT)

        response = self.client.post(reverse("token_refresh"), {"refresh": tokens["refresh"]})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class RegisterTests(APITestCase):
    def test_registro_crea_estudiante(self):
        data = {"username": "nuevo", "email": "nuevo@example.com", "password": PASSWORD}
        response = self.client.post(reverse("register"), data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("password", response.data)
        user = User.objects.get(username="nuevo")
        self.assertEqual(user.global_role, User.GlobalRole.STUDENT)
        self.assertTrue(user.check_password(PASSWORD))

    def test_registro_ignora_el_rol_enviado(self):
        data = {"username": "listo", "email": "listo@example.com", "password": PASSWORD, "global_role": "admin"}
        self.client.post(reverse("register"), data)
        self.assertEqual(User.objects.get(username="listo").global_role, User.GlobalRole.STUDENT)

    def test_registro_rechaza_contrasena_debil(self):
        data = {"username": "debil", "email": "debil@example.com", "password": "123"}
        response = self.client.post(reverse("register"), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="debil").exists())


class PasswordResetTests(APITestCase):
    def setUp(self):
        self.user = create_user("olvidadizo")

    def test_reset_de_punta_a_punta(self):
        response = self.client.post(reverse("password_reset"), {"email": "olvidadizo@example.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

        body = mail.outbox[0].body
        uid = re.search(r"uid: (\S+)", body).group(1)
        token = re.search(r"token: (\S+)", body).group(1)

        nueva = "Nueva-Clave-2026"
        response = self.client.post(
            reverse("password_reset_confirm"), {"uid": uid, "token": token, "new_password": nueva}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(reverse("token_obtain_pair"), {"username": "olvidadizo", "password": nueva})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # El token es de un solo uso: al cambiar la contraseña deja de ser válido
        response = self.client.post(
            reverse("password_reset_confirm"), {"uid": uid, "token": token, "new_password": "Otra-Clave-2026"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_email_inexistente_no_revela_nada(self):
        response = self.client.post(reverse("password_reset"), {"email": "nadie@example.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_token_invalido_es_rechazado(self):
        response = self.client.post(
            reverse("password_reset_confirm"), {"uid": "MQ", "token": "falso", "new_password": "Nueva-Clave-2026"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))


class GlobalRoleTests(APITestCase):
    def setUp(self):
        self.admin = create_user("admin", User.GlobalRole.ADMIN)
        self.evaluador = create_user("evaluador", User.GlobalRole.EVALUATOR)
        self.estudiante = create_user("estudiante")

    def cambiar_rol(self, target, role):
        return self.client.patch(reverse("user_role", args=[target.pk]), {"global_role": role})

    def test_estudiante_no_puede_cambiar_roles(self):
        self.client.force_authenticate(self.estudiante)
        response = self.cambiar_rol(self.estudiante, User.GlobalRole.ADMIN)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.estudiante.refresh_from_db()
        self.assertEqual(self.estudiante.global_role, User.GlobalRole.STUDENT)

    def test_evaluador_no_puede_cambiar_roles(self):
        self.client.force_authenticate(self.evaluador)
        response = self.cambiar_rol(self.estudiante, User.GlobalRole.EVALUATOR)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_estudiante_no_puede_listar_usuarios(self):
        self.client.force_authenticate(self.estudiante)
        response = self.client.get(reverse("user_list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_puede_cambiar_roles(self):
        self.client.force_authenticate(self.admin)
        response = self.cambiar_rol(self.estudiante, User.GlobalRole.EVALUATOR)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["global_role"], User.GlobalRole.EVALUATOR)
        self.estudiante.refresh_from_db()
        self.assertEqual(self.estudiante.global_role, User.GlobalRole.EVALUATOR)

    def test_admin_no_puede_asignar_rol_inexistente(self):
        self.client.force_authenticate(self.admin)
        response = self.cambiar_rol(self.estudiante, "superjefe")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sin_autenticar_no_puede_cambiar_roles(self):
        response = self.cambiar_rol(self.estudiante, User.GlobalRole.ADMIN)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
