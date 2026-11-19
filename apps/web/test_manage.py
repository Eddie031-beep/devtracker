import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import Action, AuditLog
from apps.projects.models import Deliverable, Milestone, Project, ProjectMembership

User = get_user_model()
Role = ProjectMembership.ProjectRole


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", SITE_URL="https://devtracker.test")
class PasswordResetWebTests(TestCase):
    def test_recupera_la_contrasena_con_el_enlace_del_correo(self):
        user = User.objects.create_user("ana", "ana@x.com", "vieja-clave-1")
        self.assertContains(self.client.get(reverse("web:login")), "¿Olvidaste tu contraseña?")
        response = self.client.post(reverse("web:password_reset"), {"email": "ANA@x.com"})
        self.assertRedirects(response, reverse("web:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"https://devtracker\.test(/recuperar/\S+/)", mail.outbox[0].body).group(1)
        form_url = self.client.get(link, follow=True).redirect_chain[-1][0]
        response = self.client.post(form_url, {"new_password1": "Nueva-Clave-2026", "new_password2": "Nueva-Clave-2026"})
        self.assertRedirects(response, reverse("web:password_reset_complete"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("Nueva-Clave-2026"))
        # El enlace sirve una sola vez
        self.assertContains(self.client.get(link, follow=True), "Enlace vencido")

    def test_correo_desconocido_no_revela_nada(self):
        response = self.client.post(reverse("web:password_reset"), {"email": "nadie@x.com"})
        self.assertRedirects(response, reverse("web:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)


@override_settings(NOTIFICATIONS_SEND_EMAIL=False)
class LeaderManageTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x", first_name="Lía")
        self.ana = User.objects.create_user("ana", "ana@x.com", "x", first_name="Ana")
        self.leo = User.objects.create_user("leo", "leo@x.com", "x", first_name="Leo")
        self.project = Project.objects.create(name="Demo", owner=self.leader, github_repo="equipo/devtracker")
        ProjectMembership.objects.create(project=self.project, user=self.leader, role=Role.LEADER)
        self.ana_membership = ProjectMembership.objects.create(project=self.project, user=self.ana, role=Role.MEMBER)
        self.milestone = Milestone.objects.create(project=self.project, title="Hito 1", due_date=timezone.now().date())
        self.deliverable = Deliverable.objects.create(
            milestone=self.milestone, title="Informe", due_at=timezone.now() + timedelta(days=2)
        )
        self.deliverable.assignees.set([self.ana])

    def actions(self):
        return list(AuditLog.objects.filter(project=self.project).values_list("action", flat=True))

    def test_crear_proyecto_deja_al_creador_como_lider(self):
        self.client.force_login(self.leo)
        response = self.client.post(reverse("web:project_create"), {"name": "Nuevo", "description": "", "github_repo": ""})
        project = Project.objects.get(name="Nuevo")
        self.assertRedirects(response, reverse("web:project", args=[project.pk]), fetch_redirect_response=False)
        self.assertEqual(project.memberships.get(user=self.leo).role, Role.LEADER)
        self.assertTrue(AuditLog.objects.filter(project=project, action=Action.PROJECT_CREATED).exists())

    def test_editar_proyecto_y_generar_secreto_que_se_ve_una_vez(self):
        self.client.force_login(self.leader)
        url = reverse("web:project_edit", args=[self.project.pk])
        data = {"name": "Demo 2", "description": "", "github_repo": "equipo/devtracker", "new_secret": "on"}
        response = self.client.post(url, data)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Demo 2")
        self.assertEqual(len(self.project.github_webhook_secret), 64)
        self.assertContains(response, self.project.github_webhook_secret)
        self.assertContains(response, f"/api/integrations/github/webhook/{self.project.pk}/")
        self.assertNotContains(self.client.get(url), self.project.github_webhook_secret)
        log = AuditLog.objects.get(project=self.project, action=Action.PROJECT_UPDATED)
        self.assertNotIn(self.project.github_webhook_secret, str(log.changes))
        self.assertEqual(log.changes["name"], {"before": "Demo", "after": "Demo 2"})

    def test_integrante_no_puede_administrar(self):
        self.client.force_login(self.ana)
        for name, args in (
            ("project_edit", [self.project.pk]), ("members", [self.project.pk]),
            ("milestone_edit", [self.milestone.pk]), ("deliverable_edit", [self.deliverable.pk]),
        ):
            self.assertEqual(self.client.get(reverse(f"web:{name}", args=args)).status_code, 403, name)
        self.assertEqual(self.client.post(reverse("web:deliverable_delete", args=[self.deliverable.pk])).status_code, 403)
        self.assertTrue(Deliverable.objects.filter(pk=self.deliverable.pk).exists())
        self.client.force_login(self.leo)  # ajeno al proyecto
        self.assertEqual(self.client.get(reverse("web:project_edit", args=[self.project.pk])).status_code, 404)

    def test_editar_entregable_audita_y_cambia_asignados(self):
        self.client.force_login(self.leader)
        ProjectMembership.objects.create(project=self.project, user=self.leo, role=Role.MEMBER)
        due = (timezone.localtime() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            reverse("web:deliverable_edit", args=[self.deliverable.pk]),
            {"milestone": self.milestone.pk, "title": "Informe final", "description": "", "due_at": due, "assignees": [self.leo.pk]},
        )
        self.assertRedirects(response, reverse("web:deliverable", args=[self.deliverable.pk]), fetch_redirect_response=False)
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.title, "Informe final")
        self.assertEqual(list(self.deliverable.assignees.all()), [self.leo])
        self.assertTrue({Action.DELIVERABLE_UPDATED, Action.DELIVERABLE_ASSIGNEES_CHANGED} <= set(self.actions()))
        page = self.client.get(reverse("web:deliverable_edit", args=[self.deliverable.pk]))
        self.assertContains(page, f'value="{due}"')  # la fecha vuelve a aparecer en el formulario

    def test_eliminar_es_logico_y_queda_en_la_auditoria(self):
        self.client.force_login(self.leader)
        self.client.post(reverse("web:deliverable_delete", args=[self.deliverable.pk]))
        self.assertFalse(Deliverable.objects.filter(pk=self.deliverable.pk).exists())
        self.assertIsNotNone(Deliverable.all_objects.get(pk=self.deliverable.pk).deleted_at)
        self.client.post(reverse("web:milestone_delete", args=[self.milestone.pk]))
        self.assertIsNotNone(Milestone.all_objects.get(pk=self.milestone.pk).deleted_at)
        self.client.post(reverse("web:project_delete", args=[self.project.pk]))
        self.assertIsNotNone(Project.all_objects.get(pk=self.project.pk).deleted_at)
        self.assertTrue({Action.DELIVERABLE_DELETED, Action.MILESTONE_DELETED, Action.PROJECT_DELETED} <= set(self.actions()))
        self.assertEqual(self.client.get(reverse("web:project", args=[self.project.pk])).status_code, 404)

    def test_editar_hito(self):
        self.client.force_login(self.leader)
        page = self.client.get(reverse("web:milestone_edit", args=[self.milestone.pk]))
        self.assertContains(page, f'value="{self.milestone.due_date:%Y-%m-%d}"')
        self.client.post(
            reverse("web:milestone_edit", args=[self.milestone.pk]),
            {"title": "Hito uno", "description": "", "due_date": "2026-12-15"},
        )
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.title, "Hito uno")
        self.assertIn(Action.MILESTONE_UPDATED, self.actions())

    def test_integrantes_agregar_cambiar_y_quitar(self):
        self.client.force_login(self.leader)
        url = reverse("web:members", args=[self.project.pk])
        self.client.post(url, {"user": self.leo.pk, "role": Role.EVALUATOR, "responsibilities": "Revisa entregas"})
        leo = self.project.memberships.get(user=self.leo)
        self.assertEqual((leo.role, leo.responsibilities), (Role.EVALUATOR, "Revisa entregas"))

        prefix = f"m{self.ana_membership.pk}"
        self.client.post(
            reverse("web:member_update", args=[self.project.pk, self.ana_membership.pk]),
            {f"{prefix}-role": Role.MEMBER, f"{prefix}-responsibilities": "Frontend"},
        )
        self.ana_membership.refresh_from_db()
        self.assertEqual(self.ana_membership.responsibilities, "Frontend")

        self.client.post(reverse("web:member_remove", args=[self.project.pk, self.ana_membership.pk]))
        self.assertFalse(self.project.memberships.filter(user=self.ana).exists())
        self.assertFalse(self.deliverable.assignees.filter(pk=self.ana.pk).exists())
        self.assertTrue(
            {Action.MEMBER_ADDED, Action.MEMBER_RESPONSIBILITIES_CHANGED, Action.MEMBER_REMOVED} <= set(self.actions())
        )

    def test_no_se_puede_quitar_al_unico_lider(self):
        self.client.force_login(self.leader)
        leader_membership = self.project.memberships.get(user=self.leader)
        prefix = f"m{leader_membership.pk}"
        response = self.client.post(
            reverse("web:member_update", args=[self.project.pk, leader_membership.pk]),
            {f"{prefix}-role": Role.MEMBER, f"{prefix}-responsibilities": ""}, follow=True,
        )
        self.assertEqual(self.project.memberships.get(user=self.leader).role, Role.LEADER)
        self.assertContains(response, "líder")


@override_settings(NOTIFICATIONS_SEND_EMAIL=False)
class TestSessionFindingsTests(TestCase):
    """Hallazgos de la prueba integral del 19/11."""

    setUp = LeaderManageTests.setUp

    def test_editar_solo_el_titulo_no_registra_cambio_de_fecha(self):
        self.client.force_login(self.leader)
        due = timezone.localtime(self.deliverable.due_at).strftime("%Y-%m-%dT%H:%M")
        # Guardada sin segundos, como la dejaría el formulario
        self.deliverable.due_at = timezone.make_aware(timezone.datetime.strptime(due, "%Y-%m-%dT%H:%M"))
        self.deliverable.save()
        self.client.post(
            reverse("web:deliverable_edit", args=[self.deliverable.pk]),
            {"milestone": self.milestone.pk, "title": "Otro título", "description": "", "due_at": due, "assignees": [self.ana.pk]},
        )
        log = AuditLog.objects.get(project=self.project, action=Action.DELIVERABLE_UPDATED)
        self.assertEqual(list(log.changes), ["title"])

    def test_agregar_integrante_arranca_como_integrante(self):
        self.client.force_login(self.leader)
        page = self.client.get(reverse("web:members", args=[self.project.pk]))
        self.assertContains(page, '<option value="member" selected>')

    def test_auditoria_muestra_el_nombre_del_integrante(self):
        self.client.force_login(self.leader)
        self.client.post(reverse("web:members", args=[self.project.pk]), {"user": self.leo.pk, "role": Role.MEMBER, "responsibilities": ""})
        page = self.client.get(reverse("web:project_audit", args=[self.project.pk]), {"action": Action.MEMBER_ADDED})
        self.assertContains(page, "Integrante · Leo")


class SuperuserRoleTests(TestCase):
    def test_createsuperuser_queda_como_administrador(self):
        user = User.objects.create_superuser("jefe", "jefe@x.com", "x")
        self.assertEqual(user.global_role, User.GlobalRole.ADMIN)
        self.assertEqual(User.objects.create_user("ana", "ana@x.com", "x").global_role, User.GlobalRole.STUDENT)
