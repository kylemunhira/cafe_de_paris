from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from branches.models import Branch, BranchType
from catalog.constants import BRANCH_INGREDIENTS_CATEGORY, INGREDIENTS_CATEGORY
from catalog.models import Product, ProductCategory
from inventory.models import BranchInventory
from purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, Supplier
from purchasing.services import apply_purchase_order_inventory, receive_purchase_order


User = get_user_model()


class PurchaseReceivePriceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="buyer", password="pass")
        self.branch = Branch.objects.create(name="Main", branch_type=BranchType.BRANCH)
        self.supplier = Supplier.objects.create(name="Dairy Co")
        self.branch_ingredients = ProductCategory.objects.create(
            name=BRANCH_INGREDIENTS_CATEGORY
        )
        self.bakery_ingredients = ProductCategory.objects.create(
            name=INGREDIENTS_CATEGORY
        )
        self.pos_category = ProductCategory.objects.create(name="Coffee")
        self.milk = Product.objects.create(
            name="Milk",
            category=self.branch_ingredients,
            selling_price=Decimal("2.00"),
        )
        self.flour = Product.objects.create(
            name="Flour",
            category=self.bakery_ingredients,
            selling_price=Decimal("5.00"),
        )
        self.latte = Product.objects.create(
            name="Latte",
            category=self.pos_category,
            selling_price=Decimal("4.50"),
        )

    def _make_approved_po(self, *lines):
        po = PurchaseOrder.objects.create(
            branch=self.branch,
            supplier=self.supplier,
            status=PurchaseOrderStatus.APPROVED,
            created_by=self.user,
        )
        for product, qty, unit_cost in lines:
            PurchaseOrderLine.objects.create(
                purchase_order=po,
                product=product,
                quantity=qty,
                unit_cost=unit_cost,
            )
        return po

    def test_receive_updates_branch_ingredient_selling_price(self):
        po = self._make_approved_po(
            (self.milk, Decimal("10"), Decimal("3.4567")),
        )
        receive_purchase_order(po)

        self.milk.refresh_from_db()
        self.assertEqual(self.milk.selling_price, Decimal("3.46"))
        inv = BranchInventory.objects.get(branch=self.branch, product=self.milk)
        self.assertEqual(inv.quantity, Decimal("10.000"))

    def test_apply_inventory_updates_bakery_ingredient_price(self):
        po = PurchaseOrder.objects.create(
            branch=self.branch,
            supplier=self.supplier,
            status=PurchaseOrderStatus.RECEIVED,
            created_by=self.user,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=po,
            product=self.flour,
            quantity=Decimal("2"),
            unit_cost=Decimal("7.50"),
        )

        apply_purchase_order_inventory(po)

        self.flour.refresh_from_db()
        self.assertEqual(self.flour.selling_price, Decimal("7.50"))

    def test_receive_does_not_change_pos_product_price(self):
        po = self._make_approved_po(
            (self.latte, Decimal("5"), Decimal("1.00")),
        )
        receive_purchase_order(po)

        self.latte.refresh_from_db()
        self.assertEqual(self.latte.selling_price, Decimal("4.50"))

    def test_zero_unit_cost_does_not_overwrite_ingredient_price(self):
        po = self._make_approved_po(
            (self.milk, Decimal("3"), Decimal("0")),
        )
        receive_purchase_order(po)

        self.milk.refresh_from_db()
        self.assertEqual(self.milk.selling_price, Decimal("2.00"))
