from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.testing import ProjectFixtureMixin

from ..models import Mitigation, Risk
from ..services import add_mitigation, create_risk


@override_settings(NOTIFICATIONS_SEND_EMAIL=False)
class RiskWebTests(ProjectFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.list_url = reverse("risks:list", args=[self.project.pk])

    def new_risk(self, probability=3, impact=3):
        return create_risk(self.project, self.member, title="Falta de tiempo", description="El semestre termina antes del cierre",
                           probability=probability, impact=impact, owner=self.member)

    def test_matriz_y_registro(self):
        self.new_risk()
        response = self.web(self.member).get(self.list_url)
        self.assertContains(response, "Matriz de riesgos abiertos")
        self.assertContains(response, "Alto: 1")
        self.assertContains(self.client.get(reverse("web:project", args=[self.project.pk])), self.list_url)
        response = self.client.post(self.list_url, {
            "title": "Conflicto de horarios", "description": "No coincidimos para reunirnos",
            "probability": 2, "impact": 1, "owner": self.member2.pk,
        })
        risk = Risk.objects.get(title="Conflicto de horarios")
        self.assertRedirects(response, reverse("risks:detail", args=[risk.pk]))
        self.assertEqual((risk.score, risk.level), (2, "low"))

    def test_filtro_por_celda_y_nivel(self):
        self.new_risk(3, 3)
        create_risk(self.project, self.member, title="Riesgo menor", description="Cambia el nombre del curso",
                    probability=1, impact=1, owner=self.member)
        response = self.web(self.member).get(self.list_url, {"p": 1, "i": 1})
        self.assertContains(response, "Riesgo menor")
        self.assertNotContains(response, "Falta de tiempo")
        response = self.client.get(self.list_url, {"level": "high"})
        self.assertContains(response, "Falta de tiempo")
        self.assertNotContains(response, "Riesgo menor")

    def test_valores_fuera_de_escala_en_el_formulario(self):
        response = self.web(self.member).post(self.list_url, {
            "title": "Algo raro", "description": "Probabilidad inventada", "probability": 7, "impact": 2, "owner": self.member.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Risk.objects.exists())
        self.assertContains(response, "Escoja una opción válida")

    def test_evaluador_consulta_pero_no_registra(self):
        self.new_risk()
        response = self.web(self.evaluator).get(self.list_url)
        self.assertNotContains(response, "Registrar riesgo")
        self.assertEqual(self.client.post(self.list_url, {}).status_code, 403)

    def test_permisos_y_404(self):
        risk = self.new_risk()
        self.assertEqual(self.web(self.outsider).get(self.list_url).status_code, 404)
        self.assertEqual(self.client.get(reverse("risks:detail", args=[risk.pk])).status_code, 404)
        self.web(self.member2)
        self.assertEqual(self.client.get(reverse("risks:edit", args=[risk.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("risks:status", args=[risk.pk]), {"status": "closed"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("risks:delete", args=[risk.pk])).status_code, 403)

    def test_mitigacion_y_estado_desde_la_web(self):
        risk = self.new_risk()
        self.web(self.member).post(reverse("risks:mitigation_add", args=[risk.pk]), {"description": "Repartir tareas por semana"})
        mitigation = Mitigation.objects.get()
        self.client.post(reverse("risks:mitigation_toggle", args=[mitigation.pk]), {"done": "1"})
        mitigation.refresh_from_db()
        self.assertTrue(mitigation.done)
        response = self.client.post(reverse("risks:status", args=[risk.pk]), {"status": "closed", "comment": ""}, follow=True)
        self.assertContains(response, "Explica qué pasó")
        self.client.post(reverse("risks:status", args=[risk.pk]), {"status": "closed", "comment": "Plan cumplido"})
        risk.refresh_from_db()
        self.assertEqual(risk.status, "closed")
        detail = self.client.get(reverse("risks:detail", args=[risk.pk]))
        self.assertContains(detail, "Plan cumplido")  # el historial lo conserva
        self.assertContains(detail, "Repartir tareas por semana")

    def test_marcar_medida_ajena_da_403(self):
        risk = self.new_risk()
        mitigation = add_mitigation(risk, self.member, description="Pedir prórroga")
        self.assertEqual(self.web(self.member2).post(reverse("risks:mitigation_toggle", args=[mitigation.pk]), {"done": "1"}).status_code, 403)
