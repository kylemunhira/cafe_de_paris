/** Branch pickers: HQ/global users may choose; everyone else is locked to their branch. */

export function branchesForUser(allBranches, staffBranchId, canSelectAny) {
  if (canSelectAny) return allBranches;
  if (!staffBranchId) return [];
  const id = String(staffBranchId);
  return allBranches.filter((b) => String(b.id) === id);
}

export function setupBranchSelect(
  select,
  branches,
  {
    canSelectAny,
    placeholder = "Select branch…",
    emptyLabel = "No branch assigned",
    formatName = (b) => b.name,
  } = {},
) {
  if (!select) return;
  if (!branches.length) {
    select.innerHTML = `<option value="">${emptyLabel}</option>`;
    select.disabled = true;
    return;
  }
  if (branches.length === 1 || !canSelectAny) {
    select.innerHTML = branches
      .map((b) => `<option value="${b.id}" selected>${formatName(b)}</option>`)
      .join("");
    select.disabled = true;
    return;
  }
  select.innerHTML =
    `<option value="">${placeholder}</option>` +
    branches.map((b) => `<option value="${b.id}">${formatName(b)}</option>`).join("");
  select.disabled = false;
}

/** Report filter dropdown: includes an "all branches" option when the user may filter. */
export function setupBranchFilter(
  select,
  branches,
  {
    canSelectAny,
    staffBranchId,
    allLabel = "All branches",
    formatName = (b) => b.name,
  } = {},
) {
  if (!select) return;
  if (!canSelectAny) {
    select.innerHTML = "";
    select.disabled = true;
    return;
  }
  select.innerHTML =
    `<option value="">${allLabel}</option>` +
    branches.map((b) => `<option value="${b.id}">${formatName(b)}</option>`).join("");
  select.disabled = false;
}

export function effectiveBranchParam(canSelectAny, staffBranchId, selectedValue) {
  if (canSelectAny && selectedValue) return String(selectedValue);
  if (!canSelectAny && staffBranchId) return String(staffBranchId);
  return "";
}
