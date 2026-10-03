import json
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request

import cases
import judgement
from judgement import compare
from storage import ReviewStore


ROOT = Path(__file__).resolve().parent.parent


OUTPUTS = ROOT /"assets" / "outputs"
CONTEXTS =ROOT/"assets" /"contexts"

#none is a real answer here, it means the calibration failed. so "not tried yet"
# needs its own marker or it would be indistinguishable from that.
_UNSET = object( )

# 500 is the hard cap, enforced here and by the textarea maxlength. no softer
# tier below it.
AGREEMENT_MAX_LENGTH=500


#Read once and shared by GET and POST, so a question cant be asked on the
#response and then not checked on the way back in.
SURVEY_QUESTIONS = (
    {
        "id": "effectiveness" ,
        "text":"Rate the effectiveness of Cashy-AI for identifying and selecting the “right” individuals for the assistance." ,
        "type" : "rating" ,
        "options": ["1", "2", "3", "4", "5"],
    },
    # verdict and reasoning are separate on purpose. one is a glance, the other
    # is the operators own words. folded into one box the stance ended up
    # implicit inside a paragraph, which is the part the study needs to read.
    {
        "id":"agreement",
        "text": "Do you agree with Cashy-AI’s decision on this case?",
        "type": "yesno" ,
        "options" :["Yes","No"],
    },
    {
        "id": "why_effectiveness",
        "text": "Why? In your own words.",
        "type": "text",
        "max_length":AGREEMENT_MAX_LENGTH ,
        "placeholder": "What in the case drove your answer.",
    },
    {
        "id" :"relevance",
        "text" : "Does Cashy-AI provide content that is relevant to help you make an informed decision?",
        "type": "yesno" ,
        "options": ["Yes" ,"No", "Not sure"],
    },
)


#first problem found, or None. returns the message rather than raising so the
#route can hand it straight to a 400, and names the question so the operator
#knows where to look.
def validate_answers(answers):
    if not isinstance(answers, dict):
        return "Expected answers as object"
    for question in SURVEY_QUESTIONS :


        qid = question["id"]
        if qid not in answers:
            return f"Missing answer for {qid}"
        value = answers [ qid]
        if question[ "type" ]=="text":
            if not isinstance(value, str):

                return f"Answer for {qid} must be text"
            if not value.strip():
                return f"Answer for {qid} is required"
            if len ( value ) >question ["max_length"] :
                return f"Answer for {qid} exceeds {question['max_length']} characters"
            continue
        if question["type"] == "multiple":
            if not isinstance(value , list )or not all (isinstance (item, str)for item in value ) :

                return f"Answer for {qid} must be a list of options"
        elif value not in question["options"]:
            return f"Answer for {qid} must be one of {', '.join(question['options'])}"
    return None


def create_app ( config =None) :
    app = Flask (__name__ )
    app.config.update(
        OUTPUTS_DIR=OUTPUTS,
        CONTEXTS_DIR= CONTEXTS ,
        REVIEWS_FILE= Path (__file__).resolve ().parent/"data"/"reviews.json",
        #69.22 is what judgement.calibrate produces on the cases that ship, at
        #100% balanced accurracy. the notebooks 71.5 came off a bigger sample
        # and does not transfer, so /api/comparison reports what this set gives.
        SIMILARITY_THRESHOLD = 69.22 ,
    )
    if config:
        app.config.update(config)
    store =ReviewStore (app.config ["REVIEWS_FILE" ])

    def record (kind,case_id ):
        path = Path(app.config["OUTPUTS_DIR"]) / f"{kind}-record-{case_id:03d}.json"
        if not path.is_file( ) :
            return None
        with path.open(encoding="utf-8") as file:
            return json.load (file)

    def case_exists(case_id):
        return record("scorecard",case_id ) is not None

    def is_completed (case_id) :
        review_data= store.get ( case_id )
        return review_data is not None and review_data [ "status"]=="completed"


    #lazy, it loads the embedding model. building the app mustnt pay for a
    # model only a comparison request needs. failing here costs the numbers not
    # the comparison, so it drops to None.
    def calibration ():
        nonlocal calibration_cache
        if calibration_cache is _UNSET :
            pairs= [ ]
            try :
                for level,number in cases.levels_by_case():
                    scorecard_record=record ("scorecard" , number)
                    cashy_record= record ( "cashy",number)
                    if scorecard_record and cashy_record :
                        pairs.append( ( level , scorecard_record,cashy_record))
                calibration_cache = judgement.calibrate(pairs) if pairs else None
            except Exception:  #noqa: BLE001 - diagnostics only, never fatal
                calibration_cache = None
        return calibration_cache

    calibration_cache = _UNSET



    @app.get("/")
    def index():
        return render_template ( "index.html")

    @ app.get ( "/api/cases" )
    def api_cases():
        #a completed case leaves the list. the survey ends a case, so it should
        #not sit in the selector waiting to be picked twice. files stay on disk
        #and /api/cases/<id> still answers: closed to work, not erased.
        remaining=[ c for c in cases.list_cases ()if not is_completed ( c[ "record_id"]) ]
        return jsonify({"cases": remaining})

    @app.get("/api/cases/<int:record_id>")
    def api_case(record_id):
        try :
            return jsonify(cases.load_case(record_id))
        except cases.CaseNotFound:
            return jsonify ( { "error":"case not found" ,"record_id":record_id} ), 404

    @app.get ( "/api/case/pending")
    def pending():
        ids = []
        for path in Path(app.config["OUTPUTS_DIR"]).glob("scorecard-record-*.json"):
            suffix= path.stem.removeprefix ("scorecard-record-" )
            if suffix.isdigit( ) :
                case_id=int( suffix )
                if record ("cashy" , case_id)is not None and store.get( case_id )is None:
                    ids.append(case_id)
        return jsonify({ "cases" :sorted( set (ids) )})

    @app.get("/api/case/<int:case_id>")
    def scorecard (case_id) :

        data = record( "scorecard" , case_id)
        return jsonify(data) if data is not None else (jsonify(error="Case not found"), 404)

    @ app.get("/api/cashy/<int:case_id>" )
    def cashy(case_id):
        data= record ("cashy",case_id )
        return jsonify(data)if data is not None else(jsonify( error ="Case not found"),404 )

    @app.get ( "/api/comparison/<int:case_id>" )
    def comparison(case_id) :
        scorecard_data = record ( "scorecard" ,case_id)
        cashy_data = record("cashy", case_id)

        context_path= Path( app.config["CONTEXTS_DIR"] )/ f"record-{case_id:03d}.json"
        if scorecard_data is None or cashy_data is None or not context_path.is_file() :
            return jsonify ( error="Case not found") ,404
        with context_path.open(encoding = "utf-8" )as file :
            context = json.load(file )
        result =compare ( scorecard_data, cashy_data , context, app.config [ "SIMILARITY_THRESHOLD"])
        result[ "calibration"]= calibration ()
        return jsonify ( result)

    @app.route("/api/case/<int:case_id>/review", methods=["POST", "PUT"])
    def review( case_id ):
        if not case_exists ( case_id) :
            return jsonify(error="Case not found"), 404

        body= request.get_json( silent =True)
        if (
            not isinstance( body, dict )
            or body.get("decision") not in ("approved", "rejected")
        ):
            return jsonify( error= "Expected decision (approved/rejected)" ),400
        review_data ={"decision" : body [ "decision"] ,
                       "status" : "awaiting_survey"}
        saved=store.add( case_id , review_data)if request.method=="POST" else store.update ( case_id ,review_data)
        if not saved:
            return jsonify ( error = "Review cannot be changed in its current state" ) ,409
        return jsonify({"case_id" : case_id ,** review_data } ) ,201 if request.method == "POST" else 200

    @ app.get ("/api/survey/<int:case_id>" )
    def survey (case_id ):
        if not case_exists(case_id ) :


            return jsonify (error="Case not found" ), 404

        review_data = store.get(case_id)
        review_resp=None
        if review_data:
            review_resp = {"decision": review_data["decision"]}
        return jsonify({
            "case_id": case_id,
            "status" : review_data["status" ]if review_data else "pending",
            "enabled" : review_data is not None ,
            "questions": list(SURVEY_QUESTIONS),
            "review" :review_resp ,
        } )



    @app.post("/api/survey/<int:case_id>")
    def submit_survey (case_id ):
        if not case_exists (case_id):
            return jsonify ( error = "Case not found" ) ,404
        review_data= store.get(case_id )
        if review_data is None:
            return jsonify(error= "Review required before survey"),409
        # mandatory and final, so a completed case is closed to a second
        # submission rather than silently re-stamped
        if review_data [ "status" ] !="awaiting_survey" :
            return jsonify ( error = "Survey already completed for this case") , 409

        body=request.get_json(silent =True )
        if not isinstance(body, dict) or "answers" not in body:
            return jsonify (error ="Expected answers") , 400
        problem = validate_answers(body["answers"])
        if problem :
            return jsonify ( error=problem) ,400
        store.update_status( case_id,"completed" )
        return jsonify({"case_id": case_id, "status": "completed"}), 200

    return app




app = create_app ( )

# not 5000, macOS claims it for AirPlay Receiver and answers on ::1 with 403 for
#any http request, so localhost:5000 lands on AirTunes. 127.0.0.1 stays ipv4.
PORT=int (os.environ.get( "PORT" , 5050) )

if __name__ == "__main__" :
    print(f"Open http://127.0.0.1:{PORT}")
    app.run(host="127.0.0.1", port=PORT, debug=True)
