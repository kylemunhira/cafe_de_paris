from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile, StaffRole
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from inventory.models import (
    BranchInventory,
    DeliveryNote,
    StockTransfer,
    StockTransferStatus,
)

User = get_user_model()


class InventoryTransferWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.hq = Branch.objects.create(
            name="HQ",
            branch_type=BranchType.HQ,
        )
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso",
            category=category,
            selling_price=Decimal("3.50"),
        )
        BranchInventory.objects.create(
            branch=self.hq,
            product=self.product,
            quantity=Decimal("100"),
        )

    def test_full_transfer_workflow_updates_inventory(self):
        create_response = self.client.post(
            "/api/transfers/",
            {
                "from_branch": self.hq.id,
                "to_branch": self.branch.id,
                "product": self.product.id,
                "quantity": "20",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        transfer_id = create_response.data["id"]
        self.assertEqual(create_response.data["status"], StockTransferStatus.REQUESTED)

        self.client.post(f"/api/transfers/{transfer_id}/approve/")
        self.client.post(f"/api/transfers/{transfer_id}/dispatch/")
        deliver_response = self.client.post(f"/api/transfers/{transfer_id}/deliver/")
        self.assertEqual(deliver_response.status_code, 200)
        self.assertEqual(
            deliver_response.data["status"],
            StockTransferStatus.DELIVERED,
        )

        hq_inventory = BranchInventory.objects.get(branch=self.hq, product=self.product)
        branch_inventory = BranchInventory.objects.get(
            branch=self.branch,
            product=self.product,
        )
        self.assertEqual(hq_inventory.quantity, Decimal("80"))
        self.assertEqual(branch_inventory.quantity, Decimal("20"))

    def test_dispatch_fails_when_insufficient_stock(self):
        transfer = StockTransfer.objects.create(
            from_branch=self.hq,
            to_branch=self.branch,
            product=self.product,
            quantity=Decimal("150"),
            status=StockTransferStatus.APPROVED,
        )
        response = self.client.post(f"/api/transfers/{transfer.id}/dispatch/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Insufficient stock", response.data["detail"])

    def test_cancel_only_allowed_before_dispatch(self):
        transfer = StockTransfer.objects.create(
            from_branch=self.hq,
            to_branch=self.branch,
            product=self.product,
            quantity=Decimal("10"),
            status=StockTransferStatus.REQUESTED,
        )
        cancel_response = self.client.post(f"/api/transfers/{transfer.id}/cancel/")
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.data["status"], StockTransferStatus.CANCELLED)

    def test_inventory_adjust_endpoint(self):
        response = self.client.post(
            "/api/inventory/adjust/",
            {
                "branch": self.branch.id,
                "product": self.product.id,
                "delta": "15",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["quantity"], "15.00")

    def test_low_stock_filter(self):
        BranchInventory.objects.create(
            branch=self.branch,
            product=self.product,
            quantity=Decimal("5"),
        )
        response = self.client.get("/api/inventory/?low_stock=true&threshold=10")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["branch"], self.branch.id)


class BakeryTransferTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.bakery = Branch.objects.create(
            name="Central Bakery",
            branch_type=BranchType.BAKERY,
        )
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        self.hq = Branch.objects.create(
            name="HQ",
            branch_type=BranchType.HQ,
        )
        category = ProductCategory.objects.create(name="Pastries")
        self.product = Product.objects.create(
            name="Croissant",
            category=category,
            selling_price=Decimal("2.75"),
        )
        BranchInventory.objects.create(
            branch=self.bakery,
            product=self.product,
            quantity=Decimal("50"),
        )

    def test_bakery_to_branch_transfer_workflow(self):
        create_response = self.client.post(
            "/api/transfers/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.branch.id,
                "product": self.product.id,
                "quantity": "12",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        transfer_id = create_response.data["id"]

        self.client.post(f"/api/transfers/{transfer_id}/approve/")
        self.client.post(f"/api/transfers/{transfer_id}/dispatch/")
        deliver_response = self.client.post(f"/api/transfers/{transfer_id}/deliver/")
        self.assertEqual(deliver_response.status_code, 200)

        bakery_stock = BranchInventory.objects.get(
            branch=self.bakery,
            product=self.product,
        )
        branch_stock = BranchInventory.objects.get(
            branch=self.branch,
            product=self.product,
        )
        self.assertEqual(bakery_stock.quantity, Decimal("38"))
        self.assertEqual(branch_stock.quantity, Decimal("12"))

    def test_rejects_transfer_from_non_bakery(self):
        response = self.client.post(
            "/api/transfers/from-bakery/",
            {
                "from_branch": self.hq.id,
                "to_branch": self.branch.id,
                "product": self.product.id,
                "quantity": "5",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("bakery", str(response.data).lower())

    def test_bakery_to_hq_transfer(self):
        response = self.client.post(
            "/api/transfers/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.hq.id,
                "product": self.product.id,
                "quantity": "5",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["to_branch"], self.hq.id)

    def test_rejects_transfer_to_bakery(self):
        other_bakery = Branch.objects.create(
            name="North Bakery",
            branch_type=BranchType.BAKERY,
        )
        response = self.client.post(
            "/api/transfers/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": other_bakery.id,
                "product": self.product.id,
                "quantity": "5",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("branch", str(response.data).lower())

    def test_bakery_only_filter(self):
        StockTransfer.objects.create(
            from_branch=self.bakery,
            to_branch=self.branch,
            product=self.product,
            quantity=Decimal("5"),
        )
        StockTransfer.objects.create(
            from_branch=self.bakery,
            to_branch=self.hq,
            product=self.product,
            quantity=Decimal("3"),
        )
        StockTransfer.objects.create(
            from_branch=self.hq,
            to_branch=self.branch,
            product=self.product,
            quantity=Decimal("5"),
        )
        response = self.client.get("/api/transfers/?bakery_only=true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        from_branches = {row["from_branch"] for row in response.data["results"]}
        self.assertEqual(from_branches, {self.bakery.id})


class DeliveryNoteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.bakery = Branch.objects.create(
            name="Central Bakery",
            branch_type=BranchType.BAKERY,
        )
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        self.baker = User.objects.create_user(username="baker", password="pass")
        StaffProfile.objects.create(
            user=self.baker,
            branch=self.bakery,
            role=StaffRole.BAKER,
        )
        self.cashier = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(
            user=self.cashier,
            branch=self.branch,
            role=StaffRole.CASHIER,
        )
        pastries = ProductCategory.objects.create(name="Pastries")
        coffee = ProductCategory.objects.create(name="Coffee")
        self.croissant = Product.objects.create(
            name="Croissant",
            category=pastries,
            selling_price=Decimal("2.75"),
        )
        self.muffin = Product.objects.create(
            name="Muffin",
            category=pastries,
            selling_price=Decimal("2.75"),
        )
        self.espresso = Product.objects.create(
            name="Espresso",
            category=coffee,
            selling_price=Decimal("3.50"),
        )
        for product in (self.croissant, self.muffin):
            BranchInventory.objects.create(
                branch=self.bakery,
                product=product,
                quantity=Decimal("50"),
            )

    def test_create_multi_product_delivery_note(self):
        self.client.force_authenticate(user=self.baker)
        response = self.client.post(
            "/api/delivery-notes/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.branch.id,
                "lines": [
                    {"product": self.croissant.id, "quantity": "12"},
                    {"product": self.muffin.id, "quantity": "8"},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["line_count"], 2)
        self.assertEqual(len(response.data["lines"]), 2)
        self.assertEqual(response.data["status"], StockTransferStatus.REQUESTED)

    def test_branch_staff_cannot_create_delivery_note(self):
        self.client.force_authenticate(user=self.cashier)
        response = self.client.post(
            "/api/delivery-notes/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.branch.id,
                "lines": [{"product": self.croissant.id, "quantity": "5"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_full_delivery_note_workflow_updates_inventory(self):
        self.client.force_authenticate(user=self.baker)
        create_response = self.client.post(
            "/api/delivery-notes/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.branch.id,
                "lines": [
                    {"product": self.croissant.id, "quantity": "10"},
                    {"product": self.muffin.id, "quantity": "5"},
                ],
            },
            format="json",
        )
        note_id = create_response.data["id"]

        self.client.post(f"/api/delivery-notes/{note_id}/approve/")
        self.client.post(f"/api/delivery-notes/{note_id}/dispatch/")

        self.client.force_authenticate(user=self.cashier)
        deliver_response = self.client.post(f"/api/delivery-notes/{note_id}/deliver/")
        self.assertEqual(deliver_response.status_code, 200)

        croissant_bakery = BranchInventory.objects.get(
            branch=self.bakery,
            product=self.croissant,
        )
        muffin_bakery = BranchInventory.objects.get(
            branch=self.bakery,
            product=self.muffin,
        )
        croissant_branch = BranchInventory.objects.get(
            branch=self.branch,
            product=self.croissant,
        )
        muffin_branch = BranchInventory.objects.get(
            branch=self.branch,
            product=self.muffin,
        )
        self.assertEqual(croissant_bakery.quantity, Decimal("40"))
        self.assertEqual(muffin_bakery.quantity, Decimal("45"))
        self.assertEqual(croissant_branch.quantity, Decimal("10"))
        self.assertEqual(muffin_branch.quantity, Decimal("5"))

    def test_bakery_cannot_confirm_receipt(self):
        note = DeliveryNote.objects.create(
            from_branch=self.bakery,
            to_branch=self.branch,
            status=StockTransferStatus.DISPATCHED,
        )
        note.lines.create(product=self.croissant, quantity=Decimal("6"))
        self.client.force_authenticate(user=self.baker)
        response = self.client.post(f"/api/delivery-notes/{note.id}/deliver/")
        self.assertEqual(response.status_code, 403)

    def test_incoming_filter_returns_only_destination_branch_notes(self):
        other_branch = Branch.objects.create(
            name="Borrowdale",
            branch_type=BranchType.BRANCH,
        )
        note_for_branch = DeliveryNote.objects.create(
            from_branch=self.bakery,
            to_branch=self.branch,
            status=StockTransferStatus.DISPATCHED,
        )
        DeliveryNote.objects.create(
            from_branch=self.bakery,
            to_branch=other_branch,
            status=StockTransferStatus.DISPATCHED,
        )

        self.client.force_authenticate(user=self.cashier)
        response = self.client.get("/api/delivery-notes/?incoming=true")
        self.assertEqual(response.status_code, 200)
        note_ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(note_ids, {note_for_branch.id})

    def test_rejects_empty_delivery_note(self):
        self.client.force_authenticate(user=self.baker)
        response = self.client.post(
            "/api/delivery-notes/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.branch.id,
                "lines": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_duplicate_products_in_delivery_note(self):
        self.client.force_authenticate(user=self.baker)
        response = self.client.post(
            "/api/delivery-notes/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.branch.id,
                "lines": [
                    {"product": self.croissant.id, "quantity": "5"},
                    {"product": self.croissant.id, "quantity": "3"},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_delivery_note_print_page(self):
        self.client.force_login(self.baker)
        note = DeliveryNote.objects.create(
            from_branch=self.bakery,
            to_branch=self.branch,
        )
        note.lines.create(product=self.croissant, quantity=Decimal("6"))
        response = self.client.get(f"/transfers/delivery-note/{note.id}/print/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delivery Note")
        self.assertContains(response, "Croissant")
        self.assertContains(response, "DN-")
