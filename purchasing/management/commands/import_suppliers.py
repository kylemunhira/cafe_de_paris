from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from purchasing.supplier_import import import_suppliers_workbook


class Command(BaseCommand):
    help = "Import suppliers from supplier list.xlsx (vat and non vat sheets)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default="supplier list.xlsx",
            help="Path to the supplier workbook (default: supplier list.xlsx).",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.is_file():
            raise CommandError(f"Workbook not found: {file_path}")

        result = import_suppliers_workbook(file_path)
        if result["errors"]:
            preview = "; ".join(
                f"row {error['row']}: {error['message']}" for error in result["errors"][:5]
            )
            raise CommandError(f"Import failed — {preview}")

        self.stdout.write(self.style.SUCCESS("Suppliers imported successfully."))
        self.stdout.write(f"  Created: {result['created']}")
        self.stdout.write(f"  Updated: {result['updated']}")
