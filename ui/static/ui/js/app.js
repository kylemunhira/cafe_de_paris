document.addEventListener("DOMContentLoaded", () => {
  const SIDEBAR_STORAGE_KEY = "cdp-sidebar-hidden";
  const MOBILE_QUERY = window.matchMedia("(max-width: 768px)");

  const appShell = document.getElementById("app-shell");
  const toggle = document.getElementById("sidebar-toggle");
  const sidebar = document.querySelector(".sidebar");

  if (!toggle || !sidebar || !appShell) {
    return;
  }

  function isMobile() {
    return MOBILE_QUERY.matches;
  }

  function isSidebarHidden() {
    return appShell.classList.contains("sidebar-hidden");
  }

  function updateToggleUi() {
    const hidden = isMobile()
      ? !sidebar.classList.contains("open")
      : isSidebarHidden();
    toggle.setAttribute("aria-expanded", hidden ? "false" : "true");
    toggle.title = hidden ? "Show navigation" : "Hide navigation";
  }

  function applyDesktopSidebarState() {
    const hidden = localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";
    appShell.classList.toggle("sidebar-hidden", hidden);
    updateToggleUi();
  }

  function applyMobileSidebarState() {
    appShell.classList.remove("sidebar-hidden");
    sidebar.classList.remove("open");
    updateToggleUi();
  }

  function syncSidebarMode() {
    if (isMobile()) {
      applyMobileSidebarState();
    } else {
      sidebar.classList.remove("open");
      applyDesktopSidebarState();
    }
  }

  toggle.addEventListener("click", () => {
    if (isMobile()) {
      sidebar.classList.toggle("open");
    } else {
      const hidden = !isSidebarHidden();
      appShell.classList.toggle("sidebar-hidden", hidden);
      localStorage.setItem(SIDEBAR_STORAGE_KEY, hidden ? "true" : "false");
    }
    updateToggleUi();
  });

  document.addEventListener("click", (e) => {
    if (
      isMobile() &&
      sidebar.classList.contains("open") &&
      !sidebar.contains(e.target) &&
      !toggle.contains(e.target)
    ) {
      sidebar.classList.remove("open");
      updateToggleUi();
    }
  });

  MOBILE_QUERY.addEventListener("change", syncSidebarMode);
  syncSidebarMode();
});
