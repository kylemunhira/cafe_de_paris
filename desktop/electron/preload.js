const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("pos", {
  getSession: () => ipcRenderer.invoke("session:get"),
  saveSession: (payload) => ipcRenderer.invoke("session:save", payload),
  clearSession: () => ipcRenderer.invoke("session:clear"),
  getCatalog: () => ipcRenderer.invoke("catalog:list"),
  replaceCatalog: (payload) => ipcRenderer.invoke("catalog:replace", payload),
  createOrder: (payload) => ipcRenderer.invoke("orders:create", payload),
  listOpenOrders: () => ipcRenderer.invoke("orders:open"),
  payOrder: (clientId, payment) => ipcRenderer.invoke("orders:pay", clientId, payment),
  listPendingSyncOrders: () => ipcRenderer.invoke("orders:pending-sync"),
  markOrderSynced: (clientId, result) =>
    ipcRenderer.invoke("orders:mark-synced", clientId, result),
  pendingSyncCount: () => ipcRenderer.invoke("sync:pending-count"),
  getSetting: (key) => ipcRenderer.invoke("settings:get", key),
  setSetting: (key, value) => ipcRenderer.invoke("settings:set", key, value),
  openExternal: (url) => ipcRenderer.invoke("app:open-external", url),
  print: (payload) => ipcRenderer.invoke("print:document", payload),
});
