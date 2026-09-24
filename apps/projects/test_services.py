from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import Deliverable, Milestone, Project, ProjectMembership
from .services import change_status, submit_deliverable

User = get_user_model()
Status = Deliverable.Status
Role = ProjectMembership.ProjectRole


class DeliverableFlowTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x")
        self.student = User.objects.create_user("estudiante", "est@x.com", "x")
        self.evaluator = User.objects.create_user("evaluador", "eva@x.com", "x")
        self.outsider = User.objects.create_user(
            "ajeno", "ajeno@x.com", "x", global_role=User.GlobalRole.EVALUATOR
        )

        project = Project.objects.create(name="Demo", owner=self.leader)
        ProjectMembership.objects.create(project=project, user=self.leader, role=Role.LEADER)
        ProjectMembership.objects.create(project=project, user=self.student, role=Role.MEMBER)
        ProjectMembership.objects.create(project=project, user=self.evaluator, role=Role.EVALUATOR)

        milestone = Milestone.objects.create(project=project, title="H1", due_date=timezone.now().date())
        self.due = timezone.now() + timedelta(days=1)
        self.deliverable = Deliverable.objects.create(milestone=milestone, title="E1", due_at=self.due)
        self.deliverable.assignees.add(self.student)

    # Helpers para no repetir código
    def on_time(self):
        return self.due - timedelta(hours=1)

    def late(self):
        return self.due + timedelta(hours=1)

    # --- Entregar ---
    def test_entrega_a_tiempo(self):
        d = submit_deliverable(self.deliverable, self.student, at=self.on_time())
        self.assertEqual(d.status, Status.SUBMITTED)
        self.assertFalse(d.is_late)

    def test_entrega_tardia_queda_marcada(self):
        d = submit_deliverable(self.deliverable, self.student, at=self.late())
        self.assertEqual(d.status, Status.LATE)
        self.assertTrue(d.is_late)

    def test_no_asignado_no_puede_entregar(self):
        with self.assertRaises(PermissionDenied):
            submit_deliverable(self.deliverable, self.leader, at=self.on_time())

    def test_no_se_puede_entregar_dos_veces(self):
        submit_deliverable(self.deliverable, self.student, at=self.on_time())
        with self.assertRaises(ValidationError):
            submit_deliverable(self.deliverable, self.student, at=self.on_time())

    # --- Revisar ---
    def test_flujo_completo_aprobado(self):
        submit_deliverable(self.deliverable, self.student, at=self.on_time())
        change_status(self.deliverable, self.evaluator, Status.IN_REVIEW)
        d = change_status(self.deliverable, self.evaluator, Status.APPROVED)
        self.assertEqual(d.status, Status.APPROVED)

    def test_is_late_no_se_borra_al_aprobar(self):
        submit_deliverable(self.deliverable, self.student, at=self.late())
        change_status(self.deliverable, self.leader, Status.IN_REVIEW)
        d = change_status(self.deliverable, self.leader, Status.APPROVED)
        self.assertTrue(d.is_late)

    def test_reentrega_tardia_tras_rechazo(self):
        submit_deliverable(self.deliverable, self.student, at=self.on_time())
        change_status(self.deliverable, self.evaluator, Status.IN_REVIEW)
        change_status(self.deliverable, self.evaluator, Status.REJECTED)
        d = submit_deliverable(self.deliverable, self.student, at=self.late())
        self.assertEqual(d.status, Status.LATE)
        self.assertTrue(d.is_late)

    def test_estudiante_no_puede_aprobar(self):
        submit_deliverable(self.deliverable, self.student, at=self.on_time())
        with self.assertRaises(PermissionDenied):
            change_status(self.deliverable, self.student, Status.IN_REVIEW)

    def test_evaluador_global_de_otro_proyecto_no_puede_revisar(self):
        submit_deliverable(self.deliverable, self.student, at=self.on_time())
        with self.assertRaises(PermissionDenied):
            change_status(self.deliverable, self.outsider, Status.IN_REVIEW)

    def test_transicion_invalida(self):
        submit_deliverable(self.deliverable, self.student, at=self.on_time())
        with self.assertRaises(ValidationError):
            change_status(self.deliverable, self.evaluator, Status.APPROVED)  # se salta IN_REVIEW

    def test_estado_inexistente(self):
        submit_deliverable(self.deliverable, self.student, at=self.on_time())
        with self.assertRaises(ValidationError):
            change_status(self.deliverable, self.evaluator, "hackeado")