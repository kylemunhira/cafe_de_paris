function roundMoney(amount) {
  return Math.round(Number(amount) * 100) / 100;
}

export function computeTaxBreakdown(inclusiveTotal, taxRate) {
  const total = roundMoney(inclusiveTotal);
  const divisor = 1 + Number(taxRate) / 100;
  const subtotal = roundMoney(total / divisor);
  const tax = roundMoney(total - subtotal);
  return { subtotal, tax, total, taxRate };
}

export function orderSalespersonName(order, session) {
  return (
    order.paid_by_name ||
    order.created_by_name ||
    session?.user?.display_name ||
    session?.user?.username ||
    ""
  );
}

export async function printOrderSlip(session, order, { taxRate }) {
  const inclusiveTotal = order.items?.length
    ? order.items.reduce(
        (sum, item) => sum + roundMoney(Number(item.price) * Number(item.quantity)),
        0
      )
    : roundMoney(order.total_amount);

  const tax = computeTaxBreakdown(inclusiveTotal, taxRate);
  const baseCurrency =
    (await window.pos.getCatalog()).currencies.find((c) => c.is_base) || null;

  await window.pos.print({
    type: "order",
    branch: session.branch,
    order,
    tax,
    salesperson: order.created_by_name || session?.user?.display_name || session?.user?.username || "",
    baseCurrency: baseCurrency
      ? { name: baseCurrency.name, code: baseCurrency.code }
      : null,
  });
}

export async function printDayEndReport(session, report, { taxRate }) {
  const grossTotal = roundMoney(report.grossTotal || 0);
  const tax = computeTaxBreakdown(grossTotal, taxRate);
  const baseCurrency =
    (await window.pos.getCatalog()).currencies.find((c) => c.is_base) || null;

  await window.pos.print({
    type: "dayend",
    branch: session.branch,
    report,
    tax,
    baseCurrency: baseCurrency
      ? { name: baseCurrency.name, code: baseCurrency.code }
      : null,
    printedAt: new Date().toISOString(),
  });
}

export async function printSalesReceipt(session, order, { currency, taxRate }) {
  const inclusiveTotal = order.items?.length
    ? order.items.reduce(
        (sum, item) => sum + roundMoney(Number(item.price) * Number(item.quantity)),
        0
      )
    : roundMoney(order.total_amount);

  const tax = computeTaxBreakdown(inclusiveTotal, taxRate);
  const baseCurrency =
    (await window.pos.getCatalog()).currencies.find((c) => c.is_base) || null;

  await window.pos.print({
    type: "receipt",
    branch: session.branch,
    order,
    tax,
    salesperson: orderSalespersonName(order, session),
    baseCurrency: baseCurrency
      ? { name: baseCurrency.name, code: baseCurrency.code }
      : null,
    payment: currency
      ? {
          currencyName: currency.name,
          currencyCode: currency.code,
          symbol: currency.symbol,
          exchangeRate: order.exchange_rate,
          amountPaid: order.amount_paid,
          isBase: currency.is_base,
        }
      : null,
  });
}
