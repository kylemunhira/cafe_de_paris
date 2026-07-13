function roundMoney(amount) {
  return Math.round(Number(amount) * 100) / 100;
}

function buildPaymentOptions(baseAmount, currencies) {
  return (currencies || [])
    .filter((c) => c.is_active !== false)
    .map((c) => {
      const rate = c.is_base ? 1 : Number(c.current_rate);
      if (!Number.isFinite(rate) || rate <= 0) return null;
      return {
        name: c.name || "",
        code: c.code || "",
        symbol: c.symbol || "",
        amount: roundMoney(Number(baseAmount) * rate),
        isBase: !!c.is_base,
      };
    })
    .filter(Boolean);
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
  const catalogCurrencies = (await window.pos.getCatalog()).currencies || [];
  const baseCurrency = catalogCurrencies.find((c) => c.is_base) || null;

  await window.pos.print({
    type: "order",
    branch: session.branch,
    order,
    tax,
    salesperson: order.created_by_name || session?.user?.display_name || session?.user?.username || "",
    baseCurrency: baseCurrency
      ? { name: baseCurrency.name, code: baseCurrency.code }
      : null,
    paymentOptions: buildPaymentOptions(tax.total, catalogCurrencies),
  });
}

export async function printDayEndReport(session, report, { taxRate }) {
  const grossTotal = roundMoney(report.gross_total || report.grossTotal || 0);
  const tax = report.tax_breakdown
    ? {
        subtotal: roundMoney(report.tax_breakdown.subtotal),
        tax: roundMoney(report.tax_breakdown.tax),
        total: roundMoney(report.tax_breakdown.total),
        taxRate: Number(report.tax_breakdown.tax_rate || taxRate),
      }
    : computeTaxBreakdown(grossTotal, taxRate);
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

export async function printSalesReceipt(session, order, { currency, taxRate, payments = null }) {
  const inclusiveTotal = order.items?.length
    ? order.items.reduce(
        (sum, item) => sum + roundMoney(Number(item.price) * Number(item.quantity)),
        0
      )
    : roundMoney(order.total_amount);

  const tax = computeTaxBreakdown(inclusiveTotal, taxRate);
  const catalogCurrencies = (await window.pos.getCatalog()).currencies || [];
  const baseCurrency = catalogCurrencies.find((c) => c.is_base) || null;
  const tenderLines = Array.isArray(payments)
    ? payments
    : Array.isArray(order.payments)
      ? order.payments
      : [];
  const enrichedLines = tenderLines.map((line) => {
    const lineCurrency =
      catalogCurrencies.find((c) => c.id === Number(line.currency_id)) ||
      (line.currency_id == null ? currency : null);
    return {
      ...line,
      currencyName: lineCurrency?.name || line.currencyName,
      currencyCode: lineCurrency?.code || line.currencyCode,
      symbol: lineCurrency?.symbol || line.symbol,
    };
  });

  await window.pos.print({
    type: "receipt",
    branch: session.branch,
    order,
    tax,
    salesperson: orderSalespersonName(order, session),
    baseCurrency: baseCurrency
      ? { name: baseCurrency.name, code: baseCurrency.code }
      : null,
    paymentOptions: buildPaymentOptions(tax.total, catalogCurrencies),
    payment: currency
      ? {
          currencyName: currency.name,
          currencyCode: currency.code,
          symbol: currency.symbol,
          exchangeRate: order.exchange_rate,
          amountPaid: order.amount_paid,
          changeGiven: order.change_given ?? order.changeGiven ?? null,
          isBase: currency.is_base,
          lines: enrichedLines,
        }
      : null,
  });
}
