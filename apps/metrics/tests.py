from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.evaluations.services import evaluate_deliverable
from apps.integrations.models import Commit
from apps.projects.models import Deliverable, Milestone, Project, ProjectMembership
from apps.projects.services import submit_deliverable

User = get_user_model()
Role = ProjectMembership.ProjectRole


class ProjectMetricsTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.leader = User.objects.create_user("lider", "lider@x.com", "x")
        self.ana = User.objects.create_user("ana", "ana@x.com", "x", first_name="Ana", last_name="Díaz")
        self.leo = User.objects.create_user("leo", "leo@x.com", "x")
        self.outsider = User.objects.create_user("ajeno", "ajeno@x.com", "x")
        self.project = Project.objects.create(name="Demo", owner=self.leader)
        ProjectMembership.objects.create(project=self.project, user=self.leader, role=Role.LEADER)
        ProjectMembership.objects.create(project=self.project, user=self.ana, role=Role.MEMBER)
        ProjectMembership.objects.create(project=self.project, user=self.leo, role=Role.MEMBER)
        milestone = Milestone.objects.create(project=self.project, title="H1", due_date=now.date())

        def deliverable(title, days, *assignees):
            d = Deliverable.objects.create(milestone=milestone, title=title, due_at=now + timedelta(days=days))
            d.assignees.set(assignees)
            return d

        # Ana: una a tiempo y aprobada con 90, otra tarde y rechazada con 50
        a1 = deliverable("A1", 3, self.ana)
        submit_deliverable(a1, self.ana, url="https://example.com/a1")
        evaluate_deliverable(a1, self.leader, "approved", 90)
        a2 = deliverable("A2", -1, self.ana)
        submit_deliverable(a2, self.ana, url="https://example.com/a2")
        evaluate_deliverable(a2, self.leader, "rejected", 50)
        # Leo: una pendiente y vencida
        deliverable("L1", -2, self.leo)

        for i, author in enumerate([self.ana, self.ana, self.leo, None]):
            Commit.objects.create(
                project=self.project, sha=f"{i:040d}", committed_at=now - timedelta(days=i), author=author,
                deliverable=a1 if i == 0 else None,
            )
        Commit.objects.create(project=self.project, sha="9" * 40, committed_at=now - timedelta(days=60), author=self.leo)

    def get(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client.get(f"/api/projects/{self.project.pk}/metrics/")

    def test_metricas_del_proyecto(self):
        data = self.get(self.ana).data
        d = data["deliverables"]
        self.assertEqual((d["total"], d["delivered"], d["late"], d["on_time_rate"]), (3, 2, 1, 50))
        self.assertEqual(d["by_status"]["approved"], 1)
        self.assertEqual(d["by_status"]["rejected"], 1)
        self.assertEqual(d["average_score"], 70.0)
        self.assertEqual(d["overdue"], 2)  # la rechazada (vencida) y la pendiente de Leo
        c = data["commits"]
        self.assertEqual((c["total"], c["linked_to_deliverables"], c["unlinked_author"], c["last_30_days"]), (5, 1, 1, 4))
        self.assertEqual(len(c["by_week"]), 8)
        self.assertEqual(sum(w["count"] for w in c["by_week"]), 4)  # el de hace 60 días queda fuera

    def test_metricas_por_integrante(self):
        members = {m["username"]: m for m in self.get(self.leader).data["members"]}
        ana = members["ana"]
        self.assertEqual(ana["name"], "Ana Díaz")
        self.assertEqual((ana["assigned"], ana["delivered"], ana["late"], ana["approved"]), (2, 2, 1, 1))
        self.assertEqual((ana["on_time_rate"], ana["average_score"], ana["commits"], ana["versions"]), (50, 70.0, 2, 2))
        leo = members["leo"]
        self.assertEqual((leo["assigned"], leo["delivered"], leo["on_time_rate"], leo["commits"]), (1, 0, None, 2))

    def test_nota_vigente_es_la_ultima_evaluacion(self):
        a2 = Deliverable.objects.get(title="A2")
        submit_deliverable(a2, self.ana, url="https://example.com/a2-v2")
        evaluate_deliverable(a2, self.leader, "approved", 80)
        data = self.get(self.ana).data
        self.assertEqual(data["deliverables"]["average_score"], 85.0)

    def test_ajeno_404_y_sin_sesion_401(self):
        self.assertEqual(self.get(self.outsider).status_code, 404)
        self.assertEqual(APIClient().get(f"/api/projects/{self.project.pk}/metrics/").status_code, 401)
