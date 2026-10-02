import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from app import create_app
from judgement import compare, semantic_match


class DisclosureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.details = []

    def handle_starttag(self, tag, attrs):
        if tag == "details":
            self.details.append(dict(attrs))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.embed_patch = patch("judgement.embed", side_effect=self.fake_embeddings)
        self.embed_patch.start()
        self.addCleanup(self.embed_patch.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "REVIEWS_FILE": Path(self.directory.name) / "reviews.json",
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.directory.cleanup()

    @staticmethod
    def fake_embeddings(texts):
        # The semantic matcher is tested separately; route tests never download a model.
        if texts[0].startswith("One-person household"):
            return ([1.0, 0.0], [1.0, 0.0])
        return ([1.0, 0.0], [0.0, 1.0])

    def test_pending_and_original_records(self):
        self.assertEqual(self.client.get("/api/case/pending").json, {"cases": [4, 324, 889]})
        for case_id in (4, 324, 889):
            with self.subTest(case_id=case_id):
                for kind, url in (("scorecard", "case"), ("cashy", "cashy")):
                    expected = json.loads(
                        (Path(self.app.config["OUTPUTS_DIR"]) /
                         f"{kind}-record-{case_id:03d}.json").read_text(encoding="utf-8")
                    )
                    self.assertEqual(self.client.get(f"/api/{url}/{case_id}").json, expected)
        self.assertEqual(self.client.get("/api/case/999").status_code, 404)
        self.assertEqual(self.client.get("/api/cashy/999").status_code, 404)
        self.assertEqual(self.client.get("/api/comparison/999").status_code, 404)

    def test_comparison_and_context_diagnostics(self):
        agreed = self.client.get("/api/comparison/4").json
        self.assertFalse(agreed["decisions_diverge"])
        self.assertFalse(agreed["show_warning"])
        self.assertEqual(agreed["bias_risk"], "low")
        self.assertEqual(agreed["text_match_percentage"], 100.0)
        self.assertTrue(agreed["decision_match"])
        self.assertEqual(agreed["differences"], [])
        self.assertEqual(agreed["context"]["record_id"], 4)
        self.assertTrue(agreed["sentences"])

        for case_id in (324, 889):
            with self.subTest(case_id=case_id):
                result = self.client.get(f"/api/comparison/{case_id}").json
                self.assertTrue(result["decisions_diverge"])
                self.assertTrue(result["show_warning"])
                self.assertEqual(result["bias_risk"], "high")
                self.assertLess(result["text_match_percentage"], 75.0)
                self.assertFalse(result["decision_match"])
                self.assertIn("decision.eligibility_target",
                              [difference["field"] for difference in result["differences"]])
                self.assertEqual(result["context"]["record_id"], case_id)

    def test_threshold_is_strict_and_requires_divergence(self):
        scorecard = {"record_id": 1, "analysis": "Interview", "decision": {"eligibility_target": "EXCLUSION"}}
        cashy = {"analysis": "Reasoning", "target": {"eligibility_target": "INCLUSION"}}
        for block in ("interview", "household", "demographics", "needs_and_coping",
                      "scores", "administrative_flags"):
            scorecard[block] = cashy[block] = {}
        context = {"description": "Context", "external_variables": {}}
        with patch("judgement.semantic_match") as matcher:
            matcher.return_value = {"text_match_percentage": 75.0, "decision_match": False}
            self.assertFalse(compare(scorecard, cashy, context)["show_warning"])
            matcher.return_value = {"text_match_percentage": 74.99, "decision_match": False}
            self.assertTrue(compare(scorecard, cashy, context)["show_warning"])
            matcher.return_value = {"text_match_percentage": 74.99, "decision_match": True}
            self.assertFalse(compare(scorecard, cashy, context)["show_warning"])

    def test_semantic_match_uses_cosine_and_decision_independently(self):
        with patch("judgement.embed", return_value=([1.0, 0.0], [0.8, 0.6])):
            result = semantic_match(
                {"eligibility_target": "INCLUSION"}, "Interview",
                {"eligibility_target": "EXCLUSION"}, "Cashy",
            )
        self.assertEqual(result, {"text_match_percentage": 80.0, "decision_match": False})

    def test_review_persists_and_survey_is_not_yet_submittable(self):
        self.assertEqual(self.client.get("/api/survey/324").json["status"], "pending")
        self.assertEqual(self.client.post("/api/survey/324").status_code, 409)
        self.assertEqual(self.client.post("/api/case/324/review", json={
            "decision": "approved", "reason": "  Operator's own assessment  "
        }).status_code, 201)
        self.assertEqual(self.client.get("/api/case/pending").json, {"cases": [4, 889]})
        survey = self.client.get("/api/survey/324").json
        self.assertEqual(survey, {
            "case_id": 324, "status": "awaiting_survey", "enabled": False,
            "questions": [], "review": {
                "decision": "approved", "reason": "Operator's own assessment"
            },
        })
        self.assertEqual(self.client.post("/api/survey/324", json={"answers": {}}).status_code, 501)
        self.assertEqual(self.client.post("/api/case/324/review", json={
            "decision": "rejected", "reason": "Other"
        }).status_code, 409)
        reloaded = create_app({
            "TESTING": True, "REVIEWS_FILE": Path(self.directory.name) / "reviews.json"
        }).test_client()
        self.assertEqual(reloaded.get("/api/case/pending").json, {"cases": [4, 889]})
        stored = json.loads((Path(self.directory.name) / "reviews.json").read_text())
        self.assertEqual(stored["324"]["decision"], "approved")
        self.assertEqual(stored["324"]["reason"], "Operator's own assessment")

    def test_review_can_change_until_survey_completion(self):
        url = "/api/case/889/review"
        self.assertEqual(self.client.put(url, json={
            "decision": "approved", "reason": "Too early"
        }).status_code, 409)
        self.client.post(url, json={"decision": "approved", "reason": "Initial view"})
        updated = self.client.put(url, json={
            "decision": "rejected", "reason": "  Revised after checking  "
        })
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json["reason"], "Revised after checking")
        self.assertEqual(self.client.get("/api/survey/889").json["review"], {
            "decision": "rejected", "reason": "Revised after checking"
        })
        self.assertEqual(self.client.get("/api/case/pending").json["cases"], [4, 324])
        path = Path(self.directory.name) / "reviews.json"
        saved = json.loads(path.read_text())
        saved["889"]["status"] = "completed"
        path.write_text(json.dumps(saved))
        self.assertEqual(self.client.put(url, json={
            "decision": "approved", "reason": "Too late"
        }).status_code, 409)

    def test_invalid_review(self):
        for body in ({}, {"decision": "yes", "reason": "ok"},
                     {"decision": "rejected", "reason": "  "},
                     {"decision": "approved", "reason": 1}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/api/case/4/review", json=body).status_code, 400)
        self.assertEqual(self.client.post("/api/case/999/review", json={
            "decision": "rejected", "reason": "Not found"
        }).status_code, 404)
        self.assertEqual(self.client.get("/api/case/pending").json, {"cases": [4, 324, 889]})

    def test_rejected_is_independent_of_cashy_and_survey_unknown_case(self):
        self.assertEqual(self.client.post("/api/case/4/review", json={
            "decision": "rejected", "reason": "Independent judgement"
        }).json["decision"], "rejected")
        self.assertEqual(self.client.get("/api/survey/999").status_code, 404)
        self.assertEqual(self.client.post("/api/survey/999").status_code, 404)

    def test_dashboard_routes_and_assets_survive_the_pull(self):
        self.assertEqual(
            [case["record_id"] for case in self.client.get("/api/cases").json["cases"]],
            [4, 324, 889],
        )
        self.assertEqual(
            self.client.get("/api/cases/324").json["eligibility"]["target"], "INCLUSION"
        )
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        for marker in (b"Cashy suggestion", b"External variables", b"context-list",
                       b"eligibility-disclosure", b"btn-survey", b"analysis-body", b"review-status",
                       b"js/api.js", b"js/dashboard.js"):
            self.assertIn(marker, page.data)
        for marker in (b"scorecard-decision", b"comparison-status",
                       b"scorecard-analysis", b"comparison-details"):
            self.assertNotIn(marker, page.data)
        parser = DisclosureParser()
        parser.feed(page.data.decode())
        self.assertEqual(len(parser.details), 2)
        self.assertTrue(all("open" not in detail for detail in parser.details))


if __name__ == "__main__":
    unittest.main()
