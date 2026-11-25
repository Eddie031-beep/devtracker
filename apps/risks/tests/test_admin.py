from django.test import TestCase

from apps.core.testing import ProjectFixtureMixin

from ..admin import MitigationInline, RiskAdmin
from ..models import Mitigation, Risk


class RiskAdminTests(ProjectFixtureMixin, TestCase):
    def test_estado_y_cumplimiento_solo_desde_el_flujo_auditado(self):
        from django.contrib.admin.sites import site

        self.assertIn("status", RiskAdmin(Risk, site).readonly_fields)
        self.assertIn("done", MitigationInline(Mitigation, site).readonly_fields)
