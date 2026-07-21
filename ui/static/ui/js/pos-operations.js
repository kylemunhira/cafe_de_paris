import { apiGet, apiPatch, apiPost, showToast, unwrapList } from "./api.js";

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

export function initPosOperations({
  branchId,
  customers,
  currencies,
  onCustomerUpdated = () => {},
}) {
  const stockButton = document.getElementById("stock-take-btn");
  const paymentButton = document.getElementById("customer-payment-btn");
  const stockModal = document.getElementById("pos-stock-take-modal");
  const paymentModal = document.getElementById("pos-customer-payment-modal");
  const stockLines = document.getElementById("pos-stock-lines");
  const stockDate = document.getElementById("pos-stock-date");
  const stockType = document.getElementById("pos-stock-type");
  const stockTitle = document.getElementById("pos-stock-title");
  const stockStart = document.getElementById("pos-stock-start");
  const stockSave = document.getElementById("pos-stock-save");
  const stockComplete = document.getElementById("pos-stock-complete");
  const paymentCustomer = document.getElementById("pos-payment-customer");
  const paymentCurrency = document.getElementById("pos-payment-currency");
  const paymentAmount = document.getElementById("pos-payment-amount");
  const paymentNotes = document.getElementById("pos-payment-notes");
  const paymentBalance = document.getElementById("pos-payment-balance");
  const paymentSave = document.getElementById("pos-payment-save");
  let activeStockTake = null;

  const close = (modal) => {
    if (modal) modal.style.display = "none";
  };
  const open = (modal) => {
    if (modal) modal.style.display = "flex";
  };

  document.querySelectorAll("[data-close-pos-modal]").forEach((button) => {
    button.addEventListener("click", () => close(button.closest(".pos-operation-modal")));
  });
  [stockModal, paymentModal].forEach((modal) => {
    modal?.addEventListener("click", (event) => {
      if (event.target === modal) close(modal);
    });
  });

  function currentBranchId() {
    const value = Number(branchId());
    if (!value) {
      showToast("Select a branch first", true);
      return null;
    }
    return value;
  }

  function stockPayload() {
    return {
      lines: Array.from(stockLines.querySelectorAll("[data-stock-line]")).map((input) => ({
        id: Number(input.dataset.stockLine),
        counted_quantity: input.value === "" ? null : input.value,
        notes: "",
      })),
    };
  }

  function renderStockTake(stockTake) {
    activeStockTake = stockTake;
    stockTitle.textContent = `${stockTake.stock_take_type_display || stockTake.stock_take_type} count · ${stockTake.count_date}`;
    stockLines.innerHTML = (stockTake.lines || []).map((line) => `
      <div style="display:grid; grid-template-columns:minmax(180px,1fr) 130px; gap:0.75rem; align-items:center; padding:0.55rem 0; border-bottom:1px solid rgba(44,24,16,0.08);">
        <div>
          <strong>${escapeHtml(line.product_name)}</strong>
          <small style="display:block; color:var(--color-muted);">${escapeHtml(line.category_name || "")}</small>
        </div>
        <input type="number" min="0" step="0.01" data-stock-line="${line.id}" value="${line.counted_quantity ?? ""}" placeholder="Counted">
      </div>
    `).join("") || `<p class="empty-state">No products are configured for this count.</p>`;
    stockStart.style.display = "none";
    stockSave.style.display = "";
    stockComplete.style.display = "";
  }

  async function loadDraft() {
    const branch = currentBranchId();
    if (!branch) return;
    const date = stockDate.value;
    const type = stockType.value;
    const periodDate = type === "monthly" ? `${date.slice(0, 7)}-01` : date;
    const data = await apiGet(`/stock-takes/?branch=${branch}&stock_take_type=${type}&status=draft&page_size=100`);
    const draft = unwrapList(data).find((item) => item.count_date === periodDate);
    if (draft) {
      renderStockTake(await apiGet(`/stock-takes/${draft.id}/`));
      return true;
    }
    activeStockTake = null;
    stockTitle.textContent = "Start stock take";
    stockLines.innerHTML = `<p class="empty-state">Choose the count type and start a count.</p>`;
    stockStart.style.display = "";
    stockSave.style.display = "none";
    stockComplete.style.display = "none";
    return false;
  }

  stockButton?.addEventListener("click", async () => {
    if (!currentBranchId()) return;
    stockDate.value = new Date().toISOString().slice(0, 10);
    open(stockModal);
    try {
      await loadDraft();
    } catch (error) {
      showToast(error.message, true);
    }
  });
  stockDate?.addEventListener("change", () => loadDraft().catch((error) => showToast(error.message, true)));
  stockType?.addEventListener("change", () => loadDraft().catch((error) => showToast(error.message, true)));
  stockStart?.addEventListener("click", async () => {
    const branch = currentBranchId();
    if (!branch) return;
    stockStart.disabled = true;
    try {
      renderStockTake(await apiPost("/stock-takes/", {
        branch,
        stock_take_type: stockType.value,
        count_date: stockDate.value,
      }));
    } catch (error) {
      showToast(error.message, true);
    } finally {
      stockStart.disabled = false;
    }
  });
  stockSave?.addEventListener("click", async () => {
    if (!activeStockTake) return;
    stockSave.disabled = true;
    try {
      renderStockTake(await apiPatch(`/stock-takes/${activeStockTake.id}/lines/`, stockPayload()));
      showToast("Stock count saved");
    } catch (error) {
      showToast(error.message, true);
    } finally {
      stockSave.disabled = false;
    }
  });
  stockComplete?.addEventListener("click", async () => {
    if (!activeStockTake) return;
    stockComplete.disabled = true;
    try {
      await apiPatch(`/stock-takes/${activeStockTake.id}/lines/`, stockPayload());
      await apiPost(`/stock-takes/${activeStockTake.id}/complete/`, {});
      showToast("Stock take completed and variances posted");
      close(stockModal);
      activeStockTake = null;
    } catch (error) {
      showToast(error.message, true);
    } finally {
      stockComplete.disabled = false;
    }
  });

  function renderPaymentOptions() {
    const customerList = customers();
    const currencyList = currencies().filter((currency) => currency.is_active);
    paymentCustomer.innerHTML = `<option value="">Select customer…</option>${customerList.map((customer) =>
      `<option value="${customer.id}">${escapeHtml(customer.full_name || `${customer.first_name} ${customer.last_name || ""}`.trim())}</option>`
    ).join("")}`;
    paymentCurrency.innerHTML = currencyList.map((currency) =>
      `<option value="${currency.id}">${escapeHtml(currency.code || currency.name)}</option>`
    ).join("");
    const base = currencyList.find((currency) => currency.is_base) || currencyList[0];
    if (base) paymentCurrency.value = String(base.id);
  }

  function updatePaymentBalance() {
    const customer = customers().find((item) => item.id === Number(paymentCustomer.value));
    paymentBalance.textContent = customer
      ? `Current balance: ${Number(customer.account_balance || 0).toFixed(2)}`
      : "Select a customer";
  }

  paymentButton?.addEventListener("click", () => {
    if (!currentBranchId()) return;
    renderPaymentOptions();
    paymentAmount.value = "";
    paymentNotes.value = "";
    updatePaymentBalance();
    open(paymentModal);
  });
  paymentCustomer?.addEventListener("change", updatePaymentBalance);
  paymentSave?.addEventListener("click", async () => {
    const branch = currentBranchId();
    const customerId = Number(paymentCustomer.value);
    const amount = Number(paymentAmount.value);
    if (!branch || !customerId) return showToast("Select a customer", true);
    if (!Number.isFinite(amount) || amount <= 0) return showToast("Enter a valid amount", true);
    paymentSave.disabled = true;
    try {
      const result = await apiPost(`/customers/${customerId}/deposit/`, {
        branch,
        currency_id: Number(paymentCurrency.value),
        amount: amount.toFixed(2),
        notes: paymentNotes.value.trim(),
      });
      onCustomerUpdated(customerId, result.account_balance);
      showToast("Customer payment recorded");
      close(paymentModal);
      if (result.transaction?.id) {
        window.open(`/customer-account-transactions/${result.transaction.id}/print/?auto=1`, "_blank", "noopener");
      }
    } catch (error) {
      showToast(error.message, true);
    } finally {
      paymentSave.disabled = false;
    }
  });

  return {
    openStockTake: () => stockButton?.click(),
  };
}
