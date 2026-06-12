import { showToast } from "./api.js";

const settingsModal = document.getElementById("settings-modal");
const settingsBtn = document.getElementById("settings-btn");
const settingsCloseBtn = document.getElementById("settings-close-btn");
const printerSelect = document.getElementById("printer-select");
const printerTestBtn = document.getElementById("printer-test-btn");
const printerHint = document.getElementById("printer-hint");

function closeSettings() {
  settingsModal.hidden = true;
}

async function loadPrinters() {
  printerSelect.innerHTML = `<option value="">Loading printers…</option>`;
  printerSelect.disabled = true;
  printerTestBtn.disabled = true;

  try {
    const [printers, selected] = await Promise.all([
      window.pos.listPrinters(),
      window.pos.getPrinter(),
    ]);

    const options = [
      `<option value="">System default</option>`,
      ...printers.map((printer) => {
        const label = printer.isDefault
          ? `${printer.displayName} (Windows default)`
          : printer.displayName;
        const selectedAttr = printer.name === selected ? " selected" : "";
        return `<option value="${escapeAttr(printer.name)}"${selectedAttr}>${escapeHtml(label)}</option>`;
      }),
    ];

    printerSelect.innerHTML = options.join("");
    if (selected && !printers.some((printer) => printer.name === selected)) {
      printerSelect.innerHTML += `<option value="${escapeAttr(selected)}" selected>${escapeHtml(selected)} (not found)</option>`;
      printerHint.textContent =
        "Saved printer is not available. Choose another printer or use system default.";
    } else if (!printers.length) {
      printerHint.textContent =
        "No printers detected. Receipts will use the Windows default when one is available.";
    } else {
      printerHint.textContent =
        "80mm thermal layout. Order tickets and sales receipts print to the selected printer.";
    }
  } catch (err) {
    printerSelect.innerHTML = `<option value="">System default</option>`;
    printerHint.textContent = `Could not load printers: ${err.message}`;
    showToast(`Could not load printers: ${err.message}`, true);
  } finally {
    printerSelect.disabled = false;
    printerTestBtn.disabled = false;
  }
}

async function openSettings() {
  settingsModal.hidden = false;
  await loadPrinters();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/"/g, "&quot;");
}

settingsBtn.addEventListener("click", () => {
  openSettings().catch((err) => showToast(err.message, true));
});

settingsCloseBtn.addEventListener("click", closeSettings);

settingsModal.addEventListener("click", (event) => {
  if (event.target === settingsModal) closeSettings();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !settingsModal.hidden) closeSettings();
});

printerSelect.addEventListener("change", async () => {
  try {
    await window.pos.setPrinter(printerSelect.value);
    const label =
      printerSelect.value === ""
        ? "System default printer"
        : printerSelect.selectedOptions[0]?.textContent || "Printer";
    showToast(`Printer set to ${label}`);
    printerHint.textContent =
      "80mm thermal layout. Order tickets and sales receipts print to the selected printer.";
  } catch (err) {
    showToast(`Could not save printer: ${err.message}`, true);
  }
});

printerTestBtn.addEventListener("click", async () => {
  printerTestBtn.disabled = true;
  try {
    await window.pos.printTest();
    showToast("Test page sent to printer");
  } catch (err) {
    showToast(`Test print failed: ${err.message}`, true);
  } finally {
    printerTestBtn.disabled = false;
  }
});
