const { app, BrowserWindow, ipcMain, shell } = require("electron");
const path = require("path");
const db = require("./db");
const { loadConfig } = require("./config");
const { printDocument } = require("./print");

function sessionWithConfig(session) {
  if (!session) return null;
  return { ...session, serverUrl: loadConfig().serverUrl };
}

const PRINTER_SETTING_KEY = "printer_device_name";

let mainWindow;

function localDayBounds(dateStr) {
  const now = new Date();
  let year;
  let month;
  let day;

  if (dateStr) {
    const parts = dateStr.split("-").map(Number);
    year = parts[0];
    month = parts[1] - 1;
    day = parts[2];
  } else {
    year = now.getFullYear();
    month = now.getMonth();
    day = now.getDate();
  }

  const start = new Date(year, month, day, 0, 0, 0, 0);
  const end = new Date(year, month, day + 1, 0, 0, 0, 0);

  return {
    startIso: start.toISOString(),
    endIso: end.toISOString(),
    reportDate: `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`,
  };
}

function getConfiguredPrinter() {
  return db.getSetting(PRINTER_SETTING_KEY, "") || "";
}

async function listSystemPrinters() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return [];
  }
  const printers = await mainWindow.webContents.getPrintersAsync();
  return printers.map((printer) => ({
    name: printer.name,
    displayName: printer.displayName || printer.name,
    isDefault: Boolean(printer.isDefault),
    status: printer.status,
  }));
}

const APP_ICON = path.join(__dirname, "..", "build", "app_icon.ico");

function createWindow(startPage = "login.html") {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 700,
    title: "Café de Paris POS",
    icon: APP_ICON,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "..", "src", startPage));
}

app.whenReady().then(() => {
  db.initDb();
  const session = db.getSession();
  createWindow(session ? "index.html" : "login.html");

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow(db.getSession() ? "index.html" : "login.html");
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

ipcMain.handle("config:get", () => loadConfig());
ipcMain.handle("session:get", () => sessionWithConfig(db.getSession()));
ipcMain.handle("session:clear", () => {
  db.clearSession();
  return true;
});
ipcMain.handle("session:save", (_event, payload) => {
  db.saveSession(payload);
  return sessionWithConfig(db.getSession());
});

ipcMain.handle("catalog:list", () => ({
  categories: db.listCategories(),
  products: db.listProducts(),
  currencies: db.listCurrencies(),
  catalogSyncedAt: db.getCatalogSyncedAt(),
}));

ipcMain.handle("orders:create", (_event, payload) => db.createOrder(payload));
ipcMain.handle("orders:open", () => db.listOpenOrders());
ipcMain.handle("orders:pay", (_event, clientId, payment) =>
  db.payOrder(clientId, payment)
);
ipcMain.handle("orders:pending-sync", () => db.listPendingSyncOrders());
ipcMain.handle("orders:mark-synced", (_event, clientId, result) =>
  db.markOrderSynced(clientId, result)
);
ipcMain.handle("sync:pending-count", () => db.pendingSyncCount());

ipcMain.handle("reports:day-end", (_event, { date } = {}) => {
  const bounds = localDayBounds(date || null);
  return {
    ...bounds,
    ...db.getDayEndReport(bounds),
  };
});

ipcMain.handle("settings:get", (_event, key) => db.getSetting(key));
ipcMain.handle("settings:set", (_event, key, value) => {
  db.setSetting(key, value);
  return true;
});

ipcMain.handle("catalog:replace", (_event, payload) => {
  db.replaceCatalog(payload);
  return db.getCatalogSyncedAt();
});

ipcMain.handle("app:open-external", (_event, url) => {
  shell.openExternal(url);
});

ipcMain.handle("printers:list", () => listSystemPrinters());

ipcMain.handle("printer:get", () => getConfiguredPrinter());

ipcMain.handle("printer:set", (_event, deviceName) => {
  db.setSetting(PRINTER_SETTING_KEY, deviceName || "");
  return getConfiguredPrinter();
});

ipcMain.handle("print:document", async (_event, payload) => {
  await printDocument(payload, { deviceName: getConfiguredPrinter() });
  return true;
});

ipcMain.handle("print:test", async () => {
  await printDocument({ type: "test" }, { deviceName: getConfiguredPrinter() });
  return true;
});
