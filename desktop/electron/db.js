const Database = require("better-sqlite3");
const path = require("path");
const { app } = require("electron");
const crypto = require("crypto");

let db;

function getDbPath() {
  return path.join(app.getPath("userData"), "pos.sqlite3");
}

function initDb() {
  db = new Database(getDbPath());
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");

  db.exec(`
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS categories (
      id INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      is_asset INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS products (
      id INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      category_id INTEGER,
      category_name TEXT,
      selling_price REAL NOT NULL,
      is_active INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS currencies (
      id INTEGER PRIMARY KEY,
      code TEXT,
      name TEXT NOT NULL,
      symbol TEXT,
      is_base INTEGER NOT NULL DEFAULT 0,
      is_active INTEGER NOT NULL DEFAULT 1,
      current_rate TEXT
    );

    CREATE TABLE IF NOT EXISTS dining_tables (
      id INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      sort_order INTEGER NOT NULL DEFAULT 0,
      is_active INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS orders (
      client_id TEXT PRIMARY KEY,
      server_id INTEGER,
      order_type TEXT NOT NULL,
      table_number TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'open',
      total_amount REAL NOT NULL DEFAULT 0,
      payment_currency_id INTEGER,
      exchange_rate REAL,
      amount_paid REAL,
      receipt_number TEXT,
      sync_status TEXT NOT NULL DEFAULT 'pending',
      sync_error TEXT,
      created_at TEXT NOT NULL,
      paid_at TEXT
    );

    CREATE TABLE IF NOT EXISTS order_items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      order_client_id TEXT NOT NULL,
      product_id INTEGER NOT NULL,
      product_name TEXT NOT NULL,
      quantity REAL NOT NULL,
      price REAL NOT NULL,
      FOREIGN KEY (order_client_id) REFERENCES orders(client_id) ON DELETE CASCADE
    );
  `);

  ensureOrderColumn("kitchen_status", "TEXT NOT NULL DEFAULT 'pending'");
  ensureOrderColumn("kitchen_started_at", "TEXT");
  ensureOrderColumn("kitchen_ready_at", "TEXT");
  ensureOrderColumn("created_by_name", "TEXT NOT NULL DEFAULT ''");
  ensureOrderColumn("paid_by_name", "TEXT NOT NULL DEFAULT ''");
  ensureTableColumn("products", "addon_groups_json", "TEXT NOT NULL DEFAULT '[]'");
  ensureTableColumn("order_items", "notes", "TEXT NOT NULL DEFAULT ''");
  ensureTableColumn("order_items", "addons_json", "TEXT NOT NULL DEFAULT '[]'");
}

function ensureTableColumn(table, column, definition) {
  const columns = db.prepare(`PRAGMA table_info(${table})`).all();
  if (!columns.some((row) => row.name === column)) {
    db.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${definition}`);
  }
}

function ensureOrderColumn(column, definition) {
  const columns = db.prepare("PRAGMA table_info(orders)").all();
  if (!columns.some((row) => row.name === column)) {
    db.exec(`ALTER TABLE orders ADD COLUMN ${column} ${definition}`);
  }
}

function getSetting(key, defaultValue = null) {
  const row = db.prepare("SELECT value FROM settings WHERE key = ?").get(key);
  return row ? row.value : defaultValue;
}

function setSetting(key, value) {
  db.prepare(
    "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value"
  ).run(key, value);
}

function clearSession() {
  db.prepare("DELETE FROM settings WHERE key IN ('auth_token', 'user_json', 'branch_json')").run();
}

function saveSession({ token, user, branch, inclusiveTaxRate }) {
  setSetting("auth_token", token);
  setSetting("user_json", JSON.stringify(user));
  setSetting("branch_json", JSON.stringify(branch));
  if (inclusiveTaxRate != null) {
    setSetting("inclusive_tax_rate", String(inclusiveTaxRate));
  }
}

function getSession() {
  const token = getSetting("auth_token");
  if (!token) return null;
  return {
    token,
    user: JSON.parse(getSetting("user_json", "{}")),
    branch: JSON.parse(getSetting("branch_json", "{}")),
    inclusiveTaxRate: Number(getSetting("inclusive_tax_rate", "15.5")),
  };
}

function replaceCatalog({ categories, products, currencies, dining_tables: diningTables = [] }) {
  const tx = db.transaction(() => {
    db.prepare("DELETE FROM categories").run();
    db.prepare("DELETE FROM products").run();
    db.prepare("DELETE FROM currencies").run();
    db.prepare("DELETE FROM dining_tables").run();

    const insertCategory = db.prepare(
      "INSERT INTO categories (id, name, is_asset) VALUES (?, ?, ?)"
    );
    for (const cat of categories) {
      insertCategory.run(cat.id, cat.name, cat.is_asset ? 1 : 0);
    }

    const insertProduct = db.prepare(
      "INSERT INTO products (id, name, category_id, category_name, selling_price, is_active, addon_groups_json) VALUES (?, ?, ?, ?, ?, ?, ?)"
    );
    for (const product of products) {
      insertProduct.run(
        product.id,
        product.name,
        product.category,
        product.category_name || "",
        Number(product.selling_price),
        product.is_active ? 1 : 0,
        JSON.stringify(product.addon_groups || [])
      );
    }

    const insertCurrency = db.prepare(
      "INSERT INTO currencies (id, code, name, symbol, is_base, is_active, current_rate) VALUES (?, ?, ?, ?, ?, ?, ?)"
    );
    for (const currency of currencies) {
      insertCurrency.run(
        currency.id,
        currency.code || "",
        currency.name,
        currency.symbol || "",
        currency.is_base ? 1 : 0,
        currency.is_active ? 1 : 0,
        currency.current_rate != null ? String(currency.current_rate) : null
      );
    }

    const insertDiningTable = db.prepare(
      "INSERT INTO dining_tables (id, name, sort_order, is_active) VALUES (?, ?, ?, ?)"
    );
    for (const table of diningTables) {
      insertDiningTable.run(
        table.id,
        table.name,
        Number(table.sort_order) || 0,
        table.is_active === false ? 0 : 1
      );
    }

    setSetting("catalog_synced_at", new Date().toISOString());
  });
  tx();
}

function listCategories() {
  return db.prepare("SELECT * FROM categories ORDER BY name").all();
}

function parseAddonGroups(raw) {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function parseOrderItemAddons(raw) {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function mapOrderItem(row) {
  return {
    product_id: row.product_id,
    product_name: row.product_name,
    quantity: row.quantity,
    price: row.price,
    notes: row.notes || "",
    addons: parseOrderItemAddons(row.addons_json),
  };
}

function listProducts() {
  return db
    .prepare(
      "SELECT id, name, category_id AS category, category_name, selling_price, is_active, addon_groups_json FROM products WHERE is_active = 1 ORDER BY name"
    )
    .all()
    .map((row) => ({
      ...row,
      addon_groups: parseAddonGroups(row.addon_groups_json),
    }));
}

function listCurrencies() {
  return db
    .prepare(
      "SELECT id, code, name, symbol, is_base, is_active, current_rate FROM currencies WHERE is_active = 1 ORDER BY name"
    )
    .all()
    .map((row) => ({
      ...row,
      is_base: Boolean(row.is_base),
      is_active: Boolean(row.is_active),
    }));
}

function listDiningTables() {
  return db
    .prepare(
      "SELECT id, name, sort_order, is_active FROM dining_tables WHERE is_active = 1 ORDER BY sort_order, name"
    )
    .all()
    .map((row) => ({
      ...row,
      is_active: Boolean(row.is_active),
    }));
}

function newClientId() {
  return crypto.randomUUID();
}

function createOrder({ orderType, tableNumber, items, createdByName = "" }) {
  const trimmedTable = (tableNumber || "").trim();
  if (orderType === "dine_in" && trimmedTable) {
    const existing = db
      .prepare(
        `SELECT client_id FROM orders
         WHERE status = 'open' AND order_type = 'dine_in' AND table_number = ?
         ORDER BY created_at DESC LIMIT 1`
      )
      .get(trimmedTable);
    if (existing) {
      return addItemsToOrder(existing.client_id, items);
    }
  }

  const clientId = newClientId();
  const createdAt = new Date().toISOString();
  let total = 0;

  for (const item of items) {
    total += Number(item.price) * Number(item.quantity);
  }

  const tx = db.transaction(() => {
    db.prepare(
      `INSERT INTO orders (
        client_id, order_type, table_number, status, total_amount,
        sync_status, created_at, created_by_name
      ) VALUES (?, ?, ?, 'open', ?, 'pending', ?, ?)`
    ).run(clientId, orderType, tableNumber || "", total, createdAt, createdByName || "");

    const insertItem = db.prepare(
      "INSERT INTO order_items (order_client_id, product_id, product_name, quantity, price, notes, addons_json) VALUES (?, ?, ?, ?, ?, ?, ?)"
    );
    for (const item of items) {
      insertItem.run(
        clientId,
        item.product_id,
        item.product_name,
        item.quantity,
        item.price,
        item.notes || "",
        JSON.stringify(item.addons || [])
      );
    }
  });
  tx();

  return getOrder(clientId);
}

function addItemsToOrder(clientId, items) {
  const order = db.prepare("SELECT * FROM orders WHERE client_id = ?").get(clientId);
  if (!order || order.status !== "open") {
    throw new Error("Only open orders can receive new items.");
  }

  const insertItem = db.prepare(
    "INSERT INTO order_items (order_client_id, product_id, product_name, quantity, price, notes, addons_json) VALUES (?, ?, ?, ?, ?, ?, ?)"
  );
  let addedTotal = 0;
  const tx = db.transaction(() => {
    for (const item of items) {
      addedTotal += Number(item.price) * Number(item.quantity);
      insertItem.run(
        clientId,
        item.product_id,
        item.product_name,
        item.quantity,
        item.price,
        item.notes || "",
        JSON.stringify(item.addons || [])
      );
    }
    db.prepare(
      `UPDATE orders SET
        total_amount = total_amount + ?,
        kitchen_status = 'pending',
        sync_status = 'pending'
      WHERE client_id = ?`
    ).run(addedTotal, clientId);
  });
  tx();
  return getOrder(clientId);
}

function consolidateTableOrders(clientId) {
  const order = db.prepare("SELECT * FROM orders WHERE client_id = ?").get(clientId);
  if (
    !order
    || order.status !== "open"
    || order.order_type !== "dine_in"
    || !(order.table_number || "").trim()
  ) {
    return order;
  }

  const siblings = db
    .prepare(
      `SELECT client_id FROM orders
       WHERE status = 'open' AND order_type = 'dine_in' AND table_number = ? AND client_id != ?`
    )
    .all(order.table_number, clientId);

  if (!siblings.length) return getOrder(clientId);

  const tx = db.transaction(() => {
    for (const sibling of siblings) {
      db.prepare(
        "UPDATE order_items SET order_client_id = ? WHERE order_client_id = ?"
      ).run(clientId, sibling.client_id);
      db.prepare("DELETE FROM orders WHERE client_id = ?").run(sibling.client_id);
    }
    const total = db
      .prepare(
        `SELECT COALESCE(SUM(quantity * price), 0) AS total
         FROM order_items WHERE order_client_id = ?`
      )
      .get(clientId).total;
    db.prepare("UPDATE orders SET total_amount = ?, sync_status = 'pending' WHERE client_id = ?").run(
      total,
      clientId
    );
  });
  tx();
  return getOrder(clientId);
}

function getOrder(clientId) {
  const order = db.prepare("SELECT * FROM orders WHERE client_id = ?").get(clientId);
  if (!order) return null;
  const items = db
    .prepare(
      "SELECT product_id, product_name, quantity, price, notes, addons_json FROM order_items WHERE order_client_id = ?"
    )
    .all(clientId)
    .map(mapOrderItem);
  return { ...order, items };
}

function listOpenOrders() {
  const orders = db
    .prepare("SELECT * FROM orders WHERE status = 'open' ORDER BY created_at DESC")
    .all();
  return orders.map((order) => ({
    ...order,
    items: db
      .prepare(
        "SELECT product_id, product_name, quantity, price, notes, addons_json FROM order_items WHERE order_client_id = ?"
      )
      .all(order.client_id)
      .map(mapOrderItem),
  }));
}

function payOrder(clientId, { currencyId, exchangeRate, amountPaid, receiptNumber, paidByName = "" }) {
  const order = consolidateTableOrders(clientId);
  const targetId = order.client_id;
  const paidAt = new Date().toISOString();
  db.prepare(
    `UPDATE orders SET
      status = 'paid',
      payment_currency_id = ?,
      exchange_rate = ?,
      amount_paid = ?,
      receipt_number = ?,
      paid_at = ?,
      paid_by_name = ?,
      sync_status = 'pending'
    WHERE client_id = ?`
  ).run(currencyId, exchangeRate, amountPaid, receiptNumber, paidAt, paidByName || "", targetId);
  return getOrder(targetId);
}

function listPendingSyncOrders() {
  return db
    .prepare("SELECT * FROM orders WHERE sync_status = 'pending' ORDER BY created_at")
    .all()
    .map((order) => ({
      ...order,
      items: db
        .prepare(
          "SELECT product_id, product_name, quantity, price, notes, addons_json FROM order_items WHERE order_client_id = ?"
        )
        .all(order.client_id)
        .map(mapOrderItem),
    }));
}

function markOrderSynced(
  clientId,
  { serverId, receiptNumber, kitchenStatus = null, syncError = null }
) {
  db.prepare(
    `UPDATE orders SET
      server_id = ?,
      receipt_number = COALESCE(?, receipt_number),
      kitchen_status = COALESCE(?, kitchen_status),
      sync_status = ?,
      sync_error = ?
    WHERE client_id = ?`
  ).run(
    serverId,
    receiptNumber,
    kitchenStatus,
    syncError ? "error" : "synced",
    syncError,
    clientId
  );
}

function updateKitchenStatuses(updates) {
  if (!updates?.length) return 0;

  const stmt = db.prepare(
    `UPDATE orders SET
      kitchen_status = ?,
      kitchen_started_at = ?,
      kitchen_ready_at = ?
    WHERE server_id = ? AND status = 'open'`
  );
  let changed = 0;

  const tx = db.transaction(() => {
    for (const update of updates) {
      const result = stmt.run(
        update.kitchen_status || "pending",
        update.kitchen_started_at || null,
        update.kitchen_ready_at || null,
        update.server_id
      );
      changed += result.changes;
    }
  });
  tx();

  return changed;
}

function pendingSyncCount() {
  return db.prepare("SELECT COUNT(*) AS count FROM orders WHERE sync_status = 'pending'").get()
    .count;
}

function getCatalogSyncedAt() {
  return getSetting("catalog_synced_at");
}

function getDayEndReport({ startIso, endIso }) {
  const orders = db
    .prepare(
      `SELECT client_id, order_type, total_amount, payment_currency_id,
              exchange_rate, amount_paid, receipt_number, paid_at
       FROM orders
       WHERE status = 'paid' AND paid_at >= ? AND paid_at < ?
       ORDER BY paid_at`
    )
    .all(startIso, endIso);

  const payments = db
    .prepare(
      `SELECT payment_currency_id, COUNT(*) AS order_count, SUM(amount_paid) AS total_paid
       FROM orders
       WHERE status = 'paid' AND paid_at >= ? AND paid_at < ?
       GROUP BY payment_currency_id
       ORDER BY payment_currency_id`
    )
    .all(startIso, endIso)
    .map((row) => {
      const currency = row.payment_currency_id
        ? db.prepare("SELECT id, code, name, symbol, is_base FROM currencies WHERE id = ?").get(
            row.payment_currency_id
          )
        : null;
      return {
        currency_id: row.payment_currency_id,
        order_count: row.order_count,
        total_paid: row.total_paid,
        currency,
      };
    });

  const products = db
    .prepare(
      `SELECT oi.product_name, SUM(oi.quantity) AS quantity, SUM(oi.quantity * oi.price) AS revenue
       FROM order_items oi
       INNER JOIN orders o ON o.client_id = oi.order_client_id
       WHERE o.status = 'paid' AND o.paid_at >= ? AND o.paid_at < ?
       GROUP BY oi.product_id, oi.product_name
       ORDER BY revenue DESC, oi.product_name`
    )
    .all(startIso, endIso);

  const orderTypes = db
    .prepare(
      `SELECT order_type, COUNT(*) AS count
       FROM orders
       WHERE status = 'paid' AND paid_at >= ? AND paid_at < ?
       GROUP BY order_type`
    )
    .all(startIso, endIso);

  const grossTotal = orders.reduce((sum, order) => sum + Number(order.total_amount), 0);

  return {
    orderCount: orders.length,
    grossTotal,
    payments,
    products,
    orderTypes,
    startIso,
    endIso,
  };
}

module.exports = {
  initDb,
  getDbPath,
  getSetting,
  setSetting,
  clearSession,
  saveSession,
  getSession,
  replaceCatalog,
  listCategories,
  listProducts,
  listCurrencies,
  listDiningTables,
  createOrder,
  getOrder,
  listOpenOrders,
  payOrder,
  listPendingSyncOrders,
  markOrderSynced,
  updateKitchenStatuses,
  pendingSyncCount,
  getCatalogSyncedAt,
  getDayEndReport,
};
