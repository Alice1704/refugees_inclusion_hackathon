"""
Confronto semantico tra due giustificazioni + confronto della decisione,
con input letti da file .txt.

Formato di ciascun file .txt:
    riga 1      -> decisione (es. "approvato" / "non approvato")
    righe 2..n  -> testo della giustificazione

Dipendenze (tutte open source):
    pip install sentence-transformers

Uso da terminale:
    python semantic_match.py file_a.txt file_b.txt
"""

from ast import main
from enum import auto
import sys
from functools import lru_cache
from pathlib import Path
from typing import Union

from sentence_transformers import SentenceTransformer, util

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# I negativi vanno controllati per primi: "non approvato" contiene "approvato".
_NEGATIVE = {"non approvato", "non approvata", "rifiutato", "rifiutata",
             "respinto", "respinta", "rejected", "not approved", "denied",
             "no", "false", "0"}
_POSITIVE = {"approvato", "approvata", "accettato", "accettata",
             "approved", "accepted", "si", "sì", "yes", "true", "1"}


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Carica il modello una sola volta (lazy)."""
    return SentenceTransformer(MODEL_NAME)


def _normalize_decision(decision: Union[bool, str]) -> bool:
    """Converte la decisione in bool (True = approvato)."""
    if isinstance(decision, bool):
        return decision
    value = str(decision).strip().lower()
    if value in _NEGATIVE:
        return False
    if value in _POSITIVE:
        return True
    raise ValueError(f"Decisione non riconosciuta: {decision!r}")


def _read_txt(path: Union[str, Path]) -> tuple[str, str]:
    """
    Legge un file .txt e restituisce (decisione, giustificazione).
    La prima riga non vuota è la decisione, il resto è la giustificazione.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"File non trovato: {path}")

    lines = path.read_text(encoding="utf-8").splitlines()
    lines = [l for l in lines]
    # salta righe vuote iniziali
    while lines and not lines[0].strip():
        lines.pop(0)
    if len(lines) < 2:
        raise ValueError(
            f"{path.name}: servono almeno una riga di decisione e una di giustificazione."
        )

    decision = lines[0].strip()
    justification = "\n".join(lines[1:]).strip()
    if not justification:
        raise ValueError(f"{path.name}: la giustificazione è vuota.")
    return decision, justification


def semantic_match(file_a: Union[str, Path], file_b: Union[str, Path]) -> dict:
    """
    Confronta due file .txt (decisione + giustificazione).

    Returns:
        {
            "text_match_percentage": float,  # 0-100, solo similarità semantica dei testi
            "decision_match": bool,          # True se le due decisioni coincidono
        }
    """
    decision_a, text_a = _read_txt(file_a)
    decision_b, text_b = _read_txt(file_b)

    model = _get_model()
    emb_a, emb_b = model.encode([text_a, text_b], convert_to_tensor=True)

    # Coseno in [-1, 1] -> clippato a [0, 1] -> percentuale
    cosine = util.cos_sim(emb_a, emb_b).item()
    percentage = round(max(0.0, min(1.0, cosine)) * 100, 2)

    return {
        "text_match_percentage": percentage,
        "decision_match": _normalize_decision(decision_a) == _normalize_decision(decision_b),
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Uso: python semantic_match.py file_a.txt file_b.txt")
    print(semantic_match(sys.argv[1], sys.argv[2]))


result = semantic_match("a.txt", "b.txt")
print(result)
