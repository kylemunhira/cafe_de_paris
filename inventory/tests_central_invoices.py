from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile, StaffRole
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from customers.models import Customer
from inventory.models import (
    BranchInventory,
    CentralInvoice,
    CentralInvoicePayment,
    TransferInvoicePaymentStatus,
)
from payments.models import Currency

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
        self.usd = Currency.objects.create(
            code="USD",
            name="US Dollar",
            symbol="$",
            is_base=True,
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

    def _create_invoice(self, quantity="5"):
        response = self.client.post(
            "/api/central-invoices/",
            {
                "from_branch": self.stores.id,
                "customer": self.customer.id,
                "lines": [{"product": self.croissant.id, "quantity": quantity}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        return response.data["id"], response.data

    def test_create_central_invoice_deducts_stores_stock(self):
        self.client.force_authenticate(user=self.stores_user)
        _invoice_id, data = self._create_invoice(quantity="10")
        self.assertTrue(data["invoice_number"].startswith("CISTR"))
        self.assertEqual(data["status"], "dispatched")
        self.assertEqual(data["payment_status"], "unpaid")

        stores_stock = BranchInventory.objects.get(
            branch=self.stores,
            product=self.croissant,
        )
        self.assertEqual(stores_stock.quantity, Decimal("40"))

    def test_record_payment_and_cancel(self):
        self.client.force_authenticate(user=self.stores_user)
        invoice_id, created = self._create_invoice()
        invoice_total = Decimal(created["total_amount"])

        paid_response = self.client.post(
            f"/api/central-invoices/{invoice_id}/record-payment/",
            {
                "payments": [
                    {
                        "currency_id": self.usd.id,
                        "amount": str(invoice_total),
                    }
                ],
                "payment_reference": "BNK-12345",
            },
            format="json",
        )
        self.assertEqual(paid_response.status_code, 200)
        self.assertEqual(
            paid_response.data["payment_status"], TransferInvoicePaymentStatus.PAID
        )
        self.assertEqual(len(paid_response.data["payments"]), 1)
        self.assertEqual(paid_response.data["payment_reference"], "BNK-12345")

        invoice = CentralInvoice.objects.get(pk=invoice_id)
        self.assertEqual(invoice.paid_by, self.stores_user)
        self.assertEqual(
            CentralInvoicePayment.objects.filter(central_invoice=invoice).count(),
            1,
        )

    def test_record_payment_rejects_insufficient_tender(self):
        self.client.force_authenticate(user=self.stores_user)
        invoice_id, created = self._create_invoice()

        response = self.client.post(
            f"/api/central-invoices/{invoice_id}/record-payment/",
            {
                "payments": [
                    {
                        "currency_id": self.usd.id,
                        "amount": "1.00",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.data)

    def test_mark_paid_requires_payment_details(self):
        self.client.force_authenticate(user=self.stores_user)
        invoice_id, _created = self._create_invoice()

        response = self.client.post(f"/api/central-invoices/{invoice_id}/mark-paid/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("record-payment", response.data["detail"])

    def test_cancel_restores_stock(self):
        self.client.force_authenticate(user=self.stores_user)
        invoice_id, _created = self._create_invoice(quantity="8")

        cancel_response = self.client.post(f"/api/central-invoices/{invoice_id}/cancel/")
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.data["status"], "cancelled")

        stores_stock = BranchInventory.objects.get(
            branch=self.stores,
            product=self.croissant,
        )
        self.assertEqual(stores_stock.quantity, Decimal("50"))
