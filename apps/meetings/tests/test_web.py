from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import ProjectFixtureMixin

from ..models import Agreement, Meeting
from ..services import add_agreement, create_meeting


@override_settings(NOTIFICATIONS_SEND_EMAIL=False)
class MeetingWebTests(ProjectFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.list_url = reverse("meetings:list", args=[self.project.pk])
        self.meeting = create_meeting(
            self.project, self.leader, title="Planificación", held_at=timezone.now() - timedelta(days=1),
            summary="Se repartieron los módulos del semestral.", participants=[self.leader, self.member],
        )
        self.agreement = add_agreement(self.meeting, self.leader, description="Terminar incidencias",
                                       responsible=self.member, due_date=timezone.localdate() + timedelta(days=2))

    def test_registrar_acta_desde_la_web(self):
        held = (timezone.localtime() - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
        response = self.web(self.member).post(self.list_url, {
            "title": "Daily del lunes", "held_at": held, "location": "Meet",
            "participants": [self.member.pk, self.member2.pk], "summary": "Cada quien contó su avance.",
        })
        meeting = Meeting.objects.get(title="Daily del lunes")
        self.assertRedirects(response, reverse("meetings:detail", args=[meeting.pk]))
        self.assertContains(self.client.get(reverse("web:project", args=[self.project.pk])), self.list_url)

    def test_fecha_futura_rechazada_en_el_servidor(self):
        held = (timezone.localtime() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
        response = self.web(self.member).post(self.list_url, {
            "title": "Del futuro", "held_at": held, "participants": [self.member.pk], "summary": "No debería guardarse.",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no puede ser futura")

    def test_todos_los_integrantes_consultan_el_acta(self):
        detail = reverse("meetings:detail", args=[self.meeting.pk])
        for user in (self.member2, self.evaluator):
            response = self.web(user).get(detail)
            self.assertContains(response, "Se repartieron los módulos")
            self.assertNotContains(response, "Marcar cumplido")  # no es su acuerdo
        self.assertEqual(self.web(self.outsider).get(detail).status_code, 404)
        self.assertEqual(self.client.get(self.list_url).status_code, 404)

    def test_solo_autorizados_actualizan_el_acuerdo(self):
        url = reverse("meetings:agreement_status", args=[self.agreement.pk])
        self.assertEqual(self.web(self.member2).post(url, {"status": "done"}).status_code, 403)
        self.assertEqual(self.web(self.evaluator).post(url, {"status": "done"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("meetings:agreement_edit", args=[self.agreement.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("meetings:agreement_add", args=[self.meeting.pk]), {}).status_code, 403)
        self.web(self.member).post(url, {"status": "done", "next": self.list_url})
        self.agreement.refresh_from_db()
        self.assertEqual(self.agreement.status, Agreement.Status.DONE)

    def test_no_redirige_fuera_del_sitio(self):
        url = reverse("meetings:agreement_status", args=[self.agreement.pk])
        response = self.web(self.member).post(url, {"status": "done", "next": "//evil.example.com/"})
        self.assertRedirects(response, reverse("meetings:detail", args=[self.meeting.pk]))

    def test_filtros_de_acuerdos(self):
        add_agreement(self.meeting, self.leader, description="Acuerdo viejo sin cumplir", responsible=self.member2,
                      due_date=timezone.localdate() - timedelta(days=1))
        response = self.web(self.member).get(self.list_url, {"status": "overdue"})
        self.assertContains(response, "Acuerdo viejo sin cumplir")
        self.assertNotContains(response, "Terminar incidencias")
        response = self.client.get(self.list_url, {"mios": "1"})
        self.assertContains(response, "Terminar incidencias")
        self.assertNotContains(response, "Acuerdo viejo sin cumplir")
