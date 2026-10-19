import hashlib
import hmac
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.projects.models import Project, ProjectMembership

from ..models import Commit

User = get_user_model()
Role = ProjectMembership.ProjectRole
SECRET = "super-secreto"
SHA_A = "a" * 40
SHA_B = "b" * 40


def push_payload(*shas, repo="equipo/devtracker"):
    return {
        "ref": "refs/heads/develop",
        "repository": {"full_name": repo},
        "commits": [
            {
                "id": sha,
                "message": f"Commit {sha[:7]}\n\nDetalle",
                "timestamp": "2026-10-18T21:30:00-05:00",
                "url": f"https://github.com/{repo}/commit/{sha}",
                "author": {"name": "Carlos Miranda", "email": "carlos@x.com", "username": "carlosm"},
            }
            for sha in shas
        ],
    }


def sign(body, secret=SECRET):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class GitHubWebhookTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x")
        self.project = Project.objects.create(
            name="Demo", owner=self.leader, github_repo="equipo/devtracker", github_webhook_secret=SECRET
        )
        ProjectMembership.objects.create(project=self.project, user=self.leader, role=Role.LEADER)
        self.client = APIClient()
        self.url = f"/api/integrations/github/webhook/{self.project.pk}/"

    def post(self, payload, event="push", signature=None, url=None):
        body = json.dumps(payload).encode()
        headers = {"HTTP_X_GITHUB_EVENT": event}
        signature = sign(body) if signature is None else signature
        if signature:
            headers["HTTP_X_HUB_SIGNATURE_256"] = signature
        return self.client.post(url or self.url, data=body, content_type="application/json", **headers)

    def test_firma_valida_guarda_los_commits(self):
        response = self.post(push_payload(SHA_A, SHA_B))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created"], 2)
        commit = Commit.objects.get(project=self.project, sha=SHA_A)
        self.assertEqual(commit.author_name, "Carlos Miranda")
        self.assertEqual(commit.author_email, "carlos@x.com")
        self.assertEqual(commit.github_username, "carlosm")
        self.assertTrue(commit.message.startswith("Commit aaaaaaa"))
        self.assertEqual(commit.url, f"https://github.com/equipo/devtracker/commit/{SHA_A}")
        self.assertEqual(commit.committed_at.isoformat(), "2026-10-19T02:30:00+00:00")

    def test_firma_invalida_403(self):
        response = self.post(push_payload(SHA_A), signature=sign(b"otro cuerpo"))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Commit.objects.exists())

    def test_firma_con_otro_secreto_403(self):
        body = json.dumps(push_payload(SHA_A)).encode()
        response = self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="push",
            HTTP_X_HUB_SIGNATURE_256=sign(body, "otro"),
        )
        self.assertEqual(response.status_code, 403)

    def test_sin_firma_403(self):
        self.assertEqual(self.post(push_payload(SHA_A), signature="").status_code, 403)

    def test_proyecto_sin_secreto_rechaza_todo(self):
        self.project.github_webhook_secret = ""
        self.project.save()
        body = json.dumps(push_payload(SHA_A)).encode()
        self.assertEqual(self.post(push_payload(SHA_A), signature=sign(body, "")).status_code, 403)

    def test_mismo_push_dos_veces_no_duplica(self):
        payload = push_payload(SHA_A, SHA_B)
        self.assertEqual(self.post(payload).data["created"], 2)
        response = self.post(payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(Commit.objects.filter(project=self.project).count(), 2)

    def test_mismo_sha_en_otro_proyecto_si_se_guarda(self):
        other = Project.objects.create(name="Otro", owner=self.leader, github_webhook_secret=SECRET)
        self.post(push_payload(SHA_A))
        self.post(push_payload(SHA_A), url=f"/api/integrations/github/webhook/{other.pk}/")
        self.assertEqual(Commit.objects.filter(sha=SHA_A).count(), 2)

    def test_ping_responde_pong(self):
        response = self.post({"zen": "Keep it simple."}, event="ping")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["detail"], "pong")

    def test_otro_evento_se_ignora(self):
        response = self.post({"action": "opened"}, event="issues")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Commit.objects.exists())

    def test_push_de_otro_repo_400(self):
        response = self.post(push_payload(SHA_A, repo="otro/repo"))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Commit.objects.exists())

    def test_proyecto_inexistente_o_borrado_404(self):
        response = self.post(push_payload(SHA_A), url="/api/integrations/github/webhook/9999/")
        self.assertEqual(response.status_code, 404)
        self.project.delete()
        self.assertEqual(self.post(push_payload(SHA_A)).status_code, 404)

    def test_solo_acepta_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


class GitHubProjectFieldsTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x")
        self.member = User.objects.create_user("ana", "ana@x.com", "x")
        self.project = Project.objects.create(name="Demo", owner=self.leader)
        ProjectMembership.objects.create(project=self.project, user=self.leader, role=Role.LEADER)
        ProjectMembership.objects.create(project=self.project, user=self.member, role=Role.MEMBER)
        self.client = APIClient()
        self.url = f"/api/projects/{self.project.pk}/"

    def test_lider_vincula_repo_y_secreto(self):
        self.client.force_authenticate(self.leader)
        response = self.client.patch(
            self.url, {"github_repo": "equipo/devtracker", "github_webhook_secret": SECRET}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.github_repo, "equipo/devtracker")
        self.assertEqual(self.project.github_webhook_secret, SECRET)

    def test_el_secreto_nunca_se_devuelve(self):
        self.project.github_webhook_secret = SECRET
        self.project.save()
        self.client.force_authenticate(self.member)
        response = self.client.get(self.url)
        self.assertNotIn("github_webhook_secret", response.data)
        self.assertTrue(response.data["has_github_webhook_secret"])

    def test_integrante_no_puede_editar_la_integracion(self):
        self.client.force_authenticate(self.member)
        response = self.client.patch(self.url, {"github_repo": "otro/repo"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.project.refresh_from_db()
        self.assertEqual(self.project.github_repo, "")

    def test_formato_de_repo_invalido_400(self):
        self.client.force_authenticate(self.leader)
        for value in ("https://github.com/equipo/devtracker", "sin-barra", "a/b/c"):
            response = self.client.patch(self.url, {"github_repo": value}, format="json")
            self.assertEqual(response.status_code, 400, value)

    def test_auditoria_registra_el_repo_pero_no_el_secreto(self):
        self.client.force_authenticate(self.leader)
        self.client.patch(
            self.url, {"github_repo": "equipo/devtracker", "github_webhook_secret": SECRET}, format="json"
        )
        log = AuditLog.objects.filter(project=self.project).first()
        self.assertIn("github_repo", log.changes)
        self.assertNotIn(SECRET, json.dumps(log.changes))
