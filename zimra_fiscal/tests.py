from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from accounts.models import StaffProfile, StaffRole
from orders.models import FiscalApprovalStatus, Order, OrderStatus
from payments.models import Currency, CurrencyRate
from zimra_fiscal.client import (
    build_device_action_url,
    build_submit_url,
    call_device_api,
    resolve_device_id,
)
from zimra_fiscal.fiscal_day import normalize_fiscal_day_status
from zimra_fiscal.models import FiscalReceipt, FiscalReceiptStatus
from zimra_fiscal.receipt import build_fiscal_receipt_payload
from zimra_fiscal.response import apply_zimra_response, parse_zimra_response_body
from zimra_fiscal.services import (
    allocate_fiscal_receipt_number,
    create_fiscal_receipt_for_payment,
)


class FiscalReceiptBuilderTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Avondale",
            code="AVO",
            branch_type=BranchType.BRANCH,
            fiscalization_enabled=True,
        )
        category = ProductCategory.objects.create(name="Drinks")
        self.product_a = Product.objects.create(
            name="Espresso",
            category=category,
            selling_price=Decimal("4.52"),
            tax_rate=Decimal("15.50"),
            hs_code="12345678",
            fiscal_tax_code="E",
            fiscal_tax_id=517,
        )
        self.product_b = Product.objects.create(
            name="Water",
            category=category,
            selling_price=Decimal("6.00"),
            tax_rate=Decimal("0"),
            fiscal_tax_code="B",
            fiscal_tax_id=2,
        )
        self.usd = Currency.objects.create(
            code="USD",
            name="US Dollar",
            symbol="$",
            is_base=True,
        )
        CurrencyRate.objects.create(
            currency=self.usd,
            rate=Decimal("1"),
            effective_from="2026-01-01",
        )
        self.order = Order.objects.create(
            branch=self.branch,
            status=OrderStatus.PAID,
            payment_currency=self.usd,
            exchange_rate=Decimal("1"),
            amount_paid=Decimal("38.10"),
            total_amount=Decimal("34.60"),
            receipt_number="AVO0906261",
        )
        self.order.items.create(
            product=self.product_a,
            quantity=Decimal("5"),
            price=Decimal("4.52"),
        )
        self.order.items.create(
            product=self.product_b,
            quantity=Decimal("2"),
            price=Decimal("6.00"),
        )

    def test_build_payload_shape(self):
        payload = build_fiscal_receipt_payload(
            self.order,
            receipt_counter=5,
            receipt_global_no=31,
            invoice_no="240247513",
        )

        receipt = payload["receipt"]
        self.assertEqual(receipt["receiptType"], "FiscalInvoice")
        self.assertEqual(receipt["receiptCurrency"], "USD")
        self.assertEqual(receipt["receiptCounter"], 5)
        self.assertEqual(receipt["receiptGlobalNo"], 31)
        self.assertEqual(receipt["invoiceNo"], "240247513")
        self.assertFalse(receipt["receiptLinesTaxInclusive"])
        self.assertEqual(len(receipt["receiptLines"]), 2)
        self.assertEqual(receipt["receiptLines"][0]["taxCode"], "E")
        self.assertEqual(receipt["receiptLines"][0]["receiptLinePrice"], 3.91)
        self.assertEqual(receipt["receiptLines"][0]["receiptLineTotal"], 19.55)
        self.assertEqual(receipt["receiptLines"][1]["taxCode"], "B")
        self.assertEqual(receipt["receiptLines"][1]["receiptLinePrice"], 6.0)
        self.assertEqual(receipt["receiptPayments"][0]["moneyTypeCode"], "Cash")
        self.assertEqual(receipt["receiptTotal"], 34.58)

    def test_tax_exclusive_line_prices(self):
        category = ProductCategory.objects.create(name="Pastries")
        muffin_product = Product.objects.create(
            name="Muffin",
            category=category,
            selling_price=Decimal("2.75"),
            tax_rate=Decimal("15.50"),
            fiscal_tax_code="E",
            fiscal_tax_id=517,
        )
        muffin_order = Order.objects.create(
            branch=self.branch,
            status=OrderStatus.PAID,
            payment_currency=self.usd,
            exchange_rate=Decimal("1"),
            amount_paid=Decimal("8.25"),
            total_amount=Decimal("8.25"),
            receipt_number="AVO0906262",
        )
        muffin_order.items.create(
            product=muffin_product,
            quantity=Decimal("3"),
            price=Decimal("2.75"),
        )
        muffin_payload = build_fiscal_receipt_payload(
            muffin_order,
            receipt_counter=2,
            receipt_global_no=2,
            invoice_no="AVO0906262",
        )
        line = muffin_payload["receipt"]["receiptLines"][0]
        self.assertEqual(line["receiptLinePrice"], 2.38)
        self.assertEqual(line["receiptLineTotal"], 7.14)
        self.assertEqual(muffin_payload["receipt"]["receiptTotal"], 8.25)

    @patch("zimra_fiscal.services.submit_receipt_payload")
    @patch("zimra_fiscal.services.timezone.localdate")
    def test_create_fiscal_receipt_increments_counters(self, mock_localdate, mock_submit):
        mock_localdate.return_value = timezone.datetime(2026, 6, 9).date()
        mock_submit.return_value = {
            "status_code": 200,
            "body": {
                "deviceBranchName": "Cafe Avondale",
                "deviceSerialNo": "SN-12345",
                "fiscalDayNumber": 12,
                "invoiceNumber": "FAVO0906261",
                "qrString": "ABC-VERIFY",
                "qrUrl": "https://fdms.zimra.co.zw/qr/abc",
                "receiptCounter": 5,
                "receiptGlobalNo": 31,
                "verificationCode": "A1B2-C3D4",
            },
        }
        fiscal_receipt = create_fiscal_receipt_for_payment(self.order)
        self.assertEqual(fiscal_receipt.receipt_counter, 5)
        self.assertEqual(fiscal_receipt.receipt_global_no, 31)
        self.assertEqual(fiscal_receipt.invoice_no, "FAVO0906261")
        self.assertNotEqual(fiscal_receipt.invoice_no, self.order.receipt_number)
        self.assertEqual(
            fiscal_receipt.payload["receipt"]["invoiceNo"],
            "FAVO0906261",
        )
        self.assertIn("receipt", fiscal_receipt.payload)
        self.assertEqual(fiscal_receipt.status, FiscalReceiptStatus.ACCEPTED)
        self.assertEqual(fiscal_receipt.device_branch_name, "Cafe Avondale")
        self.assertEqual(fiscal_receipt.fiscal_invoice_number, "FAVO0906261")
        self.assertEqual(fiscal_receipt.verification_code, "A1B2-C3D4")
        mock_submit.assert_called_once()

    @patch("zimra_fiscal.services.timezone.localdate")
    def test_fiscal_receipt_number_sequence_is_independent(self, mock_localdate):
        mock_localdate.return_value = timezone.datetime(2026, 6, 9).date()
        first = allocate_fiscal_receipt_number(self.branch)
        second = allocate_fiscal_receipt_number(self.branch)
        self.assertEqual(first, "FAVO0906261")
        self.assertEqual(second, "FAVO0906262")
        self.assertTrue(first.startswith("F"))
        self.assertNotEqual(first, self.order.receipt_number)


class ZimraResponseParserTests(TestCase):
    def test_parse_flat_response(self):
        parsed = parse_zimra_response_body(
            {
                "deviceBranchName": "Branch A",
                "verificationCode": "XYZ",
                "receiptCounter": "7",
            }
        )
        self.assertEqual(parsed["device_branch_name"], "Branch A")
        self.assertEqual(parsed["verification_code"], "XYZ")
        self.assertEqual(parsed["receipt_counter"], 7)

    def test_parse_nested_response(self):
        parsed = parse_zimra_response_body(
            {
                "data": {
                    "invoiceNumber": "998877",
                    "fiscalDayNumber": 3,
                }
            }
        )
        self.assertEqual(parsed["fiscal_invoice_number"], "998877")
        self.assertEqual(parsed["fiscal_day_number"], 3)

    def test_apply_zimra_response_updates_fiscal_receipt(self):
        branch = Branch.objects.create(name="Test", branch_type=BranchType.BRANCH)
        order = Order.objects.create(branch=branch, status=OrderStatus.PAID)
        fiscal_receipt = FiscalReceipt.objects.create(
            order=order,
            branch=branch,
            receipt_counter=1,
            receipt_global_no=1,
            invoice_no="0100000001",
            payload={"receipt": {}},
        )
        apply_zimra_response(
            fiscal_receipt,
            {
                "status_code": 200,
                "body": {"verificationCode": "DONE-123", "qrUrl": "https://example.com/qr"},
            },
        )
        fiscal_receipt.refresh_from_db()
        self.assertEqual(fiscal_receipt.verification_code, "DONE-123")
        self.assertEqual(fiscal_receipt.qr_url, "https://example.com/qr")
        self.assertEqual(fiscal_receipt.status, FiscalReceiptStatus.ACCEPTED)


class ZimraClientTests(TestCase):
    @override_settings(
        ZIMRA_FISCAL_BASE_URL="http://192.168.100.8:5008",
        ZIMRA_DEFAULT_DEVICE_ID="30541",
    )
    def test_build_submit_url(self):
        self.assertEqual(
            build_submit_url("30541"),
            "http://192.168.100.8:5008/api/submit_receipt/30541",
        )

    @override_settings(ZIMRA_FISCAL_BASE_URL="http://192.168.100.8:5008")
    def test_build_device_action_url(self):
        self.assertEqual(
            build_device_action_url("30541", "close_day"),
            "http://192.168.100.8:5008/api/close_day/30541",
        )

    @override_settings(ZIMRA_DEFAULT_DEVICE_ID="30541")
    def test_resolve_device_id_prefers_branch_value(self):
        branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
            zimra_device_id="99999",
        )
        self.assertEqual(resolve_device_id(branch), "99999")

    @override_settings(ZIMRA_DEFAULT_DEVICE_ID="30541")
    def test_resolve_device_id_falls_back_to_default(self):
        branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        self.assertEqual(resolve_device_id(branch), "30541")


class FiscalDayStatusTests(TestCase):
    def test_normalize_fiscal_day_status(self):
        normalized = normalize_fiscal_day_status(
            {
                "status_code": 200,
                "body": {
                    "fiscalDayStatus": "FiscalDayOpened",
                    "lastFiscalDayNo": 12,
                    "lastReceiptGlobalNo": 44,
                },
            }
        )
        self.assertEqual(normalized["fiscal_day_status"], "FiscalDayOpened")
        self.assertEqual(normalized["fiscal_day_number"], 12)
        self.assertEqual(normalized["last_receipt_global_no"], 44)
        self.assertTrue(normalized["can_close_day"])
        self.assertFalse(normalized["can_open_day"])

    def test_normalize_closed_day(self):
        normalized = normalize_fiscal_day_status(
            {
                "status_code": 200,
                "body": {"fiscalDayStatus": "FiscalDayClosed", "lastFiscalDayNo": 11},
            }
        )
        self.assertTrue(normalized["can_open_day"])
        self.assertFalse(normalized["can_close_day"])


class BranchFiscalDayApiTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.client = APIClient()
        self.branch = Branch.objects.create(
            name="Fiscal Branch",
            code="FIS",
            branch_type=BranchType.BRANCH,
            fiscalization_enabled=True,
            zimra_device_id="30541",
        )
        self.manager = User.objects.create_user(username="fiscalmgr", password="pass")
        StaffProfile.objects.create(
            user=self.manager,
            branch=self.branch,
            role=StaffRole.BRANCH_MANAGER,
            pos_access=True,
        )
        self.client.force_authenticate(self.manager)

    @patch("branches.views.get_fiscal_day_status")
    def test_fiscal_day_status_endpoint(self, mock_status):
        mock_status.return_value = {
            "branch_id": self.branch.id,
            "branch_name": self.branch.name,
            "device_id": "30541",
            "fiscal_day_status": "FiscalDayOpened",
            "fiscal_day_number": 3,
            "can_open_day": False,
            "can_close_day": True,
        }
        response = self.client.get(f"/api/branches/{self.branch.id}/fiscal-day/status/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["fiscal_day_status"], "FiscalDayOpened")
        mock_status.assert_called_once()

    @patch("branches.views.open_fiscal_day")
    def test_fiscal_day_open_endpoint(self, mock_open):
        mock_open.return_value = {
            "branch_id": self.branch.id,
            "fiscal_day_status": "FiscalDayOpened",
            "fiscal_day_number": 4,
            "can_open_day": False,
            "can_close_day": True,
        }
        response = self.client.post(
            f"/api/branches/{self.branch.id}/fiscal-day/open/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        mock_open.assert_called_once()

    @patch("branches.views.close_fiscal_day")
    def test_fiscal_day_close_endpoint(self, mock_close):
        mock_close.return_value = {
            "branch_id": self.branch.id,
            "operation_id": "ABC:1",
            "can_open_day": False,
            "can_close_day": False,
        }
        response = self.client.post(
            f"/api/branches/{self.branch.id}/fiscal-day/close/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        mock_close.assert_called_once()

    @patch("branches.views.get_fiscal_day_status")
    def test_cashier_can_access_fiscal_day_status(self, mock_status):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        cashier = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(
            user=cashier,
            branch=self.branch,
            role=StaffRole.CASHIER,
            pos_access=True,
        )
        mock_status.return_value = {
            "branch_id": self.branch.id,
            "fiscal_day_status": "FiscalDayClosed",
            "can_open_day": True,
            "can_close_day": False,
        }
        self.client.force_authenticate(cashier)
        response = self.client.get(f"/api/branches/{self.branch.id}/fiscal-day/status/")
        self.assertEqual(response.status_code, 200)
        mock_status.assert_called_once()


class OrderPayFiscalizationTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.client = APIClient()
        self.branch = Branch.objects.create(
            name="Fiscal Branch",
            code="FIS",
            branch_type=BranchType.BRANCH,
            fiscalization_enabled=True,
        )
        self.manager = User.objects.create_user(username="manager", password="pass")
        StaffProfile.objects.create(
            user=self.manager,
            branch=self.branch,
            role=StaffRole.BRANCH_MANAGER,
            pos_access=True,
        )
        category = ProductCategory.objects.create(name="Coffee")
        product = Product.objects.create(
            name="Latte",
            category=category,
            selling_price=Decimal("4.00"),
            tax_rate=Decimal("15.50"),
            fiscal_tax_code="E",
            fiscal_tax_id=517,
        )
        self.usd = Currency.objects.create(
            code="USD",
            name="US Dollar",
            symbol="$",
            is_base=True,
        )
        CurrencyRate.objects.create(
            currency=self.usd,
            rate=Decimal("1"),
            effective_from="2026-01-01",
        )
        self.order = Order.objects.create(branch=self.branch)
        self.order.items.create(
            product=product,
            quantity=Decimal("1"),
            price=Decimal("4.00"),
        )
        self.order.recalculate_total()
        self.client.force_authenticate(self.manager)

    def test_pay_creates_proforma_when_fiscal_enabled(self):
        response = self.client.post(
            f"/api/orders/{self.order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("fiscal_receipt", response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertEqual(
            self.order.fiscal_approval_status,
            FiscalApprovalStatus.PENDING,
        )
        self.assertFalse(FiscalReceipt.objects.filter(order=self.order).exists())

    @patch("zimra_fiscal.services.submit_receipt_payload")
    @patch("zimra_fiscal.services.timezone.localdate")
    def test_approve_fiscal_submits_receipt(self, mock_localdate, mock_submit):
        mock_localdate.return_value = timezone.datetime(2026, 6, 9).date()
        mock_submit.return_value = {
            "status_code": 200,
            "body": {"verificationCode": "DONE-123"},
        }
        self.client.post(
            f"/api/orders/{self.order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.client.force_authenticate(self.manager)
        response = self.client.post(
            f"/api/orders/{self.order.id}/approve-fiscal/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("fiscal_receipt", response.data)
        self.assertEqual(
            response.data["fiscal_receipt"]["receipt"]["receiptType"],
            "FiscalInvoice",
        )
        self.assertTrue(response.data["fiscal_receipt_number"].startswith("FFIS"))
        self.assertNotEqual(
            response.data["fiscal_receipt_number"],
            response.data["receipt_number"],
        )
        self.assertTrue(FiscalReceipt.objects.filter(order=self.order).exists())
        self.order.refresh_from_db()
        self.assertEqual(
            self.order.fiscal_approval_status,
            FiscalApprovalStatus.APPROVED,
        )
        mock_submit.assert_called_once()

    @patch("zimra_fiscal.services.submit_receipt_payload")
    def test_approve_fiscal_keeps_proforma_when_zimra_fails(self, mock_submit):
        from zimra_fiscal.exceptions import ZimraSubmissionError

        mock_submit.side_effect = ZimraSubmissionError("Device offline")
        self.client.post(
            f"/api/orders/{self.order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.client.force_authenticate(self.manager)
        response = self.client.post(
            f"/api/orders/{self.order.id}/approve-fiscal/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 502)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertEqual(
            self.order.fiscal_approval_status,
            FiscalApprovalStatus.PENDING,
        )

    def test_pay_skips_fiscal_receipt_when_disabled(self):
        self.branch.fiscalization_enabled = False
        self.branch.save(update_fields=["fiscalization_enabled"])

        response = self.client.post(
            f"/api/orders/{self.order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("fiscal_receipt", response.data)
        self.assertFalse(FiscalReceipt.objects.filter(order=self.order).exists())
