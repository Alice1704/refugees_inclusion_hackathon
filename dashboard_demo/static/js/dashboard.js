(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const { ELIGIBILITY_COPY, ANALYSIS_COPY, CHECKLIST_COPY } = window.UiData;

  const state = {
    cases: [], recordIds: [], pendingIds: new Set(), remindedIds: new Set(),
    selectedId: null, selectionVersion: 0, reviewStatus: "pending", review: null,
  };

  /* ---------------------------------------------------------
     Loading screen

     Two different waits share one screen. The first paint has nothing behind it
     yet - the case list is empty until the fetch resolves - so it claims the
     screen outright. A case switch is different: a comparison answered from warm
     weights returns in ~20ms, so that one waits SHOW_AFTER_MS first and usually
     never appears.
     --------------------------------------------------------- */

  // Long enough that a comparison answered from warm weights never flashes the
  // screen, short enough that a real load does not feel stalled.
  const SHOW_AFTER_MS = 350;

  const activeLoaders = new Set();

  /* Claim the loading screen for `delay` milliseconds - pass 0 to take it now.
     Returns a release function that is safe to call more than once.

     Each claim owns its own timer rather than sharing one, so switching case
     mid-load cannot let a superseded comparison cancel the timer of the one that
     replaced it. The screen clears once nothing is holding it: no claim has
     revealed it and none is still waiting to, which is checked rather than
     counted so the order claims are released in does not matter. */
  function claimLoading(delay) {
    const claim = { timer: null, shown: false };
    activeLoaders.add(claim);

    const reveal = () => {
      claim.timer = null;
      const screen = $("#loading-screen");
      if (!screen) return;
      // Already visible for the first paint, so this is a no-op there; kept so
      // both callers go through one path.
      screen.hidden = false;
      $("main").setAttribute("aria-busy", "true");
      claim.shown = true;
    };

    if (delay > 0) claim.timer = window.setTimeout(reveal, delay);
    else reveal();

    return function release() {
      activeLoaders.delete(claim);
      if (claim.timer !== null) {
        window.clearTimeout(claim.timer);
        claim.timer = null;
      }
      const held = Array.from(activeLoaders).some((other) => other.shown || other.timer !== null);
      if (held) return;
      const screen = $("#loading-screen");
      if (!screen) return;
      screen.hidden = true;
      $("main").removeAttribute("aria-busy");
    };
  }

  function watchModelLoad() {
    return claimLoading(SHOW_AFTER_MS);
  }

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
          '<span class="block truncate text-[11px]">' + esc(meta) +
          (state.pendingIds.has(c.record_id) ? " · Pending" : " · Awaiting survey") +
          "</span>" +
          "</span></button>"
        );
      })
      .join("");
  }

  function renderContext(detail) {
    const variables = detail.variables || [];
    $("#context-list").innerHTML = variables.length
      ? variables.map((variable) => {
        const value = variable.kind === "boolean"
          ? (variable.value ? CHECKLIST_COPY.checked : CHECKLIST_COPY.unchecked)
          : String(variable.value);
        return '<li class="check-row"><span class="min-w-0 flex-1 text-[13px] leading-body text-ink">' +
          esc(variable.label) + '</span><span class="dot-value">' + esc(value) + "</span></li>";
      }).join("")
      : '<li class="px-2.5 py-2 text-[11px] text-ink-medium">No external variables recorded.</li>';
  }

  /* ---------------------------------------------------------
     Eligibility suggestion + analysis
     --------------------------------------------------------- */

  function lockEligibility(locked) {
    const disclosure = $("#eligibility-disclosure");
    const summary = disclosure.querySelector("summary");
    disclosure.open = false;
    summary.tabIndex = locked ? -1 : 0;
    summary.setAttribute("aria-disabled", String(locked));
    $("#eligibility-lock-note").hidden = !locked;
    if (locked) $("#eligibility").textContent = "";
  }

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

  function renderReviewStatus(survey) {
    state.reviewStatus = survey.status;
    state.review = survey.review;
    const editable = survey.status === "pending" || survey.status === "awaiting_survey";
    const revising = survey.status === "awaiting_survey";
    const approveButton = $("#btn-approve");
    const excludeButton = $("#btn-exclude");
    approveButton.disabled = !editable;
    excludeButton.disabled = !editable;
    approveButton.textContent = revising ? "Revise: approve" : "Approve inclusion";
    excludeButton.textContent = revising ? "Revise: exclude" : "Exclude";
    approveButton.classList.toggle("btn-primary", !revising);
    approveButton.classList.toggle("btn-secondary", revising);
    $("#btn-survey").hidden = survey.status !== "awaiting_survey";
    $("#review-status").textContent = survey.status === "pending"
      ? "Pending operator decision. Your choice is independent of Cashy's suggestion."
      : survey.status === "awaiting_survey"
        ? "Decision saved. You can revise it until the survey is completed."
        : "Case completed.";
  }

  async function openSurveyDialog(recordId) {
    try {
      const survey = await window.CaseApi.getSurvey(recordId);
      let bodyHtml = '';
      if (survey.questions && survey.questions.length) {
        survey.questions.forEach((q, idx) => {
          // A set of radios or checkboxes is one control, so it is a fieldset
          // with a legend. A <label for> would dangle - no input carries the bare
          // q-<id> - and the options would be announced without the question.
          // Text and rating keep a real label because those do have that id.
          const isGroup = !!(q.options && q.type !== 'text' && q.type !== 'rating');
          const tag = isGroup ? 'fieldset' : 'div';
          bodyHtml += '<' + tag + ' class="mb-4">';
          if (isGroup) {
            bodyHtml += '<legend class="field-label">' + esc(q.text) + '</legend>';
          } else {
            bodyHtml += '<label class="field-label" for="q-' + esc(q.id) + '">' + esc(q.text) + '</label>';
          }
          if (q.type === 'text') {
            // maxlength is the browser's half of the cap; the server enforces the
            // other half, so a paste longer than the cap is cut rather than sent.
            bodyHtml += '<textarea class="field-area" rows="4" id="q-' + esc(q.id) + '" data-qid="' +
              esc(q.id) + '" maxlength="' + esc(q.max_length) + '" placeholder="' +
              esc(q.placeholder || '') + '"></textarea>';
            bodyHtml += '<div class="field-counter" data-counter-for="' + esc(q.id) + '">0 / ' +
              esc(q.max_length) + '</div>';
          } else if (q.type === 'rating' && q.options) {
            bodyHtml += '<select class="field mt-2" id="q-' + esc(q.id) + '" data-qid="' + esc(q.id) + '">';
            q.options.forEach(o => {
              bodyHtml += '<option value="' + esc(o) + '">' + esc(o) + '</option>';
            });
            bodyHtml += '</select>';
          } else if (q.type === 'multiple' && q.options) {
            q.options.forEach(o => {
              bodyHtml += '<div class="mt-2 flex items-center gap-2">';
              bodyHtml += '<input type="checkbox" id="q-' + esc(q.id) + '-' + idx + '-' + esc(o) + '" data-qid="' + esc(q.id) + '" value="' + esc(o) + '">';
              bodyHtml += '<label for="q-' + esc(q.id) + '-' + idx + '-' + esc(o) + '">' + esc(o) + '</label>';
              bodyHtml += '</div>';
            });
          } else if (q.options) {
            q.options.forEach(o => {
              bodyHtml += '<div class="mt-2 flex items-center gap-2">';
              bodyHtml += '<input type="radio" name="' + esc(q.id) + '" data-qid="' + esc(q.id) + '" value="' + esc(o) + '" id="q-' + esc(q.id) + '-' + esc(o) + '">';
              bodyHtml += '<label for="q-' + esc(q.id) + '-' + esc(o) + '">' + esc(o) + '</label>';
              bodyHtml += '</div>';
            });
          }
          bodyHtml += '</' + tag + '>';
        });
      } else {
        bodyHtml = '<p>The survey questions are coming soon. This case remains awaiting survey.</p>';
      }
      openModal({
        title: "Operator survey",
        description: "Case " + String(recordId).padStart(3, "0") + " · Decision saved",
        body: bodyHtml,
        footer: '<button type="button" class="btn-quiet" data-modal-close>Cancel</button><button type="button" class="btn-primary" id="survey-submit">Submit survey</button>',
        onMount: () => {
          // Count against the same number the server will enforce, so what the
          // operator sees is what they are judged against.
          $$("[data-counter-for]").forEach(counter => {
            const qid = counter.dataset.counterFor;
            const field = $('textarea[data-qid="' + qid + '"]');
            const max = Number(field.getAttribute("maxlength"));
            const paint = () => {
              const used = field.value.length;
              counter.textContent = used + " / " + max;
              counter.classList.toggle("is-at-cap", used >= max);
            };
            field.addEventListener("input", paint);
            paint();
          });
          $("#survey-submit").addEventListener("click", async () => {
            const answers = {};
            survey.questions && survey.questions.forEach(q => {
              if (q.type === 'text') {
                const field = $('textarea[data-qid="' + q.id + '"]');
                answers[q.id] = field ? field.value.trim() : '';
              } else if (q.type === 'multiple') {
                answers[q.id] = [];
                $$('input[data-qid="' + q.id + '"]:checked').forEach(cb => {
                  answers[q.id].push(cb.value);
                });
              } else if (q.type === 'rating') {
                const sel = $('select[data-qid="' + q.id + '"]');
                answers[q.id] = sel ? sel.value : '';
              } else {
                const checked = $('input[data-qid="' + q.id + '"]:checked');
                answers[q.id] = checked ? checked.value : '';
              }
            });
            try {
              await window.CaseApi.submitSurvey(recordId, answers);
              if (isModalOpen()) closeModal();
              // The case is finished, so it leaves the list and the operator
              // moves on instead of sitting on a case that is no longer theirs
              // to complete. The server drops it from /api/cases too; doing it
              // here keeps the list honest without waiting for a reload.
              const at = state.cases.findIndex((c) => c.record_id === recordId);
              state.cases = state.cases.filter((c) => c.record_id !== recordId);
              state.recordIds = state.cases.map((c) => c.record_id);
              state.pendingIds.delete(recordId);
              const next = state.cases[Math.min(at, state.cases.length - 1)];
              if (next) {
                renderCaseList(state.cases);
                await selectCase(next.record_id);
              } else {
                state.selectedId = null;
                renderCaseList([]);
                renderReviewStatus({ status: "completed", review: survey.review });
              }
              toast("Survey submitted", next
                ? "Moving to the next case."
                : "That was the last case. The list is empty.");
            } catch (err) {
              toast("Error", err.message);
            }
          });
        },
      });
    } catch (err) {
      toast("Error", err.message);
    }
  }

  function maybeShowReminder(recordId) {
    if (state.remindedIds.has(recordId)) return;
    state.remindedIds.add(recordId);
    if (Math.random() >= 0.2) return;
    openModal({
      title: "Review with care",
      body: "<p>All data has been processed by AI and could be wrong. Keep an independent, critical eye on this case.</p>",
      footer: '<button type="button" class="btn-primary" data-modal-close>Continue review</button>',
    });
  }

  function showCriticalWarning(recordId) {
    openModal({
      title: "Critical case: review with care",
      description: "Case " + String(recordId).padStart(3, "0"),
      body: "<p>The judgement engine flagged an elevated bias risk. Review the external variables and Cashy's analysis carefully. AI-processed data may be wrong.</p>",
      footer: '<button type="button" class="btn-primary" data-modal-close>Continue review</button>',
    });
  }

  function startReview(decision) {
    if (state.selectedId === null ||
        !["pending", "awaiting_survey"].includes(state.reviewStatus)) return;
    const recordId = state.selectedId;
    const approve = decision === "approved";
    const editing = state.reviewStatus === "awaiting_survey";
    openModal({
      title: approve ? "Approve inclusion?" : "Exclude this case?",
      description: "Case " + String(recordId).padStart(3, "0") +
        " · Your decision is independent of Cashy's suggestion.",
      body: '<p id="review-error" class="mt-2 text-[12px] text-ink" role="alert"></p>',
      footer: '<button type="button" class="btn-quiet" data-modal-close>Cancel</button>' +
        '<button type="button" class="btn-primary" id="confirm-ok">' +
        (editing ? "Update decision" : (approve ? "Approve" : "Exclude")) + "</button>",
      onMount: () => {
        $("#confirm-ok").addEventListener("click", async () => {
          $("#confirm-ok").disabled = true;
          try {
            await window.CaseApi.review(recordId, decision, editing);
            state.pendingIds.delete(recordId);
            renderCaseList(state.cases);
            if (state.selectedId === recordId) {
              setActiveCase(recordId);
              renderReviewStatus({
                status: "awaiting_survey", review: { decision },
              });
            }
            if (isModalOpen()) closeModal();
            if (state.selectedId === recordId) openSurveyDialog(recordId);
            toast(editing ? "Decision updated" : "Decision recorded",
              "Case awaiting the operator survey.");
          } catch (err) {
            if ($("#review-error")) $("#review-error").textContent = err.message || "Could not save the decision.";
            if ($("#confirm-ok")) $("#confirm-ok").disabled = false;
          }
        });
      },
    });
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
    const version = ++state.selectionVersion;
    setActiveCase(recordId);
    // Clear the previous case before requesting the new comparison.
    $("#context-list").textContent = "";
    $("#context-list").closest("details").open = false;
    lockEligibility(false);
    $("#eligibility").textContent = "";
    $("#analysis-body").textContent = "";
    $("#review-status").textContent = "Loading case...";
    $("#btn-survey").hidden = true;
    $("#btn-approve").disabled = true;
    $("#btn-exclude").disabled = true;
    state.reviewStatus = "loading";
    state.review = null;

    let detail, cashy, comparison, survey;
    // Only the comparison touches the model, so only it arms the loading screen.
    // try/finally rather than .finally() on the promise, because the same stop
    // function has to cover the failure path and the superseded-by-a-newer-
    // selection early return below.
    const stopLoading = watchModelLoad();
    try {
      [detail, cashy, comparison, survey] = await Promise.all([
        window.CaseApi.getCase(recordId),
        window.CaseApi.getCashy(recordId),
        window.CaseApi.getComparison(recordId),
        window.CaseApi.getSurvey(recordId),
      ]);
    } catch (err) {
      stopLoading();
      if (version === state.selectionVersion) {
        toast("Could not load case", "The case data could not be retrieved.");
      }
      return;
    }
    stopLoading();

    // Guard against a slow response landing after a newer selection.
    if (version !== state.selectionVersion) return;

    const label = "Case " + String(recordId).padStart(3, "0");
    const summary = state.cases.find((item) => item.record_id === recordId) || {};
    $("#page-title").textContent = label;
    $("#page-subtitle").textContent = [summary.month, summary.office].filter(Boolean).join(" · ");

    renderContext(detail);
    const locked = comparison.text_match_percentage < comparison.threshold;
    lockEligibility(locked);
    const suggestion = cashy.decision || {};
    if (!locked) {
      renderEligibility({
        target: suggestion.eligibility_target, status: suggestion.eligibility_status,
      });
    }
    renderAnalysis(cashy.analysis);
    renderReviewStatus(survey);
    if (comparison.show_warning) showCriticalWarning(recordId);
    else maybeShowReminder(recordId);

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
    $("#btn-approve").addEventListener("click", () => startReview("approved"));
    $("#btn-exclude").addEventListener("click", () => startReview("rejected"));
    $("#btn-survey").addEventListener("click", () => openSurveyDialog(state.selectedId));
    $("#eligibility-disclosure").addEventListener("toggle", (event) => {
      if (event.target.querySelector("summary").getAttribute("aria-disabled") === "true") {
        event.target.open = false;
      }
    });
    $("#eligibility-disclosure summary").addEventListener("click", (event) => {
      if (event.currentTarget.getAttribute("aria-disabled") === "true") event.preventDefault();
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
    // Hold the screen the markup already painted until there is a case to look
    // at. Released in finally so a failed boot shows the empty-list state and
    // the toast instead of leaving the operator on a spinner that never clears.
    const releaseBoot = claimLoading(0);
    Promise.all([window.CaseApi.getCases(), window.CaseApi.getPending()])
      .then(([cases, pendingIds]) => {
        state.cases = cases;
        state.pendingIds = new Set(pendingIds);
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
      })
      .finally(releaseBoot);
  }

  document.addEventListener("DOMContentLoaded", init);

  window.Dashboard = { toast, openModal, closeModal };
})();
