/** @typedef {{ key: string|null, dir: 'asc'|'desc' }} SortState */

export function createSortState(key = null, dir = "desc") {
  return { key, dir };
}

export function toggleSort(state, key) {
  if (state.key === key) {
    state.dir = state.dir === "asc" ? "desc" : "asc";
  } else {
    state.key = key;
    state.dir = "asc";
  }
}

function compareValues(a, b) {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;

  if (typeof a === "number" && typeof b === "number") {
    if (Number.isFinite(a) && Number.isFinite(b)) return a - b;
  }

  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
}

export function sortItems(items, state, accessors) {
  if (!state?.key || !items?.length) return items;

  const getValue = accessors[state.key];
  if (!getValue) return items;

  const mult = state.dir === "asc" ? 1 : -1;
  return [...items].sort((a, b) => mult * compareValues(getValue(a), getValue(b)));
}

export function sortTh(label, key, state, { align = "" } = {}) {
  const active = state.key === key;
  const indicator = active
    ? (state.dir === "asc" ? "▲" : "▼")
    : "";
  const alignStyle = align ? ` style="text-align: ${align};"` : "";
  const classes = ["sortable-th", active ? "sort-active" : ""].filter(Boolean).join(" ");

  return `<th class="${classes}" data-sort-key="${key}" scope="col"${alignStyle}><span class="sort-th-label">${label}</span>${indicator ? `<span class="sort-indicator" aria-hidden="true">${indicator}</span>` : ""}</th>`;
}

export function actionTh() {
  return '<th scope="col" class="sort-th-actions"></th>';
}

export function bindTableSort(container, stateOrGetter, rerender) {
  if (!container || container.dataset.sortBound) return;
  container.dataset.sortBound = "1";

  container.addEventListener("click", (event) => {
    const th = event.target.closest("th[data-sort-key]");
    if (!th || !container.contains(th)) return;
    const state = typeof stateOrGetter === "function" ? stateOrGetter() : stateOrGetter;
    toggleSort(state, th.dataset.sortKey);
    rerender();
  });
}
