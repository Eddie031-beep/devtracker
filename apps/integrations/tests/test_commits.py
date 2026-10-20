import io
import json
from datetime import timedelta
from unittest import mock
from urllib.error import HTTPError

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from kombu.exceptions import OperationalError
from rest_framework.test import APIClient

from apps.projects.models import Deliverable, Milestone, Project, ProjectMembership

from ..github_api import fetch_repo_commits
from ..models import Commit
from ..services import link_commits, save_push_commits
from ..tasks import sync_project_commits

User = get_user_model()
Role = ProjectMembership.ProjectRole


def push_commit(sha, message="Commit", username="", email="otro@x.com", name="Alguien"):
    return {
        "id": sha,
        "message": message,
        "timestamp": "2026-10-18T21:30:00-05:00",
        "url": f"https://github.com/equipo/devtracker/commit/{sha}",
        "author": {"name": name, "email": email, "username": username},
    }


def api_commit(sha, message="Commit", login=None, email="otro@x.com"):
    return {
        "sha": sha,
        "html_url": f"https://github.com/equipo/devtracker/commit/{sha}",
        "commit": {
            "message": message,
            "author": {"name": "Alguien", "email": email, "date": "2026-10-01T10:00:00Z"},
        },
        "author": {"login": login} if login else None,
    }


class ProjectFixture(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x", github_username="lider-gh")
        self.ana = User.objects.create_user("ana", "ana@x.com", "x", github_username="AnaDev")
        self.outsider = User.objects.create_user("ajeno", "ajeno@x.com", "x", github_username="ajeno-gh")
        self.project = Project.objects.create(name="Demo", owner=self.leader, github_repo="equipo/devtracker")
        ProjectMembership.objects.create(project=self.project, user=self.leader, role=Role.LEADER)
        ProjectMembership.objects.create(project=self.project, user=self.ana, role=Role.MEMBER)
        milestone = Milestone.objects.create(project=self.project, title="H1", due_date=timezone.now().date())
        self.deliverable = Deliverable.objects.create(
            milestone=milestone, title="Login", due_at=timezone.now() + timedelta(days=3)
        )

        self.other_project = Project.objects.create(name="Otro", owner=self.outsider)
        ProjectMembership.objects.create(project=self.other_project, user=self.outsider, role=Role.LEADER)
        other_milestone = Milestone.objects.create(
            project=self.other_project, title="H1", due_date=timezone.now().date()
        )
        self.other_deliverable = Deliverable.objects.create(
            milestone=other_milestone, title="Ajeno", due_at=timezone.now() + timedelta(days=3)
        )

    def save(self, *commits):
        save_push_commits(self.project, {"commits": list(commits)})


class CommitLinkTests(ProjectFixture):
    def test_github_username_conocido_vincula_al_integrante(self):
        # GitHub no distingue mayúsculas
        self.save(push_commit("a" * 40, username="anadev"))
        self.assertEqual(Commit.objects.get(sha="a" * 40).author, self.ana)

    def test_sin_username_vincula_por_email(self):
        self.save(push_commit("a" * 40, email="ANA@x.com"))
        self.assertEqual(Commit.objects.get(sha="a" * 40).author, self.ana)

    def test_email_noreply_de_github_vincula_por_username(self):
        self.save(push_commit("a" * 40, email="12345+AnaDev@users.noreply.github.com"))
        self.assertEqual(Commit.objects.get(sha="a" * 40).author, self.ana)

    def test_usuario_que_no_es_del_proyecto_no_se_vincula(self):
        self.save(push_commit("a" * 40, username="ajeno-gh", email="ajeno@x.com"))
        self.assertIsNone(Commit.objects.get(sha="a" * 40).author)

    def test_referencia_a_entregable_del_proyecto(self):
        self.save(push_commit("a" * 40, message=f"Agrega login #D{self.deliverable.pk}"))
        self.assertEqual(Commit.objects.get(sha="a" * 40).deliverable, self.deliverable)

    def test_referencia_a_entregable_de_otro_proyecto_no_se_vincula(self):
        self.save(push_commit("a" * 40, message=f"Agrega login #D{self.other_deliverable.pk}"))
        self.assertIsNone(Commit.objects.get(sha="a" * 40).deliverable)

    def test_referencia_inexistente_o_borrada_no_se_vincula(self):
        self.save(push_commit("a" * 40, message="Arregla algo #D9999"))
        deleted = Deliverable.objects.create(
            milestone=self.deliverable.milestone, title="Borrado", due_at=timezone.now()
        )
        deleted.delete()
        self.save(push_commit("b" * 40, message=f"Arregla algo #D{deleted.pk}"))
        self.assertFalse(Commit.objects.filter(deliverable__isnull=False).exists())

    def test_numero_mas_largo_no_coincide_por_prefijo(self):
        # #D{pk}0 no debe tomarse como #D{pk}
        self.save(push_commit("a" * 40, message=f"Cambio #D{self.deliverable.pk}0"))
        self.assertIsNone(Commit.objects.get(sha="a" * 40).deliverable)

    def test_registrar_github_username_despues_vincula_commits_anteriores(self):
        self.save(push_commit("a" * 40, username="leo-gh", email="leo@personal.com"))
        leo = User.objects.create_user("leo", "leo@x.com", "x")
        ProjectMembership.objects.create(project=self.project, user=leo, role=Role.MEMBER)

        client = APIClient()
        client.force_authenticate(leo)
        response = client.patch("/api/auth/me/", {"github_username": "Leo-GH"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Commit.objects.get(sha="a" * 40).author, leo)

    def test_link_commits_no_reemplaza_vinculos_existentes(self):
        self.save(push_commit("a" * 40, username="AnaDev"))
        self.ana.github_username = ""
        self.ana.save()
        self.leader.github_username = "AnaDev"
        self.leader.save()
        link_commits(self.project)
        self.assertEqual(Commit.objects.get(sha="a" * 40).author, self.ana)


class CommitListTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        self.save(
            push_commit("a" * 40, message=f"Login #D{self.deliverable.pk}", username="AnaDev"),
            push_commit("b" * 40, message="Refactor", username="lider-gh"),
            push_commit("c" * 40, message="Sin dueño", username="desconocido"),
        )
        self.client = APIClient()
        self.url = f"/api/projects/{self.project.pk}/commits/"

    def shas(self, response):
        return {c["sha"][0] for c in response.data["results"]}

    def test_integrante_ve_todos_los_commits(self):
        self.client.force_authenticate(self.ana)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        first = next(c for c in response.data["results"] if c["sha"] == "a" * 40)
        self.assertEqual(first["author"], self.ana.pk)
        self.assertEqual(first["deliverable"], self.deliverable.pk)
        self.assertEqual(first["deliverable_title"], "Login")

    def test_filtro_por_integrante(self):
        self.client.force_authenticate(self.ana)
        self.assertEqual(self.shas(self.client.get(self.url, {"author": self.ana.pk})), {"a"})
        self.assertEqual(self.shas(self.client.get(self.url, {"author": "none"})), {"c"})

    def test_filtro_por_entregable(self):
        self.client.force_authenticate(self.ana)
        self.assertEqual(self.shas(self.client.get(self.url, {"deliverable": self.deliverable.pk})), {"a"})
        self.assertEqual(self.shas(self.client.get(self.url, {"deliverable": "none"})), {"b", "c"})

    def test_filtro_invalido_400(self):
        self.client.force_authenticate(self.ana)
        self.assertEqual(self.client.get(self.url, {"author": "ana"}).status_code, 400)

    def test_ajeno_404_y_sin_autenticar_401(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.url).status_code, 404)


class CommitSyncTests(ProjectFixture):
    @override_settings(GITHUB_TOKEN="tkn")
    def test_tarea_guarda_historial_y_no_duplica_lo_del_webhook(self):
        self.save(push_commit("a" * 40))
        items = [
            api_commit("a" * 40),
            api_commit("b" * 40, message=f"Login #D{self.deliverable.pk}", login="AnaDev"),
            api_commit("c" * 40, email="lider@x.com"),
        ]
        with mock.patch("apps.integrations.tasks.fetch_repo_commits", return_value=items) as fetch:
            result = sync_project_commits(self.project.pk)
        fetch.assert_called_once_with("equipo/devtracker", "tkn")
        self.assertEqual(result["created"], 2)
        self.assertEqual(Commit.objects.filter(project=self.project).count(), 3)
        b = Commit.objects.get(sha="b" * 40)
        self.assertEqual((b.author, b.deliverable), (self.ana, self.deliverable))
        self.assertEqual(b.github_username, "AnaDev")
        self.assertEqual(Commit.objects.get(sha="c" * 40).author, self.leader)

    def test_tarea_sin_repo_no_llama_a_github(self):
        self.project.github_repo = ""
        self.project.save()
        with mock.patch("apps.integrations.tasks.fetch_repo_commits") as fetch:
            self.assertEqual(sync_project_commits(self.project.pk)["created"], 0)
        fetch.assert_not_called()

    def test_endpoint_lider_encola_la_tarea(self):
        client = APIClient()
        client.force_authenticate(self.leader)
        with mock.patch("apps.integrations.views_commits.sync_project_commits.delay") as delay:
            response = client.post(f"/api/projects/{self.project.pk}/commits/sync/")
        self.assertEqual(response.status_code, 202)
        delay.assert_called_once_with(self.project.pk)

    def test_endpoint_integrante_403_y_ajeno_404(self):
        client = APIClient()
        url = f"/api/projects/{self.project.pk}/commits/sync/"
        with mock.patch("apps.integrations.views_commits.sync_project_commits.delay") as delay:
            client.force_authenticate(self.ana)
            self.assertEqual(client.post(url).status_code, 403)
            client.force_authenticate(self.outsider)
            self.assertEqual(client.post(url).status_code, 404)
        delay.assert_not_called()

    def test_endpoint_sin_repo_400_y_redis_caido_503(self):
        client = APIClient()
        client.force_authenticate(self.leader)
        url = f"/api/projects/{self.project.pk}/commits/sync/"
        with mock.patch(
            "apps.integrations.views_commits.sync_project_commits.delay", side_effect=OperationalError
        ):
            self.assertEqual(client.post(url).status_code, 503)
        self.project.github_repo = ""
        self.project.save()
        self.assertEqual(client.post(url).status_code, 400)


class SyncCommandTests(ProjectFixture):
    def run_command(self, *args):
        out, err = io.StringIO(), io.StringIO()
        call_command("sync_github_commits", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_sincroniza_sin_celery(self):
        items = [api_commit("b" * 40, message=f"Login #D{self.deliverable.pk}", login="AnaDev")]
        with mock.patch("apps.integrations.tasks.fetch_repo_commits", return_value=items):
            out, _ = self.run_command(str(self.project.pk))
        self.assertIn("1 commits nuevos", out)
        b = Commit.objects.get(sha="b" * 40)
        self.assertEqual((b.author, b.deliverable), (self.ana, self.deliverable))

    @override_settings(GITHUB_TOKEN="")
    def test_all_solo_proyectos_con_repo(self):
        with mock.patch("apps.integrations.tasks.fetch_repo_commits", return_value=[]) as fetch:
            self.run_command("--all")
        fetch.assert_called_once_with("equipo/devtracker", "")

    def test_ids_o_all_y_proyecto_sin_repo(self):
        with self.assertRaises(CommandError):
            self.run_command()
        with self.assertRaises(CommandError):
            self.run_command("--all", str(self.project.pk))
        with self.assertRaisesMessage(CommandError, str(self.other_project.pk)):
            self.run_command(str(self.other_project.pk))

    def test_error_de_github_sigue_con_los_demas_y_falla_al_final(self):
        self.other_project.github_repo = "equipo/otro"
        self.other_project.save()
        error = HTTPError("url", 404, "Not Found", {}, None)
        with mock.patch("apps.integrations.tasks.fetch_repo_commits", side_effect=[error, []]) as fetch:
            with self.assertRaisesMessage(CommandError, "1 proyecto"):
                self.run_command("--all")
        self.assertEqual(fetch.call_count, 2)


class FakeResponse(io.BytesIO):
    def __init__(self, data, link=None):
        super().__init__(json.dumps(data).encode())
        self.headers = {"Link": link} if link else {}


class GitHubApiTests(TestCase):
    def test_pagina_siguiendo_link_y_manda_el_token(self):
        pages = [
            FakeResponse(
                [api_commit("a" * 40)], link='<https://api.github.com/x?page=2>; rel="next", <...>; rel="last"'
            ),
            FakeResponse([api_commit("b" * 40)]),
        ]
        with mock.patch("apps.integrations.github_api.urlopen", side_effect=pages) as urlopen:
            commits = fetch_repo_commits("equipo/devtracker", token="tkn")
        self.assertEqual([c["sha"] for c in commits], ["a" * 40, "b" * 40])
        first_request = urlopen.call_args_list[0].args[0]
        self.assertEqual(first_request.full_url, "https://api.github.com/repos/equipo/devtracker/commits?per_page=100")
        self.assertEqual(first_request.get_header("Authorization"), "Bearer tkn")
        self.assertEqual(urlopen.call_args_list[1].args[0].full_url, "https://api.github.com/x?page=2")

    def test_repo_inexistente_propaga_el_error(self):
        error = HTTPError("url", 404, "Not Found", {}, None)
        with mock.patch("apps.integrations.github_api.urlopen", side_effect=error):
            with self.assertRaises(HTTPError):
                fetch_repo_commits("equipo/no-existe")
