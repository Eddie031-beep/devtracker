from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import Deliverable, Milestone, Project, ProjectMembership
from .permissions import (
    IsProjectLeader,
    IsProjectMember,
    filter_deliverables_for_user,
    filter_milestones_for_user,
    filter_projects_for_user,
)

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


class ProjectPermissionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", email="owner@example.com", password="x")
        self.member = User.objects.create_user(username="member", email="member@example.com", password="x")
        self.outsider = User.objects.create_user(
            username="outsider", email="outsider@example.com", password="x"
        )
        self.admin = User.objects.create_user(
            username="admin", email="admin@example.com", password="x", global_role=User.GlobalRole.ADMIN
        )
        self.project = Project.objects.create(name="Visible", owner=self.owner)
        self.other_project = Project.objects.create(name="Private", owner=self.outsider)
        ProjectMembership.objects.create(
            project=self.project, user=self.member, role=ProjectMembership.ProjectRole.MEMBER
        )
        ProjectMembership.objects.create(
            project=self.project, user=self.owner, role=ProjectMembership.ProjectRole.LEADER
        )
        self.milestone = Milestone.objects.create(
            project=self.project, title="Hito", due_date=timezone.now().date()
        )
        self.deliverable = Deliverable.objects.create(
            milestone=self.milestone, title="Entrega", due_at=timezone.now()
        )
        other_milestone = Milestone.objects.create(
            project=self.other_project, title="Otro hito", due_date=timezone.now().date()
        )
        self.other_deliverable = Deliverable.objects.create(
            milestone=other_milestone, title="Otra entrega", due_at=timezone.now()
        )

    def test_un_integrante_ve_solo_sus_recursos(self):
        self.assertEqual(list(filter_projects_for_user(Project.objects.all(), self.member)), [self.project])
        self.assertEqual(
            list(filter_milestones_for_user(Milestone.objects.all(), self.member)), [self.milestone]
        )
        self.assertEqual(
            list(filter_deliverables_for_user(Deliverable.objects.all(), self.member)), [self.deliverable]
        )

    def test_un_no_integrante_no_puede_ver_nada_del_proyecto(self):
        request = type("Request", (), {"user": self.outsider})()
        for resource in (self.project, self.milestone, self.deliverable):
            with self.subTest(resource=resource):
                self.assertFalse(IsProjectMember().has_object_permission(request, None, resource))

    def test_lider_y_admin_pasan_el_permiso_de_liderazgo(self):
        for user in (self.owner, self.admin):
            with self.subTest(user=user):
                request = type("Request", (), {"user": user})()
                self.assertTrue(IsProjectLeader().has_object_permission(request, None, self.project))

    def test_admin_global_ve_todos_los_recursos(self):
        self.assertQuerySetEqual(
            filter_projects_for_user(Project.objects.all(), self.admin), Project.objects.all(), ordered=False
        )
        self.assertQuerySetEqual(
            filter_milestones_for_user(Milestone.objects.all(), self.admin), Milestone.objects.all(), ordered=False
        )
        self.assertQuerySetEqual(
            filter_deliverables_for_user(Deliverable.objects.all(), self.admin),
            Deliverable.objects.all(),
            ordered=False,
        )
