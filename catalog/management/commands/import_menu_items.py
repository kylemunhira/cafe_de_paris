from pathlib import Path

import openpyxl
from django.core.management.base import BaseCommand, CommandError

from catalog.menu_items_import import MENU_ITEMS_SHEET, import_menu_items


class Command(BaseCommand):
    help = "Import POS menu items from NEW DATA BASE CDP.xlsx (MENU ITEMS sheet)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default="NEW DATA BASE CDP.xlsx",
            help="Path to the menu items workbook (default: NEW DATA BASE CDP.xlsx).",
        )
        parser.add_argument(
            "--sheet",
            default=MENU_ITEMS_SHEET,
            help=f'Worksheet name (default: "{MENU_ITEMS_SHEET}").',
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.is_file():
            raise CommandError(f"Workbook not found: {file_path}")

        workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        sheet_name = options["sheet"]
        if sheet_name not in workbook.sheetnames:
            available = ", ".join(workbook.sheetnames)
            raise CommandError(f"Sheet {sheet_name!r} not found. Available: {available}")

        rows = list(workbook[sheet_name].iter_rows(values_only=True))
        stats = import_menu_items(rows)

        self.stdout.write(self.style.SUCCESS("Menu items imported successfully."))
        for key, value in stats.items():
            self.stdout.write(f"  {key.replace('_', ' ').title()}: {value}")
