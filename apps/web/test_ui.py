import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import Action, AuditLog
from apps.notifications.models import Notification
from apps.projects.models import Deliverable, Milestone, Project, ProjectMembership

User = get_user_model()
Role = ProjectMembership.ProjectRole


class LeaderToolsTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x", first_name="Lía")
        self.ana = User.objects.create_user("ana", "ana@x.com", "x", first_name="Ana")
        self.project = Project.objects.create(name="Demo", owner=self.leader)
        ProjectMembership.objects.create(project=self.project, user=self.leader, role=Role.LEADER)
        ProjectMembership.objects.create(project=self.project, user=self.ana, role=Role.MEMBER)
        self.milestone = Milestone.objects.create(project=self.project, title="Hito 1", due_date=timezone.now().date())

    def test_lider_crea_hito_y_entregable_asignado(self):
        self.client.force_login(self.leader)
        self.client.post(
            reverse("web:milestone_create", args=[self.project.pk]),
            {"title": "Hito 2", "description": "", "due_date": "2026-12-01"},
        )
        self.assertTrue(Milestone.objects.filter(title="Hito 2").exists())
        due = (timezone.now() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            reverse("web:deliverable_create", args=[self.project.pk]),
            {"milestone": self.milestone.pk, "title": "Informe", "description": "PDF", "due_at": due, "assignees": [self.ana.pk]},
        )
        deliverable = Deliverable.objects.get(title="Informe")
        self.assertRedirects(response, reverse("web:deliverable", args=[deliverable.pk]), fetch_redirect_response=False)
        self.assertEqual(list(deliverable.assignees.all()), [self.ana])
        self.assertTrue(Notification.objects.filter(recipient=self.ana, kind="assigned").exists())
        actions = set(AuditLog.objects.values_list("action", flat=True))
        self.assertTrue({Action.MILESTONE_CREATED, Action.DELIVERABLE_CREATED, Action.DELIVERABLE_ASSIGNEES_CHANGED} <= actions)

    def test_integrante_no_puede_crear(self):
        self.client.force_login(self.ana)
        page = self.client.get(reverse("web:project", args=[self.project.pk]))
        self.assertNotContains(page, "Nuevo entregable")
        response = self.client.post(
            reverse("web:milestone_create", args=[self.project.pk]), {"title": "X", "due_date": "2026-12-01"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Milestone.objects.filter(title="X").exists())

    def test_mis_entregables(self):
        deliverable = Deliverable.objects.create(milestone=self.milestone, title="Manual", due_at=timezone.now())
        deliverable.assignees.set([self.ana])
        self.client.force_login(self.ana)
        self.assertContains(self.client.get(reverse("web:my_deliverables")), "Manual")
        self.client.force_login(self.leader)
        self.assertNotContains(self.client.get(reverse("web:my_deliverables")), "Manual")

    def test_auditoria_web_con_filtros_y_permisos(self):
        self.client.force_login(self.leader)
        self.client.post(
            reverse("web:milestone_create", args=[self.project.pk]), {"title": "Hito 2", "due_date": "2026-12-01"}
        )
        url = reverse("web:project_audit", args=[self.project.pk])
        page = self.client.get(url, {"action": Action.MILESTONE_CREATED})
        self.assertContains(page, "Hito creado")
        self.assertContains(page, "Registro inmutable")
        self.assertContains(page, "Mostrando 1 de 1 registros")
        self.assertContains(self.client.get(url, {"action": Action.DELIVERABLE_SUBMITTED}), "Mostrando 0 de 0 registros")
        self.client.force_login(self.ana)
        self.assertEqual(self.client.get(url).status_code, 403)


class TeamCommandTests(TestCase):
    def test_crea_el_equipo_y_se_puede_repetir(self):
        leader = User.objects.create_user("EddieAdmin", "eddie@x.com", "x")
        project = Project.objects.create(name="DevTracker", owner=leader)
        ProjectMembership.objects.create(project=project, user=leader, role=Role.LEADER)
        for _ in range(2):
            call_command("crear_equipo", "--password", "Clave-2026", "--proyecto", str(project.pk), stdout=io.StringIO())
        self.assertEqual(project.memberships.count(), 6)
        brayan = User.objects.get(username="brayan")
        self.assertTrue(brayan.check_password("Clave-2026"))
        self.assertEqual(brayan.github_username, "Brashan09")
        self.assertEqual(project.memberships.get(user=brayan).responsibilities, "CRUD, historial de versiones")
        self.assertEqual(project.memberships.get(user__username="profesor").role, Role.EVALUATOR)
        self.assertTrue(self.client.login(username="carlos", password="Clave-2026"))
