from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import StaffProfile, StaffRole
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from inventory.models import BranchInventory
from purchasing.models import PurchaseOrder, PurchaseOrderStatus, Supplier
from purchasing.services import InvalidPurchaseOrderStateError, receive_purchase_order


User = get_user_model()


class PurchaseOrderDraftFlowTests(APITestCase):
    def setUp(self):
        self.stores = Branch.objects.create(
            name="Central Stores",
            branch_type=BranchType.STORES,
        )
        self.supplier = Supplier.objects.create(name="Dairy Co")
        category = ProductCategory.objects.create(name="Ingredients")
        self.product = Product.objects.create(
            name="Milk",
            category=category,
            selling_price=Decimal("2.00"),
        )
        self.hq = User.objects.create_user(username="hq", password="pass")
        StaffProfile.objects.create(
            user=self.hq,
            branch=self.stores,
            role=StaffRole.HQ_ADMIN,
        )
        self.payload = {
            "branch": self.stores.id,
            "supplier": self.supplier.id,
            "notes": "INV-1",
            "lines": [
                {
                    "product": self.product.id,
                    "quantity": "4",
                    "unit_cost": "3.00",
                }
            ],
        }

    def test_create_as_draft_does_not_add_stock(self):
        self.client.force_authenticate(user=self.hq)
        response = self.client.post(
            "/api/purchase-orders/",
            {**self.payload, "as_draft": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], PurchaseOrderStatus.DRAFT)
        self.assertFalse(
            BranchInventory.objects.filter(
                branch=self.stores, product=self.product
            ).exists()
        )

    def test_create_without_as_draft_receives_and_adds_stock(self):
        self.client.force_authenticate(user=self.hq)
        response = self.client.post(
            "/api/purchase-orders/",
            self.payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], PurchaseOrderStatus.RECEIVED)
        inv = BranchInventory.objects.get(branch=self.stores, product=self.product)
        self.assertEqual(inv.quantity, Decimal("4.0000"))

    def test_receive_draft_adds_stock(self):
        self.client.force_authenticate(user=self.hq)
        created = self.client.post(
            "/api/purchase-orders/",
            {**self.payload, "as_draft": True},
            format="json",
        )
        po_id = created.data["id"]
        response = self.client.post(f"/api/purchase-orders/{po_id}/receive/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], PurchaseOrderStatus.RECEIVED)
        inv = BranchInventory.objects.get(branch=self.stores, product=self.product)
        self.assertEqual(inv.quantity, Decimal("4.0000"))

    def test_cancel_draft(self):
        self.client.force_authenticate(user=self.hq)
        created = self.client.post(
            "/api/purchase-orders/",
            {**self.payload, "as_draft": True},
            format="json",
        )
        po_id = created.data["id"]
        response = self.client.post(f"/api/purchase-orders/{po_id}/cancel/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], PurchaseOrderStatus.CANCELLED)

    def test_receive_empty_draft_fails(self):
        po = PurchaseOrder.objects.create(
            branch=self.stores,
            supplier=self.supplier,
            status=PurchaseOrderStatus.DRAFT,
            created_by=self.hq,
        )
        with self.assertRaises(InvalidPurchaseOrderStateError):
            receive_purchase_order(po)
