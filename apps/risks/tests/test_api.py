from django.test import TestCase, override_settings

from apps.core.testing import ProjectFixtureMixin


@override_settings(NOTIFICATIONS_SEND_EMAIL=False)
class RiskApiTests(ProjectFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = f"/api/projects/{self.project.pk}/risks/"

    def create(self, user=None, **extra):
        payload = {"title": "Pérdida del servidor", "description": "Railway suspende el plan gratuito",
                   "probability": 2, "impact": 3, "owner_id": self.member.pk}
        return self.api(user or self.member).post(self.url, {**payload, **extra}, format="json")

    def test_crear_calcula_nivel_y_valida_la_escala(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data["score"], response.data["level"], response.data["level_display"]), (6, "high", "Alto"))
        bad = self.create(probability=0, impact=4)
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(set(bad.data), {"probability", "impact"})
        self.assertEqual(self.create(owner_id=self.evaluator.pk).status_code, 400)
        self.assertEqual(self.create(user=self.evaluator).status_code, 403)
        self.assertEqual(self.create(user=self.outsider).status_code, 404)

    def test_filtros_y_matriz(self):
        high = self.create().data["id"]
        self.create(title="Riesgo pequeño", probability=1, impact=1)
        self.assertEqual([r["id"] for r in self.api(self.evaluator).get(self.url, {"level": "high"}).data], [high])
        grid = self.api(self.evaluator).get(self.url + "matrix/").data
        top_row = grid["rows"][1]  # probabilidad 2
        self.assertEqual(top_row["probability"], 2)
        self.assertEqual(top_row["cells"][2]["risks"], [high])

    def test_estado_mitigacion_y_edicion(self):
        risk_id = self.create().data["id"]
        base = f"/api/risks/{risk_id}/"
        r = self.api(self.member).post(base + "mitigations/", {"description": "Respaldar la base cada día", "responsible_id": self.member2.pk}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.api(self.member).get(base).data["status"], "mitigating")
        self.assertEqual(self.api(self.member).post(f"/api/mitigations/{r.data['id']}/done/", {"done": True}, format="json").data["done"], True)
        self.assertEqual(self.api(self.member).post(base + "status/", {"status": "closed"}, format="json").status_code, 400)
        r = self.api(self.member).post(base + "status/", {"status": "closed", "comment": "Se compró un plan"}, format="json")
        self.assertEqual(r.data["status"], "closed")
        self.assertEqual(self.api(self.member2).patch(base, {"impact": 1}, format="json").status_code, 403)
        r = self.api(self.leader).patch(base, {"impact": 1, "score": 9}, format="json")
        self.assertEqual((r.data["score"], r.data["level"]), (2, "low"))  # el puntaje no se manda: se calcula
        self.assertEqual(self.api(self.member).delete(base).status_code, 403)
        self.assertEqual(self.api(self.leader).delete(base).status_code, 204)
