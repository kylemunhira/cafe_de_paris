import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from branches.models import Branch, BranchType
from customers.csv_io import export_customers_csv, import_customers_csv
from customers.models import Customer
from django.test import TestCase

User = get_user_model()


class CustomerImportTests(TestCase):
    def test_import_csv_creates_customers(self):
        csv_file = io.BytesIO(
            b"first_name,last_name,phone,email,account_type,loyalty_points,credit_limit\n"
            b"Jane,Doe,0771111111,jane@example.com,regular,10,50\n"
            b"Bob,,0772222222,,staff,0,100\n"
        )
        result = import_customers_csv(csv_file)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["errors"], [])

        jane = Customer.objects.get(first_name="Jane", last_name="Doe")
        self.assertEqual(jane.phone, "0771111111")
        self.assertEqual(jane.email, "jane@example.com")
        self.assertEqual(jane.account_type, "regular")
        self.assertEqual(jane.loyalty_points, 10)
        self.assertEqual(jane.credit_limit, Decimal("50"))

        bob = Customer.objects.get(first_name="Bob")
        self.assertEqual(bob.account_type, "staff")
        self.assertEqual(bob.credit_limit, Decimal("100"))

    def test_import_csv_updates_existing_customer_by_phone(self):
        Customer.objects.create(
            first_name="Jane",
            last_name="Old",
            phone="0771111111",
            loyalty_points=0,
        )
        csv_file = io.BytesIO(
            b"first_name,last_name,phone,email,account_type\n"
            b"Jane,New,0771111111,jane@example.com,family\n"
        )
        result = import_customers_csv(csv_file)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["errors"], [])

        customer = Customer.objects.get(phone="0771111111")
        self.assertEqual(customer.last_name, "New")
        self.assertEqual(customer.email, "jane@example.com")
        self.assertEqual(customer.account_type, "family")

    def test_import_csv_updates_existing_customer_by_id(self):
        customer = Customer.objects.create(first_name="Jane", last_name="Doe")
        csv_file = io.BytesIO(
            f"id,first_name,last_name,phone\n"
            f"{customer.id},Jane,Smith,0773333333\n".encode()
        )
        result = import_customers_csv(csv_file)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)

        customer.refresh_from_db()
        self.assertEqual(customer.last_name, "Smith")
        self.assertEqual(customer.phone, "0773333333")

    def test_import_csv_rejects_invalid_account_type(self):
        csv_file = io.BytesIO(
            b"first_name,account_type\n"
            b"Jane,invalid\n"
        )
        result = import_customers_csv(csv_file)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("account_type", result["errors"][0]["message"])

    def test_import_csv_requires_first_name_column(self):
        csv_file = io.BytesIO(b"phone,email\n0771111111,a@example.com\n")
        result = import_customers_csv(csv_file)
        self.assertEqual(result["errors"][0]["message"], "Missing required column: first_name")

    def test_export_includes_customer_fields(self):
        Customer.objects.create(
            first_name="Export",
            last_name="Me",
            phone="0779999999",
            email="export@example.com",
            account_type="family",
            loyalty_points=5,
            credit_limit=Decimal("25.50"),
        )
        csv_text = export_customers_csv()
        self.assertIn("first_name", csv_text)
        self.assertIn("Export", csv_text)
        self.assertIn("0779999999", csv_text)
        self.assertIn("family", csv_text)
        self.assertIn("25.50", csv_text)

    def test_import_csv_with_only_first_name_column(self):
        csv_file = io.BytesIO(
            b"first_name\n"
            b"Alice\n"
            b"Bob\n"
        )
        result = import_customers_csv(csv_file)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["errors"], [])

        alice = Customer.objects.get(first_name="Alice")
        self.assertEqual(alice.last_name, "")
        self.assertEqual(alice.phone, "")
        self.assertEqual(alice.account_type, "regular")
        self.assertEqual(alice.loyalty_points, 0)

    def test_import_csv_blank_optional_fields_on_create(self):
        csv_file = io.BytesIO(
            b"first_name,last_name,phone,email,account_type,loyalty_points,credit_limit\n"
            b"Minimal,,,,,,\n"
        )
        result = import_customers_csv(csv_file)
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["errors"], [])

        customer = Customer.objects.get(first_name="Minimal")
        self.assertEqual(customer.last_name, "")
        self.assertEqual(customer.phone, "")
        self.assertEqual(customer.email, "")
        self.assertEqual(customer.account_type, "regular")
        self.assertEqual(customer.loyalty_points, 0)
        self.assertEqual(customer.credit_limit, Decimal("0"))

    def test_import_csv_omitted_columns_preserve_existing_values(self):
        customer = Customer.objects.create(
            first_name="Jane",
            last_name="Doe",
            phone="0771111111",
            email="jane@example.com",
            loyalty_points=25,
            credit_limit=Decimal("75"),
        )
        csv_file = io.BytesIO(
            f"id,first_name\n{customer.id},Jane\n".encode()
        )
        result = import_customers_csv(csv_file)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["errors"], [])

        customer.refresh_from_db()
        self.assertEqual(customer.last_name, "Doe")
        self.assertEqual(customer.phone, "0771111111")
        self.assertEqual(customer.email, "jane@example.com")
        self.assertEqual(customer.loyalty_points, 25)
        self.assertEqual(customer.credit_limit, Decimal("75"))

    def test_import_csv_blank_cells_clear_fields_on_update(self):
        customer = Customer.objects.create(
            first_name="Jane",
            last_name="Doe",
            phone="0771111111",
            email="jane@example.com",
        )
        csv_file = io.BytesIO(
            f"id,first_name,last_name,phone,email\n"
            f"{customer.id},Jane,,,\n".encode()
        )
        result = import_customers_csv(csv_file)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["errors"], [])

        customer.refresh_from_db()
        self.assertEqual(customer.last_name, "")
        self.assertEqual(customer.phone, "")
        self.assertEqual(customer.email, "")


class CustomerImportApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(
            name="Test Branch",
            code="TST",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        self.user = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(user=self.user, branch=self.branch, pos_access=True)
        self.client.force_authenticate(user=self.user)

    def test_import_csv_endpoint(self):
        csv_file = io.BytesIO(
            b"first_name,last_name,phone\n"
            b"API,Customer,0774444444\n"
        )
        csv_file.name = "customers.csv"
        response = self.client.post(
            "/api/customers/import-csv/",
            {"file": csv_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created"], 1)
        self.assertTrue(Customer.objects.filter(first_name="API").exists())

    def test_export_csv_endpoint(self):
        Customer.objects.create(first_name="Download", last_name="Test")
        response = self.client.get("/api/customers/export-csv/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Download", response.content.decode())
