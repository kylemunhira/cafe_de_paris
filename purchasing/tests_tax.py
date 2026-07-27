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
        self.vat_supplier = Supplier.objects.create(
            name="VAT Supplier", vat_number="220163079"
        )
        self.non_vat_supplier = Supplier.objects.create(name="Cash Supplier")

    def test_split_purchase_line_total_uses_full_precision(self):
        split = split_purchase_line_total(Decimal("1.2345") * Decimal("2.5678"), self.taxable)
        self.assertGreater(split["tax"], Decimal("0"))
        self.assertEqual(split["total"], Decimal("1.2345") * Decimal("2.5678"))

    def test_zero_rated_product_still_splits_vat_for_vat_supplier(self):
        split = split_purchase_line_total(Decimal("115.50"), self.zero_rated)
        self.assertGreater(split["tax"], Decimal("0"))
        self.assertEqual(split["total"], Decimal("115.50"))

    def test_product_with_blank_tax_fields_uses_inclusive_rate(self):
        product = Product.objects.create(
            name="SPARKLING WATER",
            category=self.category,
            selling_price=Decimal("0"),
            tax_rate=Decimal("0"),
            fiscal_tax_code="",
        )
        split = split_purchase_line_total(Decimal("115.50"), product)
        self.assertGreater(split["tax"], Decimal("0"))
        self.assertEqual(split["total"], Decimal("115.50"))

    def test_non_vat_supplier_skips_vat_even_for_taxable_product(self):
        split = split_purchase_line_total(
            Decimal("115.50"), self.taxable, apply_vat=False
        )
        self.assertEqual(split["tax"], Decimal("0"))
        self.assertEqual(split["subtotal"], Decimal("115.50"))

    def test_purchase_order_amounts_quantized_to_two_dp(self):
        from branches.models import Branch, BranchType

        branch = Branch.objects.create(name="Stores", branch_type=BranchType.STORES)
        purchase_order = PurchaseOrder.objects.create(
            branch=branch,
            supplier=self.vat_supplier,
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
        self.assertGreater(amounts["vat_amount"], Decimal("0"))

    def test_purchase_order_amounts_zero_vat_for_non_vat_supplier(self):
        from branches.models import Branch, BranchType

        branch = Branch.objects.create(name="Stores", branch_type=BranchType.STORES)
        purchase_order = PurchaseOrder.objects.create(
            branch=branch,
            supplier=self.non_vat_supplier,
            status=PurchaseOrderStatus.RECEIVED,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=purchase_order,
            product=self.taxable,
            quantity=Decimal("2"),
            unit_cost=Decimal("50"),
        )

        amounts = purchase_order_amounts(purchase_order)
        self.assertEqual(amounts["vat_amount"], Decimal("0.00"))
        self.assertEqual(amounts["subtotal_amount"], Decimal("100.00"))
        self.assertEqual(amounts["total_amount"], Decimal("100.00"))
