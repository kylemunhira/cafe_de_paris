import { formatCurrency, formatDate, kitchenStatusBadge, showToast } from "./api.js";
import { printDayEndReport, printOrderSlip, printSalesReceipt } from "./print-client.js";
import { isBrowserOnline, runFullSync, runFullSyncIfOnline, startAutoSync, startKitchenRefresh } from "./sync.js";

const cart = new Map();
let session = null;
let products = [];
let categories = [];
let currencies = [];
let baseCurrency = null;
let activeCategory = "all";
let posMode = "order";
let openOrders = [];
let selectedOrder = null;
let selectedCurrencyId = null;
let inclusiveTaxRate = 15.5;
let stopAutoSync = null;
let stopKitchenRefresh = null;

const branchLabel = document.getElementById("branch-label");
const syncStatus = document.getElementById("sync-status");
const syncBtn = document.getElementById("sync-btn");
const logoutBtn = document.getElementById("logout-btn");
const dayendBtn = document.getElementById("dayend-btn");
const categoryTabs = document.getElementById("category-tabs");
const productGrid = document.getElementById("product-grid");
const cartItems = document.getElementById("cart-items");
const cartTotal = document.getElementById("cart-total");
const checkoutBtn = document.getElementById("checkout-btn");
const clearBtn = document.getElementById("clear-btn");
const panelTitle = document.getElementById("panel-title");
const orderType = document.getElementById("order-type");
const tableGroup = document.getElementById("table-group");
const tableNumber = document.getElementById("table-number");
const orderModePanel = document.getElementById("order-mode-panel");
const receiptModePanel = document.getElementById("receipt-mode-panel");
const receiptOrdersList = document.getElementById("receipt-orders-list");
const receiptPaymentSection = document.getElementById("receipt-payment-section");
const paymentCurrencySelect = document.getElementById("payment-currency");
const receiptTotals = document.getElementById("receipt-totals");
const cartTotalLabel = document.getElementById("cart-total-label");

orderType.addEventListener("change", () => {
  tableGroup.style.display = orderType.value === "dine_in" ? "block" : "none";
});

document.querySelectorAll(".pos-mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const mode = btn.dataset.mode;
    if (mode === posMode) return;
    setPosMode(mode);
  });
});

function setPosMode(mode) {
  posMode = mode;
  document.querySelectorAll(".pos-mode-btn").forEach((btn) => {
    const active = btn.dataset.mode === mode;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  orderModePanel.style.display = mode === "order" ? "" : "none";
  receiptModePanel.style.display = mode === "receipt" ? "" : "none";
  if (mode === "receipt") {
    selectedOrder = null;
    loadOpenOrders();
    renderReceiptPanel();
    startReceiptKitchenRefresh();
  } else {
    stopReceiptKitchenRefresh();
    receiptPaymentSection.style.display = "none";
    cartTotalLabel.textContent = "Total";
    renderCart();
  }
}

function stopReceiptKitchenRefresh() {
  if (stopKitchenRefresh) {
    stopKitchenRefresh();
    stopKitchenRefresh = null;
  }
}

function startReceiptKitchenRefresh() {
  stopReceiptKitchenRefresh();
  if (!session) return;

  stopKitchenRefresh = startKitchenRefresh(session, {
    onRefresh: async () => {
      if (posMode !== "receipt") return;
      const previousStatuses = new Map(
        openOrders.map((order) => [order.client_id, order.kitchen_status || "pending"])
      );
      await loadOpenOrders();
      for (const order of openOrders) {
        const previous = previousStatuses.get(order.client_id);
        if (previous === "preparing" && order.kitchen_status === "ready") {
          const label = order.receipt_number || order.client_id.slice(0, 8);
          showToast(`Order ${label} is ready for pickup`);
        }
      }
    },
  });
}

function roundMoney(amount) {
  return Math.round(Number(amount) * 100) / 100;
}

function getCartTotal() {
  let total = 0;
  for (const [, item] of cart) total += item.price * item.quantity;
  return total;
}

function computeTaxBreakdown(inclusiveTotal) {
  const total = roundMoney(inclusiveTotal);
  const divisor = 1 + inclusiveTaxRate / 100;
  const subtotal = roundMoney(total / divisor);
  const tax = roundMoney(total - subtotal);
  return { subtotal, tax, total };
}

function getOrderInclusiveTotal(order) {
  if (!order) return 0;
  if (order.items?.length) {
    return order.items.reduce(
      (sum, item) => sum + roundMoney(Number(item.price) * Number(item.quantity)),
      0
    );
  }
  return roundMoney(order.total_amount);
}

function getSelectedCurrency() {
  return currencies.find((c) => c.id === selectedCurrencyId) || null;
}

function computePaymentAmounts(inclusiveTotal) {
  const currency = getSelectedCurrency();
  if (!currency) return { hasRate: false, amountDue: null, currency: null, rate: null };
  const rate = currency.is_base ? 1 : Number(currency.current_rate);
  const hasRate = currency.is_base || (Number.isFinite(rate) && rate > 0);
  const amountDue = hasRate ? roundMoney(inclusiveTotal * rate) : null;
  return { hasRate, amountDue, currency, rate };
}

function money(amount, currency = baseCurrency) {
  return formatCurrency(amount, currency?.symbol || "$");
}

function renderPaymentCurrencySelect() {
  if (!currencies.length) {
    paymentCurrencySelect.innerHTML = `<option value="">No currencies</option>`;
    selectedCurrencyId = null;
    return;
  }
  if (!selectedCurrencyId || !currencies.some((c) => c.id === selectedCurrencyId)) {
    selectedCurrencyId = currencies[0].id;
  }
  paymentCurrencySelect.innerHTML = currencies
    .map((c) => {
      const rateLabel = c.is_base
        ? " (base)"
        : c.current_rate
          ? ` (rate ${c.current_rate})`
          : " (no rate)";
      return `<option value="${c.id}"${c.id === selectedCurrencyId ? " selected" : ""}>${c.name}${rateLabel}</option>`;
    })
    .join("");
}

function renderReceiptTotals(inclusiveTotal) {
  const { subtotal, tax, total } = computeTaxBreakdown(inclusiveTotal);
  const { rate, amountDue, currency, hasRate } = computePaymentAmounts(total);
  receiptTotals.innerHTML = `
    <div class="receipt-total-row"><span>Subtotal</span><span>${money(subtotal)}</span></div>
    <div class="receipt-total-row"><span>Tax (${inclusiveTaxRate}%)</span><span>${money(tax)}</span></div>
    <div class="receipt-total-row"><span>Total</span><span>${money(total)}</span></div>
    ${currency && !currency.is_base && hasRate ? `<div class="receipt-total-row"><span>Rate</span><span>${rate}</span></div>` : ""}
    <div class="receipt-total-row receipt-total-due"><span>Amount due</span><span>${hasRate ? money(amountDue, currency) : "—"}</span></div>
  `;
  cartTotal.textContent = hasRate ? money(amountDue, currency) : money(total);
  cartTotalLabel.textContent = hasRate && currency && !currency.is_base ? "Amount due" : "Total";
}

function renderCart() {
  panelTitle.textContent = "Current Order";
  checkoutBtn.textContent = "Place Order";
  clearBtn.style.display = "";
  receiptPaymentSection.style.display = "none";
  cartTotalLabel.textContent = "Total";

  if (cart.size === 0) {
    cartItems.innerHTML = `<div class="empty-state"><p>Tap products to add items</p></div>`;
    cartTotal.textContent = money(0);
    checkoutBtn.disabled = true;
    clearBtn.disabled = true;
    return;
  }

  cartItems.innerHTML = [...cart.values()]
    .map(
      (item) => `
    <div class="cart-item" data-id="${item.id}">
      <div class="info">
        <div class="name">${item.name}</div>
        <div class="line-total">${money(item.price)} each</div>
      </div>
      <div class="qty-control">
        <button class="qty-btn" data-action="dec" data-id="${item.id}">−</button>
        <span>${item.quantity}</span>
        <button class="qty-btn" data-action="inc" data-id="${item.id}">+</button>
      </div>
    </div>`
    )
    .join("");

  cartTotal.textContent = money(getCartTotal());
  checkoutBtn.disabled = false;
  clearBtn.disabled = false;
}

function renderReceiptPanel() {
  panelTitle.textContent = selectedOrder ? `Order` : "Receipt";
  clearBtn.style.display = "none";

  if (!selectedOrder) {
    cartItems.innerHTML = `<div class="empty-state"><p>Select an open order</p></div>`;
    cartTotal.textContent = money(0);
    receiptPaymentSection.style.display = "none";
    checkoutBtn.textContent = "Collect Payment";
    checkoutBtn.disabled = true;
    return;
  }

  const typeLabel = selectedOrder.order_type.replace("_", " ");
  cartItems.innerHTML = `
    <div class="receipt-order-meta">
      <div class="receipt-meta" style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem;">
        <span>Kitchen</span>
        ${kitchenStatusBadge(selectedOrder.kitchen_status || "pending")}
      </div>
      <div class="receipt-meta">${typeLabel}</div>
      ${selectedOrder.table_number ? `<div class="receipt-meta">Table ${selectedOrder.table_number}</div>` : ""}
      <div class="receipt-meta">${formatDate(selectedOrder.created_at)}</div>
    </div>
    ${selectedOrder.items
      .map(
        (item) => `
      <div class="cart-item">
        <div class="info">
          <div class="name">${item.product_name}</div>
          <div class="line-total">${money(item.price)} × ${item.quantity}</div>
        </div>
        <div class="line-total">${money(item.price * item.quantity)}</div>
      </div>`
      )
      .join("")}
  `;

  renderPaymentCurrencySelect();
  receiptPaymentSection.style.display = "";
  const inclusiveTotal = getOrderInclusiveTotal(selectedOrder);
  renderReceiptTotals(inclusiveTotal);
  checkoutBtn.textContent = "Collect Payment";
  const { hasRate } = computePaymentAmounts(inclusiveTotal);
  checkoutBtn.disabled = !selectedCurrencyId || !hasRate;
}

function renderOpenOrdersList() {
  if (!openOrders.length) {
    receiptOrdersList.innerHTML = `<div class="empty-state"><p>No open orders</p></div>`;
    return;
  }

  receiptOrdersList.innerHTML = openOrders
    .map((o) => {
      const selected = selectedOrder?.client_id === o.client_id ? " selected" : "";
      const readyClass = o.kitchen_status === "ready" ? " receipt-order-ready" : "";
      return `
      <button type="button" class="receipt-order-card${selected}${readyClass}" data-id="${o.client_id}">
        <div class="receipt-order-card-top">
          <strong>${o.receipt_number || o.client_id.slice(0, 8)}</strong>
          <span class="receipt-order-amount">${money(o.total_amount)}</span>
        </div>
        <div class="receipt-order-card-meta">${o.order_type.replace("_", " ")} · ${o.items.length} items</div>
        <div class="receipt-order-card-meta" style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem;">
          <span>${formatDate(o.created_at)}</span>
          ${kitchenStatusBadge(o.kitchen_status || "pending")}
        </div>
      </button>`;
    })
    .join("");
}

async function loadOpenOrders() {
  openOrders = await window.pos.listOpenOrders();
  if (selectedOrder && !openOrders.some((o) => o.client_id === selectedOrder.client_id)) {
    selectedOrder = null;
  }
  renderOpenOrdersList();
  if (posMode === "receipt") renderReceiptPanel();
}

function renderCategories() {
  const tabs = [{ id: "all", name: "All" }, ...categories];
  categoryTabs.innerHTML = tabs
    .map(
      (cat) =>
        `<button class="category-tab${activeCategory === String(cat.id) ? " active" : ""}" data-id="${cat.id}">${cat.name}</button>`
    )
    .join("");
}

function renderProducts() {
  const filtered =
    activeCategory === "all"
      ? products
      : products.filter((p) => p.category === Number(activeCategory));

  if (!filtered.length) {
    productGrid.innerHTML = `<div class="empty-state wide"><p>No products in this category</p></div>`;
    return;
  }

  productGrid.innerHTML = filtered
    .map(
      (p) => `
    <div class="card product-card" data-id="${p.id}">
      <div class="name">${p.name}</div>
      <div class="price">${money(p.selling_price)}</div>
    </div>`
    )
    .join("");
}

async function updateSyncBadge() {
  const pending = await window.pos.pendingSyncCount();
  const catalogAt = (await window.pos.getCatalog()).catalogSyncedAt;
  const online = isBrowserOnline();

  if (!online) {
    syncStatus.textContent =
      pending > 0
        ? `Offline · ${pending} order(s) queued`
        : "Offline — will sync when connected";
    syncStatus.classList.add("warn");
    return;
  }

  if (pending > 0) {
    syncStatus.textContent = `Online · ${pending} order(s) waiting to sync`;
    syncStatus.classList.add("warn");
    return;
  }

  syncStatus.textContent = catalogAt
    ? `Online · synced ${formatDate(catalogAt)}`
    : "Online · syncing…";
  syncStatus.classList.remove("warn");
}

cartItems.addEventListener("click", (e) => {
  if (posMode !== "order") return;
  const btn = e.target.closest(".qty-btn");
  if (!btn) return;
  const id = Number(btn.dataset.id);
  const item = cart.get(id);
  if (!item) return;
  item.quantity += btn.dataset.action === "inc" ? 1 : -1;
  if (item.quantity <= 0) cart.delete(id);
  renderCart();
});

categoryTabs.addEventListener("click", (e) => {
  const tab = e.target.closest(".category-tab");
  if (!tab) return;
  activeCategory = tab.dataset.id;
  renderCategories();
  renderProducts();
});

productGrid.addEventListener("click", (e) => {
  const card = e.target.closest(".product-card");
  if (!card) return;
  const product = products.find((p) => p.id === Number(card.dataset.id));
  if (!product) return;
  const existing = cart.get(product.id);
  if (existing) existing.quantity += 1;
  else {
    cart.set(product.id, {
      id: product.id,
      name: product.name,
      price: Number(product.selling_price),
      quantity: 1,
    });
  }
  renderCart();
});

receiptOrdersList.addEventListener("click", (e) => {
  const card = e.target.closest(".receipt-order-card");
  if (!card) return;
  selectedOrder = openOrders.find((o) => o.client_id === card.dataset.id) || null;
  renderOpenOrdersList();
  renderReceiptPanel();
});

clearBtn.addEventListener("click", () => {
  cart.clear();
  renderCart();
});

paymentCurrencySelect.addEventListener("change", () => {
  selectedCurrencyId = Number(paymentCurrencySelect.value) || null;
  if (selectedOrder) {
    renderReceiptTotals(getOrderInclusiveTotal(selectedOrder));
    const { hasRate } = computePaymentAmounts(getOrderInclusiveTotal(selectedOrder));
    checkoutBtn.disabled = !selectedCurrencyId || !hasRate;
  }
});

checkoutBtn.addEventListener("click", async () => {
  if (posMode === "receipt") await paySelectedOrder();
  else await placeOrder();
});

syncBtn.addEventListener("click", async () => {
  syncBtn.disabled = true;
  const result = await runFullSyncIfOnline(session, { silent: false });
  if (!result.synced && result.reason === "offline") {
    showToast("No internet connection.", true);
  } else if (!result.synced && result.reason === "server_unreachable") {
    showToast("Cannot reach server. Check config.json and that the server is running.", true);
  } else if (result.synced) {
    await loadCatalog();
  }
  await updateSyncBadge();
  syncBtn.disabled = false;
});

dayendBtn.addEventListener("click", async () => {
  dayendBtn.disabled = true;
  try {
    const report = await window.pos.getDayEndReport();
    await printDayEndReport(session, report, { taxRate: inclusiveTaxRate });
    const label = report.orderCount === 1 ? "1 order" : `${report.orderCount} orders`;
    showToast(`Day end report printed · ${label}`);
  } catch (err) {
    showToast(`Day end report failed: ${err.message}`, true);
  } finally {
    dayendBtn.disabled = false;
  }
});

logoutBtn.addEventListener("click", async () => {
  if (stopAutoSync) stopAutoSync();
  stopReceiptKitchenRefresh();
  window.removeEventListener("offline", updateSyncBadge);
  await window.pos.clearSession();
  window.location.href = "login.html";
});

async function placeOrder() {
  if (cart.size === 0) return;
  checkoutBtn.disabled = true;
  try {
    const order = await window.pos.createOrder({
      orderType: orderType.value,
      tableNumber: orderType.value === "dine_in" ? tableNumber.value.trim() : "",
      createdByName: session.user?.display_name || session.user?.username || "",
      items: [...cart.values()].map((item) => ({
        product_id: item.id,
        product_name: item.name,
        quantity: item.quantity,
        price: item.price,
      })),
    });
    cart.clear();
    renderCart();
    await updateSyncBadge();
    showToast(`Order placed — ${money(order.total_amount)}`);
    try {
      await printOrderSlip(session, order, { taxRate: inclusiveTaxRate });
    } catch (printErr) {
      showToast(`Order saved but print failed: ${printErr.message}`, true);
    }
    runFullSyncIfOnline(session, { silent: true }).then(async (result) => {
      if (result.synced) {
        await loadCatalog();
        await updateSyncBadge();
      }
    });
  } catch (err) {
    showToast(err.message, true);
  } finally {
    checkoutBtn.disabled = cart.size === 0;
  }
}

async function paySelectedOrder() {
  if (!selectedOrder || !selectedCurrencyId) return;
  const inclusiveTotal = getOrderInclusiveTotal(selectedOrder);
  const { hasRate, currency, amountDue, rate } = computePaymentAmounts(inclusiveTotal);
  if (!hasRate) {
    showToast(`No exchange rate for ${currency?.name || "currency"}`, true);
    return;
  }

  checkoutBtn.disabled = true;
  try {
    const localReceipt = `LOC-${session.branch.code || "POS"}-${Date.now().toString(36).toUpperCase()}`;
    const order = await window.pos.payOrder(selectedOrder.client_id, {
      currencyId: selectedCurrencyId,
      exchangeRate: rate,
      amountPaid: amountDue,
      receiptNumber: localReceipt,
      paidByName: session.user?.display_name || session.user?.username || "",
    });
    showToast(`Paid ${money(order.amount_paid, currency)} · ${localReceipt}`);
    try {
      await printSalesReceipt(session, order, {
        currency,
        taxRate: inclusiveTaxRate,
      });
    } catch (printErr) {
      showToast(`Payment saved but print failed: ${printErr.message}`, true);
    }
    selectedOrder = null;
    await loadOpenOrders();
    await updateSyncBadge();
    runFullSyncIfOnline(session, { silent: true }).then(async (result) => {
      if (result.synced) {
        await loadCatalog();
        await updateSyncBadge();
      }
    });
  } catch (err) {
    showToast(err.message, true);
  } finally {
    checkoutBtn.disabled = !selectedOrder;
  }
}

async function loadCatalog() {
  const data = await window.pos.getCatalog();
  products = data.products;
  categories = data.categories;
  currencies = data.currencies;
  baseCurrency = currencies.find((c) => c.is_base) || currencies[0] || null;
  const storedRate = await window.pos.getSetting("inclusive_tax_rate");
  if (storedRate) inclusiveTaxRate = Number(storedRate);
  renderCategories();
  renderProducts();
}

async function init() {
  session = await window.pos.getSession();
  if (!session?.token) {
    window.location.href = "login.html";
    return;
  }

  branchLabel.textContent = session.branch?.name || "Branch";
  inclusiveTaxRate = Number(session.inclusiveTaxRate || inclusiveTaxRate);

  await loadCatalog();
  renderCart();
  await updateSyncBadge();
  window.addEventListener("offline", updateSyncBadge);
  stopAutoSync = startAutoSync(session, {
    onSyncComplete: async () => {
      await loadCatalog();
      await updateSyncBadge();
    },
  });
}

init().catch((err) => showToast(`Failed to start POS: ${err.message}`, true));
