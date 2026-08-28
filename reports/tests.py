from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from branches.models import Branch, BranchType
from bakery.models import Recipe
from catalog.models import Product, ProductCategory
from customers.models import Customer
from inventory.models import BranchInventory, CentralInvoice, CentralInvoiceLine
from inventory.services import finalize_central_invoice_creation, record_central_invoice_payment
from orders.models import Expense, Order, OrderItem, OrderPayment, OrderStatus, OrderType, PaymentMethod
from payments.models import Currency
from orders.tax import split_inclusive_total
from reports.services import (
    build_profit_report,
    build_report_summary,
    build_sales_by_product_report,
    export_sales_csv,
)


class ReportServiceTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        self.category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso",
            category=self.category,
            selling_price=Decimal("4.00"),
            tax_rate=Decimal("15"),
            remaining_qty=Decimal("5"),
        )
        self.order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("8.00"),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=Decimal("2"),
            price=Decimal("4.00"),
        )

    def test_summary_includes_revenue_and_tax(self):
        today = timezone.localdate()
        report = build_report_summary(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
        )
        self.assertEqual(report["summary"]["order_count"], 1)
        self.assertEqual(report["summary"]["total_revenue"], Decimal("8.00"))
        self.assertEqual(
            report["summary"]["tax_collected"],
            split_inclusive_total(Decimal("8.00"))["tax"],
        )
        self.assertEqual(len(report["top_products"]), 1)
        self.assertEqual(report["top_products"][0]["product_name"], "Espresso")
        self.assertEqual(len(report["low_stock"]), 1)

    def test_sales_by_product_aggregates_qty_price_total(self):
        other = Product.objects.create(
            name="Latte",
            category=self.category,
            selling_price=Decimal("5.00"),
            remaining_qty=Decimal("20"),
        )
        order2 = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("9.00"),
        )
        OrderItem.objects.create(
            order=order2,
            product=self.product,
            quantity=Decimal("1"),
            price=Decimal("4.00"),
        )
        OrderItem.objects.create(
            order=order2,
            product=other,
            quantity=Decimal("1"),
            price=Decimal("5.00"),
        )

        today = timezone.localdate()
        report = build_sales_by_product_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
        )
        self.assertEqual(report["summary"]["product_count"], 2)
        self.assertEqual(report["summary"]["total_quantity"], Decimal("4"))
        self.assertEqual(report["summary"]["total_sales"], Decimal("17.00"))

        by_name = {row["product_name"]: row for row in report["rows"]}
        espresso = by_name["Espresso"]
        self.assertEqual(espresso["quantity"], Decimal("3"))
        self.assertEqual(espresso["unit_price"], Decimal("4.00"))
        self.assertEqual(espresso["total"], Decimal("12.00"))
        self.assertEqual(by_name["Latte"]["total"], Decimal("5.00"))

        filtered = build_sales_by_product_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            search="lat",
        )
        self.assertEqual(filtered["summary"]["product_count"], 1)
        self.assertEqual(filtered["rows"][0]["product_name"], "Latte")

    def test_summary_excludes_unpaid_orders(self):
        Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.OPEN,
            total_amount=Decimal("99.00"),
        )
        today = timezone.localdate()
        report = build_report_summary(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
        )
        self.assertEqual(report["summary"]["order_count"], 1)

    def test_summary_groups_payment_methods(self):
        from payments.models import Currency

        branch = Branch.objects.create(name="Payments Branch", branch_type=BranchType.BRANCH)
        usd = Currency.objects.create(code="USD", name="US Dollar", symbol="$", is_base=True)
        zwl = Currency.objects.create(code="ZWL", name="Zimbabwe Dollar", symbol="$")
        zwl.rates.create(rate=Decimal("25"), effective_from=timezone.localdate())

        cash_order = Order.objects.create(
            branch=branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("10.00"),
            payment_method=PaymentMethod.CASH,
        )
        OrderPayment.objects.create(
            order=cash_order,
            method="cash",
            currency=usd,
            amount=Decimal("10.00"),
            exchange_rate=Decimal("1"),
        )

        account_order = Order.objects.create(
            branch=branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("5.00"),
            payment_method=PaymentMethod.ACCOUNT,
        )

        split_order = Order.objects.create(
            branch=branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("7.00"),
            payment_method=PaymentMethod.MULTI,
        )
        OrderPayment.objects.create(
            order=split_order,
            method="cash",
            currency=usd,
            amount=Decimal("5.00"),
            exchange_rate=Decimal("1"),
        )
        OrderPayment.objects.create(
            order=split_order,
            method="ecocash",
            currency=zwl,
            amount=Decimal("51.00"),
            exchange_rate=Decimal("25"),
        )

        today = timezone.localdate()
        report = build_report_summary(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            branch_id=branch.id,
        )
        by_label = {row["method_label"]: row for row in report["by_payment_method"]}
        self.assertEqual(by_label["US Dollar"]["revenue"], Decimal("15.00"))
        self.assertEqual(by_label["US Dollar"]["order_count"], 2)
        self.assertEqual(by_label["US Dollar"]["payment_count"], 2)
        self.assertEqual(by_label["Zimbabwe Dollar"]["revenue"], Decimal("2.04"))
        self.assertEqual(by_label["Zimbabwe Dollar"]["payment_count"], 1)
        self.assertEqual(by_label["Customer account"]["revenue"], Decimal("5.00"))
        self.assertEqual(by_label["Customer account"]["order_count"], 1)

    def test_export_sales_csv(self):
        today = timezone.localdate()
        csv_text = export_sales_csv(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
        )
        self.assertIn("order_id,date,branch,product,category", csv_text)
        self.assertIn("Espresso", csv_text)
        self.assertIn("Avondale", csv_text)


class ProfitReportTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        self.category = ProductCategory.objects.create(name="Pastries")
        self.ingredient = Product.objects.create(
            name="Flour",
            category=self.category,
            selling_price=Decimal("1.00"),
        )
        self.product = Product.objects.create(
            name="Croissant",
            category=self.category,
            selling_price=Decimal("3.00"),
        )
        Recipe.objects.create(
            product=self.product,
            ingredient=self.ingredient,
            quantity_required=Decimal("0.25"),
        )
        self.order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("6.00"),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=Decimal("2"),
            price=Decimal("3.00"),
        )

    def test_profit_report_calculates_cogs_and_margin(self):
        today = timezone.localdate()
        report = build_profit_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
        )
        self.assertEqual(report["summary"]["total_revenue"], Decimal("6.00"))
        self.assertEqual(report["summary"]["total_cogs"], Decimal("0.50"))
        self.assertEqual(report["summary"]["gross_profit"], Decimal("5.50"))
        self.assertEqual(report["summary"]["gross_profit_percent"], Decimal("91.67"))
        self.assertEqual(len(report["by_product"]), 1)
        self.assertEqual(report["by_product"][0]["product_name"], "Croissant")
        self.assertEqual(report["by_product"][0]["gp_percent"], Decimal("91.67"))

    def test_profit_report_includes_operating_expenses(self):
        from payments.models import Currency

        currency = Currency.objects.create(code="USD", name="US Dollar", symbol="$")
        today = timezone.localdate()
        Expense.objects.create(
            branch=self.branch,
            expense_date=today,
            amount=Decimal("2.00"),
            currency=currency,
            description="Sugar",
        )
        report = build_profit_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
        )
        self.assertEqual(report["summary"]["operating_expenses"], Decimal("2.00"))
        self.assertEqual(report["summary"]["net_profit"], Decimal("3.50"))

    def test_profit_report_flags_products_without_recipe(self):
        Product.objects.create(
            name="Coffee",
            category=self.category,
            selling_price=Decimal("4.00"),
        )
        order = Order.objects.create(
            branch=self.branch,
            status=OrderStatus.PAID,
            total_amount=Decimal("4.00"),
        )
        OrderItem.objects.create(
            order=order,
            product=Product.objects.get(name="Coffee"),
            quantity=Decimal("1"),
            price=Decimal("4.00"),
        )
        today = timezone.localdate()
        report = build_profit_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
        )
        self.assertEqual(report["summary"]["products_without_recipe"], 1)
        self.assertEqual(report["summary"]["revenue_without_recipe"], Decimal("4.00"))


class ReportApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(name="HQ", branch_type=BranchType.HQ)
        category = ProductCategory.objects.create(name="Pastries")
        product = Product.objects.create(
            name="Croissant",
            category=category,
            selling_price=Decimal("3.00"),
        )
        order = Order.objects.create(
            branch=self.branch,
            status=OrderStatus.PAID,
            total_amount=Decimal("3.00"),
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=Decimal("1"),
            price=Decimal("3.00"),
        )

    def test_summary_endpoint(self):
        today = timezone.localdate().isoformat()
        response = self.client.get(f"/api/reports/summary/?from={today}&to={today}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["order_count"], 1)

    def test_export_endpoint(self):
        today = timezone.localdate().isoformat()
        response = self.client.get(f"/api/reports/export-csv/?from={today}&to={today}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Croissant", response.content)

    def test_profit_endpoint(self):
        today = timezone.localdate().isoformat()
        response = self.client.get(f"/api/reports/profit/?from={today}&to={today}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("gross_profit", response.data["summary"])
        self.assertIn("by_product", response.data)


class CentralInvoiceReportTests(TestCase):
    def setUp(self):
        self.stores = Branch.objects.create(
            name="Central Stores",
            branch_type=BranchType.STORES,
            code="STR",
        )
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        self.customer = Customer.objects.create(
            first_name="Wholesale",
            last_name="Buyer",
            phone="0777000001",
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
            selling_price=Decimal("3.00"),
        )
        BranchInventory.objects.create(
            branch=self.stores,
            product=self.croissant,
            quantity=Decimal("20"),
        )
        invoice = CentralInvoice.objects.create(
            from_branch=self.stores,
            customer=self.customer,
        )
        CentralInvoiceLine.objects.create(
            central_invoice=invoice,
            product=self.croissant,
            quantity=Decimal("4"),
            unit_price=Decimal("3.00"),
        )
        finalize_central_invoice_creation(invoice)
        record_central_invoice_payment(
            invoice,
            user=None,
            payment_lines=[{"currency": self.usd, "amount": Decimal("12.00")}],
        )
        self.invoice_total = Decimal("12.00")

    def test_stores_filter_includes_paid_central_invoice_sales(self):
        today = timezone.localdate()
        report = build_report_summary(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            branch_id=self.stores.id,
        )
        self.assertEqual(report["summary"]["total_revenue"], self.invoice_total)
        self.assertEqual(report["summary"]["order_count"], 1)
        self.assertEqual(len(report["by_branch"]), 1)
        self.assertEqual(report["by_branch"][0]["branch_name"], "Central Stores")

        by_product = build_sales_by_product_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            branch_id=self.stores.id,
        )
        self.assertEqual(by_product["summary"]["total_sales"], self.invoice_total)
        self.assertEqual(by_product["rows"][0]["product_name"], "Croissant")
        self.assertEqual(by_product["rows"][0]["quantity"], Decimal("4"))

        profit = build_profit_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            branch_id=self.stores.id,
        )
        self.assertEqual(profit["summary"]["total_revenue"], self.invoice_total)

        csv_text = export_sales_csv(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            branch_id=self.stores.id,
        )
        self.assertIn("CISTR", csv_text)
        self.assertIn("Croissant", csv_text)

    def test_branch_filter_excludes_central_invoice_sales(self):
        today = timezone.localdate()
        report = build_report_summary(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            branch_id=self.branch.id,
        )
        self.assertEqual(report["summary"]["total_revenue"], Decimal("0"))
        self.assertEqual(report["summary"]["order_count"], 0)

    def test_all_branches_includes_central_invoice_sales(self):
        today = timezone.localdate()
        report = build_report_summary(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
        )
        self.assertEqual(report["summary"]["total_revenue"], self.invoice_total)
        self.assertEqual(report["summary"]["order_count"], 1)
