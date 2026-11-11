"""Proof that the database tests leave the app's database untouched.

The app's database (DATABASE_URL) is only read here: its row counts are taken
before and after a full enquiry flow that runs on the tests' own ``*_test``
database, and must be the same.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from backend.app.config import Settings
from backend.app.main import create_app
from data_generator.sets import DATA
from tests import isolation

pytestmark = pytest.mark.database

SPEC = (DATA / "projects" / "showcase" / "specification.pdf").read_bytes()


def test_a_full_flow_on_the_test_database_leaves_the_app_database_untouched(
        app_database_url: str, pg_url: str, tmp_path: Path) -> None:
    assert make_url(pg_url).database.endswith("_test")
    assert make_url(pg_url).database != make_url(app_database_url).database
    before = isolation.row_counts(app_database_url)
    settings = Settings(database_url=pg_url, storage_dir=tmp_path / "storage", environment="test",
                        drawing_reading="off")
    with TestClient(create_app(settings)) as client:
        response = client.post("/enquiries", data={"name": "Isolation check"},
                               files=[("files", ("specification.pdf", SPEC))], follow_redirects=False)
        pid = int(response.headers["location"].split("/")[2])
        client.post(f"/enquiries/{pid}/check/accept-all", data={"confirm": "yes"})
        assert client.get(f"/enquiries/{pid}/quote").status_code == 200
        client.post(f"/enquiries/{pid}/delete", data={"confirm": "yes"})
    assert isolation.row_counts(pg_url)["audit_events"] > 0  # the flow did write, to the test database
    assert isolation.row_counts(app_database_url) == before
