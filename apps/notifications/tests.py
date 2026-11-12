import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.evaluations.services import evaluate_deliverable
from apps.projects.models import Deliverable, Milestone, Project, ProjectMembership
from apps.projects.services import submit_deliverable
from apps.projects.services_members import set_deliverable_assignees

from .models import Notification
from .services import send_due_reminders

User = get_user_model()
Role = ProjectMembership.ProjectRole
Kind = Notification.Kind


class NotificationTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x")
        self.ana = User.objects.create_user("ana", "ana@x.com", "x")
        self.leo = User.objects.create_user("leo", "leo@x.com", "x")
        self.prof = User.objects.create_user("prof", "prof@x.com", "x")
        self.project = Project.objects.create(name="Demo", owner=self.leader)
        ProjectMembership.objects.create(project=self.project, user=self.leader, role=Role.LEADER)
        ProjectMembership.objects.create(project=self.project, user=self.ana, role=Role.MEMBER)
        ProjectMembership.objects.create(project=self.project, user=self.leo, role=Role.MEMBER)
        ProjectMembership.objects.create(project=self.project, user=self.prof, role=Role.EVALUATOR)
        milestone = Milestone.objects.create(project=self.project, title="H1", due_date=timezone.now().date())
        self.deliverable = Deliverable.objects.create(
            milestone=milestone, title="Informe", due_at=timezone.now() + timedelta(hours=20)
        )

    def kinds(self, user):
        return list(Notification.objects.filter(recipient=user).values_list("kind", flat=True))

    def test_asignar_avisa_solo_a_los_nuevos(self):
        set_deliverable_assignees(self.deliverable, self.leader, [self.ana])
        set_deliverable_assignees(self.deliverable, self.leader, [self.ana, self.leo])
        self.assertEqual(self.kinds(self.ana), [Kind.ASSIGNED])
        self.assertEqual(self.kinds(self.leo), [Kind.ASSIGNED])
        self.assertEqual(self.kinds(self.leader), [])  # quien asigna no se avisa a sí mismo

    def test_entrega_avisa_a_lider_y_evaluador_y_manda_correo(self):
        self.deliverable.assignees.set([self.ana])
        with self.captureOnCommitCallbacks(execute=True):
            submit_deliverable(self.deliverable, self.ana, url="https://example.com/informe")
        self.assertEqual(self.kinds(self.leader), [Kind.SUBMITTED])
        self.assertEqual(self.kinds(self.prof), [Kind.SUBMITTED])
        self.assertEqual(self.kinds(self.ana), [])
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["lider@x.com", "prof@x.com"])
        self.assertIn(f"/entregables/{self.deliverable.pk}/", mail.outbox[0].body)

    def test_evaluacion_avisa_a_los_asignados(self):
        self.deliverable.assignees.set([self.ana])
        submit_deliverable(self.deliverable, self.ana, url="https://example.com/informe")
        evaluate_deliverable(self.deliverable, self.prof, "approved", 95, "Excelente")
        notification = Notification.objects.get(recipient=self.ana)
        self.assertEqual(notification.kind, Kind.EVALUATED)
        self.assertIn("95/100", notification.title)
        self.assertEqual(notification.message, "Excelente")

    def test_recordatorios_sin_repetir(self):
        self.deliverable.assignees.set([self.ana])
        self.assertEqual(send_due_reminders(hours=48), 1)
        self.assertEqual(send_due_reminders(hours=48), 0)  # mismo día: no se repite
        self.assertEqual(send_due_reminders(hours=10), 0)  # fuera de la ventana
        call_command("enviar_recordatorios", stdout=io.StringIO())
        self.assertEqual(self.kinds(self.ana), [Kind.DUE_SOON])

    def test_api_solo_los_propios_y_marcar_leidos(self):
        set_deliverable_assignees(self.deliverable, self.leader, [self.ana, self.leo])
        client = APIClient()
        client.force_authenticate(self.ana)
        listing = client.get("/api/notifications/?unread=1")
        self.assertEqual(len(listing.data), 1)
        own = listing.data[0]["id"]
        other = Notification.objects.get(recipient=self.leo).pk
        self.assertEqual(client.post(f"/api/notifications/{other}/read/").status_code, 404)
        self.assertIsNotNone(client.post(f"/api/notifications/{own}/read/").data["read_at"])
        self.assertEqual(client.get("/api/notifications/?unread=1").data, [])
        client.force_authenticate(self.leo)
        self.assertEqual(client.post("/api/notifications/read-all/").data, {"marked": 1})

    def test_web_campana_y_abrir_aviso(self):
        set_deliverable_assignees(self.deliverable, self.leader, [self.ana])
        self.client.force_login(self.ana)
        self.assertContains(self.client.get("/"), 'class="badge count">1<')
        notification = Notification.objects.get(recipient=self.ana)
        response = self.client.get(reverse("web:notification_open", args=[notification.pk]))
        self.assertRedirects(response, f"/entregables/{self.deliverable.pk}/", fetch_redirect_response=False)
        self.assertNotContains(self.client.get("/"), 'class="badge count"')
        self.client.force_login(self.leo)
        self.assertEqual(self.client.get(reverse("web:notification_open", args=[notification.pk])).status_code, 404)
