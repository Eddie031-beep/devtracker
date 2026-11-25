from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.audit.models import Action, AuditLog
from apps.core.testing import ProjectFixtureMixin
from apps.notifications.models import Notification

from .. import matrix
from ..models import Risk
from ..services import add_mitigation, change_status, create_risk, delete_risk, set_mitigation_done, update_risk

Status = Risk.Status


class MatrixTests(SimpleTestCase):
    def test_nivel_por_probabilidad_por_impacto(self):
        expected = {
            (1, 1): "low", (1, 2): "low", (2, 1): "low",
            (1, 3): "medium", (3, 1): "medium", (2, 2): "medium",
            (2, 3): "high", (3, 2): "high", (3, 3): "high",
        }
        for (p, i), level in expected.items():
            self.assertEqual(matrix.level(p, i), level, f"{p}×{i}")

    def test_fuera_de_escala(self):
        with self.assertRaises(ValueError):
            matrix.score(0, 2)
        with self.assertRaises(ValueError):
            matrix.score(2, 4)

    def test_matriz_3x3_de_alta_a_baja(self):
        grid = matrix.build_matrix([])
        self.assertEqual([row["probability"] for row in grid["rows"]], [3, 2, 1])
        self.assertEqual([c["score"] for c in grid["rows"][0]["cells"]], [3, 6, 9])


@override_settings(NOTIFICATIONS_SEND_EMAIL=False)
class RiskServiceTests(ProjectFixtureMixin, TestCase):
    def new_risk(self, actor=None, probability=2, impact=2, owner=None):
        return create_risk(
            self.project, actor or self.member, title="Se cae Railway", description="El servicio deja de responder en la demo",
            probability=probability, impact=impact, owner=owner or self.member2,
        )

    def test_registrar_calcula_el_nivel(self):
        risk = self.new_risk(probability=3, impact=2)
        self.assertEqual((risk.score, risk.level, risk.status), (6, "high", Status.IDENTIFIED))
        self.assertTrue(AuditLog.objects.filter(action=Action.RISK_CREATED, target_id=risk.pk).exists())
        # Al responsable le llega el aviso; por ser alto, también al líder y al evaluador
        self.assertEqual(set(Notification.objects.values_list("recipient__username", flat=True)), {"beto", "lider", "prof"})

    def test_quien_registra_y_validaciones(self):
        with self.assertRaises(PermissionDenied):
            self.new_risk(actor=self.evaluator)
        with self.assertRaises(PermissionDenied):
            self.new_risk(actor=self.outsider)
        with self.assertRaises(ValidationError):
            self.new_risk(probability=4)
        with self.assertRaises(ValidationError):
            self.new_risk(owner=self.evaluator)  # el responsable es un estudiante

    def test_la_base_rechaza_valores_fuera_de_escala(self):
        risk = self.new_risk()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Risk.objects.filter(pk=risk.pk).update(probability=5)

    def test_editar_recalcula_y_permisos(self):
        risk = self.new_risk()
        with self.assertRaises(PermissionDenied):
            update_risk(risk, self.member, impact=3)  # lo registró, pero no es el responsable ni el líder
        risk = update_risk(risk, self.member2, impact=3)
        self.assertEqual((risk.score, risk.level), (6, "high"))
        log = AuditLog.objects.filter(action=Action.RISK_UPDATED).last()
        self.assertEqual(log.changes["score"], {"before": 4, "after": 6})

    def test_estados(self):
        risk = self.new_risk()
        with self.assertRaises(ValidationError):
            change_status(risk, self.member2, Status.CLOSED)  # falta el comentario
        with self.assertRaises(PermissionDenied):
            change_status(risk, self.member, Status.MITIGATING)
        risk = change_status(risk, self.member2, Status.OCCURRED, "Se cayó el día de la demo")
        self.assertEqual(risk.status, Status.OCCURRED)
        with self.assertRaises(ValidationError):
            change_status(risk, self.leader, Status.IDENTIFIED)  # de materializado no vuelve a identificado
        risk = change_status(risk, self.leader, Status.CLOSED, "Se migró a otro plan")
        risk = change_status(risk, self.leader, Status.IDENTIFIED)  # reabrir
        self.assertEqual(AuditLog.objects.filter(action=Action.RISK_STATUS_CHANGED, target_id=risk.pk).count(), 3)

    def test_mitigacion(self):
        risk = self.new_risk()
        with self.assertRaises(PermissionDenied):
            add_mitigation(risk, self.member, description="Tener un respaldo local")
        with self.assertRaises(ValidationError):
            add_mitigation(risk, self.leader, description="Plan B", due_date=timezone.localdate() - timedelta(days=1))
        mitigation = add_mitigation(risk, self.leader, description="Tener un respaldo local", responsible=self.member)
        risk.refresh_from_db()
        self.assertEqual(risk.status, Status.MITIGATING)  # la primera medida lo pone en mitigación
        self.assertTrue(Notification.objects.filter(recipient=self.member, title__contains="Medida").exists())
        with self.assertRaises(PermissionDenied):
            set_mitigation_done(mitigation, self.evaluator)
        mitigation = set_mitigation_done(mitigation, self.member)
        self.assertTrue(mitigation.done)
        self.assertIsNotNone(mitigation.done_at)

    def test_no_se_mitiga_un_riesgo_cerrado(self):
        risk = change_status(self.new_risk(), self.leader, Status.CLOSED, "Ya no aplica")
        with self.assertRaises(ValidationError):
            add_mitigation(risk, self.leader, description="Algo tarde")

    def test_borrado_logico_solo_lider(self):
        risk = self.new_risk()
        with self.assertRaises(PermissionDenied):
            delete_risk(risk, self.member2)
        delete_risk(risk, self.leader)
        self.assertFalse(Risk.objects.filter(pk=risk.pk).exists())
        self.assertTrue(Risk.all_objects.filter(pk=risk.pk).exists())
