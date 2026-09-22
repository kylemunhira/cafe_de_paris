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
        self.hq = Branch.objects.create(
            name="HQ",
            branch_type=BranchType.HQ,
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
        self.hq_admin = User.objects.create_user(username="hq-admin", password="pass")
        StaffProfile.objects.create(
            user=self.hq_admin,
            branch=self.hq,
            role=StaffRole.HQ_ADMIN,
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

    def _submit_paper(self, user, requesting_branch, qty):
        self.client.force_login(user)
        return self.client.post(
            "/api/order-papers/",
            {
                "requesting_branch": requesting_branch.id,
                "bakery": self.bakery.id,
                "needed_date": self.needed,
                "submit": True,
                "lines": [
                    {"product": self.croissant.id, "quantity_requested": str(qty)},
                ],
            },
            format="json",
        )

    def test_branch_and_stores_can_submit_order_papers(self):
        branch_resp = self._submit_paper(self.manager, self.highlands, "12")
        self.assertEqual(branch_resp.status_code, 201, branch_resp.content)
        self.assertEqual(branch_resp.data["status"], OrderPaperStatus.SUBMITTED)

        stores_resp = self._submit_paper(self.stores_user, self.stores, "20")
        self.assertEqual(stores_resp.status_code, 201, stores_resp.content)
        self.assertEqual(stores_resp.data["status"], OrderPaperStatus.SUBMITTED)

    def test_bakery_cannot_see_submitted_papers_until_back_office_approves(self):
        hig = self._submit_paper(self.manager, self.highlands, "12")
        self.assertEqual(hig.status_code, 201, hig.content)

        self.client.force_login(self.baker)
        listing = self.client.get("/api/order-papers/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data.get("results", listing.data)), 0)

        demand = self.client.get(
            f"/api/order-papers/demand/?needed_date={self.needed}&bakery={self.bakery.id}"
        )
        self.assertEqual(demand.status_code, 200)
        self.assertEqual(demand.data["paper_count"], 0)

        accept = self.client.post(f"/api/order-papers/{hig.data['id']}/accept/", {}, format="json")
        self.assertEqual(accept.status_code, 404)

        self.client.force_login(self.hq_admin)
        approved = self.client.post(
            f"/api/order-papers/{hig.data['id']}/approve/",
            {},
            format="json",
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.data["status"], OrderPaperStatus.APPROVED)

        self.client.force_login(self.baker)
        listing = self.client.get("/api/order-papers/")
        self.assertEqual(listing.status_code, 200)
        results = listing.data.get("results", listing.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], OrderPaperStatus.APPROVED)

        demand = self.client.get(
            f"/api/order-papers/demand/?needed_date={self.needed}&bakery={self.bakery.id}"
        )
        self.assertEqual(demand.status_code, 200)
        self.assertEqual(demand.data["paper_count"], 1)

    def test_bakery_creates_production_sheet_from_order_papers(self):
        hig = self._submit_paper(self.manager, self.highlands, "12")
        stores = self._submit_paper(self.stores_user, self.stores, "8")

        self.client.force_login(self.hq_admin)
        for paper in (hig, stores):
            approved = self.client.post(
                f"/api/order-papers/{paper.data['id']}/approve/",
                {},
                format="json",
            )
            self.assertEqual(approved.status_code, 200, approved.content)

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
        self._submit_paper(self.manager, self.highlands, "5")
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

    def test_baker_cannot_approve_order_papers(self):
        hig = self._submit_paper(self.manager, self.highlands, "5")
        self.client.force_login(self.baker)
        # Baker cannot see submitted papers, so approve is not available.
        resp = self.client.post(
            f"/api/order-papers/{hig.data['id']}/approve/",
            {},
            format="json",
        )
        self.assertIn(resp.status_code, (403, 404))

    def test_back_office_can_edit_submitted_order_paper_lines(self):
        pastry = ProductCategory.objects.get(name="Breads & pastries")
        baguette = Product.objects.create(
            name="Baguette",
            category=pastry,
            selling_price=Decimal("1.50"),
        )
        submitted = self._submit_paper(self.manager, self.highlands, "12")
        paper_id = submitted.data["id"]

        self.client.force_login(self.hq_admin)
        updated = self.client.patch(
            f"/api/order-papers/{paper_id}/",
            {
                "notes": "Reduced croissants, added baguettes",
                "lines": [
                    {"product": self.croissant.id, "quantity_requested": "8"},
                    {"product": baguette.id, "quantity_requested": "10"},
                ],
            },
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.data["status"], OrderPaperStatus.SUBMITTED)
        self.assertEqual(updated.data["notes"], "Reduced croissants, added baguettes")
        by_product = {
            row["product"]: Decimal(str(row["quantity_requested"]))
            for row in updated.data["lines"]
        }
        self.assertEqual(by_product[self.croissant.id], Decimal("8"))
        self.assertEqual(by_product[baguette.id], Decimal("10"))
        self.assertEqual(len(updated.data["lines"]), 2)

        self.client.force_login(self.manager)
        denied = self.client.patch(
            f"/api/order-papers/{paper_id}/",
            {
                "lines": [
                    {"product": self.croissant.id, "quantity_requested": "99"},
                ],
            },
            format="json",
        )
        self.assertEqual(denied.status_code, 403)