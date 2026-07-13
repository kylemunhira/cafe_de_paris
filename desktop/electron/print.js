const fs = require("fs");
const os = require("os");
const path = require("path");
const { BrowserWindow } = require("electron");

const RECEIPT_WIDTH_MM = 80;
const CONTENT_WIDTH_MM = 58;
const LINE_CHARS = 32;
const ITEM_NAME_W = 16;
const ITEM_QTY_W = 5;
const ITEM_AMT_W = 8;
const MM_TO_MICRONS = 1000;
const PRINT_WINDOW_WIDTH = Math.round((CONTENT_WIDTH_MM / 25.4) * 96);
let cachedReceiptStyles = null;

function resolveReceiptStylesPath() {
  const candidates = [
    path.join(__dirname, "..", "receipt-css", "receipt-print.css"),
    path.join(__dirname, "..", "..", "ui", "static", "ui", "css", "receipt-print.css"),
  ];
  if (process.resourcesPath) {
    candidates.push(path.join(process.resourcesPath, "receipt-css", "receipt-print.css"));
  }
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  throw new Error("Receipt print stylesheet not found");
}

function getReceiptStyles() {
  if (!cachedReceiptStyles) {
    cachedReceiptStyles = fs.readFileSync(resolveReceiptStylesPath(), "utf8");
  }
  return cachedReceiptStyles;
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function money(amount) {
  const value = Number(amount);
  return Number.isFinite(value) ? value.toFixed(2) : "0.00";
}

function qty(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(2) : "0.00";
}

function formatTaxRate(rate) {
  const value = Number(rate);
  return Number.isFinite(value) ? value.toFixed(1) : "0.0";
}

function formatDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const day = d.getDate();
  const month = months[d.getMonth()];
  const year = d.getFullYear();
  const hours = String(d.getHours()).padStart(2, "0");
  const mins = String(d.getMinutes()).padStart(2, "0");
  return `${day} ${month} ${year}, ${hours}:${mins}`;
}

function formatReportDate(dateStr) {
  if (!dateStr) return "—";
  const [year, month, day] = dateStr.split("-").map(Number);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${day} ${months[month - 1]} ${year}`;
}

function orderTypeLabel(value) {
  return value === "dine_in" ? "Dine In" : "Takeaway";
}

function currencyCode(currency) {
  return currency?.code || currency?.name || "";
}

function truncText(text, max) {
  const value = String(text);
  return value.length > max ? `${value.slice(0, max - 1)}.` : value;
}

function padLine(left, right, width = LINE_CHARS) {
  const l = String(left);
  const r = String(right);
  const gap = Math.max(1, width - l.length - r.length);
  return `${l}${" ".repeat(gap)}${r}`;
}

function formatPaidAmount(payment) {
  const amt = money(payment.amountPaid);
  if (payment.symbol) return `${payment.symbol}${amt}`;
  const code = payment.currencyCode || payment.currencyName || "";
  return code ? `${code} ${amt}` : amt;
}

function renderSalespersonLine(name) {
  if (!name) return "";
  return `<p>Served by ${esc(name)}</p>`;
}

function renderLocation(location) {
  if (!location) return "";
  return `<p class="address">${esc(location)}</p>`;
}

function orderTypeLine(order) {
  const type = esc(orderTypeLabel(order.order_type));
  return order.table_number
    ? `${type} · Table ${esc(order.table_number)}`
    : type;
}

function itemColumns(name, quantity, amount) {
  const label = truncText(name, ITEM_NAME_W).padEnd(ITEM_NAME_W);
  const q = qty(quantity).padStart(ITEM_QTY_W);
  const a = money(amount).padStart(ITEM_AMT_W);
  return `${label}${q}${a}`;
}

function renderItemsBlock(items) {
  if (!items?.length) {
    return `<pre class="lines">No items</pre>`;
  }

  const lines = [
    "ITEM".padEnd(ITEM_NAME_W) + "QTY".padStart(ITEM_QTY_W) + "AMT".padStart(ITEM_AMT_W),
    "-".repeat(LINE_CHARS),
  ];

  for (const item of items) {
    const price = Number(item.price);
    const lineTotal = Number(item.quantity) * price;
    const name = item.product_name || item.name || "Item";
    lines.push(itemColumns(name, item.quantity, lineTotal));
    lines.push(`  ${qty(item.quantity)} x ${money(price)}`);
    for (const addon of item.addons || []) {
      const addonPrice = Number(addon.price);
      const addonLabel =
        addonPrice > 0 ? `  + ${addon.name} (${money(addonPrice)})` : `  + ${addon.name}`;
      lines.push(addonLabel);
    }
    if (item.notes) {
      lines.push(`  Note: ${item.notes}`);
    }
  }

  return `<pre class="lines">${esc(lines.join("\n"))}</pre>`;
}

function renderSummaryBlock(rows, { grand = false, boxed = false } = {}) {
  const text = rows.map(([left, right]) => padLine(left, right)).join("\n");
  const classes = ["summary-lines", grand ? "grand" : "", boxed ? "boxed" : ""]
    .filter(Boolean)
    .join(" ");
  return `<pre class="${classes}">${esc(text)}</pre>`;
}

function renderFiscalBlock(fiscal) {
  if (!fiscal) return "";

  const lines = [
    fiscal.device_branch_name ? `<p>${esc(fiscal.device_branch_name)}</p>` : "",
    fiscal.device_serial_no ? `<p>Device: ${esc(fiscal.device_serial_no)}</p>` : "",
    fiscal.fiscal_invoice_number ? `<p>Invoice: ${esc(fiscal.fiscal_invoice_number)}</p>` : "",
    fiscal.fiscal_day_number ? `<p>Fiscal day: ${esc(fiscal.fiscal_day_number)}</p>` : "",
    fiscal.receipt_counter
      ? `<p>Receipt #${esc(fiscal.receipt_counter)} / ${esc(fiscal.receipt_global_no)}</p>`
      : "",
    fiscal.verification_code ? `<p>Verification: ${esc(fiscal.verification_code)}</p>` : "",
  ].join("");

  return `
    <hr class="divider">
    <div class="center meta fiscal-meta">
      <p><strong>Fiscal receipt</strong></p>
      ${lines}
    </div>`;
}

function renderFiscalQr(fiscal) {
  const qrString = fiscal?.qr_string || fiscal?.qrString;
  if (!qrString) return "";
  const text = JSON.stringify(qrString);
  return `
    <div class="center fiscal-qr" id="fiscal-qr" aria-label="Fiscal QR code"></div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"><\/script>
    <script>
      (function () {
        const el = document.getElementById("fiscal-qr");
        if (!el) return;
        new QRCode(el, {
          text: ${text},
          width: 120,
          height: 120,
          correctLevel: QRCode.CorrectLevel.M,
        });
      })();
    <\/script>`;
}

function renderBrandHeader(branch, { onlyIfFiscal = false } = {}) {
  if (onlyIfFiscal && !branch?.fiscalization_enabled) return "";
  return `
    <div class="center brand">
      <h1>Café de Paris</h1>
      ${renderLocation(branch?.location)}
    </div>`;
}

function renderTotalsSection(tax, baseCurrency, { showTaxBreakdown = true } = {}) {
  const baseLabel = baseCurrency ? ` (${currencyCode(baseCurrency)})` : "";
  const rows = showTaxBreakdown
    ? [
        [`Subtotal${baseLabel}`, money(tax?.subtotal)],
        [`Tax (${formatTaxRate(tax?.taxRate)}%)`, money(tax?.tax)],
        [`Total${baseLabel}`, money(tax?.total)],
      ]
    : [[`Total${baseLabel}`, money(tax?.total)]];
  return renderSummaryBlock(rows);
}

function formatPaymentOptionAmount(opt) {
  const amt = money(opt.amount);
  if (opt.symbol) return `${opt.symbol}${amt}`;
  const code = opt.code || opt.name || "";
  return code ? `${code} ${amt}` : amt;
}

function renderPaymentOptions(options) {
  if (!Array.isArray(options) || !options.length) return "";
  const rows = options.map((opt) => [
    opt.name || opt.code || "Currency",
    formatPaymentOptionAmount(opt),
  ]);
  return `
    <hr class="divider">
    <div class="center meta"><p><strong>Payment options</strong></p></div>
    ${renderSummaryBlock(rows, { boxed: true })}`;
}

function wrapDocument(title, body) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>${esc(title)}</title>
  <style>${getReceiptStyles()}</style>
  <style>
    html, body {
      margin: 0;
      padding: 0;
      width: ${CONTENT_WIDTH_MM}mm;
      background: #fff;
    }
    .receipt {
      width: ${CONTENT_WIDTH_MM}mm;
      max-width: ${CONTENT_WIDTH_MM}mm;
      margin: 0;
      padding: 2mm 1mm;
      box-shadow: none;
    }
    pre.lines,
    pre.summary-lines {
      font-family: "Courier New", Courier, monospace;
      font-size: 11px;
      line-height: 1.35;
      margin: 0;
      white-space: pre;
      width: 100%;
      overflow: hidden;
    }
    pre.summary-lines.grand {
      font-weight: 700;
      border-top: 1px solid #000;
      padding-top: 0.35rem;
      margin-top: 0.35rem;
    }
    pre.summary-lines.boxed {
      background: #f5f5f5;
      padding: 0.25rem;
      margin-top: 0.35rem;
    }
  </style>
</head>
<body>${body}</body>
</html>`;
}

function renderOrderSlipHtml(data) {
  const { branch, order, tax, baseCurrency, salesperson, paymentOptions } = data;
  const orderId = order.server_id || order.client_id?.slice(0, 8).toUpperCase() || "—";

  return wrapDocument(
    `Order ${orderId}`,
    `
    <div class="receipt">
      ${renderBrandHeader(branch, { onlyIfFiscal: true })}
      <div class="center meta">
        <p><strong>Order ticket</strong></p>
        <p>Order #${esc(orderId)}</p>
        <p>${esc(formatDateTime(order.created_at))}</p>
        <p>${orderTypeLine(order)}</p>
        ${renderSalespersonLine(salesperson)}
      </div>
      <hr class="divider">
      ${renderItemsBlock(order.items)}
      <hr class="divider">
      ${renderTotalsSection(tax, baseCurrency, { showTaxBreakdown: !!branch?.fiscalization_enabled })}
      ${renderPaymentOptions(paymentOptions)}
      <div class="center footer">
        <p>Present this ticket when paying.</p>
        <p>UNPAID</p>
      </div>
    </div>`
  );
}

function tenderMethodLabel(method) {
  const labels = { cash: "Cash", bank: "Bank", ecocash: "EcoCash" };
  return labels[method] || method || "Payment";
}

function renderReceiptHtml(data) {
  const { branch, order, tax, payment, baseCurrency, fiscal, salesperson, paymentOptions } = data;
  const orderId = order.server_id || order.client_id?.slice(0, 8).toUpperCase() || "—";
  const receiptLine = order.receipt_number ? `<p>Receipt #${esc(order.receipt_number)}</p>` : "";
  const tenderLines = Array.isArray(payment?.lines) ? payment.lines : [];
  const changeAmount = Number(payment?.changeGiven);
  const hasChange = Number.isFinite(changeAmount) && changeAmount > 0.005;
  const paymentRows = payment
    ? [
        ["Paid in", payment.currencyCode || payment.currencyName || ""],
        ...(payment.exchangeRate && !payment.isBase
          ? [["Exchange rate", String(payment.exchangeRate)]]
          : []),
        ...(hasChange
          ? [
              ["Amount tendered", formatPaidAmount(payment)],
              [
                "Change",
                formatPaidAmount({
                  amountPaid: changeAmount,
                  symbol: payment.symbol,
                  currencyCode: payment.currencyCode,
                  currencyName: payment.currencyName,
                }),
              ],
            ]
          : tenderLines.map((line) => [
              line.currencyName || line.currency_name || tenderMethodLabel(line.method),
              formatPaidAmount({
                amountPaid: line.amount,
                symbol: line.symbol || payment.symbol,
                currencyCode: line.currencyCode || payment.currencyCode,
                currencyName: line.currencyName || payment.currencyName,
              }),
            ])),
      ]
    : [];

  const paymentBlock = payment
    ? hasChange
      ? `${renderSummaryBlock(paymentRows, { boxed: true })}`
      : `
      ${renderSummaryBlock(paymentRows, { boxed: true })}
      ${renderSummaryBlock([["Amount paid", formatPaidAmount(payment)]], { grand: true })}`
    : "";

  return wrapDocument(
    `Receipt ${order.receipt_number || orderId}`,
    `
    <div class="receipt">
      ${renderBrandHeader(branch, { onlyIfFiscal: true })}
      <div class="center meta">
        <p><strong>Sales Receipt</strong></p>
        ${receiptLine}
        <p>Order #${esc(orderId)}</p>
        <p>${esc(formatDateTime(order.paid_at || order.created_at))}</p>
        <p>${orderTypeLine(order)}</p>
        ${renderSalespersonLine(salesperson)}
      </div>
      <hr class="divider">
      ${renderItemsBlock(order.items)}
      <hr class="divider">
      ${renderTotalsSection(tax, baseCurrency, { showTaxBreakdown: !!branch?.fiscalization_enabled })}
      ${paymentBlock}
      ${renderPaymentOptions(paymentOptions)}
      ${renderFiscalBlock(fiscal)}
      <div class="center footer">
        <p>Thank you for your visit!</p>
        <p>PAID</p>
      </div>
      ${renderFiscalQr(fiscal)}
    </div>`
  );
}

const PRINT_DELAY_MS = 800;
const CLEANUP_DELAY_MS = 1000;
const MIN_PAGE_HEIGHT_MM = 80;
const PAGE_MARGIN_MM = 6;

function buildPrintOptions(deviceName, { pageHeightMm, usePrinterDefault = false } = {}) {
  const options = {
    silent: true,
    printBackground: true,
    margins: { marginType: "none" },
    landscape: false,
    pagesPerSheet: 1,
    collate: false,
    copies: 1,
    scaleFactor: 100,
  };

  if (usePrinterDefault) {
    options.usePrinterDefaultPageSize = true;
  } else {
    const heightMm = Math.max(pageHeightMm || MIN_PAGE_HEIGHT_MM, MIN_PAGE_HEIGHT_MM);
    options.pageSize = {
      width: RECEIPT_WIDTH_MM * MM_TO_MICRONS,
      height: heightMm * MM_TO_MICRONS,
    };
  }

  if (deviceName) {
    options.deviceName = deviceName;
  }
  return options;
}

function writeTempHtml(html) {
  const tempPath = path.join(
    os.tmpdir(),
    `cafe-pos-print-${Date.now()}-${Math.random().toString(36).slice(2)}.html`
  );
  fs.writeFileSync(tempPath, html, "utf8");
  return tempPath;
}

function removeTempFile(tempPath) {
  try {
    fs.unlinkSync(tempPath);
  } catch {
    // Ignore cleanup errors.
  }
}

async function measureContentHeightMm(printWin) {
  const heightPx = await printWin.webContents.executeJavaScript(`
    Math.max(
      document.body.scrollHeight,
      document.documentElement.scrollHeight,
      document.body.offsetHeight
    )
  `);
  return Math.ceil((heightPx / 96) * 25.4) + PAGE_MARGIN_MM;
}

function printWithOptions(webContents, options) {
  return new Promise((resolve, reject) => {
    webContents.print(options, (success, failureReason) => {
      if (success) resolve();
      else reject(new Error(failureReason || "Print failed"));
    });
  });
}

function printHtml(html, { deviceName } = {}) {
  return new Promise((resolve, reject) => {
    const tempPath = writeTempHtml(html);
    const printWin = new BrowserWindow({
      show: false,
      width: PRINT_WINDOW_WIDTH,
      height: 1200,
      paintWhenInitiallyHidden: true,
      webPreferences: {
        sandbox: false,
        backgroundThrottling: false,
      },
    });

    printWin.webContents.setBackgroundThrottling(false);

    let settled = false;
    const finish = (error) => {
      if (settled) return;
      settled = true;
      setTimeout(() => {
        if (!printWin.isDestroyed()) printWin.close();
        removeTempFile(tempPath);
      }, CLEANUP_DELAY_MS);
      if (error) reject(error);
      else resolve();
    };

    const attemptPrint = async (retryStep = 0) => {
      let options;
      if (retryStep === 0) {
        const pageHeightMm = await measureContentHeightMm(printWin);
        options = buildPrintOptions(deviceName, { pageHeightMm, usePrinterDefault: false });
      } else if (retryStep === 1) {
        options = buildPrintOptions(deviceName, { usePrinterDefault: true });
      } else {
        options = buildPrintOptions("", { usePrinterDefault: true });
      }

      try {
        await printWithOptions(printWin.webContents, options);
        finish();
      } catch (err) {
        if (retryStep < 2) {
          await attemptPrint(retryStep + 1);
          return;
        }
        finish(err);
      }
    };

    printWin.webContents.on("did-fail-load", (_event, _code, description) => {
      finish(new Error(description || "Failed to load print preview"));
    });

    printWin.webContents.once("did-finish-load", () => {
      setTimeout(() => {
        attemptPrint(0).catch((err) => finish(err));
      }, PRINT_DELAY_MS);
    });

    printWin.loadFile(tempPath).catch((err) => {
      finish(err);
    });
  });
}

function renderTestPageHtml() {
  return wrapDocument(
    "Printer test",
    `
    <div class="receipt">
      <div class="center brand">
        <h1>Café de Paris</h1>
        <p>Printer test</p>
      </div>
      <div class="center meta">
        <p>${esc(formatDateTime(new Date().toISOString()))}</p>
      </div>
      <hr class="divider">
      ${renderItemsBlock([
        { product_name: "Test item", quantity: 1, price: 10.5 },
      ])}
      ${renderSummaryBlock([
        ["Subtotal (USD)", "9.09"],
        ["Tax (15.5%)", "1.41"],
        ["Total (USD)", "10.50"],
      ])}
      ${renderSummaryBlock([["Amount paid", "USD$10.50"]], { grand: true })}
      <div class="center footer">
        <p>Amounts should line up on the right.</p>
      </div>
    </div>`
  );
}

function formatPaymentLine(payment) {
  const currency = payment.currency;
  const code =
    payment.payment_currency__code ||
    payment.payment_currency__name ||
    currency?.code ||
    currency?.name ||
    "—";
  const label = truncText(code, 10).padEnd(10);
  const amount = money(payment.total_paid);
  const symbol = payment.payment_currency__symbol || currency?.symbol || "";
  const amountText = symbol ? `${symbol}${amount}` : amount;
  const count = `(${payment.order_count || 0})`;
  return padLine(`${label} ${amountText}`, count, LINE_CHARS);
}

function formatExpenseLine(expense) {
  const label = truncText(expense.description || "Expense", 18).padEnd(18);
  const symbol = expense.currency__symbol || "";
  const amount = money(expense.amount);
  const amountText = symbol ? `${symbol}${amount}` : amount;
  return padLine(label, amountText, LINE_CHARS);
}

function formatCashupLine(label, value, symbol = "") {
  const amount = value == null || value === "" ? "—" : money(value);
  const amountText = symbol && value != null && value !== "" ? `${symbol}${amount}` : amount;
  return padLine(label, amountText, LINE_CHARS);
}

function renderProductSummaryBlock(products) {
  if (!products?.length) {
    return `<pre class="lines">No items sold</pre>`;
  }

  const lines = [
    "PRODUCT".padEnd(ITEM_NAME_W) + "QTY".padStart(ITEM_QTY_W) + "AMT".padStart(ITEM_AMT_W),
    "-".repeat(LINE_CHARS),
  ];

  for (const row of products) {
    lines.push(itemColumns(row.product_name, row.quantity, row.revenue));
  }

  return `<pre class="lines">${esc(lines.join("\n"))}</pre>`;
}

function renderDayEndReportHtml(data) {
  const { branch, report, tax, baseCurrency, printedAt } = data;
  const baseLabel = baseCurrency ? ` (${currencyCode(baseCurrency)})` : "";
  const reportDate = report.reportDate || report.report_date || "";
  const orderCount = report.orderCount || report.order_count || 0;
  const orderTypes = report.orderTypes || report.order_types || [];
  const orderTypeRows = orderTypes.map((row) => [
    orderTypeLabel(row.order_type),
    String(row.count),
  ]);

  const paymentLines = (report.payments || []).map((payment) => formatPaymentLine(payment));
  const expenseLines = (report.expenses || []).map((expense) => formatExpenseLine(expense));
  const cashupRows = report.cashup_rows || [];
  const cashupBlocks = cashupRows
    .map((row) => {
      const code =
        row.payment_currency__name ||
        row.payment_currency__code ||
        row.currency?.name ||
        row.currency?.code ||
        "—";
      const symbol = row.payment_currency__symbol || row.currency?.symbol || "";
      const lines = [
        formatCashupLine(`${code} expected`, row.expected_total, symbol),
      ];
      const expensesTotal = row.expenses_total;
      if (expensesTotal && expensesTotal !== "0" && expensesTotal !== "0.00") {
        lines.push(formatCashupLine("Less expenses", expensesTotal, symbol));
        lines.push(formatCashupLine("Net expected", row.net_expected_total, symbol));
      }
      lines.push(formatCashupLine("Counted", row.counted_total, symbol));
      lines.push(formatCashupLine("Variance", row.variance, symbol));
      return lines.join("\n");
    })
    .join("\n");

  return wrapDocument(
    `Day end ${reportDate}`,
    `
    <div class="receipt">
      ${renderBrandHeader(branch)}
      <div class="center meta">
        <p><strong>Day End Report</strong></p>
        <p>${esc(formatReportDate(reportDate))}</p>
        <p>Printed ${esc(formatDateTime(printedAt))}</p>
      </div>
      <hr class="divider">
      ${renderSummaryBlock(
        [
          ["Orders", String(orderCount)],
          ...(orderTypeRows.length ? orderTypeRows : []),
        ],
        { boxed: true }
      )}
      <hr class="divider">
      <div class="center meta"><p><strong>Sales${esc(baseLabel)}</strong></p></div>
      ${
        orderCount
          ? renderSummaryBlock([
              [`Subtotal${baseLabel}`, money(tax?.subtotal)],
              [`Tax (${formatTaxRate(tax?.taxRate)}%)`, money(tax?.tax)],
              [`Total${baseLabel}`, money(tax?.total)],
            ])
          : `<pre class="lines">No sales recorded</pre>`
      }
      ${
        paymentLines.length
          ? `
      <hr class="divider">
      <div class="center meta"><p><strong>Payments collected</strong></p></div>
      <pre class="lines">${esc(paymentLines.join("\n"))}</pre>`
          : ""
      }
      ${
        expenseLines.length
          ? `
      <hr class="divider">
      <div class="center meta"><p><strong>Expenses</strong></p></div>
      <pre class="lines">${esc(expenseLines.join("\n"))}</pre>`
          : ""
      }
      ${
        cashupBlocks
          ? `
      <hr class="divider">
      <div class="center meta"><p><strong>Cash-up reconciliation</strong></p></div>
      <pre class="lines">${esc(cashupBlocks)}</pre>
      ${
        report.has_counted_entries
          ? `<pre class="lines">${esc(
              padLine(
                "Total variance",
                money(report.variance_total || "0"),
                LINE_CHARS
              )
            )}</pre>`
          : ""
      }`
          : ""
      }
      <hr class="divider">
      <div class="center meta"><p><strong>Items sold</strong></p></div>
      ${renderProductSummaryBlock(report.products)}
      <div class="center footer">
        <p>End of day summary</p>
      </div>
    </div>`
  );
}

async function printDocument(payload, { deviceName } = {}) {
  const html =
    payload.type === "order"
      ? renderOrderSlipHtml(payload)
      : payload.type === "test"
        ? renderTestPageHtml()
        : payload.type === "dayend"
          ? renderDayEndReportHtml(payload)
          : renderReceiptHtml(payload);
  await printHtml(html, { deviceName });
}

module.exports = { printDocument };
