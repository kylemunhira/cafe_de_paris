from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile, StaffRole
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from customers.models import Customer, CustomerAccountTransaction, CustomerAccountTransactionType
from customers.reports import build_customer_balances_report
from customers.services import deposit_to_account, pay_order_from_account
from customers.statement import build_customer_statement_report
from orders.models import Order, OrderStatus, PaymentMethod
from payments.models import Currency, CurrencyRate

User = get_user_model()


class CustomerAccountTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.ui_client = Client()
        self.branch = Branch.objects.create(
            name="Test Branch",
            code="TST",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        self.usd = Currency.objects.create(
            code="USD",
            name="US Dollar",
            symbol="$",
            is_base=True,
        )
        CurrencyRate.objects.create(
            currency=self.usd,
            rate=Decimal("1"),
            effective_from="2026-01-01",
        )
        self.zwl = Currency.objects.create(
            code="ZWL",
            name="Zimbabwe Dollar",
            symbol="Z$",
        )
        CurrencyRate.objects.create(
            currency=self.zwl,
            rate=Decimal("25.5"),
            effective_from="2026-06-01",
        )
        self.customer = Customer.objects.create(
            first_name="John",
            last_name="Doe",
            phone="0771234567",
        )
        self.user = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(user=self.user, branch=self.branch, pos_access=True)
        self.client.force_authenticate(user=self.user)
        self.ui_client.force_login(self.user)

        category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso",
            category=category,
            selling_price=Decimal("3.50"),
        )

    def test_deposit_in_base_currency(self):
        txn = deposit_to_account(
            customer=self.customer,
            branch=self.branch,
            currency=self.usd,
            amount_received=Decimal("20.00"),
            recorded_by=self.user,
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.account_balance, Decimal("20.00"))
        self.assertEqual(txn.transaction_type, CustomerAccountTransactionType.DEPOSIT)
        self.assertEqual(txn.balance_after, Decimal("20.00"))

    def test_deposit_in_foreign_currency(self):
        deposit_to_account(
            customer=self.customer,
            branch=self.branch,
            currency=self.zwl,
            amount_received=Decimal("255.00"),
            recorded_by=self.user,
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.account_balance, Decimal("10.00"))

    def test_deposit_api(self):
        response = self.client.post(
            f"/api/customers/{self.customer.id}/deposit/",
            {
                "branch": self.branch.id,
                "currency_id": self.usd.id,
                "amount": "50.00",
                "notes": "Top-up",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["account_balance"], Decimal("50.00"))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.account_balance, Decimal("50.00"))

    def test_waiter_cannot_record_deposit(self):
        waiter = User.objects.create_user(username="waiter", password="pass")
        StaffProfile.objects.create(
            user=waiter,
            branch=self.branch,
            role=StaffRole.WAITER,
            pos_access=True,
        )
        self.client.force_authenticate(user=waiter)

        response = self.client.post(
            f"/api/customers/{self.customer.id}/deposit/",
            {
                "branch": self.branch.id,
                "currency_id": self.usd.id,
                "amount": "50.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.account_balance, Decimal("0.00"))

    def test_pay_order_from_account(self):
        self.customer.account_balance = Decimal("20.00")
        self.customer.save(update_fields=["account_balance"])
        order = Order.objects.create(branch=self.branch, customer=self.customer)
        order.items.create(
            product=self.product,
            quantity=Decimal("2"),
            price=Decimal("3.50"),
        )
        order.recalculate_total()

        pay_order_from_account(order=order, recorded_by=self.user)
        order.refresh_from_db()
        self.customer.refresh_from_db()

        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertEqual(order.payment_method, PaymentMethod.ACCOUNT)
        self.assertEqual(order.amount_paid, Decimal("7.00"))
        self.assertEqual(self.customer.account_balance, Decimal("13.00"))
        self.assertEqual(
            CustomerAccountTransaction.objects.filter(
                transaction_type=CustomerAccountTransactionType.PAYMENT
            ).count(),
            1,
        )

    def test_pay_order_from_account_via_api(self):
        self.customer.account_balance = Decimal("20.00")
        self.customer.save(update_fields=["account_balance"])
        order = Order.objects.create(branch=self.branch, customer=self.customer)
        order.items.create(
            product=self.product,
            quantity=Decimal("2"),
            price=Decimal("3.50"),
        )
        order.recalculate_total()

        response = self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"payment_method": "account"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.account_balance, Decimal("13.00"))

    def test_pay_order_from_account_insufficient_balance(self):
        self.customer.account_balance = Decimal("5.00")
        self.customer.save(update_fields=["account_balance"])
        order = Order.objects.create(branch=self.branch, customer=self.customer)
        order.items.create(
            product=self.product,
            quantity=Decimal("2"),
            price=Decimal("3.50"),
        )
        order.recalculate_total()

        response = self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"payment_method": "account"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Insufficient", response.data["detail"])

    def test_pay_order_from_account_within_credit_limit(self):
        self.customer.account_balance = Decimal("0.00")
        self.customer.credit_limit = Decimal("5.00")
        self.customer.save(update_fields=["account_balance", "credit_limit"])
        order = Order.objects.create(branch=self.branch, customer=self.customer)
        order.items.create(
            product=self.product,
            quantity=Decimal("1"),
            price=Decimal("3.50"),
        )
        order.recalculate_total()

        pay_order_from_account(order=order, recorded_by=self.user)
        order.refresh_from_db()
        self.customer.refresh_from_db()

        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertEqual(self.customer.account_balance, Decimal("-3.50"))

    def test_pay_order_from_account_exceeds_credit_limit(self):
        self.customer.account_balance = Decimal("0.00")
        self.customer.credit_limit = Decimal("5.00")
        self.customer.save(update_fields=["account_balance", "credit_limit"])
        order = Order.objects.create(branch=self.branch, customer=self.customer)
        order.items.create(
            product=self.product,
            quantity=Decimal("2"),
            price=Decimal("3.50"),
        )
        order.recalculate_total()

        response = self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"payment_method": "account"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Insufficient", response.data["detail"])
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.account_balance, Decimal("0.00"))

    def test_customer_accounts_page(self):
        response = self.ui_client.get("/customer-accounts/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer Accounts")

    def test_list_transactions(self):
        deposit_to_account(
            customer=self.customer,
            branch=self.branch,
            currency=self.usd,
            amount_received=Decimal("10.00"),
            recorded_by=self.user,
        )
        response = self.client.get(f"/api/customers/{self.customer.id}/transactions/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["account_balance"], Decimal("10.00"))
        self.assertEqual(len(response.data["transactions"]), 1)

    def test_transaction_statement_print(self):
        txn = deposit_to_account(
            customer=self.customer,
            branch=self.branch,
            currency=self.usd,
            amount_received=Decimal("10.00"),
            recorded_by=self.user,
        )
        response = self.ui_client.get(f"/customer-accounts/transaction/{txn.id}/print/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer account statement")
        self.assertContains(response, "Payment received")
        self.assertContains(response, "John Doe")

    def test_full_statement_print(self):
        deposit_to_account(
            customer=self.customer,
            branch=self.branch,
            currency=self.usd,
            amount_received=Decimal("10.00"),
            recorded_by=self.user,
        )
        response = self.ui_client.get(
            f"/customer-accounts/{self.customer.id}/statement/print/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Opening balance")
        self.assertContains(response, "Closing balance")
        self.assertContains(response, "Payment received")

    def test_statement_report_api(self):
        deposit_to_account(
            customer=self.customer,
            branch=self.branch,
            currency=self.usd,
            amount_received=Decimal("10.00"),
            recorded_by=self.user,
        )
        response = self.client.get(f"/api/customers/{self.customer.id}/statement/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(str(response.data["opening_balance"])), Decimal("0"))
        self.assertEqual(Decimal(str(response.data["closing_balance"])), Decimal("10.00"))
        self.assertEqual(Decimal(str(response.data["total_credits"])), Decimal("10.00"))
        self.assertEqual(len(response.data["transactions"]), 1)

    def test_statement_opening_balance_from_prior_period(self):
        deposit_to_account(
            customer=self.customer,
            branch=self.branch,
            currency=self.usd,
            amount_received=Decimal("10.00"),
            recorded_by=self.user,
        )
        report = build_customer_statement_report(
            self.customer,
            from_date="2099-01-01",
            to_date="2099-01-31",
        )
        self.assertEqual(report["opening_balance"], Decimal("10.00"))
        self.assertEqual(report["closing_balance"], Decimal("10.00"))
        self.assertEqual(report["transaction_count"], 0)

    def test_statement_all_time_print(self):
        deposit_to_account(
            customer=self.customer,
            branch=self.branch,
            currency=self.usd,
            amount_received=Decimal("10.00"),
            recorded_by=self.user,
        )
        response = self.ui_client.get(
            f"/customer-accounts/{self.customer.id}/statement/print/?all=1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "All transactions")
        self.assertContains(response, "Closing balance")

    def test_customer_balances_report(self):
        deposit_to_account(
            customer=self.customer,
            branch=self.branch,
            currency=self.usd,
            amount_received=Decimal("15.00"),
            recorded_by=self.user,
        )
        Customer.objects.create(first_name="Jane", last_name="Smith", phone="0779999999")

        report = build_customer_balances_report()
        self.assertEqual(report["summary"]["customer_count"], 2)
        self.assertEqual(report["summary"]["customers_with_balance"], 1)
        self.assertEqual(report["summary"]["total_balance"], Decimal("15.00"))
        self.assertEqual(report["customers"][0]["full_name"], "John Doe")
        self.assertEqual(report["customers"][0]["account_balance"], Decimal("15.00"))

    def test_customer_balances_report_non_zero_filter(self):
        deposit_to_account(
            customer=self.customer,
            branch=self.branch,
            currency=self.usd,
            amount_received=Decimal("5.00"),
            recorded_by=self.user,
        )
        Customer.objects.create(first_name="Jane", last_name="Smith")

        report = build_customer_balances_report(non_zero_only=True)
        self.assertEqual(report["summary"]["customer_count"], 1)
        self.assertEqual(report["customers"][0]["full_name"], "John Doe")

    def test_customer_balances_report_api(self):
        deposit_to_account(
            customer=self.customer,
            branch=self.branch,
            currency=self.usd,
            amount_received=Decimal("12.50"),
            recorded_by=self.user,
        )
        response = self.client.get("/api/reports/customer-balances/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["customer_count"], 1)
        self.assertEqual(
            Decimal(str(response.data["summary"]["total_balance"])),
            Decimal("12.50"),
        )

    def test_customer_balances_report_page(self):
        response = self.ui_client.get("/reports/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer Balances Report")

    def test_account_payment_receipt_includes_statement(self):
        self.customer.account_balance = Decimal("20.00")
        self.customer.save(update_fields=["account_balance"])
        order = Order.objects.create(branch=self.branch, customer=self.customer)
        order.items.create(
            product=self.product,
            quantity=Decimal("2"),
            price=Decimal("3.50"),
        )
        order.recalculate_total()
        pay_order_from_account(order=order, recorded_by=self.user)
        response = self.ui_client.get(f"/pos/receipt/{order.id}/print/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer account statement")
        self.assertContains(response, "Withdrawal")
