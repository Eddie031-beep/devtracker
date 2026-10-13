from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.admin import AuditLogAdmin
from apps.audit.models import Action, AuditLog, ImmutableAuditError
from apps.audit.services import diff, log_action
from apps.projects.models import Deliverable, Milestone, Project, ProjectMembership
from apps.projects.services import change_status, submit_deliverable
from apps.projects.services_members import (
    add_member,
    change_role,
    remove_member,
    set_deliverable_assignees,
    update_responsibilities,
)

User = get_user_model()
Role = ProjectMembership.ProjectRole
Status = Deliverable.Status

# Hash rápido: las pruebas crean muchos usuarios y no necesitan PBKDF2
FAST_HASH = override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])


class AuditBase(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x")
        self.student = User.objects.create_user("ana", "ana@x.com", "x")
        self.evaluator = User.objects.create_user("prof", "prof@x.com", "x")
        self.outsider = User.objects.create_user("ajeno", "ajeno@x.com", "x")
        self.newbie = User.objects.create_user("nuevo", "nuevo@x.com", "x")
        self.admin = User.objects.create_user("admin", "admin@x.com", "x", global_role=User.GlobalRole.ADMIN)

        self.project = Project.objects.create(name="Demo", owner=self.leader)
        ProjectMembership.objects.create(project=self.project, user=self.leader, role=Role.LEADER)
        self.student_m = ProjectMembership.objects.create(project=self.project, user=self.student, role=Role.MEMBER)
        ProjectMembership.objects.create(project=self.project, user=self.evaluator, role=Role.EVALUATOR)

        self.milestone = Milestone.objects.create(project=self.project, title="H1", due_date=timezone.now().date())
        self.deliverable = Deliverable.objects.create(
            milestone=self.milestone, title="E1", due_at=timezone.now() + timedelta(days=1)
        )
        self.deliverable.assignees.add(self.student)

        self.client = APIClient()

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def logs(self, action=None):
        qs = AuditLog.objects.filter(project=self.project)
        return qs.filter(action=action) if action else qs


@FAST_HASH
class ImmutabilityTests(AuditBase):
    def setUp(self):
        super().setUp()
        self.entry = log_action(self.leader, Action.PROJECT_UPDATED, self.project, changes={"name": {"before": "a", "after": "b"}})

    def test_editar_un_registro_falla(self):
        self.entry.action = Action.PROJECT_DELETED
        with self.assertRaises(ImmutableAuditError):
            self.entry.save()

    def test_borrar_un_registro_falla(self):
        with self.assertRaises(ImmutableAuditError):
            self.entry.delete()
        self.assertTrue(AuditLog.objects.filter(pk=self.entry.pk).exists())

    def test_operaciones_masivas_fallan(self):
        with self.assertRaises(ImmutableAuditError):
            AuditLog.objects.all().delete()
        with self.assertRaises(ImmutableAuditError):
            AuditLog.objects.all().update(action="x")
        with self.assertRaises(ImmutableAuditError):
            AuditLog.objects.bulk_update([self.entry], ["action"])

    def test_la_base_de_datos_rechaza_update_y_delete_en_sql_crudo(self):
        if connection.vendor not in ("postgresql", "sqlite"):
            self.skipTest("Triggers solo en Postgres y SQLite")
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE audit_auditlog SET action = 'hack'")
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM audit_auditlog")
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.action, Action.PROJECT_UPDATED)

    def test_admin_es_de_solo_lectura_incluso_para_superusuario(self):
        superuser = User.objects.create_superuser("root", "root@x.com", "x")
        request = RequestFactory().get("/admin/")
        request.user = superuser
        model_admin = AuditLogAdmin(AuditLog, admin.site)
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request, self.entry))
        self.assertFalse(model_admin.has_delete_permission(request, self.entry))

    def test_accion_desconocida_se_rechaza(self):
        with self.assertRaises(ValueError):
            log_action(self.leader, "inventada.accion", self.project)

    def test_diff_solo_incluye_lo_que_cambio(self):
        self.assertEqual(diff({"a": 1, "b": 2}, {"a": 1, "b": 3}), {"b": {"before": 2, "after": 3}})


@FAST_HASH
class ServiceAuditTests(AuditBase):
    def test_un_cambio_de_estado_genera_registro(self):
        submit_deliverable(self.deliverable, self.student)
        change_status(self.deliverable, self.evaluator, Status.IN_REVIEW)

        entry = self.logs(Action.DELIVERABLE_STATUS_CHANGED).get()
        self.assertEqual(entry.actor, self.evaluator)
        self.assertEqual(entry.target_type, "deliverable")
        self.assertEqual(entry.target_id, self.deliverable.pk)
        self.assertEqual(entry.changes["status"], {"before": Status.SUBMITTED, "after": Status.IN_REVIEW})

    def test_entrega_a_tiempo_y_tardia_se_registran(self):
        submit_deliverable(self.deliverable, self.student)
        entry = self.logs(Action.DELIVERABLE_SUBMITTED).get()
        self.assertEqual(entry.changes["status"]["after"], Status.SUBMITTED)
        self.assertNotIn("is_late", entry.changes)  # False -> False no es un cambio

        self.deliverable.refresh_from_db()
        late = Deliverable.objects.create(
            milestone=self.milestone, title="E2", due_at=timezone.now() - timedelta(hours=1)
        )
        late.assignees.add(self.student)
        submit_deliverable(late, self.student)
        late_entry = self.logs(Action.DELIVERABLE_SUBMITTED).get(target_id=late.pk)
        self.assertEqual(late_entry.changes["is_late"], {"before": False, "after": True})

    def test_un_intento_rechazado_no_deja_registro(self):
        with self.assertRaises(Exception):
            change_status(self.deliverable, self.student, Status.APPROVED)  # estudiante no revisa
        self.assertFalse(self.logs(Action.DELIVERABLE_STATUS_CHANGED).exists())

    def test_cambios_de_integrantes(self):
        member = add_member(self.project, self.leader, "nuevo@x.com", Role.MEMBER, "Backend")
        added = self.logs(Action.MEMBER_ADDED).get()
        self.assertEqual((added.target_type, added.target_id), ("user", self.newbie.pk))
        self.assertEqual(added.changes["role"], {"before": None, "after": Role.MEMBER})

        change_role(member, self.leader, Role.EVALUATOR)
        changed = self.logs(Action.MEMBER_ROLE_CHANGED).get()
        self.assertEqual(changed.changes["role"], {"before": Role.MEMBER, "after": Role.EVALUATOR})

        change_role(member, self.leader, Role.EVALUATOR)  # mismo rol: no es un cambio
        self.assertEqual(self.logs(Action.MEMBER_ROLE_CHANGED).count(), 1)

        update_responsibilities(member, self.leader, "Frontend")
        self.assertEqual(
            self.logs(Action.MEMBER_RESPONSIBILITIES_CHANGED).get().changes["responsibilities"],
            {"before": "Backend", "after": "Frontend"},
        )

        remove_member(member, self.leader)
        removed = self.logs(Action.MEMBER_REMOVED).get()
        self.assertEqual(removed.target_id, self.newbie.pk)

    def test_quitar_integrante_registra_sus_entregables_desasignados(self):
        remove_member(self.student_m, self.leader)
        removed = self.logs(Action.MEMBER_REMOVED).get()
        self.assertEqual(removed.changes["unassigned_deliverables"]["before"], [self.deliverable.pk])

    def test_cambio_de_asignados(self):
        set_deliverable_assignees(self.deliverable, self.leader, [self.leader])
        entry = self.logs(Action.DELIVERABLE_ASSIGNEES_CHANGED).get()
        self.assertEqual(entry.changes["assignees"], {"before": [self.student.pk], "after": [self.leader.pk]})
        set_deliverable_assignees(self.deliverable, self.leader, [self.leader])  # sin cambios
        self.assertEqual(self.logs(Action.DELIVERABLE_ASSIGNEES_CHANGED).count(), 1)


@FAST_HASH
class CrudAuditTests(AuditBase):
    def test_proyecto_crear_editar_borrar(self):
        client = self.as_user(self.leader)
        created = client.post("/api/projects/", {"name": "Nuevo", "start_date": "2026-10-01"}, format="json")
        self.assertEqual(created.status_code, 201)
        project_id = created.data["id"]
        entry = AuditLog.objects.get(action=Action.PROJECT_CREATED, target_id=project_id)
        self.assertEqual(entry.actor, self.leader)
        self.assertEqual(entry.project_id, project_id)
        self.assertEqual(entry.changes["name"], {"before": None, "after": "Nuevo"})

        client.patch(f"/api/projects/{project_id}/", {"name": "Renombrado"}, format="json")
        updated = AuditLog.objects.get(action=Action.PROJECT_UPDATED, target_id=project_id)
        self.assertEqual(updated.changes, {"name": {"before": "Nuevo", "after": "Renombrado"}})

        # Un PATCH que no cambia nada no ensucia la auditoría
        client.patch(f"/api/projects/{project_id}/", {"name": "Renombrado"}, format="json")
        self.assertEqual(AuditLog.objects.filter(action=Action.PROJECT_UPDATED, target_id=project_id).count(), 1)

        client.delete(f"/api/projects/{project_id}/")
        deleted = AuditLog.objects.get(action=Action.PROJECT_DELETED, target_id=project_id)
        self.assertEqual(deleted.changes["name"], {"before": "Renombrado", "after": None})

    def test_hito_y_entregable(self):
        client = self.as_user(self.leader)
        m = client.post(
            "/api/milestones/",
            {"project": self.project.pk, "title": "H2", "due_date": "2026-11-01"},
            format="json",
        )
        self.assertEqual(m.status_code, 201)
        self.assertTrue(self.logs(Action.MILESTONE_CREATED).filter(target_id=m.data["id"]).exists())

        client.patch(f"/api/milestones/{m.data['id']}/", {"title": "H2 bis"}, format="json")
        self.assertTrue(self.logs(Action.MILESTONE_UPDATED).filter(target_id=m.data["id"]).exists())

        d = client.post(
            "/api/deliverables/",
            {"milestone": m.data["id"], "title": "E9", "due_at": "2026-11-02T10:00:00Z"},
            format="json",
        )
        self.assertEqual(d.status_code, 201)
        created = self.logs(Action.DELIVERABLE_CREATED).get(target_id=d.data["id"])
        self.assertEqual(created.project, self.project)  # el proyecto se deduce del entregable

        client.delete(f"/api/deliverables/{d.data['id']}/")
        client.delete(f"/api/milestones/{m.data['id']}/")
        self.assertTrue(self.logs(Action.DELIVERABLE_DELETED).filter(target_id=d.data["id"]).exists())
        self.assertTrue(self.logs(Action.MILESTONE_DELETED).filter(target_id=m.data["id"]).exists())

    def test_una_peticion_rechazada_no_deja_registro(self):
        before = AuditLog.objects.count()
        response = self.as_user(self.student).patch(f"/api/projects/{self.project.pk}/", {"name": "X"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(AuditLog.objects.count(), before)


@FAST_HASH
class AuditEndpointTests(AuditBase):
    def setUp(self):
        super().setUp()
        self.url = f"/api/projects/{self.project.pk}/audit/"
        submit_deliverable(self.deliverable, self.student)
        change_status(self.deliverable, self.evaluator, Status.IN_REVIEW)

    def test_lider_evaluador_y_admin_pueden_verla(self):
        for user in (self.leader, self.evaluator, self.admin):
            response = self.as_user(user).get(self.url)
            self.assertEqual(response.status_code, 200, user)
            self.assertEqual(response.data["count"], 2)

    def test_integrante_normal_recibe_403(self):
        self.assertEqual(self.as_user(self.student).get(self.url).status_code, 403)

    def test_ajeno_recibe_404_y_anonimo_401(self):
        self.assertEqual(self.as_user(self.outsider).get(self.url).status_code, 404)
        self.assertIn(APIClient().get(self.url).status_code, (401, 403))

    def test_es_solo_lectura(self):
        client = self.as_user(self.leader)
        for method in (client.post, client.put, client.patch, client.delete):
            self.assertEqual(method(self.url).status_code, 405)

    def test_filtro_por_accion(self):
        response = self.as_user(self.leader).get(self.url, {"action": Action.DELIVERABLE_SUBMITTED})
        self.assertEqual([r["action"] for r in response.data["results"]], [Action.DELIVERABLE_SUBMITTED])

    def test_filtro_por_fecha(self):
        old = datetime(2026, 1, 15, 15, 0, tzinfo=dt_timezone.utc)
        with mock.patch("django.utils.timezone.now", return_value=old):
            log_action(self.leader, Action.PROJECT_UPDATED, self.project, changes={"name": {"before": "a", "after": "b"}})
        client = self.as_user(self.leader)

        january = client.get(self.url, {"date_from": "2026-01-01", "date_to": "2026-01-31"})
        self.assertEqual([r["action"] for r in january.data["results"]], [Action.PROJECT_UPDATED])

        recent = client.get(self.url, {"date_from": "2026-02-01"})
        self.assertEqual(recent.data["count"], 2)

        self.assertEqual(client.get(self.url, {"date_to": "2025-12-31"}).data["count"], 0)

    def test_fecha_invalida_da_400(self):
        response = self.as_user(self.leader).get(self.url, {"date_from": "ayer"})
        self.assertEqual(response.status_code, 400)

    def test_orden_mas_reciente_primero_y_datos_utiles(self):
        results = self.as_user(self.leader).get(self.url).data["results"]
        self.assertEqual(results[0]["action"], Action.DELIVERABLE_STATUS_CHANGED)
        self.assertEqual(results[0]["actor_name"], str(self.evaluator))
        self.assertEqual(results[0]["action_display"], "Cambio de estado de entregable")

    def test_solo_muestra_registros_de_ese_proyecto(self):
        other = Project.objects.create(name="Otro", owner=self.leader)
        ProjectMembership.objects.create(project=other, user=self.leader, role=Role.LEADER)
        log_action(self.leader, Action.PROJECT_UPDATED, other, changes={})
        self.assertEqual(self.as_user(self.leader).get(self.url).data["count"], 2)

    def test_auditoria_de_proyecto_eliminado_sigue_consultable(self):
        self.as_user(self.leader).delete(f"/api/projects/{self.project.pk}/")
        response = self.as_user(self.leader).get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["action"], Action.PROJECT_DELETED)
