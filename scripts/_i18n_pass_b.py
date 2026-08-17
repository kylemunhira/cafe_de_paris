"""i18n pass B: remaining interactive templates + helpers from pass A."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(r"c:\Users\HP\Documents\GitHub\cafe_de_paris\ui\templates\ui")


def ensure_load(text: str) -> str:
    if "i18n" in (re.search(r"\{%\s*load\s+([^%]*)%\}", text) or [None, ""])[1]:
        return text
    if "{% load static l10n %}" in text:
        return text.replace("{% load static l10n %}", "{% load static l10n i18n %}", 1)
    return text.replace("{% load static %}", "{% load static i18n %}", 1)


def th(s: str) -> str:
    return '{% trans "' + s.replace("\\", "\\\\").replace('"', '\\"') + '" %}'


def inject_t(js: str) -> str:
    if "window.CDP.t(msgid)" in js:
        return js
    lines = js.splitlines(keepends=True)
    idx = 0
    for i, line in enumerate(lines):
        if line.startswith("import "):
            idx = i + 1
    lines.insert(idx, "\nconst t = (msgid) => window.CDP.t(msgid);\n")
    return "".join(lines)


CALLS = ("showToast", "confirm", "sortTh", "actionTh", "alert")


def wrap_call_string_args(js: str) -> str:
    def repl(m: re.Match) -> str:
        fn, q, s, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        if not s or s.startswith("/") or s.startswith("http") or s.startswith("#"):
            return m.group(0)
        start = m.start()
        if js[max(0, start - 2) : start].endswith("t("):
            return m.group(0)
        return f"{fn}(t({q}{s}{q}){rest}"

    pattern = (
        r"\b(" + "|".join(CALLS) + r")\(\s*(['\"])((?:\\.|(?!\2).)*)\2(\s*[,)])"
    )
    return re.sub(pattern, repl, js)


def wrap_quoted(js: str, extras: list[str]) -> str:
    for s in sorted(set(extras), key=len, reverse=True):
        for q in ('"', "'"):
            lit = f"{q}{s}{q}"
            wrapped = f"t({lit})"
            if lit not in js:
                continue
            parts = js.split(lit)
            out = [parts[0]]
            for part in parts[1:]:
                if out[-1].endswith("t("):
                    out.append(lit + part)
                else:
                    out.append(wrapped + part)
            js = "".join(out)
    return js


def apply_pairs(text: str, pairs: list[tuple[str, str]]) -> str:
    for old, new in pairs:
        if old in text:
            text = text.replace(old, new)
    return text


def process(name: str, html_pairs: list[tuple[str, str]], js_extras: list[str] | None = None) -> None:
    path = ROOT / name
    text = ensure_load(path.read_text(encoding="utf-8"))
    m = re.search(r"(<script\b[^>]*>)(.*?)(</script>)", text, flags=re.I | re.S)
    if not m:
        path.write_text(apply_pairs(text, html_pairs), encoding="utf-8")
        print(f"ok {name} (no script)")
        return
    before, js, after = text[: m.start(2)], m.group(2), text[m.end(2) :]
    before = apply_pairs(before, html_pairs)
    js = inject_t(js)
    js = wrap_call_string_args(js)
    if js_extras:
        js = wrap_quoted(js, js_extras)
    path.write_text(before + js + after, encoding="utf-8")
    print(f"ok {name}")


JS_COMMON = [
    "No branches available",
    "Select product…",
    "No products",
    "Available:",
    "Insufficient stock",
    "Add at least one product",
    "Remove",
    "Approve",
    "Dispatch",
    "Receive",
    "Cancel",
    "Print",
    "View",
    "From",
    "To",
    "Status",
    "Date",
    "Items",
    "Actions",
    "Pending",
    "Completed",
    "Draft",
    "Close",
    "Save",
    "Loading…",
    "Failed to load",
]

COMMON_TABS = [
    (">All</button>", f">{th('All')}</button>"),
    (">Requested</button>", f">{th('Requested')}</button>"),
    (">Approved</button>", f">{th('Approved')}</button>"),
    (">Dispatched</button>", f">{th('Dispatched')}</button>"),
    (">Delivered</button>", f">{th('Delivered')}</button>"),
    (">Cancelled</button>", f">{th('Cancelled')}</button>"),
    (">Loading…</option>", f">{th('Loading…')}</option>"),
    (">Select product…</option>", f">{th('Select product…')}</option>"),
    (">Add product</button>", f">{th('Add product')}</button>"),
    ("<th>Product</th>", f"<th>{th('Product')}</th>"),
    ('<th style="text-align: right;">Qty</th>', f'<th style="text-align: right;">{th("Qty")}</th>'),
    ('<th style="text-align: right;">Available</th>', f'<th style="text-align: right;">{th("Available")}</th>'),
    ('<th style="text-align: right;">Unit cost</th>', f'<th style="text-align: right;">{th("Unit cost")}</th>'),
    ('<th style="text-align: right;">Unit price</th>', f'<th style="text-align: right;">{th("Unit price")}</th>'),
    ('<th style="text-align: right;">Line total</th>', f'<th style="text-align: right;">{th("Line total")}</th>'),
]

process(
    "stores_transfers.html",
    [
        ("{% block title %}Stores Transfers — Café de Paris{% endblock %}", f"{{% block title %}}{th('Stores Transfers')} — Café de Paris{{% endblock %}}"),
        ("{% block page_title %}Central Stores → Branches &amp; Bakery{% endblock %}", f"{{% block page_title %}}{th('Central Stores → Branches & Bakery')}{{% endblock %}}"),
        ("New delivery note &amp; invoice", th("New delivery note & invoice")),
        ('for="from-branch">Central stores</label>', f'for="from-branch">{th("Central stores")}</label>'),
        ('for="to-branch">Destination (branch, HQ, or bakery)</label>', f'for="to-branch">{th("Destination (branch, HQ, or bakery)")}</label>'),
        (">Select branch…</option>", f">{th('Select branch…')}</option>"),
        (">Ingredient type</label>", f">{th('Ingredient type')}</label>"),
        ('data-ingredient-filter="all">All</button>', f'data-ingredient-filter="all">{th("All")}</button>'),
        ('data-ingredient-filter="bakery">Bakery</button>', f'data-ingredient-filter="bakery">{th("Bakery")}</button>'),
        ('data-ingredient-filter="branch">Branch</button>', f'data-ingredient-filter="branch">{th("Branch")}</button>'),
        ('for="product">Ingredient</label>', f'for="product">{th("Ingredient")}</label>'),
        (">Select ingredient…</option>", f">{th('Select ingredient…')}</option>"),
        ('for="quantity">Qty</label>', f'for="quantity">{th("Qty")}</label>'),
        (">Add ingredient</button>", f">{th('Add ingredient')}</button>"),
        ("<th>Ingredient</th>", f"<th>{th('Ingredient')}</th>"),
        (">Create delivery note</button>", f">{th('Create delivery note')}</button>"),
        *COMMON_TABS,
    ],
    JS_COMMON
    + [
        "Select branch…",
        "Select ingredient…",
        "Add ingredient",
        "Create delivery note",
        "Delivery note created",
        "No transfers yet",
        "Invoice",
        "Mark paid",
        "Unit cost",
        "Line total",
        "Ingredient",
    ],
)

process(
    "bakery_production.html",
    [
        ("{% block title %}Bakery Production — Café de Paris{% endblock %}", f"{{% block title %}}{th('Bakery Production')} — Café de Paris{{% endblock %}}"),
        ("{% block page_title %}Bakery Production{% endblock %}", f"{{% block page_title %}}{th('Bakery Production')}{{% endblock %}}"),
        (">Bakery transfers</a>", f">{th('Bakery transfers')}</a>"),
        ('for="bakery-branch">Central bakery</label>', f'for="bakery-branch">{th("Central bakery")}</label>'),
        ('for="production-date">Production date</label>', f'for="production-date">{th("Production date")}</label>'),
        (">New production sheet</button>", f">{th('New production sheet')}</button>"),
        (
            "Enter quantities produced for each destination — Highlands, Churchill, and Central stores.\n    Completing a sheet adds finished goods to bakery stock (and deducts recipe ingredients).",
            f"{th('Enter quantities produced for each destination — Highlands, Churchill, and Central stores.')}\n    {th('Completing a sheet adds finished goods to bakery stock (and deducts recipe ingredients).')}",
        ),
        (">Active production</h3>", f">{th('Active production')}</h3>"),
        (">Close</button>", f">{th('Close')}</button>"),
        (">Save progress</button>", f">{th('Save progress')}</button>"),
        (">Cancel</button>", f">{th('Cancel')}</button>"),
        (">Complete production</button>", f">{th('Complete production')}</button>"),
        ('data-filter="all">All</button>', f'data-filter="all">{th("All")}</button>'),
        ('data-filter="draft">In progress</button>', f'data-filter="draft">{th("In progress")}</button>'),
        ('data-filter="completed">Completed</button>', f'data-filter="completed">{th("Completed")}</button>'),
        (">Loading…</option>", f">{th('Loading…')}</option>"),
    ],
    JS_COMMON
    + [
        "Open sheets",
        "Completed sheets",
        "Units produced",
        "No production sheets yet",
        "Production date",
        "Lines",
        "Opened",
        "By",
        "Resume",
        "Product",
        "Total",
        "Progress saved",
        "Production completed",
        "Sheet cancelled",
        "Cancel this production sheet?",
        "Complete this production sheet?",
        "Failed to start sheet",
        "No bakery branch configured",
        "Active production",
        "Save progress",
        "Complete production",
        "Show all",
        "With qty",
        "Empty",
    ],
)

process(
    "central_invoices.html",
    [
        ("{% block title %}Central Invoice — Café de Paris{% endblock %}", f"{{% block title %}}{th('Central Invoice')} — Café de Paris{{% endblock %}}"),
        ("{% block page_title %}Central Invoice{% endblock %}", f"{{% block page_title %}}{th('Central Invoice')}{{% endblock %}}"),
        (
            "Sell or transfer bakery products from central stores to external customers. Stock is deducted when the invoice is created.",
            th("Sell or transfer bakery products from central stores to external customers. Stock is deducted when the invoice is created."),
        ),
        (">New central invoice</h3>", f">{th('New central invoice')}</h3>"),
        ('for="from-branch">Central stores</label>', f'for="from-branch">{th("Central stores")}</label>'),
        ('for="customer">External customer</label>', f'for="customer">{th("External customer")}</label>'),
        (">Select customer…</option>", f">{th('Select customer…')}</option>"),
        ('for="product">Product</label>', f'for="product">{th("Product")}</label>'),
        ('for="quantity">Qty</label>', f'for="quantity">{th("Qty")}</label>'),
        ('for="notes">Notes (optional)</label>', f'for="notes">{th("Notes (optional)")}</label>'),
        ('placeholder="Delivery instructions, PO reference, etc."', f'placeholder="{th("Delivery instructions, PO reference, etc.")}"'),
        (">Create invoice</button>", f">{th('Create invoice')}</button>"),
        ('data-filter="all">All</button>', f'data-filter="all">{th("All")}</button>'),
        ('data-filter="dispatched">Active</button>', f'data-filter="dispatched">{th("Active")}</button>'),
        ('data-filter="unpaid">Unpaid</button>', f'data-filter="unpaid">{th("Unpaid")}</button>'),
        ('data-filter="paid">Paid</button>', f'data-filter="paid">{th("Paid")}</button>'),
        ('data-filter="cancelled">Cancelled</button>', f'data-filter="cancelled">{th("Cancelled")}</button>'),
        *COMMON_TABS,
    ],
    JS_COMMON
    + [
        "Select customer…",
        "Create invoice",
        "Invoice created",
        "No invoices yet",
        "Customer",
        "Total",
        "Mark paid",
        "Active invoices",
        "Unpaid total",
    ],
)

process(
    "purchase_orders.html",
    [
        ("{% block title %}Purchases — Café de Paris{% endblock %}", f"{{% block title %}}{th('Purchases')} — Café de Paris{{% endblock %}}"),
        ("{% block page_title %}Purchases{% endblock %}", f"{{% block page_title %}}{th('Purchases')}{{% endblock %}}"),
        (">Record purchase</h3>", f">{th('Record purchase')}</h3>"),
        (
            "Record a supplier purchase for any branch. Stock is added immediately when you save.",
            th("Record a supplier purchase for any branch. Stock is added immediately when you save."),
        ),
        ('for="po-branch">Branch</label>', f'for="po-branch">{th("Branch")}</label>'),
        ('for="po-supplier">Supplier</label>', f'for="po-supplier">{th("Supplier")}</label>'),
        (">Select supplier…</option>", f">{th('Select supplier…')}</option>"),
        ('for="po-notes">Invoice / reference</label>', f'for="po-notes">{th("Invoice / reference")}</label>'),
        ('placeholder="Supplier invoice or delivery note number"', f'placeholder="{th("Supplier invoice or delivery note number")}"'),
        (">Purchase for</label>", f">{th('Purchase for')}</label>"),
        (">Raw materials</button>", f">{th('Raw materials')}</button>"),
        (">POS products</button>", f">{th('POS products')}</button>"),
        (
            "Menu items sold at the till — same products as on POS.",
            th("Menu items sold at the till — same products as on POS."),
        ),
        ('id="po-product-label">Product</label>', f'id="po-product-label">{th("Product")}</label>'),
        ('for="po-qty">Qty</label>', f'for="po-qty">{th("Qty")}</label>'),
        ('for="po-line-total">Line total</label>', f'for="po-line-total">{th("Line total")}</label>'),
        (">Add line</button>", f">{th('Add line')}</button>"),
        (">Subtotal</td>", f">{th('Subtotal')}</td>"),
        (">VAT</td>", f">{th('VAT')}</td>"),
        (">Total</td>", f">{th('Total')}</td>"),
        (">Record purchase</button>", f">{th('Record purchase')}</button>"),
        ('data-filter="all">All</button>', f'data-filter="all">{th("All")}</button>'),
        ('data-filter="cancelled">Cancelled</button>', f'data-filter="cancelled">{th("Cancelled")}</button>'),
        *COMMON_TABS,
    ],
    JS_COMMON
    + [
        "Select supplier…",
        "Add line",
        "Record purchase",
        "Purchase recorded",
        "No purchases yet",
        "Supplier",
        "Invoice / reference",
        "Raw materials",
        "POS products",
        "Ingredient",
        "Select ingredient…",
        "Purchases this month",
        "Total spend",
    ],
)

process(
    "customer_accounts.html",
    [
        ("{% block title %}Customer Accounts — Café de Paris{% endblock %}", f"{{% block title %}}{th('Customer Accounts')} — Café de Paris{{% endblock %}}"),
        ("{% block page_title %}Customer Accounts{% endblock %}", f"{{% block page_title %}}{th('Customer Accounts')}{{% endblock %}}"),
        ('for="customer-search">Customer</label>', f'for="customer-search">{th("Customer")}</label>'),
        ('placeholder="Filter by name or phone…"', f'placeholder="{th("Filter by name or phone…")}"'),
        ('data-type="all">All</button>', f'data-type="all">{th("All")}</button>'),
        ('data-type="family">Family</button>', f'data-type="family">{th("Family")}</button>'),
        ('data-type="staff">Staff</button>', f'data-type="staff">{th("Staff")}</button>'),
        ('data-type="regular">Regular</button>', f'data-type="regular">{th("Regular")}</button>'),
        (">Account balance</div>", f">{th('Account balance')}</div>"),
        (">Print statement</button>", f">{th('Print statement')}</button>"),
        ("<span>From</span>", f"<span>{th('From')}</span>"),
        ("<span>To</span>", f"<span>{th('To')}</span>"),
        (">Apply</button>", f">{th('Apply')}</button>"),
        (">Opening balance</div>", f">{th('Opening balance')}</div>"),
        (">Payments received</div>", f">{th('Payments received')}</div>"),
        (">Withdrawals</div>", f">{th('Withdrawals')}</div>"),
        (">Closing balance</div>", f">{th('Closing balance')}</div>"),
        (">Record deposit</h3>", f">{th('Record deposit')}</h3>"),
        ('for="deposit-currency">Payment currency</label>', f'for="deposit-currency">{th("Payment currency")}</label>'),
        ('for="deposit-amount">Amount received</label>', f'for="deposit-amount">{th("Amount received")}</label>'),
        ('for="deposit-notes">Notes (optional)</label>', f'for="deposit-notes">{th("Notes (optional)")}</label>'),
        ('placeholder="e.g. Cash top-up"', f'placeholder="{th("e.g. Cash top-up")}"'),
        (">Record deposit</button>", f">{th('Record deposit')}</button>"),
        (">Adjust balance</h3>", f">{th('Adjust balance')}</h3>"),
        (
            "Enter a signed amount such as <strong>-12.00</strong> to debit, or a positive amount to credit. This posts a Balance adjustment on the customer statement.",
            th("Enter a signed amount such as -12.00 to debit, or a positive amount to credit. This posts a Balance adjustment on the customer statement."),
        ),
        ('for="adjust-amount">Adjustment amount</label>', f'for="adjust-amount">{th("Adjustment amount")}</label>'),
        ('for="adjust-notes">Notes (optional)</label>', f'for="adjust-notes">{th("Notes (optional)")}</label>'),
        ('placeholder="e.g. Correction"', f'placeholder="{th("e.g. Correction")}"'),
        (">Apply adjustment</button>", f">{th('Apply adjustment')}</button>"),
        (">Transaction history</h3>", f">{th('Transaction history')}</h3>"),
        (
            "Select a customer to view their account or record a deposit.",
            th("Select a customer to view their account or record a deposit."),
        ),
        (">Loading…</option>", f">{th('Loading…')}</option>"),
    ],
    JS_COMMON
    + [
        "Credit limit:",
        "New balance:",
        "No customers found",
        "No transactions",
        "Deposit recorded",
        "Balance adjusted",
        "Print",
        "Type",
        "Amount",
        "Balance",
        "Notes",
        "Recorded by",
        "Family",
        "Staff",
        "Regular",
        "Select a customer",
        "Failed to load customers",
        "Failed to load transactions",
        "Enter a non-zero adjustment amount.",
        "Deposit amount is required.",
    ],
)

print("pass B done")
