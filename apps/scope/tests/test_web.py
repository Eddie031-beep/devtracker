from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.testing import ProjectFixtureMixin

from ..models import ChangeRequest
from ..services import propose_change


@override_settings(NOTIFICATIONS_SEND_EMAIL=False)
class ChangeRequestWebTests(ProjectFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.list_url = reverse("scope:list", args=[self.project.pk])
        self.data = {
            "title": "Agregar exportar a PDF", "description": "Un botón para bajar el reporte en PDF",
            "justification": "El profesor pidió el reporte impreso", "expected_impact": "Dos días de trabajo de un integrante",
            "impact_level": "medium",
        }

    def propose(self):
        return propose_change(self.project, self.member, **self.data)

    def test_estudiante_propone_desde_la_web(self):
        response = self.web(self.member).post(self.list_url, self.data)
        change = ChangeRequest.objects.get()
        self.assertRedirects(response, reverse("scope:detail", args=[change.pk]))
        self.assertContains(self.client.get(reverse("web:project", args=[self.project.pk])), self.list_url)

    def test_validacion_del_formulario(self):
        response = self.web(self.member).post(self.list_url, {**self.data, "justification": "corta"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "al menos 10 caracteres")
        self.assertFalse(ChangeRequest.objects.exists())

    def test_evaluador_no_propone_pero_decide(self):
        change = self.propose()
        response = self.web(self.evaluator).get(self.list_url)
        self.assertNotContains(response, "Proponer un cambio")
        self.assertContains(response, "por decidir")
        self.assertEqual(self.client.post(self.list_url, self.data).status_code, 403)
        detail = reverse("scope:detail", args=[change.pk])
        self.assertContains(self.client.get(detail), "Aprobar")
        self.client.post(reverse("scope:decide", args=[change.pk]), {"decision": "rejected", "comment": "No entra en el plazo"})
        change.refresh_from_db()
        self.assertEqual(change.status, "rejected")
        self.assertContains(self.client.get(detail), "No entra en el plazo")

    def test_integrante_no_decide(self):
        change = self.propose()
        self.web(self.leader)
        self.assertNotContains(self.client.get(reverse("scope:detail", args=[change.pk])), "Rechazar")
        response = self.client.post(reverse("scope:decide", args=[change.pk]), {"decision": "approved", "comment": "Yo apruebo"})
        self.assertEqual(response.status_code, 403)

    def test_retirar_y_permisos(self):
        change = self.propose()
        self.assertEqual(self.web(self.outsider).get(reverse("scope:detail", args=[change.pk])).status_code, 404)
        self.assertEqual(self.web(self.member2).get(reverse("scope:edit", args=[change.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("scope:withdraw", args=[change.pk])).status_code, 403)
        self.web(self.member).post(reverse("scope:withdraw", args=[change.pk]))
        change.refresh_from_db()
        self.assertEqual(change.status, "withdrawn")
        self.assertContains(self.client.get(self.list_url), "Retirada")  # se conserva
