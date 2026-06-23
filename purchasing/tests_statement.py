from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile, StaffRole
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, Supplier
from purchasing.reports import build_supplier_spend_summary_report
from purchasing.statement import build_supplier_statement_report

User = get_user_model()


class SupplierStatementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(
            name="Highland",
            code="HIG",
            branch_type=BranchType.BRANCH,
        )
        self.other_branch = Branch.objects.create(
            name="Avondale",
            code="AVO",
            branch_type=BranchType.BRANCH,
        )
        self.category = ProductCategory.objects.create(name="Ingredients")
        self.product = Product.objects.create(
            name="Flour",
            category=self.category,
            selling_price=Decimal("0"),
        )
        self.supplier = Supplier.objects.create(name="Bakers Co", phone="0771234567")
        self.other_supplier = Supplier.objects.create(name="Other Supplier")
        self.manager = User.objects.create_user(username="manager", password="pass")
        StaffProfile.objects.create(
            user=self.manager,
            branch=self.branch,
            role=StaffRole.BRANCH_MANAGER,
        )
        self.client.force_authenticate(user=self.manager)

        jan = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.UTC)
        feb = datetime(2026, 2, 10, 10, 0, tzinfo=timezone.UTC)

        self.jan_po = PurchaseOrder.objects.create(
            branch=self.branch,
            supplier=self.supplier,
            status=PurchaseOrderStatus.RECEIVED,
            received_at=jan,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=self.jan_po,
            product=self.product,
            quantity=Decimal("10"),
            unit_cost=Decimal("5.00"),
        )

        self.feb_po = PurchaseOrder.objects.create(
            branch=self.branch,
            supplier=self.supplier,
            status=PurchaseOrderStatus.RECEIVED,
            received_at=feb,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=self.feb_po,
            product=self.product,
            quantity=Decimal("4"),
            unit_cost=Decimal("12.50"),
        )

        self.other_branch_po = PurchaseOrder.objects.create(
            branch=self.other_branch,
            supplier=self.supplier,
            status=PurchaseOrderStatus.RECEIVED,
            received_at=feb,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=self.other_branch_po,
            product=self.product,
            quantity=Decimal("1"),
            unit_cost=Decimal("100.00"),
        )

        PurchaseOrder.objects.create(
            branch=self.branch,
            supplier=self.supplier,
            status=PurchaseOrderStatus.CANCELLED,
            received_at=feb,
        )

        self.other_supplier_po = PurchaseOrder.objects.create(
            branch=self.branch,
            supplier=self.other_supplier,
            status=PurchaseOrderStatus.RECEIVED,
            received_at=feb,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=self.other_supplier_po,
            product=self.product,
            quantity=Decimal("2"),
            unit_cost=Decimal("20.00"),
        )

    def test_statement_period_spend_and_opening(self):
        report = build_supplier_statement_report(
            self.supplier,
            from_date="2026-02-01",
            to_date="2026-02-28",
            branch_id=self.branch.id,
        )
        self.assertEqual(report["opening_spend"], Decimal("50.00"))
        self.assertEqual(report["period_spend"], Decimal("50.00"))
        self.assertEqual(report["closing_spend"], Decimal("100.00"))
        self.assertEqual(report["purchase_count"], 1)
        self.assertEqual(report["purchases"][0].id, self.feb_po.id)

    def test_statement_all_time_includes_all_received_purchases(self):
        report = build_supplier_statement_report(
            self.supplier,
            all_time=True,
            branch_id=self.branch.id,
        )
        self.assertEqual(report["all_time_spend"], Decimal("100.00"))
        self.assertEqual(report["purchase_count"], 2)

    def test_spend_summary_groups_by_supplier(self):
        report = build_supplier_spend_summary_report(
            from_date="2026-02-01",
            to_date="2026-02-28",
            branch_id=self.branch.id,
        )
        self.assertEqual(report["summary"]["supplier_count"], 2)
        self.assertEqual(report["summary"]["suppliers_with_spend"], 2)
        self.assertEqual(report["summary"]["total_spend"], Decimal("90.00"))

        by_id = {row["id"]: row for row in report["suppliers"]}
        self.assertEqual(by_id[self.supplier.id]["period_spend"], Decimal("50.00"))
        self.assertEqual(by_id[self.other_supplier.id]["period_spend"], Decimal("40.00"))

    def test_statement_api_endpoint(self):
        response = self.client.get(
            f"/api/suppliers/{self.supplier.id}/statement/"
            "?from=2026-02-01&to=2026-02-28&branch={}".format(self.branch.id)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data["period_spend"]), Decimal("50.00"))
        self.assertEqual(len(response.data["purchases"]), 1)

    def test_history_api_endpoint(self):
        response = self.client.get(f"/api/suppliers/{self.supplier.id}/history/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data["all_time_spend"]), Decimal("200.00"))
        self.assertEqual(len(response.data["purchases"]), 3)
        first = response.data["purchases"][0]
        self.assertIn("lines", first)
        self.assertIn("notes", first)

    def test_spend_summary_api_endpoint(self):
        response = self.client.get(
            "/api/reports/supplier-spend/"
            "?from=2026-02-01&to=2026-02-28&branch={}".format(self.branch.id)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Decimal(response.data["summary"]["total_spend"]),
            Decimal("90.00"),
        )
