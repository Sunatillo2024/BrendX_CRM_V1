"""Tests for the deployment health probe (used by Docker health checks)."""
from django.test import TestCase


class HealthEndpointTests(TestCase):
    def test_health_endpoint_reports_ok(self):
        response = self.client.get('/health/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertTrue(payload['database'])

    def test_health_endpoint_is_public(self):
        # No Authorization header is sent: the probe must never require auth.
        response = self.client.get('/health/')
        self.assertNotEqual(response.status_code, 401)
        self.assertNotEqual(response.status_code, 403)
