from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from catalog.menu_addons import seed_menu_addons
from catalog.models import MenuAddon, MenuAddonGroup, Product, ProductCategory, ProductMenuAddonGroup
from catalog.pos_catalog import pos_catalog_products
from orders.models import Order, OrderItemAddon

User = get_user_model()


class MenuAddonSeedTests(TestCase):
    def test_seed_menu_addons_creates_groups_and_links(self):
        coffee_category = ProductCategory.objects.create(name="Coffee")
        Product.objects.create(
            name="Cafe Latte (Tall)",
            category=coffee_category,
            selling_price=Decimal("4"),
        )

        seed_menu_addons(link_products=True)

        self.assertTrue(MenuAddonGroup.objects.filter(name="Coffee Extras").exists())
        self.assertTrue(MenuAddon.objects.filter(name="Add Oat Milk").exists())
        self.assertTrue(ProductMenuAddonGroup.objects.exists())


class PosCatalogAddonExclusionTests(TestCase):
    def test_pos_catalog_excludes_extras_category_and_add_prefix_products(self):
        extras = ProductCategory.objects.create(name="Extras")
        coffee = ProductCategory.objects.create(name="Coffee")
        Product.objects.create(name="Add Hot Milk", category=extras, selling_price=Decimal("1"))
        Product.objects.create(name="Add Oat Milk", category=coffee, selling_price=Decimal("1"))
        latte = Product.objects.create(
            name="Cafe Latte (Tall)",
            category=coffee,
            selling_price=Decimal("4"),
        )

        names = {product.name for product in pos_catalog_products()}
        self.assertIn(latte.name, names)
        self.assertNotIn("Add Hot Milk", names)
        self.assertNotIn("Add Oat Milk", names)


class MenuAddonActivationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        seed_menu_addons(link_products=False)
        self.addon = MenuAddon.objects.get(name="Add Oat Milk")

    def test_patch_can_deactivate_and_reactivate_addon(self):
        response = self.client.patch(
            f"/api/menu-addons/{self.addon.id}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])
        self.addon.refresh_from_db()
        self.assertFalse(self.addon.is_active)

        response = self.client.patch(
            f"/api/menu-addons/{self.addon.id}/",
            {"is_active": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_active"])


class OrderAddonCreateTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        from branches.models import Branch, BranchType

        self.branch = Branch.objects.create(
            name="Test Branch",
            code="TST",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        self.user = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(user=self.user, branch=self.branch, pos_access=True)
        self.client.force_authenticate(user=self.user)
        category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Cafe Latte (Tall)",
            category=category,
            selling_price=Decimal("4"),
        )
        seed_menu_addons(link_products=True)
        self.addon = MenuAddon.objects.get(name="Add Oat Milk")

    def test_create_order_with_addons_updates_total(self):
        response = self.client.post(
            "/api/orders/",
            {
                "branch": self.branch.id,
                "order_type": "takeaway",
                "items": [
                    {
                        "product_id": self.product.id,
                        "quantity": "1",
                        "addon_ids": [self.addon.id],
                        "notes": "Extra hot",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.total_amount, Decimal("5.00"))
        item = order.items.get()
        self.assertEqual(item.notes, "Extra hot")
        self.assertEqual(item.addons.count(), 1)
        self.assertEqual(OrderItemAddon.objects.filter(order_item=item).first().name, "Add Oat Milk")

    def test_rejects_addon_not_linked_to_product(self):
        other_category = ProductCategory.objects.create(name="Cakes ")
        other_product = Product.objects.create(
            name="Chocolate Cake",
            category=other_category,
            selling_price=Decimal("30"),
        )
        response = self.client.post(
            "/api/orders/",
            {
                "branch": self.branch.id,
                "order_type": "takeaway",
                "items": [
                    {
                        "product_id": other_product.id,
                        "quantity": "1",
                        "addon_ids": [self.addon.id],
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class PosCatalogCategoryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.drinks = ProductCategory.objects.create(name="Drinks")
        self.ingredients = ProductCategory.objects.create(name="Ingredients")
        self.assets = ProductCategory.objects.create(name="Cutlery", is_asset=True)
        Product.objects.create(
            name="Espresso",
            category=self.drinks,
            selling_price=Decimal("3.50"),
            is_active=True,
        )
        Product.objects.create(
            name="Coffee Beans",
            category=self.ingredients,
            selling_price=Decimal("5.00"),
            is_active=True,
        )
        Product.objects.create(
            name="Spoon",
            category=self.assets,
            selling_price=Decimal("1.00"),
            is_active=True,
        )

    def test_categories_pos_catalog_filter_matches_sellable_categories(self):
        response = self.client.get("/api/categories/?pos_catalog=true")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertEqual(names, {"Drinks"})

    def test_categories_without_filter_returns_all(self):
        response = self.client.get("/api/categories/")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertEqual(names, {"Cutlery", "Drinks", "Ingredients"})
