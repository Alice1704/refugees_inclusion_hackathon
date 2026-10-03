import json
import re

import tempfile
import unittest
import zlib
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

import judgement


from app import AGREEMENT_MAX_LENGTH, SURVEY_QUESTIONS, create_app, validate_answers
from cases import STATUS_LEVELS, available_record_ids, levels_by_case
from judgement import calibrate,compare , semantic_match
from models import context as context_schema

from models import scoreboard as output_schema

#dimensions for the embedding stand in below. big enough that two texts which
#happen to share a hashed bucket still separate on their other words.
FAKE_DIM =512

#cases are generated, so the tests read them off disk instead of pinning ids:
# regenerating the set shouldnt mean rewriting the suite.
LEVELS=dict( levels_by_case( ))
BY_LEVEL = {}
for _level, _id in levels_by_case():


    BY_LEVEL.setdefault( _level ,[ ]).append ( _id)


ASSETS=Path ( __file__ ).resolve( ).parent.parent.parent /"assets"


# read("scorecard", 94) or read("record", 94)
def read( kind ,case_id):
    if kind == "record":
        directory, stem ="contexts", f"record-{case_id:03d}"
    else :
        directory, stem = "outputs", f"{kind}-record-{case_id:03d}"

    path =ASSETS/ directory
    return json.loads(( path/ f"{stem}.json").read_text( encoding = "utf-8") )


class DisclosureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.details = []

    def handle_starttag ( self, tag,attrs ):
        if tag == "details":

            self.details.append(dict(attrs))


class ApiTests ( unittest.TestCase):
    def setUp( self):
        self.embed_patch=patch("judgement.embed", side_effect =self.fake_embeddings)
        self.embed_patch.start()
        self.addCleanup (self.embed_patch.stop )
        self.directory = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING" : True,
            "REVIEWS_FILE": Path(self.directory.name) / "reviews.json",
        })
        self.client = self.app.test_client()
        self.threshold= self.app.config [ "SIMILARITY_THRESHOLD" ]

    def tearDown ( self):
        self.directory.cleanup()

    #deterministic stand in for the embedding model. hashed bag of the content
    # words, so two texts stating the same facts land close and two that dont
    #land apart. stands in for meaning rather than letters, enough to exercise
    # the ordering the real model gives without loading 200MB in a unit test. the
    # real models numbers are in ModelTests below.
    @staticmethod
    def fake_embeddings(texts):
        import judgement

        vectors =[]
        for text in texts:
            vector = [ 0.0]*FAKE_DIM
            for word in judgement.words(text):
                vector [zlib.crc32(word.encode ( "utf-8" )) % FAKE_DIM ]+=1.0
            vectors.append ( vector)

        return vectors

    #POST the review route, decision is a decision or a whole body
    def review(self, case_id, decision="approved"):
        body= { "decision" :decision } if isinstance (decision,str )else decision
        return self.client.post(f"/api/case/{case_id}/review", json =body )

    def test_pending_and_original_records (self) :
        ids = available_record_ids()
        self.assertEqual(self.client.get("/api/case/pending").json, {"cases": ids})
        for case_id in ids :
            with self.subTest( case_id =case_id ):
                for kind ,url in ( ("scorecard", "case") ,( "cashy" ,"cashy" )) :
                    self.assertEqual (
                        self.client.get(f"/api/{url}/{case_id}").json, read(kind, case_id)
                    )
        self.assertEqual(self.client.get ("/api/case/999").status_code , 404 )
        self.assertEqual (self.client.get ( "/api/cashy/999" ).status_code,404)
        self.assertEqual(self.client.get("/api/comparison/999").status_code, 404)



    def test_warning_follows_divergence_not_the_percentage( self ) :
        #the percentage needs a model, the divergence is decided on the record,
        # so those are the two facts the flag is built from and they get checked
        # here with the matcher stubbed. whether the percentage actually separates
        # the levels is a claim about the model, see ModelTests.
        for level in ("similar", "partial", "different"):
            diverges= level == "different"
            for case_id in BY_LEVEL[level]:
                with self.subTest(level= level , case_id = case_id ):
                    result=self.client.get(f"/api/comparison/{case_id}").json
                    self.assertEqual ( result ["decisions_diverge" ] , diverges )
                    self.assertEqual( result [ "decision_match" ], not diverges )

        case_id= BY_LEVEL["similar"] [ 0 ]
        with patch("judgement.semantic_match") as matcher:
            #diverging and far apart is the bias risk the dashboard exists to show
            matcher.return_value={ "text_match_percentage" :10.0, "decision_match":False }
            self.assertEqual ( self.client.get (f"/api/comparison/{case_id}").json[ "bias_risk" ] ,"high" )
            # diverging but saying the same thing is not
            matcher.return_value= {"text_match_percentage":95.0 , "decision_match" : False }
            self.assertEqual (self.client.get(f"/api/comparison/{case_id}").json ["bias_risk"] ,"low")
            # agreeing never warns, however far apart the wording
            matcher.return_value= {"text_match_percentage":10.0 ,"decision_match" : True }
            self.assertEqual (self.client.get (f"/api/comparison/{case_id}").json [ "bias_risk" ] ,"low" )

    def test_flag_hidden_cases_differ_only_on_the_decision (self):
        #the bias the dashboard exists to surface: the form excluded on an
        #administrative flag, cashy never saw it and reasoned from need alone
        for case_id in BY_LEVEL["different"]:
            with self.subTest(case_id=case_id):

                scorecard = read("scorecard", case_id)
                cashy = read("cashy", case_id)
                self.assertTrue(
                    scorecard["decision"]["eligibility_status"].startswith("No Elegible por")
                )
                # cashy reads the case as eligible, the flag is not its input
                self.assertEqual(cashy ["decision" ][ "eligibility_status"] ,"Elegible")
                self.assertNotEqual ( cashy [ "analysis" ],scorecard[ "analysis"])

                result = compare(scorecard, cashy, read("record", case_id))
                fields =[difference [ "field" ] for difference in result [ "differences" ]]
                self.assertIn("decision.eligibility_status", fields)

                #everything else on the form is identical: the disagreement is
                # the decision, not a different reading of the household. target
                #only crosses over when need alone lands on the other side.
                self.assertEqual([f for f in fields if not f.startswith("decision.")], [])
                crossed = scorecard["decision"]["eligibility_target"] != cashy["decision"]["eligibility_target"]
                self.assertEqual (
                    crossed, "decision.eligibility_target" in fields
                )

    def test_comparison_reports_the_notebook_calibration ( self) :
        # every comparison carries the tester that produced the threshold. the
        #numbers are a claim about the model (ModelTests), here they only have
        #to be present and grouped by level.
        calibration=self.client.get(f"/api/comparison/{BY_LEVEL['similar'][0]}").json[ "calibration"]
        self.assertEqual (calibration [ "summary"].keys() ,{"similar" , "partial" , "different"} )
        for level, ids in BY_LEVEL.items():
            with self.subTest(level=level):
                self.assertEqual(calibration["summary"][level]["pairs"], len(ids))
                self.assertEqual(
                    calibration [ "summary" ] [ level]["decisions_agree"],
                    0.0 if level =="different" else 1.0,
                )

    def test_threshold_is_strict_and_requires_divergence (self ):

        scorecard = {"record_id": 1, "analysis": "Interview", "decision": {"eligibility_target": "EXCLUSION"}}
        cashy= { "analysis": "Reasoning", "decision":{"eligibility_target" : "INCLUSION"} }
        for block in ("interview", "household", "demographics", "needs_and_coping",
                      "scores" , "administrative_flags"):
            scorecard[ block ]=cashy [block]={}
        context = {"description": "Context", "external_variables": {}}
        with patch ("judgement.semantic_match")as matcher:
            matcher.return_value = {"text_match_percentage": 75.0, "decision_match": False}
            self.assertFalse ( compare( scorecard,cashy , context ) ["show_warning"])
            matcher.return_value = { "text_match_percentage": 74.99, "decision_match": False }
            self.assertTrue (compare(scorecard ,cashy , context) [ "show_warning"] )


            matcher.return_value= {"text_match_percentage": 74.99, "decision_match":True}

            self.assertFalse(compare( scorecard,cashy , context)[ "show_warning" ])

    def test_semantic_match_uses_cosine_and_decision_independently(self):
        with patch ( "judgement.embed", return_value = ([ 1.0 , 0.0], [ 0.8,0.6])) :
            result=semantic_match(
                {"eligibility_target":"INCLUSION"} ,"Interview" ,
                {"eligibility_target": "EXCLUSION" } ,"Cashy",
            )
        self.assertEqual (result , {"text_match_percentage" :80.0 ,"decision_match" : False } )



    def test_the_model_load_has_a_loading_screen (self ) :
        # the wait is covered by a screen and its the first thing painted
        page= self.client.get( "/" ).data.decode( )
        self.assertIn ( 'id="loading-screen"',page )
        # NOT hidden in the markup. cases arrive from script so anything painted
        #before they resolve is an empty shell, and showing the screen only once
        # the first comparison is slow is what produced the visible flash of an
        # empty list followed by the screen.
        self.assertNotRegex(page, r'id="loading-screen"[^>]*\shidden')
        # announced rather than only drawn, so the wait is not silent
        self.assertRegex (page , r'id="loading-screen"[^>]*role="status"' )
        self.assertRegex(page ,r'id="loading-screen"[^>]*aria-live="polite"' )
        self.assertIn("Loading judgement engine", page)
        #workspace is busy from the first paint, not once script runs
        self.assertRegex( page,r"<main[^>]*aria-busy=\"true\"")

        # the indeterminate bar carries nothing a screen reader can use
        self.assertIn ( 'role="presentation"' , page )
        # without script the screen would sit there for good, so say so instead
        self.assertIn ("<noscript>",page)
        self.assertIn(".loading-screen { display: none; }", page)

        css_response = self.client.get("/static/css/output.css")
        css =css_response.data.decode ()
        css_response.close ( )#the static handler hands back a file wrapper
        for name in ( "loading-screen","loading-card","loading-track", "loading-bar" ) :
            with self.subTest ( class_name= name ) :
                self.assertIn ( name, css)


        self.assertIn("loading-sweep" , css )
        # sweep is decorative so it needs an off switch
        self.assertIn ("prefers-reduced-motion", css)

    def test_the_loading_message_stays_short( self ):
        # one line naming the step: the operator is waiting, not reading
        page=self.client.get ("/" ).data.decode( )
        card= page[page.index( 'id="loading-screen"') : page.index ( 'id="loading-screen"' ) + 900]
        card =card [: card.index( "</div>\n</div>" ) + 12]
        for node_id in ("loading-detail", "loading-note"):
            self.assertNotIn ( node_id, page )
        # no explanation paragraphs survive in the card itself
        self.assertNotIn ( "<p",card)
        self.assertLess(len(re.sub(r"\s+", " ", card)), 420)

    def test_review_persists_and_survey_is_not_yet_submittable(self):
        case_id = BY_LEVEL["partial"][0]
        self.assertEqual ( self.client.get(f"/api/survey/{case_id}").json["status"] ,"pending" )
        self.assertEqual( self.client.post (f"/api/survey/{case_id}").status_code, 409 )
        self.assertEqual(self.review(case_id).status_code, 201)
        self.assertNotIn(case_id , self.client.get("/api/case/pending").json[ "cases"])
        survey =self.client.get (f"/api/survey/{case_id}").json

        self.assertEqual(survey["case_id"], case_id)
        self.assertEqual(survey[ "status"] , "awaiting_survey" )
        self.assertTrue ( survey[ "enabled"])
        self.assertEqual(survey ["questions"] ,list (SURVEY_QUESTIONS ))
        self.assertEqual (survey[ "review"],{ "decision" : "approved" } )
        self.assertEqual (
            self.client.post(f"/api/survey/{case_id}",json ={"answers":{ }}).status_code ,400
        )
        self.assertEqual ( self.review(case_id ,"rejected" ).status_code, 409 )
        reloaded = create_app ( {
            "TESTING":True , "REVIEWS_FILE": Path( self.directory.name)/"reviews.json"
        } ).test_client()
        self.assertNotIn (case_id , reloaded.get ( "/api/case/pending").json[ "cases" ])
        stored = json.loads((Path(self.directory.name) / "reviews.json").read_text())

        self.assertEqual(stored [ str( case_id)] ["decision"] , "approved")


    def test_a_completed_case_leaves_the_list(self):
        # the survey ends a case, so the case leaves the operators list
        case_id= BY_LEVEL[ "different" ][0]

        def listed():
            return [ c["record_id" ]for c in self.client.get( "/api/cases" ).json ["cases" ]]

        def pending() :
            return self.client.get("/api/case/pending").json[ "cases"]

        self.assertIn(case_id,listed( ))
        self.assertIn(case_id, pending())

        #reviewed but not surveyed: still the operators to finish, so it stays
        # in the list and only drops off the pending queue
        self.assertEqual (self.review( case_id).status_code ,201)
        self.assertIn ( case_id, listed () )
        self.assertNotIn (case_id ,pending ( ))

        self.client.post(
            f"/api/survey/{case_id}",
            json = { "answers": {"effectiveness" :"3" , "agreement":"No",
                              "why_effectiveness": "the flag was not on the form", "relevance": "Yes"}},
        )
        self.assertNotIn (case_id , listed () )
        self.assertNotIn (case_id, pending ( ))
        self.assertEqual (len ( listed( ) ),len (available_record_ids ( ) )- 1 )

        #gone from the working list, not erased: the detail route still answers,
        #so a completed case is closed to work rather than lost
        self.assertEqual (self.client.get (f"/api/cases/{case_id}").status_code,200)
        self.assertEqual (self.client.get(f"/api/survey/{case_id}").json [ "status" ],"completed" )

    def test_completing_every_case_empties_the_list(self):
        for case_id in available_record_ids():
            self.assertEqual( self.review ( case_id ).status_code, 201 )
            self.client.post(
                f"/api/survey/{case_id}",
                json = {"answers" : {"effectiveness" : "4" , "agreement" : "Yes" ,
                                  "why_effectiveness":"fine","relevance":"Yes"} },
            )

        self.assertEqual (self.client.get("/api/cases").json [ "cases" ], [ ] )
        self.assertEqual(self.client.get("/api/case/pending").json["cases"], [])

    def test_review_can_change_until_survey_completion (self):
        case_id=BY_LEVEL[ "different"] [ 0 ]
        url= f"/api/case/{case_id}/review"
        self.assertEqual(
            self.client.put (url ,json ={ "decision" :"approved" ,"reason" :"Too early" } ).status_code , 409
        )
        self.assertEqual (self.review( case_id).status_code ,201 )
        self.assertEqual(self.client.put ( url ,json = {"decision": "rejected"} ).status_code,200)
        self.assertEqual(self.client.get(f"/api/survey/{case_id}").json[ "review" ], {
            "decision" : "rejected"
        })
        path = Path(self.directory.name) / "reviews.json"
        saved=json.loads(path.read_text ( ) )
        saved[str ( case_id )][ "status" ]= "completed"
        path.write_text (json.dumps( saved) )
        self.assertEqual(self.client.put(url, json={"decision": "approved"}).status_code, 409)

    def test_invalid_review(self):
        case_id = BY_LEVEL["similar"][0]


        for body in ( { },{ "decision" : "yes"} ) :
            with self.subTest(body=body):
                self.assertEqual ( self.review ( case_id ,body ).status_code ,400 )
        self.assertEqual( self.review(999 , "rejected").status_code, 404 )
        self.assertEqual(
            self.client.get("/api/case/pending").json["cases"], available_record_ids()
        )

    def test_rejected_is_independent_of_cashy_and_survey_unknown_case ( self) :
        case_id = BY_LEVEL[ "similar"][ 0 ]
        self.assertEqual (self.review (case_id, "rejected").json ["decision" ],"rejected")
        self.assertEqual (self.client.get("/api/survey/999").status_code ,404)
        self.assertEqual(self.client.post("/api/survey/999").status_code, 404)

    def test_dashboard_routes_and_assets_survive_the_pull(self) :
        self.assertEqual(
            [case[ "record_id"]for case in self.client.get("/api/cases" ).json [ "cases"] ],
            available_record_ids () ,
        )
        detail= self.client.get (f"/api/cases/{BY_LEVEL['partial'][0]}").json
        self.assertIn ( detail["eligibility" ]["target" ],("INCLUSION" ,"EXCLUSION" ))
        page = self.client.get("/")
        self.assertEqual (page.status_code, 200)


        for marker in (b"Cashy suggestion", b"External variables", b"context-list",
                       b"eligibility-disclosure" , b"btn-survey", b"analysis-body" ,b"review-status" ,
                       b"js/api.js", b"js/dashboard.js"):
            self.assertIn ( marker, page.data)
        for marker in (b"scorecard-decision" , b"comparison-status" ,
                       b"scorecard-analysis", b"comparison-details") :
            self.assertNotIn (marker ,page.data )
        parser = DisclosureParser()
        parser.feed(page.data.decode())
        self.assertEqual ( len(parser.details ) , 2 )
        self.assertTrue(all( "open" not in detail for detail in parser.details))


#the reason answer is open text with a hard cap, on both sides
class SurveyQuestionTests( unittest.TestCase) :
    def setUp (self ) :

        self.question = next(q for q in SURVEY_QUESTIONS if q["type"] == "text")
        self.case_id=BY_LEVEL ["similar" ][ 0]
        self.directory =tempfile.TemporaryDirectory ()
        self.addCleanup (self.directory.cleanup)
        self.app = create_app({
            "TESTING":True,
            "REVIEWS_FILE": Path(self.directory.name) / "reviews.json",
        })
        self.client = self.app.test_client()
        self.client.post(f"/api/case/{self.case_id}/review", json={ "decision" : "approved" })

    def submit(self, agreement, verdict="Yes"):

        return self.client.post(
            f"/api/survey/{self.case_id}",
            json={"answers": {"effectiveness": "4", "agreement": verdict,
                              "why_effectiveness": agreement, "relevance": "Yes"}},
        )



    def test_the_agreement_answer_is_split_into_verdict_and_reason( self ) :
        #a yes/no stance, then the operators own words for it
        ids = [q["id"]for q in SURVEY_QUESTIONS ]

        self.assertEqual (ids ,["effectiveness" ,"agreement", "why_effectiveness" ,"relevance"])
        # reason sits directly under the verdict it explains
        self.assertLess ( ids.index ("agreement") ,ids.index( "why_effectiveness" ) )

        stance=next(q for q in SURVEY_QUESTIONS if q ["id" ] =="agreement" )
        self.assertEqual (stance [ "type" ], "yesno")
        self.assertEqual(stance [ "options"] , [ "Yes" ,"No"] )

        reason=next(q for q in SURVEY_QUESTIONS if q ["id"] == "why_effectiveness" )
        self.assertEqual(reason["type"], "text")
        self.assertEqual(reason["max_length"], AGREEMENT_MAX_LENGTH)
        self.assertNotIn( "options" , reason)

        # served as asked, so the browser enforces the same shape
        served= self.client.get(f"/api/survey/{self.case_id}").json[ "questions"]
        self.assertEqual ( [q ["id" ]for q in served ],ids)
        self.assertEqual (next( q for q in served if q["id"]== "agreement") [ "options"] , ["Yes", "No" ])
        self.assertEqual(next(q for q in served if q["type"] == "text")["max_length"], 500)

    def test_the_verdict_only_takes_yes_or_no (self) :
        for value , ok in(("Yes" ,True) ,( "No" ,True ) ,("Not sure" , False) ,( "" ,False),
                          ( True, False ) ,(["Yes" ], False ) ):
            with self.subTest ( value = value) :
                problem =validate_answers(self.answers ( "it checks the form",verdict= value))


                self.assertEqual( problem is None, ok )
                self.assertIn("agreement" , problem or "agreement" )

    def test_cap_accepts_up_to_five_hundred ( self ):
        for length in( 1,200,499 ,AGREEMENT_MAX_LENGTH) :
            with self.subTest(length= length):
                self.assertEqual(validate_answers( self.answers( "x"*length )) , None)


    def test_cap_rejects_over_five_hundred ( self):
        problem=validate_answers(self.answers( "x" * ( AGREEMENT_MAX_LENGTH + 1 )))
        self.assertIn("exceeds 500",problem)

    def test_blank_and_wrong_typed_answers_are_rejected(self):
        self.assertIn ("required" ,validate_answers (self.answers( "   " ) ) )
        self.assertIn("must be text", validate_answers(self.answers(["a"])))
        self.assertIn("must be text", validate_answers(self.answers(None)))
        self.assertIsNone (validate_answers( self.answers( " it checks the form " ) ) )

    def test_every_question_is_required (self ) :
        for question in SURVEY_QUESTIONS :
            with self.subTest ( question = question ["id"] ):
                answers =self.answers( "it checks the form" )
                del answers[question["id"]]
                self.assertEqual(validate_answers(answers), f"Missing answer for {question['id']}")


    def test_option_answers_are_checked_against_their_options(self):
        for field in ( "effectiveness" , "relevance"):
            for value , ok in(("3" if field== "effectiveness" else "Yes",True),
                              ("9" if field == "effectiveness" else "Perhaps", False),
                              ( [ "a"],False) ,( 3 , False )) :
                with self.subTest(field=field , value= value) :
                    answers=self.answers ("it checks the form" )
                    answers[field] = value
                    self.assertEqual(validate_answers( answers)is None, ok )

    def test_the_cap_holds_over_http (self) :
        self.assertEqual( self.submit ( "x" * AGREEMENT_MAX_LENGTH ).status_code, 200)
        # survey is final, so a second submission is closed rather than restamped,
        # cap or no cap
        self.assertEqual ( self.submit ("still within the cap" ).status_code,409)

        at_cap, over_cap =BY_LEVEL [ "partial" ][ 0],BY_LEVEL["partial"] [ 1 ]
        for case_id, length in(( at_cap,AGREEMENT_MAX_LENGTH) ,(over_cap ,AGREEMENT_MAX_LENGTH + 1 )) :
            with self.subTest(case_id=case_id, length = length ):
                self.client.post (f"/api/case/{case_id}/review",json={"decision" :"approved"})
                response= self.client.post(
                    f"/api/survey/{case_id}",
                    json={"answers": {"effectiveness": "4", "agreement": "No",
                                      "why_effectiveness" :"x" *length, "relevance": "Yes" } } ,
                )
                self.assertEqual(response.status_code, 200 if length <= AGREEMENT_MAX_LENGTH else 400)
                #rejected over the cap, so that case is still awaiting its survey
                self.assertEqual(
                    self.client.get(f"/api/survey/{case_id}").json [ "status" ] ,
                    "completed" if length <= AGREEMENT_MAX_LENGTH else "awaiting_survey",
                )

    @staticmethod
    def answers(agreement, verdict="Yes"):

        return {"effectiveness": "4", "agreement": verdict,
                "why_effectiveness":agreement , "relevance":"Yes"}



#every shipped record satisfies the schema its directory documents
class GeneratedAssetTests (unittest.TestCase) :


    def test_records_match_the_output_schema ( self ) :
        for case_id in available_record_ids ( ) :
            for kind in("scorecard" , "cashy" ):
                with self.subTest(case_id =case_id , kind=kind):
                    output_schema.load(read(kind, case_id))

    def test_contexts_match_the_context_schema (self ):
        for case_id in available_record_ids ( ) :
            with self.subTest ( case_id=case_id ) :
                context_schema.load(read ("record" , case_id ))


    def test_the_schema_layer_rejects_what_the_json_schema_rejects( self) :
        #the dataclasses are the enforcement, so they have to be strict
        broken = read( "scorecard" ,BY_LEVEL [ "similar" ][0 ])
        for field, value in (("month", "2024-4"), ("month", "April"), ("month", 2024), ("office", 7)):
            with self.subTest(field=field, value=value):
                broken [ "interview"] [field ]=value
                with self.assertRaises (Exception) :
                    output_schema.load (broken)
        broken = read("scorecard", BY_LEVEL["similar"][0])
        broken ["decision"] ["eligibility_target" ] = "MAYBE"
        with self.assertRaises(Exception):
            output_schema.load( broken )
        broken =read("scorecard",BY_LEVEL ["similar" ] [ 0 ] )
        broken ["unexpected"]= True

        with self.assertRaises( Exception ) :
            output_schema.load ( broken )

    def test_every_required_field_is_required_here_too(self):
        # a missing required key has to fail, or the layer is laxer than the
        #file. a dataclass defaulting a field the json schema lists in required
        # would let through exactly the records the schema exists to reject.
        case_id =BY_LEVEL["different"][ 0]
        required =json.loads(
            (ASSETS / "outputs" / "output-schema.json").read_text(encoding="utf-8")
        )["required"]
        for field in required:
            with self.subTest ( schema="output",field=field ) :
                broken =read ("scorecard",case_id )
                del broken[field]
                with self.assertRaises(Exception):
                    output_schema.load(broken)

        required = json.loads(
            (ASSETS / "contexts" / "schema.json").read_text(encoding="utf-8")
        )["required"]
        for field in required :

            with self.subTest( schema="context",field= field):
                broken = read("record", case_id)
                del broken [field ]
                with self.assertRaises(Exception ) :
                    context_schema.load (broken )

    def test_every_status_maps_to_a_known_level(self ) :
        for case_id in available_record_ids():
            status = read ("scorecard" , case_id)[ "decision"]["eligibility_status" ]
            with self.subTest( case_id =case_id):

                self.assertIn ( status , STATUS_LEVELS)

    def test_the_generator_is_deterministic ( self ):
        # same dataset in, same records out, or the calibration is a coincidence
        import build_cases


        self.assertEqual(build_cases.curate(build_cases.read_rows()),
                         build_cases.curate(build_cases.read_rows ( ) ))
        row = build_cases.read_rows()[BY_LEVEL["different"][0] - 1]
        first =build_cases.build_records (row)
        second =build_cases.build_records (row)
        self.assertEqual(first,second )


#the real embedding model, when its already on disk. the notebooks claim is about
# meaning rather than shared characters which a stand in cant check, so this runs
# the real model against the shipped cases. skipped when the weights arent cached
# to keep the suite runnable offline.
class ModelTests(unittest.TestCase):
    CACHE = Path.home() / ".cache" / "huggingface" / "hub"

    def setUp(self):
        if not any(self.CACHE.glob("models--*paraphrase-multilingual-MiniLM*")):

            self.skipTest("paraphrase-multilingual-MiniLM-L12-v2 is not in the local HF cache")

    def test_the_local_model_orders_the_levels( self):
        result=calibrate( [
            ( level , read( "scorecard" ,case_id), read("cashy",case_id) )
            for level, case_id in levels_by_case()
        ] )
        means = {level: row["mean"] for level, row in result["summary"].items()}
        self.assertTrue( result [ "ordered" ] ,means)
        self.assertEqual ( result["balanced_accuracy"] ,1.0)
        self.assertEqual(result["summary"]["similar"]["decisions_agree"], 1.0)
        self.assertEqual(result["summary"]["partial"]["decisions_agree"], 1.0)
        #cashy never saw the flag so it lands on the other side every time
        self.assertEqual( result["summary" ] ["different" ]["decisions_agree" ] , 0.0 )

        #configured threshold only means something if it sits in the gap the
        #shipped cases leave, which is the claim app.py makes
        app_module_threshold =create_app( { "TESTING":True } ).config["SIMILARITY_THRESHOLD"]
        self.assertEqual( round (result[ "best_split" ], 2), round(app_module_threshold,2 ) )
        self.assertGreater ( means["partial"], app_module_threshold)
        self.assertLess(means["different"],app_module_threshold)
        self.assertTrue (result [ "banded" ] )

    def test_the_model_resolves_from_the_local_cache(self):
        # the percentage must not depend on a network call to the hub
        import os



        environment = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        original=os.environ.copy ()
        try :
            os.environ.update(environment)
            judgement.embedder.cache_clear ( )
            vectors = judgement.embed( ["a household of four","a household of four people"])
        finally:
            os.environ.clear ( )
            os.environ.update(original)
            judgement.embedder.cache_clear( )
        self.assertEqual (len ( vectors) ,2 )
        self.assertTrue (all ( len( vector) >0 for vector in vectors ) )


if __name__== "__main__" :
    unittest.main()
