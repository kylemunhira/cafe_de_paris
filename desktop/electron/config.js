const fs = require("fs");
const path = require("path");
const { app } = require("electron");

const DEFAULT_CONFIG = {
  serverUrl: "http://127.0.0.1:8000",
};

function getConfigPath() {
  if (app.isPackaged) {
    return path.join(path.dirname(process.execPath), "config.json");
  }
  return path.join(__dirname, "..", "config.json");
}

function loadConfig() {
  const configPath = getConfigPath();
  if (!fs.existsSync(configPath)) {
    return { ...DEFAULT_CONFIG };
  }

  try {
    const parsed = JSON.parse(fs.readFileSync(configPath, "utf8"));
    return {
      serverUrl: String(parsed.serverUrl || DEFAULT_CONFIG.serverUrl).replace(/\/$/, ""),
    };
  } catch {
    return { ...DEFAULT_CONFIG };
  }
}

module.exports = { loadConfig, getConfigPath };
