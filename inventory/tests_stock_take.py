from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from branches.models import Branch, BranchType
from catalog.constants import BRANCH_INGREDIENTS_CATEGORY
from catalog.models import Product, ProductCategory
from inventory.models import (
    BranchInventory,
    StockTake,
    StockTakeStatus,
    StockTakeType,
)

User = get_user_model()


class StockTakeWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        food_cat = ProductCategory.objects.create(name="Pastries", is_asset=False)
        ingredient_cat = ProductCategory.objects.create(
            name=BRANCH_INGREDIENTS_CATEGORY, is_asset=False
        )
        asset_cat = ProductCategory.objects.create(name="Equipment", is_asset=True)

        self.croissant = Product.objects.create(
            name="Croissant",
            category=food_cat,
            selling_price=Decimal("2.75"),
        )
        self.flour = Product.objects.create(
            name="Flour",
            category=ingredient_cat,
            selling_price=Decimal("5.00"),
            daily_stock_take=True,
        )
        self.blender = Product.objects.create(
            name="Blender",
            category=asset_cat,
            selling_price=Decimal("200.00"),
        )

        BranchInventory.objects.create(
            branch=self.branch,
            product=self.croissant,
            quantity=Decimal("10"),
        )
        BranchInventory.objects.create(
            branch=self.branch,
            product=self.flour,
            quantity=Decimal("50"),
        )
        BranchInventory.objects.create(
            branch=self.branch,
            product=self.blender,
            quantity=Decimal("2"),
        )

    def test_daily_stock_take_includes_flagged_products_only(self):
        response = self.client.post(
            "/api/stock-takes/",
            {
                "branch": self.branch.id,
                "stock_take_type": StockTakeType.DAILY,
                "count_date": "2026-06-09",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        product_ids = {line["product"] for line in response.data["lines"]}
        self.assertIn(self.flour.id, product_ids)
        self.assertNotIn(self.croissant.id, product_ids)
        self.assertNotIn(self.blender.id, product_ids)

    def test_retrieve_draft_stock_take_drops_pos_products(self):
        from inventory.models import StockTakeLine

        stock_take = StockTake.objects.create(
            branch=self.branch,
            stock_take_type=StockTakeType.DAILY,
            count_date=date(2026, 6, 17),
            status=StockTakeStatus.DRAFT,
        )
        StockTakeLine.objects.create(
            stock_take=stock_take,
            product=self.croissant,
            system_quantity=Decimal("10"),
        )
        StockTakeLine.objects.create(
            stock_take=stock_take,
            product=self.flour,
            system_quantity=Decimal("50"),
        )

        response = self.client.get(f"/api/stock-takes/{stock_take.id}/")
        self.assertEqual(response.status_code, 200)
        product_ids = {line["product"] for line in response.data["lines"]}
        self.assertIn(self.flour.id, product_ids)
        self.assertNotIn(self.croissant.id, product_ids)

    def test_monthly_stock_take_includes_ingredients_and_assets(self):
        response = self.client.post(
            "/api/stock-takes/",
            {
                "branch": self.branch.id,
                "stock_take_type": StockTakeType.MONTHLY,
                "count_date": "2026-06-15",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["count_date"], "2026-06-01")
        product_ids = {line["product"] for line in response.data["lines"]}
        self.assertIn(self.flour.id, product_ids)
        self.assertIn(self.blender.id, product_ids)
        self.assertNotIn(self.croissant.id, product_ids)

    def test_complete_stock_take_posts_variances(self):
        create_response = self.client.post(
            "/api/stock-takes/",
            {
                "branch": self.branch.id,
                "stock_take_type": StockTakeType.DAILY,
                "count_date": "2026-06-09",
            },
            format="json",
        )
        stock_take_id = create_response.data["id"]
        lines = create_response.data["lines"]

        flour_line = next(line for line in lines if line["product"] == self.flour.id)

        patch_response = self.client.patch(
            f"/api/stock-takes/{stock_take_id}/lines/",
            {
                "lines": [
                    {
                        "id": flour_line["id"],
                        "counted_quantity": "48",
                    },
                ]
            },
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)

        complete_response = self.client.post(
            f"/api/stock-takes/{stock_take_id}/complete/",
            {},
            format="json",
        )
        self.assertEqual(complete_response.status_code, 200)
        self.assertEqual(complete_response.data["status"], StockTakeStatus.COMPLETED)

        flour_inventory = BranchInventory.objects.get(
            branch=self.branch, product=self.flour
        )
        self.assertEqual(flour_inventory.quantity, Decimal("48"))
        self.flour.refresh_from_db()
        self.assertEqual(self.flour.remaining_qty, Decimal("48"))

        croissant_inventory = BranchInventory.objects.get(
            branch=self.branch, product=self.croissant
        )
        self.assertEqual(croissant_inventory.quantity, Decimal("10"))

    def test_complete_stock_take_overrides_inventory_when_sales_occurred_during_count(self):
        create_response = self.client.post(
            "/api/stock-takes/",
            {
                "branch": self.branch.id,
                "stock_take_type": StockTakeType.DAILY,
                "count_date": "2026-06-16",
            },
            format="json",
        )
        stock_take_id = create_response.data["id"]
        flour_line = next(
            line for line in create_response.data["lines"]
            if line["product"] == self.flour.id
        )

        flour_inventory = BranchInventory.objects.get(
            branch=self.branch, product=self.flour
        )
        flour_inventory.quantity = Decimal("45")
        flour_inventory.save(update_fields=["quantity"])

        self.client.patch(
            f"/api/stock-takes/{stock_take_id}/lines/",
            {
                "lines": [
                    {"id": flour_line["id"], "counted_quantity": "50"},
                ]
            },
            format="json",
        )
        complete_response = self.client.post(
            f"/api/stock-takes/{stock_take_id}/complete/",
            {},
            format="json",
        )
        self.assertEqual(complete_response.status_code, 200)

        flour_inventory.refresh_from_db()
        self.assertEqual(flour_inventory.quantity, Decimal("50"))
        self.flour.refresh_from_db()
        self.assertEqual(self.flour.remaining_qty, Decimal("50"))

    def test_duplicate_completed_daily_stock_take_rejected(self):
        stock_take = StockTake.objects.create(
            branch=self.branch,
            stock_take_type=StockTakeType.DAILY,
            count_date=date(2026, 6, 9),
            status=StockTakeStatus.COMPLETED,
        )
        self.assertEqual(stock_take.pk, stock_take.id)

        response = self.client.post(
            "/api/stock-takes/",
            {
                "branch": self.branch.id,
                "stock_take_type": StockTakeType.DAILY,
                "count_date": "2026-06-09",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("already exists", response.data["detail"])

    def test_export_and_import_stock_take_csv(self):
        create_response = self.client.post(
            "/api/stock-takes/",
            {
                "branch": self.branch.id,
                "stock_take_type": StockTakeType.DAILY,
                "count_date": "2026-06-10",
            },
            format="json",
        )
        stock_take_id = create_response.data["id"]
        flour_line = next(
            line
            for line in create_response.data["lines"]
            if line["product"] == self.flour.id
        )

        export_response = self.client.get(
            f"/api/stock-takes/{stock_take_id}/export-csv/"
        )
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response["Content-Type"], "text/csv; charset=utf-8")
        csv_text = export_response.content.decode("utf-8")
        self.assertIn("line_id", csv_text)
        self.assertIn("counted_quantity", csv_text)
        self.assertIn(str(flour_line["id"]), csv_text)

        csv_content = (
            "line_id,category,product_name,counted_quantity\n"
            f"{flour_line['id']},Ingredients,Flour,48\n"
        )
        import_response = self.client.post(
            f"/api/stock-takes/{stock_take_id}/import-csv/",
            {
                "file": SimpleUploadedFile(
                    "stock-take.csv",
                    csv_content.encode("utf-8"),
                    content_type="text/csv",
                )
            },
            format="multipart",
        )
        self.assertEqual(import_response.status_code, 200)
        self.assertEqual(import_response.data["updated"], 1)

        flour_imported = next(
            line
            for line in import_response.data["stock_take"]["lines"]
            if line["product"] == self.flour.id
        )
        self.assertEqual(flour_imported["counted_quantity"], "48.00")

    def test_export_completed_stock_take_report_csv(self):
        create_response = self.client.post(
            "/api/stock-takes/",
            {
                "branch": self.branch.id,
                "stock_take_type": StockTakeType.DAILY,
                "count_date": "2026-06-12",
            },
            format="json",
        )
        stock_take_id = create_response.data["id"]
        flour_line = next(
            line
            for line in create_response.data["lines"]
            if line["product"] == self.flour.id
        )

        self.client.patch(
            f"/api/stock-takes/{stock_take_id}/lines/",
            {
                "lines": [
                    {"id": flour_line["id"], "counted_quantity": "48"},
                ]
            },
            format="json",
        )
        self.client.post(f"/api/stock-takes/{stock_take_id}/complete/", {}, format="json")

        export_response = self.client.get(
            f"/api/stock-takes/{stock_take_id}/export-report-csv/"
        )
        self.assertEqual(export_response.status_code, 200)
        csv_text = export_response.content.decode("utf-8")
        self.assertIn("system_quantity", csv_text)
        self.assertIn("variance", csv_text)
        self.assertIn("-2", csv_text)

    def test_save_lines_accepts_null_counted_quantity(self):
        create_response = self.client.post(
            "/api/stock-takes/",
            {
                "branch": self.branch.id,
                "stock_take_type": StockTakeType.DAILY,
                "count_date": "2026-06-11",
            },
            format="json",
        )
        stock_take_id = create_response.data["id"]
        line = create_response.data["lines"][0]

        patch_response = self.client.patch(
            f"/api/stock-takes/{stock_take_id}/lines/",
            {
                "lines": [
                    {
                        "id": line["id"],
                        "counted_quantity": None,
                        "notes": "",
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)

    def test_day_end_check_requires_completed_daily_stock_take(self):
        response = self.client.get(
            f"/api/stock-takes/day-end-check/?branch={self.branch.id}&date=2026-06-13"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["completed"])
        self.assertIn("daily stock take", response.data["detail"].lower())

        StockTake.objects.create(
            branch=self.branch,
            stock_take_type=StockTakeType.DAILY,
            count_date=date(2026, 6, 13),
            status=StockTakeStatus.COMPLETED,
        )
        response = self.client.get(
            f"/api/stock-takes/day-end-check/?branch={self.branch.id}&date=2026-06-13"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["completed"])

    def test_day_end_check_ignores_draft_stock_take(self):
        StockTake.objects.create(
            branch=self.branch,
            stock_take_type=StockTakeType.DAILY,
            count_date=date(2026, 6, 14),
            status=StockTakeStatus.DRAFT,
        )
        response = self.client.get(
            f"/api/stock-takes/day-end-check/?branch={self.branch.id}&date=2026-06-14"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["completed"])
        self.assertTrue(response.data["draft_in_progress"])
        self.assertIn("post variances", response.data["detail"].lower())


class StockTakeBranchAccessTests(TestCase):
    def setUp(self):
        from accounts.models import StaffProfile, StaffRole

        self.client = APIClient()
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        self.other_branch = Branch.objects.create(
            name="Borrowdale",
            branch_type=BranchType.BRANCH,
        )

        self.branch_staff = User.objects.create_user(username="branchmgr", password="pass")
        StaffProfile.objects.create(
            user=self.branch_staff,
            branch=self.branch,
            role=StaffRole.BRANCH_MANAGER,
        )

        self.hq_admin = User.objects.create_user(username="hqadmin", password="pass")
        StaffProfile.objects.create(
            user=self.hq_admin,
            branch=self.branch,
            role=StaffRole.HQ_ADMIN,
        )

    def test_branch_staff_cannot_create_stock_take_for_other_branch(self):
        self.client.force_authenticate(user=self.branch_staff)
        response = self.client.post(
            "/api/stock-takes/",
            {
                "branch": self.other_branch.id,
                "stock_take_type": StockTakeType.DAILY,
                "count_date": "2026-06-20",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("assigned branch", str(response.data).lower())

    def test_branch_staff_can_create_stock_take_for_own_branch(self):
        self.client.force_authenticate(user=self.branch_staff)
        response = self.client.post(
            "/api/stock-takes/",
            {
                "branch": self.branch.id,
                "stock_take_type": StockTakeType.DAILY,
                "count_date": "2026-06-20",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_hq_admin_can_create_stock_take_for_any_branch(self):
        self.client.force_authenticate(user=self.hq_admin)
        response = self.client.post(
            "/api/stock-takes/",
            {
                "branch": self.other_branch.id,
                "stock_take_type": StockTakeType.DAILY,
                "count_date": "2026-06-20",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_branch_staff_only_sees_own_branch_stock_takes(self):
        StockTake.objects.create(
            branch=self.branch,
            stock_take_type=StockTakeType.DAILY,
            count_date=date(2026, 6, 20),
            status=StockTakeStatus.DRAFT,
        )
        StockTake.objects.create(
            branch=self.other_branch,
            stock_take_type=StockTakeType.DAILY,
            count_date=date(2026, 6, 20),
            status=StockTakeStatus.DRAFT,
        )

        self.client.force_authenticate(user=self.branch_staff)
        response = self.client.get("/api/stock-takes/")
        self.assertEqual(response.status_code, 200)
        branch_ids = {item["branch"] for item in response.data["results"]}
        self.assertEqual(branch_ids, {self.branch.id})
