from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import Deliverable, Milestone, Project, ProjectMembership
from .services_members import (
    add_member,
    change_role,
    remove_member,
    set_deliverable_assignees,
    update_responsibilities,
)

User = get_user_model()
Role = ProjectMembership.ProjectRole


class MembersServiceTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x")
        self.member = User.objects.create_user("ana", "ana@x.com", "x")
        self.evaluator = User.objects.create_user("prof", "prof@x.com", "x")
        self.newbie = User.objects.create_user("nuevo", "nuevo@x.com", "x")
        self.admin = User.objects.create_user(
            "admin", "admin@x.com", "x", global_role=User.GlobalRole.ADMIN
        )

        self.project = Project.objects.create(name="Demo", owner=self.leader)
        self.leader_m = ProjectMembership.objects.create(project=self.project, user=self.leader, role=Role.LEADER)
        self.member_m = ProjectMembership.objects.create(project=self.project, user=self.member, role=Role.MEMBER)
        ProjectMembership.objects.create(project=self.project, user=self.evaluator, role=Role.EVALUATOR)

        milestone = Milestone.objects.create(project=self.project, title="H1", due_date=timezone.now().date())
        self.deliverable = Deliverable.objects.create(milestone=milestone, title="E1", due_at=timezone.now())
        self.deliverable.assignees.add(self.member)

    # --- Agregar ---
    def test_lider_agrega_por_correo_sin_importar_mayusculas(self):
        m = add_member(self.project, self.leader, "NUEVO@x.com")
        self.assertEqual(m.user, self.newbie)
        self.assertEqual(m.role, Role.MEMBER)

    def test_admin_global_puede_agregar(self):
        add_member(self.project, self.admin, "nuevo@x.com")
        self.assertTrue(ProjectMembership.objects.filter(project=self.project, user=self.newbie).exists())

    def test_integrante_no_puede_agregar(self):
        with self.assertRaises(PermissionDenied):
            add_member(self.project, self.member, "nuevo@x.com")

    def test_evaluador_no_puede_gestionar_miembros(self):
        with self.assertRaises(PermissionDenied):
            add_member(self.project, self.evaluator, "nuevo@x.com")

    def test_no_se_puede_agregar_dos_veces(self):
        with self.assertRaises(ValidationError):
            add_member(self.project, self.leader, "ana@x.com")

    def test_correo_inexistente(self):
        with self.assertRaises(ValidationError):
            add_member(self.project, self.leader, "nadie@x.com")

    def test_rol_invalido(self):
        with self.assertRaises(ValidationError):
            add_member(self.project, self.leader, "nuevo@x.com", role="jefe")

    # --- Cambiar rol ---
    def test_cambiar_rol(self):
        m = change_role(self.member_m, self.leader, Role.EVALUATOR)
        self.assertEqual(m.role, Role.EVALUATOR)

    def test_no_se_puede_degradar_al_unico_lider(self):
        with self.assertRaises(ValidationError):
            change_role(self.leader_m, self.leader, Role.MEMBER)

    def test_lider_a_lider_no_es_error(self):
        # Protege contra el falso positivo que discutimos
        m = change_role(self.leader_m, self.leader, Role.LEADER)
        self.assertEqual(m.role, Role.LEADER)

    def test_con_dos_lideres_si_se_puede_degradar_uno(self):
        change_role(self.member_m, self.leader, Role.LEADER)
        m = change_role(self.leader_m, self.leader, Role.MEMBER)
        self.assertEqual(m.role, Role.MEMBER)

    # --- Quitar ---
    def test_no_se_puede_quitar_al_unico_lider(self):
        with self.assertRaises(ValidationError):
            remove_member(self.leader_m, self.leader)

    def test_quitar_integrante_lo_quita_de_sus_entregables(self):
        remove_member(self.member_m, self.leader)
        self.assertFalse(ProjectMembership.objects.filter(pk=self.member_m.pk).exists())
        self.assertNotIn(self.member, self.deliverable.assignees.all())

    # --- Responsabilidades ---
    def test_actualizar_responsabilidades(self):
        m = update_responsibilities(self.member_m, self.leader, "  Frontend y pruebas  ")
        self.assertEqual(m.responsibilities, "Frontend y pruebas")

    # --- Asignar entregables ---
    def test_no_se_puede_asignar_a_alguien_de_fuera(self):
        with self.assertRaises(ValidationError):
            set_deliverable_assignees(self.deliverable, self.leader, [self.newbie])

    def test_asignar_reemplaza_la_lista(self):
        set_deliverable_assignees(self.deliverable, self.leader, [self.leader])
        self.assertEqual(list(self.deliverable.assignees.all()), [self.leader])