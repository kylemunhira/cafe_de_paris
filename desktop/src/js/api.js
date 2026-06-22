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
