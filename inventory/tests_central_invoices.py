from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile, StaffRole
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from customers.models import Customer
from inventory.models import BranchInventory, CentralInvoice, TransferInvoicePaymentStatus

User = get_user_model()


class CentralInvoiceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.stores = Branch.objects.create(
            name="Central Stores",
            branch_type=BranchType.STORES,
            code="STR",
        )
        self.hq = Branch.objects.create(name="HQ", branch_type=BranchType.HQ)
        self.stores_user = User.objects.create_user(username="stores", password="pass")
        StaffProfile.objects.create(
            user=self.stores_user,
            branch=self.hq,
            role=StaffRole.HQ_ADMIN,
        )
        self.customer = Customer.objects.create(
            first_name="Wholesale",
            last_name="Buyer",
            phone="0777123456",
        )
        category = ProductCategory.objects.create(name="Breads & pastries")
        self.croissant = Product.objects.create(
            name="Croissant",
            category=category,
            selling_price=Decimal("2.75"),
        )
        BranchInventory.objects.create(
            branch=self.stores,
            product=self.croissant,
            quantity=Decimal("50"),
        )

    def test_create_central_invoice_deducts_stores_stock(self):
        self.client.force_authenticate(user=self.stores_user)
        response = self.client.post(
            "/api/central-invoices/",
            {
                "from_branch": self.stores.id,
                "customer": self.customer.id,
                "lines": [{"product": self.croissant.id, "quantity": "10"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["invoice_number"].startswith("CISTR"))
        self.assertEqual(response.data["status"], "dispatched")
        self.assertEqual(response.data["payment_status"], "unpaid")

        stores_stock = BranchInventory.objects.get(
            branch=self.stores,
            product=self.croissant,
        )
        self.assertEqual(stores_stock.quantity, Decimal("40"))

    def test_mark_paid_and_cancel(self):
        self.client.force_authenticate(user=self.stores_user)
        create_response = self.client.post(
            "/api/central-invoices/",
            {
                "from_branch": self.stores.id,
                "customer": self.customer.id,
                "lines": [{"product": self.croissant.id, "quantity": "5"}],
            },
            format="json",
        )
        invoice_id = create_response.data["id"]

        paid_response = self.client.post(f"/api/central-invoices/{invoice_id}/mark-paid/")
        self.assertEqual(paid_response.status_code, 200)
        self.assertEqual(paid_response.data["payment_status"], TransferInvoicePaymentStatus.PAID)

        invoice = CentralInvoice.objects.get(pk=invoice_id)
        self.assertEqual(invoice.paid_by, self.stores_user)

    def test_cancel_restores_stock(self):
        self.client.force_authenticate(user=self.stores_user)
        create_response = self.client.post(
            "/api/central-invoices/",
            {
                "from_branch": self.stores.id,
                "customer": self.customer.id,
                "lines": [{"product": self.croissant.id, "quantity": "8"}],
            },
            format="json",
        )
        invoice_id = create_response.data["id"]

        cancel_response = self.client.post(f"/api/central-invoices/{invoice_id}/cancel/")
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.data["status"], "cancelled")

        stores_stock = BranchInventory.objects.get(
            branch=self.stores,
            product=self.croissant,
        )
        self.assertEqual(stores_stock.quantity, Decimal("50"))
