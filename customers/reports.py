from decimal import Decimal

from django.db.models import Q, Sum

from .models import Customer


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"))


def build_customer_balances_report(*, search=None, non_zero_only=False):
    qs = Customer.objects.all()

    if search:
        term = search.strip()
        if term:
            qs = qs.filter(
                Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
                | Q(phone__icontains=term)
                | Q(email__icontains=term)
            )

    if non_zero_only:
        qs = qs.filter(account_balance__gt=0)

    customers = list(qs.order_by("-account_balance", "first_name", "last_name", "id"))
    total_balance = qs.aggregate(total=Sum("account_balance"))["total"] or Decimal("0")
    with_balance = sum(1 for customer in customers if customer.account_balance > 0)

    return {
        "filters": {
            "search": search or "",
            "non_zero_only": non_zero_only,
        },
        "summary": {
            "customer_count": len(customers),
            "customers_with_balance": with_balance,
            "total_balance": _quantize(total_balance),
        },
        "customers": [
            {
                "id": customer.pk,
                "full_name": str(customer),
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "phone": customer.phone,
                "email": customer.email,
                "account_balance": customer.account_balance,
                "loyalty_points": customer.loyalty_points,
            }
            for customer in customers
        ],
    }
