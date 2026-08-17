"""i18n pass for remaining interactive templates (HTML + major JS strings)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(r"c:\Users\HP\Documents\GitHub\cafe_de_paris\ui\templates\ui")


def ensure_load(text: str) -> str:
    if re.search(r"\{%\s*load\s+[^%]*%\}", text) and "i18n" in text.split("{% load")[1].split("%}")[0]:
        return text
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


CALLS = (
    "showToast",
    "confirm",
    "sortTh",
    "actionTh",
    "alert",
)


def wrap_call_string_args(js: str) -> str:
    """Wrap first string literal arg of known callables with t(...), if not already."""

    def repl(m: re.Match) -> str:
        fn = m.group(1)
        q = m.group(2)
        s = m.group(3)
        rest = m.group(4)
        # skip empty / numeric-looking / URLs / css-ish
        if not s or s.startswith("/") or s.startswith("http") or s.startswith("#"):
            return m.group(0)
        # already t(
        start = m.start()
        before = js[max(0, start - 2) : start]
        if before.endswith("t("):
            return m.group(0)
        return f"{fn}(t({q}{s}{q}){rest}"

    pattern = (
        r"\b("
        + "|".join(CALLS)
        + r")\(\s*(['\"])((?:\\.|(?!\2).)*)\2(\s*[,)])"
    )
    return re.sub(pattern, repl, js)


def wrap_quoted_ui_strings(js: str, extras: list[str]) -> str:
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
        text = apply_pairs(text, html_pairs)
        path.write_text(text, encoding="utf-8")
        print(f"ok {name} (no script)")
        return
    before, js, after = text[: m.start(2)], m.group(2), text[m.end(2) :]
    before = apply_pairs(before, html_pairs)
    js = inject_t(js)
    js = wrap_call_string_args(js)
    if js_extras:
        js = wrap_quoted_ui_strings(js, js_extras)
    path.write_text(before + js + after, encoding="utf-8")
    print(f"ok {name}")


COMMON_TABS = [
    (">All</button>", f">{th('All')}</button>"),
    (">Requested</button>", f">{th('Requested')}</button>"),
    (">Approved</button>", f">{th('Approved')}</button>"),
    (">Dispatched</button>", f">{th('Dispatched')}</button>"),
    (">Delivered</button>", f">{th('Delivered')}</button>"),
    (">Cancelled</button>", f">{th('Cancelled')}</button>"),
    (">Loading…</option>", f">{th('Loading…')}</option>"),
    (">Select destination…</option>", f">{th('Select destination…')}</option>"),
    (">Select product…</option>", f">{th('Select product…')}</option>"),
    (">Add product</button>", f">{th('Add product')}</button>"),
    ("<th>Product</th>", f"<th>{th('Product')}</th>"),
    ('<th style="text-align: right;">Qty</th>', f'<th style="text-align: right;">{th("Qty")}</th>'),
    ('<th style="text-align: right;">Available</th>', f'<th style="text-align: right;">{th("Available")}</th>'),
]

JS_COMMON = [
    "No branches available",
    "Select product…",
    "No products",
    "Available:",
    "Insufficient stock",
    "Add at least one product",
    "Transfer created",
    "Delivery note created",
    "Failed to load",
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
    "Open",
    "Save",
    "Close",
    "Loading…",
]

# --- wastage ---
process(
    "wastage.html",
    [
        ("{% block title %}Wastage — Café de Paris{% endblock %}", f"{{% block title %}}{th('Wastage')} — Café de Paris{{% endblock %}}"),
        ("{% block page_title %}Wastage{% endblock %}", f"{{% block page_title %}}{th('Wastage')}{{% endblock %}}"),
        (
            "  Record items leaving sellable stock for bakery reuse, kitchen use, or disposal.\n  Processing subtracts quantity from the source branch and, for bakery reuse, credits the bakery.",
            f"  {th('Record items leaving sellable stock for bakery reuse, kitchen use, or disposal.')}\n  {th('Processing subtracts quantity from the source branch and, for bakery reuse, credits the bakery.')}",
        ),
        (">Record wastage</h3>", f">{th('Record wastage')}</h3>"),
        ('for="wastage-branch">Branch</label>', f'for="wastage-branch">{th("Branch")}</label>'),
        ('for="wastage-product">Product</label>', f'for="wastage-product">{th("Product")}</label>'),
        ('for="wastage-quantity">Quantity</label>', f'for="wastage-quantity">{th("Quantity")}</label>'),
        ('for="wastage-reason">Reason</label>', f'for="wastage-reason">{th("Reason")}</label>'),
        (">Actual wastage/disposal</option>", f">{th('Actual wastage/disposal')}</option>"),
        (">Transferred for bakery reuse</option>", f">{th('Transferred for bakery reuse')}</option>"),
        (">Transferred to the kitchen</option>", f">{th('Transferred to the kitchen')}</option>"),
        (">Bakery destination</label>", f">{th('Bakery destination')}</label>"),
        (">Select bakery…</option>", f">{th('Select bakery…')}</option>"),
        (">Notes <span", f">{th('Notes')} <span"),
        (">(optional)</span>", f">{th('(optional)')}</span>"),
        ('placeholder="e.g. end-of-day leftovers, damaged packaging"', f'placeholder="{th("e.g. end-of-day leftovers, damaged packaging")}"'),
        ("Record &amp; process", th("Record & process")),
        (">Save as draft\n      </button>", f">{th('Save as draft')}\n      </button>"),
        ("<span>From</span>", f"<span>{th('From')}</span>"),
        ("<span>To</span>", f"<span>{th('To')}</span>"),
        ("<span>Branch</span>", f"<span>{th('Branch')}</span>"),
        (">All branches</option>", f">{th('All branches')}</option>"),
        ("<span>Reason</span>", f"<span>{th('Reason')}</span>"),
        (">All reasons</option>", f">{th('All reasons')}</option>"),
        ("<span>Status</span>", f"<span>{th('Status')}</span>"),
        (">All statuses</option>", f">{th('All statuses')}</option>"),
        ('value="draft">Draft</option>', f'value="draft">{th("Draft")}</option>'),
        ('value="processed">Processed</option>', f'value="processed">{th("Processed")}</option>'),
        ('value="cancelled">Cancelled</option>', f'value="cancelled">{th("Cancelled")}</option>'),
        (">Apply</button>", f">{th('Apply')}</button>"),
        ('placeholder="Search product, branch, reason, notes…"', f'placeholder="{th("Search product, branch, reason, notes…")}"'),
        (">Loading…</option>", f">{th('Loading…')}</option>"),
    ],
    JS_COMMON
    + [
        "Current stock: 0",
        "Select bakery…",
        "No bakery branches found",
        "Select product…",
        "No products",
        "Processed entries",
        "units total",
        "Bakery reuse",
        "entries",
        "Kitchen transfer",
        "Disposal",
        "Processed",
        "Draft",
        "Cancelled",
        "No matching wastage entries",
        "No wastage entries in this period",
        "Logged",
        "Destination",
        "Process",
        "Failed to load wastage:",
        "Fill in branch, product, quantity, and reason.",
        "Select the bakery destination for reuse transfers.",
        "Wastage recorded and stock updated.",
        "Wastage saved as draft.",
        "Failed to record wastage.",
        "Process this wastage entry and subtract from stock?",
        "Cancel this draft wastage entry?",
        "Wastage processed; stock updated.",
        "Draft cancelled.",
        "Action failed.",
        "Failed to initialize wastage page.",
        "Failed to load:",
    ],
)

# --- stock take ---
process(
    "stock_take.html",
    [
        ("{% block title %}Stock Take — Café de Paris{% endblock %}", f"{{% block title %}}{th('Stock Take')} — Café de Paris{{% endblock %}}"),
        ("{% block page_title %}Stock Take{% endblock %}", f"{{% block page_title %}}{th('Stock Take')}{{% endblock %}}"),
        ('for="branch-select">Branch</label>', f'for="branch-select">{th("Branch")}</label>'),
        ('for="count-date">Count date</label>', f'for="count-date">{th("Count date")}</label>'),
        (">Start daily count</button>", f">{th('Start daily count')}</button>"),
        (">Start monthly count</button>", f">{th('Start monthly count')}</button>"),
        ("<strong>Daily</strong>", f"<strong>{th('Daily')}</strong>"),
        (" — products marked for daily count (shop stock and branch ingredients).", f" — {th('products marked for daily count (shop stock and branch ingredients).')}"),
        ("<strong>Monthly</strong>", f"<strong>{th('Monthly')}</strong>"),
        (" — ingredients plus fixed assets.", f" — {th('ingredients plus fixed assets.')}"),
        (">Active count</h3>", f">{th('Active count')}</h3>"),
        (">Download CSV</a>", f">{th('Download CSV')}</a>"),
        ("Import CSV", th("Import CSV")),
        (">Close</button>", f">{th('Close')}</button>"),
        (">Save progress</button>", f">{th('Save progress')}</button>"),
        (">Cancel</button>", f">{th('Cancel')}</button>"),
        ("Complete &amp; post variances", th("Complete & post variances")),
        ('data-filter="all">All</button>', f'data-filter="all">{th("All")}</button>'),
        ('data-filter="daily">Daily</button>', f'data-filter="daily">{th("Daily")}</button>'),
        ('data-filter="monthly">Monthly</button>', f'data-filter="monthly">{th("Monthly")}</button>'),
        ('data-filter="draft">In progress</button>', f'data-filter="draft">{th("In progress")}</button>'),
        ('data-filter="completed">Completed</button>', f'data-filter="completed">{th("Completed")}</button>'),
        (">Loading…</option>", f">{th('Loading…')}</option>"),
    ],
    JS_COMMON
    + [
        "Open counts",
        "Completed counts",
        "Variances posted",
        "No stock takes yet",
        "Type",
        "Branch",
        "Count date",
        "Lines",
        "Opened",
        "By",
        "Resume",
        "View",
        "System qty",
        "Counted qty",
        "Variance",
        "Product",
        "No lines",
        "Save progress first?",
        "Progress saved",
        "Count completed",
        "Count cancelled",
        "Cancel this count? Progress will be discarded.",
        "Complete count and post stock variances?",
        "Failed to start count",
        "Failed to load stock takes",
        "Show all",
        "With variance",
        "Zero counted",
        "Matched",
        "CSV imported",
        "Select a branch",
    ],
)

# --- grv ---
process(
    "grv.html",
    [
        ("{% block title %}GRV — Café de Paris{% endblock %}", f"{{% block title %}}{th('GRV')} — Café de Paris{{% endblock %}}"),
        ("{% block page_title %}Goods Received Voucher{% endblock %}", f"{{% block page_title %}}{th('Goods Received Voucher')}{{% endblock %}}"),
        ('data-filter="incoming">Incoming</button>', f'data-filter="incoming">{th("Incoming")}</button>'),
        ('data-filter="requested">Not approved</button>', f'data-filter="requested">{th("Not approved")}</button>'),
        ('data-filter="dispatched">Awaiting receipt</button>', f'data-filter="dispatched">{th("Awaiting receipt")}</button>'),
        ('data-filter="delivered">Received</button>', f'data-filter="delivered">{th("Received")}</button>'),
        ('data-filter="flagged">Flagged</button>', f'data-filter="flagged">{th("Flagged")}</button>'),
        ('data-filter="all">All</button>', f'data-filter="all">{th("All")}</button>'),
        (">Receive GRV</h3>", f">{th('Receive GRV')}</h3>"),
        (">Close</button>", f">{th('Close')}</button>"),
        ("<th>Product</th>", f"<th>{th('Product')}</th>"),
        ("<th>Sent</th>", f"<th>{th('Sent')}</th>"),
        ("<th>Received (good)</th>", f"<th>{th('Received (good)')}</th>"),
        ("<th>Damaged (return)</th>", f"<th>{th('Damaged (return)')}</th>"),
        ("<th>Line notes</th>", f"<th>{th('Line notes')}</th>"),
        (">Remarks</span>", f">{th('Remarks')}</span>"),
        ('placeholder="Optional notes for bakery / stores"', f'placeholder="{th("Optional notes for bakery / stores")}"'),
        (">Flag this dnote for follow-up</span>", f">{th('Flag this dnote for follow-up')}</span>"),
        (
            "Damaged or short quantities are credited back to the sender. Variance auto-flags the note.",
            th("Damaged or short quantities are credited back to the sender. Variance auto-flags the note."),
        ),
        (">Cancel</button>", f">{th('Cancel')}</button>"),
        (">Confirm receive</button>", f">{th('Confirm receive')}</button>"),
    ],
    JS_COMMON
    + [
        "Incoming",
        "Awaiting receipt",
        "Received today",
        "No delivery notes",
        "DN #",
        "From",
        "Products",
        "Receive",
        "Print",
        "Receive GRV",
        "Confirm receive",
        "GRV received",
        "Failed to load GRVs",
        "Line notes",
    ],
)

# --- branch transfers ---
process(
    "branch_transfers.html",
    [
        ("{% block title %}Branch Transfers — Café de Paris{% endblock %}", f"{{% block title %}}{th('Branch Transfers')} — Café de Paris{{% endblock %}}"),
        ("{% block page_title %}Branch → Branch{% endblock %}", f"{{% block page_title %}}{th('Branch → Branch')}{{% endblock %}}"),
        (">New branch transfer</h3>", f">{th('New branch transfer')}</h3>"),
        ('for="from-branch">From branch</label>', f'for="from-branch">{th("From branch")}</label>'),
        ('for="to-branch">To branch</label>', f'for="to-branch">{th("To branch")}</label>'),
        ('for="product">Product</label>', f'for="product">{th("Product")}</label>'),
        ('for="quantity">Qty</label>', f'for="quantity">{th("Qty")}</label>'),
        (">Create transfer</button>", f">{th('Create transfer')}</button>"),
        *COMMON_TABS,
    ],
    JS_COMMON
    + [
        "New branch transfer",
        "Create transfer",
        "Transfer created",
        "No transfers yet",
        "Pending approval",
        "In transit",
    ],
)

# --- bakery transfers (transfers.html) ---
process(
    "transfers.html",
    [
        ("{% block title %}Stock Transfers — Café de Paris{% endblock %}", f"{{% block title %}}{th('Stock Transfers')} — Café de Paris{{% endblock %}}"),
        ("{% block page_title %}Bakery → Stores & Branches{% endblock %}", f"{{% block page_title %}}{th('Bakery → Stores & Branches')}{{% endblock %}}"),
        (">Record production</a>", f">{th('Record production')}</a>"),
        (">New delivery note</h3>", f">{th('New delivery note')}</h3>"),
        ('for="from-branch">Central bakery</label>', f'for="from-branch">{th("Central bakery")}</label>'),
        ('for="to-branch">Destination (stores or branch)</label>', f'for="to-branch">{th("Destination (stores or branch)")}</label>'),
        ('for="product">Product</label>', f'for="product">{th("Product")}</label>'),
        ('for="quantity">Qty</label>', f'for="quantity">{th("Qty")}</label>'),
        (">Create delivery note</button>", f">{th('Create delivery note')}</button>"),
        *COMMON_TABS,
    ],
    JS_COMMON
    + [
        "Create delivery note",
        "Delivery note created",
        "No delivery notes yet",
        "Central bakery",
    ],
)

print("pass A done")
