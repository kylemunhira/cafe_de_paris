from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile, StaffRole
from bakery.models import Recipe
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from orders.models import Order, OrderStatus
from payments.models import Currency, CurrencyRate
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
        self.stores = Branch.objects.create(
            name="Central Stores",
            branch_type=BranchType.STORES,
            code="STR",
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
                "to_branch": self.stores.id,
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
        stores_inventory = BranchInventory.objects.get(
            branch=self.stores,
            product=self.product,
        )
        self.assertEqual(hq_inventory.quantity, Decimal("80"))
        self.assertEqual(stores_inventory.quantity, Decimal("20"))

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

    def test_dispatch_still_blocks_negative_when_branch_allows_negative_sales(self):
        self.hq.allow_negative_stock = True
        self.hq.save(update_fields=["allow_negative_stock"])
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

    def test_inventory_set_endpoint(self):
        BranchInventory.objects.create(
            branch=self.branch,
            product=self.product,
            quantity=Decimal("10"),
        )
        response = self.client.post(
            "/api/inventory/set/",
            {
                "branch": self.branch.id,
                "product": self.product.id,
                "quantity": "42.5",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["quantity"], "42.50")
        self.assertEqual(
            BranchInventory.objects.get(
                branch=self.branch, product=self.product
            ).quantity,
            Decimal("42.50"),
        )

    def test_inventory_set_rejects_negative(self):
        response = self.client.post(
            "/api/inventory/set/",
            {
                "branch": self.branch.id,
                "product": self.product.id,
                "quantity": "-1",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_inventory_adjust_creates_stock_movement(self):
        from inventory.models import StockMovement, StockMovementReason

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
        movement = StockMovement.objects.get(
            branch=self.branch, product=self.product
        )
        self.assertEqual(movement.delta, Decimal("15"))
        self.assertEqual(movement.quantity_before, Decimal("0"))
        self.assertEqual(movement.quantity_after, Decimal("15"))
        self.assertEqual(movement.reason, StockMovementReason.MANUAL_ADD)

    def test_inventory_movements_endpoint(self):
        from inventory.models import StockMovement, StockMovementReason

        StockMovement.objects.create(
            branch=self.branch,
            product=self.product,
            quantity_before=Decimal("0"),
            delta=Decimal("10"),
            quantity_after=Decimal("10"),
            reason=StockMovementReason.MANUAL_ADD,
        )
        response = self.client.get(
            f"/api/inventory/movements/?branch={self.branch.id}&product={self.product.id}"
        )
        self.assertEqual(response.status_code, 200)
        results = response.data["results"] if "results" in response.data else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["delta"], "10.00")
        self.assertEqual(results[0]["reason"], StockMovementReason.MANUAL_ADD)

    def test_inventory_movements_requires_branch_and_product(self):
        response = self.client.get("/api/inventory/movements/")
        self.assertEqual(response.status_code, 400)

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

    def test_category_filter(self):
        ingredients = ProductCategory.objects.create(name="Ingredients")
        ingredient = Product.objects.create(
            name="Flour",
            category=ingredients,
            selling_price=Decimal("1.00"),
        )
        BranchInventory.objects.create(
            branch=self.branch,
            product=ingredient,
            quantity=Decimal("12"),
        )
        response = self.client.get("/api/inventory/?category=Ingredients")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["product"], ingredient.id)


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
        self.stores = Branch.objects.create(
            name="Central Stores",
            branch_type=BranchType.STORES,
            code="STR",
        )
        category = ProductCategory.objects.create(name="Breads & pastries")
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
                "to_branch": self.stores.id,
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
            branch=self.stores,
            product=self.product,
        )
        self.assertEqual(bakery_stock.quantity, Decimal("38"))
        self.assertEqual(branch_stock.quantity, Decimal("12"))

    def test_rejects_transfer_from_non_bakery(self):
        response = self.client.post(
            "/api/transfers/from-bakery/",
            {
                "from_branch": self.hq.id,
                "to_branch": self.stores.id,
                "product": self.product.id,
                "quantity": "5",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("bakery", str(response.data).lower())

    def test_allows_direct_transfer_to_branch(self):
        response = self.client.post(
            "/api/transfers/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.branch.id,
                "product": self.product.id,
                "quantity": "5",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["to_branch"], self.branch.id)

    def test_rejects_transfer_to_hq(self):
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
        self.assertEqual(response.status_code, 400)
        self.assertIn("central stores or a branch", str(response.data).lower())

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

    def test_rejects_ingredient_transfer(self):
        ingredients = ProductCategory.objects.create(name="Ingredients")
        flour = Product.objects.create(
            name="Flour",
            category=ingredients,
            selling_price=Decimal("1.00"),
        )
        BranchInventory.objects.create(
            branch=self.bakery,
            product=flour,
            quantity=Decimal("100"),
        )
        response = self.client.post(
            "/api/transfers/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.stores.id,
                "product": flour.id,
                "quantity": "5",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("finished bakery", str(response.data).lower())

    def test_bakery_only_filter(self):
        StockTransfer.objects.create(
            from_branch=self.bakery,
            to_branch=self.stores,
            product=self.product,
            quantity=Decimal("5"),
        )
        StockTransfer.objects.create(
            from_branch=self.bakery,
            to_branch=self.stores,
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
            code="AVO",
        )
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
        self.cashier = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(
            user=self.cashier,
            branch=self.branch,
            role=StaffRole.CASHIER,
        )
        self.stores_clerk = User.objects.create_user(username="stores", password="pass")
        StaffProfile.objects.create(
            user=self.stores_clerk,
            branch=self.stores,
            role=StaffRole.BRANCH_MANAGER,
        )
        pastries = ProductCategory.objects.create(name="Breads & pastries")
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
                "to_branch": self.stores.id,
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
                "to_branch": self.stores.id,
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
                "to_branch": self.stores.id,
                "lines": [
                    {"product": self.croissant.id, "quantity": "10"},
                    {"product": self.muffin.id, "quantity": "5"},
                ],
            },
            format="json",
        )
        note_id = create_response.data["id"]
        self.assertEqual(create_response.data["status"], StockTransferStatus.REQUESTED)

        croissant_bakery = BranchInventory.objects.get(
            branch=self.bakery,
            product=self.croissant,
        )
        muffin_bakery = BranchInventory.objects.get(
            branch=self.bakery,
            product=self.muffin,
        )
        self.assertEqual(croissant_bakery.quantity, Decimal("40"))
        self.assertEqual(muffin_bakery.quantity, Decimal("45"))

        self.client.force_authenticate(user=self.stores_clerk)
        approve_response = self.client.post(f"/api/delivery-notes/{note_id}/approve/")
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.data["status"], StockTransferStatus.DELIVERED)

        croissant_stores = BranchInventory.objects.get(
            branch=self.stores,
            product=self.croissant,
        )
        muffin_stores = BranchInventory.objects.get(
            branch=self.stores,
            product=self.muffin,
        )
        self.assertEqual(croissant_stores.quantity, Decimal("10"))
        self.assertEqual(muffin_stores.quantity, Decimal("5"))

    def test_bakery_to_branch_delivery_note_workflow(self):
        self.client.force_authenticate(user=self.baker)
        create_response = self.client.post(
            "/api/delivery-notes/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.branch.id,
                "lines": [{"product": self.croissant.id, "quantity": "6"}],
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        note_id = create_response.data["id"]

        bakery_stock = BranchInventory.objects.get(
            branch=self.bakery,
            product=self.croissant,
        )
        self.assertEqual(bakery_stock.quantity, Decimal("44"))

        self.client.force_authenticate(user=self.cashier)
        approve_response = self.client.post(f"/api/delivery-notes/{note_id}/approve/")
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.data["status"], StockTransferStatus.DELIVERED)

        branch_stock = BranchInventory.objects.get(
            branch=self.branch,
            product=self.croissant,
        )
        self.assertEqual(branch_stock.quantity, Decimal("6"))

    def test_bakery_cannot_approve_incoming_to_branch(self):
        self.client.force_authenticate(user=self.baker)
        create_response = self.client.post(
            "/api/delivery-notes/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.branch.id,
                "lines": [{"product": self.croissant.id, "quantity": "6"}],
            },
            format="json",
        )
        note_id = create_response.data["id"]
        response = self.client.post(f"/api/delivery-notes/{note_id}/approve/")
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
                "to_branch": self.stores.id,
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
                "to_branch": self.stores.id,
                "lines": [
                    {"product": self.croissant.id, "quantity": "5"},
                    {"product": self.croissant.id, "quantity": "3"},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_ingredient_in_delivery_note(self):
        ingredients = ProductCategory.objects.create(name="Ingredients")
        flour = Product.objects.create(
            name="Flour",
            category=ingredients,
            selling_price=Decimal("1.00"),
        )
        self.client.force_authenticate(user=self.baker)
        response = self.client.post(
            "/api/delivery-notes/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.stores.id,
                "lines": [{"product": flour.id, "quantity": "5"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("finished bakery", str(response.data).lower())

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
        self.assertContains(response, "cafe-de-paris-logo.png")
        self.assertContains(response, "size: A4")


class StoresTransferTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.stores = Branch.objects.create(
            name="Central Stores",
            branch_type=BranchType.STORES,
            code="STR",
        )
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
            code="AVO",
        )
        self.stores_clerk = User.objects.create_user(username="stores", password="pass")
        StaffProfile.objects.create(
            user=self.stores_clerk,
            branch=self.stores,
            role=StaffRole.HQ_ADMIN,
        )
        self.cashier = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(
            user=self.cashier,
            branch=self.branch,
            role=StaffRole.CASHIER,
        )
        pastries = ProductCategory.objects.create(name="Breads & pastries")
        ingredients = ProductCategory.objects.create(name="Ingredients")
        self.croissant = Product.objects.create(
            name="Croissant",
            category=pastries,
            selling_price=Decimal("2.75"),
        )
        flour = Product.objects.create(
            name="Flour",
            category=ingredients,
            selling_price=Decimal("1.00"),
        )
        Recipe.objects.create(
            product=self.croissant,
            ingredient=flour,
            quantity_required=Decimal("1.50"),
        )
        BranchInventory.objects.create(
            branch=self.stores,
            product=flour,
            quantity=Decimal("30"),
        )
        self.flour = flour

    def test_create_stores_delivery_note_assigns_invoice(self):
        self.client.force_authenticate(user=self.stores_clerk)
        response = self.client.post(
            "/api/delivery-notes/from-stores/",
            {
                "from_branch": self.stores.id,
                "to_branch": self.branch.id,
                "lines": [{"product": self.flour.id, "quantity": "6"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["invoice_number"])
        self.assertEqual(response.data["lines"][0]["unit_price"], "1.00")
        self.assertEqual(response.data["total_amount"], "6.00")

    def test_create_stores_delivery_note_rejects_bakery_products(self):
        self.client.force_authenticate(user=self.stores_clerk)
        response = self.client.post(
            "/api/delivery-notes/from-stores/",
            {
                "from_branch": self.stores.id,
                "to_branch": self.branch.id,
                "lines": [{"product": self.croissant.id, "quantity": "6"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_stores_to_branch_workflow_updates_inventory(self):
        self.client.force_authenticate(user=self.stores_clerk)
        create_response = self.client.post(
            "/api/delivery-notes/from-stores/",
            {
                "from_branch": self.stores.id,
                "to_branch": self.branch.id,
                "lines": [{"product": self.flour.id, "quantity": "6"}],
            },
            format="json",
        )
        note_id = create_response.data["id"]

        self.client.post(f"/api/delivery-notes/{note_id}/approve/")
        self.client.post(f"/api/delivery-notes/{note_id}/dispatch/")

        self.client.force_authenticate(user=self.cashier)
        deliver_response = self.client.post(f"/api/delivery-notes/{note_id}/deliver/")
        self.assertEqual(deliver_response.status_code, 200)

        stores_stock = BranchInventory.objects.get(
            branch=self.stores,
            product=self.flour,
        )
        branch_stock = BranchInventory.objects.get(
            branch=self.branch,
            product=self.flour,
        )
        self.assertEqual(stores_stock.quantity, Decimal("24"))
        self.assertEqual(branch_stock.quantity, Decimal("6"))

    def test_stores_to_bakery_workflow_updates_inventory(self):
        bakery = Branch.objects.create(
            name="Central Bakery",
            branch_type=BranchType.BAKERY,
            code="BAK",
        )
        bakery_clerk = User.objects.create_user(username="baker", password="pass")
        StaffProfile.objects.create(
            user=bakery_clerk,
            branch=bakery,
            role=StaffRole.BRANCH_MANAGER,
        )

        self.client.force_authenticate(user=self.stores_clerk)
        create_response = self.client.post(
            "/api/delivery-notes/from-stores/",
            {
                "from_branch": self.stores.id,
                "to_branch": bakery.id,
                "lines": [{"product": self.flour.id, "quantity": "4"}],
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        note_id = create_response.data["id"]

        self.client.post(f"/api/delivery-notes/{note_id}/approve/")
        self.client.post(f"/api/delivery-notes/{note_id}/dispatch/")

        self.client.force_authenticate(user=bakery_clerk)
        deliver_response = self.client.post(f"/api/delivery-notes/{note_id}/deliver/")
        self.assertEqual(deliver_response.status_code, 200)

        bakery_stock = BranchInventory.objects.get(
            branch=bakery,
            product=self.flour,
        )
        self.assertEqual(bakery_stock.quantity, Decimal("4"))

    def test_transfer_invoice_print_page(self):
        self.client.force_login(self.stores_clerk)
        note = DeliveryNote.objects.create(
            from_branch=self.stores,
            to_branch=self.branch,
            invoice_number="STRAVO00001",
        )
        note.lines.create(
            product=self.flour,
            quantity=Decimal("6"),
            unit_price=Decimal("1.00"),
        )
        response = self.client.get(f"/transfers/invoice/{note.id}/print/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "STRAVO00001")
        self.assertContains(response, "Flour")
        self.assertContains(response, "Unpaid")
        self.assertContains(response, "cafe-de-paris-logo.png")

    def test_mark_transfer_invoice_paid(self):
        self.client.force_authenticate(user=self.stores_clerk)
        note = DeliveryNote.objects.create(
            from_branch=self.stores,
            to_branch=self.branch,
            invoice_number="STRAVO00002",
        )
        note.lines.create(
            product=self.flour,
            quantity=Decimal("2"),
            unit_price=Decimal("1.00"),
        )

        response = self.client.post(f"/api/delivery-notes/{note.id}/mark-paid/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["payment_status"], "paid")
        self.assertIsNotNone(response.data["paid_at"])
        self.assertEqual(response.data["paid_by_name"], self.stores_clerk.username)

        note.refresh_from_db()
        self.assertEqual(note.payment_status, "paid")
        self.assertEqual(note.paid_by, self.stores_clerk)

        duplicate = self.client.post(f"/api/delivery-notes/{note.id}/mark-paid/")
        self.assertEqual(duplicate.status_code, 400)

    def test_branch_staff_cannot_mark_transfer_invoice_paid(self):
        self.client.force_authenticate(user=self.cashier)
        note = DeliveryNote.objects.create(
            from_branch=self.stores,
            to_branch=self.branch,
            invoice_number="STRAVO00003",
        )
        response = self.client.post(f"/api/delivery-notes/{note.id}/mark-paid/")
        self.assertEqual(response.status_code, 403)

    def test_create_stores_delivery_note_defaults_unpaid(self):
        self.client.force_authenticate(user=self.stores_clerk)
        response = self.client.post(
            "/api/delivery-notes/from-stores/",
            {
                "from_branch": self.stores.id,
                "to_branch": self.branch.id,
                "lines": [{"product": self.flour.id, "quantity": "3"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["payment_status"], "unpaid")


class OrderRecipeConsumptionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(
            name="Test Branch",
            code="TST",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        self.user = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(
            user=self.user,
            branch=self.branch,
            role=StaffRole.CASHIER,
            pos_access=True,
        )
        self.client.force_authenticate(user=self.user)
        self.menu_category = ProductCategory.objects.create(name="Coffee")
        self.ingredient_category = ProductCategory.objects.create(name="Ingredients")
        self.beans = Product.objects.create(
            name="Coffee Beans",
            category=self.ingredient_category,
            selling_price=Decimal("10.00"),
        )
        self.milk = Product.objects.create(
            name="Milk",
            category=self.ingredient_category,
            selling_price=Decimal("2.00"),
        )
        self.espresso = Product.objects.create(
            name="Espresso",
            category=self.menu_category,
            selling_price=Decimal("3.50"),
        )
        Recipe.objects.create(
            product=self.espresso,
            ingredient=self.beans,
            quantity_required=Decimal("0.02"),
        )
        Recipe.objects.create(
            product=self.espresso,
            ingredient=self.milk,
            quantity_required=Decimal("0.10"),
        )
        BranchInventory.objects.create(
            branch=self.branch,
            product=self.beans,
            quantity=Decimal("1.00"),
        )
        BranchInventory.objects.create(
            branch=self.branch,
            product=self.milk,
            quantity=Decimal("1.00"),
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

    def _create_order(self, quantity="2"):
        order = Order.objects.create(branch=self.branch)
        order.items.create(
            product=self.espresso,
            quantity=Decimal(quantity),
            price=self.espresso.selling_price,
        )
        order.recalculate_total()
        return order

    def test_pay_deducts_recipe_ingredients(self):
        order = self._create_order(quantity="2")
        response = self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        beans = BranchInventory.objects.get(branch=self.branch, product=self.beans)
        milk = BranchInventory.objects.get(branch=self.branch, product=self.milk)
        self.assertEqual(beans.quantity, Decimal("0.96"))
        self.assertEqual(milk.quantity, Decimal("0.80"))

    def test_pay_blocked_when_ingredients_insufficient(self):
        BranchInventory.objects.filter(
            branch=self.branch,
            product=self.beans,
        ).update(quantity=Decimal("0.01"))
        order = self._create_order(quantity="2")
        response = self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Insufficient stock", response.data["detail"])
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.OPEN)

    def test_pay_deducts_bakery_product_stock_not_ingredients(self):
        bakery_category = ProductCategory.objects.create(name="Breads & pastries")
        flour = Product.objects.create(
            name="Flour",
            category=self.ingredient_category,
            selling_price=Decimal("1.00"),
        )
        pie = Product.objects.create(
            name="Meat Pie",
            category=bakery_category,
            selling_price=Decimal("3.00"),
        )
        Recipe.objects.create(
            product=pie,
            ingredient=flour,
            quantity_required=Decimal("0.20"),
        )
        BranchInventory.objects.create(
            branch=self.branch,
            product=flour,
            quantity=Decimal("10.00"),
        )
        BranchInventory.objects.create(
            branch=self.branch,
            product=pie,
            quantity=Decimal("5.00"),
        )

        order = Order.objects.create(branch=self.branch)
        order.items.create(product=pie, quantity=Decimal("2"), price=pie.selling_price)
        order.recalculate_total()

        response = self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        pie_stock = BranchInventory.objects.get(branch=self.branch, product=pie)
        flour_stock = BranchInventory.objects.get(branch=self.branch, product=flour)
        self.assertEqual(pie_stock.quantity, Decimal("3.00"))
        self.assertEqual(flour_stock.quantity, Decimal("10.00"))

    def test_pay_blocked_when_bakery_product_stock_insufficient(self):
        bakery_category = ProductCategory.objects.create(name="Savory")
        pie = Product.objects.create(
            name="Chicken Pie",
            category=bakery_category,
            selling_price=Decimal("3.00"),
        )
        BranchInventory.objects.create(
            branch=self.branch,
            product=pie,
            quantity=Decimal("1.00"),
        )

        order = Order.objects.create(branch=self.branch)
        order.items.create(product=pie, quantity=Decimal("2"), price=pie.selling_price)
        order.recalculate_total()

        response = self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Insufficient stock", response.data["detail"])
        self.assertIn("Chicken Pie", response.data["detail"])
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.OPEN)

    def test_pay_allows_negative_stock_when_branch_setting_enabled(self):
        bakery_category = ProductCategory.objects.create(name="Breads & pastries")
        brioche = Product.objects.create(
            name="120G Brioche rolls",
            category=bakery_category,
            selling_price=Decimal("1.00"),
        )
        BranchInventory.objects.create(
            branch=self.branch,
            product=brioche,
            quantity=Decimal("0.00"),
        )
        self.branch.allow_negative_stock = True
        self.branch.save(update_fields=["allow_negative_stock"])

        order = Order.objects.create(branch=self.branch)
        order.items.create(
            product=brioche,
            quantity=Decimal("1.00"),
            price=brioche.selling_price,
        )
        order.recalculate_total()

        response = self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        stock = BranchInventory.objects.get(branch=self.branch, product=brioche)
        self.assertEqual(stock.quantity, Decimal("-1.00"))
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PAID)

    def test_pay_without_recipe_does_not_require_stock(self):
        latte = Product.objects.create(
            name="Latte",
            category=self.menu_category,
            selling_price=Decimal("4.00"),
        )
        order = Order.objects.create(branch=self.branch)
        order.items.create(product=latte, quantity=Decimal("1"), price=latte.selling_price)
        order.recalculate_total()

        response = self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PAID)
