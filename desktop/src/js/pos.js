import {
  closeFiscalDay,
  createDiningTable,
  fetchDiningTables,
  fetchFiscalDayStatus,
  fetchStockTakeDayEndCheck,
  formatCurrency,
  formatDate,
  kitchenStatusBadge,
  openFiscalDay,
  showToast,
  updateDiningTable,
} from "./api.js";
import { printDayEndReport, printOrderSlip, printSalesReceipt } from "./print-client.js";
import { isBrowserOnline, runFullSync, runFullSyncIfOnline, startAutoSync, startKitchenRefresh } from "./sync.js";

const cart = new Map();
let session = null;
let products = [];
let categories = [];
let currencies = [];
let baseCurrency = null;
let activeCategory = "all";
let searchQuery = "";
let posMode = "order";
let openOrders = [];
let selectedOrder = null;
let selectedCurrencyId = null;
let paymentMethod = "cash";
let customers = [];
let inclusiveTaxRate = 15.5;
let stopAutoSync = null;
let stopKitchenRefresh = null;
let fiscalDayStatus = null;
let diningTables = [];
let tablePickerManageMode = false;

const FISCAL_STATUS_LABELS = {
  FiscalDayClosed: "Closed",
  FiscalDayOpened: "Open",
  FiscalDayCloseFailed: "Close failed",
  FiscalDayCloseInitiated: "Closing…",
};

const branchLabel = document.getElementById("branch-label");
const syncStatus = document.getElementById("sync-status");
const syncBtn = document.getElementById("sync-btn");
const logoutBtn = document.getElementById("logout-btn");
const fiscalDayBtn = document.getElementById("fiscal-day-btn");
const dayendBtn = document.getElementById("dayend-btn");
const fiscalDayModal = document.getElementById("fiscal-day-modal");
const fiscalDayCloseBtn = document.getElementById("fiscal-day-close-btn");
const fiscalDayRefreshBtn = document.getElementById("fiscal-day-refresh-btn");
const fiscalDayOpenBtn = document.getElementById("fiscal-day-open-btn");
const fiscalDayCloseDayBtn = document.getElementById("fiscal-day-close-day-btn");
const fiscalDayBranchLabel = document.getElementById("fiscal-day-branch");
const fiscalDayStatusBadge = document.getElementById("fiscal-day-status-badge");
const fiscalDayNumberEl = document.getElementById("fiscal-day-number");
const fiscalDayGlobalNoEl = document.getElementById("fiscal-day-global-no");
const fiscalDayErrorEl = document.getElementById("fiscal-day-error");
const stockTakeRequiredModal = document.getElementById("stock-take-required-modal");
const stockTakeRequiredMessage = document.getElementById("stock-take-required-message");
const stockTakeRequiredCloseBtn = document.getElementById("stock-take-required-close-btn");
const stockTakeRequiredCancelBtn = document.getElementById("stock-take-required-cancel-btn");
const stockTakeRequiredOpenBtn = document.getElementById("stock-take-required-open-btn");
const categoryTabs = document.getElementById("category-tabs");
const productSearchInput = document.getElementById("product-search");
const productGrid = document.getElementById("product-grid");
const cartItems = document.getElementById("cart-items");
const cartTotal = document.getElementById("cart-total");
const checkoutBtn = document.getElementById("checkout-btn");
const clearBtn = document.getElementById("clear-btn");
const panelTitle = document.getElementById("panel-title");
const orderType = document.getElementById("order-type");
const tableGroup = document.getElementById("table-group");
const tableNumber = document.getElementById("table-number");
const tableSelectBtn = document.getElementById("table-select-btn");
const tableSelectLabel = document.getElementById("table-select-label");
const tablePickerModal = document.getElementById("table-picker-modal");
const tablePickerTitle = document.getElementById("table-picker-title");
const tablePickerView = document.getElementById("table-picker-view");
const tableManageView = document.getElementById("table-manage-view");
const tablePickerGrid = document.getElementById("table-picker-grid");
const tableManageList = document.getElementById("table-manage-list");
const tableAddNameInput = document.getElementById("table-add-name");
const tableAddBtn = document.getElementById("table-add-btn");
const tableManageToggleBtn = document.getElementById("table-manage-toggle-btn");
const tablePickerCloseBtn = document.getElementById("table-picker-close-btn");
const tablePickerCancelBtn = document.getElementById("table-picker-cancel-btn");
const orderModePanel = document.getElementById("order-mode-panel");
const receiptModePanel = document.getElementById("receipt-mode-panel");
const receiptOrdersList = document.getElementById("receipt-orders-list");
const receiptPaymentSection = document.getElementById("receipt-payment-section");
const paymentMethodToggle = document.getElementById("payment-method-toggle");
const paymentCurrencyToggle = document.getElementById("payment-currency-toggle");
const paymentCurrencyGroup = document.getElementById("payment-currency-group");
const receiptCustomerSelect = document.getElementById("receipt-customer");
const receiptCustomerGroup = document.getElementById("receipt-customer-group");
const accountBalanceHint = document.getElementById("account-balance-hint");
const receiptAccountBalance = document.getElementById("receipt-account-balance");
const receiptTotals = document.getElementById("receipt-totals");
const cartTotalLabel = document.getElementById("cart-total-label");
const posModeToggle = document.getElementById("pos-mode-toggle");

function closeStockTakeRequiredModal() {
  stockTakeRequiredModal.hidden = true;
}

function openStockTakeRequiredModal(message) {
  stockTakeRequiredMessage.textContent = message;
  stockTakeRequiredModal.hidden = false;
}

async function ensureDailyStockTakeForDayEnd(reportDate) {
  if (!session?.branch?.id) {
    showToast("Branch is not configured for this session.", true);
    return false;
  }
  const date = reportDate || new Date().toISOString().slice(0, 10);
  try {
    const result = await fetchStockTakeDayEndCheck(session, session.branch.id, date);
    if (result.completed) return true;
    openStockTakeRequiredModal(
      result.detail || `Complete and post variances on the daily stock take for ${date} before running day end.`
    );
    return false;
  } catch (err) {
    showToast(err.message, true);
    return false;
  }
}

function canManageFiscalDay() {
  if (session?.user?.can_manage_fiscal_day != null) {
    return Boolean(session.user.can_manage_fiscal_day);
  }
  return Boolean(session?.branch?.fiscalization_enabled);
}

function canManageDiningTables() {
  if (session?.user?.can_manage_dining_tables != null) {
    return Boolean(session.user.can_manage_dining_tables);
  }
  return session?.user?.role === "branch_manager";
}

function fiscalStatusBadgeHtml(status) {
  const label = FISCAL_STATUS_LABELS[status] || status || "Unknown";
  const cls = status === "FiscalDayOpened"
    ? "badge-active"
    : status === "FiscalDayCloseFailed"
      ? "badge-inactive"
      : "badge-open";
  return `<span class="badge ${cls}">${label}</span>`;
}

function updateFiscalDayButtonVisibility() {
  if (!fiscalDayBtn) return;
  const show = canManageFiscalDay() && session?.branch?.fiscalization_enabled;
  fiscalDayBtn.hidden = !show;
}

function updateTableManageVisibility() {
  if (tableManageToggleBtn) {
    tableManageToggleBtn.hidden = !canManageDiningTables();
  }
}

function renderFiscalDayModal(status = null, error = "") {
  const branch = session?.branch;
  if (fiscalDayBranchLabel) {
    fiscalDayBranchLabel.textContent = branch
      ? `${branch.name}${branch.zimra_device_id ? ` · Device ${branch.zimra_device_id}` : ""}`
      : "";
  }
  if (fiscalDayErrorEl) {
    fiscalDayErrorEl.hidden = !error;
    fiscalDayErrorEl.textContent = error || "";
  }
  if (fiscalDayStatusBadge) {
    fiscalDayStatusBadge.innerHTML = error
      ? `<span class="badge badge-inactive">Error</span>`
      : fiscalStatusBadgeHtml(status?.fiscal_day_status);
  }
  if (fiscalDayNumberEl) {
    fiscalDayNumberEl.textContent = status?.fiscal_day_number ?? "—";
  }
  if (fiscalDayGlobalNoEl) {
    fiscalDayGlobalNoEl.textContent = status?.last_receipt_global_no ?? "—";
  }
  if (fiscalDayOpenBtn) fiscalDayOpenBtn.disabled = Boolean(error) || !status?.can_open_day;
  if (fiscalDayCloseDayBtn) fiscalDayCloseDayBtn.disabled = Boolean(error) || !status?.can_close_day;
  if (fiscalDayRefreshBtn) fiscalDayRefreshBtn.disabled = false;
}

function closeFiscalDayModal() {
  if (fiscalDayModal) fiscalDayModal.hidden = true;
}

async function refreshFiscalDayStatus() {
  if (!session?.branch?.id || !session.branch.fiscalization_enabled) return;
  if (!isBrowserOnline()) {
    renderFiscalDayModal(null, "Fiscal day requires an online connection.");
    return;
  }

  if (fiscalDayRefreshBtn) fiscalDayRefreshBtn.disabled = true;
  if (fiscalDayOpenBtn) fiscalDayOpenBtn.disabled = true;
  if (fiscalDayCloseDayBtn) fiscalDayCloseDayBtn.disabled = true;

  try {
    fiscalDayStatus = await fetchFiscalDayStatus(session, session.branch.id);
    renderFiscalDayModal(fiscalDayStatus);
  } catch (err) {
    fiscalDayStatus = null;
    renderFiscalDayModal(null, err.message);
    showToast(err.message, true);
  }
}

async function runFiscalDayAction(action) {
  if (!session?.branch?.id || !session.branch.fiscalization_enabled) return;
  if (!isBrowserOnline()) {
    showToast("Fiscal day requires an online connection.", true);
    return;
  }

  if (fiscalDayRefreshBtn) fiscalDayRefreshBtn.disabled = true;
  if (fiscalDayOpenBtn) fiscalDayOpenBtn.disabled = true;
  if (fiscalDayCloseDayBtn) fiscalDayCloseDayBtn.disabled = true;

  try {
    const request = action === "open" ? openFiscalDay : closeFiscalDay;
    fiscalDayStatus = await request(session, session.branch.id);
    renderFiscalDayModal(fiscalDayStatus);
    showToast(action === "open" ? "Fiscal day opened" : "Fiscal day close requested");
    if (action === "close") {
      setTimeout(() => refreshFiscalDayStatus().catch(() => {}), 2500);
    }
  } catch (err) {
    showToast(err.message, true);
    await refreshFiscalDayStatus();
  }
}

function openFiscalDayModal() {
  if (!session?.branch?.fiscalization_enabled) {
    showToast("This branch is not configured for fiscalization.", true);
    return;
  }
  if (!isBrowserOnline()) {
    showToast("Fiscal day requires an online connection.", true);
    return;
  }
  if (fiscalDayModal) fiscalDayModal.hidden = false;
  renderFiscalDayModal(fiscalDayStatus);
  refreshFiscalDayStatus();
}

orderType.addEventListener("change", () => {
  tableGroup.style.display = orderType.value === "dine_in" ? "block" : "none";
  if (orderType.value !== "dine_in") {
    setSelectedTable("");
  }
});

function setSelectedTable(name) {
  const value = (name || "").trim();
  tableNumber.value = value;
  tableSelectLabel.textContent = value || "Choose table…";
  tableSelectBtn.classList.toggle("has-value", Boolean(value));
}

function occupiedTableNames() {
  const names = new Set();
  for (const order of openOrders) {
    if (order.order_type === "dine_in" && order.table_number) {
      names.add(order.table_number);
    }
  }
  return names;
}

async function loadDiningTables() {
  const local = await window.pos.getCatalog();
  diningTables = (local.diningTables || []).filter((table) => table.is_active);
  if (session?.branch?.id && isBrowserOnline()) {
    try {
      const data = await fetchDiningTables(session, session.branch.id);
      const remote = Array.isArray(data?.results) ? data.results : Array.isArray(data) ? data : [];
      diningTables = remote.filter((table) => table.is_active);
    } catch {
      // keep cached tables when offline or request fails
    }
  }
}

function renderTablePickerGrid() {
  if (!diningTables.length) {
    const hint = canManageDiningTables()
      ? "No tables configured. Sync online or use Manage tables."
      : "No tables configured. Ask a branch manager to set up tables.";
    tablePickerGrid.innerHTML = `<div class="empty-state wide"><p>${hint}</p></div>`;
    return;
  }

  const occupied = occupiedTableNames();
  const selected = tableNumber.value;
  tablePickerGrid.innerHTML = diningTables
    .map((table) => {
      const classes = ["card", "category-tab", "category-card"];
      if (occupied.has(table.name)) classes.push("occupied");
      if (table.name === selected) classes.push("active");
      const statusLabel = occupied.has(table.name) ? "In use" : "Available";
      return `
        <button type="button" class="${classes.join(" ")}" data-table-name="${table.name}">
          <div class="name">${table.name}</div>
          <div class="table-status">${statusLabel}</div>
        </button>`;
    })
    .join("");
}

function renderTableManageList() {
  if (!diningTables.length) {
    tableManageList.innerHTML = `<div class="empty-state"><p>No tables yet.</p></div>`;
    return;
  }

  tableManageList.innerHTML = diningTables
    .map(
      (table) => `
    <div class="table-manage-row" data-table-id="${table.id}">
      <input type="text" class="report-input table-manage-name" value="${table.name}" maxlength="20">
      <button type="button" class="btn btn-ghost btn-sm table-manage-save">Save</button>
      <button type="button" class="btn btn-ghost btn-sm table-manage-delete">Remove</button>
    </div>`
    )
    .join("");
}

function setTablePickerManageMode(enabled) {
  tablePickerManageMode = enabled;
  tablePickerView.hidden = enabled;
  tableManageView.hidden = !enabled;
  tablePickerTitle.textContent = enabled ? "Manage tables" : "Select table";
  tableManageToggleBtn.textContent = enabled ? "Back to tables" : "Manage tables";
  if (enabled) renderTableManageList();
  else renderTablePickerGrid();
}

function closeTablePickerModal() {
  tablePickerModal.hidden = true;
  setTablePickerManageMode(false);
  tableAddNameInput.value = "";
}

async function openTablePickerModal() {
  await loadOpenOrders();
  await loadDiningTables();
  setTablePickerManageMode(false);
  tablePickerModal.hidden = false;
  renderTablePickerGrid();
}

tableSelectBtn.addEventListener("click", openTablePickerModal);

tablePickerGrid.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-table-name]");
  if (!btn) return;
  setSelectedTable(btn.dataset.tableName);
  closeTablePickerModal();
});

tableManageToggleBtn?.addEventListener("click", () => {
  if (!canManageDiningTables()) return;
  setTablePickerManageMode(!tablePickerManageMode);
});

if (tableManageList) {
  tableManageList.addEventListener("click", async (event) => {
    if (!canManageDiningTables()) return;
    if (!isBrowserOnline()) {
      showToast("Managing tables requires an online connection.", true);
      return;
    }
  const row = event.target.closest(".table-manage-row");
  if (!row) return;
  const tableId = Number(row.dataset.tableId);
  const table = diningTables.find((item) => item.id === tableId);
  if (!table) return;

  if (event.target.closest(".table-manage-save")) {
    const name = (row.querySelector(".table-manage-name")?.value || "").trim();
    if (!name) {
      showToast("Table name is required", true);
      return;
    }
    try {
      await updateDiningTable(session, tableId, { name });
      showToast("Table updated");
      await runFullSyncIfOnline(session, { silent: true });
      await loadDiningTables();
      if (tableNumber.value === table.name && name !== table.name) setSelectedTable(name);
      renderTableManageList();
      renderTablePickerGrid();
    } catch (err) {
      showToast(err.message, true);
    }
    return;
  }

  if (event.target.closest(".table-manage-delete")) {
    if (!window.confirm(`Remove table "${table.name}"?`)) return;
    try {
      await updateDiningTable(session, tableId, { is_active: false });
      showToast("Table removed");
      if (tableNumber.value === table.name) setSelectedTable("");
      await runFullSyncIfOnline(session, { silent: true });
      await loadDiningTables();
      renderTableManageList();
      renderTablePickerGrid();
    } catch (err) {
      showToast(err.message, true);
    }
  }
  });
}

tableAddBtn?.addEventListener("click", async () => {
  if (!canManageDiningTables()) return;
  if (!isBrowserOnline()) {
    showToast("Managing tables requires an online connection.", true);
    return;
  }
  const name = (tableAddNameInput.value || "").trim();
  if (!name) {
    showToast("Enter a table name", true);
    return;
  }
  try {
    const maxSort = diningTables.reduce((max, table) => Math.max(max, table.sort_order || 0), -1);
    await createDiningTable(session, {
      branch: session.branch.id,
      name,
      sort_order: maxSort + 1,
      is_active: true,
    });
    tableAddNameInput.value = "";
    showToast("Table added");
    await runFullSyncIfOnline(session, { silent: true });
    await loadDiningTables();
    renderTableManageList();
    renderTablePickerGrid();
  } catch (err) {
    showToast(err.message, true);
  }
});

tablePickerCloseBtn?.addEventListener("click", closeTablePickerModal);
tablePickerCancelBtn?.addEventListener("click", closeTablePickerModal);
tablePickerModal?.addEventListener("click", (event) => {
  if (event.target === tablePickerModal) closeTablePickerModal();
});

function syncPaymentMethodUI() {
  const isAccount = paymentMethod === "account";
  receiptCustomerGroup.style.display = isAccount ? "" : "none";
  paymentCurrencyGroup.style.display = isAccount ? "none" : "";
  if (isAccount) {
    updateAccountBalanceHint();
  } else {
    accountBalanceHint.style.display = "none";
  }
}

function setPaymentMethod(method, { force = false } = {}) {
  if (!force && method === paymentMethod) return;
  paymentMethod = method;
  paymentMethodToggle.querySelectorAll(".pos-mode-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.method === method);
  });
  syncPaymentMethodUI();
  if (selectedOrder) {
    const inclusiveTotal = getOrderInclusiveTotal(selectedOrder);
    renderReceiptTotals(inclusiveTotal);
    updateCheckoutButtonState(inclusiveTotal);
  }
}

paymentMethodToggle.addEventListener("click", (e) => {
  const btn = e.target.closest(".pos-mode-btn");
  if (!btn || !paymentMethodToggle.contains(btn)) return;
  setPaymentMethod(btn.dataset.method);
});

function setPaymentCurrency(currencyId) {
  selectedCurrencyId = currencyId;
  paymentCurrencyToggle.querySelectorAll(".pos-mode-btn").forEach((b) => {
    b.classList.toggle("active", Number(b.dataset.currencyId) === currencyId);
  });
  if (selectedOrder) {
    const inclusiveTotal = getOrderInclusiveTotal(selectedOrder);
    renderReceiptTotals(inclusiveTotal);
    updateCheckoutButtonState(inclusiveTotal);
  }
}

paymentCurrencyToggle.addEventListener("click", (e) => {
  const btn = e.target.closest(".pos-mode-btn");
  if (!btn || !paymentCurrencyToggle.contains(btn)) return;
  setPaymentCurrency(Number(btn.dataset.currencyId) || null);
});

function customerDisplayName(customer) {
  return customer.full_name || `${customer.first_name} ${customer.last_name || ""}`.trim();
}

function renderCustomerSelect() {
  const options = customers.map((c) => {
    const balance = Number(c.account_balance) > 0 ? ` · ${money(c.account_balance)}` : "";
    return `<option value="${c.id}">${customerDisplayName(c)}${balance}</option>`;
  }).join("");
  receiptCustomerSelect.innerHTML = `<option value="">Walk-in (no account)</option>${options}`;
}

function getCustomerById(id) {
  if (!id) return null;
  return customers.find((c) => c.id === Number(id)) || null;
}

function updateAccountBalanceHint() {
  if (paymentMethod !== "account") {
    accountBalanceHint.style.display = "none";
    return;
  }
  const customer = getCustomerById(receiptCustomerSelect.value);
  if (!customer) {
    accountBalanceHint.style.display = "none";
    return;
  }
  accountBalanceHint.style.display = "";
  receiptAccountBalance.textContent = money(customer.account_balance);
}

function updateCheckoutButtonState(inclusiveTotal) {
  if (paymentMethod === "account") {
    const customer = getCustomerById(receiptCustomerSelect.value);
    const total = computeTaxBreakdown(inclusiveTotal).total;
    const hasBalance = customer && Number(customer.account_balance) >= total;
    checkoutBtn.disabled = !customer || !hasBalance;
    return;
  }
  const { hasRate } = computePaymentAmounts(computeTaxBreakdown(inclusiveTotal).total);
  checkoutBtn.disabled = !selectedCurrencyId || !hasRate;
}

receiptCustomerSelect.addEventListener("change", () => {
  updateAccountBalanceHint();
  if (!selectedOrder) return;
  const inclusiveTotal = getOrderInclusiveTotal(selectedOrder);
  renderReceiptTotals(inclusiveTotal);
  updateCheckoutButtonState(inclusiveTotal);
});

posModeToggle.addEventListener("click", (e) => {
  const btn = e.target.closest(".pos-mode-btn");
  if (!btn || !posModeToggle.contains(btn)) return;
  const mode = btn.dataset.mode;
  if (!mode || mode === posMode) return;
  setPosMode(mode);
});

function setPosMode(mode) {
  posMode = mode;
  posModeToggle.querySelectorAll(".pos-mode-btn").forEach((btn) => {
    const active = btn.dataset.mode === mode;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  orderModePanel.style.display = mode === "order" ? "" : "none";
  receiptModePanel.style.display = mode === "receipt" ? "" : "none";
  if (mode === "receipt") {
    selectedOrder = null;
    loadCustomers();
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

function renderPaymentCurrencyToggle() {
  const active = currencies.filter((c) => c.is_active);
  if (!active.length) {
    paymentCurrencyToggle.innerHTML = `<span class="pos-segment-placeholder">No currencies configured</span>`;
    selectedCurrencyId = null;
    return;
  }

  if (!selectedCurrencyId || !active.some((c) => c.id === selectedCurrencyId)) {
    selectedCurrencyId = active[0].id;
  }

  paymentCurrencyToggle.innerHTML = active
    .map((c) => {
      const rateLabel = c.is_base
        ? ""
        : c.current_rate
          ? ` · ${c.current_rate}`
          : " · no rate";
      const label = c.name;
      return `<button type="button" class="pos-mode-btn${c.id === selectedCurrencyId ? " active" : ""}" data-currency-id="${c.id}" title="${c.name}${rateLabel}">${label}</button>`;
    })
    .join("");
}

function renderReceiptTotals(inclusiveTotal) {
  const { subtotal, tax, total } = computeTaxBreakdown(inclusiveTotal);
  const { rate, amountDue, currency, hasRate } = computePaymentAmounts(total);
  const rateRow =
    currency && !currency.is_base && hasRate
      ? `<div class="receipt-total-row"><span>Exchange rate</span><span>${rate}</span></div>`
      : "";
  const missingRate =
    currency && !currency.is_base && !hasRate
      ? `<div class="receipt-total-row" style="color: #b45309;"><span>No rate set</span><span>Add under Rates</span></div>`
      : "";

  receiptTotals.innerHTML = `
    <div class="receipt-total-row"><span>Subtotal${baseCurrency ? ` (${baseCurrency.name})` : ""}</span><span>${money(subtotal)}</span></div>
    <div class="receipt-total-row"><span>Tax (${inclusiveTaxRate}%)</span><span>${money(tax)}</span></div>
    <div class="receipt-total-row"><span>Total${baseCurrency ? ` (${baseCurrency.name})` : ""}</span><span>${money(total)}</span></div>
    ${rateRow}
    ${missingRate}
    <div class="receipt-total-row receipt-total-due"><span>Amount due${currency ? ` (${currency.name})` : ""}</span><span>${hasRate ? money(amountDue, currency) : "—"}</span></div>
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
    cartItems.innerHTML = `<div class="empty-state" style="padding: 2rem 0;"><p style="margin: 0; font-size: 0.85rem;">Tap products to add items</p></div>`;
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
        <span style="min-width: 1.5rem; text-align: center; font-weight: 600;">${item.quantity}</span>
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
  panelTitle.textContent = selectedOrder
    ? `Order ${selectedOrder.receipt_number || selectedOrder.client_id.slice(0, 8)}`
    : "Receipt";
  clearBtn.style.display = "none";

  if (!selectedOrder) {
    cartItems.innerHTML = `<div class="empty-state" style="padding: 2rem 0;"><p style="margin: 0; font-size: 0.85rem;">Select an open order to view details</p></div>`;
    cartTotal.textContent = money(0);
    cartTotalLabel.textContent = "Total";
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
        <div class="line-total" style="font-weight: 600;">${money(item.price * item.quantity)}</div>
      </div>`
      )
      .join("")}
  `;

  renderPaymentCurrencyToggle();
  setPaymentMethod("cash", { force: true });
  receiptCustomerSelect.value = "";
  updateAccountBalanceHint();
  receiptPaymentSection.style.display = "";
  const inclusiveTotal = getOrderInclusiveTotal(selectedOrder);
  renderReceiptTotals(inclusiveTotal);
  checkoutBtn.textContent = "Collect Payment";
  updateCheckoutButtonState(inclusiveTotal);
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
      (cat) => `
    <button type="button" class="card category-tab category-card${activeCategory === String(cat.id) ? " active" : ""}" data-id="${cat.id}">
      <div class="name">${cat.name}</div>
    </button>`
    )
    .join("");
}

function matchesProductSearch(product) {
  if (!searchQuery) return true;
  const haystack = [product.name, product.category_name]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(searchQuery);
}

function renderProducts() {
  let filtered =
    activeCategory === "all"
      ? products
      : products.filter((p) => p.category === Number(activeCategory));
  filtered = filtered.filter(matchesProductSearch);

  if (!filtered.length) {
    const message = searchQuery
      ? "No matching products"
      : "No products in this category";
    productGrid.innerHTML = `<div class="empty-state wide"><p>${message}</p></div>`;
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
  productSearchInput.value = "";
  searchQuery = "";
  renderCategories();
  renderProducts();
});

productSearchInput.addEventListener("input", () => {
  searchQuery = productSearchInput.value.trim().toLowerCase();
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
    const allowed = await ensureDailyStockTakeForDayEnd();
    if (!allowed) return;
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

stockTakeRequiredCloseBtn?.addEventListener("click", closeStockTakeRequiredModal);
stockTakeRequiredCancelBtn?.addEventListener("click", closeStockTakeRequiredModal);
stockTakeRequiredOpenBtn?.addEventListener("click", async () => {
  const base = session?.serverUrl?.replace(/\/$/, "");
  if (!base) {
    showToast("Server URL is not configured.", true);
    return;
  }
  await window.pos.openExternal(`${base}/stock-take/`);
  closeStockTakeRequiredModal();
});
stockTakeRequiredModal?.addEventListener("click", (event) => {
  if (event.target === stockTakeRequiredModal) closeStockTakeRequiredModal();
});

if (fiscalDayBtn) {
  fiscalDayBtn.addEventListener("click", openFiscalDayModal);
}
fiscalDayCloseBtn?.addEventListener("click", closeFiscalDayModal);
fiscalDayRefreshBtn?.addEventListener("click", () => refreshFiscalDayStatus());
fiscalDayOpenBtn?.addEventListener("click", () => runFiscalDayAction("open"));
fiscalDayCloseDayBtn?.addEventListener("click", () => runFiscalDayAction("close"));
fiscalDayModal?.addEventListener("click", (event) => {
  if (event.target === fiscalDayModal) closeFiscalDayModal();
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
    if (orderType.value === "dine_in") {
      setSelectedTable("");
    }
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
  if (!selectedOrder) return;
  const inclusiveTotal = getOrderInclusiveTotal(selectedOrder);
  const orderTotal = computeTaxBreakdown(inclusiveTotal).total;

  if (paymentMethod === "account") {
    showToast("Customer account payment is not available on desktop POS yet", true);
    return;
  }

  if (!selectedCurrencyId) {
    showToast("Please select a payment currency", true);
    return;
  }

  const { hasRate, currency, amountDue, rate } = computePaymentAmounts(orderTotal);
  if (!hasRate) {
    showToast(`No exchange rate configured for ${currency?.name || "this currency"}`, true);
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

async function loadCustomers() {
  if (!session?.serverUrl || !session?.token || !isBrowserOnline()) {
    customers = [];
    renderCustomerSelect();
    return;
  }

  try {
    const base = session.serverUrl.replace(/\/$/, "");
    const res = await fetch(`${base}/api/customers/?page_size=500`, {
      headers: { Authorization: `Token ${session.token}` },
    });
    if (!res.ok) throw new Error("Could not load customers");
    const data = await res.json();
    customers = Array.isArray(data?.results) ? data.results : Array.isArray(data) ? data : [];
    renderCustomerSelect();
  } catch {
    customers = [];
    renderCustomerSelect();
  }
}

async function loadCatalog() {
  const data = await window.pos.getCatalog();
  products = data.products;
  categories = data.categories;
  currencies = data.currencies;
  diningTables = (data.diningTables || []).filter((table) => table.is_active);
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
  updateFiscalDayButtonVisibility();
  updateTableManageVisibility();

  await loadCatalog();
  await loadDiningTables();
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
