# dashboard_demo

Judgement dashboard written in Python, Flask, and browser JavaScript. The API reads the sample scorecard, Cashy, and context records in `../assets`.

The UI shows external variables and Cashy's analysis. Cashy's suggestion is locked when the comparison's match falls below the set threshold percentage.

## How to run

1. Create and activate the Python virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install the dependencies by using `pip`:

```bash
pip install -r requirements.txt
```

3. Run the application:

```bash
python app.py
```

4. Open the browser at [http://127.0.0.1:5050](http://127.0.0.1:5050).

## The cases

Twelve cases, four per level of agreement between the scorecard and Cashy, generated from `../assets/datasets/S8.synthetic_cashy_sample.csv` by `build_cases.py`:

| Level | Case ids | What it tests |
| --- | --- | --- |
| `similar` | 114, 743, 1114, 1216 | The two reach the same decision with compatible reasoning |
| `partial` | 827, 1592, 1780, 1872 | Same decision, but one side leans on something the other did not |
| `different` | 94, 621, 1055, 1206 | The interview beat the form, and Cashy falls on the other side |


## API

| Method | Route | Response |
| --- | --- | --- |
| GET | `/api/case/pending` | `{"cases": [94, 114, 621, ...]}` before any review |
| GET | `/api/cases` | Case selector summaries, excluding completed cases |
| GET | `/api/cases/<id>` | Context checklist and case metadata for the UI |
| GET | `/api/case/<id>` | Unmodified scorecard JSON |
| GET | `/api/cashy/<id>` | Unmodified Cashy JSON |
| GET | `/api/comparison/<id>` | Judgement result (see below) |
| POST | `/api/case/<id>/review` | Store the operator's own decision |
| PUT | `/api/case/<id>/review` | Revise a saved decision while awaiting survey |
| GET | `/api/survey/<id>` | Survey status and available questions |
| POST | `/api/survey/<id>` | Submit the survey once the case has been reviewed |

## Tests

Run the backend tests from this directory:

```bash
python -m unittest discover -s tests -v
```
