from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.testing import ProjectFixtureMixin
from apps.projects.models import Deliverable, Milestone


@override_settings(NOTIFICATIONS_SEND_EMAIL=False)
class ChangeRequestApiTests(ProjectFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = f"/api/projects/{self.project.pk}/change-requests/"
        milestone = Milestone.objects.create(project=self.project, title="H1", due_date=timezone.localdate())
        self.deliverable = Deliverable.objects.create(milestone=milestone, title="Reporte", due_at=timezone.now() + timedelta(days=3))

    def create(self, user=None, **extra):
        payload = {
            "title": "Cambiar el reporte a PDF", "description": "Generar PDF en vez de la vista imprimible",
            "justification": "La vista imprimible se ve mal en Safari", "expected_impact": "Tres días de trabajo",
            "impact_level": "low", "affected_deliverables": [self.deliverable.pk],
        }
        return self.api(user or self.member).post(self.url, {**payload, **extra}, format="json")

    def test_flujo_por_la_api(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["affected_deliverable_ids"], [self.deliverable.pk])
        base = f"/api/change-requests/{response.data['id']}/"
        self.assertEqual(self.api(self.leader).post(base + "decide/", {"decision": "approved", "comment": "Me parece bien"}, format="json").status_code, 403)
        self.assertEqual(self.api(self.evaluator).post(base + "decide/", {"decision": "approved", "comment": ""}, format="json").status_code, 400)
        r = self.api(self.evaluator).post(base + "decide/", {"decision": "approved", "comment": "Aprobado, sin mover fechas"}, format="json")
        self.assertEqual((r.data["status"], r.data["decided_by"]["username"]), ("approved", "prof"))
        self.assertEqual(self.api(self.member).patch(base, {"title": "Otro título"}, format="json").status_code, 403)
        self.assertEqual(self.api(self.member).delete(base).status_code, 405)  # no se borran
        self.assertEqual([c["status"] for c in self.api(self.evaluator).get(self.url, {"status": "approved"}).data], ["approved"])

    def test_validaciones_y_acceso(self):
        self.assertEqual(self.create(justification="no").status_code, 400)
        self.assertEqual(self.create(affected_deliverables=[999]).status_code, 400)
        self.assertEqual(self.create(user=self.evaluator).status_code, 403)
        self.assertEqual(self.create(user=self.outsider).status_code, 404)

    def test_retirar(self):
        change_id = self.create().data["id"]
        self.assertEqual(self.api(self.member2).post(f"/api/change-requests/{change_id}/withdraw/").status_code, 403)
        self.assertEqual(self.api(self.member).post(f"/api/change-requests/{change_id}/withdraw/").data["status"], "withdrawn")
