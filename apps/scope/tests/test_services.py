from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.audit.models import Action, AuditLog
from apps.core.testing import ProjectFixtureMixin
from apps.notifications.models import Notification
from apps.projects.models import Deliverable, Milestone, Project

from ..models import ChangeRequest, ImmutableChangeRequestError
from ..services import decide_change, propose_change, update_change, withdraw_change

Status = ChangeRequest.Status


@override_settings(NOTIFICATIONS_SEND_EMAIL=False)
class ChangeRequestServiceTests(ProjectFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        milestone = Milestone.objects.create(project=self.project, title="H1", due_date=timezone.localdate())
        self.deliverable = Deliverable.objects.create(
            milestone=milestone, title="Login con Google", description="OAuth2", due_at=timezone.now() + timedelta(days=5)
        )
        self.deliverable.assignees.set([self.member])

    def propose(self, actor=None, **extra):
        data = {
            "title": "Quitar el login con Google", "description": "No implementar el login con Google",
            "justification": "La API de Google pide verificar la app y no da tiempo",
            "expected_impact": "Se libera una semana para pruebas", "impact_level": "high",
            "affected_deliverables": [self.deliverable],
        }
        return propose_change(self.project, actor or self.member, **{**data, **extra})

    def snapshot_deliverable(self):
        d = Deliverable.objects.get(pk=self.deliverable.pk)
        return (d.title, d.description, d.due_at, d.status, d.deleted_at, list(d.assignees.values_list("pk", flat=True)))

    def test_estudiante_propone_con_justificacion_e_impacto(self):
        change = self.propose()
        self.assertEqual(change.status, Status.PENDING)
        self.assertEqual(list(change.affected_deliverables.all()), [self.deliverable])
        self.assertTrue(AuditLog.objects.filter(action=Action.CHANGE_REQUESTED, target_id=change.pk).exists())
        # Le avisa al evaluador (y al líder)
        self.assertEqual(set(Notification.objects.values_list("recipient__username", flat=True)), {"prof", "lider"})

    def test_quien_propone_y_validaciones(self):
        with self.assertRaises(PermissionDenied):
            self.propose(actor=self.evaluator)
        with self.assertRaises(PermissionDenied):
            self.propose(actor=self.outsider)
        with self.assertRaises(ValidationError):
            self.propose(justification="corta")
        other = Project.objects.create(name="Otro", owner=self.leader)
        foreign = Deliverable.objects.create(
            milestone=Milestone.objects.create(project=other, title="X", due_date=timezone.localdate()),
            title="Ajeno", due_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            self.propose(affected_deliverables=[foreign])

    def test_evaluador_aprueba_sin_tocar_los_entregables(self):
        change = self.propose()
        before = self.snapshot_deliverable()
        with self.assertRaises(PermissionDenied):
            decide_change(change, self.leader, "approved", "Me parece bien")  # el líder es estudiante
        with self.assertRaises(ValidationError):
            decide_change(change, self.evaluator, "approved", "")  # la decisión se explica
        change = decide_change(change, self.evaluator, "approved", "De acuerdo, prioricen las pruebas")
        self.assertEqual((change.status, change.decided_by), (Status.APPROVED, self.evaluator))
        self.assertIsNotNone(change.decided_at)
        self.assertEqual(self.snapshot_deliverable(), before)  # el entregable sigue igual
        self.assertTrue(Notification.objects.filter(recipient=self.member, title="Solicitud de cambio aprobada: Quitar el login con Google").exists())

    def test_rechazo_definitivo_y_registro_inmutable(self):
        change = decide_change(self.propose(), self.evaluator, "rejected", "Es parte del alcance mínimo")
        with self.assertRaises(ValidationError):
            decide_change(change, self.evaluator, "approved", "Cambio de opinión")
        with self.assertRaises(PermissionDenied):
            update_change(change, self.member, title="Otro título")
        change.decision_comment = "editado a mano"
        with self.assertRaises(ImmutableChangeRequestError):
            change.save()
        with self.assertRaises(ImmutableChangeRequestError):
            change.delete()
        with self.assertRaises(ImmutableChangeRequestError):
            ChangeRequest.objects.all().delete()
        # Tampoco en bloque: update() y bulk_update() se saltarían save()
        with self.assertRaises(ImmutableChangeRequestError):
            ChangeRequest.objects.filter(pk=change.pk).update(decision_comment="reescrito")
        with self.assertRaises(ImmutableChangeRequestError):
            ChangeRequest.objects.bulk_update([change], ["decision_comment"])
        change.refresh_from_db()
        self.assertEqual(change.decision_comment, "Es parte del alcance mínimo")
        self.assertEqual(AuditLog.objects.filter(action=Action.CHANGE_DECIDED).count(), 1)

    def test_editar_y_retirar_solo_quien_propuso(self):
        change = self.propose()
        with self.assertRaises(PermissionDenied):
            update_change(change, self.member2, title="Otro título")
        change = update_change(change, self.member, title="Posponer el login con Google", affected_deliverables=[])
        self.assertEqual(change.affected_deliverables.count(), 0)
        log = AuditLog.objects.filter(action=Action.CHANGE_UPDATED).last()
        self.assertEqual(set(log.changes), {"title", "affected_deliverables"})
        with self.assertRaises(PermissionDenied):
            withdraw_change(change, self.leader)
        change = withdraw_change(change, self.member)
        self.assertEqual(change.status, Status.WITHDRAWN)
        with self.assertRaises(ValidationError):
            decide_change(change, self.evaluator, "approved", "Tarde")

    def test_decision_invalida(self):
        with self.assertRaises(ValidationError):
            decide_change(self.propose(), self.evaluator, "maybe", "No sé")
