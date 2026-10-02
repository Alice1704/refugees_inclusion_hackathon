/* ---------------------------------------------------------------------------
 * UI copy and formatting constants.
 * Case data itself comes from the API (see api.js); navigation structure is
 * rendered by Jinja, so neither lives here.
 * ------------------------------------------------------------------------- */
(function () {
  "use strict";

  /* Wording for the eligibility panel. The suggestion is model output, so the
     UI states that plainly rather than presenting it as a decision. */
  const ELIGIBILITY_COPY = {
    heading: "Eligibility suggestion",
    caution:
      "Cashy's suggestion, not a decision. Review the analysis before you act on it.",
    empty: "No eligibility suggestion was produced for this case.",
  };

  const ANALYSIS_COPY = {
    heading: "Cashy analysis",
    empty: "No analysis was produced for this case.",
  };

  const CHECKLIST_COPY = { checked: "Yes", unchecked: "No" };

  window.UiData = { ELIGIBILITY_COPY, ANALYSIS_COPY, CHECKLIST_COPY };
})();
