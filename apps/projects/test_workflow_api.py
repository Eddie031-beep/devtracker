from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Deliverable, Milestone, Project, ProjectMembership

User = get_user_model()
Status = Deliverable.Status
Role = ProjectMembership.ProjectRole


class WorkflowApiTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x")
        self.student = User.objects.create_user("ana", "ana@x.com", "x")
        self.evaluator = User.objects.create_user("prof", "prof@x.com", "x")
        self.outsider = User.objects.create_user("ajeno", "ajeno@x.com", "x")

        project = Project.objects.create(name="Demo", owner=self.leader)
        ProjectMembership.objects.create(project=project, user=self.leader, role=Role.LEADER)
        ProjectMembership.objects.create(project=project, user=self.student, role=Role.MEMBER)
        ProjectMembership.objects.create(project=project, user=self.evaluator, role=Role.EVALUATOR)

        milestone = Milestone.objects.create(project=project, title="H1", due_date=timezone.now().date())
        self.deliverable = Deliverable.objects.create(
            milestone=milestone, title="E1", due_at=timezone.now() + timedelta(days=1)
        )
        self.deliverable.assignees.add(self.student)

        self.client = APIClient()
        self.submit_url = f"/api/deliverables/{self.deliverable.pk}/submit/"
        self.status_url = f"/api/deliverables/{self.deliverable.pk}/status/"
        self.submit_data = {"url": "https://github.com/org/repo/pull/1", "comment": "Entrega inicial"}

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def test_estudiante_asignado_entrega(self):
        response = self.as_user(self.student).post(self.submit_url, self.submit_data, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Status.SUBMITTED)

    def test_entrega_tardia_queda_marcada(self):
        self.deliverable.due_at = timezone.now() - timedelta(hours=1)
        self.deliverable.save()
        response = self.as_user(self.student).post(self.submit_url, self.submit_data, format="json")
        self.assertEqual(response.data["status"], Status.LATE)
        self.assertTrue(response.data["is_late"])

    def test_no_asignado_recibe_403(self):
        response = self.as_user(self.leader).post(self.submit_url, self.submit_data, format="json")
        self.assertEqual(response.status_code, 403)

    def test_ajeno_recibe_404(self):
        response = self.as_user(self.outsider).post(self.submit_url, self.submit_data, format="json")
        self.assertEqual(response.status_code, 404)

    def test_entregar_dos_veces_da_400(self):
        self.as_user(self.student).post(self.submit_url, self.submit_data, format="json")
        response = self.client.post(self.submit_url, self.submit_data, format="json")
        self.assertEqual(response.status_code, 400)

    def test_flujo_completo_por_api(self):
        self.as_user(self.student).post(self.submit_url, self.submit_data, format="json")
        client = self.as_user(self.evaluator)
        client.post(self.status_url, {"status": "in_review"}, format="json")
        response = client.post(self.status_url, {"status": "approved"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Status.APPROVED)

    def test_estudiante_no_puede_revisar(self):
        self.as_user(self.student).post(self.submit_url, self.submit_data, format="json")
        response = self.client.post(self.status_url, {"status": "in_review"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_transicion_invalida_da_400(self):
        self.as_user(self.student).post(self.submit_url, self.submit_data, format="json")
        response = self.as_user(self.evaluator).post(self.status_url, {"status": "approved"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_sin_status_da_400(self):
        response = self.as_user(self.evaluator).post(self.status_url, {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_sin_url_da_400(self):
        response = self.as_user(self.student).post(self.submit_url, {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("url", response.data)

    def test_url_invalida_da_400(self):
        for bad_url in ["ftp://servidor.com/archivo", "no-es-url", "javascript:alert(1)"]:
            response = self.as_user(self.student).post(self.submit_url, {"url": bad_url}, format="json")
            self.assertEqual(response.status_code, 400)

    def test_submit_crea_version_y_auditoria(self):
        response = self.as_user(self.student).post(
            self.submit_url,
            {"url": "https://github.com/org/repo/pull/1", "comment": "Primera versión"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.deliverable.versions.count(), 1)
        v = self.deliverable.versions.first()
        self.assertEqual(v.number, 1)
        self.assertEqual(v.url, "https://github.com/org/repo/pull/1")
        self.assertEqual(v.comment, "Primera versión")
        self.assertEqual(v.author, self.student)

    def test_reentrega_crea_nueva_version_correlativa(self):
        self.as_user(self.student).post(
            self.submit_url, {"url": "https://github.com/org/repo/pull/1"}, format="json"
        )
        self.as_user(self.evaluator).post(self.status_url, {"status": "in_review"}, format="json")
        self.as_user(self.evaluator).post(self.status_url, {"status": "rejected"}, format="json")

        response = self.as_user(self.student).post(
            self.submit_url, {"url": "https://github.com/org/repo/pull/2"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.deliverable.versions.count(), 2)
        v2 = self.deliverable.versions.order_by("-number").first()
        self.assertEqual(v2.number, 2)
        self.assertEqual(v2.url, "https://github.com/org/repo/pull/2")

    def test_listar_versiones_integrantes_del_proyecto(self):
        self.as_user(self.student).post(
            self.submit_url, {"url": "https://github.com/org/repo/pull/1", "comment": "v1"}, format="json"
        )
        self.as_user(self.evaluator).post(self.status_url, {"status": "in_review"}, format="json")
        self.as_user(self.evaluator).post(self.status_url, {"status": "rejected"}, format="json")
        self.as_user(self.student).post(
            self.submit_url, {"url": "https://github.com/org/repo/pull/2", "comment": "v2"}, format="json"
        )

        versions_url = f"/api/deliverables/{self.deliverable.pk}/versions/"

        for user in (self.leader, self.student, self.evaluator):
            res = self.as_user(user).get(versions_url)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(len(res.data), 2)
            self.assertEqual(res.data[0]["number"], 1)
            self.assertEqual(res.data[0]["url"], "https://github.com/org/repo/pull/1")
            self.assertEqual(res.data[0]["comment"], "v1")
            self.assertEqual(res.data[0]["author"]["id"], self.student.id)
            self.assertEqual(res.data[0]["author"]["username"], self.student.username)
            self.assertEqual(res.data[0]["author"]["email"], self.student.email)
            self.assertEqual(res.data[1]["number"], 2)
            self.assertEqual(res.data[1]["url"], "https://github.com/org/repo/pull/2")

    def test_versiones_usuario_ajeno_recibe_404(self):
        versions_url = f"/api/deliverables/{self.deliverable.pk}/versions/"
        res = self.as_user(self.outsider).get(versions_url)
        self.assertEqual(res.status_code, 404)

    def test_versiones_sin_autenticar_recibe_401(self):
        versions_url = f"/api/deliverables/{self.deliverable.pk}/versions/"
        client = APIClient()
        res = client.get(versions_url)
        self.assertEqual(res.status_code, 401)

    def test_versiones_solo_lectura_metodos_no_permitidos_dan_405(self):
        versions_url = f"/api/deliverables/{self.deliverable.pk}/versions/"
        client = self.as_user(self.student)
        for method in (client.post, client.put, client.patch, client.delete):
            res = method(versions_url, {"url": "https://example.com"}, format="json")
            self.assertEqual(res.status_code, 405)
    
    def test_entrega_con_url_larga(self):
        url_larga = "https://docs.google.com/document/d/" + "a" * 500 + "/edit"
        response = self.as_user(self.student).post(
            self.submit_url, {"url": url_larga}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.deliverable.versions.get().url, url_larga)