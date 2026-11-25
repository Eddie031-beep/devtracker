from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.testing import ProjectFixtureMixin

from ..models import Issue
from ..services import assign_issue, create_issue, transition_issue


@override_settings(NOTIFICATIONS_SEND_EMAIL=False)
class IssueWebTests(ProjectFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.list_url = reverse("issues:list", args=[self.project.pk])

    def new_issue(self):
        return create_issue(
            self.project, self.member, title="Botón Guardar no responde",
            description="Al guardar el perfil no pasa nada", steps_to_reproduce="1. Perfil\n2. Guardar",
        )

    def test_pagina_con_tailwind_y_acceso_desde_el_proyecto(self):
        response = self.web(self.member).get(self.list_url)
        self.assertContains(response, "Registrar incidencia")
        self.assertContains(response, "web/tailwind.css")
        self.assertContains(self.client.get(reverse("web:project", args=[self.project.pk])), self.list_url)

    def test_registrar_desde_la_web(self):
        response = self.web(self.member).post(self.list_url, {
            "title": "La tabla se corta en móvil", "priority": "medium",
            "description": "En 390 px la tabla desborda", "steps_to_reproduce": "Abrir en un teléfono",
        })
        issue = Issue.objects.get()
        self.assertRedirects(response, reverse("issues:detail", args=[issue.pk]))
        self.assertIsNone(issue.assignee)  # el integrante no elige responsable

    def test_formulario_invalido_muestra_errores(self):
        response = self.web(self.member).post(self.list_url, {"title": "x", "priority": "medium", "description": "", "steps_to_reproduce": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "al menos 5 caracteres")
        self.assertFalse(Issue.objects.exists())

    def test_permisos_web(self):
        issue = self.new_issue()
        self.assertEqual(self.web(self.outsider).get(self.list_url).status_code, 404)
        self.assertEqual(self.client.get(reverse("issues:detail", args=[issue.pk])).status_code, 404)
        self.web(self.member2)
        self.assertEqual(self.client.get(reverse("issues:edit", args=[issue.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("issues:delete", args=[issue.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("issues:assign", args=[issue.pk]), {"assignee": self.member2.pk}).status_code, 403)

    def test_flujo_web_del_evaluador(self):
        issue = assign_issue(self.new_issue(), self.leader, self.member)
        transition_issue(issue, self.member, "start")
        transition_issue(issue, self.member, "resolve", "Faltaba el csrf_token")
        detail = reverse("issues:detail", args=[issue.pk])
        self.assertContains(self.web(self.evaluator).get(detail), "Verificar solución")
        self.assertNotContains(self.web(self.member).get(detail), "Verificar solución")
        self.web(self.evaluator).post(reverse("issues:transition", args=[issue.pk]), {"action": "reopen", "comment": "No guarda la foto"})
        issue.refresh_from_db()
        self.assertEqual(issue.status, "open")
        response = self.client.get(detail)
        self.assertContains(response, "No guarda la foto")
        self.assertContains(response, "Faltaba el csrf_token")  # el historial previo sigue visible

    def test_reabrir_sin_motivo_muestra_el_error(self):
        issue = assign_issue(self.new_issue(), self.leader, self.member)
        transition_issue(issue, self.member, "start")
        transition_issue(issue, self.member, "resolve", "ok")
        response = self.web(self.evaluator).post(
            reverse("issues:transition", args=[issue.pk]), {"action": "reopen", "comment": ""}, follow=True
        )
        self.assertContains(response, "Indica por qué se reabre")
