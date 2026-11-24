from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.audit.models import Action, AuditLog
from apps.core.testing import ProjectFixtureMixin
from apps.notifications.models import Notification

from ..models import Agreement, Meeting
from ..services import add_agreement, create_meeting, delete_meeting, update_agreement, update_meeting

Status = Agreement.Status


@override_settings(NOTIFICATIONS_SEND_EMAIL=False)
class MeetingServiceTests(ProjectFixtureMixin, TestCase):
    def new_meeting(self, actor=None, **extra):
        data = {
            "title": "Revisión de la etapa 5", "held_at": timezone.now() - timedelta(hours=2),
            "summary": "Se revisó el avance de los cuatro módulos y la integración con Tailwind.",
            "participants": [self.leader, self.member, self.member2], "location": "Aula 3-205",
        }
        return create_meeting(self.project, actor or self.leader, **{**data, **extra})

    def test_registrar_acta_con_participantes(self):
        meeting = self.new_meeting()
        self.assertEqual(meeting.participants.count(), 3)
        self.assertTrue(AuditLog.objects.filter(action=Action.MEETING_CREATED, target_id=meeting.pk).exists())
        # Les avisa a los participantes, no a quien la registró
        self.assertEqual(set(Notification.objects.values_list("recipient__username", flat=True)), {"ana", "beto"})

    def test_validaciones_del_acta(self):
        with self.assertRaises(ValidationError):
            self.new_meeting(participants=[])
        with self.assertRaises(ValidationError):
            self.new_meeting(participants=[self.outsider])
        with self.assertRaises(ValidationError):
            self.new_meeting(held_at=timezone.now() + timedelta(days=2))  # el acta es de algo que ya pasó
        with self.assertRaises(ValidationError):
            self.new_meeting(summary="corto")
        with self.assertRaises(PermissionDenied):
            self.new_meeting(actor=self.evaluator)

    def test_editar_y_borrar_acta(self):
        meeting = self.new_meeting(actor=self.member)
        with self.assertRaises(PermissionDenied):
            update_meeting(meeting, self.member2, title="Otra")
        meeting = update_meeting(meeting, self.member, title="Revisión semanal", participants=[self.member])
        self.assertEqual(list(meeting.participants.all()), [self.member])
        update_meeting(meeting, self.leader, summary="El líder completó el resumen de la reunión.")
        with self.assertRaises(PermissionDenied):
            delete_meeting(meeting, self.member2)
        delete_meeting(meeting, self.leader)
        self.assertTrue(Meeting.all_objects.filter(pk=meeting.pk, deleted_at__isnull=False).exists())

    def test_acuerdos_con_responsable_fecha_y_estado(self):
        meeting = self.new_meeting()
        due = timezone.localdate() + timedelta(days=3)
        with self.assertRaises(PermissionDenied):
            add_agreement(meeting, self.member, description="Subir el PR", responsible=self.member, due_date=due)
        with self.assertRaises(ValidationError):
            add_agreement(meeting, self.leader, description="Subir el PR", responsible=self.evaluator, due_date=due)
        with self.assertRaises(ValidationError):
            add_agreement(meeting, self.leader, description="Subir el PR", responsible=self.member,
                          due_date=timezone.localdate() - timedelta(days=5))  # antes de la reunión
        agreement = add_agreement(meeting, self.leader, description="Subir el PR de riesgos", responsible=self.member, due_date=due)
        self.assertEqual(agreement.status, Status.PENDING)
        self.assertTrue(Notification.objects.filter(recipient=self.member, title__contains="acuerdo").exists())

    def test_solo_autorizados_actualizan_acuerdos(self):
        meeting = self.new_meeting()
        agreement = add_agreement(meeting, self.leader, description="Preparar la demo", responsible=self.member,
                                  due_date=timezone.localdate() + timedelta(days=1))
        for intruder in (self.member2, self.evaluator):
            with self.assertRaises(PermissionDenied):
                update_agreement(agreement, intruder, status=Status.DONE)
        agreement = update_agreement(agreement, self.member, status=Status.DONE)
        self.assertEqual((agreement.status, agreement.completed_by), (Status.DONE, self.member))
        self.assertIsNotNone(agreement.completed_at)
        log = AuditLog.objects.filter(action=Action.AGREEMENT_STATUS_CHANGED).last()
        self.assertEqual(log.changes["status"], {"before": "pending", "after": "done"})
        agreement = update_agreement(agreement, self.leader, status=Status.PENDING)
        self.assertIsNone(agreement.completed_at)
        with self.assertRaises(PermissionDenied):
            update_agreement(agreement, self.member, responsible=self.member2)  # solo el líder reasigna
        agreement = update_agreement(agreement, self.leader, responsible=self.member2)
        self.assertEqual(agreement.responsible, self.member2)

    def test_acuerdo_vencido(self):
        meeting = self.new_meeting(held_at=timezone.now() - timedelta(days=10))
        agreement = add_agreement(meeting, self.leader, description="Entregar informe", responsible=self.member,
                                  due_date=timezone.localdate() - timedelta(days=2))
        self.assertTrue(agreement.is_overdue)
        self.assertEqual(agreement.status_label, "Vencido")
        agreement = update_agreement(agreement, self.member, status=Status.DONE)
        self.assertFalse(agreement.is_overdue)
