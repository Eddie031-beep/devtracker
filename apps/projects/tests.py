from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

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

    def test_recursos_de_proyecto_borrado_no_aparecen(self):
        self.project.delete()
        self.assertFalse(filter_milestones_for_user(Milestone.objects.all(), self.member).exists())
        self.assertFalse(filter_deliverables_for_user(Deliverable.objects.all(), self.member).exists())


class ProjectCrudApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", email="owner@example.com", password="x")
        self.member = User.objects.create_user(username="member", email="member@example.com", password="x")
        self.outsider = User.objects.create_user(
            username="outsider", email="outsider@example.com", password="x"
        )
        self.project = Project.objects.create(name="Project A", owner=self.owner)
        ProjectMembership.objects.create(
            project=self.project, user=self.owner, role=ProjectMembership.ProjectRole.LEADER
        )
        ProjectMembership.objects.create(
            project=self.project, user=self.member, role=ProjectMembership.ProjectRole.MEMBER
        )
        self.milestone = Milestone.objects.create(
            project=self.project, title="Hito A", due_date=timezone.now().date()
        )
        self.deliverable = Deliverable.objects.create(
            milestone=self.milestone, title="Entrega A", due_at=timezone.now()
        )

    def test_usuario_ajeno_recibe_404_en_proyecto_hito_y_entregable(self):
        self.client.force_authenticate(self.outsider)
        for name, instance in (
            ("project_detail", self.project),
            ("milestone_detail", self.milestone),
            ("deliverable_detail", self.deliverable),
        ):
            with self.subTest(resource=name):
                response = self.client.get(reverse(name, args=[instance.pk]))
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_usuario_ajeno_no_puede_editar_ni_borrar(self):
        self.client.force_authenticate(self.outsider)
        for name, instance, payload in (
            ("project_detail", self.project, {"name": "Intruso"}),
            ("milestone_detail", self.milestone, {"title": "Intruso"}),
            ("deliverable_detail", self.deliverable, {"title": "Intruso"}),
        ):
            with self.subTest(resource=name, method="patch"):
                response = self.client.patch(reverse(name, args=[instance.pk]), payload)
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
            with self.subTest(resource=name, method="delete"):
                response = self.client.delete(reverse(name, args=[instance.pk]))
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_crear_proyecto_registra_al_creador_como_lider(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(reverse("project_list_create"), {"name": "Nuevo proyecto"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        project = Project.objects.get(pk=response.data["id"])
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=project, user=self.owner, role=ProjectMembership.ProjectRole.LEADER
            ).exists()
        )

    def test_solo_el_lider_puede_crear_hitos_y_entregables(self):
        self.client.force_authenticate(self.member)
        milestone_response = self.client.post(
            reverse("milestone_list_create"),
            {"project": self.project.pk, "title": "No autorizado", "due_date": "2026-10-01"},
        )
        self.assertEqual(milestone_response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.owner)
        milestone_response = self.client.post(
            reverse("milestone_list_create"),
            {"project": self.project.pk, "title": "Nuevo hito", "due_date": "2026-10-01"},
        )
        self.assertEqual(milestone_response.status_code, status.HTTP_201_CREATED)
        deliverable_response = self.client.post(
            reverse("deliverable_list_create"),
            {
                "milestone": milestone_response.data["id"],
                "title": "Nueva entrega",
                "due_at": "2026-10-01T12:00:00Z",
            },
        )
        self.assertEqual(deliverable_response.status_code, status.HTTP_201_CREATED)
