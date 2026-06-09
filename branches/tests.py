from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import StaffProfile, StaffRole
from branches.models import Branch, BranchType

User = get_user_model()


class BranchesPageAccessTests(APITestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )

        self.hq_admin = User.objects.create_user(username="hqboss", password="pass")
        StaffProfile.objects.create(
            user=self.hq_admin,
            branch=self.branch,
            role=StaffRole.HQ_ADMIN,
        )

        self.zimhope = User.objects.create_user(username="Zimhope", password="pass")
        StaffProfile.objects.create(
            user=self.zimhope,
            branch=self.branch,
            role=StaffRole.CASHIER,
        )

    def test_branches_page_shows_edit_controls_only_for_zimhope(self):
        self.client.force_login(self.hq_admin)
        response = self.client.get(reverse("ui:branches"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="branch-form"')

        self.client.force_login(self.zimhope)
        response = self.client.get(reverse("ui:branches"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="branch-form"')
        self.assertContains(response, "canManageBranches = true")
