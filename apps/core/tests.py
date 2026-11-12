from django.test import TestCase
from django.urls import reverse


class HealthTests(TestCase):
    def test_health_is_public(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_root_redirects_to_admin(self):
        response = self.client.get("/")
        self.assertRedirects(response, "/admin/", fetch_redirect_response=False)


class ApiDocsTests(TestCase):
    def test_schema_y_swagger_son_publicos(self):
        schema = self.client.get(reverse("schema"))
        self.assertEqual(schema.status_code, 200)
        self.assertIn(b"/api/deliverables/{id}/submit/", schema.content)
        self.assertEqual(self.client.get(reverse("api_docs")).status_code, 200)
