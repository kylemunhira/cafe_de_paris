export async function desktopLogin(serverUrl, username, password) {
  const base = serverUrl.replace(/\/$/, "");
  const res = await fetch(`${base}/api/auth/desktop-login/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ server_url: base, username, password }),
  });
  return parseResponse(res);
}

export async function syncPull(serverUrl, token) {
  const base = serverUrl.replace(/\/$/, "");
  const res = await fetch(`${base}/api/sync/pull/`, {
    headers: { Authorization: `Token ${token}` },
  });
  return parseResponse(res);
}

export async function syncPush(serverUrl, token, orders) {
  const base = serverUrl.replace(/\/$/, "");
  const res = await fetch(`${base}/api/sync/push/`, {
    method: "POST",
    headers: {
      Authorization: `Token ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ orders }),
  });
  return parseResponse(res);
}

export async function fetchOpenOrders(serverUrl, token, branchId) {
  const base = serverUrl.replace(/\/$/, "");
  const res = await fetch(
    `${base}/api/orders/?status=open&branch=${branchId}&page_size=500`,
    {
      headers: { Authorization: `Token ${token}` },
    }
  );
  return parseResponse(res);
}

async function authedRequest(session, path, { method = "GET", body } = {}) {
  if (!session?.serverUrl || !session?.token) {
    throw new Error("Sign in and connect to the server first.");
  }
  const base = session.serverUrl.replace(/\/$/, "");
  const res = await fetch(`${base}/api${path}`, {
    method,
    headers: {
      Authorization: `Token ${session.token}`,
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return parseResponse(res);
}

export function fetchFiscalDayStatus(session, branchId) {
  return authedRequest(session, `/branches/${branchId}/fiscal-day/status/`);
}

export function openFiscalDay(session, branchId) {
  return authedRequest(session, `/branches/${branchId}/fiscal-day/open/`, {
    method: "POST",
    body: {},
  });
}

export function closeFiscalDay(session, branchId) {
  return authedRequest(session, `/branches/${branchId}/fiscal-day/close/`, {
    method: "POST",
    body: {},
  });
}

export function fetchStockTakeDayEndCheck(session, branchId, date) {
  const query = new URLSearchParams({
    branch: String(branchId),
    date: date || new Date().toISOString().slice(0, 10),
  });
  return authedRequest(session, `/stock-takes/day-end-check/?${query.toString()}`);
}

export function fetchDiningTables(session, branchId) {
  return authedRequest(
    session,
    `/dining-tables/?branch=${branchId}&active_only=true&page_size=500`
  );
}

export function createDiningTable(session, payload) {
  return authedRequest(session, "/dining-tables/", { method: "POST", body: payload });
}

export function updateDiningTable(session, tableId, payload) {
  return authedRequest(session, `/dining-tables/${tableId}/`, {
    method: "PATCH",
    body: payload,
  });
}

async function parseResponse(res) {
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    const message =
      data?.detail ||
      (typeof data === "object" ? JSON.stringify(data) : text) ||
      res.statusText;
    throw new Error(message);
  }
  return data;
}

export function formatCurrency(amount, symbol = "$") {
  const value = Number(amount);
  const formatted = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(value) ? value : 0);
  return `${symbol}${formatted}`;
}

export function formatDate(iso) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}

export function showToast(message, isError = false) {
  let container = document.querySelector(".toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = `toast${isError ? " error" : ""}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3500);
}

export function kitchenStatusBadge(status) {
  const labels = {
    pending: "New",
    preparing: "Preparing",
    ready: "Ready",
  };
  const classes = {
    pending: "badge-open",
    preparing: "badge-requested",
    ready: "badge-delivered",
  };
  const label = labels[status] || status || "New";
  const className = classes[status] || "badge-open";
  return `<span class="badge ${className}">${label}</span>`;
}
