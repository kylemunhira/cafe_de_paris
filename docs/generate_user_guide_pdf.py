"""Generate Café de Paris end-user guide PDF (English)."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(__file__).resolve().parent / "Cafe_de_Paris_User_Guide.pdf"

BRAND = colors.HexColor("#1a2332")
ACCENT = colors.HexColor("#b8956a")
MUTED = colors.HexColor("#5c6570")
LIGHT = colors.HexColor("#f5f2eb")
LINE = colors.HexColor("#d4cfc4")
WHITE = colors.white


def styles():
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=26,
            textColor=BRAND,
            alignment=TA_CENTER,
            spaceAfter=8,
            leading=32,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=5,
            leading=15,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=BRAND,
            spaceBefore=12,
            spaceAfter=6,
            leading=17,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            textColor=ACCENT,
            spaceBefore=9,
            spaceAfter=4,
            leading=13,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=BRAND,
            leading=12,
            spaceAfter=4,
            alignment=TA_LEFT,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=MUTED,
            leading=11,
            spaceAfter=3,
        ),
        "toc": ParagraphStyle(
            "toc",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            textColor=BRAND,
            leading=15,
            spaceAfter=2,
            leftIndent=4,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=BRAND,
            leading=12,
            leftIndent=4,
        ),
        "tip": ParagraphStyle(
            "tip",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8.5,
            textColor=MUTED,
            leading=11,
            spaceBefore=2,
            spaceAfter=4,
            leftIndent=6,
            rightIndent=6,
        ),
        "step": ParagraphStyle(
            "step",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=BRAND,
            leading=12,
            leftIndent=4,
        ),
    }


def section_rule():
    t = Table([[""]], colWidths=[170 * mm])
    t.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 1.5, ACCENT),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def simple_table(headers, rows, col_widths=None):
    style_n = ParagraphStyle(
        "th", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, leading=10
    )
    style_c = ParagraphStyle(
        "td", fontName="Helvetica", fontSize=8, textColor=BRAND, leading=10
    )
    data = [[Paragraph(h, style_n) for h in headers]]
    for row in rows:
        data.append([Paragraph(str(c), style_c) for c in row])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("BACKGROUND", (0, 1), (-1, -1), LIGHT),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT, WHITE]),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def bullets(items, s):
    return ListFlowable(
        [
            ListItem(Paragraph(i, s["bullet"]), leftIndent=10, bulletColor=ACCENT)
            for i in items
        ],
        bulletType="bullet",
        start="•",
        leftIndent=12,
        bulletFontSize=9,
        bulletColor=ACCENT,
    )


def numbered(items, s):
    return ListFlowable(
        [ListItem(Paragraph(i, s["step"]), leftIndent=12) for i in items],
        bulletType="1",
        leftIndent=16,
        bulletFontSize=9,
        bulletColor=BRAND,
    )


def tip(text, s):
    return Paragraph(f"<b>Tip:</b> {text}", s["tip"])


def add_header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, A4[1] - 12 * mm, A4[0] - 18 * mm, A4[1] - 12 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, A4[1] - 10 * mm, "Café de Paris — User Guide")
    canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 10 * mm, "Staff operations")
    canvas.line(18 * mm, 12 * mm, A4[0] - 18 * mm, 12 * mm)
    canvas.drawCentredString(A4[0] / 2, 7 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _cover_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(BRAND)
    canvas.rect(0, 0, 8 * mm, A4[1], fill=1, stroke=0)
    canvas.setFillColor(ACCENT)
    canvas.rect(8 * mm, 0, 2 * mm, A4[1], fill=1, stroke=0)
    canvas.restoreState()


def build():
    s = styles()
    story = []

    # Cover
    story.append(Spacer(1, 42 * mm))
    story.append(Paragraph("Café de Paris", s["cover_title"]))
    story.append(Paragraph("User Guide", s["cover_title"]))
    story.append(Spacer(1, 5 * mm))
    story.append(section_rule())
    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            "Practical how-to guide for staff using the Management Console, "
            "Point of Sale, kitchen display, bakery, stores, and reports.",
            s["cover_sub"],
        )
    )
    story.append(Paragraph("Language: English · Audience: Cashiers, waiters, managers, bakery & stores staff, HQ", s["cover_sub"]))
    story.append(Paragraph("Timezone: Africa/Harare · Fiscal: ZIMRA (where enabled)", s["cover_sub"]))
    story.append(Spacer(1, 18 * mm))
    story.append(
        Paragraph(
            "Menus you see depend on your role and branch type. "
            "If a screen is missing, ask your manager to check your user permissions.",
            s["small"],
        )
    )
    story.append(PageBreak())

    # TOC
    story.append(Paragraph("Contents", s["h1"]))
    story.append(section_rule())
    for line in [
        "1. Getting started",
        "2. Roles & what you can do",
        "3. Point of Sale (cashiers & waiters)",
        "4. Kitchen display",
        "5. Orders, invoices & fiscal receipts",
        "6. Stock take, adjustments & wastage",
        "7. Transfers & GRV (goods received)",
        "8. Bakery production & recipes",
        "9. Purchases, suppliers & central invoices",
        "10. Customers & account payments",
        "11. Expenses & day end",
        "12. Products & catalogue",
        "13. Users, branches & audit log",
        "14. Reports & payment rates",
        "15. Quick troubleshooting",
    ]:
        story.append(Paragraph(line, s["toc"]))
    story.append(PageBreak())

    # 1 Getting started
    story.append(Paragraph("1. Getting started", s["h1"]))
    story.append(section_rule())
    story.append(Paragraph("1.1 Sign in", s["h2"]))
    story.append(
        Paragraph(
            "Open the Café de Paris Management Console in your browser (or the desktop / tablet POS app).",
            s["body"],
        )
    )
    story.append(
        numbered(
            [
                "Enter your <b>username and password</b>, <b>or</b> your unique <b>4-digit access code</b>.",
                "Choose a language from the selector if needed (this guide is English).",
                "You land on the home screen for your role (often Point of Sale, Bakery Production, GRV, or Dashboard).",
            ],
            s,
        )
    )
    story.append(tip("Keep your access code private. Managers use codes to approve restricted actions.", s))

    story.append(Paragraph("1.2 The console layout", s["h2"]))
    story.append(
        bullets(
            [
                "<b>Sidebar</b> — main menu (items appear based on your role).",
                "<b>Top bar</b> — page title, language, your username, Log out.",
                "<b>Main area</b> — forms, lists, POS cart, reports.",
            ],
            s,
        )
    )

    story.append(Paragraph("1.3 Branch types (how the business is organised)", s["h2"]))
    story.append(
        simple_table(
            ["Type", "What it does"],
            [
                ["Headquarters (HQ)", "Oversight, users, multi-branch reports, configuration"],
                ["Branch (café)", "POS sales, kitchen, stock take, receive deliveries, expenses"],
                ["Bakery", "Produce finished goods from recipes; send bakery transfers"],
                ["Central Stores", "Buy stock from suppliers; send stores transfers; wholesale invoices"],
            ],
            col_widths=[42 * mm, 128 * mm],
        )
    )

    # 2 Roles
    story.append(Paragraph("2. Roles & what you can do", s["h1"]))
    story.append(section_rule())
    story.append(
        simple_table(
            ["Role", "Typical daily work"],
            [
                ["HQ Admin", "Dashboard, all branches, users, suppliers, fiscal overview, reports"],
                ["Branch Manager", "Run the café: POS, orders, stock, transfers, tables, approve fiscal"],
                ["Cashier", "Take orders, collect payment, stock take, customer payments, day end"],
                ["Waiter", "Enter orders only (no payment / receipt / day end)"],
                ["Baker", "Bakery production sheets and bakery transfers"],
                ["Staff", "Receive goods on the GRV screen"],
            ],
            col_widths=[38 * mm, 132 * mm],
        )
    )
    story.append(
        Paragraph(
            "Branch managers and HQ usually do not need an access code for order cancels; "
            "cashiers and waiters may be prompted for a manager code.",
            s["small"],
        )
    )
    story.append(PageBreak())

    # 3 POS
    story.append(Paragraph("3. Point of Sale (cashiers & waiters)", s["h1"]))
    story.append(section_rule())
    story.append(
        Paragraph(
            "Open <b>Point of Sale</b> from the sidebar. Cashiers see two modes; waiters see Order only.",
            s["body"],
        )
    )

    story.append(Paragraph("3.1 Place an order (Order mode)", s["h2"]))
    story.append(
        numbered(
            [
                "Confirm the correct <b>Branch</b>.",
                "Choose <b>Takeaway</b> or <b>Dine In</b>. For dine-in, pick a <b>Table</b>.",
                "Optionally select a <b>Customer</b> (or leave Walk-in).",
                "Search or tap categories to add products. Add any required <b>add-ons</b>.",
                "Review the cart totals (tax / levy included where configured).",
                "Submit the order. Print an <b>order slip</b> for the kitchen if needed.",
            ],
            s,
        )
    )
    story.append(tip("Waiters stop here. The kitchen board updates when the order is placed.", s))

    story.append(Paragraph("3.2 Collect payment (Receipt mode)", s["h2"]))
    story.append(
        numbered(
            [
                "Switch to <b>Receipt</b> mode.",
                "Select an open or unpaid order from the list.",
                "Choose tender: cash, bank, EcoCash, split currencies, or <b>customer account</b>.",
                "Confirm payment. A receipt number is assigned.",
                "Print the receipt when prompted.",
            ],
            s,
        )
    )
    story.append(
        bullets(
            [
                "Stock is deducted when the order is paid (finished bakery items or recipe ingredients).",
                "You can cancel open unpaid orders (no stock impact). Voiding paid sales may need a manager and is blocked after fiscal approval.",
            ],
            s,
        )
    )

    story.append(Paragraph("3.3 POS shortcuts (top bar)", s["h2"]))
    story.append(
        simple_table(
            ["Button", "Use it to"],
            [
                ["Fiscal day", "Open or close the fiscal day (managers, fiscal branches)"],
                ["Stock take", "Jump to stock take before day end"],
                ["Customer payment", "Record a deposit onto a customer account"],
                ["Add expense", "Log a branch expense against the till"],
                ["Day end", "Cash up and close the trading day"],
            ],
            col_widths=[40 * mm, 130 * mm],
        )
    )

    # 4 Kitchen
    story.append(Paragraph("4. Kitchen display", s["h1"]))
    story.append(section_rule())
    story.append(
        numbered(
            [
                "Open <b>Kitchen</b> from the sidebar.",
                "Filter by station (bar / kitchen) if your account is station-scoped.",
                "New tickets appear as pending. Move them: <b>Preparing</b> → <b>Ready</b>.",
                "Paid orders leave the board when complete.",
            ],
            s,
        )
    )
    story.append(
        tip(
            "Adding items to an open order can send the ticket back to pending so nothing is missed.",
            s,
        )
    )
    story.append(PageBreak())

    # 5 Orders / fiscal
    story.append(Paragraph("5. Orders, invoices & fiscal receipts", s["h1"]))
    story.append(section_rule())

    story.append(Paragraph("5.1 Orders", s["h2"]))
    story.append(
        Paragraph(
            "Use <b>Orders</b> to search recent sales (about the last month). Filter by All / Open / Unpaid / Paid / Cancelled. "
            "Search by order number, branch, receipt number, or staff.",
            s["body"],
        )
    )

    story.append(Paragraph("5.2 Invoices", s["h2"]))
    story.append(
        Paragraph(
            "<b>Invoices</b> lists POS receipts and transfer invoices. Print copies and mark transfer invoices as paid when applicable.",
            s["body"],
        )
    )

    story.append(Paragraph("5.3 Fiscal branches (ZIMRA)", s["h2"]))
    story.append(
        bullets(
            [
                "<b>Proforma</b> — paid sales waiting for fiscal approval (today’s fiscal snapshot).",
                "<b>Fiscalise</b> — issued fiscal receipts after a manager approves and submits to ZIMRA.",
                "Open the <b>fiscal day</b> before trading; close it when the day is finished.",
                "VAT reports only include fiscalised (approved) sales — pending proformas are excluded.",
            ],
            s,
        )
    )
    story.append(
        Paragraph(
            "Non-fiscal branches: pay → receipt number → print thermal receipt. No Proforma / Fiscalise steps.",
            s["small"],
        )
    )

    # 6 Stock
    story.append(Paragraph("6. Stock take, adjustments & wastage", s["h1"]))
    story.append(section_rule())

    story.append(Paragraph("6.1 Stock take", s["h2"]))
    story.append(
        numbered(
            [
                "Open <b>Stock Take</b>.",
                "Create or continue a <b>daily</b> take (shop stock + branch ingredients) or a <b>monthly</b> take (ingredients + assets).",
                "Enter counted quantities (or import CSV where available).",
                "Complete the take so variances are posted to stock.",
            ],
            s,
        )
    )
    story.append(
        tip(
            "Day end often requires a completed daily stock take first. If day end is blocked, finish stock take and try again.",
            s,
        )
    )

    story.append(Paragraph("6.2 Stock adjustment", s["h2"]))
    story.append(
        Paragraph(
            "Managers use <b>Stock adjustment</b> to increase or decrease quantities by item type when a count correction or write-up is needed outside a full take.",
            s["body"],
        )
    )

    story.append(Paragraph("6.3 Wastage", s["h2"]))
    story.append(
        bullets(
            [
                "Record disposal of damaged or expired goods.",
                "Options may include bakery reuse or kitchen transfer, depending on branch setup.",
                "Always record wastage promptly so reports and costing stay accurate.",
            ],
            s,
        )
    )
    story.append(PageBreak())

    # 7 Transfers & GRV
    story.append(Paragraph("7. Transfers & GRV (goods received)", s["h1"]))
    story.append(section_rule())
    story.append(
        Paragraph(
            "Stock moves between Central Stores, Bakery, and café Branches using transfer documents. "
            "Receiving locations confirm goods on <b>GRV</b> or Branch Transfers.",
            s["body"],
        )
    )

    story.append(Paragraph("7.1 Types of transfers", s["h2"]))
    story.append(
        simple_table(
            ["Screen", "Direction"],
            [
                ["Bakery Transfers", "Bakery → stores or café branches"],
                ["Stores Transfers", "Central Stores → branches or bakery"],
                ["Branch Transfers", "Branch ↔ branch (send and receive)"],
            ],
            col_widths=[42 * mm, 128 * mm],
        )
    )

    story.append(Paragraph("7.2 How to receive (GRV)", s["h2"]))
    story.append(
        numbered(
            [
                "Open <b>GRV</b> (or Branch Transfers for cashiers receiving branch-to-branch stock).",
                "Find the pending delivery note.",
                "Confirm quantities received. Flag damaged lines when needed.",
                "Complete receive so stock is credited to your branch.",
            ],
            s,
        )
    )
    story.append(
        tip(
            "Cashiers typically receive branch transfers on Branch Transfers, not the full GRV console.",
            s,
        )
    )

    # 8 Bakery
    story.append(Paragraph("8. Bakery production & recipes", s["h1"]))
    story.append(section_rule())

    story.append(Paragraph("8.1 Recipes", s["h2"]))
    story.append(
        Paragraph(
            "Under <b>Recipes</b>, maintain the bill of materials (ingredients per finished product). "
            "Review recipe cost versus selling price and margin before production.",
            s["body"],
        )
    )

    story.append(Paragraph("8.2 Bakery production", s["h2"]))
    story.append(
        numbered(
            [
                "Open <b>Bakery Production</b>.",
                "Select the production date and destination sheet as required.",
                "Enter quantities to produce. Check that ingredient stock is sufficient.",
                "Complete the sheet — ingredients are consumed and finished goods are added to bakery stock.",
                "Send finished goods out with <b>Bakery Transfers</b> (delivery notes).",
            ],
            s,
        )
    )

    # 9 Purchases
    story.append(Paragraph("9. Purchases, suppliers & central invoices", s["h1"]))
    story.append(section_rule())

    story.append(Paragraph("9.1 Suppliers & Purchases", s["h2"]))
    story.append(
        numbered(
            [
                "Maintain suppliers under <b>List Suppliers</b> (HQ).",
                "Open <b>Purchases</b> to record a purchase into Central Stores (raw materials or POS products).",
                "Add lines and quantities, then save — stock increases at stores when received.",
            ],
            s,
        )
    )

    story.append(Paragraph("9.2 Central Invoice (wholesale)", s["h2"]))
    story.append(
        Paragraph(
            "Use <b>Central Invoice</b> when Central Stores sells bakery/store goods to an <b>external customer</b> "
            "(not an inter-branch transfer). Print the invoice and mark it paid when payment is received. "
            "Cancelling restocks the stores.",
            s["body"],
        )
    )
    story.append(PageBreak())

    # 10 Customers
    story.append(Paragraph("10. Customers & account payments", s["h1"]))
    story.append(section_rule())

    story.append(Paragraph("10.1 Customer list", s["h2"]))
    story.append(
        bullets(
            [
                "Add or edit customers under <b>List Customer</b>.",
                "Types: <b>Regular</b>, <b>Family</b>, <b>Staff</b> (staff may use cost pricing where configured).",
                "Set credit limits and loyalty fields as your policy requires.",
                "Import / export CSV when available for bulk updates.",
            ],
            s,
        )
    )

    story.append(Paragraph("10.2 Customer accounts", s["h2"]))
    story.append(
        numbered(
            [
                "Open <b>Customer Accounts</b> (or <b>Customer Payment</b> from POS / sidebar for cashiers).",
                "Select the customer and record a payment / deposit.",
                "At POS, charge an order to the account when the customer has enough balance / credit.",
                "Print statements from the accounts screen when customers request them.",
            ],
            s,
        )
    )
    story.append(
        tip(
            "HQ can adjust balances when correcting errors; use audit trail for accountability.",
            s,
        )
    )

    # 11 Expenses & day end
    story.append(Paragraph("11. Expenses & day end", s["h1"]))
    story.append(section_rule())

    story.append(Paragraph("11.1 Expenses", s["h2"]))
    story.append(
        Paragraph(
            "Record branch expenses from <b>Expenses</b> or the POS <b>Add expense</b> button. "
            "Include currency and optional supplier. Expenses reduce expected till at day end.",
            s["body"],
        )
    )

    story.append(Paragraph("11.2 Day end (cash-up)", s["h2"]))
    story.append(
        numbered(
            [
                "Complete the <b>daily stock take</b> if required.",
                "From POS, open <b>Day end</b>.",
                "Review sales, customer deposits, and expenses for the day.",
                "Count the till per currency and enter actual amounts.",
                "Save the day-end close and print the day-end report.",
            ],
            s,
        )
    )
    story.append(
        Paragraph(
            "Expected till ≈ sales + customer deposits − expenses. Investigate large variances before closing.",
            s["small"],
        )
    )

    # 12 Products
    story.append(Paragraph("12. Products & catalogue", s["h1"]))
    story.append(section_rule())
    story.append(
        simple_table(
            ["Screen", "Purpose"],
            [
                ["List Products", "Made-to-order menu items: price, category, branch availability, POS station"],
                ["Menu Add-ons", "Groups (choose one / any) and options shown on POS"],
                ["List Ingredients", "Raw materials tracked in inventory and recipes"],
                ["Product Categories", "Grouping, POS visibility, asset flags"],
                ["Bakery Products", "Finished bakery goods for production and transfer"],
            ],
            col_widths=[42 * mm, 128 * mm],
        )
    )
    story.append(
        tip(
            "If a product does not appear on POS, check category visibility, branch availability, and that the item is active.",
            s,
        )
    )
    story.append(PageBreak())

    # 13 Users / branches / audit
    story.append(Paragraph("13. Users, branches & audit log", s["h1"]))
    story.append(section_rule())

    story.append(Paragraph("13.1 Users", s["h2"]))
    story.append(
        Paragraph(
            "HQ (and authorised managers) use <b>Users</b> to create staff accounts: username, password, "
            "4-digit access code, role, home branch, POS access, and kitchen station.",
            s["body"],
        )
    )

    story.append(Paragraph("13.2 Branches", s["h2"]))
    story.append(
        Paragraph(
            "Configure sites under <b>Branches</b> (HQ / Branch / Bakery / Central Stores). "
            "Branch codes appear on receipt numbers. Enable fiscalization per branch. "
            "Managers/HQ can maintain dining tables for dine-in POS.",
            s["body"],
        )
    )

    story.append(Paragraph("13.3 Audit log", s["h2"]))
    story.append(
        Paragraph(
            "The <b>Audit log</b> records sensitive actions (updates, deletes, cancels, voids). "
            "Filter by date, branch, action, and entity when investigating discrepancies.",
            s["body"],
        )
    )

    # 14 Reports
    story.append(Paragraph("14. Reports & payment rates", s["h1"]))
    story.append(section_rule())
    story.append(
        simple_table(
            ["Report", "When to use it"],
            [
                ["Ingredient Stock", "See on-hand ingredients by branch"],
                ["Ingredient Usage", "Track consumption over a date range"],
                ["Day End", "Review past cash-up closes"],
                ["Sales by Product", "Best sellers and product performance"],
                ["Voided & Cancelled", "Monitor voids and cancellations"],
                ["Customer Balances", "Account balances across customers"],
                ["VAT Report", "Fiscalised sales VAT (fiscal branches)"],
                ["Supplier Statements", "Supplier spend over a period"],
                ["Dashboard (HQ)", "Sales, profit charts, CSV export"],
            ],
            col_widths=[42 * mm, 128 * mm],
        )
    )
    story.append(Paragraph("Payment & Rates", s["h2"]))
    story.append(
        bullets(
            [
                "<b>Currency</b> — maintain currencies used at POS and expenses.",
                "<b>Rates</b> — keep exchange rates up to date for multi-currency tenders.",
                "Currency create/edit may be limited to a designated global administrator.",
            ],
            s,
        )
    )

    # 15 Troubleshooting
    story.append(Paragraph("15. Quick troubleshooting", s["h1"]))
    story.append(section_rule())
    story.append(
        simple_table(
            ["Problem", "What to try"],
            [
                ["Menu item missing", "Check role permissions and branch type; ask HQ to review Users"],
                ["Cannot pay / no Receipt mode", "Waiter accounts cannot collect payment — use a cashier or manager"],
                ["Day end blocked", "Complete today’s daily stock take, then reopen Day end"],
                ["Product missing on POS", "Check category, branch availability, and active status"],
                ["Cannot void a sale", "Fiscalised approved receipts cannot be voided; ask manager"],
                ["Transfer not in stock", "Confirm GRV / receive was completed at the destination"],
                ["Fiscal submit fails", "Ensure fiscal day is open; check network and ask manager to re-approve"],
                ["Wrong language", "Use the language selector on the login page or top bar"],
            ],
            col_widths=[48 * mm, 122 * mm],
        )
    )

    story.append(Spacer(1, 8 * mm))
    story.append(section_rule())
    story.append(Paragraph("Printables you may see", s["h2"]))
    story.append(
        bullets(
            [
                "Order slips (kitchen) · Customer receipts · Transfer / delivery notes",
                "Central invoices · Customer statements · Supplier statements · Day-end close printout",
            ],
            s,
        )
    )

    story.append(Spacer(1, 10 * mm))
    story.append(section_rule())
    story.append(
        Paragraph(
            "Related document: <b>Café de Paris — Application Process Flow</b> (ops overview). "
            "Regenerate this guide with: <font face='Courier'>python docs/generate_user_guide_pdf.py</font>",
            s["small"],
        )
    )

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Café de Paris — User Guide",
        author="Café de Paris",
    )
    doc.build(story, onFirstPage=_cover_page, onLaterPages=add_header_footer)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()
