from flask import Flask, jsonify, render_template

import cases

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/cases")
def api_cases():
    """Summary list for the case selector."""
    return jsonify({"cases": cases.list_cases()})


@app.get("/api/cases/<int:record_id>")
def api_case(record_id):
    """Normalised detail payload for a single case."""
    try:
        return jsonify(cases.load_case(record_id))
    except cases.CaseNotFound:
        return jsonify({"error": "case not found", "record_id": record_id}), 404


if __name__ == "__main__":
    app.run(debug=True)
