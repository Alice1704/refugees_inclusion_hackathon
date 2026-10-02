/* ---------------------------------------------------------------------------
 * Client for the case and operator review APIs.
 * Exposed on window.CaseApi for dashboard.js.
 * ------------------------------------------------------------------------- */
(function () {
  "use strict";

  async function request(url, options) {
    const response = await fetch(url, {
      ...options,
      headers: { Accept: "application/json", ...(options && options.headers) },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const error = new Error(payload.error || "Request failed (" + response.status + ") for " + url);
      error.status = response.status;
      throw error;
    }
    return response.json();
  }

  /** Summary rows for the case selector: [{record_id, month, office}] */
  async function getCases() {
    const payload = await request("/api/cases");
    return payload.cases || [];
  }

  async function getPending() {
    const payload = await request("/api/case/pending");
    return payload.cases || [];
  }

  function getCashy(recordId) {
    return request("/api/cashy/" + encodeURIComponent(recordId));
  }

  function getCase(recordId) {
    return request("/api/cases/" + encodeURIComponent(recordId));
  }

  function getComparison(recordId) {
    return request("/api/comparison/" + encodeURIComponent(recordId));
  }

  function getSurvey(recordId) {
    return request("/api/survey/" + encodeURIComponent(recordId));
  }

  function review(recordId, decision, reason, editing) {
    return request("/api/case/" + encodeURIComponent(recordId) + "/review", {
      method: editing ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, reason }),
    });
  }

  window.CaseApi = {
    getCases, getPending, getCase, getCashy, getComparison, getSurvey, review,
  };
})();
