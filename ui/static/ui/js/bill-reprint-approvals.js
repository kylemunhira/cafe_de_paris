import { apiGet, apiPost, showToast, unwrapList } from "./api.js";

const t = (msgid) => window.CDP?.t?.(msgid) || msgid;

const POLL_MS = 3000;
const activeWaiters = new Map();
let managerPollTimer = null;
const dismissedRequestIds = new Set();

function orderSummary(request) {
  const parts = [`Order #${request.order_id}`];
  if (request.table_number) parts.push(`Table ${request.table_number}`);
  if (request.branch_name) parts.push(request.branch_name);
  return parts.join(" · ");
}

export function openBillPrintWindow(orderId) {
  const printUrl = `/pos/order/${orderId}/print/?auto=1&bill=1`;
  const printWindow = window.open(printUrl, "_blank");
  if (!printWindow) {
    window.open(printUrl, "_blank", "noopener");
  }
}

async function fetchBillReprintStatus(requestId, orderId) {
  if (orderId) {
    try {
      const orderStatus = await apiGet(`/orders/${orderId}/bill-reprint-status/`);
      if (orderStatus.has_request && orderStatus.id === requestId) {
        return orderStatus;
      }
    } catch {
      /* fall back to request detail */
    }
  }
  return apiGet(`/bill-reprint-requests/${requestId}/`);
}

export function waitForBillReprintApproval(requestId, { orderId, onApproved, onRejected, onPending } = {}) {
  if (activeWaiters.has(requestId)) {
    return activeWaiters.get(requestId);
  }

  let cancelled = false;
  const promise = new Promise((resolve, reject) => {
    const poll = async () => {
      if (cancelled) return;
      try {
        const request = await fetchBillReprintStatus(requestId, orderId);
        if (request.status === "approved") {
          activeWaiters.delete(requestId);
          onApproved?.(request);
          resolve(request);
          return;
        }
        if (request.status === "rejected") {
          activeWaiters.delete(requestId);
          onRejected?.(request);
          reject(new Error(t("Bill reprint was rejected by manager")));
          return;
        }
        if (request.status === "cancelled") {
          activeWaiters.delete(requestId);
          reject(new Error(t("Bill reprint request was cancelled")));
          return;
        }
        onPending?.(request);
        setTimeout(poll, 2000);
      } catch (err) {
        activeWaiters.delete(requestId);
        reject(err);
      }
    };
    poll();
  });

  promise.cancel = () => {
    cancelled = true;
    activeWaiters.delete(requestId);
  };

  activeWaiters.set(requestId, promise);
  return promise;
}

export async function requestBillPrint(orderId, payload = {}) {
  const res = await fetch(`/api/orders/${orderId}/print-bill/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": document.querySelector('meta[name="csrf-token"]')?.content || "",
    },
    body: JSON.stringify(payload),
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    throw new Error(text || res.statusText);
  }
  if (!res.ok && res.status !== 202) {
    const detail = data?.detail || res.statusText;
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }
  return { status: res.status, data };
}

function buildApprovalOverlay(request) {
  const overlay = document.createElement("div");
  overlay.className = "bill-reprint-approval-overlay";
  overlay.style.cssText =
    "position:fixed;inset:0;background:rgba(15,23,42,0.5);z-index:1200;display:flex;align-items:center;justify-content:center;padding:1rem;";
  overlay.dataset.requestId = String(request.id);
  overlay.innerHTML = `
    <div class="card" style="width:min(440px,100%);padding:1.25rem;">
      <h3 style="margin:0 0 0.5rem;font-size:1.05rem;">${t("Bill reprint approval")}</h3>
      <p style="margin:0 0 0.75rem;font-size:0.9rem;color:var(--color-muted);">
        ${t("A cashier requested to reprint a guest bill.")}
      </p>
      <div style="background:rgba(44,24,16,0.04);border-radius:8px;padding:0.75rem 1rem;margin-bottom:1rem;font-size:0.9rem;">
        <div><strong>${orderSummary(request)}</strong></div>
        <div style="margin-top:0.35rem;color:var(--color-muted);">
          ${t("Requested by")} ${request.requested_by_name || "—"}
        </div>
        <div style="margin-top:0.35rem;color:var(--color-muted);">
          ${t("Previous prints")}: ${request.bill_print_count || 0}
        </div>
      </div>
      <div style="display:flex;gap:0.5rem;justify-content:flex-end;flex-wrap:wrap;">
        <button type="button" class="btn btn-ghost" data-action="reject">${t("Reject")}</button>
        <button type="button" class="btn btn-primary" data-action="approve">${t("Approve reprint")}</button>
      </div>
    </div>
  `;
  return overlay;
}

function showManagerApprovalPopup(request) {
  if (dismissedRequestIds.has(request.id)) return;
  if (document.querySelector(`[data-request-id="${request.id}"]`)) return;

  const overlay = buildApprovalOverlay(request);
  document.body.appendChild(overlay);

  overlay.addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-action]");
    if (!btn) return;
    const action = btn.dataset.action;
    btn.disabled = true;
    overlay.querySelectorAll("button").forEach((el) => {
      el.disabled = true;
    });
    try {
      if (action === "approve") {
        await apiPost(`/bill-reprint-requests/${request.id}/approve/`, {});
        showToast(`${t("Bill reprint approved for order")} #${request.order_id}`);
      } else {
        await apiPost(`/bill-reprint-requests/${request.id}/reject/`, {});
        showToast(`${t("Bill reprint rejected for order")} #${request.order_id}`);
      }
      dismissedRequestIds.add(request.id);
      overlay.remove();
    } catch (err) {
      showToast(err.message, true);
      overlay.querySelectorAll("button").forEach((el) => {
        el.disabled = false;
      });
    }
  });
}

async function pollPendingApprovals() {
  try {
    const pending = unwrapList(await apiGet("/bill-reprint-requests/?status=pending"));
    pending.forEach((request) => showManagerApprovalPopup(request));
  } catch {
    /* ignore transient network errors */
  }
}

export function startManagerBillReprintPolling() {
  if (managerPollTimer) return;
  pollPendingApprovals();
  managerPollTimer = window.setInterval(pollPendingApprovals, POLL_MS);
}

export function showBillReprintPendingDialog(requestId, orderId) {
  return new Promise((resolve, reject) => {
    const overlay = document.createElement("div");
    overlay.style.cssText =
      "position:fixed;inset:0;background:rgba(15,23,42,0.45);z-index:1100;display:flex;align-items:center;justify-content:center;padding:1rem;";
    overlay.innerHTML = `
      <div class="card" style="width:min(420px,100%);padding:1.25rem;text-align:center;">
        <h3 style="margin:0 0 0.5rem;">${t("Approval pending")}</h3>
        <p style="margin:0 0 1rem;font-size:0.9rem;color:var(--color-muted);">
          ${t("Waiting for a manager to approve this bill reprint from the portal.")}
        </p>
        <span class="loading-spinner"></span>
        <div style="margin-top:1rem;">
          <button type="button" class="btn btn-ghost" data-action="cancel">${t("Cancel")}</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const waiter = waitForBillReprintApproval(requestId, {
      orderId,
      onApproved: (request) => {
        overlay.remove();
        resolve(request);
      },
      onRejected: (request) => {
        overlay.remove();
        reject(new Error(t("Bill reprint was rejected by manager")));
      },
    });

    overlay.querySelector("[data-action=cancel]")?.addEventListener("click", async () => {
      waiter.cancel?.();
      try {
        await apiPost(`/bill-reprint-requests/${requestId}/cancel/`, {});
      } catch {
        /* ignore */
      }
      overlay.remove();
      reject(new Error(t("Bill reprint request cancelled")));
    });
  });
}

export async function printBillWithApproval(orderId, { payload = {}, billPrintCount = 0 } = {}) {
  const { status, data } = await requestBillPrint(orderId, payload);
  if (status === 202 || data?.approval_required) {
    await showBillReprintPendingDialog(data.id, orderId);
    openBillPrintWindow(orderId);
    return { ...data, bill_print_count: (billPrintCount || 0) + 1 };
  }
  openBillPrintWindow(orderId);
  return data;
}
