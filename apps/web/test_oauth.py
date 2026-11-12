import io
import json
from unittest import mock
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.integrations.models import Commit
from apps.projects.models import Project, ProjectMembership

User = get_user_model()
OAUTH = {"GITHUB_OAUTH_CLIENT_ID": "cid", "GITHUB_OAUTH_CLIENT_SECRET": "secreto"}


def fake_github(login="AnaDev", token_payload=None):
    """Simula las dos llamadas a GitHub: canjear el código y leer el usuario."""
    responses = [token_payload or {"access_token": "tok"}, {"login": login}]

    def urlopen(request, timeout=None):
        return io.BytesIO(json.dumps(responses.pop(0)).encode())

    return mock.patch("apps.web.oauth.urlopen", side_effect=urlopen)


@override_settings(**OAUTH)
class GitHubLoginTests(TestCase):
    def setUp(self):
        self.ana = User.objects.create_user("ana", "ana@x.com", "x", github_username="anadev")

    def start(self, next_url=""):
        response = self.client.get(reverse("web:github_login") + (f"?next={next_url}" if next_url else ""))
        query = parse_qs(urlparse(response["Location"]).query)
        return response, query

    def test_redirige_a_github_con_state(self):
        response, query = self.start()
        self.assertTrue(response["Location"].startswith("https://github.com/login/oauth/authorize?"))
        self.assertEqual(query["client_id"], ["cid"])
        self.assertEqual(query["redirect_uri"], ["http://testserver/login/github/callback/"])
        self.assertTrue(query["state"][0])

    def test_entra_si_el_github_username_esta_vinculado(self):
        _, query = self.start(next_url="/perfil/")
        with fake_github(login="AnaDev") as urlopen:
            response = self.client.get(reverse("web:github_callback"), {"code": "abc", "state": query["state"][0]})
        self.assertRedirects(response, "/perfil/", fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.ana.pk)
        token_request = urlopen.call_args_list[0].args[0]
        self.assertIn(b"client_secret=secreto", token_request.data)

    def test_cuenta_no_vinculada_no_entra(self):
        _, query = self.start()
        with fake_github(login="desconocido"):
            response = self.client.get(
                reverse("web:github_callback"), {"code": "abc", "state": query["state"][0]}, follow=True
            )
        self.assertContains(response, "@desconocido no está vinculada")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_state_invalido_o_github_caido(self):
        self.start()
        response = self.client.get(reverse("web:github_callback"), {"code": "abc", "state": "otro"}, follow=True)
        self.assertContains(response, "no es válida")
        _, query = self.start()
        with mock.patch("apps.web.oauth.urlopen", side_effect=URLError("sin red")):
            response = self.client.get(
                reverse("web:github_callback"), {"code": "abc", "state": query["state"][0]}, follow=True
            )
        self.assertContains(response, "No se pudo completar")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_boton_solo_si_esta_configurado(self):
        self.assertContains(self.client.get(reverse("web:login")), "Entrar con GitHub")
        with override_settings(GITHUB_OAUTH_CLIENT_ID=""):
            self.assertNotContains(self.client.get(reverse("web:login")), "Entrar con GitHub")
            self.assertRedirects(self.client.get(reverse("web:github_login")), reverse("web:login"))


class ProfileTests(TestCase):
    def test_guardar_github_username_vincula_commits(self):
        user = User.objects.create_user("leo", "leo@x.com", "x")
        project = Project.objects.create(name="Demo", owner=user)
        ProjectMembership.objects.create(project=project, user=user, role=ProjectMembership.ProjectRole.LEADER)
        Commit.objects.create(project=project, sha="a" * 40, github_username="Leo-GH", committed_at="2026-10-01T10:00Z")
        self.client.force_login(user)
        response = self.client.post(
            reverse("web:profile"), {"first_name": "Leo", "last_name": "Paz", "github_username": "Leo-GH"}
        )
        self.assertRedirects(response, reverse("web:profile"), fetch_redirect_response=False)
        self.assertEqual(Commit.objects.get().author, user)

    def test_github_username_invalido_o_repetido(self):
        User.objects.create_user("ana", "ana@x.com", "x", github_username="AnaDev")
        user = User.objects.create_user("leo", "leo@x.com", "x")
        self.client.force_login(user)
        for value in ("-mal-", "anadev"):
            response = self.client.post(reverse("web:profile"), {"first_name": "", "last_name": "", "github_username": value})
            self.assertEqual(response.status_code, 200)  # vuelve a mostrar el formulario con el error
            user.refresh_from_db()
            self.assertEqual(user.github_username, "")
