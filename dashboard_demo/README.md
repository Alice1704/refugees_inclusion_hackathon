# dashboard_demo

Judgement dashboard written in Python, Flask, and browser JavaScript. The API
reads the sample scorecard, Cashy, and context records in `../assets`. The UI
shows external variables and Cashy's analysis. Cashy's suggestion is locked
when the comparison's semantic text match falls below 75%; the scorecard
decision and agreement details are not shown.

## How to run

1. Create and activate the Python virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install the dependeces by using `pip`:
  
```bash
pip install -r requirements.txt
```

3. Run the application:

```bash
python app.py
```

4. Open the browser at [http://localhost:5000](http://localhost:5000).

## API

| Method | Route | Response |
| --- | --- | --- |
| GET | `/api/case/pending` | `{"cases": [4, 324, 889]}` before any review |
| GET | `/api/cases` | Case selector summaries (including reviewed cases) |
| GET | `/api/cases/<id>` | Context checklist and case metadata for the UI |
| GET | `/api/case/<id>` | Unmodified scorecard JSON |
| GET | `/api/cashy/<id>` | Unmodified Cashy JSON |
| GET | `/api/comparison/<id>` | Judgement result (see below) |
| POST | `/api/case/<id>/review` | Store the operator's own decision |
| PUT | `/api/case/<id>/review` | Revise a saved decision while awaiting survey |
| GET | `/api/survey/<id>` | Survey status and available questions |
| POST | `/api/survey/<id>` | Disabled until the survey questions are defined |

The comparison runs field differences, sentence attribution, shortcut checks,
and `semantic_match` from the **main-branch** `judgement.ipynb`, adapted to
the current records (`analysis` and `decision`/`target`). The embedding model is
`paraphrase-multilingual-MiniLM-L12-v2` via the notebook's ONNX fallback,
FastEmbed; its first use downloads model weights. `text_match_percentage` and
`threshold` are percentages from 0 to 100, with a default threshold of `75`.
`decision_match` compares the two eligibility decisions independently.
`show_warning` is true only when they diverge **and** the semantic match is
below the threshold; `bias_risk` is `high` then, otherwise `low`. The match
is not a calibrated bias probability. The response includes the context,
`differences`, `sentences` (each with
`interview_overlap`, `context_overlap`, and `source`), `shortcuts`, and
`context_only_sentences`.

To make an independent operator decision, send:

`POST /api/case/324/review` with a JSON body:

```json
{"decision": "approved", "reason": "My assessment of this case"}
```

`decision` must be `approved` or `rejected`, and `reason` must be nonempty.
The response has status 201 and includes `case_id`, `decision`, `reason`, and
`status: "awaiting_survey"`. Once reviewed, a case leaves the pending list.
Reviews persist in `data/reviews.json` (ignored by Git). A repeated POST gets
409; PUT can revise the decision until the survey is completed. Missing cases
get 404 and invalid review payloads get 400.

`GET /api/survey/<id>` currently returns `enabled: false`, `questions: []`,
the saved operator review (or `null`), and status `pending` or
`awaiting_survey`. `POST` returns 409 before a review or 501 after a review
until the questions are supplied. No case is marked `completed` before its
survey is implemented.

The UI starts with both disclosures closed and unlocked. On every case change
it closes and unlocks them again, then loads context variables, Cashy's
analysis, survey state, and the main notebook's `text_match_percentage`. The
suggestion stays closed and cannot be opened only when that case's
`text_match_percentage < threshold`. The scorecard and comparison data are not
displayed. Each entry into a case with `show_warning: true` opens a
critical-case warning. For non-critical cases, the first view per page load
has an independent 20% chance of showing the AI-data reminder.
Approve/Exclude asks for an operator reason and opens the survey dialog after
saving. Its *Back to review* button closes the dialog, and the decision can be
revised until the survey is completed. *Continue to survey* appears as the
primary next action above the revision buttons. The dialog currently says the
questions are coming soon, so the case stays *Awaiting survey*.

Run the backend tests from this directory:

```bash
python -m unittest discover -s tests -v
```
