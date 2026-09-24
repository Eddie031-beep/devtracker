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

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def test_estudiante_asignado_entrega(self):
        response = self.as_user(self.student).post(self.submit_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Status.SUBMITTED)

    def test_entrega_tardia_queda_marcada(self):
        self.deliverable.due_at = timezone.now() - timedelta(hours=1)
        self.deliverable.save()
        response = self.as_user(self.student).post(self.submit_url)
        self.assertEqual(response.data["status"], Status.LATE)
        self.assertTrue(response.data["is_late"])

    def test_no_asignado_recibe_403(self):
        response = self.as_user(self.leader).post(self.submit_url)
        self.assertEqual(response.status_code, 403)

    def test_ajeno_recibe_404(self):
        response = self.as_user(self.outsider).post(self.submit_url)
        self.assertEqual(response.status_code, 404)

    def test_entregar_dos_veces_da_400(self):
        self.as_user(self.student).post(self.submit_url)
        response = self.client.post(self.submit_url)
        self.assertEqual(response.status_code, 400)

    def test_flujo_completo_por_api(self):
        self.as_user(self.student).post(self.submit_url)
        client = self.as_user(self.evaluator)
        client.post(self.status_url, {"status": "in_review"}, format="json")
        response = client.post(self.status_url, {"status": "approved"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Status.APPROVED)

    def test_estudiante_no_puede_revisar(self):
        self.as_user(self.student).post(self.submit_url)
        response = self.client.post(self.status_url, {"status": "in_review"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_transicion_invalida_da_400(self):
        self.as_user(self.student).post(self.submit_url)
        response = self.as_user(self.evaluator).post(self.status_url, {"status": "approved"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_sin_status_da_400(self):
        response = self.as_user(self.evaluator).post(self.status_url, {}, format="json")
        self.assertEqual(response.status_code, 400)
