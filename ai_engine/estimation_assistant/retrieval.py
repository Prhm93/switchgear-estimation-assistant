"""Searches a small set of synthetic technical notes by meaning (embeddings)."""

import math
import ollama

EMBED_MODEL = "mxbai-embed-large"

NOTES = {
    "D1": "A moulded case circuit breaker switches off a circuit when the current is too high.",
    "D2": "A busbar carries current between circuit breakers in a panel.",
    "D3": "Cable glands seal the point where a cable enters an enclosure.",
    "D4": "A current transformer measures the current in a cable so that a meter can read it.",
}

def cosine_notes(a: list[float], b: list[float]) -> float:
    """Return the cosine similarity of two vectors (1 = same direction)."""
    dot = sum(x * y for x, y in zip(a, b))
    length_a = math.sqrt(sum(x * x for x in a))
    length_b = math.sqrt(sum(y * y for y in b))
    return dot / (length_a * length_b)

def rank_notes(question: str) ->list[tuple[float, str]]:
    """Return (score, note id) pairs for a question, best match first."""

    # Notes and question must be embedded by the same model
    note_vectors = ollama.embed(
        model=EMBED_MODEL,
        input=list(NOTES.values())
    ).embeddings

    question_vector = ollama.embed(
        model=EMBED_MODEL,
        input = question
    ).embeddings[0]

    scores = []
    for note_id, note_vector in zip(NOTES, note_vectors):
        score = cosine_notes(note_vector, question_vector)
        scores.append((score, note_id))
    scores.sort(reverse=True)
    return scores


def search_notes(question: str) -> str:
    """Find the technical note that best matches a question, by meaning.
    Use it for questions about what a part does or how it is used.
    Do not use it for prices; use lookup_price for those.
    The reply gives the note id (the source), the match score and the note text.
    """
    best_score, best_id = rank_notes(question)[0]
    return f"Source {best_id} (score {round(best_score, 3)}): {NOTES[best_id]}"
