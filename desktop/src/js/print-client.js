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

export async function printOrderSlip(session, order) {
  await window.pos.print({
    type: "order",
    branch: session.branch,
    cashier: session.user,
    order,
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
    baseCurrency: baseCurrency ? { name: baseCurrency.name } : null,
    payment: currency
      ? {
          currencyName: currency.name,
          symbol: currency.symbol,
          exchangeRate: order.exchange_rate,
          amountPaid: order.amount_paid,
          isBase: currency.is_base,
        }
      : null,
  });
}
