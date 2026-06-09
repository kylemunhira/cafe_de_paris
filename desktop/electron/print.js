const { BrowserWindow } = require("electron");

const RECEIPT_STYLES = `
  @page { size: 80mm auto; margin: 4mm; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: "Segoe UI", system-ui, sans-serif;
    color: #2c1810;
    background: #fff;
    font-size: 10pt;
    line-height: 1.4;
  }
  .receipt {
    width: 72mm;
    max-width: 100%;
    margin: 0 auto;
    padding: 4mm 3mm;
  }
  .center { text-align: center; }
  .brand { margin-bottom: 0.75rem; }
  .brand h1 { margin: 0; font-size: 1.15rem; }
  .brand p { margin: 0.2rem 0 0; color: #6b5c52; font-size: 0.75rem; }
  .meta { font-size: 0.78rem; color: #6b5c52; margin-bottom: 0.75rem; }
  .meta p { margin: 0.15rem 0; }
  .badge {
    display: inline-block;
    margin: 0.35rem 0;
    padding: 0.2rem 0.55rem;
    border: 1px solid #2c1810;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
  }
  .divider { border: none; border-top: 1px dashed #c4a77d; margin: 0.65rem 0; }
  .items { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  .items th {
    text-align: left;
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #6b5c52;
    padding-bottom: 0.35rem;
    border-bottom: 1px solid #e8dfd4;
  }
  .items th.qty, .items th.amt { text-align: right; }
  .items td { padding: 0.35rem 0; vertical-align: top; }
  .items td.qty, .items td.amt { text-align: right; white-space: nowrap; }
  .item-name { font-weight: 600; }
  .item-detail { font-size: 0.72rem; color: #6b5c52; }
  .totals { font-size: 0.82rem; }
  .total-row {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    margin: 0.2rem 0;
  }
  .total-row.grand {
    margin-top: 0.45rem;
    padding-top: 0.45rem;
    border-top: 1px solid #2c1810;
    font-size: 0.95rem;
    font-weight: 700;
  }
  .payment-box {
    margin-top: 0.5rem;
    padding: 0.45rem 0.5rem;
    background: #faf6f1;
    border-radius: 4px;
    font-size: 0.78rem;
  }
  .footer { margin-top: 0.85rem; font-size: 0.75rem; color: #6b5c52; }
`;

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function money(amount, symbol = "") {
  const value = Number(amount);
  const formatted = Number.isFinite(value)
    ? value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : "0.00";
  return symbol ? `${symbol}${formatted}` : formatted;
}

function formatDateTime(iso) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}

function orderTypeLabel(value) {
  return value === "dine_in" ? "Dine in" : "Takeaway";
}

function renderItemsRows(items) {
  if (!items?.length) {
    return `<tr><td colspan="3">No items</td></tr>`;
  }
  return items
    .map((item) => {
      const qty = Number(item.quantity);
      const price = Number(item.price);
      const line = qty * price;
      const name = esc(item.product_name || item.name || "Item");
      return `
        <tr>
          <td>
            <div class="item-name">${name}</div>
            <div class="item-detail">${money(price)} each</div>
          </td>
          <td class="qty">${qty}</td>
          <td class="amt">${money(line)}</td>
        </tr>`;
    })
    .join("");
}

function wrapDocument(title, body) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>${esc(title)}</title>
  <style>${RECEIPT_STYLES}</style>
</head>
<body>${body}</body>
</html>`;
}

function renderOrderSlipHtml(data) {
  const { branch, order, cashier } = data;
  const ref = order.receipt_number || order.client_id?.slice(0, 8).toUpperCase() || "—";
  const tableLine = order.table_number
    ? `<p>Table ${esc(order.table_number)}</p>`
    : "";

  return wrapDocument(
    `Order ${ref}`,
    `
    <div class="receipt">
      <div class="center brand">
        <h1>Café de Paris</h1>
        ${branch?.name ? `<p>${esc(branch.name)}</p>` : ""}
        ${branch?.location ? `<p>${esc(branch.location)}</p>` : ""}
      </div>
      <div class="center meta">
        <p><strong>Order ticket</strong></p>
        <span class="badge">UNPAID</span>
        <p>Ref ${esc(ref)}</p>
        <p>${esc(formatDateTime(order.created_at))}</p>
        <p>${esc(orderTypeLabel(order.order_type))}</p>
        ${tableLine}
        ${cashier?.display_name ? `<p>Cashier: ${esc(cashier.display_name)}</p>` : ""}
      </div>
      <hr class="divider">
      <table class="items">
        <thead>
          <tr><th>Item</th><th class="qty">Qty</th><th class="amt">Amount</th></tr>
        </thead>
        <tbody>${renderItemsRows(order.items)}</tbody>
      </table>
      <hr class="divider">
      <div class="totals">
        <div class="total-row grand">
          <span>Total due</span>
          <span>${money(order.total_amount)}</span>
        </div>
      </div>
      <div class="center footer">
        <p>Present this ticket when paying.</p>
      </div>
    </div>`
  );
}

function renderReceiptHtml(data) {
  const { branch, order, tax, payment, baseCurrency } = data;
  const ref = order.receipt_number || order.client_id?.slice(0, 8).toUpperCase() || "—";
  const serverLine = order.server_id ? `<p>Order #${esc(order.server_id)}</p>` : "";
  const tableLine = order.table_number
    ? `<p>${esc(orderTypeLabel(order.order_type))} · Table ${esc(order.table_number)}</p>`
    : `<p>${esc(orderTypeLabel(order.order_type))}</p>`;

  const paymentBlock = payment
    ? `
      <div class="payment-box">
        <div class="total-row">
          <span>Paid in</span>
          <strong>${esc(payment.currencyName)}</strong>
        </div>
        ${
          payment.exchangeRate && !payment.isBase
            ? `<div class="total-row"><span>Exchange rate</span><span>${esc(payment.exchangeRate)}</span></div>`
            : ""
        }
      </div>
      <div class="total-row grand">
        <span>Amount paid</span>
        <span>${money(payment.amountPaid, payment.symbol || "")}</span>
      </div>`
    : "";

  return wrapDocument(
    `Receipt ${ref}`,
    `
    <div class="receipt">
      <div class="center brand">
        <h1>Café de Paris</h1>
        ${branch?.location ? `<p>${esc(branch.location)}</p>` : ""}
      </div>
      <div class="center meta">
        <p><strong>Sales receipt</strong></p>
        <p>Receipt #${esc(ref)}</p>
        ${serverLine}
        <p>${esc(formatDateTime(order.paid_at || order.created_at))}</p>
        ${tableLine}
      </div>
      <hr class="divider">
      <table class="items">
        <thead>
          <tr><th>Item</th><th class="qty">Qty</th><th class="amt">Amount</th></tr>
        </thead>
        <tbody>${renderItemsRows(order.items)}</tbody>
      </table>
      <hr class="divider">
      <div class="totals">
        <div class="total-row">
          <span>Subtotal${baseCurrency?.name ? ` (${esc(baseCurrency.name)})` : ""}</span>
          <span>${money(tax?.subtotal)}</span>
        </div>
        <div class="total-row">
          <span>Tax (${esc(tax?.taxRate ?? "0")}%)</span>
          <span>${money(tax?.tax)}</span>
        </div>
        <div class="total-row">
          <span>Total${baseCurrency?.name ? ` (${esc(baseCurrency.name)})` : ""}</span>
          <span>${money(tax?.total)}</span>
        </div>
        ${paymentBlock}
      </div>
      <div class="center footer">
        <p>Thank you for your visit!</p>
        <p><strong>PAID</strong></p>
      </div>
    </div>`
  );
}

function printHtml(html) {
  return new Promise((resolve, reject) => {
    const printWin = new BrowserWindow({
      show: false,
      webPreferences: { sandbox: true },
    });

    const cleanup = () => {
      if (!printWin.isDestroyed()) printWin.close();
    };

    printWin.webContents.on("did-fail-load", (_event, _code, description) => {
      cleanup();
      reject(new Error(description || "Failed to load print preview"));
    });

    printWin.webContents.once("did-finish-load", () => {
      // Brief delay so layout is ready; silent prints to the system default printer.
      setTimeout(() => {
        printWin.webContents.print(
          {
            silent: true,
            printBackground: true,
            margins: { marginType: "none" },
          },
          (success, failureReason) => {
            cleanup();
            if (success) resolve();
            else reject(new Error(failureReason || "Print failed"));
          }
        );
      }, 200);
    });

    printWin
      .loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`)
      .catch((err) => {
        cleanup();
        reject(err);
      });
  });
}

async function printDocument(payload) {
  const html =
    payload.type === "order"
      ? renderOrderSlipHtml(payload)
      : renderReceiptHtml(payload);
  await printHtml(html);
}

module.exports = { printDocument };
