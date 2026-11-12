from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.evaluations.models import Evaluation
from apps.evaluations.services import evaluate_deliverable
from apps.projects.models import Deliverable, Milestone, Project, ProjectMembership
from apps.projects.services import submit_deliverable

User = get_user_model()
Status = Deliverable.Status
Role = ProjectMembership.ProjectRole


class WebTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user("lider", "lider@x.com", "x")
        self.ana = User.objects.create_user("ana", "ana@x.com", "x", first_name="Ana")
        self.prof = User.objects.create_user("prof", "prof@x.com", "x", global_role="evaluator")
        self.outsider = User.objects.create_user("ajeno", "ajeno@x.com", "x")
        self.admin = User.objects.create_superuser("root", "root@x.com", "x", global_role="admin")

        self.project = Project.objects.create(name="DevTracker", owner=self.leader)
        ProjectMembership.objects.create(project=self.project, user=self.leader, role=Role.LEADER)
        ProjectMembership.objects.create(project=self.project, user=self.ana, role=Role.MEMBER)
        ProjectMembership.objects.create(project=self.project, user=self.prof, role=Role.EVALUATOR)
        milestone = Milestone.objects.create(project=self.project, title="Hito 1", due_date=timezone.now().date())
        self.pending = Deliverable.objects.create(
            milestone=milestone, title="Informe final", due_at=timezone.now() + timedelta(days=2)
        )
        self.pending.assignees.set([self.ana])
        self.submitted = Deliverable.objects.create(
            milestone=milestone, title="Manual", due_at=timezone.now() + timedelta(days=2)
        )
        self.submitted.assignees.set([self.ana])
        submit_deliverable(self.submitted, self.ana, url="https://example.com/manual")

    def test_sin_sesion_va_al_login_y_el_login_funciona(self):
        self.assertRedirects(self.client.get("/"), "/login/?next=/", fetch_redirect_response=False)
        response = self.client.post(reverse("web:login"), {"username": "ana", "password": "x"})
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertContains(self.client.get("/"), "Hola, Ana")

    def test_dashboard_estudiante(self):
        self.client.force_login(self.ana)
        response = self.client.get("/")
        self.assertContains(response, "Informe final")  # su entrega pendiente
        self.assertNotContains(response, "Por revisar")
        self.assertNotContains(response, "Resumen general")

    def test_dashboard_evaluador_ve_lo_que_debe_revisar(self):
        self.client.force_login(self.prof)
        response = self.client.get("/")
        self.assertContains(response, "Por revisar")
        self.assertContains(response, "Manual")
        self.assertNotContains(response, "Resumen general")

    def test_dashboard_admin_ve_resumen_general(self):
        self.client.force_login(self.admin)
        response = self.client.get("/")
        self.assertContains(response, "Resumen general")
        self.assertContains(response, "overview-data")

    def test_proyecto_con_metricas_y_ajeno_404(self):
        self.client.force_login(self.ana)
        response = self.client.get(reverse("web:project", args=[self.project.pk]))
        self.assertContains(response, "Métricas por integrante")
        self.assertContains(response, "chart-data")
        self.assertContains(response, "Ana")
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("web:project", args=[self.project.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("web:deliverable", args=[self.pending.pk])).status_code, 404)

    def test_nota_promedio_cero_se_muestra(self):
        # Una nota de 0 es válida: no debe confundirse con «sin nota» (—)
        evaluate_deliverable(self.submitted, self.prof, "rejected", 0)
        self.client.force_login(self.ana)
        response = self.client.get(reverse("web:project", args=[self.project.pk]))
        self.assertContains(response, "<strong>0,0</strong><span>Nota promedio</span>", html=False)

    def test_estudiante_entrega_desde_la_web(self):
        self.client.force_login(self.ana)
        page = self.client.get(reverse("web:deliverable", args=[self.pending.pk]))
        self.assertContains(page, "Entregar")
        self.assertNotContains(page, "Registrar evaluación")
        self.client.post(
            reverse("web:deliverable_submit", args=[self.pending.pk]),
            {"url": "https://example.com/informe", "comment": "Primera versión"},
        )
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, Status.SUBMITTED)
        self.assertEqual(self.pending.versions.get().comment, "Primera versión")

    def test_url_invalida_no_entrega(self):
        self.client.force_login(self.ana)
        response = self.client.post(
            reverse("web:deliverable_submit", args=[self.pending.pk]), {"url": "ftp://x.com/a"}, follow=True
        )
        self.assertContains(response, "URL válida")
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, Status.PENDING)

    def test_evaluador_evalua_y_estudiante_no_puede(self):
        url = reverse("web:deliverable_evaluate", args=[self.submitted.pk])
        self.client.force_login(self.ana)
        response = self.client.post(url, {"decision": "approved", "score": 100}, follow=True)
        self.assertContains(response, "evaluador o el líder")
        self.assertFalse(Evaluation.objects.exists())

        self.client.force_login(self.prof)
        response = self.client.post(url, {"decision": "approved", "score": 92, "feedback": "Bien"}, follow=True)
        self.assertContains(response, "Evaluación registrada")
        self.submitted.refresh_from_db()
        self.assertEqual(self.submitted.status, Status.APPROVED)
        self.assertEqual(Evaluation.objects.get().score, 92)

    def test_logout_es_post(self):
        self.client.force_login(self.ana)
        response = self.client.post(reverse("web:logout"))
        self.assertRedirects(response, reverse("web:login"), fetch_redirect_response=False)
