from django.test import TestCase
from django.urls import reverse
from .models import User
class SecuritySmokeTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="company1",email="company1@example.com",password="StrongPass!234",role=User.Role.COMPANY)
        User.objects.create_user(username="procurement1",email="procurement1@example.com",password="StrongPass!234",role=User.Role.PROCUREMENT)
    def test_company_cannot_open_procurement_review(self):
        self.client.login(username="company1",password="StrongPass!234")
        self.assertEqual(self.client.get(reverse("registration_review")).status_code,302)
    def test_procurement_can_open_review(self):
        self.client.login(username="procurement1",password="StrongPass!234")
        self.assertEqual(self.client.get(reverse("registration_review")).status_code,200)
    def test_anonymous_dashboard_redirects(self):
        self.assertEqual(self.client.get(reverse("dashboard")).status_code,302)
