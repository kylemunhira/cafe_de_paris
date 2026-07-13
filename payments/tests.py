from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from .models import Currency, CurrencyRate


class PaymentModelsTests(TestCase):
    def test_base_currency_rate_must_be_one(self):
        usd = Currency.objects.create(
            code="USD",
            name="US Dollar",
            symbol="$",
            is_base=True,
        )
        rate = CurrencyRate(
            currency=usd,
            rate=Decimal("2"),
            effective_from="2026-01-01",
        )
        with self.assertRaises(Exception):
            rate.full_clean()

    def test_convert_from_base(self):
        usd = Currency.objects.create(name="US Dollar", is_base=True)
        zwl = Currency.objects.create(name="Zimbabwe Dollar")
        CurrencyRate.objects.create(
            currency=zwl,
            rate=Decimal("25.5"),
            effective_from="2026-06-01",
        )
        self.assertEqual(zwl.convert_from_base(Decimal("10")), Decimal("255.00"))

    def test_payment_options_for_amount(self):
        from .services import payment_options_for_amount

        usd = Currency.objects.create(
            code="USD",
            name="US Dollar",
            symbol="$",
            is_base=True,
        )
        zwg = Currency.objects.create(code="ZWG", name="ZiG", symbol="ZiG")
        Currency.objects.create(code="ZAR", name="Rand", symbol="R", is_active=False)
        CurrencyRate.objects.create(
            currency=zwg,
            rate=Decimal("25.5"),
            effective_from="2026-06-01",
        )

        options = payment_options_for_amount(Decimal("20"))
        self.assertEqual(len(options), 2)
        by_name = {opt["name"]: opt for opt in options}
        self.assertEqual(by_name["US Dollar"]["amount"], Decimal("20.00"))
        self.assertEqual(by_name["US Dollar"]["symbol"], "$")
        self.assertEqual(by_name["ZiG"]["amount"], Decimal("510.00"))
        self.assertNotIn("Rand", by_name)


class PaymentApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
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

    def test_duplicate_currency_name_rejected(self):
        response = self.client.post(
            "/api/currencies/",
            {"name": "US Dollar", "code": "USD2"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_create_currency_and_rate(self):
        response = self.client.post(
            "/api/currencies/",
            {"code": "ZWL", "name": "Zimbabwe Dollar", "symbol": "Z$"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        zwl_id = response.data["id"]

        rate_response = self.client.post(
            "/api/currency-rates/",
            {
                "currency": zwl_id,
                "rate": "25.500000",
                "effective_from": "2026-06-01",
            },
            format="json",
        )
        self.assertEqual(rate_response.status_code, 201)
