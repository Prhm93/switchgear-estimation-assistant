"""The question box in the app (Stage 9): passages in the database, search, answer, save and audit.

- :func:`index`: cuts every read file of the enquiry into passages (:func:`backend.app.rag.chunk_pages`) and stores
  them with their vectors for the current embedder, once per file. A file deleted or read again loses its passages
  (:mod:`backend.app.services`), and they are made again on the next question.
- :func:`nearest`: on PostgreSQL the search runs in the database with pgvector (``embedding <=> query``, cosine
  distance); on SQLite (the fast tests) the same cosine is worked out in Python.
- :func:`ask`: answers from the passages (:func:`backend.app.rag.answer`: a quote with its file and page, or a
  refusal when there is no evidence), checks every quoted number against the engineer's approved values, then
  saves the question and the answer (``ask_questions``) and writes one audit entry.
"""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app import rag
from backend.app.models import AskPassage, AskQuestion, Document, Project
from backend.app.schemas import ReviewStatus
from backend.app.vector import vector_literal

MAX_QUESTION = 500  # characters; a longer question is cut, not refused


def index(session: Session, project: Project, embedder: rag.Embedder) -> int:
    """Store passages for every read file that has none for this embedder yet. Returns how many were added."""
    have = set(session.scalars(select(AskPassage.document_id).where(
        AskPassage.project_id == project.id, AskPassage.embedder == embedder.name).distinct()))
    pages = [rag.PageText(d.id, d.original_name, d.kind, p.number, p.text)
             for d in project.documents if d.id not in have for p in d.pages if p.text and p.text.strip()]
    passages = rag.chunk_pages(pages)
    if not passages:
        return 0
    vectors = embedder.embed([p.text for p in passages])
    for p, v in zip(passages, vectors, strict=True):
        session.add(AskPassage(project_id=project.id, document_id=p.document_id, page=p.page, text=p.text,
                               embedder=embedder.name, embedding=v))
    session.flush()
    return len(passages)


def _passage(row: AskPassage) -> rag.Passage:
    doc: Document = row.document
    return rag.Passage(row.document_id, doc.original_name, doc.kind, row.page, row.text)


def nearest(session: Session, project_id: int, embedder: rag.Embedder, question: str,
            k: int = 3) -> list[tuple[float, rag.Passage]]:
    """The ``k`` passages closest to the question, best first, as (cosine similarity, passage)."""
    if not question.strip():
        return []
    q = embedder.embed([question])[0]
    if session.get_bind().dialect.name == "postgresql":
        rows = session.execute(text(
            "SELECT id, 1 - (embedding <=> CAST(:q AS vector)) AS score FROM ask_passages "
            "WHERE project_id = :p AND embedder = :e ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"),
            {"q": vector_literal(q), "p": project_id, "e": embedder.name, "k": k}).all()
        found = {r.id: float(r.score) for r in rows}
        passages = {p.id: p for p in session.scalars(select(AskPassage).where(AskPassage.id.in_(found)))}
        return [(found[i], _passage(passages[i])) for i in found]
    rows = list(session.scalars(select(AskPassage).where(AskPassage.project_id == project_id,
                                                         AskPassage.embedder == embedder.name)))
    scored = sorted(((rag.cosine(q, r.embedding or []), r) for r in rows), key=lambda x: -x[0])[:k]
    return [(s, _passage(r)) for s, r in scored]


def approved(project: Project) -> list[rag.Approved]:
    return [rag.Approved(v.field, v.approved_value, v.approved_unit) for v in project.values
            if v.review_status in (ReviewStatus.APPROVED.value, ReviewStatus.EDITED.value)]


def ask(session: Session, project: Project, question: str, embedder: rag.Embedder,
        actor: str = "engineer") -> tuple[AskQuestion, rag.Answer]:
    """Answer one question, then save it and audit it (one entry, with the actor)."""
    from backend.app.services import audit

    question = " ".join(question.split())[:MAX_QUESTION]
    try:
        index(session, project, embedder)
        hits = nearest(session, project.id, embedder, question)
        result = rag.answer(question, hits, approved(project), embedder.min_score)
    except rag.EmbedderUnavailable:
        result = rag.Answer(question=question, refused=True,
                            text="The search model is not reachable, so no answer is given. The files are unchanged.")
    row = AskQuestion(project_id=project.id, question=question, answer=result.text, refused=result.refused,
                      sources=result.sources_json(), embedder=embedder.name, actor=actor,
                      numbers={"approved": result.approved_numbers, "not_approved": result.unapproved_numbers,
                               "flagged_instruction": result.flagged, "score": result.score})
    session.add(row)
    session.flush()
    audit(session, "ask", "question", row.id, project.id, actor=actor, question=question, refused=result.refused,
          sources=[f"{s['document']} p{s['page']}" for s in row.sources])
    session.commit()
    return row, result


def history(session: Session, project_id: int, n: int = 5) -> list[AskQuestion]:
    return list(session.scalars(select(AskQuestion).where(AskQuestion.project_id == project_id)
                                .order_by(AskQuestion.id.desc()).limit(n)))


