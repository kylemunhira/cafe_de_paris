const API_BASE = "/api";

function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta?.content) return meta.content;

  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function mutationHeaders(extra = {}) {
  const headers = { ...extra };
  const token = csrfToken();
  if (token) headers["X-CSRFToken"] = token;
  return headers;
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

export async function apiGet(endpoint, { cache = "default" } = {}) {
  const res = await fetch(`${API_BASE}${endpoint}`, { cache });
  return parseResponse(res);
}

export async function apiPost(endpoint, body) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: mutationHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  return parseResponse(res);
}

export async function apiPatch(endpoint, body) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "PATCH",
    headers: mutationHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  return parseResponse(res);
}

export async function apiDelete(endpoint) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "DELETE",
    headers: mutationHeaders(),
  });
  if (res.status === 204) return null;
  return parseResponse(res);
}

export async function apiUpload(endpoint, formData) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: mutationHeaders(),
    body: formData,
  });
  return parseResponse(res);
}

export function unwrapList(data) {
  return data?.results ?? data ?? [];
}

function apiPathFromNext(nextUrl) {
  const url = new URL(nextUrl, window.location.origin);
  return `${url.pathname.replace(/^\/api/, "")}${url.search}`;
}

/** Fetch every page from a paginated list endpoint. */
export async function fetchAllPages(endpoint, params = {}) {
  const query = new URLSearchParams({ page_size: "1000", ...params });
  let next = `${endpoint}?${query}`;
  const results = [];

  while (next) {
    const data = await apiGet(next);
    results.push(...unwrapList(data));
    next = data?.next ? apiPathFromNext(data.next) : null;
  }

  return results;
}

let cachedBaseCurrency = null;

/** Normalize a currency object or ISO code for formatting. */
function resolveCurrency(currency) {
  if (!currency) return null;
  if (typeof currency === "string") {
    return { code: currency.toUpperCase(), symbol: "" };
  }
  const code = (currency.code || "").toUpperCase();
  return {
    code: code || "",
    symbol: currency.symbol || "",
    name: currency.name || "",
  };
}

/**
 * Format an amount in the given currency (or base / USD fallback).
 * @param {number|string} amount
 * @param {object|string|null} [currency] - currency object `{code,symbol}` or ISO code
 */
export function formatCurrency(amount, currency = null) {
  const value = Number.isFinite(Number(amount)) ? Number(amount) : 0;
  const resolved = resolveCurrency(currency) || resolveCurrency(cachedBaseCurrency);
  const formatted = value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  if (resolved?.symbol) {
    return `${resolved.symbol}${formatted}`;
  }

  const code = resolved?.code;
  if (code && /^[A-Z]{3}$/.test(code)) {
    try {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: code,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(value);
    } catch {
      return `${code} ${formatted}`;
    }
  }

  if (code) return `${code} ${formatted}`;
  return formatted;
}

/** Cache / return the configured base currency for list UIs. */
export async function getBaseCurrency({ force = false } = {}) {
  if (cachedBaseCurrency && !force) return cachedBaseCurrency;
  try {
    const data = await apiGet("/currencies/?page_size=500");
    const currencies = unwrapList(data);
    cachedBaseCurrency = currencies.find((c) => c.is_base) || currencies.find((c) => c.is_active) || null;
  } catch {
    cachedBaseCurrency = null;
  }
  return cachedBaseCurrency;
}

export function setBaseCurrency(currency) {
  cachedBaseCurrency = currency || null;
}

export function formatDate(iso) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}

export function statusBadge(status) {
  const map = {
    open: "badge-open",
    paid: "badge-paid",
    cancelled: "badge-cancelled",
    requested: "badge-requested",
    approved: "badge-approved",
    dispatched: "badge-dispatched",
    delivered: "badge-delivered",
    draft: "badge-open",
    submitted: "badge-requested",
    received: "badge-delivered",
    pending: "badge-open",
    preparing: "badge-requested",
    ready: "badge-delivered",
    unpaid: "badge-unpaid",
  };
  return `<span class="badge ${map[status] || ""}">${status}</span>`;
}

export function kitchenStatusBadge(status) {
  const labels = {
    pending: "New",
    preparing: "Preparing",
    ready: "Ready",
  };
  return statusBadge(status).replace(`>${status}<`, `>${labels[status] || status}<`);
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
