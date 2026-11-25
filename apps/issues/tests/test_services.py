from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings

from apps.audit.models import Action, AuditLog
from apps.core.testing import ProjectFixtureMixin
from apps.notifications.models import Notification

from ..models import ImmutableHistoryError, Issue, IssueEvent
from ..services import (
    allowed_actions, assign_issue, comment_issue, create_issue, delete_issue, transition_issue, update_issue,
)

Status = Issue.Status
Kind = IssueEvent.Kind


@override_settings(NOTIFICATIONS_SEND_EMAIL=False)
class IssueFlowTests(ProjectFixtureMixin, TestCase):
    def new_issue(self, actor=None, **extra):
        data = {"title": "Login falla", "description": "Da error 500", "steps_to_reproduce": "1. Entrar\n2. Ver error"}
        return create_issue(self.project, actor or self.member, **{**data, **extra})

    def test_integrante_registra_con_prioridad_y_pasos(self):
        issue = self.new_issue(priority=Issue.Priority.HIGH)
        self.assertEqual(issue.status, Status.OPEN)
        self.assertEqual(issue.reported_by, self.member)
        self.assertEqual(issue.priority, "high")
        self.assertEqual(list(issue.events.values_list("kind", flat=True)), [Kind.CREATED])
        self.assertTrue(AuditLog.objects.filter(action=Action.ISSUE_CREATED, target_id=issue.pk).exists())
        # Al líder y al evaluador les llega el aviso
        self.assertEqual(
            set(Notification.objects.values_list("recipient__username", flat=True)), {"lider", "prof"}
        )

    def test_ajeno_no_registra(self):
        with self.assertRaises(PermissionDenied):
            self.new_issue(actor=self.outsider)

    def test_solo_el_lider_asigna_y_a_un_estudiante(self):
        issue = self.new_issue()
        with self.assertRaises(PermissionDenied):
            assign_issue(issue, self.member, self.member2)
        with self.assertRaises(ValidationError):
            assign_issue(issue, self.leader, self.evaluator)
        with self.assertRaises(ValidationError):
            assign_issue(issue, self.leader, self.outsider)
        issue = assign_issue(issue, self.leader, self.member2)
        self.assertEqual(issue.assignee, self.member2)
        self.assertTrue(Notification.objects.filter(recipient=self.member2, title__contains="asignaron").exists())

    def test_flujo_completo_con_verificacion(self):
        issue = assign_issue(self.new_issue(), self.leader, self.member2)
        self.assertEqual(allowed_actions(self.member2, issue), ["start"])
        with self.assertRaises(PermissionDenied):
            transition_issue(issue, self.member, "start")  # no es el responsable
        issue = transition_issue(issue, self.member2, "start")
        self.assertEqual(issue.status, Status.IN_PROGRESS)
        with self.assertRaises(ValidationError):
            transition_issue(issue, self.member2, "resolve", "")  # hay que explicar la solución
        issue = transition_issue(issue, self.member2, "resolve", "Se validó el token")
        self.assertEqual(issue.status, Status.RESOLVED)
        self.assertIsNotNone(issue.resolved_at)
        with self.assertRaises(PermissionDenied):
            transition_issue(issue, self.leader, "verify")  # el líder no verifica: es el evaluador
        issue = transition_issue(issue, self.evaluator, "verify", "Comprobado")
        self.assertEqual(issue.status, Status.VERIFIED)
        self.assertIsNotNone(issue.verified_at)
        self.assertEqual(
            list(issue.events.values_list("kind", flat=True)),
            [Kind.CREATED, Kind.ASSIGNED, Kind.STARTED, Kind.RESOLVED, Kind.VERIFIED],
        )

    def test_reabrir_conserva_el_historial(self):
        issue = self.new_issue(actor=self.leader, assignee=self.member)
        transition_issue(issue, self.member, "start")
        transition_issue(issue, self.member, "resolve", "Arreglado")
        with self.assertRaises(ValidationError):
            transition_issue(issue, self.evaluator, "reopen", "")  # el motivo es obligatorio
        issue = transition_issue(issue, self.evaluator, "reopen", "Sigue fallando en móvil")
        self.assertEqual(issue.status, Status.OPEN)
        self.assertIsNone(issue.resolved_at)
        kinds = list(issue.events.values_list("kind", flat=True))
        self.assertEqual(kinds.count(Kind.RESOLVED), 1)  # lo anterior sigue ahí
        self.assertEqual(kinds[-1], Kind.REOPENED)
        self.assertTrue(Notification.objects.filter(recipient=self.member, title__contains="reabierta").exists())
        # Se puede volver a resolver
        transition_issue(issue, self.member, "start")
        transition_issue(issue, self.member, "resolve", "Ahora sí")
        self.assertEqual(issue.events.filter(kind=Kind.RESOLVED).count(), 2)

    def test_transicion_invalida(self):
        issue = self.new_issue(actor=self.leader, assignee=self.member)
        with self.assertRaises(ValidationError):
            transition_issue(issue, self.evaluator, "verify")  # aún no está resuelta
        with self.assertRaises(ValidationError):
            transition_issue(issue, self.member, "cerrar")

    def test_editar_solo_quien_reporto_o_el_lider(self):
        issue = self.new_issue()
        with self.assertRaises(PermissionDenied):
            update_issue(issue, self.member2, title="Otro")
        update_issue(issue, self.member, title="Login falla en Safari", priority="critical")
        update_issue(issue, self.leader, description="Más detalle")
        issue.refresh_from_db()
        self.assertEqual((issue.title, issue.priority), ("Login falla en Safari", "critical"))
        log = AuditLog.objects.filter(action=Action.ISSUE_UPDATED).last()
        self.assertEqual(set(log.changes), {"title", "priority"})

    def test_no_se_edita_verificada(self):
        issue = self.new_issue(actor=self.leader, assignee=self.member)
        transition_issue(issue, self.member, "start")
        transition_issue(issue, self.member, "resolve", "ok")
        transition_issue(issue, self.evaluator, "verify")
        with self.assertRaises(PermissionDenied):
            update_issue(issue, self.leader, title="x")

    def test_comentarios_y_borrado_logico(self):
        issue = self.new_issue()
        comment_issue(issue, self.evaluator, "¿En qué navegador?")
        with self.assertRaises(ValidationError):
            comment_issue(issue, self.member, "   ")
        with self.assertRaises(PermissionDenied):
            delete_issue(issue, self.member)
        delete_issue(issue, self.leader)
        self.assertFalse(Issue.objects.filter(pk=issue.pk).exists())
        self.assertTrue(Issue.all_objects.filter(pk=issue.pk).exists())
        self.assertEqual(IssueEvent.objects.filter(issue=issue).count(), 2)

    def test_historial_inmutable(self):
        event = self.new_issue().events.first()
        event.comment = "cambiado"
        with self.assertRaises(ImmutableHistoryError):
            event.save()
        with self.assertRaises(ImmutableHistoryError):
            event.delete()
        with self.assertRaises(ImmutableHistoryError):
            IssueEvent.objects.all().update(comment="x")
