from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from branches.models import Branch, BranchType
from orders.models import Order

from .branch_access import (
    user_can_access_bakery_transfers,
    user_can_access_cashier_invoices,
    user_can_access_dashboard,
    user_can_access_fiscal_receipts,
    user_can_access_grv,
    user_can_access_kitchen,
    user_can_access_management_console,
    user_can_access_pos,
    user_can_access_stores_transfers,
    user_can_manage_branches,
    user_can_manage_users,
    user_has_global_branch_access,
    user_is_cashier,
    user_is_branch_manager,
    user_is_grv_staff,
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

    def test_create_cashier_grants_pos_access(self):
        response = self.client.post(
            self.list_url,
            {
                "username": "poscashier",
                "email": "pos@example.com",
                "password": "securepass1",
                "branch": self.branch.id,
                "role": StaffRole.CASHIER,
                "pos_access": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["pos_access"])
        user = User.objects.get(username="poscashier")
        self.assertTrue(user.staff_profile.pos_access)
        self.assertTrue(user_can_access_pos(user))

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

    def test_update_pos_access(self):
        user = User.objects.create_user(
            username="hqcashier",
            email="hq@example.com",
            password="securepass1",
        )
        hq = Branch.objects.create(name="HQ", branch_type=BranchType.HQ)
        StaffProfile.objects.create(
            user=user,
            branch=hq,
            role=StaffRole.CASHIER,
            pos_access=False,
        )

        response = self.client.patch(
            reverse("staffuser-detail", args=[user.pk]),
            {"pos_access": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["pos_access"])
        user.staff_profile.refresh_from_db()
        self.assertTrue(user.staff_profile.pos_access)
        self.assertTrue(user_can_access_pos(user))

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
        self.stores = Branch.objects.create(
            name="Central Stores",
            branch_type=BranchType.STORES,
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
            pos_access=True,
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

        self.stores_clerk = User.objects.create_user(username="stores", password="pass")
        StaffProfile.objects.create(
            user=self.stores_clerk,
            branch=self.stores,
            role=StaffRole.STAFF,
        )

        self.branch_manager = User.objects.create_user(
            username="manager", password="pass"
        )
        StaffProfile.objects.create(
            user=self.branch_manager,
            branch=self.stores,
            role=StaffRole.BRANCH_MANAGER,
        )

    def test_bakery_staff_access_flags(self):
        self.assertTrue(user_can_access_bakery_transfers(self.baker))
        self.assertFalse(user_can_access_grv(self.baker))
        self.assertFalse(user_can_access_pos(self.baker))

    def test_stores_staff_access_flags(self):
        self.assertFalse(user_can_access_stores_transfers(self.stores_clerk))
        self.assertTrue(user_can_access_grv(self.stores_clerk))
        self.assertFalse(user_can_access_bakery_transfers(self.stores_clerk))
        self.assertFalse(user_can_access_pos(self.stores_clerk))
        self.assertFalse(user_can_access_stores_transfers(self.branch_manager))
        self.assertTrue(user_is_branch_manager(self.branch_manager))
        self.assertFalse(user_can_access_dashboard(self.branch_manager))
        self.assertFalse(user_can_manage_users(self.branch_manager))

    def test_branch_staff_access_flags(self):
        self.assertFalse(user_can_access_bakery_transfers(self.cashier))
        self.assertFalse(user_can_access_grv(self.cashier))
        self.assertTrue(user_can_access_pos(self.cashier))
        self.assertTrue(user_is_cashier(self.cashier))
        self.assertFalse(user_can_access_management_console(self.cashier))

    def test_hq_staff_access_flags(self):
        self.assertFalse(user_can_access_bakery_transfers(self.hq_staff))
        self.assertTrue(user_can_access_grv(self.hq_staff))
        self.assertFalse(user_can_access_pos(self.hq_staff))
        self.assertTrue(user_is_grv_staff(self.hq_staff))
        self.assertFalse(user_can_access_management_console(self.hq_staff))

    def test_pos_access_can_be_granted_independently_of_branch(self):
        hq_cashier = User.objects.create_user(username="hqcashier", password="pass")
        StaffProfile.objects.create(
            user=hq_cashier,
            branch=self.hq,
            role=StaffRole.CASHIER,
            pos_access=False,
        )
        self.assertTrue(user_can_access_pos(hq_cashier))

    def test_cashier_role_grants_pos_access_without_flag(self):
        cashier = User.objects.create_user(username="nocheck", password="pass")
        StaffProfile.objects.create(
            user=cashier,
            branch=self.hq,
            role=StaffRole.CASHIER,
            pos_access=False,
        )
        self.assertTrue(user_can_access_pos(cashier))

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

    def test_bakery_production_page_requires_bakery_access(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse("ui:bakery-production"))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.baker)
        response = self.client.get(reverse("ui:bakery-production"))
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.hq_admin)
        response = self.client.get(reverse("ui:bakery-production"))
        self.assertEqual(response.status_code, 200)

    def test_stores_transfers_page_requires_stores_access(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse("ui:stores-transfers"))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.stores_clerk)
        response = self.client.get(reverse("ui:stores-transfers"))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.hq_admin)
        response = self.client.get(reverse("ui:stores-transfers"))
        self.assertEqual(response.status_code, 200)

    def test_grv_page_requires_branch_access(self):
        self.client.force_login(self.baker)
        response = self.client.get(reverse("ui:grv"))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.cashier)
        response = self.client.get(reverse("ui:grv"))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.hq_staff)
        response = self.client.get(reverse("ui:grv"))
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.stores_clerk)
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


class PurchaseOrderBranchAccessTests(APITestCase):
    def setUp(self):
        from catalog.models import Product, ProductCategory
        from purchasing.models import PurchaseOrder, Supplier

        self.branch_a = Branch.objects.create(
            name="Branch A",
            branch_type=BranchType.BRANCH,
        )
        self.branch_b = Branch.objects.create(
            name="Branch B",
            branch_type=BranchType.BRANCH,
        )
        self.supplier = Supplier.objects.create(name="Main Supplier")
        category = ProductCategory.objects.create(name="Beverages")
        self.product = Product.objects.create(
            name="Coffee",
            category=category,
            selling_price="3.00",
        )

        self.manager_a = User.objects.create_user(username="manager_a", password="pass")
        StaffProfile.objects.create(
            user=self.manager_a,
            branch=self.branch_a,
            role=StaffRole.BRANCH_MANAGER,
        )

        self.hq_admin = User.objects.create_user(username="hqboss", password="pass")
        StaffProfile.objects.create(
            user=self.hq_admin,
            branch=self.branch_a,
            role=StaffRole.HQ_ADMIN,
        )

        self.po_a = PurchaseOrder.objects.create(
            branch=self.branch_a,
            supplier=self.supplier,
            created_by=self.hq_admin,
        )
        self.po_b = PurchaseOrder.objects.create(
            branch=self.branch_b,
            supplier=self.supplier,
            created_by=self.hq_admin,
        )

        self.po_payload = {
            "branch": self.branch_b.id,
            "supplier": self.supplier.id,
            "notes": "",
            "lines": [
                {
                    "product": self.product.id,
                    "quantity": "1",
                    "unit_cost": "10.00",
                }
            ],
        }

    def test_branch_manager_only_sees_own_purchase_orders(self):
        self.client.force_authenticate(user=self.manager_a)
        response = self.client.get("/api/purchase-orders/")
        po_branches = {row["branch"] for row in response.data["results"]}
        self.assertEqual(po_branches, {self.branch_a.id})

    def test_branch_manager_cannot_filter_other_branch_purchase_orders(self):
        self.client.force_authenticate(user=self.manager_a)
        response = self.client.get(f"/api/purchase-orders/?branch={self.branch_b.id}")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["branch"], self.branch_a.id)

    def test_branch_manager_cannot_create_purchase_for_other_branch(self):
        self.client.force_authenticate(user=self.manager_a)
        response = self.client.post(
            "/api/purchase-orders/", self.po_payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("branch", response.data)

    def test_hq_admin_sees_all_purchase_orders(self):
        self.client.force_authenticate(user=self.hq_admin)
        response = self.client.get("/api/purchase-orders/")
        po_branches = {row["branch"] for row in response.data["results"]}
        self.assertEqual(po_branches, {self.branch_a.id, self.branch_b.id})

    def test_hq_admin_can_create_purchase_for_other_branch(self):
        self.client.force_authenticate(user=self.hq_admin)
        response = self.client.post(
            "/api/purchase-orders/", self.po_payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["branch"], self.branch_b.id)


class KitchenLoginTests(APITestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Main Street",
            branch_type=BranchType.BRANCH,
        )
        self.bakery = Branch.objects.create(
            name="Central Bakery",
            branch_type=BranchType.BAKERY,
        )
        self.kitchen_staff = User.objects.create_user(username="cook", password="secret")
        StaffProfile.objects.create(
            user=self.kitchen_staff,
            branch=self.branch,
            role=StaffRole.STAFF,
        )
        self.baker = User.objects.create_user(username="baker", password="secret")
        StaffProfile.objects.create(
            user=self.baker,
            branch=self.bakery,
            role=StaffRole.BAKER,
        )
        self.login_url = "/api/auth/kitchen-login/"

    def test_kitchen_staff_can_login(self):
        response = self.client.post(
            self.login_url,
            {"username": "cook", "password": "secret"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.data)
        self.assertEqual(response.data["branch"]["id"], self.branch.id)
        self.assertTrue(user_can_access_kitchen(self.kitchen_staff))

    def test_bakery_staff_cannot_login(self):
        response = self.client.post(
            self.login_url,
            {"username": "baker", "password": "secret"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(user_can_access_kitchen(self.baker))


class MobileAppLoginTests(APITestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Main Street",
            branch_type=BranchType.BRANCH,
        )
        self.cashier = User.objects.create_user(username="cashier", password="secret")
        StaffProfile.objects.create(
            user=self.cashier,
            branch=self.branch,
            role=StaffRole.CASHIER,
            pos_access=True,
        )
        self.kitchen_staff = User.objects.create_user(username="cook", password="secret")
        StaffProfile.objects.create(
            user=self.kitchen_staff,
            branch=self.branch,
            role=StaffRole.STAFF,
        )
        self.login_url = "/api/auth/mobile-login/"

    def test_cashier_gets_pos_access(self):
        response = self.client.post(
            self.login_url,
            {"username": "cashier", "password": "secret"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["can_access_pos"])
        self.assertTrue(response.data["can_access_kitchen"])
        self.assertEqual(response.data["user"]["role"], StaffRole.CASHIER)

    def test_kitchen_staff_gets_kitchen_only(self):
        response = self.client.post(
            self.login_url,
            {"username": "cook", "password": "secret"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["can_access_pos"])
        self.assertTrue(response.data["can_access_kitchen"])


class CashierConsoleAccessTests(APITestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
            fiscalization_enabled=True,
        )
        self.non_fiscal_branch = Branch.objects.create(
            name="Borrowdale",
            branch_type=BranchType.BRANCH,
            fiscalization_enabled=False,
        )

        self.cashier = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(
            user=self.cashier,
            branch=self.branch,
            role=StaffRole.CASHIER,
            pos_access=True,
        )

        self.non_fiscal_cashier = User.objects.create_user(
            username="cashier2", password="pass"
        )
        StaffProfile.objects.create(
            user=self.non_fiscal_cashier,
            branch=self.non_fiscal_branch,
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

    def test_cashier_redirected_from_dashboard_to_pos(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse("ui:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ui:pos"))

    def test_cashier_can_access_pos_only_pages(self):
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse("ui:pos")).status_code, 200)
        self.assertEqual(self.client.get(reverse("ui:stock-take")).status_code, 200)
        self.assertEqual(self.client.get(reverse("ui:orders")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ui:products")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ui:expenses")).status_code, 403)

    def test_fiscal_cashier_can_access_invoices_and_receipts(self):
        self.assertTrue(user_can_access_cashier_invoices(self.cashier))
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse("ui:invoices")).status_code, 200)
        self.assertEqual(self.client.get(reverse("ui:receipts")).status_code, 200)

    def test_non_fiscal_cashier_cannot_access_invoices_or_receipts(self):
        self.assertFalse(user_can_access_cashier_invoices(self.non_fiscal_cashier))
        self.assertFalse(user_can_access_fiscal_receipts(self.non_fiscal_cashier))
        self.client.force_login(self.non_fiscal_cashier)
        self.assertEqual(self.client.get(reverse("ui:invoices")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ui:receipts")).status_code, 403)

    def test_branch_manager_retains_operational_console_access(self):
        self.assertFalse(user_is_cashier(self.manager))
        self.assertTrue(user_can_access_management_console(self.manager))
        self.assertFalse(user_can_access_dashboard(self.manager))
        self.client.force_login(self.manager)
        response = self.client.get(reverse("ui:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse("ui:orders")).status_code, 200)


class GrvStaffConsoleAccessTests(APITestCase):
    def setUp(self):
        self.hq = Branch.objects.create(
            name="HQ",
            branch_type=BranchType.HQ,
        )
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )

        self.grv_staff = User.objects.create_user(username="hqstaff", password="pass")
        StaffProfile.objects.create(
            user=self.grv_staff,
            branch=self.hq,
            role=StaffRole.STAFF,
        )

        self.manager = User.objects.create_user(username="manager", password="pass")
        StaffProfile.objects.create(
            user=self.manager,
            branch=self.branch,
            role=StaffRole.BRANCH_MANAGER,
        )

    def test_grv_staff_redirected_from_dashboard_to_grv(self):
        self.client.force_login(self.grv_staff)
        response = self.client.get(reverse("ui:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ui:grv"))

    def test_grv_staff_can_access_grv_only(self):
        self.client.force_login(self.grv_staff)
        self.assertEqual(self.client.get(reverse("ui:grv")).status_code, 200)
        self.assertEqual(self.client.get(reverse("ui:kitchen")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ui:orders")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ui:pos")).status_code, 403)

    def test_branch_manager_retains_operational_console_access(self):
        self.assertFalse(user_is_grv_staff(self.manager))
        self.assertTrue(user_can_access_management_console(self.manager))
        self.assertFalse(user_can_access_dashboard(self.manager))
        self.client.force_login(self.manager)
        response = self.client.get(reverse("ui:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse("ui:grv")).status_code, 200)


class BranchManagerConsoleAccessTests(APITestCase):
    def setUp(self):
        self.stores = Branch.objects.create(
            name="Central Stores",
            branch_type=BranchType.STORES,
        )
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )

        self.manager = User.objects.create_user(username="manager", password="pass")
        StaffProfile.objects.create(
            user=self.manager,
            branch=self.branch,
            role=StaffRole.BRANCH_MANAGER,
            pos_access=True,
        )

        self.hq_admin = User.objects.create_user(username="hqboss", password="pass")
        StaffProfile.objects.create(
            user=self.hq_admin,
            branch=self.branch,
            role=StaffRole.HQ_ADMIN,
        )

    def test_branch_manager_cannot_access_dashboard_users_or_stores_transfers(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("ui:dashboard")).status_code, 302)
        self.assertEqual(self.client.get(reverse("ui:users")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ui:stores-transfers")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ui:pos")).status_code, 200)

    def test_hq_admin_keeps_dashboard_users_and_stores_transfers(self):
        self.client.force_login(self.hq_admin)
        self.assertEqual(self.client.get(reverse("ui:dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("ui:users")).status_code, 200)
        self.assertEqual(self.client.get(reverse("ui:stores-transfers")).status_code, 200)
