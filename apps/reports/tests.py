import csv
import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.evaluations.services import evaluate_deliverable
from apps.projects.models import Deliverable, Milestone, Project, ProjectMembership
from apps.projects.services import submit_deliverable

User = get_user_model()
Role = ProjectMembership.ProjectRole


def read_csv(response):
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")
    return list(csv.reader(io.StringIO(text.lstrip("﻿"))))


class ReportTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x", first_name="Lía")
        self.ana = User.objects.create_user("ana", "ana@x.com", "x", first_name="Ana", last_name="Díaz")
        self.outsider = User.objects.create_user("ajeno", "ajeno@x.com", "x")
        self.project = Project.objects.create(name="Proyecto Ñandú", owner=self.leader)
        ProjectMembership.objects.create(project=self.project, user=self.leader, role=Role.LEADER)
        ProjectMembership.objects.create(project=self.project, user=self.ana, role=Role.MEMBER)
        milestone = Milestone.objects.create(project=self.project, title="Hito 1", due_date=timezone.now().date())
        self.deliverable = Deliverable.objects.create(
            milestone=milestone, title="Informe", due_at=timezone.now() + timedelta(days=2)
        )
        self.deliverable.assignees.set([self.ana])
        submit_deliverable(self.deliverable, self.ana, url="https://example.com/informe")
        evaluate_deliverable(self.deliverable, self.leader, "approved", 88)

    def url(self, name):
        return reverse(f"reports:{name}", args=[self.project.pk])

    def test_csv_de_entregables(self):
        self.client.force_login(self.ana)
        response = self.client.get(self.url("deliverables_csv"))
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("proyecto-nandu-entregables", response["Content-Disposition"])
        rows = read_csv(response)
        self.assertEqual(rows[0][:3], ["Hito", "Entregable", "Asignados"])
        self.assertEqual(rows[1][1:4], ["Informe", "Ana Díaz", "Aprobado"])
        self.assertEqual(rows[1][-2:], ["1", "88"])

    def test_csv_de_integrantes(self):
        self.client.force_login(self.ana)
        rows = read_csv(self.client.get(self.url("members_csv")))
        ana = next(r for r in rows if r[1] == "ana")
        self.assertEqual(ana[3:6], ["1", "1", "0"])
        self.assertEqual(ana[8], "88.0")

    def test_auditoria_solo_para_quien_revisa(self):
        self.client.force_login(self.ana)
        self.assertEqual(self.client.get(self.url("audit_csv")).status_code, 403)
        self.client.force_login(self.leader)
        rows = read_csv(self.client.get(self.url("audit_csv")))
        self.assertIn("Entregable evaluado", [r[2] for r in rows])

    def test_reporte_imprimible_y_ajeno_404(self):
        self.client.force_login(self.ana)
        response = self.client.get(self.url("project"))
        self.assertContains(response, "Reporte del proyecto: Proyecto Ñandú")
        self.assertContains(response, "window.print()")
        self.client.force_login(self.outsider)
        for name in ("project", "deliverables_csv", "members_csv", "audit_csv"):
            self.assertEqual(self.client.get(self.url(name)).status_code, 404, name)
