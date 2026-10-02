(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const { ELIGIBILITY_COPY, ANALYSIS_COPY, CHECKLIST_COPY } = window.UiData;

  /* Current selection. The case list is fetched once; the detail is fetched per
     case so the browser never holds more than one record's payload. */
  const state = { recordIds: [], selectedId: null };

  /* Escape interpolated values before they enter markup. Labels come from the
     API and analysis text is model output, so neither is trusted as HTML. */
  function esc(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ---------------------------------------------------------
     Toast
     --------------------------------------------------------- */

  function toast(title, message) {
    const el = document.createElement("div");
    el.className = "flex items-start gap-3 rounded-sm border border-line border-l-4 border-l-brand bg-white p-3";
    el.setAttribute("role", "status");
    el.innerHTML =
      '<div class="min-w-0"><div class="text-[13px] font-semibold text-ink"></div>' +
      '<div class="mt-0.5 text-[11px] leading-body text-ink-medium"></div></div>' +
      '<button type="button" class="ml-auto grid h-6 w-6 shrink-0 place-items-center rounded-sm text-ink-medium transition-colors hover:bg-brand-20 hover:text-brand-dark" aria-label="Dismiss notification">&times;</button>';

    el.querySelector(".font-semibold").textContent = title;
    const msg = el.querySelector(".text-ink-medium");
    if (message) msg.textContent = message;
    else msg.remove();

    const close = () => el.remove();
    el.querySelector("button").addEventListener("click", close);
    $("#toast-stack").appendChild(el);
    setTimeout(close, 4000);
  }

  /* ---------------------------------------------------------
     Modal (with focus trap + focus restore)
     --------------------------------------------------------- */

  let lastFocused = null;

  function openModal(opts) {
    lastFocused = document.activeElement;

    $("#modal-head").innerHTML =
      '<div class="min-w-0">' +
      '<div id="modal-title" class="font-heading text-sm font-bold leading-subheading text-ink"></div>' +
      '<div class="mt-1 text-[11px] leading-body text-ink-medium"></div>' +
      "</div>" +
      '<button type="button" class="ml-auto grid h-7 w-7 shrink-0 place-items-center rounded-sm text-lg leading-none text-ink-medium transition-colors hover:bg-brand-20 hover:text-brand-dark" data-modal-close aria-label="Close dialog">&times;</button>';
    $("#modal-head .font-bold").textContent = opts.title || "";
    const desc = $("#modal-head .text-ink-medium");
    if (opts.description) desc.textContent = opts.description;
    else desc.remove();

    $("#modal-body").innerHTML = opts.body || "";
    $("#modal-foot").innerHTML = opts.footer || "";
    $("#modal-backdrop").hidden = false;
    if (typeof opts.onMount === "function") opts.onMount($("#modal"));

    const first = $("#modal").querySelector("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])");
    if (first) first.focus();
  }

  function closeModal() {
    $("#modal-backdrop").hidden = true;
    if (lastFocused && document.contains(lastFocused)) lastFocused.focus();
    lastFocused = null;
  }

  function isModalOpen() {
    return !$("#modal-backdrop").hidden;
  }

  function confirmAction(opts) {
    openModal({
      title: opts.title,
      description: opts.description,
      body: opts.body || "",
      footer:
        '<button type="button" class="btn-quiet" data-modal-close>Cancel</button>' +
        '<button type="button" class="btn-primary" id="confirm-ok">' +
        (opts.confirmText || "Confirm") +
        "</button>",
      onMount: () => {
        $("#confirm-ok").addEventListener("click", () => {
          closeModal();
          if (opts.onConfirm) opts.onConfirm();
        });
      },
    });
  }

  function trapFocus(e) {
    if (!isModalOpen() || e.key !== "Tab") return;
    const focusables = $$(
      "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])",
      $("#modal")
    ).filter((n) => !n.disabled);
    if (!focusables.length) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  /* ---------------------------------------------------------
     Case list (sidebar)
     --------------------------------------------------------- */

  function renderCaseList(cases) {
    const list = $("#case-list");
    if (!cases.length) {
      list.innerHTML =
        '<p class="px-2.5 py-2 text-[11px] leading-body text-ink-medium">No cases available.</p>';
      return;
    }

    list.innerHTML = cases
      .map((c) => {
        const active = c.record_id === state.selectedId;
        const meta = [String(c.record_id).padStart(3, "0"), c.month, c.office]
          .filter(Boolean)
          .join(" · ");
        return (
          '<button type="button" class="case-item' + (active ? " is-active" : "") + '" ' +
          'data-record-id="' + esc(c.record_id) + '" ' +
          'role="option" aria-selected="' + active + '" ' +
          'tabindex="' + (active ? "0" : "-1") + '" ' +
          (active ? 'aria-current="true"' : "") + ">" +
          '<span class="case-dot" aria-hidden="true"></span>' +
          '<span class="min-w-0 flex-1 text-left">' +
          '<span class="block truncate text-[13px] font-medium">Case ' +
          esc(String(c.record_id).padStart(3, "0")) +
          "</span>" +
          '<span class="block truncate text-[11px]">' + esc(meta) + "</span>" +
          "</span></button>"
        );
      })
      .join("");
  }

  /* ---------------------------------------------------------
     Context checklist
     --------------------------------------------------------- */

  function checklistValue(variable) {
    if (variable.kind === "boolean") {
      const on = variable.value === true;
      return (
        '<span class="check ' + (on ? "is-checked" : "") + '" role="img" ' +
        'aria-label="' + (on ? CHECKLIST_COPY.checked : CHECKLIST_COPY.unchecked) + '">' +
        '<svg class="h-3 w-3" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
        'stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7"/></svg>' +
        "</span>"
      );
    }
    return '<span class="dot-value">' + esc(variable.value) + "</span>";
  }

  function renderContext(detail) {
    const variables = detail.variables || [];
    if (!variables.length) {
      $("#context-list").innerHTML =
        '<li class="px-2.5 py-2 text-[11px] text-ink-medium">No context variables recorded.</li>';
      return;
    }

    $("#context-list").innerHTML = variables
      .map(
        (v) =>
          '<li class="check-row' + (v.kind === "boolean" ? " is-boolean" : "") + '">' +
          '<span class="min-w-0 flex-1 text-[13px] leading-body text-ink">' + esc(v.label) + "</span>" +
          checklistValue(v) +
          "</li>"
      )
      .join("");
  }

  /* ---------------------------------------------------------
     Eligibility suggestion + analysis
     --------------------------------------------------------- */

  function renderEligibility(eligibility) {
    const panel = $("#eligibility");
    const target = eligibility && eligibility.target;
    const status = eligibility && eligibility.status;

    if (!status) {
      panel.innerHTML =
        '<p class="text-[13px] leading-body text-ink-medium">' + esc(ELIGIBILITY_COPY.empty) + "</p>";
      return;
    }

    // Inclusion reads as the positive outcome; exclusion stays neutral-gray so
    // the panel does not imply a recommendation either way.
    const tone = target === "INCLUSION" ? "is-inclusion" : "is-exclusion";
    panel.innerHTML =
      '<div class="eligibility-banner ' + tone + '">' +
      '<span class="eligibility-target">' + esc(target) + "</span>" +
      '<span class="eligibility-status">' + esc(status) + "</span>" +
      "</div>" +
      '<p class="caution" role="note">' +
      '<svg class="caution-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
      '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5h.01"/></svg>' +
      "<span>" + esc(ELIGIBILITY_COPY.caution) + "</span></p>";
  }

  function renderAnalysis(analysis) {
    const el = $("#analysis-body");
    if (analysis) el.textContent = analysis;
    else el.innerHTML = '<span class="text-ink-medium">' + esc(ANALYSIS_COPY.empty) + "</span>";
  }

  /* ---------------------------------------------------------
     Case selection
     --------------------------------------------------------- */

  function setActiveCase(recordId) {
    state.selectedId = recordId;
    $$("#case-list .case-item").forEach((el) => {
      const active = Number(el.dataset.recordId) === recordId;
      el.classList.toggle("is-active", active);
      el.setAttribute("aria-selected", String(active));
      el.tabIndex = active ? 0 : -1;
      if (active) el.setAttribute("aria-current", "true");
      else el.removeAttribute("aria-current");
    });
  }

  async function selectCase(recordId, options) {
    const opts = options || {};
    setActiveCase(recordId);

    let detail;
    try {
      detail = await window.CaseApi.getCase(recordId);
    } catch (err) {
      toast("Could not load case", "The case data could not be retrieved.");
      return;
    }

    // Guard against a slow response landing after a newer selection.
    if (state.selectedId !== recordId) return;

    const label = "Case " + String(recordId).padStart(3, "0");
    $("#page-title").textContent = label;
    $("#page-subtitle").textContent = [detail.month, detail.office].filter(Boolean).join(" · ");

    renderContext(detail);
    renderEligibility(detail.eligibility);
    renderAnalysis(detail.analysis);

    if (opts.announce) toast("Case selected", label + " is now the active case.");
  }

  /* Keyboard navigation across the case list. */
  function onCaseListKeydown(e) {
    const ids = state.recordIds;
    if (!ids.length) return;
    const idx = ids.indexOf(state.selectedId);

    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const delta = e.key === "ArrowDown" ? 1 : -1;
      const next = Math.min(ids.length - 1, Math.max(0, idx + delta));
      selectCase(ids[next]);
      const el = $('#case-list [data-record-id="' + ids[next] + '"]');
      if (el) el.focus();
    } else if (e.key === "Home") {
      e.preventDefault();
      selectCase(ids[0]);
      const el = $('#case-list [data-record-id="' + ids[0] + '"]');
      if (el) el.focus();
    } else if (e.key === "End") {
      e.preventDefault();
      const last = ids[ids.length - 1];
      selectCase(last);
      const el = $('#case-list [data-record-id="' + last + '"]');
      if (el) el.focus();
    }
  }

  /* ---------------------------------------------------------
     Wire up
     --------------------------------------------------------- */

  function setActive(selector, el) {
    $$(selector).forEach((n) => {
      n.classList.remove("is-active");
      n.removeAttribute("aria-current");
    });
    el.classList.add("is-active");
    el.setAttribute("aria-current", "page");
  }

  function init() {
    /* ---- Sidebar drawer (below lg) ---- */
    const sidebar = $("#sidebar");
    const backdrop = $("#sidebar-backdrop");
    const toggle = $("#sidebar-toggle");
    const closeBtn = $("#sidebar-close");

    const drawerOpen = () => !backdrop.classList.contains("hidden");
    const openDrawer = () => {
      sidebar.classList.remove("-translate-x-full");
      backdrop.classList.remove("hidden");
      toggle.setAttribute("aria-expanded", "true");
      closeBtn.focus();
    };
    const closeDrawer = () => {
      sidebar.classList.add("-translate-x-full");
      backdrop.classList.add("hidden");
      toggle.setAttribute("aria-expanded", "false");
    };

    toggle.addEventListener("click", () => (drawerOpen() ? closeDrawer() : openDrawer()));
    closeBtn.addEventListener("click", closeDrawer);
    backdrop.addEventListener("click", closeDrawer);

    // The drawer only exists below lg; reset it when entering the desktop breakpoint.
    // MediaQueryList.addEventListener is missing in older Gecko/WebKit, so fall
    // back to the deprecated addListener where necessary.
    const desktopQuery = window.matchMedia("(min-width: 1024px)");
    const onBreakpointChange = (e) => {
      if (e.matches) closeDrawer();
    };
    if (typeof desktopQuery.addEventListener === "function") {
      desktopQuery.addEventListener("change", onBreakpointChange);
    } else if (typeof desktopQuery.addListener === "function") {
      desktopQuery.addListener(onBreakpointChange);
    }

    /* ---- Sidebar navigation (mock sections) ---- */
    $$(".nav-item").forEach((item) => {
      item.addEventListener("click", () => {
        setActive(".nav-item", item);
        closeDrawer();
        toast(item.dataset.view, "This section is a mock placeholder.");
      });
    });

    /* ---- Case selection ---- */
    $("#case-list").addEventListener("click", (e) => {
      const item = e.target.closest("[data-record-id]");
      if (!item) return;
      selectCase(Number(item.dataset.recordId));
      closeDrawer();
    });
    $("#case-list").addEventListener("keydown", onCaseListKeydown);

    /* ---- Detail actions ---- */
    $("#btn-approve").addEventListener("click", () => {
      const label = "Case " + String(state.selectedId).padStart(3, "0");
      confirmAction({
        title: "Approve inclusion?",
        description: label + " will be marked as included.",
        confirmText: "Approve",
        onConfirm: () => toast("Inclusion approved", label + " marked as approved."),
      });
    });

    $("#btn-exclude").addEventListener("click", () => {
      const label = "Case " + String(state.selectedId).padStart(3, "0");
      confirmAction({
        title: "Exclude this case?",
        description: label + " will be marked as excluded.",
        confirmText: "Exclude",
        onConfirm: () => toast("Case excluded", label + " marked as excluded."),
      });
    });

    /* ---- Modal + global keyboard ---- */
    $("#modal-backdrop").addEventListener("click", (e) => {
      if (e.target.id === "modal-backdrop" || e.target.closest("[data-modal-close]")) closeModal();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Tab") return trapFocus(e);
      if (e.key !== "Escape") return;
      if (isModalOpen()) closeModal();
      else if (drawerOpen()) closeDrawer();
    });

    /* ---- Load cases, then the first one ---- */
    window.CaseApi.getCases()
      .then((cases) => {
        state.recordIds = cases.map((c) => c.record_id);
        if (!state.recordIds.length) {
          renderCaseList([]);
          return;
        }
        state.selectedId = state.recordIds[0];
        renderCaseList(cases);
        return selectCase(state.recordIds[0]);
      })
      .catch(() => {
        renderCaseList([]);
        toast("Could not load cases", "The case list could not be retrieved.");
      });
  }

  document.addEventListener("DOMContentLoaded", init);

  window.Dashboard = { toast, openModal, closeModal };
})();
