"""Score the question box's search on a project set: does the passage it quotes hold the true value's source?

For each project and each of the fields below, the question is "What is the <plain label>?" (for example "What is
the fault level?"). The specification and the customer letter are read exactly as the app reads them, cut into the
same passages (:func:`backend.app.rag.chunk_pages`) and searched with the chosen embedder. A question counts as

- **found at 1** when the quoted passage (the best one) is on a page where the answer key states that field and holds
  the key's source text, and **found in 3** when one of the three best passages does;
- **refused** when the best score is under the embedder's threshold (the box then says there is no evidence).

Fields the two files do not state are skipped. Nothing is tuned on these numbers.

Usage::

    python -m backend.ask_eval --set fresh                                  # word embedder, laptop
    python -m backend.ask_eval --set fresh --embedder ollama --url http://127.0.0.1:11434   # Colab
    python -m backend.ask_eval --set fresh --embedder ollama --out data/recorded-ask/fresh-mxbai.json

``--out`` saves every question, the passages found with their scores, and the totals (git-ignored folder).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from backend.app import rag
from backend.app.labels import FIELD_LABELS
from backend.app.reading import read_document
from backend.app.storage import EXTENSIONS
from data_generator.project import load_answers
from data_generator.sets import DATA, FRESH_COUNT, REWORDED_COUNT, TEST_COUNT, fresh_id, reworded_id, testset_id

FILES = ("specification.pdf", "requirements.docx")
FIELDS = ("system.voltage", "system.frequency", "system.fault_level", "system.earthing", "incomer.device",
          "incomer.rating", "busbar.rating", "metering.ct_ratio", "enclosure.form", "enclosure.ip_rating",
          "enclosure.cable_entry", "ways.count")
SETS = {"test": (TEST_COUNT, testset_id), "reworded": (REWORDED_COUNT, reworded_id), "fresh": (FRESH_COUNT, fresh_id)}


def project_folders(set_name: str) -> list[Path]:
    if set_name == "showcase":
        return [DATA / "projects" / "showcase"]
    count, name = SETS[set_name]
    return [DATA / "projects" / set_name / name(i) for i in range(1, count + 1)]


def pages_of(folder: Path) -> list[rag.PageText]:
    out: list[rag.PageText] = []
    for i, name in enumerate(FILES, start=1):
        path = folder / name
        if not path.exists():
            continue
        result = read_document(EXTENSIONS[path.suffix.lower()], path.read_bytes())
        kind = "specification" if name.startswith("spec") else "requirements"
        out += [rag.PageText(i, name, kind, p.number, "\n".join(p.lines)) for p in result.pages]
    return out


def _squash(text: str) -> str:
    return " ".join(text.lower().split())


def is_source(passage: rag.Passage, truths: list[tuple[str, int | None, str | None]]) -> bool:
    return any(passage.document == file and passage.page == page and text and _squash(text) in _squash(passage.text)
               for file, page, text in truths)


def evaluate(folders: list[Path], embedder: rag.Embedder) -> dict:
    rows, totals = [], {"questions": 0, "found_at_1": 0, "found_in_3": 0, "refused": 0}
    for folder in folders:
        key = load_answers(folder / "answers.json")
        passages = rag.chunk_pages(pages_of(folder))
        vectors = embedder.embed([p.text for p in passages])
        for field in FIELDS:
            truths = [(t.source.file, t.source.page, t.source.source_text) for t in key.values_for(field)
                      if t.source.file in FILES and t.source.source_text]
            if not truths:
                continue
            question = f"What is the {FIELD_LABELS[field].lower()}?"
            hits = rag.search(question, passages, vectors, embedder, k=3)
            refused = not hits or hits[0][0] < embedder.min_score
            at1 = bool(hits) and not refused and is_source(hits[0][1], truths)
            in3 = not refused and any(is_source(p, truths) for s, p in hits if s >= embedder.min_score)
            totals["questions"] += 1
            totals["found_at_1"] += at1
            totals["found_in_3"] += in3
            totals["refused"] += refused
            rows.append({"project": folder.name, "field": field, "question": question, "refused": refused,
                         "found_at_1": at1, "found_in_3": in3,
                         "hits": [{"score": round(s, 4), "file": p.document, "page": p.page, "text": p.text}
                                  for s, p in hits]})
    return {"totals": totals, "rows": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--set", default="fresh", choices=["showcase", *SETS])
    parser.add_argument("--embedder", default="words", choices=["words", "ollama"])
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--count", type=int, default=None, help="first N projects only")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    folders = project_folders(args.set)[: args.count]
    missing = [f for f in folders if not (f / "answers.json").exists()]
    if missing:
        print(f"Build the set first: python -m data_generator build --set {args.set} ({len(missing)} missing)")
        return 2
    embedder = rag.make_embedder(args.embedder, args.url)
    result = evaluate(folders, embedder)
    t = result["totals"]
    n = t["questions"] or 1
    print(f"{args.set}, {len(folders)} projects, embedder {embedder.name} (threshold {embedder.min_score}): "
          f"{t['questions']} questions; found at 1 {t['found_at_1']} ({t['found_at_1'] / n:.3f}), "
          f"in 3 {t['found_in_3']} ({t['found_in_3'] / n:.3f}), refused {t['refused']}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        result.update({"set": args.set, "embedder": embedder.name, "min_score": embedder.min_score,
                       "date": datetime.now(UTC).isoformat(timespec="seconds")})
        args.out.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(f"Saved {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
