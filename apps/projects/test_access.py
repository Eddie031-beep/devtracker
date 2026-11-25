from django.http import Http404
from django.test import TestCase

from apps.core.testing import ProjectFixtureMixin
from apps.web.modules import PROJECT_MODULES, ProjectModule, module_context

from .access import get_project_or_404, is_evaluator, is_leader, is_project_member, is_student, project_people, project_role


class ProjectAccessTests(ProjectFixtureMixin, TestCase):
    def test_roles_en_el_proyecto(self):
        self.assertEqual(project_role(self.leader, self.project), "leader")
        self.assertEqual(project_role(self.evaluator, self.project), "evaluator")
        self.assertEqual(project_role(self.admin, self.project), "admin")
        self.assertIsNone(project_role(self.outsider, self.project))

    def test_quien_es_que(self):
        self.assertTrue(is_leader(self.leader, self.project))
        self.assertFalse(is_leader(self.member, self.project))
        # El evaluador es del proyecto, pero no es estudiante; el líder sí lo es y no evalúa
        self.assertTrue(is_evaluator(self.evaluator, self.project))
        self.assertFalse(is_evaluator(self.leader, self.project))
        self.assertTrue(is_student(self.leader, self.project))
        self.assertTrue(is_student(self.member, self.project))
        self.assertFalse(is_student(self.evaluator, self.project))
        self.assertTrue(is_project_member(self.admin, self.project))
        self.assertFalse(is_project_member(self.outsider, self.project))

    def test_proyecto_ajeno_da_404(self):
        self.assertEqual(get_project_or_404(self.member, self.project.pk), self.project)
        with self.assertRaises(Http404):
            get_project_or_404(self.outsider, self.project.pk)

    def test_personas_del_proyecto_por_rol(self):
        self.assertEqual(project_people(self.project).count(), 4)
        self.assertEqual(list(project_people(self.project, roles=["evaluator"])), [self.evaluator])


class ProjectModulesTests(ProjectFixtureMixin, TestCase):
    def test_contexto_de_un_modulo(self):
        module = ProjectModule("demo", "web:project_history", "Demo", "Módulo de prueba")
        PROJECT_MODULES.append(module)
        self.addCleanup(PROJECT_MODULES.remove, module)
        context = module_context(self.project, "demo")
        self.assertEqual(context["active_module"], "demo")
        self.assertIn({"module": module, "url": f"/proyectos/{self.project.pk}/historial/"}, context["modules"])
        # La página del proyecto muestra la sección con el acceso al módulo
        response = self.web(self.member).get(f"/proyectos/{self.project.pk}/")
        self.assertContains(response, "Gestión del proyecto")
        self.assertContains(response, "Módulo de prueba")
