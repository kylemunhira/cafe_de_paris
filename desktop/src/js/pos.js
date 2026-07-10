import {
  cancelServerOrder,
  closeFiscalDay,
  createDiningTable,
  createExpense,
  fetchDayEndReport,
  fetchDiningTables,
  fetchFiscalDayStatus,
  fetchOpenOrders,
  fetchStockTakeDayEndCheck,
  fetchSuppliers,
  formatCurrency,
  formatDate,
  kitchenStatusBadge,
  openFiscalDay,
  patchServerOrder,
  payServerOrder,
  showToast,
  updateDiningTable,
} from "./api.js";
import { printDayEndReport, printOrderSlip, printSalesReceipt } from "./print-client.js";
import {
  checkServerReachable,
  isBrowserOnline,
  runFullSync,
  runFullSyncIfOnline,
  startAutoSync,
  startKitchenRefresh,
} from "./sync.js";

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
let receiptOpenOrders = [];
let remoteOpenOrders = [];
let selectedOrder = null;
let selectedCurrencyId = null;
let paymentMethod = "cash";
/** Order key whose payment UI was last initialized; avoids resetting Cash/Account on kitchen refresh. */
let receiptPaymentOrderKey = null;
let customers = [];
let suppliers = [];
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
const syncStatusLabel = document.getElementById("sync-status-label");
const syncStatusError = document.getElementById("sync-status-error");
const syncBtn = document.getElementById("sync-btn");
const logoutBtn = document.getElementById("logout-btn");
const fiscalDayBtn = document.getElementById("fiscal-day-btn");
const expenseBtn = document.getElementById("expense-btn");
const dayendBtn = document.getElementById("dayend-btn");
const expenseModal = document.getElementById("expense-modal");
const expenseCloseBtn = document.getElementById("expense-close-btn");
const expenseCancelBtn = document.getElementById("expense-cancel-btn");
const expenseSaveBtn = document.getElementById("expense-save-btn");
const expenseDateInput = document.getElementById("expense-date");
const expenseSupplierSelect = document.getElementById("expense-supplier");
const expenseDescriptionInput = document.getElementById("expense-description");
const expenseCurrencySelect = document.getElementById("expense-currency");
const expenseAmountInput = document.getElementById("expense-amount");
const dayendModal = document.getElementById("dayend-modal");
const dayendCloseBtn = document.getElementById("dayend-close-btn");
const dayendCancelBtn = document.getElementById("dayend-cancel-btn");
const dayendPrintBtn = document.getElementById("dayend-print-btn");
const dayendDateInput = document.getElementById("dayend-date");
const dayendCurrencyFields = document.getElementById("dayend-currency-fields");
const dayendCodeGroup = document.getElementById("dayend-code-group");
const dayendCurrencyCodeSelect = document.getElementById("dayend-currency-code");
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
const cancelOrderBtn = document.getElementById("cancel-order-btn");
const clearBtn = document.getElementById("clear-btn");
const panelTitle = document.getElementById("panel-title");
const orderType = document.getElementById("order-type");
const tableGroup = document.getElementById("table-group");
const tableNumber = document.getElementById("table-number");
const tableSelectBtn = document.getElementById("table-select-btn");
const tableSelectLabel = document.getElementById("table-select-label");
const tablesInUseSummary = document.getElementById("tables-in-use-summary");
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
const splitPaymentGroup = document.getElementById("split-payment-group");
const splitPaymentEnabledInput = document.getElementById("split-payment-enabled");
const splitPaymentFields = document.getElementById("split-payment-fields");
const splitPaymentRows = document.getElementById("split-payment-rows");
const splitRemainingEl = document.getElementById("split-remaining");
const splitFillBaseBtn = document.getElementById("split-fill-base-btn");
let splitPaymentEnabled = false;
const receiptCustomerSelect = document.getElementById("receipt-customer");
const receiptCustomerGroup = document.getElementById("receipt-customer-group");
const accountBalanceHint = document.getElementById("account-balance-hint");
const receiptAccountBalance = document.getElementById("receipt-account-balance");
const receiptTotals = document.getElementById("receipt-totals");
const cartTotalLabel = document.getElementById("cart-total-label");
const posModeToggle = document.getElementById("pos-mode-toggle");
const addonPickerModal = document.getElementById("addon-picker-modal");
const addonPickerTitle = document.getElementById("addon-picker-title");
const addonPickerGroups = document.getElementById("addon-picker-groups");
const addonNotesInput = document.getElementById("addon-notes-input");
const addonPickerCloseBtn = document.getElementById("addon-picker-close-btn");
const addonPickerCancelBtn = document.getElementById("addon-picker-cancel-btn");
const addonPickerConfirmBtn = document.getElementById("addon-picker-confirm-btn");

let addonPickerProduct = null;
const addonPickerSelections = new Map();

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

function canCollectPayment() {
  if (session?.user?.can_collect_payment != null) {
    return Boolean(session.user.can_collect_payment);
  }
  return session?.user?.role !== "waiter";
}

function updateReceiptModeVisibility() {
  if (!posModeToggle) return;
  const showReceipt = canCollectPayment();
  posModeToggle.style.display = showReceipt ? "" : "none";
  if (!showReceipt && posMode === "receipt") {
    setPosMode("order");
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
  renderTablesInUseSummary();
});

function setSelectedTable(name) {
  const value = (name || "").trim();
  tableNumber.value = value;
  tableSelectLabel.textContent = value || "Choose table…";
  tableSelectBtn.classList.toggle("has-value", Boolean(value));
}

function occupiedTableNames() {
  const names = new Set();
  const localServerIds = new Set(
    openOrders.map((order) => order.server_id).filter(Boolean)
  );

  for (const order of openOrders) {
    if (order.order_type === "dine_in" && order.table_number) {
      names.add(order.table_number);
    }
  }

  for (const order of remoteOpenOrders) {
    if (order.order_type !== "dine_in" || !order.table_number) continue;
    if (order.id && localServerIds.has(order.id)) continue;
    names.add(order.table_number);
  }

  return names;
}

function ordersOnTable(tableName) {
  const table = (tableName || "").trim();
  if (!table) return { local: [], remote: [], total: 0 };

  const local = openOrdersForTable(table);
  const localServerIds = new Set(local.map((order) => order.server_id).filter(Boolean));
  const remote = remoteOpenOrders.filter((order) => {
    if (order.order_type !== "dine_in" || order.table_number !== table) return false;
    if (order.id && localServerIds.has(order.id)) return false;
    return true;
  });

  return { local, remote, total: local.length + remote.length };
}

function getOccupiedTablesSorted() {
  const occupied = occupiedTableNames();
  const known = diningTables.map((table) => table.name).filter((name) => occupied.has(name));
  const extra = [...occupied].filter((name) => !known.includes(name));
  return [...known, ...extra].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
}

function renderTablesInUseSummary() {
  if (!tablesInUseSummary) return;
  if (orderType.value !== "dine_in") {
    tablesInUseSummary.hidden = true;
    tablesInUseSummary.textContent = "";
    return;
  }

  const tables = getOccupiedTablesSorted();
  if (!tables.length) {
    tablesInUseSummary.hidden = true;
    tablesInUseSummary.textContent = "";
    return;
  }

  tablesInUseSummary.hidden = false;
  tablesInUseSummary.textContent =
    tables.length === 1 ? `Tables in use: ${tables[0]}` : `Tables in use: ${tables.join(", ")}`;
}

async function loadRemoteOpenOrders() {
  if (!session?.branch?.id || !session?.serverUrl || !session?.token || !isBrowserOnline()) {
    remoteOpenOrders = [];
    receiptOpenOrders = mergeReceiptOpenOrders(openOrders, remoteOpenOrders);
    return;
  }

  try {
    const data = await fetchOpenOrders(
      session.serverUrl,
      session.token,
      session.branch.id
    );
    remoteOpenOrders = Array.isArray(data?.results)
      ? data.results
      : Array.isArray(data)
        ? data
        : [];
  } catch {
    remoteOpenOrders = [];
  }
  receiptOpenOrders = mergeReceiptOpenOrders(openOrders, remoteOpenOrders);
}

function normalizeRemoteOrder(order) {
  return {
    client_id: `remote-${order.id}`,
    server_id: order.id,
    order_type: order.order_type,
    table_number: order.table_number || "",
    status: "open",
    total_amount: Number(order.total_amount),
    receipt_number: order.receipt_number || null,
    kitchen_status: order.kitchen_status || "pending",
    kitchen_started_at: order.kitchen_started_at || null,
    kitchen_ready_at: order.kitchen_ready_at || null,
    created_at: order.created_at,
    customer: order.customer || null,
    is_remote: true,
    items: (order.items || []).map((item) => ({
      product_id: item.product,
      product_name: item.product_name,
      quantity: Number(item.quantity),
      price: Number(item.price),
      notes: item.notes || "",
      addons: (item.addons || []).map((addon) => ({
        id: addon.id,
        name: addon.name,
        price: Number(addon.price || 0),
      })),
    })),
  };
}

function mergeReceiptOpenOrders(localOrders, remoteOrders) {
  const localServerIds = new Set(localOrders.map((order) => order.server_id).filter(Boolean));
  const merged = [...localOrders];
  for (const remote of remoteOrders) {
    if (remote.id && localServerIds.has(remote.id)) continue;
    merged.push(normalizeRemoteOrder(remote));
  }
  return merged.sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
}

function orderDisplayLabel(order) {
  if (!order) return "";
  if (order.receipt_number) return order.receipt_number;
  if (order.server_id) return `#${order.server_id}`;
  return order.client_id.slice(0, 8);
}

function receiptOrdersForTable(tableNumber) {
  const table = (tableNumber || "").trim();
  if (!table) return [];
  return receiptOpenOrders.filter(
    (order) => order.order_type === "dine_in" && order.table_number === table
  );
}

function shouldPayOrderOnline(order) {
  return Boolean(order?.is_remote || order?.server_id);
}

function mapApiOrderForPrint(apiOrder, paymentMeta = {}) {
  return {
    client_id: apiOrder.id ? `remote-${apiOrder.id}` : "",
    server_id: apiOrder.id,
    receipt_number: apiOrder.receipt_number,
    order_type: apiOrder.order_type,
    table_number: apiOrder.table_number || "",
    total_amount: Number(apiOrder.total_amount),
    amount_paid: Number(apiOrder.amount_paid),
    exchange_rate: apiOrder.exchange_rate,
    paid_by_name: apiOrder.paid_by_name,
    created_by_name: apiOrder.created_by_name,
    payment_currency_name: apiOrder.payment_currency_name,
    payment_currency_symbol: apiOrder.payment_currency_symbol,
    items: (apiOrder.items || []).map((item) => ({
      product_name: item.product_name,
      quantity: Number(item.quantity),
      price: Number(item.price),
      notes: item.notes || "",
      addons: item.addons || [],
    })),
    payments: apiOrder.payments || paymentMeta.payments || [],
    ...paymentMeta,
  };
}

function openOrdersForTable(tableNumber) {
  const table = (tableNumber || "").trim();
  if (!table) return [];
  return openOrders.filter(
    (order) => order.order_type === "dine_in" && order.table_number === table
  );
}

function getReceiptOrders() {
  if (!selectedOrder) return [];
  const tableOrders = receiptOrdersForTable(selectedOrder.table_number);
  return tableOrders.length > 1 ? tableOrders : [selectedOrder];
}

function getReceiptInclusiveTotal() {
  return getReceiptOrders().reduce(
    (sum, order) => sum + getOrderInclusiveTotal(order),
    0
  );
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
      const occupancy = ordersOnTable(table.name);
      if (occupied.has(table.name)) classes.push("occupied");
      if (table.name === selected) classes.push("active");
      const statusLabel = occupancy.total
        ? occupancy.total > 1
          ? `In use · ${occupancy.total} orders`
          : "In use"
        : "Available";
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
  if (tableManageToggleBtn) {
    tableManageToggleBtn.textContent = enabled ? "Back to tables" : "Manage tables";
  }
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

function allowsSplitPayment() {
  return Boolean(session?.branch && !session.branch.fiscalization_enabled);
}

function isSplitPaymentActive() {
  return allowsSplitPayment() && splitPaymentEnabled && paymentMethod !== "account";
}

function getSplitPaymentInputs() {
  return Array.from(document.querySelectorAll(".split-payment-input"));
}

function currencyRate(currency) {
  if (!currency) return null;
  if (currency.is_base) return 1;
  const rate = Number(currency.current_rate);
  return Number.isFinite(rate) && rate > 0 ? rate : null;
}

function amountToBase(amount, currency) {
  const rate = currencyRate(currency);
  if (rate == null) return null;
  return roundMoney(amount / rate);
}

function amountFromBase(baseAmount, currency) {
  const rate = currencyRate(currency);
  if (rate == null) return null;
  return roundMoney(baseAmount * rate);
}

function renderSplitPaymentRows() {
  if (!splitPaymentRows) return;
  const active = currencies.filter((c) => c.is_active);
  if (!active.length) {
    splitPaymentRows.innerHTML = `<span class="pos-segment-placeholder">No currencies configured</span>`;
    return;
  }
  const previous = {};
  getSplitPaymentInputs().forEach((input) => {
    previous[input.dataset.currencyId] = input.value;
  });
  splitPaymentRows.innerHTML = active
    .map((c) => {
      const rateLabel = c.is_base ? "" : c.current_rate ? ` · ${c.current_rate}` : " · no rate";
      const value = previous[String(c.id)] || "";
      const placeholder = splitPaymentPlaceholderForCurrency(c);
      return `
      <div class="split-payment-row">
        <label for="split-currency-${c.id}" title="${c.name}${rateLabel}">${c.name}</label>
        <input
          type="number"
          id="split-currency-${c.id}"
          class="split-payment-input"
          data-currency-id="${c.id}"
          step="0.01"
          min="0"
          placeholder="${placeholder}"
          value="${value}"
        >
      </div>
    `;
    })
    .join("");
  getSplitPaymentInputs().forEach((input) => {
    input.addEventListener("input", () => {
      updateSplitPaymentRemaining();
      if (selectedOrder) {
        updateCheckoutButtonState(getReceiptInclusiveTotal());
      }
    });
  });
}

function clearSplitPaymentInputs() {
  getSplitPaymentInputs().forEach((input) => {
    input.value = "";
  });
  updateSplitPaymentRemaining();
}

function setSplitPaymentEnabled(enabled) {
  splitPaymentEnabled = Boolean(enabled);
  if (splitPaymentEnabledInput) {
    splitPaymentEnabledInput.checked = splitPaymentEnabled;
  }
  if (splitPaymentEnabled) {
    renderSplitPaymentRows();
  } else {
    clearSplitPaymentInputs();
  }
  if (splitPaymentFields) {
    splitPaymentFields.style.display = splitPaymentEnabled ? "" : "none";
  }
  if (paymentCurrencyGroup && paymentMethod !== "account") {
    paymentCurrencyGroup.style.display = splitPaymentEnabled ? "none" : "";
  }
  updateSplitPaymentRemaining();
  if (selectedOrder) {
    const inclusiveTotal = getReceiptInclusiveTotal();
    renderReceiptTotals(inclusiveTotal);
    updateCheckoutButtonState(inclusiveTotal);
  }
}

function getSplitPaymentLines() {
  if (!isSplitPaymentActive()) return [];
  return getSplitPaymentInputs()
    .map((input) => {
      const amount = Number(input.value);
      if (!Number.isFinite(amount) || amount <= 0) return null;
      const currencyId = Number(input.dataset.currencyId);
      const currency = currencies.find((c) => c.id === currencyId);
      if (!currency || currencyRate(currency) == null) return null;
      return {
        currency_id: currencyId,
        currency,
        amount: roundMoney(amount),
        base_amount: amountToBase(amount, currency),
      };
    })
    .filter(Boolean);
}

function getSplitPaymentAllocatedBase() {
  return getSplitPaymentLines().reduce((sum, line) => sum + line.base_amount, 0);
}

function getSplitPaymentRemainingBaseForCurrency(excludeCurrencyId) {
  const orderTotal = getOrderTotalBase();
  if (orderTotal == null) return null;
  const othersBase = getSplitPaymentLines()
    .filter((line) => line.currency_id !== excludeCurrencyId)
    .reduce((sum, line) => sum + line.base_amount, 0);
  return roundMoney(orderTotal - othersBase);
}

function splitPaymentPlaceholderForCurrency(currency) {
  const remainingBase = getSplitPaymentRemainingBaseForCurrency(currency.id);
  if (remainingBase == null || currencyRate(currency) == null) return "0.00";
  const amount = amountFromBase(remainingBase, currency);
  return amount > 0 ? amount.toFixed(2) : "0.00";
}

function updateSplitPaymentPlaceholders() {
  if (!isSplitPaymentActive()) return;
  getSplitPaymentInputs().forEach((input) => {
    const currencyId = Number(input.dataset.currencyId);
    const currency = currencies.find((c) => c.id === currencyId);
    input.placeholder = currency ? splitPaymentPlaceholderForCurrency(currency) : "0.00";
  });
}

function getOrderTotalBase() {
  if (!selectedOrder || paymentMethod === "account") return null;
  const inclusiveTotal = getReceiptInclusiveTotal();
  return computeTaxBreakdown(inclusiveTotal).total;
}

function updateSplitPaymentRemaining() {
  if (!isSplitPaymentActive()) {
    return;
  }
  updateSplitPaymentPlaceholders();
  if (!splitRemainingEl) {
    return;
  }
  const orderTotal = getOrderTotalBase();
  if (orderTotal == null) {
    splitRemainingEl.textContent = "—";
    splitRemainingEl.className = "";
    return;
  }
  const remaining = roundMoney(orderTotal - getSplitPaymentAllocatedBase());
  splitRemainingEl.textContent = money(remaining, baseCurrency);
  splitRemainingEl.className = "";
  if (Math.abs(remaining) < 0.005) {
    splitRemainingEl.classList.add("split-balanced");
  } else if (remaining < 0) {
    splitRemainingEl.classList.add("split-over");
  }
}

function syncSplitPaymentUI() {
  if (!splitPaymentGroup) return;
  const available = paymentMethod !== "account" && allowsSplitPayment();
  splitPaymentGroup.style.display = available ? "" : "none";
  if (!available) {
    setSplitPaymentEnabled(false);
    return;
  }
  if (splitPaymentEnabled) {
    renderSplitPaymentRows();
  }
  if (splitPaymentFields) {
    splitPaymentFields.style.display = splitPaymentEnabled ? "" : "none";
  }
  if (splitPaymentEnabledInput) {
    splitPaymentEnabledInput.checked = splitPaymentEnabled;
  }
  if (paymentCurrencyGroup) {
    paymentCurrencyGroup.style.display = splitPaymentEnabled ? "none" : "";
  }
  updateSplitPaymentRemaining();
}

function syncPaymentMethodUI() {
  const isAccount = paymentMethod === "account";
  receiptCustomerGroup.style.display = isAccount ? "" : "none";
  if (isAccount) {
    paymentCurrencyGroup.style.display = "none";
    updateAccountBalanceHint();
  } else {
    accountBalanceHint.style.display = "none";
    paymentCurrencyGroup.style.display = isSplitPaymentActive() ? "none" : "";
  }
  syncSplitPaymentUI();
}

function setPaymentMethod(method, { force = false } = {}) {
  if (!force && method === paymentMethod) return;
  paymentMethod = method;
  paymentMethodToggle.querySelectorAll(".pos-mode-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.method === method);
  });
  syncPaymentMethodUI();
  if (selectedOrder) {
    const inclusiveTotal = getReceiptInclusiveTotal();
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
    const inclusiveTotal = getReceiptInclusiveTotal();
    renderReceiptTotals(inclusiveTotal);
    updateSplitPaymentRemaining();
    updateCheckoutButtonState(inclusiveTotal);
  }
}

paymentCurrencyToggle.addEventListener("click", (e) => {
  const btn = e.target.closest(".pos-mode-btn");
  if (!btn || !paymentCurrencyToggle.contains(btn)) return;
  setPaymentCurrency(Number(btn.dataset.currencyId) || null);
});

splitPaymentEnabledInput?.addEventListener("change", () => {
  setSplitPaymentEnabled(splitPaymentEnabledInput.checked);
});

splitFillBaseBtn?.addEventListener("click", () => {
  if (!isSplitPaymentActive()) return;
  const orderTotal = getOrderTotalBase();
  if (orderTotal == null) return;
  const targetCurrency =
    baseCurrency || currencies.find((c) => c.is_active && currencyRate(c) != null) || null;
  if (!targetCurrency) return;
  const input = getSplitPaymentInputs().find(
    (el) => Number(el.dataset.currencyId) === targetCurrency.id,
  );
  if (!input) return;
  const othersBase = getSplitPaymentLines()
    .filter((line) => line.currency_id !== targetCurrency.id)
    .reduce((sum, line) => sum + line.base_amount, 0);
  const restBase = roundMoney(orderTotal - othersBase);
  const rest = amountFromBase(restBase, targetCurrency);
  input.value = rest > 0 ? rest.toFixed(2) : "";
  updateSplitPaymentRemaining();
  if (selectedOrder) {
    updateCheckoutButtonState(getReceiptInclusiveTotal());
  }
});

function customerDisplayName(customer) {
  return customer.full_name || `${customer.first_name} ${customer.last_name || ""}`.trim();
}

function renderCustomerSelect() {
  const previous = receiptCustomerSelect.value;
  const options = customers.map((c) => {
    const balance = Number(c.account_balance) > 0 ? ` · ${money(c.account_balance)}` : "";
    return `<option value="${c.id}">${customerDisplayName(c)}${balance}</option>`;
  }).join("");
  receiptCustomerSelect.innerHTML = `<option value="">Walk-in (no account)</option>${options}`;
  if (previous && customers.some((c) => String(c.id) === previous)) {
    receiptCustomerSelect.value = previous;
  }
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
  if (isSplitPaymentActive()) {
    const orderTotal = computeTaxBreakdown(inclusiveTotal).total;
    const lines = getSplitPaymentLines();
    const allocated = roundMoney(lines.reduce((sum, line) => sum + line.base_amount, 0));
    checkoutBtn.disabled = !lines.length || Math.abs(allocated - orderTotal) >= 0.005;
    return;
  }
  const { hasRate } = computePaymentAmounts(computeTaxBreakdown(inclusiveTotal).total);
  checkoutBtn.disabled = !selectedCurrencyId || !hasRate;
}

async function linkCustomerToOrder(orderId, customerId) {
  const payload = { customer: customerId ? Number(customerId) : null };
  return patchServerOrder(session, orderId, payload);
}

receiptCustomerSelect.addEventListener("change", async () => {
  updateAccountBalanceHint();
  if (!selectedOrder) return;
  const inclusiveTotal = getReceiptInclusiveTotal();
  renderReceiptTotals(inclusiveTotal);
  updateCheckoutButtonState(inclusiveTotal);

  const customerId = receiptCustomerSelect.value;
  selectedOrder.customer = customerId ? Number(customerId) : null;
  if (!shouldPayOrderOnline(selectedOrder) || !selectedOrder.server_id) return;
  if (!isBrowserOnline()) return;
  try {
    const reachable = await checkServerReachable(session);
    if (!reachable) return;
    await linkCustomerToOrder(selectedOrder.server_id, customerId);
  } catch (err) {
    showToast(err.message, true);
  }
});

posModeToggle?.addEventListener("click", (e) => {
  const btn = e.target.closest(".pos-mode-btn");
  if (!btn || !posModeToggle.contains(btn)) return;
  const mode = btn.dataset.mode;
  if (!mode || mode === posMode) return;
  if (mode === "receipt" && !canCollectPayment()) return;
  setPosMode(mode);
});

function setPosMode(mode) {
  if (mode === "receipt" && !canCollectPayment()) {
    mode = "order";
  }
  posMode = mode;
  posModeToggle?.querySelectorAll(".pos-mode-btn").forEach((btn) => {
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
    return order.items.reduce((sum, item) => {
      const addonTotal = (item.addons || []).reduce(
        (addonSum, addon) => addonSum + Number(addon.price || 0),
        0
      );
      return sum + roundMoney((Number(item.price) + addonTotal) * Number(item.quantity));
    }, 0);
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

function productHasActiveAddons(product) {
  return (product.addon_groups || []).some((group) =>
    (group.addons || []).some((addon) => addon.is_active !== false)
  );
}

function cartLineKey(productId, addonIds, notes) {
  const sorted = [...addonIds].sort((a, b) => a - b).join(",");
  return `${productId}:${sorted}:${notes || ""}`;
}

function formatAddonChipLabel(addon) {
  const price = Number(addon.selling_price);
  return price > 0 ? `${addon.name} (+${money(price)})` : addon.name;
}

function cartLineDetailHtml(item) {
  const parts = [];
  if (item.addons?.length) {
    parts.push(
      `<div class="addon-line">${item.addons.map((addon) => addon.name).join(", ")}</div>`
    );
  }
  if (item.notes) {
    parts.push(`<div class="notes-line">${item.notes}</div>`);
  }
  return parts.join("");
}

function addProductToCart(product, addons = [], notes = "") {
  const addonPrice = addons.reduce((sum, addon) => sum + Number(addon.price), 0);
  const unitPrice = Number(product.selling_price) + addonPrice;
  const lineKey = cartLineKey(
    product.id,
    addons.map((addon) => addon.id),
    notes
  );
  const existing = cart.get(lineKey);
  if (existing) {
    existing.quantity += 1;
  } else {
    cart.set(lineKey, {
      lineKey,
      id: product.id,
      name: product.name,
      basePrice: Number(product.selling_price),
      price: unitPrice,
      quantity: 1,
      addons,
      notes,
    });
  }
  renderCart();
}

function renderPaymentCurrencyToggle() {
  const active = currencies.filter((c) => c.is_active);
  if (!active.length) {
    paymentCurrencyToggle.innerHTML = `<span class="pos-segment-placeholder">No currencies configured</span>`;
    selectedCurrencyId = null;
    return;
  }

  if (!selectedCurrencyId || !active.some((c) => c.id === selectedCurrencyId)) {
    selectedCurrencyId = (baseCurrency && active.some((c) => c.id === baseCurrency.id)
      ? baseCurrency.id
      : active[0].id);
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
  const useFx = paymentMethod !== "account" && !isSplitPaymentActive();
  const { rate, amountDue, currency, hasRate } = useFx
    ? computePaymentAmounts(total)
    : { rate: null, amountDue: null, currency: null, hasRate: false };
  const rateRow =
    currency && !currency.is_base && hasRate
      ? `<div class="receipt-total-row"><span>Exchange rate</span><span>${rate}</span></div>`
      : "";
  const missingRate =
    currency && !currency.is_base && !hasRate
      ? `<div class="receipt-total-row" style="color: #b45309;"><span>No rate set</span><span>Add under Rates</span></div>`
      : "";
  const dueRow = useFx
    ? `<div class="receipt-total-row receipt-total-due"><span>Amount due${currency ? ` (${currency.name})` : ""}</span><span>${hasRate ? money(amountDue, currency) : "—"}</span></div>`
    : `<div class="receipt-total-row receipt-total-due"><span>Amount due${baseCurrency ? ` (${baseCurrency.name})` : ""}</span><span>${money(total)}</span></div>`;

  receiptTotals.innerHTML = `
    <div class="receipt-total-row"><span>Subtotal${baseCurrency ? ` (${baseCurrency.name})` : ""}</span><span>${money(subtotal)}</span></div>
    <div class="receipt-total-row"><span>Tax (${inclusiveTaxRate}%)</span><span>${money(tax)}</span></div>
    <div class="receipt-total-row"><span>Total${baseCurrency ? ` (${baseCurrency.name})` : ""}</span><span>${money(total)}</span></div>
    ${rateRow}
    ${missingRate}
    ${dueRow}
  `;
  if (useFx && hasRate) {
    cartTotal.textContent = money(amountDue, currency);
    cartTotalLabel.textContent = currency && !currency.is_base ? "Amount due" : "Total";
  } else {
    cartTotal.textContent = money(total);
    cartTotalLabel.textContent = "Total";
  }
  updateSplitPaymentRemaining();
}

function renderCart() {
  panelTitle.textContent = "Current Order";
  checkoutBtn.textContent = "Place Order";
  clearBtn.style.display = "";
  if (cancelOrderBtn) {
    cancelOrderBtn.style.display = "none";
    cancelOrderBtn.disabled = true;
  }
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
    <div class="cart-item" data-line-key="${item.lineKey}">
      <div class="info">
        <div class="name">${item.name}</div>
        <div class="line-total">${money(item.price)} each</div>
        ${cartLineDetailHtml(item)}
      </div>
      <div class="qty-control">
        <button class="qty-btn" data-action="dec" data-line-key="${item.lineKey}">−</button>
        <span style="min-width: 1.5rem; text-align: center; font-weight: 600;">${item.quantity}</span>
        <button class="qty-btn" data-action="inc" data-line-key="${item.lineKey}">+</button>
      </div>
    </div>`
    )
    .join("");

  cartTotal.textContent = money(getCartTotal());
  checkoutBtn.disabled = false;
  clearBtn.disabled = false;
}

function renderReceiptPanel() {
  if (!selectedOrder) {
    receiptPaymentOrderKey = null;
    panelTitle.textContent = "Receipt";
    clearBtn.style.display = "none";
    if (cancelOrderBtn) {
      cancelOrderBtn.style.display = "none";
      cancelOrderBtn.disabled = true;
    }
    cartItems.innerHTML = `<div class="empty-state" style="padding: 2rem 0;"><p style="margin: 0; font-size: 0.85rem;">Select an open order to view details</p></div>`;
    cartTotal.textContent = money(0);
    cartTotalLabel.textContent = "Total";
    receiptPaymentSection.style.display = "none";
    checkoutBtn.textContent = "Collect Payment";
    checkoutBtn.disabled = true;
    return;
  }

  const orderKey = selectedOrder.client_id;
  const orderChanged = orderKey !== receiptPaymentOrderKey;
  receiptPaymentOrderKey = orderKey;

  const receiptOrders = getReceiptOrders();
  const combined = receiptOrders.length > 1;
  panelTitle.textContent = combined
    ? `Table ${selectedOrder.table_number} — ${receiptOrders.length} orders`
    : `Order ${orderDisplayLabel(selectedOrder)}`;
  clearBtn.style.display = "none";
  if (cancelOrderBtn) {
    cancelOrderBtn.style.display = "";
    cancelOrderBtn.disabled = false;
  }

  const typeLabel = selectedOrder.order_type.replace("_", " ");
  cartItems.innerHTML = `
    <div class="receipt-order-meta">
      <div class="receipt-meta" style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem;">
        <span>Kitchen</span>
        ${kitchenStatusBadge(selectedOrder.kitchen_status || "pending")}
      </div>
      <div class="receipt-meta">${typeLabel}</div>
      ${selectedOrder.table_number && !combined ? `<div class="receipt-meta">Table ${selectedOrder.table_number}</div>` : ""}
      ${combined ? `<div class="receipt-meta">Combined bill for table ${selectedOrder.table_number}</div>` : ""}
      <div class="receipt-meta">${formatDate(selectedOrder.created_at)}</div>
    </div>
    ${receiptOrders
      .map(
        (order) => `
      ${combined ? `<div class="receipt-meta" style="margin-top:0.75rem;font-weight:600;">Order ${orderDisplayLabel(order)}</div>` : ""}
      ${order.items
        .map(
          (item) => `
      <div class="cart-item">
        <div class="info">
          <div class="name">${item.product_name}</div>
          <div class="line-total">${money(item.price)} × ${item.quantity}</div>
          ${cartLineDetailHtml({
            addons: item.addons,
            notes: item.notes,
          })}
        </div>
        <div class="line-total" style="font-weight: 600;">${money(item.price * item.quantity)}</div>
      </div>`
        )
        .join("")}`
      )
      .join("")}
  `;

  renderPaymentCurrencyToggle();
  if (orderChanged) {
    setPaymentMethod("cash", { force: true });
    setSplitPaymentEnabled(false);
    receiptCustomerSelect.value = selectedOrder.customer ? String(selectedOrder.customer) : "";
  } else {
    syncPaymentMethodUI();
  }
  updateAccountBalanceHint();
  receiptPaymentSection.style.display = "";
  const inclusiveTotal = getReceiptInclusiveTotal();
  renderReceiptTotals(inclusiveTotal);
  checkoutBtn.textContent = combined ? "Collect Table Payment" : "Collect Payment";
  updateCheckoutButtonState(inclusiveTotal);
}

function renderOpenOrdersList() {
  if (!receiptOpenOrders.length) {
    receiptOrdersList.innerHTML = `<div class="empty-state"><p>No open orders for this branch</p></div>`;
    return;
  }

  receiptOrdersList.innerHTML = receiptOpenOrders
    .map((o) => {
      const tableOrders = o.table_number ? receiptOrdersForTable(o.table_number) : [];
      const combinedLabel =
        tableOrders.length > 1 ? ` · ${tableOrders.length} orders on table` : "";
      const displayTotal =
        tableOrders.length > 1
          ? tableOrders.reduce((sum, order) => sum + Number(order.total_amount), 0)
          : o.total_amount;
      const selected = selectedOrder?.client_id === o.client_id ? " selected" : "";
      const readyClass = o.kitchen_status === "ready" ? " receipt-order-ready" : "";
      return `
      <button type="button" class="receipt-order-card${selected}${readyClass}" data-id="${o.client_id}">
        <div class="receipt-order-card-top">
          <strong>${orderDisplayLabel(o)}</strong>
          <span class="receipt-order-amount">${money(displayTotal)}</span>
        </div>
        <div class="receipt-order-card-meta">${o.order_type.replace("_", " ")}${o.table_number ? ` · Table ${o.table_number}` : ""}${combinedLabel} · ${o.items.length} items</div>
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
  await loadRemoteOpenOrders();
  const visibleOrders = receiptOpenOrders;
  if (selectedOrder && !visibleOrders.some((o) => o.client_id === selectedOrder.client_id)) {
    selectedOrder = null;
  }
  renderOpenOrdersList();
  renderTablesInUseSummary();
  if (!tablePickerModal.hidden) {
    renderTablePickerGrid();
  }
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
    .map((p) => {
      const addonHint = productHasActiveAddons(p)
        ? `<div class="addon-hint">Tap to choose add-ons</div>`
        : "";
      return `
    <div class="card product-card" data-id="${p.id}">
      <div class="name">${p.name}</div>
      <div class="price">${money(p.selling_price)}</div>
      ${addonHint}
    </div>`;
    })
    .join("");
}

function setSyncErrorMessage(message) {
  const text = (message || "").trim();
  if (!text) {
    syncStatusError.hidden = true;
    syncStatusError.textContent = "";
    syncStatus.classList.remove("has-error");
    return;
  }
  syncStatusError.hidden = false;
  syncStatusError.textContent = text;
  syncStatus.classList.add("has-error");
}

async function updateSyncBadge() {
  const { pending, error } = await window.pos.getPendingSyncStatus();
  const catalogAt = (await window.pos.getCatalog()).catalogSyncedAt;
  const online = isBrowserOnline();

  setSyncErrorMessage("");

  if (!online) {
    const queued =
      pending === 1 ? "1 order queued" : `${pending} orders queued`;
    syncStatusLabel.textContent =
      pending > 0 ? `Offline · ${queued}` : "Offline — will sync when connected";
    if (error) {
      setSyncErrorMessage(error);
    }
    syncStatusLabel.classList.add("warn");
    return;
  }

  if (pending > 0) {
    const waiting =
      pending === 1 ? "1 order waiting to sync" : `${pending} orders waiting to sync`;
    syncStatusLabel.textContent = `Online · ${waiting}`;
    if (error) {
      setSyncErrorMessage(error);
    }
    syncStatusLabel.classList.add("warn");
    return;
  }

  syncStatusLabel.textContent = catalogAt
    ? `Online · synced ${formatDate(catalogAt)}`
    : "Online · syncing…";
  syncStatusLabel.classList.remove("warn");
}

cartItems.addEventListener("click", (e) => {
  if (posMode !== "order") return;
  const btn = e.target.closest(".qty-btn");
  if (!btn) return;
  const lineKey = btn.dataset.lineKey;
  const item = cart.get(lineKey);
  if (!item) return;
  item.quantity += btn.dataset.action === "inc" ? 1 : -1;
  if (item.quantity <= 0) cart.delete(lineKey);
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

function closeAddonPickerModal() {
  addonPickerModal.hidden = true;
  addonPickerProduct = null;
  addonPickerSelections.clear();
  addonPickerGroups.innerHTML = "";
  addonNotesInput.value = "";
}

function renderAddonPickerGroups(product) {
  addonPickerGroups.innerHTML = "";
  addonPickerSelections.clear();

  for (const group of product.addon_groups || []) {
    const activeAddons = (group.addons || []).filter((addon) => addon.is_active !== false);
    if (!activeAddons.length) continue;

    const section = document.createElement("div");
    section.className = "addon-picker-group";
    section.dataset.groupId = String(group.id);
    section.dataset.selectionType = group.selection_type || "multiple";

    const title = document.createElement("p");
    title.className = "addon-picker-group-title";
    title.textContent = group.name;
    section.appendChild(title);

    const chipGroup = document.createElement("div");
    chipGroup.className = "addon-chip-group";
    const groupSelections = new Set();
    addonPickerSelections.set(group.id, groupSelections);

    for (const addon of activeAddons) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "addon-chip";
      chip.textContent = formatAddonChipLabel(addon);
      chip.dataset.addonId = String(addon.id);
      chip.addEventListener("click", () => {
        const isSingle = section.dataset.selectionType === "single";
        if (isSingle) {
          groupSelections.clear();
          chipGroup.querySelectorAll(".addon-chip").forEach((el) => el.classList.remove("active"));
        }
        if (groupSelections.has(addon.id)) {
          groupSelections.delete(addon.id);
          chip.classList.remove("active");
        } else {
          groupSelections.add(addon.id);
          chip.classList.add("active");
        }
      });
      chipGroup.appendChild(chip);
    }

    section.appendChild(chipGroup);
    addonPickerGroups.appendChild(section);
  }
}

function openAddonPickerModal(product) {
  addonPickerProduct = product;
  addonPickerTitle.textContent = `Add-ons — ${product.name}`;
  addonNotesInput.value = "";
  renderAddonPickerGroups(product);
  addonPickerModal.hidden = false;
}

function collectSelectedAddons(product) {
  const addons = [];
  for (const group of product.addon_groups || []) {
    const selectedIds = addonPickerSelections.get(group.id) || new Set();
    for (const addon of group.addons || []) {
      if (selectedIds.has(addon.id)) {
        addons.push({
          id: addon.id,
          name: addon.name,
          price: Number(addon.selling_price),
        });
      }
    }
  }
  return addons;
}

function confirmAddonPicker() {
  if (!addonPickerProduct) return;
  const addons = collectSelectedAddons(addonPickerProduct);
  const notes = addonNotesInput.value.trim();
  addProductToCart(addonPickerProduct, addons, notes);
  closeAddonPickerModal();
}

addonPickerCloseBtn?.addEventListener("click", closeAddonPickerModal);
addonPickerCancelBtn?.addEventListener("click", closeAddonPickerModal);
addonPickerConfirmBtn?.addEventListener("click", confirmAddonPicker);
addonPickerModal?.addEventListener("click", (event) => {
  if (event.target === addonPickerModal) closeAddonPickerModal();
});

productGrid.addEventListener("click", (e) => {
  const card = e.target.closest(".product-card");
  if (!card) return;
  const product = products.find((p) => p.id === Number(card.dataset.id));
  if (!product) return;
  if (productHasActiveAddons(product)) {
    openAddonPickerModal(product);
    return;
  }
  addProductToCart(product);
});

receiptOrdersList.addEventListener("click", (e) => {
  const card = e.target.closest(".receipt-order-card");
  if (!card) return;
  selectedOrder = receiptOpenOrders.find((o) => o.client_id === card.dataset.id) || null;
  renderOpenOrdersList();
  renderReceiptPanel();
});

clearBtn.addEventListener("click", () => {
  cart.clear();
  renderCart();
});

cancelOrderBtn?.addEventListener("click", () => {
  cancelSelectedOrder();
});

checkoutBtn.addEventListener("click", async () => {
  if (posMode === "receipt") await paySelectedOrder();
  else await placeOrder();
});

syncBtn.addEventListener("click", async () => {
  syncBtn.disabled = true;
  const result = await runFullSyncIfOnline(session, { silent: false });
  if (result.synced) {
    await loadCatalog();
  }
  await updateSyncBadge();
  syncBtn.disabled = false;
});

dayendBtn.addEventListener("click", async () => {
  if (!isBrowserOnline()) {
    showToast("Day-end cash-up with expenses requires an online connection.", true);
    return;
  }
  const reachable = await checkServerReachable(session);
  if (!reachable) {
    showToast("Cannot reach server for day-end report.", true);
    return;
  }
  await openDayEndModal(getTodayISO());
});

expenseBtn?.addEventListener("click", async () => {
  if (!isBrowserOnline()) {
    showToast("Recording expenses requires an online connection.", true);
    return;
  }
  const reachable = await checkServerReachable(session);
  if (!reachable) {
    showToast("Cannot reach server to record expense.", true);
    return;
  }
  await loadSuppliers();
  openExpenseModal();
});

function getTodayISO() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function closeExpenseModal() {
  if (expenseModal) expenseModal.hidden = true;
}

function openExpenseModal() {
  const activeCurrencies = currencies.filter((c) => c.is_active);
  const activeSuppliers = suppliers.filter((s) => s.is_active);
  expenseDateInput.value = getTodayISO();
  expenseDescriptionInput.value = "";
  expenseAmountInput.value = "";
  expenseSupplierSelect.innerHTML = activeSuppliers.length
    ? `<option value="">None (optional)</option>${activeSuppliers.map((s) => `<option value="${s.id}">${s.name}</option>`).join("")}`
    : `<option value="">None (optional)</option>`;
  expenseCurrencySelect.innerHTML = activeCurrencies
    .map((currency) => {
      const label = currency.code || currency.name || `Currency ${currency.id}`;
      const symbol = currency.symbol ? ` (${currency.symbol})` : "";
      return `<option value="${currency.id}">${label}${symbol}</option>`;
    })
    .join("");
  if (baseCurrency) {
    expenseCurrencySelect.value = String(baseCurrency.id);
  } else if (activeCurrencies.length) {
    expenseCurrencySelect.value = String(activeCurrencies[0].id);
  }
  expenseModal.hidden = false;
  expenseDescriptionInput.focus();
}

async function saveExpense() {
  const description = (expenseDescriptionInput.value || "").trim();
  const amountRaw = (expenseAmountInput.value || "").trim();
  const expenseDate = (expenseDateInput.value || "").trim() || getTodayISO();
  const currencyId = expenseCurrencySelect.value;

  if (!description) {
    showToast("Enter a description", true);
    expenseDescriptionInput.focus();
    return;
  }
  if (!amountRaw) {
    showToast("Enter an amount", true);
    expenseAmountInput.focus();
    return;
  }
  const amount = Number(amountRaw);
  if (!Number.isFinite(amount) || amount <= 0) {
    showToast("Amount must be a positive number", true);
    expenseAmountInput.focus();
    return;
  }
  if (!currencyId) {
    showToast("Select a currency", true);
    return;
  }

  expenseSaveBtn.disabled = true;
  try {
    const payload = {
      branch: session.branch.id,
      expense_date: expenseDate,
      amount: amount.toFixed(2),
      currency: Number(currencyId),
      description,
    };
    if (expenseSupplierSelect.value) {
      payload.supplier = Number(expenseSupplierSelect.value);
    }
    await createExpense(session, payload);
    showToast("Expense recorded");
    closeExpenseModal();
  } catch (err) {
    showToast(err.message, true);
  } finally {
    expenseSaveBtn.disabled = false;
  }
}

function closeDayEndModal() {
  if (dayendModal) dayendModal.hidden = true;
}

function currencyCodeOf(currency) {
  return String(currency?.code || "").trim().toUpperCase();
}

function isFiscalBranchSession() {
  return Boolean(session?.branch?.fiscalization_enabled);
}

function dayEndCurrencyCodes(activeCurrencies) {
  return [...new Set(activeCurrencies.map(currencyCodeOf).filter(Boolean))].sort();
}

function renderDayEndCurrencyFields() {
  if (!dayendCurrencyFields) return;
  const activeCurrencies = currencies.filter((c) => c.is_active);
  const fiscal = isFiscalBranchSession();
  let visible = activeCurrencies;
  if (fiscal && dayendCurrencyCodeSelect) {
    const selectedCode = String(dayendCurrencyCodeSelect.value || "").trim().toUpperCase();
    visible = activeCurrencies.filter((c) => currencyCodeOf(c) === selectedCode);
  }
  dayendCurrencyFields.innerHTML = visible
    .map((currency) => {
      const label = currency.name || currency.code || `Currency ${currency.id}`;
      return `
        <div class="form-group" style="margin:0;">
          <label for="dayend-counted-${currency.id}">${label}</label>
          <input
            type="number"
            id="dayend-counted-${currency.id}"
            class="report-input"
            data-currency-id="${currency.id}"
            data-currency-code="${currencyCodeOf(currency)}"
            step="0.01"
            min="0"
            placeholder="Counted amount"
          >
        </div>`;
    })
    .join("") || `<p class="settings-hint" style="margin:0;">No currencies for this code.</p>`;
}

function setupDayEndCurrencyCodePicker(activeCurrencies) {
  const fiscal = isFiscalBranchSession();
  if (!dayendCodeGroup || !dayendCurrencyCodeSelect) {
    renderDayEndCurrencyFields();
    return;
  }
  if (!fiscal) {
    dayendCodeGroup.hidden = true;
    dayendCurrencyCodeSelect.innerHTML = "";
    renderDayEndCurrencyFields();
    return;
  }
  const codes = dayEndCurrencyCodes(activeCurrencies);
  dayendCodeGroup.hidden = false;
  const previous = String(dayendCurrencyCodeSelect.value || "").trim().toUpperCase();
  dayendCurrencyCodeSelect.innerHTML = codes
    .map((code) => `<option value="${code}">${code}</option>`)
    .join("");
  if (previous && codes.includes(previous)) {
    dayendCurrencyCodeSelect.value = previous;
  } else if (baseCurrency && codes.includes(currencyCodeOf(baseCurrency))) {
    dayendCurrencyCodeSelect.value = currencyCodeOf(baseCurrency);
  } else if (codes.length) {
    dayendCurrencyCodeSelect.value = codes[0];
  }
  renderDayEndCurrencyFields();
}

async function openDayEndModal(date) {
  const allowed = await ensureDailyStockTakeForDayEnd(date);
  if (!allowed) return;

  const activeCurrencies = currencies.filter((c) => c.is_active);
  dayendDateInput.value = date;
  setupDayEndCurrencyCodePicker(activeCurrencies);
  dayendModal.hidden = false;
  dayendDateInput.focus();
}

async function printDayEndCashUp() {
  const reportDate = (dayendDateInput.value || "").trim() || getTodayISO();
  const allowed = await ensureDailyStockTakeForDayEnd(reportDate);
  if (!allowed) {
    closeDayEndModal();
    return;
  }

  const counted = {};
  const countedCodes = new Set();
  const inputs = dayendCurrencyFields.querySelectorAll("input[data-currency-id]");
  for (const input of inputs) {
    const raw = (input.value || "").trim();
    if (!raw) continue;
    const parsed = Number(raw);
    const currencyId = input.dataset.currencyId;
    if (!Number.isFinite(parsed) || parsed < 0) {
      showToast(`Invalid amount for currency ${currencyId}`, true);
      return;
    }
    const code = String(input.dataset.currencyCode || "").trim().toUpperCase();
    if (code) countedCodes.add(code);
    counted[currencyId] = String(parsed);
  }
  if (isFiscalBranchSession() && countedCodes.size > 1) {
    showToast(
      `On fiscal branches, count only one currency code (${[...countedCodes].sort().join(" or ")}). Do not mix USD and ZWG.`,
      true,
    );
    return;
  }

  dayendPrintBtn.disabled = true;
  try {
    const response = await fetchDayEndReport(session, { date: reportDate, counted });
    const report = response.report || response;
    await printDayEndReport(session, report, { taxRate: inclusiveTaxRate });
    const orderCount = Number(report.order_count || report.orderCount || 0);
    const label = orderCount === 1 ? "1 order" : `${orderCount} orders`;
    showToast(`Day end report printed · ${label}`);
    closeDayEndModal();
  } catch (err) {
    showToast(err.message, true);
  } finally {
    dayendPrintBtn.disabled = false;
  }
}

expenseCloseBtn?.addEventListener("click", closeExpenseModal);
expenseCancelBtn?.addEventListener("click", closeExpenseModal);
expenseSaveBtn?.addEventListener("click", saveExpense);
expenseModal?.addEventListener("click", (event) => {
  if (event.target === expenseModal) closeExpenseModal();
});
dayendCloseBtn?.addEventListener("click", closeDayEndModal);
dayendCancelBtn?.addEventListener("click", closeDayEndModal);
dayendPrintBtn?.addEventListener("click", printDayEndCashUp);
dayendCurrencyCodeSelect?.addEventListener("change", () => renderDayEndCurrencyFields());
dayendDateInput?.addEventListener("change", async () => {
  if (dayendModal.hidden) return;
  const date = (dayendDateInput.value || "").trim() || getTodayISO();
  const allowed = await ensureDailyStockTakeForDayEnd(date);
  if (!allowed) closeDayEndModal();
});
dayendModal?.addEventListener("click", (event) => {
  if (event.target === dayendModal) closeDayEndModal();
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
    const table = orderType.value === "dine_in" ? tableNumber.value.trim() : "";
    const existingTableOrder = table ? openOrdersForTable(table)[0] : null;
    const order = await window.pos.createOrder({
      orderType: orderType.value,
      tableNumber: table,
      createdByName: session.user?.display_name || session.user?.username || "",
      items: [...cart.values()].map((item) => ({
        product_id: item.id,
        product_name: item.name,
        quantity: item.quantity,
        price: item.price,
        notes: item.notes || "",
        addons: item.addons || [],
      })),
    });
    cart.clear();
    renderCart();
    await updateSyncBadge();
    const addedToExisting =
      existingTableOrder && order.client_id === existingTableOrder.client_id;
    showToast(
      addedToExisting
        ? `Items added to order — ${money(order.total_amount)}`
        : `Order placed — ${money(order.total_amount)}`
    );
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

async function cancelSelectedOrder() {
  if (!selectedOrder) return;
  const label = orderDisplayLabel(selectedOrder);
  if (!window.confirm(`Cancel unpaid order ${label}?`)) return;

  cancelOrderBtn.disabled = true;
  try {
    if (shouldPayOrderOnline(selectedOrder)) {
      if (!isBrowserOnline()) {
        throw new Error("Cannot cancel this order while offline.");
      }
      const reachable = await checkServerReachable(session);
      if (!reachable) {
        throw new Error("Cannot reach server to cancel this order.");
      }
      await cancelServerOrder(session, selectedOrder.server_id);
      if (!selectedOrder.is_remote) {
        await window.pos.cancelOrder(selectedOrder.client_id);
      } else if (selectedOrder.table_number) {
        await window.pos.dismissLocalTableOrders(selectedOrder.table_number);
      }
    } else {
      await window.pos.cancelOrder(selectedOrder.client_id);
    }
    showToast(`Order ${label} cancelled`);
    selectedOrder = null;
    await loadOpenOrders();
    renderReceiptPanel();
  } catch (err) {
    showToast(err.message, true);
    cancelOrderBtn.disabled = Boolean(selectedOrder);
  }
}

async function paySelectedOrder() {
  if (!selectedOrder) return;
  const inclusiveTotal = getReceiptInclusiveTotal();
  const orderTotal = computeTaxBreakdown(inclusiveTotal).total;

  const payingFromAccount = paymentMethod === "account";

  if (payingFromAccount) {
    const customer = getCustomerById(receiptCustomerSelect.value);
    if (!customer) {
      showToast("Select a customer to pay from account", true);
      return;
    }
    if (Number(customer.account_balance) < orderTotal) {
      showToast(`Insufficient balance. Available: ${money(customer.account_balance)}`, true);
      return;
    }
    if (!shouldPayOrderOnline(selectedOrder) || !selectedOrder.server_id) {
      showToast("Customer account payment requires a synced online order.", true);
      return;
    }
  } else if (!selectedCurrencyId && !isSplitPaymentActive()) {
    showToast("Please select a payment currency", true);
    return;
  }

  let currency = null;
  let amountDue = null;
  let rate = null;
  let splitLines = [];

  if (!payingFromAccount) {
    if (isSplitPaymentActive()) {
      splitLines = getSplitPaymentLines();
      if (!splitLines.length) {
        showToast("Enter at least one currency amount, or turn off split payment", true);
        return;
      }
      const allocated = roundMoney(splitLines.reduce((sum, line) => sum + line.base_amount, 0));
      if (Math.abs(allocated - orderTotal) >= 0.005) {
        showToast(
          `Split payments must total ${money(orderTotal)} (now ${money(allocated)})`,
          true,
        );
        return;
      }
      currency = baseCurrency || splitLines[0].currency;
      amountDue = orderTotal;
      rate = 1;
    } else {
      const paymentInfo = computePaymentAmounts(orderTotal);
      ({ hasRate: rate, currency, amountDue, rate } = {
        hasRate: paymentInfo.hasRate,
        currency: paymentInfo.currency,
        amountDue: paymentInfo.amountDue,
        rate: paymentInfo.rate,
      });
      if (!paymentInfo.hasRate) {
        showToast(`No exchange rate configured for ${currency?.name || "this currency"}`, true);
        return;
      }
    }
  } else {
    currency = baseCurrency;
    amountDue = orderTotal;
    rate = 1;
  }

  checkoutBtn.disabled = true;
  try {
    const localReceipt = `LOC-${session.branch.code || "POS"}-${Date.now().toString(36).toUpperCase()}`;
    const payments = payingFromAccount
      ? []
      : splitLines.length
        ? splitLines.map((line) => ({
            currency_id: line.currency_id,
            amount: Number(line.amount.toFixed(2)),
          }))
        : [{ currency_id: selectedCurrencyId, amount: Number(amountDue.toFixed(2)) }];
    const paymentMethodValue = payingFromAccount
      ? "account"
      : payments.length > 1
        ? "multi"
        : "cash";
    const paymentRecord = {
      currencyId: payingFromAccount
        ? baseCurrency?.id || null
        : splitLines.length
          ? baseCurrency?.id || payments[0].currency_id
          : selectedCurrencyId,
      exchangeRate: rate,
      amountPaid: amountDue,
      receiptNumber: localReceipt,
      paidByName: session.user?.display_name || session.user?.username || "",
      paymentMethod: paymentMethodValue,
      payments,
    };

    let order;
    if (payingFromAccount || shouldPayOrderOnline(selectedOrder)) {
      if (!isBrowserOnline()) {
        throw new Error("Connect to the server to collect payment for this order.");
      }
      const reachable = await checkServerReachable(session);
      if (!reachable) {
        throw new Error("Cannot reach server to collect payment for this order.");
      }

      let payPayload;
      if (payingFromAccount) {
        const customerId = Number(receiptCustomerSelect.value);
        if (Number(selectedOrder.customer) !== customerId) {
          await linkCustomerToOrder(selectedOrder.server_id, customerId);
          selectedOrder.customer = customerId;
        }
        payPayload = { payment_method: "account" };
      } else if (splitLines.length) {
        payPayload = {
          payment_method: paymentMethodValue,
          payments: splitLines.map((line) => ({
            currency_id: line.currency_id,
            amount: line.amount.toFixed(2),
          })),
        };
      } else {
        payPayload = {
          currency_id: selectedCurrencyId,
          payment_method: "cash",
        };
      }

      const apiOrder = await payServerOrder(session, selectedOrder.server_id, payPayload);
      order =
        (await window.pos.syncLocalPaymentFromServer(selectedOrder.server_id, {
          ...paymentRecord,
          receiptNumber: apiOrder.receipt_number || localReceipt,
          amountPaid: Number(apiOrder.amount_paid || amountDue),
          exchangeRate: apiOrder.exchange_rate || rate,
        })) || mapApiOrderForPrint(apiOrder, paymentRecord);
      if (selectedOrder.is_remote && selectedOrder.table_number) {
        await window.pos.dismissLocalTableOrders(selectedOrder.table_number);
      }
      if (payingFromAccount) {
        const customer = getCustomerById(receiptCustomerSelect.value);
        if (customer && apiOrder.customer_account_balance != null) {
          customer.account_balance = apiOrder.customer_account_balance;
          renderCustomerSelect();
          receiptCustomerSelect.value = String(customer.id);
        }
        showToast(
          `Paid from account ${money(orderTotal)} · ${order.receipt_number || apiOrder.receipt_number || orderDisplayLabel(selectedOrder)}`
        );
      } else {
        showToast(
          `Paid ${money(order.amount_paid || apiOrder.amount_paid, currency)} · ${order.receipt_number || apiOrder.receipt_number || orderDisplayLabel(selectedOrder)}`
        );
      }
    } else {
      order = await window.pos.payOrder(selectedOrder.client_id, paymentRecord);
      showToast(`Paid ${money(order.amount_paid, currency)} · ${localReceipt}`);
    }

    try {
      await printSalesReceipt(session, order, {
        currency,
        taxRate: inclusiveTaxRate,
        payments,
      });
    } catch (printErr) {
      showToast(`Payment saved but print failed: ${printErr.message}`, true);
    }
    selectedOrder = null;
    receiptPaymentOrderKey = null;
    setSplitPaymentEnabled(false);
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
    if (selectedOrder) {
      updateCheckoutButtonState(getReceiptInclusiveTotal());
    }
  }
}

async function loadSuppliers() {
  if (!session?.serverUrl || !session?.token || !isBrowserOnline()) {
    suppliers = [];
    return;
  }
  try {
    const data = await fetchSuppliers(session);
    suppliers = Array.isArray(data?.results) ? data.results : Array.isArray(data) ? data : [];
  } catch {
    suppliers = [];
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
  updateReceiptModeVisibility();

  await loadCatalog();
  await loadDiningTables();
  await loadOpenOrders();
  renderCart();
  await updateSyncBadge();
  window.addEventListener("offline", updateSyncBadge);
  stopAutoSync = startAutoSync(session, {
    onSyncComplete: async () => {
      await loadCatalog();
    },
    onSyncFinished: async () => {
      await updateSyncBadge();
      await loadOpenOrders();
    },
  });
}

init().catch((err) => showToast(`Failed to start POS: ${err.message}`, true));
