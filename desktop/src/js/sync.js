import { syncPull, syncPush, fetchOpenOrders, showToast } from "./api.js";

const PING_TIMEOUT_MS = 5000;
const AUTO_SYNC_INTERVAL_MS = 30000;
const KITCHEN_REFRESH_INTERVAL_MS = 15000;

let syncing = false;

export function isBrowserOnline() {
  return navigator.onLine;
}

export async function checkServerReachable(session) {
  if (!navigator.onLine || !session?.serverUrl || !session?.token) {
    return false;
  }

  const base = session.serverUrl.replace(/\/$/, "");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PING_TIMEOUT_MS);

  try {
    const res = await fetch(`${base}/api/sync/ping/`, {
      headers: { Authorization: `Token ${session.token}` },
      signal: controller.signal,
    });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export async function pullCatalog(session) {
  const data = await syncPull(session.serverUrl, session.token);
  await window.pos.replaceCatalog({
    categories: data.categories,
    products: data.products,
    currencies: data.currencies,
    dining_tables: data.dining_tables || [],
  });
  if (data.inclusive_tax_rate != null) {
    await window.pos.setSetting("inclusive_tax_rate", data.inclusive_tax_rate);
  }
  return data;
}

export function buildPushPayload(order) {
  const payload = {
    client_id: order.client_id,
    order_type: order.order_type,
    table_number: order.table_number || "",
    created_at: order.created_at,
    items: order.items.map((item) => ({
      product_id: item.product_id,
      quantity: String(item.quantity),
    })),
  };
  if (order.status === "paid" && order.payment_currency_id) {
    payload.payment = {
      currency_id: order.payment_currency_id,
      paid_at: order.paid_at,
    };
  }
  return payload;
}

export async function pushPendingOrders(session) {
  const pending = await window.pos.listPendingSyncOrders();
  if (!pending.length) return { pushed: 0 };

  const payload = pending.map(buildPushPayload);
  const response = await syncPush(session.serverUrl, session.token, payload);

  for (const result of response.results) {
    await window.pos.markOrderSynced(result.client_id, {
      serverId: result.server_id,
      receiptNumber: result.receipt_number,
      kitchenStatus: result.kitchen_status,
    });
  }

  return { pushed: response.results.length };
}

export async function pullKitchenStatus(session) {
  if (!session?.branch?.id || !session?.serverUrl || !session?.token) {
    return { updated: 0 };
  }

  const data = await fetchOpenOrders(
    session.serverUrl,
    session.token,
    session.branch.id
  );
  const orders = Array.isArray(data?.results) ? data.results : Array.isArray(data) ? data : [];
  const updates = orders.map((order) => ({
    server_id: order.id,
    kitchen_status: order.kitchen_status || "pending",
    kitchen_started_at: order.kitchen_started_at,
    kitchen_ready_at: order.kitchen_ready_at,
  }));

  const updated = updates.length
    ? await window.pos.updateKitchenStatuses(updates)
    : 0;
  return { updated };
}

export async function runFullSync(session, { silent = false } = {}) {
  await pullCatalog(session);
  const { pushed } = await pushPendingOrders(session);
  await pullKitchenStatus(session);
  if (!silent) {
    const msg =
      pushed > 0
        ? `Synced catalog and uploaded ${pushed} order(s).`
        : "Catalog updated. No pending orders.";
    showToast(msg);
  }
  return { pushed };
}

export async function runFullSyncIfOnline(session, options = {}) {
  if (!navigator.onLine) {
    return { synced: false, reason: "offline" };
  }

  const reachable = await checkServerReachable(session);
  if (!reachable) {
    return { synced: false, reason: "server_unreachable" };
  }

  if (syncing) {
    return { synced: false, reason: "in_progress" };
  }

  syncing = true;
  try {
    const result = await runFullSync(session, options);
    return { synced: true, ...result };
  } catch (err) {
    if (!options.silent) {
      showToast(`Sync failed: ${err.message}`, true);
    }
    return { synced: false, reason: "error", error: err };
  } finally {
    syncing = false;
  }
}

/**
 * Sync when the network/server is available: on startup, when browser goes
 * online, and on a periodic retry interval.
 */
export function startAutoSync(session, { onSyncComplete } = {}) {
  const trySync = async () => {
    const result = await runFullSyncIfOnline(session, { silent: true });
    if (result.synced && onSyncComplete) {
      await onSyncComplete(result);
    }
    return result;
  };

  const onOnline = () => trySync();

  window.addEventListener("online", onOnline);
  trySync();

  const interval = setInterval(trySync, AUTO_SYNC_INTERVAL_MS);

  return () => {
    clearInterval(interval);
    window.removeEventListener("online", onOnline);
  };
}

export function startKitchenRefresh(session, { onRefresh } = {}) {
  const refresh = async () => {
    if (!navigator.onLine) return;
    const reachable = await checkServerReachable(session);
    if (!reachable) return;
    try {
      await pullKitchenStatus(session);
      if (onRefresh) await onRefresh();
    } catch {
      // Kitchen status refresh is best-effort.
    }
  };

  refresh();
  const interval = setInterval(refresh, KITCHEN_REFRESH_INTERVAL_MS);
  return () => clearInterval(interval);
}
