from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import StaffProfile, StaffRole
from branches.models import Branch, BranchType, DiningTable

User = get_user_model()


class BranchListAccessTests(APITestCase):
    def setUp(self):
        self.branch_a = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        self.branch_b = Branch.objects.create(
            name="Borrowdale",
            branch_type=BranchType.BRANCH,
        )

        self.hq_admin = User.objects.create_user(username="hqboss", password="pass")
        StaffProfile.objects.create(
            user=self.hq_admin,
            branch=self.branch_a,
            role=StaffRole.HQ_ADMIN,
        )

        self.cashier = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(
            user=self.cashier,
            branch=self.branch_a,
            role=StaffRole.CASHIER,
            pos_access=True,
        )

    def test_cashier_sees_only_own_branch_in_api_list(self):
        self.client.force_authenticate(user=self.cashier)
        response = self.client.get(reverse("branch-list"))
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data["results"]}
        self.assertEqual(ids, {self.branch_a.id})

    def test_hq_admin_sees_all_branches_in_api_list(self):
        self.client.force_authenticate(user=self.hq_admin)
        response = self.client.get(reverse("branch-list"), {"page_size": 500})
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(self.branch_a.id, ids)
        self.assertIn(self.branch_b.id, ids)


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


class DiningTablePermissionTests(APITestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        self.table = DiningTable.objects.create(
            branch=self.branch,
            name="T1",
            sort_order=0,
        )

        self.cashier = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(
            user=self.cashier,
            branch=self.branch,
            role=StaffRole.CASHIER,
            pos_access=True,
        )

        self.manager = User.objects.create_user(username="manager", password="pass")
        StaffProfile.objects.create(
            user=self.manager,
            branch=self.branch,
            role=StaffRole.BRANCH_MANAGER,
            pos_access=True,
        )

    def test_cashier_can_list_but_not_create_dining_tables(self):
        list_url = reverse("dining-table-list")
        self.client.force_login(self.cashier)

        response = self.client.get(list_url, {"branch": self.branch.id})
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            list_url,
            {
                "branch": self.branch.id,
                "name": "T99",
                "sort_order": 99,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_branch_manager_can_create_dining_tables(self):
        list_url = reverse("dining-table-list")
        self.client.force_login(self.manager)

        response = self.client.post(
            list_url,
            {
                "branch": self.branch.id,
                "name": "T99",
                "sort_order": 99,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            DiningTable.objects.filter(branch=self.branch, name="T99").exists()
        )
