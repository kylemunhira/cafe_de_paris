from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile, StaffRole
from bakery.models import ProductionOrder, ProductionSheetStatus, Recipe
from bakery.services import destination_column_label
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from inventory.models import BranchInventory

User = get_user_model()


class BakeryProductionSheetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.bakery = Branch.objects.create(
            name="Central Bakery",
            branch_type=BranchType.BAKERY,
        )
        self.highlands = Branch.objects.create(
            name="Cafe de Paris Highlands",
            branch_type=BranchType.BRANCH,
            code="HIG",
        )
        self.churchill = Branch.objects.create(
            name="Cafe de Paris Churchill",
            branch_type=BranchType.BRANCH,
            code="CHU",
        )
        self.stores = Branch.objects.filter(branch_type=BranchType.STORES).first()
        if self.stores is None:
            self.stores = Branch.objects.create(
                name="Central Stores",
                branch_type=BranchType.STORES,
                code="STR",
            )

        self.baker = User.objects.create_user(username="baker", password="pass")
        StaffProfile.objects.create(
            user=self.baker,
            branch=self.bakery,
            role=StaffRole.BAKER,
        )
        self.client.force_login(self.baker)

        pastries = ProductCategory.objects.create(name="Breads & pastries")
        ingredients = ProductCategory.objects.create(name="Ingredients")

        self.croissant = Product.objects.create(
            name="Almond Croissants",
            category=pastries,
            selling_price=Decimal("2.75"),
        )
        self.baguette = Product.objects.create(
            name="Baguette",
            category=pastries,
            selling_price=Decimal("1.50"),
        )
        self.flour = Product.objects.create(
            name="Flour",
            category=ingredients,
            selling_price=Decimal("5.00"),
        )

        Recipe.objects.create(
            product=self.croissant,
            ingredient=self.flour,
            quantity_required=Decimal("0.30"),
        )
        BranchInventory.objects.create(
            branch=self.bakery,
            product=self.flour,
            quantity=Decimal("100"),
        )

    def test_destination_labels(self):
        self.assertEqual(destination_column_label(self.highlands), "Highlands qty")
        self.assertEqual(destination_column_label(self.churchill), "Churchill")
        self.assertEqual(destination_column_label(self.stores), "Central stores")

    def test_create_production_sheet_lists_bakery_products(self):
        response = self.client.post(
            "/api/production-sheets/",
            {
                "branch": self.bakery.id,
                "production_date": "2026-07-27",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], ProductionSheetStatus.DRAFT)
        self.assertEqual(response.data["line_count"], 2)
        labels = [d["label"] for d in response.data["destinations"]]
        self.assertEqual(labels, ["Highlands qty", "Churchill", "Central stores"])
        product_names = {line["product_name"] for line in response.data["lines"]}
        self.assertEqual(product_names, {"Almond Croissants", "Baguette"})
        for line in response.data["lines"]:
            self.assertEqual(len(line["allocations"]), 3)

    def test_update_and_complete_production_sheet(self):
        create = self.client.post(
            "/api/production-sheets/",
            {
                "branch": self.bakery.id,
                "production_date": str(date.today()),
            },
            format="json",
        )
        sheet_id = create.data["id"]
        croissant_line = next(
            line for line in create.data["lines"]
            if line["product"] == self.croissant.id
        )

        patch = self.client.patch(
            f"/api/production-sheets/{sheet_id}/lines/",
            {
                "lines": [
                    {
                        "id": croissant_line["id"],
                        "allocations": [
                            {"destination_branch": self.highlands.id, "quantity": "10"},
                            {"destination_branch": self.churchill.id, "quantity": "5"},
                            {"destination_branch": self.stores.id, "quantity": "2"},
                        ],
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(patch.status_code, 200)
        updated_line = next(
            line for line in patch.data["lines"]
            if line["product"] == self.croissant.id
        )
        self.assertEqual(Decimal(updated_line["total_quantity"]), Decimal("17"))

        complete = self.client.post(f"/api/production-sheets/{sheet_id}/complete/", {})
        self.assertEqual(complete.status_code, 200)
        self.assertEqual(complete.data["status"], ProductionSheetStatus.COMPLETED)

        stock = BranchInventory.objects.get(branch=self.bakery, product=self.croissant)
        self.assertEqual(stock.quantity, Decimal("17"))
        flour = BranchInventory.objects.get(branch=self.bakery, product=self.flour)
        self.assertEqual(flour.quantity, Decimal("94.90"))
        self.assertEqual(
            ProductionOrder.objects.filter(product=self.croissant).count(),
            1,
        )

        from inventory.models import DeliveryNote, StockTransferStatus

        notes = list(
            DeliveryNote.objects.filter(
                from_branch=self.bakery,
                status=StockTransferStatus.REQUESTED,
            ).prefetch_related("lines")
        )
        self.assertEqual(len(notes), 3)
        by_dest = {note.to_branch_id: note for note in notes}
        self.assertEqual(
            by_dest[self.highlands.id].lines.get().quantity,
            Decimal("10"),
        )
        self.assertEqual(
            by_dest[self.churchill.id].lines.get().quantity,
            Decimal("5"),
        )
        self.assertEqual(
            by_dest[self.stores.id].lines.get().quantity,
            Decimal("2"),
        )

        # GRV approve moves stock bakery → destination.
        highland_note = by_dest[self.highlands.id]
        cashier = User.objects.create_user(username="highland_cashier", password="pass")
        StaffProfile.objects.create(
            user=cashier,
            branch=self.highlands,
            role=StaffRole.CASHIER,
        )
        self.client.force_login(cashier)
        approve = self.client.post(f"/api/delivery-notes/{highland_note.id}/approve/")
        self.assertEqual(approve.status_code, 200)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal("7"))
        highland_stock = BranchInventory.objects.get(
            branch=self.highlands,
            product=self.croissant,
        )
        self.assertEqual(highland_stock.quantity, Decimal("10"))

    def test_cannot_complete_empty_sheet(self):
        create = self.client.post(
            "/api/production-sheets/",
            {
                "branch": self.bakery.id,
                "production_date": "2026-07-28",
            },
            format="json",
        )
        response = self.client.post(
            f"/api/production-sheets/{create.data['id']}/complete/",
            {},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("no quantities", response.data["detail"].lower())

    def test_list_production_sheets(self):
        self.client.post(
            "/api/production-sheets/",
            {
                "branch": self.bakery.id,
                "production_date": "2026-07-27",
            },
            format="json",
        )
        response = self.client.get(f"/api/production-sheets/?branch={self.bakery.id}")
        self.assertEqual(response.status_code, 200)
        results = response.data["results"] if "results" in response.data else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["lines"], [])
        self.assertEqual(results[0]["line_count"], 2)

    def test_multiple_sheets_same_day_allowed(self):
        today = str(date.today())
        first = self.client.post(
            "/api/production-sheets/",
            {"branch": self.bakery.id, "production_date": today},
            format="json",
        )
        self.assertEqual(first.status_code, 201)
        croissant_line = next(
            line for line in first.data["lines"]
            if line["product"] == self.croissant.id
        )
        self.client.patch(
            f"/api/production-sheets/{first.data['id']}/lines/",
            {
                "lines": [
                    {
                        "id": croissant_line["id"],
                        "allocations": [
                            {"destination_branch": self.highlands.id, "quantity": "5"},
                            {"destination_branch": self.churchill.id, "quantity": "0"},
                            {"destination_branch": self.stores.id, "quantity": "0"},
                        ],
                    }
                ]
            },
            format="json",
        )
        complete_first = self.client.post(
            f"/api/production-sheets/{first.data['id']}/complete/",
            {},
        )
        self.assertEqual(complete_first.status_code, 200)

        second = self.client.post(
            "/api/production-sheets/",
            {"branch": self.bakery.id, "production_date": today},
            format="json",
        )
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(second.data["id"], first.data["id"])

        list_response = self.client.get(f"/api/production-sheets/?branch={self.bakery.id}")
        results = (
            list_response.data["results"]
            if "results" in list_response.data
            else list_response.data
        )
        today_sheets = [sheet for sheet in results if sheet["production_date"] == today]
        self.assertEqual(len(today_sheets), 2)
        self.assertEqual(
            sum(1 for sheet in today_sheets if sheet["status"] == ProductionSheetStatus.COMPLETED),
            1,
        )
        self.assertEqual(
            sum(1 for sheet in today_sheets if sheet["status"] == ProductionSheetStatus.DRAFT),
            1,
        )
