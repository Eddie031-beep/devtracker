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
