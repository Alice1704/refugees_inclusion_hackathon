import json
from pathlib import Path

from flask import Flask, jsonify, render_template, request

import cases
from judgement import compare
from storage import ReviewStore


ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "assets" / "outputs"
CONTEXTS = ROOT / "assets" / "contexts"


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        OUTPUTS_DIR=OUTPUTS,
        CONTEXTS_DIR=CONTEXTS,
        REVIEWS_FILE=Path(__file__).resolve().parent / "data" / "reviews.json",
        SIMILARITY_THRESHOLD=75.0,
    )
    if config:
        app.config.update(config)
    store = ReviewStore(app.config["REVIEWS_FILE"])

    def record(kind, case_id):
        path = Path(app.config["OUTPUTS_DIR"]) / f"{kind}-record-{case_id:03d}.json"
        if not path.is_file():
            return None
        with path.open(encoding="utf-8") as file:
            return json.load(file)

    def case_exists(case_id):
        return record("scorecard", case_id) is not None

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/cases")
    def api_cases():
        return jsonify({"cases": cases.list_cases()})

    @app.get("/api/cases/<int:record_id>")
    def api_case(record_id):
        try:
            return jsonify(cases.load_case(record_id))
        except cases.CaseNotFound:
            return jsonify({"error": "case not found", "record_id": record_id}), 404

    @app.get("/api/case/pending")
    def pending():
        ids = []
        for path in Path(app.config["OUTPUTS_DIR"]).glob("scorecard-record-*.json"):
            suffix = path.stem.removeprefix("scorecard-record-")
            if suffix.isdigit():
                case_id = int(suffix)
                if record("cashy", case_id) is not None and store.get(case_id) is None:
                    ids.append(case_id)
        return jsonify({"cases": sorted(set(ids))})

    @app.get("/api/case/<int:case_id>")
    def scorecard(case_id):
        data = record("scorecard", case_id)
        return jsonify(data) if data is not None else (jsonify(error="Case not found"), 404)

    @app.get("/api/cashy/<int:case_id>")
    def cashy(case_id):
        data = record("cashy", case_id)
        return jsonify(data) if data is not None else (jsonify(error="Case not found"), 404)

    @app.get("/api/comparison/<int:case_id>")
    def comparison(case_id):
        scorecard_data = record("scorecard", case_id)
        cashy_data = record("cashy", case_id)
        context_path = Path(app.config["CONTEXTS_DIR"]) / f"record-{case_id:03d}.json"
        if scorecard_data is None or cashy_data is None or not context_path.is_file():
            return jsonify(error="Case not found"), 404
        with context_path.open(encoding="utf-8") as file:
            context = json.load(file)
        return jsonify(compare(scorecard_data, cashy_data, context, app.config["SIMILARITY_THRESHOLD"]))

    @app.route("/api/case/<int:case_id>/review", methods=["POST", "PUT"])
    def review(case_id):
        if not case_exists(case_id):
            return jsonify(error="Case not found"), 404
        body = request.get_json(silent=True)
        if (
            not isinstance(body, dict)
            or body.get("decision") not in ("approved", "rejected")
            or not isinstance(body.get("reason"), str)
            or not body["reason"].strip()
        ):
            return jsonify(error="Expected decision (approved/rejected) and nonempty reason"), 400
        review_data = {"decision": body["decision"], "reason": body["reason"].strip(),
                       "status": "awaiting_survey"}
        saved = store.add(case_id, review_data) if request.method == "POST" else store.update(case_id, review_data)
        if not saved:
            return jsonify(error="Review cannot be changed in its current state"), 409
        return jsonify({"case_id": case_id, **review_data}), 201 if request.method == "POST" else 200

    @app.get("/api/survey/<int:case_id>")
    def survey(case_id):
        if not case_exists(case_id):
            return jsonify(error="Case not found"), 404
        review_data = store.get(case_id)
        return jsonify({
            "case_id": case_id,
            "status": review_data["status"] if review_data else "pending",
            "enabled": False,
            "questions": [],
            "review": {
                "decision": review_data["decision"],
                "reason": review_data["reason"],
            } if review_data else None,
        })

    @app.post("/api/survey/<int:case_id>")
    def submit_survey(case_id):
        if not case_exists(case_id):
            return jsonify(error="Case not found"), 404
        if store.get(case_id) is None:
            return jsonify(error="Review required before survey"), 409
        return jsonify(error="Survey questions have not been defined yet"), 501

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
