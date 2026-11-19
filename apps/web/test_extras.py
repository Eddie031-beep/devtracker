import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.integrations.models import Commit, PullRequest
from apps.projects.models import Deliverable, Milestone, Project, ProjectMembership

from .ical import calendar_token

User = get_user_model()
Role = ProjectMembership.ProjectRole


class Fixture(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x")
        self.ana = User.objects.create_user("ana", "ana@x.com", "x")
        self.leo = User.objects.create_user("leo", "leo@x.com", "x")
        self.project = Project.objects.create(name="Demo, curso", owner=self.leader)
        ProjectMembership.objects.create(project=self.project, user=self.leader, role=Role.LEADER)
        ProjectMembership.objects.create(project=self.project, user=self.ana, role=Role.MEMBER)
        ProjectMembership.objects.create(project=self.project, user=self.leo, role=Role.MEMBER)
        self.milestone = Milestone.objects.create(project=self.project, title="Hito 1", due_date=timezone.now().date())
        self.mine = Deliverable.objects.create(milestone=self.milestone, title="Informe; parte 1", due_at=timezone.now() + timedelta(days=3))
        self.mine.assignees.set([self.ana])
        self.other = Deliverable.objects.create(milestone=self.milestone, title="Manual", due_at=timezone.now() + timedelta(days=4))
        self.other.assignees.set([self.leo])


class CalendarTests(Fixture):
    def test_estudiante_ve_sus_entregas_y_el_lider_todas(self):
        self.client.force_login(self.ana)
        body = self.client.get(reverse("web:calendar_download")).content.decode()
        self.assertTrue(body.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertIn(f"UID:deliverable-{self.mine.pk}@devtracker", body)
        self.assertNotIn(f"UID:deliverable-{self.other.pk}@devtracker", body)
        self.assertIn(r"Informe\; parte 1 (Demo\, curso)", body)  # escapado según RFC 5545
        self.assertIn(f"UID:milestone-{self.milestone.pk}@devtracker", body)
        self.assertTrue(all(len(line.encode()) <= 75 for line in body.split("\r\n")))
        self.client.force_login(self.leader)
        self.assertIn(f"deliverable-{self.other.pk}", self.client.get(reverse("web:calendar_download")).content.decode())

    def test_enlace_firmado_sin_sesion_y_firma_falsa_404(self):
        url = reverse("web:calendar_feed", args=[calendar_token(self.ana)])
        response = self.client.get(url)
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn(f"deliverable-{self.mine.pk}", response.content.decode())
        bad = reverse("web:calendar_feed", args=[f"{self.leader.pk}:firma-falsa"])
        self.assertEqual(self.client.get(bad).status_code, 404)
        self.client.force_login(self.ana)
        self.assertContains(self.client.get(reverse("web:profile")), url)


class DarkModeTests(Fixture):
    def test_boton_de_tema_en_el_menu(self):
        self.client.force_login(self.ana)
        page = self.client.get(reverse("web:dashboard"))
        self.assertContains(page, 'id="theme-toggle"')
        self.assertContains(page, "devtracker-theme")


class FakeResponse:
    def __init__(self, data):
        self.data = json.dumps(data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *args):
        return self.data


class GeminiTests(Fixture):
    def setUp(self):
        super().setUp()
        PullRequest.objects.create(
            project=self.project, number=3, title="Informe", body="Agrega el informe", head_ref="feature/informe",
            base_ref="develop", opened_at=timezone.now(), deliverable=self.mine,
        )
        Commit.objects.create(project=self.project, sha="a" * 40, message="Agrega tablas", committed_at=timezone.now(), deliverable=self.mine)
        self.url = reverse("web:deliverable", args=[self.mine.pk])

    def test_sin_clave_no_aparece(self):
        self.client.force_login(self.leader)
        self.assertNotContains(self.client.get(self.url), "Sugerencias de Gemini")

    @override_settings(GEMINI_API_KEY="clave", GEMINI_MODEL="gemini-test")
    def test_revisor_pide_sugerencias_y_se_muestran(self):
        self.client.force_login(self.leader)
        self.assertContains(self.client.get(self.url), "Pedir sugerencias")
        answer = {"candidates": [{"content": {"parts": [{"text": "Qué cambia: agrega el informe."}]}}]}
        with mock.patch("apps.integrations.gemini.urlopen", return_value=FakeResponse(answer)) as urlopen:
            page = self.client.post(reverse("web:deliverable_gemini", args=[self.mine.pk]), follow=True)
        self.assertContains(page, "Qué cambia: agrega el informe.")
        request = urlopen.call_args.args[0]
        self.assertIn("models/gemini-test:generateContent", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"), "clave")
        prompt = json.loads(request.data)["contents"][0]["parts"][0]["text"]
        self.assertIn("Pull request #3: Informe", prompt)
        self.assertIn("- Agrega tablas", prompt)
        # Se muestra una vez
        self.assertNotContains(self.client.get(self.url), "Qué cambia: agrega el informe.")

    @override_settings(GEMINI_API_KEY="clave")
    def test_estudiante_no_puede_y_error_se_explica(self):
        self.client.force_login(self.ana)
        self.assertNotContains(self.client.get(self.url), "Pedir sugerencias")
        self.assertEqual(self.client.post(reverse("web:deliverable_gemini", args=[self.mine.pk])).status_code, 403)
        self.client.force_login(self.leader)
        with mock.patch("apps.integrations.gemini.urlopen", side_effect=OSError("red")):
            page = self.client.post(reverse("web:deliverable_gemini", args=[self.mine.pk]), follow=True)
        self.assertContains(page, "Gemini no respondió")
