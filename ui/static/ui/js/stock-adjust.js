/** Shared helpers for quick branch stock Add / Set. */

export function formatStockQty(value) {
  const qty = Number(value);
  return Number.isFinite(qty)
    ? qty.toLocaleString("en-US", { maximumFractionDigits: 2 })
    : "0";
}

function formatDelta(value) {
  const qty = Number(value);
  if (!Number.isFinite(qty)) return "0";
  const formatted = qty.toLocaleString("en-US", { maximumFractionDigits: 2 });
  return qty > 0 ? `+${formatted}` : formatted;
}

function formatMovementWhen(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function referenceLabel(row) {
  if (!row.reference_type || !row.reference_id) return "";
  const type = String(row.reference_type).replace(/_/g, " ");
  return `${type} #${row.reference_id}`;
}

/**
 * Apply a stock change for one product at a branch.
 * @param {Function} apiPost
 * @param {{ branchId: number, productId: number, mode: "add"|"set", amount: string|number }} opts
 */
export async function applyStockChange(apiPost, { branchId, productId, mode, amount }) {
  if (!branchId) {
    throw new Error("Select a branch before adjusting stock");
  }
  const qty = Number(amount);
  if (!Number.isFinite(qty)) {
    throw new Error("Enter a valid quantity");
  }

  if (mode === "set") {
    if (qty < 0) {
      throw new Error("Quantity cannot be negative");
    }
    return apiPost("/inventory/set/", {
      branch: branchId,
      product: productId,
      quantity: qty,
    });
  }

  if (qty === 0) {
    throw new Error("Add amount must not be zero");
  }
  if (qty < 0) {
    throw new Error("Add amount must be positive");
  }
  return apiPost("/inventory/adjust/", {
    branch: branchId,
    product: productId,
    delta: qty,
  });
}

/**
 * Compact inline Add/Set control for list/card rows.
 * @param {{ productId: number|string, disabled?: boolean }} opts
 */
export function stockAdjustInlineHtml({ productId, disabled = false }) {
  const disabledAttr = disabled ? "disabled" : "";
  return `
    <div class="stock-adjust-inline" data-product-id="${productId}">
      <select class="stock-adjust-inline__mode" data-stock-mode aria-label="Stock mode" ${disabledAttr}>
        <option value="add">Add</option>
        <option value="set">Set</option>
      </select>
      <input
        type="number"
        class="stock-adjust-inline__qty"
        data-stock-qty
        min="0"
        step="0.01"
        placeholder="Qty"
        aria-label="Quantity"
        ${disabledAttr}
      >
      <button type="button" class="btn btn-primary btn-sm" data-apply-stock ${disabledAttr}>Apply</button>
    </div>
  `;
}

/**
 * Handle click on [data-apply-stock] within a container.
 * Returns null if the click was not on an apply button.
 */
export async function handleInlineStockApply(event, {
  apiPost,
  branchId,
  getCurrentQty,
  onSuccess,
}) {
  const btn = event.target.closest("[data-apply-stock]");
  if (!btn) return null;

  const wrap = btn.closest(".stock-adjust-inline");
  if (!wrap) return null;

  const productId = Number(wrap.dataset.productId);
  const mode = wrap.querySelector("[data-stock-mode]")?.value || "add";
  const amount = wrap.querySelector("[data-stock-qty]")?.value;

  btn.disabled = true;
  try {
    const result = await applyStockChange(apiPost, {
      branchId,
      productId,
      mode,
      amount,
    });
    const qtyInput = wrap.querySelector("[data-stock-qty]");
    if (qtyInput) qtyInput.value = "";
    if (onSuccess) {
      await onSuccess(productId, Number(result.quantity), result);
    }
    return result;
  } finally {
    btn.disabled = false;
  }
}

function ensureMovementModal() {
  let modal = document.getElementById("stock-movement-modal");
  if (modal) return modal;

  modal = document.createElement("div");
  modal.id = "stock-movement-modal";
  modal.style.cssText = "display:none; position:fixed; inset:0; background:rgba(15,23,42,0.45); z-index:1000; align-items:center; justify-content:center; padding:1rem;";
  modal.innerHTML = `
    <div class="card" style="width:min(720px, 100%); max-height:90vh; overflow:auto; padding:1rem 1rem 1.25rem;">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:0.75rem; margin-bottom:0.75rem;">
        <div>
          <h3 id="stock-movement-title" style="margin:0; font-size:1.05rem;">Stock movements</h3>
          <p id="stock-movement-subtitle" style="margin:0.25rem 0 0; font-size:0.85rem; color:var(--color-muted);"></p>
        </div>
        <button type="button" class="btn btn-ghost btn-sm" id="stock-movement-close-btn">Close</button>
      </div>
      <div id="stock-movement-body">
        <div style="padding:1.5rem; text-align:center;"><span class="loading-spinner"></span></div>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  const close = () => {
    modal.style.display = "none";
  };
  modal.querySelector("#stock-movement-close-btn").addEventListener("click", close);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) close();
  });
  return modal;
}

/**
 * Open a modal listing stock movements for one product at a branch.
 */
export async function openStockMovementHistory({
  apiGet,
  unwrapList,
  branchId,
  productId,
  productName = "Product",
  branchName = "Branch",
}) {
  if (!branchId || !productId) {
    throw new Error("Select a branch and product to view movements");
  }

  const modal = ensureMovementModal();
  const title = modal.querySelector("#stock-movement-title");
  const subtitle = modal.querySelector("#stock-movement-subtitle");
  const body = modal.querySelector("#stock-movement-body");
  title.textContent = productName;
  subtitle.textContent = `Stock movements at ${branchName}`;
  body.innerHTML = `<div style="padding:1.5rem; text-align:center;"><span class="loading-spinner"></span></div>`;
  modal.style.display = "flex";

  try {
    const data = await apiGet(
      `/inventory/movements/?branch=${encodeURIComponent(branchId)}&product=${encodeURIComponent(productId)}&page_size=100`,
    );
    const rows = unwrapList(data);
    if (!rows.length) {
      body.innerHTML = `<div class="empty-state"><p>No movements recorded yet for this product at this branch.</p></div>`;
      return;
    }

    body.innerHTML = `
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>When</th>
              <th>Reason</th>
              <th style="text-align:right;">Change</th>
              <th style="text-align:right;">Balance</th>
              <th>By</th>
              <th>Ref</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(row => `
              <tr>
                <td style="white-space:nowrap; font-size:0.85rem;">${formatMovementWhen(row.created_at)}</td>
                <td>
                  <div>${row.reason_display || row.reason}</div>
                  ${row.note ? `<div style="font-size:0.8rem; color:var(--color-muted);">${row.note}</div>` : ""}
                </td>
                <td style="text-align:right; font-weight:600; color:${Number(row.delta) < 0 ? "var(--color-danger, #b91c1c)" : "var(--color-espresso);"}">
                  ${formatDelta(row.delta)}
                </td>
                <td style="text-align:right;">${formatStockQty(row.quantity_after)}</td>
                <td style="font-size:0.85rem;">${row.created_by_name || "—"}</td>
                <td style="font-size:0.8rem; color:var(--color-muted);">${referenceLabel(row) || "—"}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  } catch (err) {
    body.innerHTML = `<div class="empty-state"><p>${err.message || "Failed to load movements"}</p></div>`;
    throw err;
  }
}
