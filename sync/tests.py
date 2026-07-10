from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from inventory.models import BranchInventory
from orders.models import Order, OrderStatus
from payments.models import Currency

from .models import SyncedClientOrder

User = get_user_model()


class DesktopSyncTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Highland",
            code="HIG",
            branch_type=BranchType.BRANCH,
            is_active=True,
        )
        self.category = ProductCategory.objects.create(name="Drinks")
        self.product = Product.objects.create(
            name="Espresso",
            category=self.category,
            selling_price=Decimal("3.50"),
            is_active=True,
        )
        self.base_currency = Currency.objects.create(
            name="USD",
            code="USD",
            symbol="$",
            is_base=True,
            is_active=True,
        )

        self.cashier = User.objects.create_user(
            username="cashier1",
            password="pass1234",
        )
        from accounts.models import StaffProfile, StaffRole

        StaffProfile.objects.create(
            user=self.cashier,
            branch=self.branch,
            role=StaffRole.CASHIER,
            pos_access=True,
        )
        self.token = Token.objects.create(user=self.cashier)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_ping(self):
        response = self.client.get("/api/sync/ping/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])

    def test_pull_catalog(self):
        response = self.client.get("/api/sync/pull/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["branch"]["id"], self.branch.id)
        self.assertEqual(len(response.data["products"]), 1)
        self.assertEqual(len(response.data["currencies"]), 1)

    def test_pull_catalog_excludes_non_sellable_products(self):
        ingredients = ProductCategory.objects.create(name="Ingredients")
        assets = ProductCategory.objects.create(name="Cutlery", is_asset=True)
        components = ProductCategory.objects.create(name="Components")
        bakery = ProductCategory.objects.create(name="Breads & pastries")
        Product.objects.create(
            name="Coffee Beans",
            category=ingredients,
            selling_price=Decimal("5.00"),
            is_active=True,
        )
        Product.objects.create(
            name="Spoon",
            category=assets,
            selling_price=Decimal("1.00"),
            is_active=True,
        )
        Product.objects.create(
            name="Pastry Cream",
            category=components,
            selling_price=Decimal("0"),
            is_active=True,
        )
        Product.objects.create(
            name="Croissant",
            category=bakery,
            selling_price=Decimal("2.75"),
            is_active=True,
        )

        response = self.client.get("/api/sync/pull/")
        self.assertEqual(response.status_code, 200)
        product_names = {p["name"] for p in response.data["products"]}
        self.assertEqual(product_names, {"Espresso", "Croissant"})
        category_names = {c["name"] for c in response.data["categories"]}
        self.assertEqual(category_names, {"Drinks", "Breads & pastries"})

    def test_push_open_order_then_payment(self):
        client_id = "660e8400-e29b-41d4-a716-446655440001"
        open_payload = {
            "orders": [
                {
                    "client_id": client_id,
                    "order_type": "takeaway",
                    "items": [{"product_id": self.product.id, "quantity": "1"}],
                }
            ]
        }
        first = self.client.post("/api/sync/push/", open_payload, format="json")
        self.assertEqual(first.status_code, 200)
        order = Order.objects.get()
        self.assertEqual(order.status, OrderStatus.OPEN)
        self.assertFalse(order.receipt_number)

        paid_payload = {
            "orders": [
                {
                    "client_id": client_id,
                    "order_type": "takeaway",
                    "items": [{"product_id": self.product.id, "quantity": "1"}],
                    "payment": {"currency_id": self.base_currency.id},
                }
            ]
        }
        second = self.client.post("/api/sync/push/", paid_payload, format="json")
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["results"][0]["already_synced"])
        self.assertTrue(second.data["results"][0]["receipt_number"])

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertTrue(order.receipt_number)
        self.assertEqual(Order.objects.count(), 1)

    def test_push_order_idempotent(self):
        payload = {
            "orders": [
                {
                    "client_id": "550e8400-e29b-41d4-a716-446655440000",
                    "order_type": "takeaway",
                    "items": [{"product_id": self.product.id, "quantity": "2"}],
                    "payment": {"currency_id": self.base_currency.id},
                }
            ]
        }
        first = self.client.post("/api/sync/push/", payload, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["results"][0]["server_id"], Order.objects.first().id)
        self.assertTrue(first.data["results"][0]["receipt_number"])

        second = self.client.post("/api/sync/push/", payload, format="json")
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["results"][0]["already_synced"])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(SyncedClientOrder.objects.count(), 1)

    def test_hq_admin_cannot_use_desktop_sync(self):
        hq_branch = Branch.objects.create(
            name="HQ",
            branch_type=BranchType.HQ,
            is_active=True,
        )
        admin = User.objects.create_user(username="hqadmin", password="pass1234")
        from accounts.models import StaffProfile, StaffRole

        StaffProfile.objects.create(
            user=admin,
            branch=hq_branch,
            role=StaffRole.HQ_ADMIN,
        )
        token = Token.objects.create(user=admin)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = client.get("/api/sync/pull/")
        self.assertEqual(response.status_code, 403)

    def test_push_paid_order_allows_negative_stock_when_branch_setting_enabled(self):
        bakery_category = ProductCategory.objects.create(name="Breads & pastries")
        brioche = Product.objects.create(
            name="120G Brioche rolls",
            category=bakery_category,
            selling_price=Decimal("1.00"),
            is_active=True,
        )
        BranchInventory.objects.create(
            branch=self.branch,
            product=brioche,
            quantity=Decimal("0.00"),
        )
        self.branch.allow_negative_stock = True
        self.branch.save(update_fields=["allow_negative_stock"])

        client_id = "770e8400-e29b-41d4-a716-446655440002"
        payload = {
            "orders": [
                {
                    "client_id": client_id,
                    "order_type": "takeaway",
                    "items": [{"product_id": brioche.id, "quantity": "1"}],
                    "payment": {"currency_id": self.base_currency.id},
                }
            ]
        }
        response = self.client.post("/api/sync/push/", payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["results"][0]["receipt_number"])

        order = Order.objects.get()
        self.assertEqual(order.status, OrderStatus.PAID)
        stock = BranchInventory.objects.get(branch=self.branch, product=brioche)
        self.assertEqual(stock.quantity, Decimal("-1.00"))

    def test_push_reconciles_items_after_table_order_grows(self):
        latte = Product.objects.create(
            name="Latte",
            category=self.category,
            selling_price=Decimal("4.00"),
            is_active=True,
        )
        muffin = Product.objects.create(
            name="Muffin",
            category=self.category,
            selling_price=Decimal("2.50"),
            is_active=True,
        )
        client_id = "880e8400-e29b-41d4-a716-446655440003"
        open_payload = {
            "orders": [
                {
                    "client_id": client_id,
                    "order_type": "dine_in",
                    "table_number": "T10",
                    "items": [
                        {"product_id": self.product.id, "quantity": "1"},
                        {"product_id": latte.id, "quantity": "1"},
                    ],
                }
            ]
        }
        first = self.client.post("/api/sync/push/", open_payload, format="json")
        self.assertEqual(first.status_code, 200)
        order = Order.objects.get()
        self.assertEqual(order.total_amount, Decimal("7.50"))

        paid_payload = {
            "orders": [
                {
                    "client_id": client_id,
                    "order_type": "dine_in",
                    "table_number": "T10",
                    "items": [
                        {"product_id": self.product.id, "quantity": "1"},
                        {"product_id": latte.id, "quantity": "1"},
                        {"product_id": muffin.id, "quantity": "2"},
                    ],
                    "payment": {"currency_id": self.base_currency.id},
                }
            ]
        }
        second = self.client.post("/api/sync/push/", paid_payload, format="json")
        self.assertEqual(second.status_code, 200, second.data)

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertEqual(order.total_amount, Decimal("12.50"))
        self.assertEqual(order.items.count(), 3)

    def test_push_consolidates_sibling_table_orders_before_payment(self):
        latte = Product.objects.create(
            name="Latte",
            category=self.category,
            selling_price=Decimal("4.00"),
            is_active=True,
        )
        client_id = "990e8400-e29b-41d4-a716-446655440004"
        primary = Order.objects.create(
            branch=self.branch,
            order_type="dine_in",
            table_number="T12",
        )
        primary.items.create(
            product=self.product,
            quantity=Decimal("1"),
            price=self.product.selling_price,
        )
        primary.recalculate_total()
        SyncedClientOrder.objects.create(client_id=client_id, order=primary)

        sibling = Order.objects.create(
            branch=self.branch,
            order_type="dine_in",
            table_number="T12",
        )
        sibling.items.create(
            product=latte,
            quantity=Decimal("1"),
            price=latte.selling_price,
        )
        sibling.recalculate_total()

        paid_payload = {
            "orders": [
                {
                    "client_id": client_id,
                    "order_type": "dine_in",
                    "table_number": "T12",
                    "items": [
                        {"product_id": self.product.id, "quantity": "1"},
                        {"product_id": latte.id, "quantity": "1"},
                    ],
                    "payment": {"currency_id": self.base_currency.id},
                }
            ]
        }
        response = self.client.post("/api/sync/push/", paid_payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)

        primary.refresh_from_db()
        self.assertEqual(primary.status, OrderStatus.PAID)
        self.assertEqual(primary.total_amount, Decimal("7.50"))
        self.assertFalse(Order.objects.filter(pk=sibling.pk).exists())
