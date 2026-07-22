from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from customers.balance_import import import_customer_balances


class Command(BaseCommand):
    help = (
        "Import actual customer account balances from Customer_Accounts_final.xlsx. "
        "Sets each matched customer's balance to the Excel value and records a "
        "highlighted balance-adjustment entry in customer history."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default="csvdata/Customer_Accounts_final.xlsx",
            help="Path to the balances workbook.",
        )
        parser.add_argument(
            "--branch-id",
            type=int,
            default=None,
            help="Branch id for adjustment history (default: first active branch).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing to the database.",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.is_file():
            raise CommandError(f"Workbook not found: {file_path}")

        result = import_customer_balances(
            file_path,
            branch_id=options["branch_id"],
            dry_run=options["dry_run"],
        )

        if result["errors"]:
            preview = "; ".join(
                f"row {error['row']}: {error['message']}" for error in result["errors"][:8]
            )
            raise CommandError(f"Import failed — {preview}")

        label = "Dry run" if options["dry_run"] else "Import"
        self.stdout.write(self.style.SUCCESS(f"{label} complete."))
        self.stdout.write(f"  Adjusted:  {result['adjusted']}")
        self.stdout.write(f"  Unchanged: {result['unchanged']}")
        self.stdout.write(f"  Missing:   {result['missing']}")
        self.stdout.write(f"  Skipped:   {result['skipped']}")

        for detail in result["details"]:
            if detail["status"] != "adjusted":
                continue
            self.stdout.write(
                f"  - {detail['name']} ({detail.get('phone') or '-'}): "
                f"{detail['before']} -> {detail['after']} (delta {detail['delta']})"
            )

        skipped = [d for d in result["details"] if d["status"] == "skipped"]
        if skipped:
            self.stdout.write(self.style.WARNING("Skipped rows:"))
            for detail in skipped[:20]:
                self.stdout.write(
                    f"  - row {detail['row']}: {detail.get('message') or 'skipped'}"
                )

        missing = [d for d in result["details"] if d["status"] == "missing"]
        if missing:
            self.stdout.write(self.style.WARNING("Customers not found in the system:"))
            for detail in missing[:30]:
                self.stdout.write(
                    f"  - row {detail['row']}: {detail['name']} "
                    f"({detail.get('phone') or '-'}) excel={detail['excel_balance']}"
                )
            if len(missing) > 30:
                self.stdout.write(f"  ... and {len(missing) - 30} more")
