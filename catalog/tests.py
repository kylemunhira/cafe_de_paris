import io
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from catalog.csv_io import (
    export_ingredients_csv,
    export_products_csv,
    import_ingredients_csv,
    import_products_csv,
)
from catalog.menu_items_import import export_menu_items_csv
from catalog.constants import BRANCH_INGREDIENTS_CATEGORY, INGREDIENTS_CATEGORY
from catalog.models import Product, ProductCategory


class ProductCsvTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso",
            category=self.category,
            selling_price="3.50",
        )

    def test_export_includes_products(self):
        csv_text = export_products_csv()
        self.assertIn("remaining_qty", csv_text)
        self.assertIn("tax_rate", csv_text)
        self.assertIn("Espresso", csv_text)
        self.assertIn("Coffee", csv_text)

    def test_import_creates_product(self):
        csv_file = io.BytesIO(
            b"name,category,selling_price,is_active\nLatte,Coffee,4.00,true\n"
        )
        result = import_products_csv(csv_file)
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["errors"], [])
        self.assertTrue(Product.objects.filter(name="Latte").exists())

    def test_import_updates_case_insensitive_name_match(self):
        csv_file = io.BytesIO(
            b"name,category,selling_price,is_active\nESPRESSO,Coffee,4.00,true\n"
        )
        result = import_products_csv(csv_file)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["errors"], [])
        self.assertEqual(Product.objects.filter(name__iexact="espresso").count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "ESPRESSO")
        self.assertEqual(self.product.selling_price, Decimal("4.00"))

    def test_import_updates_by_id(self):
        csv_file = io.BytesIO(
            f"id,name,category,selling_price,is_active\n"
            f"{self.product.id},Espresso Double,Coffee,4.50,false\n".encode()
        )
        result = import_products_csv(csv_file)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Espresso Double")
        self.assertFalse(self.product.is_active)

    def test_import_rolls_back_on_error(self):
        csv_file = io.BytesIO(
            b"name,category,selling_price\nGood Product,Coffee,3.00\n,Tea,2.00\n"
        )
        result = import_products_csv(csv_file)
        self.assertEqual(len(result["errors"]), 1)
        self.assertFalse(Product.objects.filter(name="Good Product").exists())

    def test_export_endpoint(self):
        response = self.client.get("/api/products/export-csv/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(b"Espresso", response.content)

    def test_import_endpoint(self):
        csv_content = b"name,category,selling_price\nCappuccino,Coffee,3.75\n"
        upload = io.BytesIO(csv_content)
        upload.name = "products.csv"
        response = self.client.post(
            "/api/products/import-csv/",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created"], 1)
        self.assertTrue(Product.objects.filter(name="Cappuccino").exists())


class BakeryTransferProductFilterTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.bakery_category = ProductCategory.objects.create(name="Breads & pastries")
        self.component_category = ProductCategory.objects.create(name="Components")
        self.coffee_category = ProductCategory.objects.create(name="Coffee")
        self.croissant = Product.objects.create(
            name="Croissant",
            category=self.bakery_category,
            selling_price="2.75",
        )
        Product.objects.create(
            name="Pastry Cream",
            category=self.component_category,
            selling_price="0",
        )
        Product.objects.create(
            name="Espresso",
            category=self.coffee_category,
            selling_price="3.50",
        )

    def test_bakery_transfer_filter_returns_sellable_bakery_products_only(self):
        response = self.client.get("/api/products/?bakery_transfer=true")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertEqual(names, {"Croissant"})

    def test_bakery_manufactured_filter_includes_components(self):
        response = self.client.get("/api/products/?bakery_manufactured=true")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertEqual(names, {"Croissant", "Pastry Cream"})

    def test_exclude_bakery_filter_omits_bakery_categories(self):
        response = self.client.get("/api/products/?exclude_bakery=true")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertEqual(names, {"Espresso"})

    def test_pos_catalog_includes_bakery_finished_goods(self):
        response = self.client.get("/api/products/?pos_catalog=true")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertEqual(names, {"Croissant", "Espresso"})

    def test_pos_catalog_excludes_components(self):
        response = self.client.get("/api/products/?pos_catalog=true")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertNotIn("Pastry Cream", names)

    def test_pos_catalog_excludes_inactive_products(self):
        self.croissant.is_active = False
        self.croissant.save(update_fields=["is_active"])
        response = self.client.get("/api/products/?pos_catalog=true")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertEqual(names, {"Espresso"})

    def test_bakery_manufactured_excludes_inactive_products(self):
        self.croissant.is_active = False
        self.croissant.save(update_fields=["is_active"])
        response = self.client.get("/api/products/?bakery_manufactured=true")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertEqual(names, {"Pastry Cream"})

    def test_exclude_bakery_excludes_inactive_products(self):
        Product.objects.filter(name="Espresso").update(is_active=False)
        response = self.client.get("/api/products/?exclude_bakery=true")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertEqual(names, set())


class ProductNameUniquenessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso",
            category=self.category,
            selling_price=Decimal("3.50"),
        )

    def test_create_rejects_case_insensitive_duplicate(self):
        response = self.client.post(
            "/api/products/",
            {
                "name": "ESPRESSO",
                "category": self.category.id,
                "selling_price": "4.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)
        self.assertEqual(Product.objects.filter(name__iexact="espresso").count(), 1)

    def test_create_reactivates_inactive_case_insensitive_match(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        response = self.client.post(
            "/api/products/",
            {
                "name": "espresso",
                "category": self.category.id,
                "selling_price": "4.25",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Product.objects.filter(name__iexact="espresso").count(), 1)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)
        self.assertEqual(self.product.name, "espresso")
        self.assertEqual(self.product.selling_price, Decimal("4.25"))

    def test_update_rejects_case_insensitive_duplicate(self):
        other = Product.objects.create(
            name="Latte",
            category=self.category,
            selling_price=Decimal("4.00"),
        )
        response = self.client.patch(
            f"/api/products/{other.id}/",
            {"name": "ESPRESSO"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_deactivate_allows_existing_case_insensitive_duplicate(self):
        Product.objects.create(
            name="ESPRESSO",
            category=self.category,
            selling_price=Decimal("4.00"),
        )
        response = self.client.patch(
            f"/api/products/{self.product.id}/",
            {
                "name": self.product.name,
                "category": self.category.id,
                "selling_price": "3.50",
                "is_active": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)


class IngredientCsvTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = ProductCategory.objects.create(name=INGREDIENTS_CATEGORY)
        self.ingredient = Product.objects.create(
            name="Butter",
            category=self.category,
            selling_price="8.70",
            remaining_qty="12",
        )

    def test_export_ingredients_csv(self):
        csv_text = export_ingredients_csv()
        self.assertIn("unit_cost", csv_text)
        self.assertIn("Butter", csv_text)
        self.assertNotIn("category", csv_text)

    def test_import_ingredients_csv_creates(self):
        csv_file = io.BytesIO(b"name,unit_cost,remaining_qty\nFlour,1.00,50\n")
        result = import_ingredients_csv(csv_file)
        self.assertEqual(result["created"], 1)
        product = Product.objects.get(name="Flour")
        self.assertEqual(product.category.name, INGREDIENTS_CATEGORY)

    def test_import_ingredients_csv_falls_back_to_name_when_id_missing(self):
        csv_file = io.BytesIO(b"id,name,unit_cost\n99999,Butter,9.50\n")
        result = import_ingredients_csv(csv_file)
        self.assertEqual(result["updated"], 1)
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.selling_price, Decimal("9.50"))

    def test_import_ingredients_endpoint(self):
        upload = io.BytesIO(b"name,unit_cost\nSugar,1.00\n")
        upload.name = "ingredients.csv"
        response = self.client.post(
            "/api/products/import-ingredients-csv/",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Product.objects.filter(name="Sugar").exists())

    def test_import_branch_ingredients_csv_uses_branch_category(self):
        csv_file = io.BytesIO(b"name,unit_cost,remaining_qty\n12 CM SAUCERS,10.74,15\n")
        result = import_ingredients_csv(csv_file, category_name=BRANCH_INGREDIENTS_CATEGORY)
        self.assertEqual(result["created"], 1)
        product = Product.objects.get(name="12 CM SAUCERS")
        self.assertEqual(product.category.name, BRANCH_INGREDIENTS_CATEGORY)

    def test_import_ingredients_csv_sets_branch_stock(self):
        from branches.models import Branch, BranchType
        from inventory.models import BranchInventory

        bakery = Branch.objects.create(name="Bakery", branch_type=BranchType.BAKERY)
        csv_file = io.BytesIO(b"name,unit_cost,remaining_qty\nFlour,1.00,50\n")
        result = import_ingredients_csv(csv_file, branch=bakery)
        self.assertEqual(result["created"], 1)
        product = Product.objects.get(name="Flour")
        stock = BranchInventory.objects.get(branch=bakery, product=product)
        self.assertEqual(stock.quantity, Decimal("50"))

    def test_export_ingredients_csv_uses_branch_stock(self):
        from branches.models import Branch, BranchType
        from inventory.models import BranchInventory

        bakery = Branch.objects.create(name="Bakery", branch_type=BranchType.BAKERY)
        BranchInventory.objects.create(
            branch=bakery,
            product=self.ingredient,
            quantity=Decimal("15"),
        )
        # Product.remaining_qty is still 12 — export with branch should show inventory qty
        csv_text = export_ingredients_csv(branch=bakery)
        self.assertIn("15", csv_text)
        self.assertIn("Butter", csv_text)

    def test_import_ingredients_endpoint_with_branch_sets_stock(self):
        from branches.models import Branch, BranchType
        from inventory.models import BranchInventory

        bakery = Branch.objects.create(name="Bakery", branch_type=BranchType.BAKERY)
        upload = io.BytesIO(b"name,unit_cost,remaining_qty\nSugar,1.00,20\n")
        upload.name = "ingredients.csv"
        response = self.client.post(
            "/api/products/import-ingredients-csv/",
            {"file": upload, "branch": bakery.id},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(name="Sugar")
        stock = BranchInventory.objects.get(branch=bakery, product=product)
        self.assertEqual(stock.quantity, Decimal("20"))


class DailyStockTakeFieldTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso",
            category=self.category,
            selling_price="3.50",
            daily_stock_take=True,
        )

    def test_product_api_includes_daily_stock_take(self):
        response = self.client.get(f"/api/products/{self.product.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["daily_stock_take"])

    def test_product_patch_daily_stock_take(self):
        response = self.client.patch(
            f"/api/products/{self.product.id}/",
            {"daily_stock_take": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertFalse(self.product.daily_stock_take)


class BranchIngredientFilterTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        bakery_cat = ProductCategory.objects.create(name=INGREDIENTS_CATEGORY)
        branch_cat = ProductCategory.objects.create(name=BRANCH_INGREDIENTS_CATEGORY)
        self.bakery_ingredient = Product.objects.create(
            name="Flour",
            category=bakery_cat,
            selling_price="1.00",
        )
        self.branch_ingredient = Product.objects.create(
            name="12 CM SAUCERS",
            category=branch_cat,
            selling_price="10.74",
        )
        from branches.models import Branch, BranchType

        self.bakery = Branch.objects.create(name="Bakery", branch_type=BranchType.BAKERY)
        self.stores = Branch.objects.create(name="Stores", branch_type=BranchType.STORES)
        self.outlet = Branch.objects.create(name="Avondale", branch_type=BranchType.BRANCH)

    def test_for_branch_bakery_excludes_branch_ingredients(self):
        response = self.client.get(f"/api/products/?for_branch={self.bakery.id}")
        names = {item["name"] for item in response.data["results"]}
        self.assertIn("Flour", names)
        self.assertNotIn("12 CM SAUCERS", names)

    def test_for_branch_outlet_excludes_bakery_ingredients(self):
        response = self.client.get(f"/api/products/?for_branch={self.outlet.id}")
        names = {item["name"] for item in response.data["results"]}
        self.assertIn("12 CM SAUCERS", names)
        self.assertNotIn("Flour", names)

    def test_for_branch_ignores_null_string(self):
        response = self.client.get("/api/products/?for_branch=null")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertIn("Flour", names)
        self.assertIn("12 CM SAUCERS", names)

    def test_for_branch_stores_includes_both(self):
        response = self.client.get(f"/api/products/?for_branch={self.stores.id}")
        names = {item["name"] for item in response.data["results"]}
        self.assertEqual(names, {"Flour", "12 CM SAUCERS"})


class MenuItemsCsvApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso (Short)",
            category=self.category,
            selling_price=Decimal("2"),
            tax_rate=Decimal("0"),
        )

    def test_export_menu_items_csv(self):
        csv_text = export_menu_items_csv()
        self.assertIn("ch,name,category", csv_text)
        self.assertIn("Espresso (Short)", csv_text)
        self.assertIn("Coffee", csv_text)

    def test_import_menu_items_endpoint_replaces_missing_products(self):
        desserts = ProductCategory.objects.create(name="Desserts")
        Product.objects.create(name="Old Tart", category=desserts, selling_price=Decimal("5"))

        csv_content = (
            "ch,name,category,selling_price,remaining_qty,tax_rate,is_active,id\n"
            f"Coffee,Espresso (Short),,2,15,0,TRUE,{self.product.id}\n"
        ).encode()
        upload = io.BytesIO(csv_content)
        upload.name = "menu_items.csv"
        response = self.client.post(
            "/api/products/import-menu-items-csv/?replace=true",
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["products_updated"], 1)
        self.assertEqual(response.data["deactivated"], 1)
        self.assertFalse(Product.objects.get(name="Old Tart").is_active)

    def test_export_menu_items_endpoint(self):
        response = self.client.get("/api/products/export-menu-items-csv/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(b"Espresso (Short)", response.content)


class ProductDeleteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso",
            category=self.category,
            selling_price=Decimal("3.50"),
        )

    def test_delete_unused_product(self):
        product_id = self.product.id
        response = self.client.delete(f"/api/products/{product_id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Product.objects.filter(id=product_id).exists())

    def test_delete_used_product_deactivates(self):
        from branches.models import Branch, BranchType
        from orders.models import Order, OrderItem, OrderStatus, OrderType

        branch = Branch.objects.create(name="Avondale", branch_type=BranchType.BRANCH)
        order = Order.objects.create(
            branch=branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("3.50"),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=Decimal("1"),
            price=Decimal("3.50"),
        )

        response = self.client.delete(f"/api/products/{self.product.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)
        self.assertTrue(Product.objects.filter(id=self.product.id).exists())


class ProductCategoryPosStationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = ProductCategory.objects.create(
            name="Coffee",
            pos_station="bar",
            show_on_pos=True,
        )

    def test_category_api_includes_pos_station(self):
        response = self.client.get(f"/api/categories/{self.category.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["pos_station"], "bar")
        self.assertEqual(response.data["pos_station_display"], "Bar")
        self.assertTrue(response.data["show_on_pos"])

    def test_category_patch_pos_station(self):
        response = self.client.patch(
            f"/api/categories/{self.category.id}/",
            {"pos_station": "kitchen"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.category.refresh_from_db()
        self.assertEqual(self.category.pos_station, "kitchen")

    def test_category_create_with_pos_station(self):
        response = self.client.post(
            "/api/categories/",
            {"name": "Mains", "pos_station": "kitchen", "show_on_pos": True},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["pos_station"], "kitchen")
        self.assertTrue(response.data["show_on_pos"])

    def test_category_patch_show_on_pos(self):
        response = self.client.patch(
            f"/api/categories/{self.category.id}/",
            {"show_on_pos": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.category.refresh_from_db()
        self.assertFalse(self.category.show_on_pos)


class ProductCategoryDeleteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = ProductCategory.objects.create(name="Coffee")

    def test_delete_empty_category(self):
        category_id = self.category.id
        response = self.client.delete(f"/api/categories/{category_id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ProductCategory.objects.filter(id=category_id).exists())

    def test_delete_category_with_only_inactive_products(self):
        Product.objects.create(
            name="Old Espresso",
            category=self.category,
            selling_price=Decimal("3.50"),
            is_active=False,
        )
        category_id = self.category.id
        response = self.client.delete(f"/api/categories/{category_id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ProductCategory.objects.filter(id=category_id).exists())
        self.assertFalse(Product.objects.filter(name="Old Espresso").exists())

    def test_delete_category_blocked_by_active_products(self):
        Product.objects.create(
            name="Espresso",
            category=self.category,
            selling_price=Decimal("3.50"),
            is_active=True,
        )
        response = self.client.delete(f"/api/categories/{self.category.id}/")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(ProductCategory.objects.filter(id=self.category.id).exists())

    def test_delete_category_moves_inactive_products_with_history_to_archived(self):
        from branches.models import Branch, BranchType
        from orders.models import Order, OrderItem, OrderStatus, OrderType

        product = Product.objects.create(
            name="Espresso",
            category=self.category,
            selling_price=Decimal("3.50"),
            is_active=False,
        )
        branch = Branch.objects.create(name="Avondale", branch_type=BranchType.BRANCH)
        order = Order.objects.create(
            branch=branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("3.50"),
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=Decimal("1"),
            price=Decimal("3.50"),
        )

        category_id = self.category.id
        response = self.client.delete(f"/api/categories/{category_id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ProductCategory.objects.filter(id=category_id).exists())
        product.refresh_from_db()
        self.assertEqual(product.category.name, "Archived")

    def test_delete_archived_category_blocked_by_inactive_products_with_history(self):
        from branches.models import Branch, BranchType
        from orders.models import Order, OrderItem, OrderStatus, OrderType

        archived = ProductCategory.objects.create(name="Archived")
        product = Product.objects.create(
            name="Espresso",
            category=archived,
            selling_price=Decimal("3.50"),
            is_active=False,
        )
        branch = Branch.objects.create(name="Avondale", branch_type=BranchType.BRANCH)
        order = Order.objects.create(
            branch=branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("3.50"),
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=Decimal("1"),
            price=Decimal("3.50"),
        )

        response = self.client.delete(f"/api/categories/{archived.id}/")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(ProductCategory.objects.filter(id=archived.id).exists())
        self.assertIn("Espresso", response.data["products"])
