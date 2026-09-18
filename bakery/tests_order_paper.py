from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile, StaffRole
from bakery.models import OrderPaperStatus, ProductionSheetStatus, Recipe
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from inventory.models import BranchInventory

User = get_user_model()


class OrderPaperFlowTests(TestCase):
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
        self.stores = Branch.objects.filter(branch_type=BranchType.STORES).first()
        if self.stores is None:
            self.stores = Branch.objects.create(
                name="Central Stores",
                branch_type=BranchType.STORES,
                code="STR",
            )

        self.manager = User.objects.create_user(username="hig-manager", password="pass")
        StaffProfile.objects.create(
            user=self.manager,
            branch=self.highlands,
            role=StaffRole.BRANCH_MANAGER,
        )
        self.stores_user = User.objects.create_user(username="stores-user", password="pass")
        StaffProfile.objects.create(
            user=self.stores_user,
            branch=self.stores,
            role=StaffRole.BRANCH_MANAGER,
        )
        self.baker = User.objects.create_user(username="baker", password="pass")
        StaffProfile.objects.create(
            user=self.baker,
            branch=self.bakery,
            role=StaffRole.BAKER,
        )

        pastries = ProductCategory.objects.create(name="Breads & pastries")
        ingredients = ProductCategory.objects.create(name="Ingredients")
        self.croissant = Product.objects.create(
            name="Almond Croissants",
            category=pastries,
            selling_price=Decimal("2.75"),
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
        self.needed = (date.today() + timedelta(days=1)).isoformat()

    def test_branch_and_stores_can_submit_order_papers(self):
        self.client.force_login(self.manager)
        branch_resp = self.client.post(
            "/api/order-papers/",
            {
                "requesting_branch": self.highlands.id,
                "bakery": self.bakery.id,
                "needed_date": self.needed,
                "submit": True,
                "lines": [
                    {"product": self.croissant.id, "quantity_requested": "12"},
                ],
            },
            format="json",
        )
        self.assertEqual(branch_resp.status_code, 201, branch_resp.content)
        self.assertEqual(branch_resp.data["status"], OrderPaperStatus.SUBMITTED)

        self.client.force_login(self.stores_user)
        stores_resp = self.client.post(
            "/api/order-papers/",
            {
                "requesting_branch": self.stores.id,
                "bakery": self.bakery.id,
                "needed_date": self.needed,
                "submit": True,
                "lines": [
                    {"product": self.croissant.id, "quantity_requested": "20"},
                ],
            },
            format="json",
        )
        self.assertEqual(stores_resp.status_code, 201, stores_resp.content)
        self.assertEqual(stores_resp.data["status"], OrderPaperStatus.SUBMITTED)

    def test_bakery_creates_production_sheet_from_order_papers(self):
        self.client.force_login(self.manager)
        hig = self.client.post(
            "/api/order-papers/",
            {
                "requesting_branch": self.highlands.id,
                "bakery": self.bakery.id,
                "needed_date": self.needed,
                "submit": True,
                "lines": [
                    {"product": self.croissant.id, "quantity_requested": "12"},
                ],
            },
            format="json",
        )
        self.client.force_login(self.stores_user)
        stores = self.client.post(
            "/api/order-papers/",
            {
                "requesting_branch": self.stores.id,
                "bakery": self.bakery.id,
                "needed_date": self.needed,
                "submit": True,
                "lines": [
                    {"product": self.croissant.id, "quantity_requested": "8"},
                ],
            },
            format="json",
        )

        self.client.force_login(self.baker)
        demand = self.client.get(
            f"/api/order-papers/demand/?needed_date={self.needed}&bakery={self.bakery.id}"
        )
        self.assertEqual(demand.status_code, 200)
        self.assertEqual(demand.data["paper_count"], 2)
        self.assertEqual(Decimal(str(demand.data["product_totals"][0]["quantity"])), Decimal("20"))

        sheet_resp = self.client.post(
            "/api/production-sheets/from-order-papers/",
            {
                "branch": self.bakery.id,
                "production_date": self.needed,
                "order_paper_ids": [hig.data["id"], stores.data["id"]],
            },
            format="json",
        )
        self.assertEqual(sheet_resp.status_code, 201, sheet_resp.content)
        self.assertEqual(sheet_resp.data["status"], ProductionSheetStatus.DRAFT)

        croissant_line = next(
            line
            for line in sheet_resp.data["lines"]
            if line["product"] == self.croissant.id
        )
        by_dest = {
            row["destination_branch"]: Decimal(str(row["quantity"] or 0))
            for row in croissant_line["allocations"]
        }
        self.assertEqual(by_dest[self.highlands.id], Decimal("12"))
        self.assertEqual(by_dest[self.stores.id], Decimal("8"))

        paper = self.client.get(f"/api/order-papers/{hig.data['id']}/")
        self.assertEqual(paper.data["status"], OrderPaperStatus.ACCEPTED)
        self.assertEqual(paper.data["production_sheet"], sheet_resp.data["id"])

    def test_branch_cannot_see_other_branch_papers(self):
        self.client.force_login(self.manager)
        self.client.post(
            "/api/order-papers/",
            {
                "requesting_branch": self.highlands.id,
                "bakery": self.bakery.id,
                "needed_date": self.needed,
                "submit": True,
                "lines": [
                    {"product": self.croissant.id, "quantity_requested": "5"},
                ],
            },
            format="json",
        )
        other = User.objects.create_user(username="other-mgr", password="pass")
        other_branch = Branch.objects.create(
            name="Other Branch",
            branch_type=BranchType.BRANCH,
            code="OTH",
        )
        StaffProfile.objects.create(
            user=other,
            branch=other_branch,
            role=StaffRole.BRANCH_MANAGER,
        )
        self.client.force_login(other)
        listing = self.client.get("/api/order-papers/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data.get("results", listing.data)), 0)
