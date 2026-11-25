from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.testing import ProjectFixtureMixin


@override_settings(NOTIFICATIONS_SEND_EMAIL=False)
class MeetingApiTests(ProjectFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = f"/api/projects/{self.project.pk}/meetings/"

    def create(self, user=None, **extra):
        payload = {
            "title": "Cierre de sprint", "held_at": (timezone.now() - timedelta(hours=1)).isoformat(),
            "summary": "Se cerró el sprint y se revisaron los riesgos.", "participant_ids": [self.leader.pk, self.member.pk],
        }
        return self.api(user or self.leader).post(self.url, {**payload, **extra}, format="json")

    def test_actas_y_acuerdos(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual([p["username"] for p in response.data["participants"]], ["lider", "ana"])
        base = f"/api/meetings/{response.data['id']}/"
        due = (timezone.localdate() + timedelta(days=2)).isoformat()
        r = self.api(self.leader).post(base + "agreements/", {"description": "Revisar la API", "responsible_id": self.member.pk, "due_date": due}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        agreement_url = f"/api/agreements/{r.data['id']}/"
        # Todos los integrantes consultan; solo los autorizados actualizan
        self.assertEqual(len(self.api(self.evaluator).get(base).data["agreements"]), 1)
        self.assertEqual(self.api(self.member2).patch(agreement_url, {"status": "done"}, format="json").status_code, 403)
        r = self.api(self.member).patch(agreement_url, {"status": "done"}, format="json")
        self.assertEqual((r.data["status"], r.data["completed_by"]["username"]), ("done", "ana"))
        self.assertEqual(self.api(self.member).patch(agreement_url, {"responsible_id": self.member2.pk}, format="json").status_code, 403)
        listed = self.api(self.evaluator).get(f"/api/projects/{self.project.pk}/agreements/", {"status": "done"}).data
        self.assertEqual([a["id"] for a in listed], [r.data["id"]])

    def test_validaciones_y_acceso(self):
        self.assertEqual(self.create(participant_ids=[]).status_code, 400)
        self.assertEqual(self.create(participant_ids=[self.outsider.pk]).status_code, 400)
        self.assertEqual(self.create(held_at=(timezone.now() + timedelta(days=1)).isoformat()).status_code, 400)
        self.assertEqual(self.create(user=self.evaluator).status_code, 403)
        self.assertEqual(self.create(user=self.outsider).status_code, 404)
        meeting_id = self.create().data["id"]
        self.assertEqual(self.api(self.outsider).get(f"/api/meetings/{meeting_id}/").status_code, 404)
        self.assertEqual(self.api(self.member).delete(f"/api/meetings/{meeting_id}/").status_code, 403)
        self.assertEqual(self.api(self.leader).delete(f"/api/meetings/{meeting_id}/").status_code, 204)
