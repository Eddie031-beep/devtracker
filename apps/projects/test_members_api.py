from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Deliverable, Milestone, Project, ProjectMembership

User = get_user_model()
Role = ProjectMembership.ProjectRole


class MembersApiTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x")
        self.member = User.objects.create_user("ana", "ana@x.com", "x")
        self.newbie = User.objects.create_user("nuevo", "nuevo@x.com", "x")
        self.outsider = User.objects.create_user("ajeno", "ajeno@x.com", "x")

        self.project = Project.objects.create(name="Demo", owner=self.leader)
        self.leader_m = ProjectMembership.objects.create(project=self.project, user=self.leader, role=Role.LEADER)
        self.member_m = ProjectMembership.objects.create(project=self.project, user=self.member, role=Role.MEMBER)

        milestone = Milestone.objects.create(project=self.project, title="H1", due_date=timezone.now().date())
        self.deliverable = Deliverable.objects.create(milestone=milestone, title="E1", due_at=timezone.now())

        self.client = APIClient()
        self.members_url = f"/api/projects/{self.project.pk}/members/"

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def member_url(self, membership):
        return f"{self.members_url}{membership.pk}/"

    # --- Listar ---
    def test_integrante_ve_la_lista(self):
        response = self.as_user(self.member).get(self.members_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_ajeno_recibe_404(self):
        response = self.as_user(self.outsider).get(self.members_url)
        self.assertEqual(response.status_code, 404)

    # --- Agregar ---
    def test_lider_agrega_por_correo(self):
        response = self.as_user(self.leader).post(self.members_url, {"email": "nuevo@x.com"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["username"], "nuevo")
        self.assertEqual(response.data["role"], Role.MEMBER)

    def test_integrante_no_puede_agregar(self):
        response = self.as_user(self.member).post(self.members_url, {"email": "nuevo@x.com"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_agregar_duplicado_da_400(self):
        response = self.as_user(self.leader).post(self.members_url, {"email": "ana@x.com"}, format="json")
        self.assertEqual(response.status_code, 400)

    # --- Editar ---
    def test_cambiar_rol_y_responsabilidades(self):
        response = self.as_user(self.leader).patch(
            self.member_url(self.member_m), {"role": "evaluator", "responsibilities": "Pruebas"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["role"], Role.EVALUATOR)
        self.assertEqual(response.data["responsibilities"], "Pruebas")

    def test_degradar_al_unico_lider_da_400(self):
        response = self.as_user(self.leader).patch(self.member_url(self.leader_m), {"role": "member"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_patch_vacio_da_400(self):
        response = self.as_user(self.leader).patch(self.member_url(self.member_m), {}, format="json")
        self.assertEqual(response.status_code, 400)

    # --- Quitar ---
    def test_lider_quita_integrante(self):
        response = self.as_user(self.leader).delete(self.member_url(self.member_m))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ProjectMembership.objects.filter(pk=self.member_m.pk).exists())

    def test_quitar_al_unico_lider_da_400(self):
        response = self.as_user(self.leader).delete(self.member_url(self.leader_m))
        self.assertEqual(response.status_code, 400)

    # --- Asignar entregables ---
    def test_asignar_entregable_a_integrante(self):
        response = self.as_user(self.leader).put(
            f"/api/deliverables/{self.deliverable.pk}/assignees/", {"assignees": [self.member.pk]}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["assignees"], [self.member.pk])

    def test_asignar_a_alguien_de_fuera_da_400(self):
        response = self.as_user(self.leader).put(
            f"/api/deliverables/{self.deliverable.pk}/assignees/", {"assignees": [self.outsider.pk]}, format="json"
        )
        self.assertEqual(response.status_code, 400)
