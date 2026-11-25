"""Datos comunes para las pruebas de los módulos del proyecto (incidencias, riesgos, cambios, reuniones)."""

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.projects.models import Project, ProjectMembership

User = get_user_model()
Role = ProjectMembership.ProjectRole


class ProjectFixtureMixin:
    """Un proyecto con líder, dos integrantes, evaluador, un ajeno y un admin global."""

    def setUp(self):
        super().setUp()
        self.leader = User.objects.create_user("lider", "lider@x.com", "x", first_name="Lía")
        self.member = User.objects.create_user("ana", "ana@x.com", "x", first_name="Ana")
        self.member2 = User.objects.create_user("beto", "beto@x.com", "x", first_name="Beto")
        self.evaluator = User.objects.create_user("prof", "prof@x.com", "x", first_name="Profe")
        self.outsider = User.objects.create_user("ajeno", "ajeno@x.com", "x")
        self.admin = User.objects.create_user("admin", "admin@x.com", "x", global_role=User.GlobalRole.ADMIN)
        self.project = Project.objects.create(name="Demo", owner=self.leader)
        for user, role in [
            (self.leader, Role.LEADER), (self.member, Role.MEMBER), (self.member2, Role.MEMBER), (self.evaluator, Role.EVALUATOR),
        ]:
            ProjectMembership.objects.create(project=self.project, user=user, role=role)

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def web(self, user):
        self.client.force_login(user)
        return self.client
