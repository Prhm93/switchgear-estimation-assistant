"""Stage 9: the question-box search scorer counts a hit only on the key's own file, page and source text."""

from __future__ import annotations

from backend.app.rag import HashingEmbedder, Passage
from backend.ask_eval import evaluate, is_source, project_folders


def test_a_passage_is_the_source_only_with_the_same_file_page_and_text() -> None:
    p = Passage(1, "specification.pdf", "specification", 4, "3.4 Prospective fault level: 36 kA for 1 s.")
    truth = [("specification.pdf", 4, "Prospective fault level: 36 kA")]
    assert is_source(p, truth)
    assert not is_source(p, [("specification.pdf", 5, "Prospective fault level: 36 kA")])
    assert not is_source(p, [("requirements.docx", 4, "Prospective fault level: 36 kA")])
    assert not is_source(p, [("specification.pdf", 4, "50 kA")])


def test_the_showcase_is_scored_with_the_word_embedder() -> None:
    result = evaluate(project_folders("showcase"), HashingEmbedder())
    t = result["totals"]
    assert t["questions"] == len(result["rows"]) > 5
    assert 0 < t["found_at_1"] <= t["found_in_3"] <= t["questions"]
    assert all(len(r["hits"]) <= 3 for r in result["rows"])
