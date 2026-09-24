from datetime import date, timedelta
 
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
 
from .models import Deliverable, Milestone, Project, ProjectMembership
 
User = get_user_model()
Role = ProjectMembership.ProjectRole
 
 
class CrudTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x")
        self.member = User.objects.create_user("ana", "ana@x.com", "x")
        self.outsider = User.objects.create_user("ajeno", "ajeno@x.com", "x")
 
        self.project = Project.objects.create(
            name="Demo", owner=self.leader, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
        )
        ProjectMembership.objects.create(project=self.project, user=self.leader, role=Role.LEADER)
        ProjectMembership.objects.create(project=self.project, user=self.member, role=Role.MEMBER)
 
        self.client = APIClient()
 
    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client
 
    # --- Proyectos ---
    def test_crear_proyecto_deja_al_creador_como_lider(self):
        response = self.as_user(self.outsider).post("/api/projects/", {"name": "Nuevo"}, format="json")
        self.assertEqual(response.status_code, 201)
        membership = ProjectMembership.objects.get(project_id=response.data["id"], user=self.outsider)
        self.assertEqual(membership.role, Role.LEADER)
 
    def test_fecha_fin_anterior_al_inicio_se_rechaza(self):
        response = self.as_user(self.leader).post(
            "/api/projects/", {"name": "X", "start_date": "2026-05-10", "end_date": "2026-05-01"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("end_date", response.data)
 
    def test_patch_parcial_valida_contra_la_fecha_guardada(self):
        # Solo se envía end_date; debe compararse con el start_date ya guardado
        response = self.as_user(self.leader).patch(
            f"/api/projects/{self.project.pk}/", {"end_date": "2025-12-31"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
 
    def test_integrante_no_puede_editar_el_proyecto(self):
        response = self.as_user(self.member).patch(
            f"/api/projects/{self.project.pk}/", {"name": "Cambio"}, format="json"
        )
        self.assertEqual(response.status_code, 403)
 
    def test_eliminar_proyecto_es_borrado_logico(self):
        response = self.as_user(self.leader).delete(f"/api/projects/{self.project.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        self.assertTrue(Project.all_objects.filter(pk=self.project.pk).exists())
 
    def test_ajeno_no_ve_el_proyecto(self):
        response = self.as_user(self.outsider).get(f"/api/projects/{self.project.pk}/")
        self.assertEqual(response.status_code, 404)
 
    # --- Hitos ---
    def test_crear_hito_dentro_del_rango(self):
        response = self.as_user(self.leader).post(
            "/api/milestones/", {"project": self.project.pk, "title": "H1", "due_date": "2026-06-01"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
 
    def test_hito_fuera_del_rango_se_rechaza(self):
        response = self.as_user(self.leader).post(
            "/api/milestones/", {"project": self.project.pk, "title": "H1", "due_date": "2027-01-15"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("due_date", response.data)
 
    def test_integrante_no_puede_crear_hitos(self):
        response = self.as_user(self.member).post(
            "/api/milestones/", {"project": self.project.pk, "title": "H1", "due_date": "2026-06-01"}, format="json"
        )
        self.assertEqual(response.status_code, 403)
 
    # --- Entregables ---
    def test_crear_y_eliminar_entregable(self):
        milestone = Milestone.objects.create(project=self.project, title="H1", due_date=date(2026, 6, 1))
        due_at = (timezone.now() + timedelta(days=7)).isoformat()
        client = self.as_user(self.leader)
        response = client.post(
            "/api/deliverables/", {"milestone": milestone.pk, "title": "E1", "due_at": due_at}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        deliverable_id = response.data["id"]
 
        response = client.delete(f"/api/deliverables/{deliverable_id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Deliverable.objects.filter(pk=deliverable_id).exists())
        self.assertTrue(Deliverable.all_objects.filter(pk=deliverable_id).exists())
 
    def test_integrante_ve_los_entregables_de_su_proyecto(self):
        milestone = Milestone.objects.create(project=self.project, title="H1", due_date=date(2026, 6, 1))
        Deliverable.objects.create(milestone=milestone, title="E1", due_at=timezone.now())
        response = self.as_user(self.member).get("/api/deliverables/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)