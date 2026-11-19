import hashlib
import hmac
import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.evaluations.services import evaluate_deliverable
from apps.notifications.models import Notification
from apps.projects.models import Deliverable, Milestone, Project, ProjectMembership

from ..github_api import fetch_repo_extras
from ..models import Commit, PullRequest
from ..services import save_api_commits
from ..tasks import sync_project_commits

User = get_user_model()
Role = ProjectMembership.ProjectRole
Status = Deliverable.Status
SECRET = "super-secreto"


def pull(number, title="Login", login="AnaDev", action_state="open", merged=False, branch="feature/login", body=""):
    return {
        "number": number,
        "title": title,
        "body": body,
        "state": "closed" if merged or action_state == "closed" else "open",
        "draft": False,
        "user": {"login": login},
        "html_url": f"https://github.com/equipo/devtracker/pull/{number}",
        "head": {"ref": branch, "sha": "h" * 40},
        "base": {"ref": "develop"},
        "merge_commit_sha": "m" * 40,
        "created_at": "2026-11-10T10:00:00Z",
        "merged_at": "2026-11-11T10:00:00Z" if merged else None,
        "closed_at": "2026-11-11T10:00:00Z" if merged or action_state == "closed" else None,
    }


@override_settings(NOTIFICATIONS_SEND_EMAIL=False)
class PullRequestWebhookTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x", github_username="lider-gh")
        self.ana = User.objects.create_user("ana", "ana@x.com", "x", github_username="AnaDev")
        self.leo = User.objects.create_user("leo", "leo@x.com", "x", github_username="LeoDev")
        self.project = Project.objects.create(
            name="Demo", owner=self.leader, github_repo="equipo/devtracker", github_webhook_secret=SECRET
        )
        for user, role in ((self.leader, Role.LEADER), (self.ana, Role.MEMBER), (self.leo, Role.MEMBER)):
            ProjectMembership.objects.create(project=self.project, user=user, role=role)
        milestone = Milestone.objects.create(project=self.project, title="H1", due_date=timezone.now().date())
        self.deliverable = Deliverable.objects.create(
            milestone=milestone, title="Login", due_at=timezone.now() + timedelta(days=3)
        )
        self.deliverable.assignees.set([self.ana])
        self.client = APIClient()
        self.url = f"/api/integrations/github/webhook/{self.project.pk}/"

    def post(self, action, data, repo="equipo/devtracker"):
        body = json.dumps({"action": action, "pull_request": data, "repository": {"full_name": repo}}).encode()
        signature = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(
            self.url, data=body, content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request", HTTP_X_HUB_SIGNATURE_256=signature,
        )

    def test_pr_del_asignado_entrega_el_entregable(self):
        response = self.post("opened", pull(7, title=f"Login con JWT #D{self.deliverable.pk}"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("entregado con el PR #7", response.data["submission"])
        pr = PullRequest.objects.get(project=self.project, number=7)
        self.assertEqual((pr.author, pr.deliverable, pr.state), (self.ana, self.deliverable, PullRequest.State.OPEN))
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.status, Status.SUBMITTED)
        version = self.deliverable.versions.get()
        self.assertEqual(version.url, "https://github.com/equipo/devtracker/pull/7")
        self.assertEqual(version.author, self.ana)
        # El líder recibe el aviso de que hay algo por revisar
        self.assertTrue(Notification.objects.filter(recipient=self.leader, kind="submitted").exists())

    def test_rama_con_el_numero_tambien_vincula(self):
        self.post("opened", pull(8, title="Login", branch=f"feature/D{self.deliverable.pk}-login"))
        self.assertEqual(PullRequest.objects.get(number=8).deliverable, self.deliverable)

    def test_repetir_el_evento_no_duplica_y_actualiza_el_estado(self):
        data = pull(7, title=f"Login #D{self.deliverable.pk}")
        self.post("opened", data)
        self.post("opened", data)
        self.post("closed", pull(7, title=f"Login #D{self.deliverable.pk}", merged=True))
        self.assertEqual(PullRequest.objects.filter(project=self.project).count(), 1)
        pr = PullRequest.objects.get(number=7)
        self.assertEqual(pr.state, PullRequest.State.MERGED)
        self.assertEqual(pr.merge_sha, "m" * 40)
        self.assertEqual(self.deliverable.versions.count(), 1)

    def test_rechazado_y_nuevo_push_al_pr_entrega_version_2(self):
        data = pull(7, title=f"Login #D{self.deliverable.pk}")
        self.post("opened", data)
        evaluate_deliverable(self.deliverable, self.leader, "rejected", 60, "Faltan pruebas")
        response = self.post("synchronize", data)
        self.assertIn("entregado", response.data["submission"])
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.status, Status.SUBMITTED)
        self.assertEqual(self.deliverable.versions.count(), 2)

    def test_quien_no_es_asignado_no_entrega(self):
        response = self.post("opened", pull(9, title=f"Login #D{self.deliverable.pk}", login="LeoDev"))
        self.assertIn("no se entregó", response.data["submission"])
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.status, Status.PENDING)
        # El PR sí queda registrado y vinculado
        self.assertEqual(PullRequest.objects.get(number=9).author, self.leo)

    def test_cuenta_ajena_borrador_y_sin_referencia(self):
        self.assertIn("no es integrante", self.post("opened", pull(1, title=f"X #D{self.deliverable.pk}", login="nadie")).data["submission"])
        draft = pull(2, title=f"X #D{self.deliverable.pk}")
        draft["draft"] = True
        self.assertIn("borrador", self.post("opened", draft).data["submission"])
        self.assertIn("no menciona", self.post("opened", pull(3, title="Sin referencia")).data["submission"])
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.status, Status.PENDING)

    def test_otro_repo_400(self):
        response = self.post("opened", pull(7), repo="otro/repo")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PullRequest.objects.exists())


class GraphDataTests(TestCase):
    def setUp(self):
        leader = User.objects.create_user("lider", "lider@x.com", "x")
        self.project = Project.objects.create(name="Demo", owner=leader, github_repo="equipo/devtracker", github_webhook_secret=SECRET)

    def test_push_encadena_los_padres_y_guarda_la_rama(self):
        payload = {
            "ref": "refs/heads/feature/login",
            "before": "0" * 40,
            "repository": {"full_name": "equipo/devtracker"},
            "commits": [
                {"id": sha * 40, "message": "c", "timestamp": "2026-11-10T10:00:00Z", "url": "", "author": {}}
                for sha in ("a", "b")
            ],
        }
        body = json.dumps(payload).encode()
        signature = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        APIClient().post(
            f"/api/integrations/github/webhook/{self.project.pk}/", data=body, content_type="application/json",
            HTTP_X_GITHUB_EVENT="push", HTTP_X_HUB_SIGNATURE_256=signature,
        )
        a, b = Commit.objects.get(sha="a" * 40), Commit.objects.get(sha="b" * 40)
        self.assertEqual((a.parents, b.parents), ([], ["a" * 40]))
        self.assertEqual(b.branch, "feature/login")

    def test_sincronizar_completa_los_padres_reales(self):
        Commit.objects.create(project=self.project, sha="c" * 40, committed_at=timezone.now(), parents=["b" * 40])
        item = {
            "sha": "c" * 40,
            "commit": {"message": "Merge", "author": {"date": "2026-11-10T10:00:00Z"}},
            "parents": [{"sha": "a" * 40}, {"sha": "b" * 40}],
        }
        self.assertEqual(save_api_commits(self.project, [item], branch="main"), 0)
        commit = Commit.objects.get(sha="c" * 40)
        self.assertEqual(commit.parents, ["a" * 40, "b" * 40])
        self.assertEqual(commit.branch, "main")

    def test_tarea_guarda_ramas_y_pull_requests(self):
        main = [{"sha": "a" * 40, "commit": {"message": "base", "author": {"date": "2026-11-01T10:00:00Z"}}, "parents": []}]
        feature = [{"sha": "b" * 40, "commit": {"message": "login", "author": {"date": "2026-11-02T10:00:00Z"}}, "parents": [{"sha": "a" * 40}]}] + main
        with mock.patch("apps.integrations.tasks.fetch_repo_commits", return_value=main), mock.patch(
            "apps.integrations.tasks.fetch_repo_extras", return_value=("main", {"feature/login": feature}, [pull(4)])
        ):
            result = sync_project_commits(self.project.pk)
        self.assertEqual((result["created"], result["pull_requests"]), (2, 1))
        self.assertEqual(Commit.objects.get(sha="a" * 40).branch, "main")
        self.assertEqual(Commit.objects.get(sha="b" * 40).branch, "feature/login")
        # La sincronización registra el historial, pero no entrega nada por su cuenta
        self.assertEqual(PullRequest.objects.get(number=4).state, PullRequest.State.OPEN)

    def test_extras_pide_rama_principal_ramas_y_prs(self):
        def fake_get(url, token):
            if url.endswith("/repos/equipo/devtracker"):
                return {"default_branch": "main"}, ""
            if "/branches" in url:
                return [{"name": "main"}, {"name": "feature/x"}], ""
            if "/pulls" in url:
                return [pull(1)], ""
            return [{"sha": "b" * 40}], ""

        with mock.patch("apps.integrations.github_api._get", side_effect=fake_get) as get:
            default, branches, pulls = fetch_repo_extras("equipo/devtracker", "tkn")
        self.assertEqual(default, "main")
        self.assertEqual(list(branches), ["feature/x"])
        self.assertEqual(len(pulls), 1)
        self.assertIn("sha=feature%2Fx", " ".join(call.args[0] for call in get.call_args_list))
