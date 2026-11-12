"""Stage 5 on Check: a difference between files names both files; two readings of one file are told apart.

The showcase has one planted difference between files: way Q2's rating (specification against drawing).
A second, made-up reading of one file is added to the database to show the other case. Nothing is
approved, rejected or picked by the check itself.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app import enquiry
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import ExtractedValueRow, Project
from data_generator.sets import DATA

SHOWCASE = DATA / "projects" / "showcase"
FILES = [("specification.pdf", (SHOWCASE / "specification.pdf").read_bytes()),
         ("requirements.docx", (SHOWCASE / "requirements.docx").read_bytes()),
         ("schematic.dxf", (SHOWCASE / "drawing" / "schematic.dxf").read_bytes())]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test", drawing_reading="off")
    with TestClient(create_app(settings)) as c:
        yield c


def new_enquiry(client: TestClient) -> int:
    response = client.post("/enquiries", data={"name": "Cross-check"}, files=[("files", f) for f in FILES],
                           follow_redirects=False)
    return int(response.headers["location"].split("/")[2])


def card(page: str, field: str) -> str:
    match = re.search(rf'<article class="decision decision--conflict" id="f-{re.escape(field)}">(.*?)</article>',
                      page, re.S)
    assert match, f"no conflict card for {field}"
    return match.group(1)


def test_the_planted_difference_names_both_files(client: TestClient) -> None:
    pid = new_enquiry(client)
    with client.app.state.sessions() as session:
        found = enquiry.decisions(session.get(Project, pid))
        statuses = sorted(v.review_status for v in session.get(Project, pid).values)
    assert "way.Q2.rating" in found.between_files
    q2 = card(client.get(f"/enquiries/{pid}/check").text, "way.Q2.rating")
    assert "The documents disagree" in q2
    assert re.search(r"The specification says \d+ A; the drawing says \d+ A", q2)
    assert set(statuses) == {"extracted"}  # the check flags only: nothing approved, rejected or picked


def test_two_readings_of_one_file_are_not_called_a_difference_between_files(client: TestClient) -> None:
    pid = new_enquiry(client)
    with client.app.state.sessions() as session:
        project = session.get(Project, pid)
        groups = enquiry.review_groups(project)
        field = next(f for f, g in groups.items() if not g["conflict"] and len(g["values"]) == 1
                     and isinstance(g["values"][0].value, int | float))
        row = session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.project_id == pid,
                                                              ExtractedValueRow.field == field)).one()
        clone = ExtractedValueRow(**{c.name: getattr(row, c.name) for c in ExtractedValueRow.__table__.columns
                                     if c.name != "id"})
        clone.value = row.value + 1
        session.add(clone)
        session.commit()
    with client.app.state.sessions() as session:
        found = enquiry.decisions(session.get(Project, pid))
    assert field in {g["field"] for g in found.conflicts} and field not in found.between_files
    one = card(client.get(f"/enquiries/{pid}/check").text, field)
    assert "Two readings of one file differ" in one and "The documents disagree" not in one
