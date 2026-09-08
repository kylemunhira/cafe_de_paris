from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile, StaffRole
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from orders.models import FiscalApprovalStatus, Order, OrderItem, OrderStatus, OrderType
from orders.tax import split_inclusive_total
from payments.models import Currency, CurrencyRate
from purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, Supplier
from reports.vat import build_vat_report

User = get_user_model()


class VATReportTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.ui_client = Client()
        self.usd = Currency.objects.create(
            code="USD",
            name="US Dollar",
            symbol="$",
            is_base=True,
        )
        self.zwg = Currency.objects.create(
            code="ZWG",
            name="ZiG",
            symbol="ZiG",
        )
        CurrencyRate.objects.create(
            currency=self.zwg,
            rate=Decimal("25.50"),
            effective_from=timezone.localdate(),
        )
        self.branch = Branch.objects.create(
            name="Highland",
            code="HIG",
            branch_type=BranchType.BRANCH,
            fiscalization_enabled=True,
        )
        self.bakery = Branch.objects.create(
            name="Bakery",
            branch_type=BranchType.BAKERY,
        )
        self.category = ProductCategory.objects.create(name="Coffee")
        self.ingredients = ProductCategory.objects.create(name="Ingredients")
        self.product = Product.objects.create(
            name="Espresso",
            category=self.category,
            selling_price=Decimal("67.00"),
            tax_rate=Decimal("15.5"),
        )
        self.flour = Product.objects.create(
            name="Flour",
            category=self.ingredients,
            selling_price=Decimal("0"),
            tax_rate=Decimal("15.5"),
        )
        self.supplier = Supplier.objects.create(
            name="VAT Supplier",
            vat_number="1000123456",
        )
        self.user = User.objects.create_user(username="fiscal", password="pass")
        StaffProfile.objects.create(
            user=self.user,
            branch=self.branch,
            role=StaffRole.BRANCH_MANAGER,
            pos_access=True,
        )
        self.client.force_authenticate(user=self.user)
        self.ui_client.force_login(self.user)

        now = timezone.now()
        self.order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("67.00"),
            payment_currency=self.usd,
            exchange_rate=Decimal("1"),
            amount_paid=Decimal("67.00"),
            paid_at=now,
            fiscal_approval_status=FiscalApprovalStatus.APPROVED,
            fiscal_approved_at=now,
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=Decimal("1"),
            price=Decimal("67.00"),
        )

        self.purchase_order = PurchaseOrder.objects.create(
            branch=self.branch,
            supplier=self.supplier,
            status=PurchaseOrderStatus.RECEIVED,
            received_at=now,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=self.purchase_order,
            product=self.flour,
            quantity=Decimal("2"),
            unit_cost=Decimal("11.60"),
        )

    def test_vat_report_output_tax_from_fiscalized_sales(self):
        today = timezone.localdate()
        report = build_vat_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            branch_id=self.branch.id,
        )
        expected = split_inclusive_total(Decimal("67.00"), Decimal("15.5"))
        self.assertEqual(
            report["output_tax"]["total_sales_including_vat"],
            expected["total"],
        )
        self.assertEqual(
            report["output_tax"]["vat_on_taxable_sales"],
            expected["tax"],
        )
        self.assertEqual(report["meta"]["fiscalized_sales_count"], 1)

    def test_vat_report_input_tax_from_vat_supplier_purchases(self):
        today = timezone.localdate()
        report = build_vat_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            branch_id=self.branch.id,
        )
        line_total = Decimal("23.20")
        expected = split_inclusive_total(line_total, Decimal("15.5"))
        self.assertEqual(
            report["input_tax"]["total_purchases_including_vat"],
            expected["total"],
        )
        self.assertEqual(
            report["input_tax"]["total_raw_materials_including_vat"],
            expected["total"],
        )
        self.assertEqual(report["meta"]["vat_purchase_order_count"], 1)

    def test_vat_report_excludes_non_fiscal_sales(self):
        Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("50.00"),
            paid_at=timezone.now(),
        )
        today = timezone.localdate()
        report = build_vat_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            branch_id=self.branch.id,
        )
        self.assertEqual(report["meta"]["fiscalized_sales_count"], 1)

    def test_vat_report_excludes_proforma_pending(self):
        Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("50.00"),
            paid_at=timezone.now(),
            fiscal_approval_status=FiscalApprovalStatus.PENDING,
        )
        today = timezone.localdate()
        report = build_vat_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            branch_id=self.branch.id,
        )
        self.assertEqual(report["meta"]["fiscalized_sales_count"], 1)
        self.assertEqual(
            report["output_tax"]["total_sales_including_vat"],
            split_inclusive_total(Decimal("67.00"), Decimal("15.5"))["total"],
        )

    def test_vat_report_uses_fiscal_approved_date_not_paid_date(self):
        now = timezone.now()
        approved_order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("20.00"),
            payment_currency=self.usd,
            exchange_rate=Decimal("1"),
            amount_paid=Decimal("20.00"),
            paid_at=now,
            fiscal_approval_status=FiscalApprovalStatus.APPROVED,
            fiscal_approved_at=now,
        )
        OrderItem.objects.create(
            order=approved_order,
            product=self.product,
            quantity=Decimal("1"),
            price=Decimal("20.00"),
        )

        old_approved = timezone.now() - timedelta(days=40)
        self.order.fiscal_approved_at = old_approved
        self.order.paid_at = old_approved
        self.order.save(update_fields=["fiscal_approved_at", "paid_at"])

        today = timezone.localdate()
        report = build_vat_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            branch_id=self.branch.id,
        )
        self.assertEqual(report["meta"]["fiscalized_sales_count"], 1)
        self.assertEqual(
            report["output_tax"]["total_sales_including_vat"],
            split_inclusive_total(Decimal("20.00"), Decimal("15.5"))["total"],
        )

    def test_vat_report_excludes_suppliers_without_vat_number(self):
        supplier = Supplier.objects.create(name="No VAT Supplier")
        PurchaseOrder.objects.create(
            branch=self.branch,
            supplier=supplier,
            status=PurchaseOrderStatus.RECEIVED,
            received_at=timezone.now(),
        )
        today = timezone.localdate()
        report = build_vat_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            branch_id=self.branch.id,
        )
        self.assertEqual(report["meta"]["vat_purchase_order_count"], 1)

    def test_vat_report_rejects_non_physical_branch(self):
        today = timezone.localdate()
        with self.assertRaises(ValueError):
            build_vat_report(
                from_date=today.isoformat(),
                to_date=today.isoformat(),
                branch_id=self.bakery.id,
            )

    def test_vat_report_api(self):
        today = timezone.localdate()
        response = self.client.get(
            f"/api/reports/vat/?from={today.isoformat()}&to={today.isoformat()}&branch={self.branch.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("output_tax", response.data)
        self.assertIn("net_vat", response.data)

    def test_vat_report_page(self):
        response = self.ui_client.get("/reports/vat/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "VAT Report")
        self.assertContains(response, "Output TAX Amount")
        self.assertContains(response, "filter-currency")

    def test_vat_report_currency_usd_paid_only(self):
        today = timezone.localdate()
        now = timezone.now()
        zwg_order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("10.00"),
            payment_currency=self.zwg,
            exchange_rate=Decimal("25.50"),
            amount_paid=Decimal("255.00"),
            paid_at=now,
            fiscal_approval_status=FiscalApprovalStatus.APPROVED,
            fiscal_approved_at=now,
        )
        OrderItem.objects.create(
            order=zwg_order,
            product=self.product,
            quantity=Decimal("1"),
            price=Decimal("10.00"),
        )

        report = build_vat_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            branch_id=self.branch.id,
            currency="usd",
        )
        self.assertEqual(report["currency"]["mode"], "usd")
        self.assertEqual(report["currency"]["basis"], "payment_currency")
        self.assertIn("USD", report["amounts_by_currency"])
        self.assertNotIn("ZWG", report["amounts_by_currency"])
        expected = split_inclusive_total(Decimal("67.00"), Decimal("15.5"))
        self.assertEqual(
            report["amounts_by_currency"]["USD"]["output_tax"]["total_sales_including_vat"],
            expected["total"],
        )
        self.assertEqual(report["amounts_by_currency"]["USD"]["sales_count"], 1)
        self.assertEqual(report["meta"]["usd_paid_fiscalized_sales_count"], 1)
        self.assertEqual(report["meta"]["zwg_paid_fiscalized_sales_count"], 1)

    def test_vat_report_currency_zwg_paid_uses_order_rate_not_current_fx(self):
        today = timezone.localdate()
        now = timezone.now()
        # Current rate is 25.50; this sale used 20 at payment time.
        zwg_order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("10.00"),
            payment_currency=self.zwg,
            exchange_rate=Decimal("20.00"),
            amount_paid=Decimal("200.00"),
            paid_at=now,
            fiscal_approval_status=FiscalApprovalStatus.APPROVED,
            fiscal_approved_at=now,
        )
        OrderItem.objects.create(
            order=zwg_order,
            product=self.product,
            quantity=Decimal("1"),
            price=Decimal("10.00"),
        )

        report = build_vat_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            branch_id=self.branch.id,
            currency="zwg",
        )
        self.assertEqual(report["currency"]["mode"], "zwg")
        self.assertIn("ZWG", report["amounts_by_currency"])
        self.assertNotIn("USD", report["amounts_by_currency"])
        # Only ZWG-paid order; expressed with payment exchange_rate 20, not 25.50.
        expected_base = split_inclusive_total(Decimal("10.00"), Decimal("15.5"))
        self.assertEqual(
            report["amounts_by_currency"]["ZWG"]["output_tax"]["total_sales_including_vat"],
            (expected_base["total"] * Decimal("20.00")).quantize(Decimal("0.01")),
        )
        self.assertEqual(
            report["amounts_by_currency"]["ZWG"]["output_tax"]["vat_on_taxable_sales"],
            (expected_base["tax"] * Decimal("20.00")).quantize(Decimal("0.01")),
        )
        # Purchases stay in USD/base — ZWG column has no purchase VAT.
        self.assertEqual(
            report["amounts_by_currency"]["ZWG"]["input_tax"]["vat_on_taxable_purchases"],
            Decimal("0"),
        )

    def test_vat_report_currency_both_splits_by_payment_currency(self):
        today = timezone.localdate()
        now = timezone.now()
        zwg_order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("10.00"),
            payment_currency=self.zwg,
            exchange_rate=Decimal("20.00"),
            amount_paid=Decimal("200.00"),
            paid_at=now,
            fiscal_approval_status=FiscalApprovalStatus.APPROVED,
            fiscal_approved_at=now,
        )
        OrderItem.objects.create(
            order=zwg_order,
            product=self.product,
            quantity=Decimal("1"),
            price=Decimal("10.00"),
        )

        report = build_vat_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            branch_id=self.branch.id,
            currency="both",
        )
        self.assertEqual(report["currency"]["mode"], "both")
        self.assertIn("USD", report["amounts_by_currency"])
        self.assertIn("ZWG", report["amounts_by_currency"])
        usd_expected = split_inclusive_total(Decimal("67.00"), Decimal("15.5"))
        zwg_expected = split_inclusive_total(Decimal("10.00"), Decimal("15.5"))
        self.assertEqual(
            report["amounts_by_currency"]["USD"]["output_tax"]["total_sales_including_vat"],
            usd_expected["total"],
        )
        self.assertEqual(
            report["amounts_by_currency"]["ZWG"]["output_tax"]["total_sales_including_vat"],
            (zwg_expected["total"] * Decimal("20.00")).quantize(Decimal("0.01")),
        )
        # Top-level remains all fiscalised sales in base currency.
        self.assertEqual(
            report["output_tax"]["total_sales_including_vat"],
            usd_expected["total"] + zwg_expected["total"],
        )

    def test_vat_report_currency_api(self):
        today = timezone.localdate()
        response = self.client.get(
            f"/api/reports/vat/?from={today.isoformat()}&to={today.isoformat()}"
            f"&branch={self.branch.id}&currency=both"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["currency"]["mode"], "both")
        self.assertEqual(response.data["currency"]["basis"], "payment_currency")
        self.assertIn("ZWG", response.data["amounts_by_currency"])

    def test_vat_report_currency_api_rejects_invalid_mode(self):
        today = timezone.localdate()
        response = self.client.get(
            f"/api/reports/vat/?from={today.isoformat()}&to={today.isoformat()}"
            f"&branch={self.branch.id}&currency=eur"
        )
        self.assertEqual(response.status_code, 400)
