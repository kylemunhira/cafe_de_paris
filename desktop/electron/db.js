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

function saveSession({ token, user, branch, serverUrl, inclusiveTaxRate }) {
  setSetting("auth_token", token);
  setSetting("user_json", JSON.stringify(user));
  setSetting("branch_json", JSON.stringify(branch));
  setSetting("server_url", serverUrl);
  if (inclusiveTaxRate != null) {
    setSetting("inclusive_tax_rate", String(inclusiveTaxRate));
  }
}

function getSession() {
  const token = getSetting("auth_token");
  if (!token) return null;
  return {
    token,
    serverUrl: getSetting("server_url", "http://127.0.0.1:8000"),
    user: JSON.parse(getSetting("user_json", "{}")),
    branch: JSON.parse(getSetting("branch_json", "{}")),
    inclusiveTaxRate: Number(getSetting("inclusive_tax_rate", "15.5")),
  };
}

function replaceCatalog({ categories, products, currencies }) {
  const tx = db.transaction(() => {
    db.prepare("DELETE FROM categories").run();
    db.prepare("DELETE FROM products").run();
    db.prepare("DELETE FROM currencies").run();

    const insertCategory = db.prepare(
      "INSERT INTO categories (id, name, is_asset) VALUES (?, ?, ?)"
    );
    for (const cat of categories) {
      insertCategory.run(cat.id, cat.name, cat.is_asset ? 1 : 0);
    }

    const insertProduct = db.prepare(
      "INSERT INTO products (id, name, category_id, category_name, selling_price, is_active) VALUES (?, ?, ?, ?, ?, ?)"
    );
    for (const product of products) {
      insertProduct.run(
        product.id,
        product.name,
        product.category,
        product.category_name || "",
        Number(product.selling_price),
        product.is_active ? 1 : 0
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

    setSetting("catalog_synced_at", new Date().toISOString());
  });
  tx();
}

function listCategories() {
  return db.prepare("SELECT * FROM categories ORDER BY name").all();
}

function listProducts() {
  return db
    .prepare(
      "SELECT id, name, category_id AS category, category_name, selling_price, is_active FROM products WHERE is_active = 1 ORDER BY name"
    )
    .all();
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

function newClientId() {
  return crypto.randomUUID();
}

function createOrder({ orderType, tableNumber, items }) {
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
        sync_status, created_at
      ) VALUES (?, ?, ?, 'open', ?, 'pending', ?)`
    ).run(clientId, orderType, tableNumber || "", total, createdAt);

    const insertItem = db.prepare(
      "INSERT INTO order_items (order_client_id, product_id, product_name, quantity, price) VALUES (?, ?, ?, ?, ?)"
    );
    for (const item of items) {
      insertItem.run(
        clientId,
        item.product_id,
        item.product_name,
        item.quantity,
        item.price
      );
    }
  });
  tx();

  return getOrder(clientId);
}

function getOrder(clientId) {
  const order = db.prepare("SELECT * FROM orders WHERE client_id = ?").get(clientId);
  if (!order) return null;
  const items = db
    .prepare("SELECT product_id, product_name, quantity, price FROM order_items WHERE order_client_id = ?")
    .all(clientId);
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
        "SELECT product_id, product_name, quantity, price FROM order_items WHERE order_client_id = ?"
      )
      .all(order.client_id),
  }));
}

function payOrder(clientId, { currencyId, exchangeRate, amountPaid, receiptNumber }) {
  const paidAt = new Date().toISOString();
  db.prepare(
    `UPDATE orders SET
      status = 'paid',
      payment_currency_id = ?,
      exchange_rate = ?,
      amount_paid = ?,
      receipt_number = ?,
      paid_at = ?,
      sync_status = 'pending'
    WHERE client_id = ?`
  ).run(currencyId, exchangeRate, amountPaid, receiptNumber, paidAt, clientId);
  return getOrder(clientId);
}

function listPendingSyncOrders() {
  return db
    .prepare("SELECT * FROM orders WHERE sync_status = 'pending' ORDER BY created_at")
    .all()
    .map((order) => ({
      ...order,
      items: db
        .prepare(
          "SELECT product_id, product_name, quantity, price FROM order_items WHERE order_client_id = ?"
        )
        .all(order.client_id),
    }));
}

function markOrderSynced(clientId, { serverId, receiptNumber, syncError = null }) {
  db.prepare(
    `UPDATE orders SET
      server_id = ?,
      receipt_number = COALESCE(?, receipt_number),
      sync_status = ?,
      sync_error = ?
    WHERE client_id = ?`
  ).run(
    serverId,
    receiptNumber,
    syncError ? "error" : "synced",
    syncError,
    clientId
  );
}

function pendingSyncCount() {
  return db.prepare("SELECT COUNT(*) AS count FROM orders WHERE sync_status = 'pending'").get()
    .count;
}

function getCatalogSyncedAt() {
  return getSetting("catalog_synced_at");
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
  createOrder,
  getOrder,
  listOpenOrders,
  payOrder,
  listPendingSyncOrders,
  markOrderSynced,
  pendingSyncCount,
  getCatalogSyncedAt,
};
