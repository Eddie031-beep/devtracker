from django.test import TestCase, override_settings

from apps.core.testing import ProjectFixtureMixin

from ..models import Issue


@override_settings(NOTIFICATIONS_SEND_EMAIL=False)
class IssueApiTests(ProjectFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = f"/api/projects/{self.project.pk}/issues/"
        self.payload = {
            "title": "Error al exportar CSV", "description": "El archivo sale vacío siempre",
            "steps_to_reproduce": "1. Abrir reporte\n2. Descargar CSV", "priority": "high",
        }

    def create(self, user=None, **extra):
        return self.api(user or self.member).post(self.url, {**self.payload, **extra}, format="json")

    def test_crear_y_listar(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "open")
        self.assertEqual(response.data["reported_by"]["username"], "ana")
        listed = self.api(self.evaluator).get(self.url, {"priority": "high"})
        self.assertEqual([i["id"] for i in listed.data], [response.data["id"]])
        self.assertEqual(self.api(self.evaluator).get(self.url, {"priority": "low"}).data, [])

    def test_validacion_en_el_backend(self):
        response = self.create(title="abc", description="corto", priority="urgente")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.data), {"title", "description", "priority"})

    def test_ajeno_recibe_404(self):
        self.assertEqual(self.create(user=self.outsider).status_code, 404)
        issue_id = self.create().data["id"]
        self.assertEqual(self.api(self.outsider).get(f"/api/issues/{issue_id}/").status_code, 404)

    def test_integrante_no_asigna_al_crear(self):
        self.assertEqual(self.create(assignee_id=self.member2.pk).status_code, 403)
        self.assertEqual(self.create(user=self.leader, assignee_id=self.member2.pk).status_code, 201)

    def test_flujo_por_la_api(self):
        issue_id = self.create().data["id"]
        base = f"/api/issues/{issue_id}/"
        self.assertEqual(self.api(self.member).post(base + "assign/", {"assignee_id": self.member.pk}, format="json").status_code, 403)
        self.assertEqual(self.api(self.leader).post(base + "assign/", {"assignee_id": self.member.pk}, format="json").status_code, 200)
        self.assertEqual(self.api(self.member).post(base + "transition/", {"action": "start"}, format="json").status_code, 200)
        r = self.api(self.member).post(base + "transition/", {"action": "resolve"}, format="json")
        self.assertEqual(r.status_code, 400)  # falta el comentario
        self.api(self.member).post(base + "transition/", {"action": "resolve", "comment": "Corregido"}, format="json")
        self.assertEqual(self.api(self.leader).post(base + "transition/", {"action": "verify"}, format="json").status_code, 403)
        r = self.api(self.evaluator).post(base + "transition/", {"action": "reopen", "comment": "Sigue vacío"}, format="json")
        self.assertEqual(r.data["status"], "open")
        self.api(self.evaluator).post(base + "history/", {"comment": "Prueben con datos reales"}, format="json")
        history = self.api(self.member).get(base + "history/").data
        self.assertEqual(
            [e["kind"] for e in history], ["created", "assigned", "started", "resolved", "reopened", "commented"]
        )

    def test_editar_y_borrar(self):
        issue_id = self.create().data["id"]
        base = f"/api/issues/{issue_id}/"
        self.assertEqual(self.api(self.member2).patch(base, {"title": "Otro título"}, format="json").status_code, 403)
        r = self.api(self.member).patch(base, {"title": "CSV vacío al exportar", "status": "verified"}, format="json")
        self.assertEqual((r.status_code, r.data["title"], r.data["status"]), (200, "CSV vacío al exportar", "open"))
        # Cambiar el responsable por aquí no se acepta (ni se ignora en silencio): tiene su endpoint
        r = self.api(self.leader).patch(base, {"assignee_id": self.member2.pk}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("assign", str(r.data["assignee_id"]))
        self.assertEqual(self.api(self.member).delete(base).status_code, 403)
        self.assertEqual(self.api(self.leader).delete(base).status_code, 204)
        self.assertTrue(Issue.all_objects.get(pk=issue_id).deleted_at)
