from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import Deliverable, Milestone, Project

User = get_user_model()


class SoftDeleteTests(TestCase):
    def test_deleted_project_is_hidden_but_kept(self):
        owner = User.objects.create_user(username="lider", email="lider@example.com", password="x")
        project = Project.objects.create(name="Demo", owner=owner)
        project.delete()
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())
        self.assertTrue(Project.all_objects.filter(pk=project.pk).exists())


class DeliverableTests(TestCase):
    def test_is_past_due(self):
        owner = User.objects.create_user(username="lider", email="lider@example.com", password="x")
        project = Project.objects.create(name="Demo", owner=owner)
        milestone = Milestone.objects.create(project=project, title="H1", due_date=timezone.now().date())
        d = Deliverable.objects.create(milestone=milestone, title="E1", due_at=timezone.now() - timedelta(hours=1))
        self.assertTrue(d.is_past_due())
