from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from branches.models import Branch, BranchType
from orders.models import Order

from .branch_access import (
    user_can_access_bakery_transfers,
    user_can_access_grv,
    user_can_access_pos,
    user_can_manage_branches,
    user_can_manage_users,
    user_has_global_branch_access,
)
from .models import StaffProfile, StaffRole

User = get_user_model()


class StaffUserApiTests(APITestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="Main Street", location="Downtown")
        self.list_url = reverse("staffuser-list")
        self.hq_admin = User.objects.create_user(username="hqboss", password="pass")
        StaffProfile.objects.create(
            user=self.hq_admin,
            branch=self.branch,
            role=StaffRole.HQ_ADMIN,
        )
        self.client.force_authenticate(user=self.hq_admin)

    def test_create_staff_user_with_branch(self):
        response = self.client.post(
            self.list_url,
            {
                "username": "cashier1",
                "email": "cashier1@example.com",
                "password": "securepass1",
                "branch": self.branch.id,
                "role": StaffRole.BRANCH_MANAGER,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["username"], "cashier1")
        self.assertEqual(response.data["branch"], self.branch.id)
        self.assertEqual(response.data["branch_name"], "Main Street")
        self.assertEqual(response.data["role"], StaffRole.BRANCH_MANAGER)
        self.assertEqual(response.data["role_display"], "Branch Manager")
        self.assertNotIn("password", response.data)

        user = User.objects.get(username="cashier1")
        self.assertTrue(user.check_password("securepass1"))
        self.assertEqual(user.staff_profile.branch_id, self.branch.id)
        self.assertEqual(user.staff_profile.role, StaffRole.BRANCH_MANAGER)

    def test_list_staff_users(self):
        user = User.objects.create_user(username="manager", password="securepass1")
        StaffProfile.objects.create(user=user, branch=self.branch)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        manager = next(row for row in results if row["username"] == "manager")
        self.assertEqual(manager["branch_name"], "Main Street")
        self.assertEqual(manager["role"], StaffRole.CASHIER)
        self.assertEqual(manager["role_display"], "Cashier")

    def test_list_available_roles(self):
        response = self.client.get(reverse("staffuser-roles"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(any(r["value"] == StaffRole.CASHIER for r in response.data))

    def test_update_staff_user(self):
        user = User.objects.create_user(
            username="cashier1",
            email="old@example.com",
            password="securepass1",
        )
        StaffProfile.objects.create(
            user=user,
            branch=self.branch,
            role=StaffRole.CASHIER,
        )
        other_branch = Branch.objects.create(name="Second", location="Uptown")

        response = self.client.patch(
            reverse("staffuser-detail", args=[user.pk]),
            {
                "username": "cashier1",
                "email": "new@example.com",
                "branch": other_branch.id,
                "role": StaffRole.BRANCH_MANAGER,
                "is_active": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "new@example.com")
        self.assertEqual(response.data["branch"], other_branch.id)
        self.assertEqual(response.data["role"], StaffRole.BRANCH_MANAGER)
        self.assertFalse(response.data["is_active"])

        user.refresh_from_db()
        user.staff_profile.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")
        self.assertEqual(user.staff_profile.branch_id, other_branch.id)
        self.assertEqual(user.staff_profile.role, StaffRole.BRANCH_MANAGER)
        self.assertFalse(user.is_active)

    def test_cashier_cannot_access_users_api(self):
        cashier = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(
            user=cashier,
            branch=self.branch,
            role=StaffRole.CASHIER,
        )
        self.client.force_authenticate(user=cashier)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class BranchAccessTests(APITestCase):
    def setUp(self):
        self.branch_a = Branch.objects.create(
            name="Branch A",
            branch_type=BranchType.BRANCH,
        )
        self.branch_b = Branch.objects.create(
            name="Branch B",
            branch_type=BranchType.BRANCH,
        )
        Order.objects.create(branch=self.branch_a)
        Order.objects.create(branch=self.branch_b)

        self.cashier = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(
            user=self.cashier,
            branch=self.branch_a,
            role=StaffRole.CASHIER,
        )

        self.hq_admin = User.objects.create_user(username="hqboss", password="pass")
        StaffProfile.objects.create(
            user=self.hq_admin,
            branch=self.branch_a,
            role=StaffRole.HQ_ADMIN,
        )

        self.zimhope = User.objects.create_user(username="Zimhope", password="pass")
        StaffProfile.objects.create(
            user=self.zimhope,
            branch=self.branch_b,
            role=StaffRole.CASHIER,
        )

    def test_global_access_flags(self):
        self.assertTrue(user_has_global_branch_access(self.hq_admin))
        self.assertTrue(user_has_global_branch_access(self.zimhope))
        self.assertFalse(user_has_global_branch_access(self.cashier))

    def test_branch_staff_only_sees_own_orders(self):
        self.client.force_authenticate(user=self.cashier)
        response = self.client.get("/api/orders/")
        order_branches = {row["branch"] for row in response.data["results"]}
        self.assertEqual(order_branches, {self.branch_a.id})

    def test_branch_staff_cannot_filter_other_branch(self):
        self.client.force_authenticate(user=self.cashier)
        response = self.client.get(f"/api/orders/?branch={self.branch_b.id}")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["branch"], self.branch_a.id)

    def test_hq_admin_sees_all_orders(self):
        self.client.force_authenticate(user=self.hq_admin)
        response = self.client.get("/api/orders/")
        order_branches = {row["branch"] for row in response.data["results"]}
        self.assertEqual(order_branches, {self.branch_a.id, self.branch_b.id})

    def test_zimhope_sees_all_orders(self):
        self.client.force_authenticate(user=self.zimhope)
        response = self.client.get("/api/orders/")
        self.assertEqual(response.data["count"], 2)


class TransferNavAccessTests(APITestCase):
    def setUp(self):
        self.bakery = Branch.objects.create(
            name="Central Bakery",
            branch_type=BranchType.BAKERY,
        )
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        self.hq = Branch.objects.create(
            name="HQ",
            branch_type=BranchType.HQ,
        )

        self.baker = User.objects.create_user(username="baker", password="pass")
        StaffProfile.objects.create(
            user=self.baker,
            branch=self.bakery,
            role=StaffRole.BAKER,
        )

        self.cashier = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(
            user=self.cashier,
            branch=self.branch,
            role=StaffRole.CASHIER,
        )

        self.hq_staff = User.objects.create_user(username="hqstaff", password="pass")
        StaffProfile.objects.create(
            user=self.hq_staff,
            branch=self.hq,
            role=StaffRole.STAFF,
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

    def test_bakery_staff_access_flags(self):
        self.assertTrue(user_can_access_bakery_transfers(self.baker))
        self.assertFalse(user_can_access_grv(self.baker))
        self.assertFalse(user_can_access_pos(self.baker))

    def test_branch_staff_access_flags(self):
        self.assertFalse(user_can_access_bakery_transfers(self.cashier))
        self.assertTrue(user_can_access_grv(self.cashier))
        self.assertTrue(user_can_access_pos(self.cashier))

    def test_hq_staff_access_flags(self):
        self.assertFalse(user_can_access_bakery_transfers(self.hq_staff))
        self.assertTrue(user_can_access_grv(self.hq_staff))
        self.assertFalse(user_can_access_pos(self.hq_staff))

    def test_global_users_use_bakery_transfers_not_grv(self):
        self.assertTrue(user_can_access_bakery_transfers(self.hq_admin))
        self.assertFalse(user_can_access_grv(self.hq_admin))
        self.assertTrue(user_can_access_bakery_transfers(self.zimhope))
        self.assertFalse(user_can_access_grv(self.zimhope))
        self.assertTrue(user_can_access_pos(self.hq_admin))
        self.assertTrue(user_can_access_pos(self.zimhope))

    def test_pos_page_requires_branch_retail_access(self):
        self.client.force_login(self.baker)
        response = self.client.get(reverse("ui:pos"))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.hq_staff)
        response = self.client.get(reverse("ui:pos"))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.cashier)
        response = self.client.get(reverse("ui:pos"))
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.hq_admin)
        response = self.client.get(reverse("ui:pos"))
        self.assertEqual(response.status_code, 200)

    def test_transfers_page_requires_bakery_access(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse("ui:transfers"))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.baker)
        response = self.client.get(reverse("ui:transfers"))
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.hq_admin)
        response = self.client.get(reverse("ui:transfers"))
        self.assertEqual(response.status_code, 200)

    def test_grv_page_requires_branch_access(self):
        self.client.force_login(self.baker)
        response = self.client.get(reverse("ui:grv"))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.cashier)
        response = self.client.get(reverse("ui:grv"))
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.hq_staff)
        response = self.client.get(reverse("ui:grv"))
        self.assertEqual(response.status_code, 200)


class BranchManageAccessTests(APITestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )

        self.cashier = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(
            user=self.cashier,
            branch=self.branch,
            role=StaffRole.CASHIER,
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

    def test_manage_branches_access_flags(self):
        self.assertFalse(user_can_manage_branches(self.cashier))
        self.assertFalse(user_can_manage_branches(self.hq_admin))
        self.assertTrue(user_can_manage_branches(self.zimhope))

    def test_branch_list_allowed_for_all_staff(self):
        self.client.force_authenticate(user=self.cashier)
        response = self.client.get("/api/branches/")
        self.assertEqual(response.status_code, 200)

    def test_branch_create_restricted_to_zimhope(self):
        payload = {
            "name": "New Branch",
            "location": "Uptown",
            "branch_type": BranchType.BRANCH,
        }

        self.client.force_authenticate(user=self.hq_admin)
        response = self.client.post("/api/branches/", payload)
        self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(user=self.zimhope)
        response = self.client.post("/api/branches/", payload)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "New Branch")

    def test_branch_update_restricted_to_zimhope(self):
        payload = {"name": "Renamed Branch"}

        self.client.force_authenticate(user=self.hq_admin)
        response = self.client.patch(f"/api/branches/{self.branch.id}/", payload)
        self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(user=self.zimhope)
        response = self.client.patch(f"/api/branches/{self.branch.id}/", payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Renamed Branch")


class UsersNavAccessTests(APITestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )

        self.cashier = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(
            user=self.cashier,
            branch=self.branch,
            role=StaffRole.CASHIER,
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

    def test_manage_users_access_flags(self):
        self.assertFalse(user_can_manage_users(self.cashier))
        self.assertTrue(user_can_manage_users(self.hq_admin))
        self.assertTrue(user_can_manage_users(self.zimhope))

    def test_users_page_requires_manage_users_access(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse("ui:users"))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.hq_admin)
        response = self.client.get(reverse("ui:users"))
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.zimhope)
        response = self.client.get(reverse("ui:users"))
        self.assertEqual(response.status_code, 200)
