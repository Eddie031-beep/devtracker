from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Deliverable, Milestone, Project, ProjectMembership

User = get_user_model()
Role = ProjectMembership.ProjectRole


class ApiSecurityTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x")
        # Líder del proyecto A, pero solo integrante del proyecto B
        self.project_a = Project.objects.create(name="A", owner=self.leader)
        self.project_b = Project.objects.create(name="B", owner=self.leader)
        ProjectMembership.objects.create(project=self.project_a, user=self.leader, role=Role.LEADER)
        ProjectMembership.objects.create(project=self.project_b, user=self.leader, role=Role.MEMBER)

        today = timezone.now().date()
        self.milestone_a = Milestone.objects.create(project=self.project_a, title="H-A", due_date=today)
        self.milestone_b = Milestone.objects.create(project=self.project_b, title="H-B", due_date=today)
        self.deliverable = Deliverable.objects.create(
            milestone=self.milestone_a, title="E1", due_at=timezone.now() + timedelta(days=1)
        )

        self.client = APIClient()
        self.client.force_authenticate(self.leader)

    def test_status_no_se_puede_cambiar_por_la_api(self):
        self.client.patch(f"/api/deliverables/{self.deliverable.pk}/", {"status": "approved"}, format="json")
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.status, Deliverable.Status.PENDING)

    def test_submitted_at_no_se_puede_cambiar_por_la_api(self):
        self.client.patch(
            f"/api/deliverables/{self.deliverable.pk}/", {"submitted_at": timezone.now().isoformat()}, format="json"
        )
        self.deliverable.refresh_from_db()
        self.assertIsNone(self.deliverable.submitted_at)

    def test_no_se_puede_mover_hito_a_otro_proyecto(self):
        response = self.client.patch(
            f"/api/milestones/{self.milestone_a.pk}/", {"project": self.project_b.pk}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.milestone_a.refresh_from_db()
        self.assertEqual(self.milestone_a.project, self.project_a)

    def test_no_se_puede_mover_entregable_a_otro_proyecto(self):
        response = self.client.patch(
            f"/api/deliverables/{self.deliverable.pk}/", {"milestone": self.milestone_b.pk}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.milestone, self.milestone_a)
