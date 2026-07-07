from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalog.bakery_products_import import (
    BAKERY_PRODUCTS_CSV_DEFAULT,
    import_bakery_products_csv,
)


class Command(BaseCommand):
    help = (
        "Import finished bakery products from csvdata/Backerproducts.csv "
        "(transferable to central stores and branches)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default=BAKERY_PRODUCTS_CSV_DEFAULT,
            help=f"Path to the bakery products CSV (default: {BAKERY_PRODUCTS_CSV_DEFAULT}).",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Deactivate bakery products not present in the import file.",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.is_file():
            raise CommandError(f"CSV not found: {file_path}")

        with file_path.open("rb") as handle:
            stats = import_bakery_products_csv(handle, replace=options["replace"])

        if stats.get("skipped"):
            preview = "; ".join(
                f"row {error['row']}: {error['message']}"
                for error in stats["skipped"][:5]
            )
            self.stdout.write(self.style.WARNING(f"Skipped rows: {preview}"))

        self.stdout.write(self.style.SUCCESS("Bakery products imported successfully."))
        for key, value in stats.items():
            if key == "skipped":
                continue
            self.stdout.write(f"  {key.replace('_', ' ').title()}: {value}")
