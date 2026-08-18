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
    StockMovement,
    StockMovementReason,
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

    def test_partial_receive_credits_damaged_back_to_bakery(self):
        self.client.force_authenticate(user=self.baker)
        create_response = self.client.post(
            "/api/delivery-notes/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.branch.id,
                "lines": [{"product": self.croissant.id, "quantity": "7"}],
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        note_id = create_response.data["id"]
        line_id = create_response.data["lines"][0]["id"]

        bakery_after_send = BranchInventory.objects.get(
            branch=self.bakery,
            product=self.croissant,
        )
        self.assertEqual(bakery_after_send.quantity, Decimal("43"))

        self.client.force_authenticate(user=self.cashier)
        approve_response = self.client.post(
            f"/api/delivery-notes/{note_id}/approve/",
            {
                "remarks": "2 crushed in transit",
                "is_flagged": True,
                "lines": [
                    {
                        "id": line_id,
                        "received_quantity": "5",
                        "damaged_quantity": "2",
                        "notes": "crushed packaging",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.data["status"], StockTransferStatus.DELIVERED)
        self.assertTrue(approve_response.data["is_flagged"])
        self.assertEqual(approve_response.data["remarks"], "2 crushed in transit")
        line = approve_response.data["lines"][0]
        self.assertEqual(Decimal(line["received_quantity"]), Decimal("5"))
        self.assertEqual(Decimal(line["damaged_quantity"]), Decimal("2"))
        self.assertEqual(Decimal(line["returned_quantity"]), Decimal("2"))

        branch_stock = BranchInventory.objects.get(
            branch=self.branch,
            product=self.croissant,
        )
        bakery_stock = BranchInventory.objects.get(
            branch=self.bakery,
            product=self.croissant,
        )
        self.assertEqual(branch_stock.quantity, Decimal("5"))
        self.assertEqual(bakery_stock.quantity, Decimal("45"))

        from inventory.models import StockMovement, StockMovementReason

        returns = StockMovement.objects.filter(
            branch=self.bakery,
            product=self.croissant,
            reason=StockMovementReason.DELIVERY_RETURN,
            reference_id=note_id,
        )
        self.assertEqual(returns.count(), 1)
        self.assertEqual(returns.first().delta, Decimal("2"))

    def test_partial_receive_rejects_over_sent_quantity(self):
        self.client.force_authenticate(user=self.baker)
        create_response = self.client.post(
            "/api/delivery-notes/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.branch.id,
                "lines": [{"product": self.croissant.id, "quantity": "7"}],
            },
            format="json",
        )
        note_id = create_response.data["id"]
        line_id = create_response.data["lines"][0]["id"]

        self.client.force_authenticate(user=self.cashier)
        response = self.client.post(
            f"/api/delivery-notes/{note_id}/approve/",
            {
                "lines": [
                    {
                        "id": line_id,
                        "received_quantity": "6",
                        "damaged_quantity": "2",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

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

    def test_hq_admin_incoming_filter_returns_all_branch_notes(self):
        other_branch = Branch.objects.create(
            name="Borrowdale",
            branch_type=BranchType.BRANCH,
        )
        note_for_branch = DeliveryNote.objects.create(
            from_branch=self.bakery,
            to_branch=self.branch,
            status=StockTransferStatus.DISPATCHED,
        )
        note_for_other = DeliveryNote.objects.create(
            from_branch=self.bakery,
            to_branch=other_branch,
            status=StockTransferStatus.DISPATCHED,
        )
        hq_admin = User.objects.create_user(username="hqboss", password="pass")
        StaffProfile.objects.create(
            user=hq_admin,
            branch=self.branch,
            role=StaffRole.HQ_ADMIN,
        )

        self.client.force_authenticate(user=hq_admin)
        response = self.client.get("/api/delivery-notes/?incoming=true")
        self.assertEqual(response.status_code, 200)
        note_ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(note_ids, {note_for_branch.id, note_for_other.id})

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

    def test_rejects_insufficient_stock_on_create(self):
        self.client.force_authenticate(user=self.baker)
        response = self.client.post(
            "/api/delivery-notes/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.stores.id,
                "lines": [{"product": self.croissant.id, "quantity": "999"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Insufficient stock", response.data["detail"])
        self.assertEqual(response.data["available"], "50.00")
        self.assertEqual(response.data["requested"], "999.00")
        self.assertFalse(
            DeliveryNote.objects.filter(
                from_branch=self.bakery,
                to_branch=self.stores,
                lines__product=self.croissant,
                lines__quantity=Decimal("999"),
            ).exists()
        )

    def test_rejects_inactive_product_on_create(self):
        self.croissant.is_active = False
        self.croissant.save(update_fields=["is_active"])
        self.client.force_authenticate(user=self.baker)
        response = self.client.post(
            "/api/delivery-notes/from-bakery/",
            {
                "from_branch": self.bakery.id,
                "to_branch": self.stores.id,
                "lines": [{"product": self.croissant.id, "quantity": "5"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("inactive product", str(response.data).lower())

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
        self.assertContains(response, "Print 80mm")

        thermal_response = self.client.get(
            f"/transfers/delivery-note/{note.id}/print/?paper=80mm"
        )
        self.assertEqual(thermal_response.status_code, 200)
        self.assertContains(thermal_response, "size: 80mm auto")
        self.assertContains(thermal_response, 'class="paper-80mm"')


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
        branch_ingredients = ProductCategory.objects.create(name="Branch Ingredients")
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
        branch_flour = Product.objects.create(
            name="Branch Flour",
            category=branch_ingredients,
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
        BranchInventory.objects.create(
            branch=self.stores,
            product=branch_flour,
            quantity=Decimal("30"),
        )
        self.flour = flour
        self.branch_flour = branch_flour

    def test_create_stores_delivery_note_assigns_invoice(self):
        self.client.force_authenticate(user=self.stores_clerk)
        response = self.client.post(
            "/api/delivery-notes/from-stores/",
            {
                "from_branch": self.stores.id,
                "to_branch": self.branch.id,
                "lines": [{"product": self.branch_flour.id, "quantity": "6"}],
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
                "lines": [{"product": self.branch_flour.id, "quantity": "6"}],
            },
            format="json",
        )
        note_id = create_response.data["id"]

        approve_response = self.client.post(f"/api/delivery-notes/{note_id}/approve/")
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.data["status"], "delivered")

        stores_stock = BranchInventory.objects.get(
            branch=self.stores,
            product=self.branch_flour,
        )
        branch_stock = BranchInventory.objects.get(
            branch=self.branch,
            product=self.branch_flour,
        )
        self.assertEqual(stores_stock.quantity, Decimal("24"))
        self.assertEqual(branch_stock.quantity, Decimal("6"))

    def test_stores_to_bakery_workflow_updates_inventory(self):
        bakery = Branch.objects.create(
            name="Central Bakery",
            branch_type=BranchType.BAKERY,
            code="BAK",
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

        approve_response = self.client.post(f"/api/delivery-notes/{note_id}/approve/")
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.data["status"], "delivered")

        bakery_stock = BranchInventory.objects.get(
            branch=bakery,
            product=self.flour,
        )
        self.assertEqual(bakery_stock.quantity, Decimal("4"))
        stores_stock = BranchInventory.objects.get(
            branch=self.stores,
            product=self.flour,
        )
        self.assertEqual(stores_stock.quantity, Decimal("26"))

    def test_stores_to_bakery_accepts_branch_ingredients(self):
        """Central Bakery can receive Branch Ingredients from Central Stores."""
        bakery = Branch.objects.create(
            name="Central Bakery",
            branch_type=BranchType.BAKERY,
            code="CBK",
        )

        self.client.force_authenticate(user=self.stores_clerk)
        create_response = self.client.post(
            "/api/delivery-notes/from-stores/",
            {
                "from_branch": self.stores.id,
                "to_branch": bakery.id,
                "lines": [{"product": self.branch_flour.id, "quantity": "5"}],
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        note_id = create_response.data["id"]

        approve_response = self.client.post(f"/api/delivery-notes/{note_id}/approve/")
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.data["status"], "delivered")

        bakery_stock = BranchInventory.objects.get(
            branch=bakery,
            product=self.branch_flour,
        )
        self.assertEqual(bakery_stock.quantity, Decimal("5"))
        stores_stock = BranchInventory.objects.get(
            branch=self.stores,
            product=self.branch_flour,
        )
        self.assertEqual(stores_stock.quantity, Decimal("25"))

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
                "lines": [{"product": self.branch_flour.id, "quantity": "3"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["payment_status"], "unpaid")


class BranchTransferTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch_a = Branch.objects.create(
            name="Highland",
            branch_type=BranchType.BRANCH,
            code="HIG",
        )
        self.branch_b = Branch.objects.create(
            name="Churchill",
            branch_type=BranchType.BRANCH,
            code="CHU",
        )
        self.stores = Branch.objects.create(
            name="Central Stores",
            branch_type=BranchType.STORES,
            code="STR",
        )
        self.cashier = User.objects.create_user(username="cashier_a", password="pass")
        StaffProfile.objects.create(
            user=self.cashier,
            branch=self.branch_a,
            role=StaffRole.CASHIER,
            pos_access=True,
        )
        self.manager = User.objects.create_user(username="manager_a", password="pass")
        StaffProfile.objects.create(
            user=self.manager,
            branch=self.branch_a,
            role=StaffRole.BRANCH_MANAGER,
        )
        self.cashier_b = User.objects.create_user(username="cashier_b", password="pass")
        StaffProfile.objects.create(
            user=self.cashier_b,
            branch=self.branch_b,
            role=StaffRole.CASHIER,
            pos_access=True,
        )
        self.hq_admin = User.objects.create_user(username="hqboss", password="pass")
        StaffProfile.objects.create(
            user=self.hq_admin,
            branch=self.branch_a,
            role=StaffRole.HQ_ADMIN,
        )
        category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso Beans",
            category=category,
            selling_price=Decimal("5.00"),
        )
        BranchInventory.objects.create(
            branch=self.branch_a,
            product=self.product,
            quantity=Decimal("20"),
        )

    def test_branch_to_branch_workflow_deducts_on_dispatch(self):
        self.client.force_authenticate(user=self.cashier)
        create_response = self.client.post(
            "/api/delivery-notes/from-branch/",
            {
                "from_branch": self.branch_a.id,
                "to_branch": self.branch_b.id,
                "lines": [{"product": self.product.id, "quantity": "5"}],
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data["status"], "requested")
        note_id = create_response.data["id"]

        source = BranchInventory.objects.get(branch=self.branch_a, product=self.product)
        self.assertEqual(source.quantity, Decimal("20"))

        approve_response = self.client.post(f"/api/delivery-notes/{note_id}/approve/")
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.data["status"], "approved")
        source.refresh_from_db()
        self.assertEqual(source.quantity, Decimal("20"))

        dispatch_response = self.client.post(f"/api/delivery-notes/{note_id}/dispatch/")
        self.assertEqual(dispatch_response.status_code, 200)
        self.assertEqual(dispatch_response.data["status"], "dispatched")
        source.refresh_from_db()
        self.assertEqual(source.quantity, Decimal("15"))
        self.assertFalse(
            BranchInventory.objects.filter(
                branch=self.branch_b, product=self.product
            ).exists()
        )

        self.client.force_authenticate(user=self.cashier_b)
        deliver_response = self.client.post(f"/api/delivery-notes/{note_id}/deliver/")
        self.assertEqual(deliver_response.status_code, 200)
        self.assertEqual(deliver_response.data["status"], "delivered")
        dest = BranchInventory.objects.get(branch=self.branch_b, product=self.product)
        self.assertEqual(dest.quantity, Decimal("5"))

    def test_cashier_cannot_transfer_from_other_branch(self):
        self.client.force_authenticate(user=self.cashier_b)
        response = self.client.post(
            "/api/delivery-notes/from-branch/",
            {
                "from_branch": self.branch_a.id,
                "to_branch": self.branch_b.id,
                "lines": [{"product": self.product.id, "quantity": "2"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_transfer_to_stores(self):
        self.client.force_authenticate(user=self.cashier)
        response = self.client.post(
            "/api/delivery-notes/from-branch/",
            {
                "from_branch": self.branch_a.id,
                "to_branch": self.stores.id,
                "lines": [{"product": self.product.id, "quantity": "2"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_hq_admin_can_create_branch_transfer(self):
        self.client.force_authenticate(user=self.hq_admin)
        response = self.client.post(
            "/api/delivery-notes/from-branch/",
            {
                "from_branch": self.branch_a.id,
                "to_branch": self.branch_b.id,
                "lines": [{"product": self.product.id, "quantity": "3"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_branch_manager_can_create_branch_transfer(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.post(
            "/api/delivery-notes/from-branch/",
            {
                "from_branch": self.branch_a.id,
                "to_branch": self.branch_b.id,
                "lines": [{"product": self.product.id, "quantity": "1"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_dispatch_requires_sufficient_stock(self):
        self.client.force_authenticate(user=self.cashier)
        create_response = self.client.post(
            "/api/delivery-notes/from-branch/",
            {
                "from_branch": self.branch_a.id,
                "to_branch": self.branch_b.id,
                "lines": [{"product": self.product.id, "quantity": "25"}],
            },
            format="json",
        )
        note_id = create_response.data["id"]
        self.client.post(f"/api/delivery-notes/{note_id}/approve/")
        dispatch_response = self.client.post(f"/api/delivery-notes/{note_id}/dispatch/")
        self.assertEqual(dispatch_response.status_code, 400)
        source = BranchInventory.objects.get(branch=self.branch_a, product=self.product)
        self.assertEqual(source.quantity, Decimal("20"))


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


class OrderAddonRecipeConsumptionTests(TestCase):
    def setUp(self):
        from catalog.models import MenuAddon, MenuAddonGroup, ProductMenuAddonGroup
        from payments.models import Currency, CurrencyRate

        self.client = APIClient()
        self.branch = Branch.objects.create(
            name="Addon Branch",
            code="ADB",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        self.user = User.objects.create_user(username="addon-cashier", password="pass")
        StaffProfile.objects.create(
            user=self.user,
            branch=self.branch,
            role=StaffRole.CASHIER,
            pos_access=True,
        )
        self.client.force_authenticate(user=self.user)

        self.menu_category = ProductCategory.objects.create(name="Coffee")
        self.ingredient_category = ProductCategory.objects.create(name="Ingredients")
        self.latte = Product.objects.create(
            name="Latte",
            category=self.menu_category,
            selling_price=Decimal("4.00"),
        )
        self.oat_milk = Product.objects.create(
            name="Oat Milk Stock",
            category=self.ingredient_category,
            selling_price=Decimal("2.00"),
        )
        self.group = MenuAddonGroup.objects.create(name="Addon Recipe Extras")
        self.addon = MenuAddon.objects.create(
            group=self.group,
            name="Add Oat Milk Stock Test",
            selling_price=Decimal("1.00"),
        )
        ProductMenuAddonGroup.objects.create(product=self.latte, group=self.group)
        Recipe.objects.create(
            menu_addon=self.addon,
            ingredient=self.oat_milk,
            quantity_required=Decimal("0.15"),
        )
        BranchInventory.objects.create(
            branch=self.branch,
            product=self.oat_milk,
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

    def test_pay_deducts_addon_recipe_ingredients(self):
        from orders.models import OrderItemAddon

        order = Order.objects.create(branch=self.branch)
        item = order.items.create(
            product=self.latte,
            quantity=Decimal("2"),
            price=self.latte.selling_price,
        )
        OrderItemAddon.objects.create(
            order_item=item,
            menu_addon=self.addon,
            name=self.addon.name,
            price=self.addon.selling_price,
        )
        order.recalculate_total()

        response = self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        milk = BranchInventory.objects.get(branch=self.branch, product=self.oat_milk)
        # 2 drinks * 0.15 oat milk = 0.30 deducted from 1.00
        self.assertEqual(milk.quantity, Decimal("0.70"))


class WastageRecordingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
            code="AVO",
        )
        self.bakery = Branch.objects.create(
            name="Central Bakery",
            branch_type=BranchType.BAKERY,
            code="BAK",
        )
        category = ProductCategory.objects.create(name="Pastries")
        self.product = Product.objects.create(
            name="Croissant",
            category=category,
            selling_price=Decimal("2.50"),
        )
        BranchInventory.objects.create(
            branch=self.branch,
            product=self.product,
            quantity=Decimal("20"),
        )
        self.admin = User.objects.create_user(
            username="wastage_admin",
            password="pass",
        )
        StaffProfile.objects.create(
            user=self.admin,
            role=StaffRole.HQ_ADMIN,
            branch=self.branch,
        )
        self.client.force_authenticate(user=self.admin)

    def test_disposal_subtracts_source_stock_when_processed(self):
        response = self.client.post(
            "/api/wastage/",
            {
                "branch": self.branch.id,
                "product": self.product.id,
                "quantity": "3",
                "reason": "disposal",
                "process_now": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "processed")
        self.assertEqual(response.data["reason"], "disposal")

        stock = BranchInventory.objects.get(branch=self.branch, product=self.product)
        self.assertEqual(stock.quantity, Decimal("17"))

        movement = StockMovement.objects.filter(
            branch=self.branch,
            product=self.product,
            reason=StockMovementReason.WASTAGE,
        ).latest("id")
        self.assertEqual(movement.delta, Decimal("-3"))
        self.assertIn("disposal", movement.note.lower())

    def test_bakery_reuse_transfers_stock_to_bakery(self):
        response = self.client.post(
            "/api/wastage/",
            {
                "branch": self.branch.id,
                "product": self.product.id,
                "quantity": "5",
                "reason": "bakery_reuse",
                "destination_branch": self.bakery.id,
                "process_now": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "processed")

        source = BranchInventory.objects.get(branch=self.branch, product=self.product)
        bakery_stock = BranchInventory.objects.get(
            branch=self.bakery, product=self.product
        )
        self.assertEqual(source.quantity, Decimal("15"))
        self.assertEqual(bakery_stock.quantity, Decimal("5"))

    def test_kitchen_reason_subtracts_without_destination_credit(self):
        response = self.client.post(
            "/api/wastage/",
            {
                "branch": self.branch.id,
                "product": self.product.id,
                "quantity": "2",
                "reason": "kitchen",
                "notes": "staff meal prep",
                "process_now": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        source = BranchInventory.objects.get(branch=self.branch, product=self.product)
        self.assertEqual(source.quantity, Decimal("18"))
        self.assertFalse(
            BranchInventory.objects.filter(
                branch=self.bakery, product=self.product
            ).exists()
        )

    def test_draft_does_not_change_stock_until_processed(self):
        create = self.client.post(
            "/api/wastage/",
            {
                "branch": self.branch.id,
                "product": self.product.id,
                "quantity": "4",
                "reason": "disposal",
                "process_now": False,
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201, create.data)
        self.assertEqual(create.data["status"], "draft")
        stock = BranchInventory.objects.get(branch=self.branch, product=self.product)
        self.assertEqual(stock.quantity, Decimal("20"))

        process = self.client.post(f"/api/wastage/{create.data['id']}/process/", {})
        self.assertEqual(process.status_code, 200, process.data)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal("16"))

    def test_bakery_reuse_requires_bakery_destination(self):
        response = self.client.post(
            "/api/wastage/",
            {
                "branch": self.branch.id,
                "product": self.product.id,
                "quantity": "1",
                "reason": "bakery_reuse",
                "process_now": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_insufficient_stock_rejects_process(self):
        response = self.client.post(
            "/api/wastage/",
            {
                "branch": self.branch.id,
                "product": self.product.id,
                "quantity": "50",
                "reason": "disposal",
                "process_now": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        stock = BranchInventory.objects.get(branch=self.branch, product=self.product)
        self.assertEqual(stock.quantity, Decimal("20"))

    def test_summary_groups_by_reason(self):
        for reason, qty in (("disposal", "3"), ("kitchen", "2"), ("bakery_reuse", "1")):
            payload = {
                "branch": self.branch.id,
                "product": self.product.id,
                "quantity": qty,
                "reason": reason,
                "process_now": True,
            }
            if reason == "bakery_reuse":
                payload["destination_branch"] = self.bakery.id
            created = self.client.post("/api/wastage/", payload, format="json")
            self.assertEqual(created.status_code, 201, created.data)

        summary = self.client.get("/api/wastage/summary/")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data["count"], 3)
        self.assertEqual(summary.data["by_reason"]["disposal"]["quantity"], "3.00")
        self.assertEqual(summary.data["by_reason"]["kitchen"]["quantity"], "2.00")
        self.assertEqual(summary.data["by_reason"]["bakery_reuse"]["quantity"], "1.00")
