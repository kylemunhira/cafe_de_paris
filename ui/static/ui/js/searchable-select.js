const instances = new WeakMap();

function highlightOption(list, activeIndex) {
  const options = list.querySelectorAll(".searchable-select-option");
  options.forEach((option, index) => {
    option.classList.toggle("active", index === activeIndex);
    if (index === activeIndex) {
      option.scrollIntoView({ block: "nearest" });
    }
  });
}

export function syncSearchableSelect(select) {
  const instance = instances.get(select);
  if (!instance) return;
  instance.syncInputFromSelect();
  if (!instance.list.hidden) {
    instance.renderList(instance.input.value);
  }
}

export function initSearchableSelect(select, options = {}) {
  if (!select || select.dataset.searchableEnhanced === "true") {
    return instances.get(select) || null;
  }

  const placeholder =
    options.placeholder ||
    select.querySelector('option[value=""]')?.textContent?.trim() ||
    "Type to search…";

  const wrapper = document.createElement("div");
  wrapper.className = "searchable-select";
  select.parentNode.insertBefore(wrapper, select);
  wrapper.appendChild(select);

  select.classList.add("searchable-select-native");
  select.dataset.searchableEnhanced = "true";

  const input = document.createElement("input");
  input.type = "search";
  input.className = "searchable-select-input report-input";
  input.placeholder = placeholder;
  input.autocomplete = "off";
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-autocomplete", "list");

  const list = document.createElement("div");
  list.className = "searchable-select-list";
  list.hidden = true;
  list.setAttribute("role", "listbox");

  wrapper.appendChild(input);
  wrapper.appendChild(list);

  let activeIndex = -1;
  let blurTimeout = null;

  function getOptions() {
    return [...select.options].filter((option) => option.value !== "");
  }

  function selectedLabel() {
    const option = select.options[select.selectedIndex];
    return option && option.value ? option.textContent : "";
  }

  function syncInputFromSelect() {
    input.value = selectedLabel();
    input.disabled = select.disabled;
  }

  function filterOptions(query) {
    const normalized = query.trim().toLowerCase();
    return getOptions().filter((option) => {
      if (!normalized) return true;
      return option.textContent.toLowerCase().includes(normalized);
    });
  }

  function renderList(query = "") {
    const matches = filterOptions(query);
    activeIndex = matches.length ? 0 : -1;

    if (!matches.length) {
      list.innerHTML = `<div class="searchable-select-empty">No matches</div>`;
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      return;
    }

    list.innerHTML = matches
      .map(
        (option, index) => `
      <button
        type="button"
        class="searchable-select-option${index === activeIndex ? " active" : ""}"
        data-value="${option.value}"
        role="option"
      >
        ${option.textContent}
      </button>`
      )
      .join("");
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function closeList() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
  }

  function selectValue(value) {
    select.value = value;
    syncInputFromSelect();
    closeList();
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  input.addEventListener("focus", () => {
    clearTimeout(blurTimeout);
    renderList(input.value);
  });

  input.addEventListener("input", () => {
    renderList(input.value);
  });

  input.addEventListener("keydown", (event) => {
    const optionButtons = list.querySelectorAll(".searchable-select-option");
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (list.hidden) {
        renderList(input.value);
        return;
      }
      activeIndex = Math.min(activeIndex + 1, optionButtons.length - 1);
      highlightOption(list, activeIndex);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      highlightOption(list, activeIndex);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const option = optionButtons[activeIndex];
      if (option) {
        selectValue(option.dataset.value);
      }
      return;
    }
    if (event.key === "Escape") {
      closeList();
      syncInputFromSelect();
    }
  });

  input.addEventListener("blur", () => {
    blurTimeout = setTimeout(() => {
      closeList();
      syncInputFromSelect();
    }, 150);
  });

  list.addEventListener("mousedown", (event) => {
    event.preventDefault();
    const option = event.target.closest(".searchable-select-option");
    if (option) {
      selectValue(option.dataset.value);
    }
  });

  const observer = new MutationObserver(() => {
    syncInputFromSelect();
    if (!list.hidden) {
      renderList(input.value);
    }
  });
  observer.observe(select, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled"] });

  select.addEventListener("change", syncInputFromSelect);

  const instance = {
    input,
    list,
    observer,
    syncInputFromSelect,
    renderList,
  };
  instances.set(select, instance);
  syncInputFromSelect();
  return instance;
}

export function initSearchableSelects(root = document) {
  root.querySelectorAll("select.searchable-select").forEach((select) => {
    initSearchableSelect(select);
  });
}
