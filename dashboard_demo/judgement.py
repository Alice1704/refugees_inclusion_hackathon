import logging
import re
import warnings
from functools import lru_cache

import numpy as np


BLOCKS = (
    "interview",
    "household" ,
    "demographics",
    "needs_and_coping",
    "scores" ,
    "administrative_flags",
    "decision" ,
)
COMMON = set (
    "a an the and or but if of to in on at for with by is are was were be been being it its "
    "this that i my me we our they their he she his her them as not no so than then there here what "
    "which who from into over under more most less least do does did done have has had can could "
    "would should will shall may might must about after before during while when where how why all "
    "any each other another such own same too very just also because".split ()
)
DECIDES = ("recommend", "include", "exclusion", "serve", "waiting list", "should be", "i would put")
SHORTCUTS= (
    "spanish", "integrat", "working","sole carer" , "low-need" ,
    "low priority", "coherent", "settled",
)


MODEL_NAME ="paraphrase-multilingual-MiniLM-L12-v2"  # apache 2.0, english + spanish
POSITIVE = {"approved","accepted" ,"yes","true" , "1" ,"aprobado" , "aprobada","concedido" ,"concedida" }
NEGATIVE = {
    "not approved", "rejected", "denied", "no", "false", "0",
    "no aprobado", "no aprobada", "denegado", "denegada", "rechazado", "rechazada",
    "desestimado", "desestimada",
}


# Same backend order as the notebook: sentence-transformers, then onnx/fastembed.
#local cache first, so it resolves with no network call once the weights are on
# disk. the hub is only reached when the cache is cold, keeps a fresh clone
# working without making every run depend on it.
@lru_cache( maxsize = 1 )
def embedder():

    warnings.filterwarnings("ignore", message="IProgress not found.*")
    logging.getLogger( "huggingface_hub").setLevel(logging.ERROR)
    try :
        from sentence_transformers import SentenceTransformer
    except ( ImportError,OSError):
        from fastembed import TextEmbedding



        for local_only in(True,False ) :
            try:
                model = TextEmbedding(
                    model_name=f"sentence-transformers/{MODEL_NAME}",
                    local_files_only= local_only ,
                )
                return lambda batch: np.asarray(list(model.embed(batch)))
            except(ValueError , OSError) :
                continue
        raise ImportError(
            f"{MODEL_NAME} is not in the local fastembed cache and could not be downloaded"
        )


    for local_only in( True,False ):
        try:
            model=SentenceTransformer( MODEL_NAME , local_files_only= local_only )
            return lambda batch: np.asarray(model.encode(batch))
        except ( OSError,ValueError ) :
            continue
    raise ImportError(f"{MODEL_NAME} is not in the local cache and could not be downloaded")


def embed(texts ) :
    return embedder()(texts)



#Normalise a decision for comparison, recursing into the decision block. The
#notebook drops "rule" here since Cashy states no rule, but output-schema.json
#has no such key: both sides carry eligibility_target + eligibility_status, and
# a difference in either is a real difference, so nothing gets dropped.
def decision_value(decision ):
    if isinstance( decision , dict) :
        return {key: decision_value(value) for key, value in decision.items()}
    if isinstance( decision,bool ):
        return decision
    value= str ( decision ).strip ().lower( )
    if value in NEGATIVE :
        return False
    if value in POSITIVE:
        return True
    return value


#notebooks semantic text match (0-100) plus an independent decision match
def semantic_match(decision_a, text_a, decision_b, text_b):
    if not text_a.strip () or not text_b.strip( ) :
        raise ValueError( "Both texts are needed to compare them." )
    vector_a,vector_b =(np.asarray(vector)for vector in embed ([text_a , text_b ] ))
    cosine =float (vector_a @vector_b /( np.linalg.norm(vector_a) *np.linalg.norm( vector_b ) ))
    return {
        "text_match_percentage":round(max( 0.0 , min(1.0 ,cosine ) ) * 100 , 2),
        "decision_match": decision_value ( decision_a)== decision_value( decision_b ) ,
    }


def words(text):
    return set(re.findall(r"[a-z']+",text.lower( )) ) -COMMON


# The notebooks matching tester, over pairs of generated records. pairs is a
# list of (level, scorecard, cashy) where level is the similar/partial/different
#the generator built them to be. Checks the matching answers the way the
#generator intended and reports the thresholds the numbers suggest: the cut that
#best splits similar from different, plus the two edges of a manual review band.
# The point of porting it is that the threshold in the config is a number this
#reproduces rather than one someone picked.
def calibrate(pairs):

    scored={ }
    for level, scorecard, cashy in pairs:
        result= semantic_match (
            scorecard [ "decision"],scorecard[ "analysis" ] ,
            cashy[ "decision" ] , cashy [ "analysis"],
        )
        scored.setdefault(level , []).append ( (result ["text_match_percentage"] , result[ "decision_match" ] ))

    summary= {
        level:{
            "pairs":len (rows ),
            "min" : round(min ( pct for pct, _ in rows) , 2),
            "mean": round ( float( np.mean ([pct for pct, _ in rows ])),2 ) ,
            "max":round ( max(pct for pct ,_ in rows) ,2) ,
            "decisions_agree" : round( sum ( agree for _, agree in rows)/ len( rows ),2) ,
        }
        for level,rows in scored.items()
    }

    ordered=[summary [ level]["mean"] for level in( "similar" , "partial","different") if level in summary ]
    result = {
        "summary": summary,
        "ordered": len(ordered) == 3 and ordered[0] > ordered[1] > ordered[2],
    }

    similar = [pct for pct, _ in scored.get("similar", [])]
    different = [pct for pct, _ in scored.get("different", [])]
    if not similar or not different:
        return result

    values = sorted ( set(similar+ different) )
    cuts=[( low+high) / 2 for low ,high in zip(values ,values[1 : ] )] or values

    def balanced_accuracy(cut):


        return (
            sum(pct >= cut for pct in similar) / len(similar)
            + sum(pct < cut for pct in different) / len(different)
        ) / 2

    best =max( cuts ,key = balanced_accuracy)
    match_edge, review_edge = float(np.percentile(similar, 10)), float(np.percentile(different, 90))
    result.update ( {
        "best_split" :round ( best ,2),
        "balanced_accuracy" :round( balanced_accuracy (best ) ,4) ,
        "match_edge": round(match_edge, 2),
        "review_edge": round(review_edge, 2),
        #overlapping levels mean a single cut. the edges would cross and a
        # three way band would read as a measurement it is not.
        "banded": review_edge < match_edge,
    } )
    return result


#the notebooks field, text and context diagnostics, as json data
def compare( scorecard, cashy, context ,threshold= 75.0) :
    scorecard_decision= scorecard ["decision" ]
    cashy_decision= cashy ["decision"]
    differences = []
    for block in BLOCKS :
        left = cashy_decision if block == "decision" else cashy[block]
        right=scorecard_decision if block == "decision" else scorecard [ block]
        for field in dict.fromkeys ( ( *left,*right ) ) :
            if left.get(field) != right.get(field):
                differences.append({
                    "field": f"{block}.{field}",
                    "cashy":left.get ( field ),
                    "scorecard":right.get ( field ) ,
                } )

    record_text =scorecard["analysis"]
    reasoning = cashy ["analysis" ]
    context_text = context["description"] + " " + " ".join(
        str ( value )for value in context [ "external_variables" ].values ()
    )
    record_words = words( record_text)

    context_words=words ( context_text )-record_words
    sentences= []
    for sentence in re.split (r"(?<=[.!?])\s+",reasoning ) :
        sentence_words=words (sentence)
        if len ( sentence_words ) <3 :
            continue
        on_record = len( sentence_words& record_words)/len ( sentence_words )
        on_context = len(sentence_words & context_words) / len(sentence_words)

        if any ( term in sentence.lower ()for term in DECIDES ):
            source= "carries_decision"
        elif on_record > on_context * 2:
            source="interview"
        elif on_context>on_record *2:
            source= "context"
        else:
            source = "neither"
        sentences.append( {
            "text" : sentence.strip () ,
            "interview_overlap" : on_record ,
            "context_overlap" :on_context ,
            "source" :source,
        })

    match= semantic_match( scorecard_decision,record_text, cashy_decision, reasoning)
    diverges =not match ["decision_match"]
    warning = diverges and match [ "text_match_percentage" ]<threshold
    return{
        "case_id" :scorecard[ "record_id"],
        "differences": differences,
        "scorecard_analysis" : record_text ,
        "cashy_analysis" : reasoning ,
        "context": context,
        "sentences": sentences,
        **match,
        "threshold" :threshold,
        "shortcuts" :[term for term in SHORTCUTS if term in reasoning.lower ( ) ],
        "context_only_sentences": sum(
            row [ "source" ] =="context" for row in sentences if "context" not in reasoning.lower()
        ),
        "decisions_diverge": diverges,
        "bias_risk":"high" if warning else "low" ,
        "show_warning": warning,
    }
