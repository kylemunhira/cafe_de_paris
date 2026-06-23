import io
from pathlib import Path

from django.test import TestCase

from purchasing.models import Supplier
from purchasing.supplier_import import (
    export_suppliers_csv,
    import_suppliers_csv,
    import_suppliers_workbook,
    normalize_vat_number,
)


class SupplierImportTests(TestCase):
    def test_normalize_vat_number_from_float(self):
        self.assertEqual(normalize_vat_number(220163079), "220163079")

    def test_import_csv_creates_vat_and_non_vat_suppliers(self):
        csv_file = io.BytesIO(
            b"name,vat_number,address,notes\n"
            b"VAT Supplier,220163079,1 Main St,DAIRY\n"
            b"Cash Supplier,,,MEAT\n"
        )
        result = import_suppliers_csv(csv_file)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["errors"], [])

        vat_supplier = Supplier.objects.get(name="VAT Supplier")
        self.assertEqual(vat_supplier.vat_number, "220163079")
        self.assertEqual(vat_supplier.address, "1 Main St")
        self.assertEqual(vat_supplier.notes, "DAIRY")

        cash_supplier = Supplier.objects.get(name="Cash Supplier")
        self.assertEqual(cash_supplier.vat_number, "")

    def test_import_csv_updates_existing_supplier_by_name(self):
        Supplier.objects.create(name="Country Choice Foods", notes="OLD")
        csv_file = io.BytesIO(
            b"name,vat_number,notes\nCountry Choice Foods,220024195,SUGAR\n"
        )
        result = import_suppliers_csv(csv_file)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)
        supplier = Supplier.objects.get(name="Country Choice Foods")
        self.assertEqual(supplier.vat_number, "220024195")
        self.assertEqual(supplier.notes, "SUGAR")

    def test_export_includes_vat_number(self):
        Supplier.objects.create(name="Exporter", vat_number="220000001")
        csv_text = export_suppliers_csv()
        self.assertIn("vat_number", csv_text)
        self.assertIn("Exporter", csv_text)
        self.assertIn("220000001", csv_text)

    def test_import_workbook_from_repo_file(self):
        workbook_path = Path("supplier list.xlsx")
        if not workbook_path.is_file():
            self.skipTest("supplier list.xlsx not available")

        result = import_suppliers_workbook(workbook_path)
        self.assertEqual(result["errors"], [])
        self.assertGreater(result["created"], 0)
        self.assertGreater(Supplier.objects.filter(vat_number__gt="").count(), 0)
        self.assertGreater(Supplier.objects.filter(vat_number="").count(), 0)
