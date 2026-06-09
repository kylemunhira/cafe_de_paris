const { app, BrowserWindow, ipcMain, shell } = require("electron");
const path = require("path");
const db = require("./db");
const { printDocument } = require("./print");

let mainWindow;

function createWindow(startPage = "login.html") {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 700,
    title: "Café de Paris POS",
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

ipcMain.handle("session:get", () => db.getSession());
ipcMain.handle("session:clear", () => {
  db.clearSession();
  return true;
});
ipcMain.handle("session:save", (_event, payload) => {
  db.saveSession(payload);
  return db.getSession();
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

ipcMain.handle("print:document", async (_event, payload) => {
  await printDocument(payload);
  return true;
});
