from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from orders.models import FiscalApprovalStatus, Order, OrderItem, OrderStatus, OrderType
from orders.tax import split_inclusive_total
from purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, Supplier
from reports.vat import build_vat_report

User = get_user_model()


class VATReportTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.ui_client = Client()
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
