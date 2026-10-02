"""Judgement comparison adapted from the main-branch judgement.ipynb."""

import logging
import re
import warnings
from functools import lru_cache

import numpy as np


BLOCKS = (
    "interview",
    "household",
    "demographics",
    "needs_and_coping",
    "scores",
    "administrative_flags",
    "decision",
)
COMMON = set(
    "a an the and or but if of to in on at for with by is are was were be been being it its "
    "this that i my me we our they their he she his her them as not no so than then there here what "
    "which who from into over under more most less least do does did done have has had can could "
    "would should will shall may might must about after before during while when where how why all "
    "any each other another such own same too very just also because".split()
)
DECIDES = ("recommend", "include", "exclusion", "serve", "waiting list", "should be", "i would put")
SHORTCUTS = (
    "spanish", "integrat", "working", "sole carer", "low-need",
    "low priority", "coherent", "settled",
)
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"  # Apache 2.0, covers English and Spanish
POSITIVE = {"approved", "accepted", "yes", "true", "1", "aprobado", "aprobada", "concedido", "concedida"}
NEGATIVE = {
    "not approved", "rejected", "denied", "no", "false", "0",
    "no aprobado", "no aprobada", "denegado", "denegada", "rechazado", "rechazada",
    "desestimado", "desestimada",
}


@lru_cache(maxsize=1)
def embedder():
    """Same backend order as the notebook: sentence-transformers, then ONNX/FastEmbed."""
    warnings.filterwarnings("ignore", message="IProgress not found.*")
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(MODEL_NAME)
        return lambda batch: np.asarray(model.encode(batch))
    except (ImportError, OSError):
        from fastembed import TextEmbedding

        model = TextEmbedding(model_name=f"sentence-transformers/{MODEL_NAME}")
        return lambda batch: np.asarray(list(model.embed(batch)))


def embed(texts):
    return embedder()(texts)


def decision_value(decision):
    if isinstance(decision, dict):
        return {key: decision_value(value) for key, value in decision.items() if key != "rule"}
    if isinstance(decision, bool):
        return decision
    value = str(decision).strip().lower()
    if value in NEGATIVE:
        return False
    if value in POSITIVE:
        return True
    return value


def semantic_match(decision_a, text_a, decision_b, text_b):
    """Main notebook's semantic text match (0-100) and independent decision match."""
    if not text_a.strip() or not text_b.strip():
        raise ValueError("Both texts are needed to compare them.")
    vector_a, vector_b = (np.asarray(vector) for vector in embed([text_a, text_b]))
    cosine = float(vector_a @ vector_b / (np.linalg.norm(vector_a) * np.linalg.norm(vector_b)))
    return {
        "text_match_percentage": round(max(0.0, min(1.0, cosine)) * 100, 2),
        "decision_match": decision_value(decision_a) == decision_value(decision_b),
    }


def words(text):
    return set(re.findall(r"[a-z']+", text.lower())) - COMMON


def compare(scorecard, cashy, context, threshold=75.0):
    """Return the notebook's field, text, and context diagnostics as JSON data."""
    scorecard_decision = scorecard["decision"]
    cashy_decision = cashy.get("target", cashy.get("decision"))
    differences = []
    for block in BLOCKS:
        left = cashy_decision if block == "decision" else cashy[block]
        right = scorecard_decision if block == "decision" else scorecard[block]
        for field in dict.fromkeys((*left, *right)):
            if left.get(field) != right.get(field):
                differences.append({
                    "field": f"{block}.{field}",
                    "cashy": left.get(field),
                    "scorecard": right.get(field),
                })

    record_text = scorecard["analysis"]
    reasoning = cashy["analysis"]
    context_text = context["description"] + " " + " ".join(
        str(value) for value in context["external_variables"].values()
    )
    record_words = words(record_text)
    context_words = words(context_text) - record_words
    sentences = []
    for sentence in re.split(r"(?<=[.!?])\s+", reasoning):
        sentence_words = words(sentence)
        if len(sentence_words) < 3:
            continue
        on_record = len(sentence_words & record_words) / len(sentence_words)
        on_context = len(sentence_words & context_words) / len(sentence_words)
        if any(term in sentence.lower() for term in DECIDES):
            source = "carries_decision"
        elif on_record > on_context * 2:
            source = "interview"
        elif on_context > on_record * 2:
            source = "context"
        else:
            source = "neither"
        sentences.append({
            "text": sentence.strip(),
            "interview_overlap": on_record,
            "context_overlap": on_context,
            "source": source,
        })

    match = semantic_match(scorecard_decision, record_text, cashy_decision, reasoning)
    diverges = not match["decision_match"]
    warning = diverges and match["text_match_percentage"] < threshold
    return {
        "case_id": scorecard["record_id"],
        "differences": differences,
        "scorecard_analysis": record_text,
        "cashy_analysis": reasoning,
        "context": context,
        "sentences": sentences,
        **match,
        "threshold": threshold,
        "shortcuts": [term for term in SHORTCUTS if term in reasoning.lower()],
        "context_only_sentences": sum(
            row["source"] == "context" for row in sentences if "context" not in reasoning.lower()
        ),
        "decisions_diverge": diverges,
        "bias_risk": "high" if warning else "low",
        "show_warning": warning,
    }
