from decimal import Decimal
from pathlib import Path
import tempfile

import openpyxl
from django.test import TestCase

from branches.models import Branch, BranchType
from customers.balance_import import (
    import_customer_balances,
    parse_balance,
    phone_match_key,
)
from customers.models import Customer, CustomerAccountTransaction, CustomerAccountTransactionType
from customers.services import apply_account_balance_adjustment


class BalanceImportHelpersTests(TestCase):
    def test_parse_balance_formats(self):
        self.assertEqual(parse_balance("+3.00"), Decimal("3.00"))
        self.assertEqual(parse_balance("-3"), Decimal("-3.00"))
        self.assertEqual(parse_balance("(2.5)"), Decimal("-2.50"))
        self.assertIsNone(parse_balance("-"))
        self.assertIsNone(parse_balance(None))
        self.assertIsNone(parse_balance(""))

    def test_phone_match_key_strips_leading_zero(self):
        self.assertEqual(phone_match_key("0783606275"), "783606275")
        self.assertEqual(phone_match_key("783606275"), "783606275")


class AccountBalanceAdjustmentTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Main",
            code="MN",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        self.customer = Customer.objects.create(
            first_name="Shayda",
            phone="772722789",
            account_balance=Decimal("-3.00"),
        )

    def test_zero_current_and_excel_negative_sets_negative(self):
        self.customer.account_balance = Decimal("0")
        self.customer.save(update_fields=["account_balance"])
        txn = apply_account_balance_adjustment(
            customer=self.customer,
            branch=self.branch,
            target_balance=Decimal("-3"),
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.account_balance, Decimal("-3.00"))
        self.assertEqual(txn.amount, Decimal("-3.00"))
        self.assertEqual(txn.transaction_type, CustomerAccountTransactionType.ADJUSTMENT)

    def test_current_negative_and_excel_positive_sets_excel(self):
        """Excel is the actual balance — current -3 and excel +3 becomes +3."""
        txn = apply_account_balance_adjustment(
            customer=self.customer,
            branch=self.branch,
            target_balance=Decimal("3"),
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.account_balance, Decimal("3.00"))
        self.assertEqual(txn.amount, Decimal("6.00"))
        self.assertEqual(txn.balance_after, Decimal("3.00"))

    def test_unchanged_balance_creates_no_transaction(self):
        txn = apply_account_balance_adjustment(
            customer=self.customer,
            branch=self.branch,
            target_balance=Decimal("-3"),
        )
        self.assertIsNone(txn)
        self.assertEqual(CustomerAccountTransaction.objects.count(), 0)


class ImportCustomerBalancesWorkbookTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Main",
            code="MN",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        self.customer = Customer.objects.create(
            first_name="Claire",
            phone="783606275",
            account_balance=Decimal("8.50"),
        )
        self.owing = Customer.objects.create(
            first_name="Abbas",
            last_name="Kanthraria",
            phone="0712602509",
            account_balance=Decimal("0"),
        )
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)

    def _write_workbook(self, rows):
        path = Path(self._tmpdir.name) / "balances.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Customers"
        ws.append(["Name", "Phone Number", "Balance"])
        for row in rows:
            ws.append(row)
        wb.save(path)
        return path

    def test_import_sets_balance_and_records_adjustment(self):
        path = self._write_workbook(
            [
                ["Claire", "0783606275", "+8.50"],
                ["Abbas Kanthraria", "0712602509", "-0.50"],
                ["Ghost Customer", "0700000000", "5.00"],
            ]
        )
        result = import_customer_balances(path, branch=self.branch)
        self.assertEqual(result["unchanged"], 1)
        self.assertEqual(result["adjusted"], 1)
        self.assertEqual(result["missing"], 1)

        self.owing.refresh_from_db()
        self.assertEqual(self.owing.account_balance, Decimal("-0.50"))
        txn = CustomerAccountTransaction.objects.get(customer=self.owing)
        self.assertEqual(txn.transaction_type, CustomerAccountTransactionType.ADJUSTMENT)
        self.assertEqual(txn.amount, Decimal("-0.50"))
        self.assertTrue(txn.is_balance_adjustment)
