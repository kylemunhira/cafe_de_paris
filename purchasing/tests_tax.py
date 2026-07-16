from decimal import Decimal

from django.test import TestCase

from catalog.models import Product, ProductCategory
from purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, Supplier
from purchasing.tax import purchase_order_amounts, split_purchase_line_total


class PurchaseTaxTests(TestCase):
    def setUp(self):
        self.category = ProductCategory.objects.create(name="Ingredients")
        self.taxable = Product.objects.create(
            name="Flour",
            category=self.category,
            selling_price=Decimal("0"),
            tax_rate=Decimal("15.5"),
        )
        self.zero_rated = Product.objects.create(
            name="Water",
            category=self.category,
            selling_price=Decimal("0"),
            fiscal_tax_code="B",
        )
        self.supplier = Supplier.objects.create(name="Supplier")

    def test_split_purchase_line_total_uses_full_precision(self):
        split = split_purchase_line_total(Decimal("1.2345") * Decimal("2.5678"), self.taxable)
        self.assertGreater(split["tax"], Decimal("0"))
        self.assertEqual(split["total"], Decimal("1.2345") * Decimal("2.5678"))

    def test_zero_rated_product_has_no_vat(self):
        split = split_purchase_line_total(Decimal("10.00"), self.zero_rated)
        self.assertEqual(split["tax"], Decimal("0"))
        self.assertEqual(split["subtotal"], Decimal("10.00"))

    def test_purchase_order_amounts_quantized_to_two_dp(self):
        from branches.models import Branch, BranchType

        branch = Branch.objects.create(name="Stores", branch_type=BranchType.STORES)
        purchase_order = PurchaseOrder.objects.create(
            branch=branch,
            supplier=self.supplier,
            status=PurchaseOrderStatus.RECEIVED,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=purchase_order,
            product=self.taxable,
            quantity=Decimal("1.1111"),
            unit_cost=Decimal("2.2222"),
        )
        PurchaseOrderLine.objects.create(
            purchase_order=purchase_order,
            product=self.zero_rated,
            quantity=Decimal("3"),
            unit_cost=Decimal("4.5678"),
        )

        amounts = purchase_order_amounts(purchase_order)
        self.assertEqual(amounts["subtotal_amount"].as_tuple().exponent, -2)
        self.assertEqual(amounts["vat_amount"].as_tuple().exponent, -2)
        self.assertEqual(amounts["total_amount"].as_tuple().exponent, -2)
        self.assertEqual(
            amounts["total_amount"],
            amounts["subtotal_amount"] + amounts["vat_amount"],
        )
