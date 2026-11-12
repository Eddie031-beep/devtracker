from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import Action, AuditLog
from apps.projects.models import Deliverable, Milestone, Project, ProjectMembership
from apps.projects.services import submit_deliverable

from .models import Evaluation, ImmutableEvaluationError

User = get_user_model()
Status = Deliverable.Status
Role = ProjectMembership.ProjectRole


class EvaluationApiTests(TestCase):
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
            milestone=milestone, title="Informe", due_at=timezone.now() + timedelta(days=3)
        )
        self.deliverable.assignees.set([self.student])
        submit_deliverable(self.deliverable, self.student, url="https://example.com/informe")
        self.url = f"/api/deliverables/{self.deliverable.pk}/evaluate/"

    def as_user(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_evaluador_aprueba_con_nota_y_queda_auditado(self):
        response = self.as_user(self.evaluator).post(
            self.url, {"decision": "approved", "score": 95, "feedback": "Muy bien"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["score"], 95)
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.status, Status.APPROVED)
        actions = list(AuditLog.objects.values_list("action", flat=True))
        self.assertIn(Action.DELIVERABLE_EVALUATED, actions)
        # Pasa por «En revisión» antes de la decisión: el flujo de estados (#5) se respeta
        self.assertEqual(actions.count(Action.DELIVERABLE_STATUS_CHANGED), 2)

    def test_rechazo_permite_reentregar_y_reevaluar(self):
        self.as_user(self.leader).post(self.url, {"decision": "rejected", "score": 40}, format="json")
        submit_deliverable(self.deliverable, self.student, url="https://example.com/informe-v2")
        response = self.as_user(self.leader).post(self.url, {"decision": "approved", "score": 85}, format="json")
        self.assertEqual(response.status_code, 201)
        listing = self.as_user(self.student).get(f"/api/deliverables/{self.deliverable.pk}/evaluations/")
        self.assertEqual([e["score"] for e in listing.data], [85, 40])

    def test_integrante_403_y_ajeno_404(self):
        body = {"decision": "approved", "score": 100}
        self.assertEqual(self.as_user(self.student).post(self.url, body, format="json").status_code, 403)
        self.assertEqual(self.as_user(self.outsider).post(self.url, body, format="json").status_code, 404)
        self.assertFalse(Evaluation.objects.exists())

    def test_nota_fuera_de_rango_y_estado_invalido_400(self):
        client = self.as_user(self.evaluator)
        self.assertEqual(client.post(self.url, {"decision": "approved", "score": 101}, format="json").status_code, 400)
        client.post(self.url, {"decision": "approved", "score": 90}, format="json")
        # Ya está aprobado: no se puede volver a evaluar
        self.assertEqual(client.post(self.url, {"decision": "rejected", "score": 10}, format="json").status_code, 400)

    def test_evaluacion_inmutable(self):
        self.as_user(self.evaluator).post(self.url, {"decision": "approved", "score": 90}, format="json")
        evaluation = Evaluation.objects.get()
        evaluation.score = 100
        with self.assertRaises(ImmutableEvaluationError):
            evaluation.save()
        with self.assertRaises(ImmutableEvaluationError):
            evaluation.delete()
        with self.assertRaises(ImmutableEvaluationError):
            Evaluation.objects.update(score=0)
