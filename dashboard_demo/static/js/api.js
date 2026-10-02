/* ---------------------------------------------------------------------------
 * Read-only client for the case API.
 * Exposed on window.CaseApi for dashboard.js.
 * ------------------------------------------------------------------------- */
(function () {
  "use strict";

  async function request(url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) {
      throw new Error("Request failed (" + response.status + ") for " + url);
    }
    return response.json();
  }

  /** Summary rows for the case selector: [{record_id, month, office}] */
  async function getCases() {
    const payload = await request("/api/cases");
    return payload.cases || [];
  }

  /** Normalised detail payload for one case. */
  function getCase(recordId) {
    return request("/api/cases/" + encodeURIComponent(recordId));
  }

  window.CaseApi = { getCases, getCase };
})();
