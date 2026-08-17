"""i18n for pos.html — HTML/modals + major JS UI strings."""
from __future__ import annotations

import re
from pathlib import Path

PATH = Path(r"c:\Users\HP\Documents\GitHub\cafe_de_paris\ui\templates\ui\pos.html")


def th(s: str) -> str:
    return '{% trans "' + s.replace("\\", "\\\\").replace('"', '\\"') + '" %}'


HTML_PAIRS = [
    ("{% load static l10n %}", "{% load static l10n i18n %}"),
    ("{% block title %}Point of Sale — Café de Paris{% endblock %}", f"{{% block title %}}{th('Point of Sale')} — Café de Paris{{% endblock %}}"),
    ("{% block page_title %}Point of Sale{% endblock %}", f"{{% block page_title %}}{th('Point of Sale')}{{% endblock %}}"),
    (">Fiscal day</button>", f">{th('Fiscal day')}</button>"),
    (">Stock take</button>", f">{th('Stock take')}</button>"),
    (">Customer payment</button>", f">{th('Customer payment')}</button>"),
    (">Add expense</button>", f">{th('Add expense')}</button>"),
    (">Day end</button>", f">{th('Day end')}</button>"),
    ('aria-label="POS mode"', f'aria-label="{th("POS mode")}"'),
    ('data-mode="order" role="tab" aria-selected="true">Order</button>', f'data-mode="order" role="tab" aria-selected="true">{th("Order")}</button>'),
    ('data-mode="receipt" role="tab" aria-selected="false">Receipt</button>', f'data-mode="receipt" role="tab" aria-selected="false">{th("Receipt")}</button>'),
    ('for="branch-select">Branch</label>', f'for="branch-select">{th("Branch")}</label>'),
    (">Loading…</option>", f">{th('Loading…')}</option>"),
    ('for="order-type">Order Type</label>', f'for="order-type">{th("Order Type")}</label>'),
    (">Takeaway</option>", f">{th('Takeaway')}</option>"),
    (">Dine In</option>", f">{th('Dine In')}</option>"),
    ('for="table-select-btn">Table</label>', f'for="table-select-btn">{th("Table")}</label>'),
    (">Choose table…</span>", f">{th('Choose table…')}</span>"),
    ('for="order-customer">Customer (optional)</label>', f'for="order-customer">{th("Customer (optional)")}</label>'),
    (">Walk-in</option>", f">{th('Walk-in')}</option>"),
    ('placeholder="Search products…"', f'placeholder="{th("Search products…")}"'),
    (">Open orders</h3>", f">{th('Open orders')}</h3>"),
    (">Open and unpaid · select to collect payment or cancel</p>", f">{th('Open and unpaid · select to collect payment or cancel')}</p>"),
    (">No open orders</p>", f">{th('No open orders')}</p>"),
    (">Current Order</h3>", f">{th('Current Order')}</h3>"),
    (">Tap products to add items</p>", f">{th('Tap products to add items')}</p>"),
    (">Payment method</label>", f">{th('Payment method')}</label>"),
    ('aria-label="Payment method"', f'aria-label="{th("Payment method")}"'),
    (">Cash</button>", f">{th('Cash')}</button>"),
    (">Customer account</button>", f">{th('Customer account')}</button>"),
    ('for="receipt-customer">Customer</label>', f'for="receipt-customer">{th("Customer")}</label>'),
    (">Walk-in (no account)</option>", f">{th('Walk-in (no account)')}</option>"),
    (">Credit limit: <strong", f">{th('Credit limit:')} <strong"),
    ("> · Priced at cost</span>", f"> · {th('Priced at cost')}</span>"),
    (">Payment currency</label>", f">{th('Payment currency')}</label>"),
    ('aria-label="Payment currency"', f'aria-label="{th("Payment currency")}"'),
    (">Loading…</span>", f">{th('Loading…')}</span>"),
    (">Split across payment currencies</span>", f">{th('Split across payment currencies')}</span>"),
    (">Put rest on base</button>", f">{th('Put rest on base')}</button>"),
    (">Total</span>", f">{th('Total')}</span>"),
    (">Place Order\n      </button>", f">{th('Place Order')}\n      </button>"),
    (">Order actions</div>", f">{th('Order actions')}</div>"),
    (">Cancel entire order\n        </button>", f">{th('Cancel entire order')}\n        </button>"),
    (">Transfer to table…\n        </button>", f">{th('Transfer to table…')}\n        </button>"),
    (">Clear Cart\n      </button>", f">{th('Clear Cart')}\n      </button>"),
    (">Start stock take</h3>", f">{th('Start stock take')}</h3>"),
    (">Close</button>", f">{th('Close')}</button>"),
    ('for="pos-stock-date">Count date</label>', f'for="pos-stock-date">{th("Count date")}</label>'),
    ('for="pos-stock-type">Count type</label>', f'for="pos-stock-type">{th("Count type")}</label>'),
    (">Daily</option>", f">{th('Daily')}</option>"),
    (">Monthly</option>", f">{th('Monthly')}</option>"),
    (">Start count</button>", f">{th('Start count')}</button>"),
    (
        "Enter the physical quantity for every item. System quantities remain hidden while counting.",
        th("Enter the physical quantity for every item. System quantities remain hidden while counting."),
    ),
    (">Choose the count type and start a count.</p>", f">{th('Choose the count type and start a count.')}</p>"),
    (">Save progress</button>", f">{th('Save progress')}</button>"),
    ("Complete &amp; post variances", th("Complete & post variances")),
    (">Record customer payment</h3>", f">{th('Record customer payment')}</h3>"),
    ('for="pos-payment-customer">Customer</label>', f'for="pos-payment-customer">{th("Customer")}</label>'),
    (">Select a customer</p>", f">{th('Select a customer')}</p>"),
    ('for="pos-payment-currency">Currency</label>', f'for="pos-payment-currency">{th("Currency")}</label>'),
    ('for="pos-payment-amount">Amount received</label>', f'for="pos-payment-amount">{th("Amount received")}</label>'),
    ('for="pos-payment-notes">Notes (optional)</label>', f'for="pos-payment-notes">{th("Notes (optional)")}</label>'),
    (">Cancel</button>", f">{th('Cancel')}</button>"),
    (">Record payment</button>", f">{th('Record payment')}</button>"),
    (">Record expense</h3>", f">{th('Record expense')}</h3>"),
    ('for="expense-date">Date</label>', f'for="expense-date">{th("Date")}</label>'),
    ('for="expense-supplier">Supplier</label>', f'for="expense-supplier">{th("Supplier")}</label>'),
    (">None (optional)</option>", f">{th('None (optional)')}</option>"),
    ('for="expense-description">Description</label>', f'for="expense-description">{th("Description")}</label>'),
    ('placeholder="e.g. Milk delivery, petty cash"', f'placeholder="{th("e.g. Milk delivery, petty cash")}"'),
    ('for="expense-currency">Currency</label>', f'for="expense-currency">{th("Currency")}</label>'),
    ('for="expense-amount">Amount</label>', f'for="expense-amount">{th("Amount")}</label>'),
    (">Save expense</button>", f">{th('Save expense')}</button>"),
    (">Day-end cash-up</h3>", f">{th('Day-end cash-up')}</h3>"),
    ('for="dayend-date">Report date</label>', f'for="dayend-date">{th("Report date")}</label>'),
    (
        "Enter counted amounts per currency. Leave blank for currencies you have not counted.\n      On fiscal branches, count only one currency code (USD or ZWG) — do not mix them.",
        f"{th('Enter counted amounts per currency. Leave blank for currencies you have not counted.')}\n      {th('On fiscal branches, count only one currency code (USD or ZWG) — do not mix them.')}",
    ),
    ('for="dayend-currency-code">Currency code</label>', f'for="dayend-currency-code">{th("Currency code")}</label>'),
    (">Print cash-up</button>", f">{th('Print cash-up')}</button>"),
    (">Completed daily stock take required</h3>", f">{th('Completed daily stock take required')}</h3>"),
    (">Go to stock take</a>", f">{th('Go to stock take')}</a>"),
    (">Select table</h3>", f">{th('Select table')}</h3>"),
    (
        "Tap a table to select it. Highlighted tables have open dine-in orders.",
        th("Tap a table to select it. Highlighted tables have open dine-in orders."),
    ),
    (
        "Rename or remove tables. Changes apply to this branch only.",
        th("Rename or remove tables. Changes apply to this branch only."),
    ),
    ('placeholder="New table name (e.g. T12)"', f'placeholder="{th("New table name (e.g. T12)")}"'),
    (">Add table</button>", f">{th('Add table')}</button>"),
    (">Manage tables</button>", f">{th('Manage tables')}</button>"),
    (">Transfer to order</h3>", f">{th('Transfer to order')}</h3>"),
    (
        "Choose an open takeaway order, or start a new one.",
        th("Choose an open takeaway order, or start a new one."),
    ),
    (">Fiscal day</h3>", f">{th('Fiscal day')}</h3>"),
    (">Fiscal day #</label>", f">{th('Fiscal day #')}</label>"),
    (">Last receipt global #</label>", f">{th('Last receipt global #')}</label>"),
    (
        "Open the fiscal day before approving receipts. Close it at end of trading.",
        th("Open the fiscal day before approving receipts. Close it at end of trading."),
    ),
    (">Refresh</button>", f">{th('Refresh')}</button>"),
    (">Open day</button>", f">{th('Open day')}</button>"),
    (">Close day</button>", f">{th('Close day')}</button>"),
    (">Add-ons</h3>", f">{th('Add-ons')}</h3>"),
    ('for="addon-modal-notes">Order notes</label>', f'for="addon-modal-notes">{th("Order notes")}</label>'),
    ('placeholder="Special instructions for kitchen…"', f'placeholder="{th("Special instructions for kitchen…")}"'),
    (">Add to cart</button>", f">{th('Add to cart')}</button>"),
]

JS_EXTRAS = [
    "All",
    "No products match your search",
    "No products in this category",
    "Tap products to add items",
    "Current Order",
    "Collect Payment",
    "Place Order",
    "Clear Cart",
    "Pay Now",
    "Open orders",
    "No open orders",
    "Order placed",
    "Payment collected",
    "Cart cleared",
    "Select a branch first",
    "Choose table…",
    "Select table",
    "Walk-in",
    "Takeaway",
    "Dine In",
    "Table",
    "Customer",
    "Subtotal",
    "Tax",
    "Total",
    "Change",
    "Amount tendered",
    "Remaining:",
    "Paid",
    "Cash",
    "Customer account",
    "Insufficient account balance",
    "Select a customer with an account",
    "Order cancelled",
    "Cancel this entire order?",
    "Items transferred",
    "Transfer to table…",
    "New takeaway order",
    "No open takeaway orders",
    "Add-ons",
    "Add to cart",
    "Remove",
    "Void item",
    "Void this item?",
    "Item voided",
    "Expense saved",
    "Enter description and amount",
    "Day-end report printed",
    "Select at least one counted currency",
    "Stock take started",
    "Progress saved",
    "Count completed",
    "Payment recorded",
    "Select a customer",
    "Fiscal day opened",
    "Fiscal day closed",
    "Refresh",
    "Open",
    "Closed",
    "Failed to load products",
    "Failed to place order",
    "Failed to collect payment",
    "Manage tables",
    "Done",
    "Rename",
    "Delete",
    "Table added",
    "Table updated",
    "Table deleted",
    "Delete this table?",
    "Enter a table name",
    "Loading…",
    "Credit limit:",
    "Priced at cost",
    "Account balance",
    "Available credit",
    "Order #",
    "Served by",
    "each",
    "Notes",
    "Qty",
    "Actions",
]


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


CALLS = ("showToast", "confirm", "alert", "sortTh", "actionTh")


def wrap_calls(js: str) -> str:
    def repl(m: re.Match) -> str:
        fn, q, s, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        if not s or s.startswith("/") or s.startswith("http"):
            return m.group(0)
        if js[max(0, m.start() - 2) : m.start()].endswith("t("):
            return m.group(0)
        return f"{fn}(t({q}{s}{q}){rest}"

    return re.sub(
        r"\b(" + "|".join(CALLS) + r")\(\s*(['\"])((?:\\.|(?!\2).)*)\2(\s*[,)])",
        repl,
        js,
    )


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


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    for old, new in HTML_PAIRS:
        if old in text:
            text = text.replace(old, new)
        elif new not in text and "trans" not in old:
            print(f"missing: {old[:70]!r}")

    m = re.search(r"(<script\b[^>]*>)(.*?)(</script>)", text, flags=re.I | re.S)
    if not m:
        raise SystemExit("no script")
    before, js, after = text[: m.start(2)], m.group(2), text[m.end(2) :]
    js = inject_t(js)
    js = wrap_calls(js)
    js = wrap_quoted(js, JS_EXTRAS)
    PATH.write_text(before + js + after, encoding="utf-8")
    print("ok pos.html")


if __name__ == "__main__":
    main()
