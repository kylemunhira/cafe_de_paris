from pathlib import Path
import csv
import io

from django.core.management.base import BaseCommand, CommandError

from catalog.constants import INGREDIENTS_CATEGORY
from catalog.csv_io import import_ingredients_csv
from catalog.models import Product


class Command(BaseCommand):
    help = "Import bakery ingredients from csvdata/BAKERY INGREDIENTS.csv (Central Stores & Bakery)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default="csvdata/BAKERY INGREDIENTS.csv",
            help="Path to the ingredients CSV (default: csvdata/BAKERY INGREDIENTS.csv).",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Deactivate ingredients not present in the CSV after import.",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.is_file():
            raise CommandError(f"CSV not found: {file_path}")

        with file_path.open("rb") as handle:
            result = import_ingredients_csv(handle)

        if result["errors"]:
            preview = "; ".join(
                f"row {error['row']}: {error['message']}" for error in result["errors"][:5]
            )
            raise CommandError(f"Import failed — {preview}")

        deactivated = 0
        if options["replace"]:
            names_in_csv = set()
            raw = file_path.read_bytes()
            for encoding in ("utf-8-sig", "cp1252"):
                try:
                    text = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    text = None
            if text is None:
                raise CommandError("CSV must be UTF-8 or Windows-1252 encoded")

            for row in csv.DictReader(io.StringIO(text)):
                name = (row.get("name") or "").strip()
                if name:
                    names_in_csv.add(name)

            deactivated = (
                Product.objects.filter(category__name=INGREDIENTS_CATEGORY, is_active=True)
                .exclude(name__in=names_in_csv)
                .update(is_active=False)
            )

        self.stdout.write(self.style.SUCCESS("Ingredients imported successfully."))
        self.stdout.write(f"  Created: {result['created']}")
        self.stdout.write(f"  Updated: {result['updated']}")
        if options["replace"]:
            self.stdout.write(f"  Deactivated: {deactivated}")
