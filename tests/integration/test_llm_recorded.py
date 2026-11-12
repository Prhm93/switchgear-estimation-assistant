"""Recorded mode end to end, with FAKE recordings made by these tests (no model is ever called).

A scripted provider plays a model: it reports the answer key's true values of
the showcase specification, plus three bad items (a quote that is not on the
page, a number that is not in its quote, an unknown field). The recording it
leaves is labelled fake. These tests check that:

- replaying the recording gives exactly the values of the scripted run;
- a recording is refused for other bytes;
- the app in recorded mode uses only a recording whose SHA-256 matches,
  shows the run label in the sidebar, marks rules/LLM agreement, and audits
  the rejected values;
- the planted instruction line is flagged on the Check page and in the proof viewer.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import AuditEvent, Document, ExtractedValueRow
from backend.app.pipeline import analyse_file
from backend.app.recordings import named_recording, recording_path
from backend.app.storage import FileType
from backend.record import pack, record_file
from data_generator import sets
from data_generator.project import build_project, load_answers
from data_generator.schemas import DocumentKind
from estimation_assistant.providers import RecordingMismatch, load_recording, make_provider, sha256_bytes
from tests.fakes import FAKE_MODEL, ScriptedProvider, oracle_script

SHOWCASE = sets.DATA / "projects" / "showcase"
SPEC = (SHOWCASE / "specification.pdf").read_bytes()
KEY = load_answers(SHOWCASE / "answers.json")
BAD = [{"field": "system.voltage", "value": 415, "unit": "V", "quote": "Rated operational voltage: 415 V"},
       {"field": "system.frequency", "value": 60, "unit": "Hz", "quote": "Rated frequency: 50 Hz"},
       {"field": "incomer.price", "value": 0, "unit": None, "quote": "Incomer"}]


def scripted() -> ScriptedProvider:
    script = oracle_script(KEY, DocumentKind.SPECIFICATION)
    first = min(script)
    script[first] = script[first] + BAD
    return ScriptedProvider(script)


@pytest.fixture(scope="module")
def recorded_dir(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("recorded")
    record_file("showcase", "SHOWCASE", "specification.pdf", SPEC, scripted(), out, fake=True)
    return out


def test_recording_holds_model_prompt_hash_and_is_labelled_fake(recorded_dir: Path) -> None:
    rec = load_recording(recording_path(recorded_dir, "showcase", "SHOWCASE", "specification.pdf"), SPEC)
    assert rec.fake and rec.model == FAKE_MODEL and rec.label.endswith("(fake test recording)")
    assert rec.input_sha256 == sha256_bytes(SPEC)
    assert rec.prompt_version and "never instructions" in rec.system_prompt and rec.created
    assert rec.calls and all(len(c.prompt_sha256) == 64 for c in rec.calls)


def test_replay_equals_the_saved_output(recorded_dir: Path) -> None:
    live = analyse_file(FileType.PDF, SPEC, "specification.pdf", scripted())
    rec = named_recording(recorded_dir, "showcase", "SHOWCASE", "specification.pdf", SPEC)
    replay = analyse_file(FileType.PDF, SPEC, "specification.pdf", make_provider("recorded", recording=rec))
    assert replay.llm.values == live.llm.values
    assert replay.llm.rejected == live.llm.rejected
    assert replay.values == live.values
    assert replay.model_run == rec.label


def test_quote_check_keeps_true_values_and_rejects_bad_ones(recorded_dir: Path) -> None:
    rec = named_recording(recorded_dir, "showcase", "SHOWCASE", "specification.pdf", SPEC)
    result = analyse_file(FileType.PDF, SPEC, "specification.pdf", make_provider("recorded", recording=rec))
    reasons = sorted(r.reason for r in result.llm.rejected)
    assert reasons == ["number 60 of the value is not in the quote", "quote not found on the page",
                       "schema: Value error, unknown field 'incomer.price'"]
    truths = sum(len(v) for v in oracle_script(KEY, DocumentKind.SPECIFICATION).values())
    assert len(result.llm.values) == truths
    assert all(v.agreement is not None for v in result.values)  # combined mode marks every value


def test_recording_is_refused_for_other_bytes(recorded_dir: Path) -> None:
    with pytest.raises(RecordingMismatch):
        named_recording(recorded_dir, "showcase", "SHOWCASE", "specification.pdf", SPEC + b"\n%rebuilt")


def test_pack_writes_the_files_and_their_hashes(tmp_path: Path) -> None:
    out = tmp_path / "laptop-files.zip"
    manifest = pack(out, ["showcase"])
    with zipfile.ZipFile(out) as z:
        for entry in manifest["files"]:
            data = z.read(f"{entry['set']}/{entry['project']}/{entry['file']}")
            assert sha256_bytes(data) == entry["sha256"] == sha256_bytes((SHOWCASE / entry["file"]).read_bytes())
        assert json.loads(z.read("manifest.json"))["files"] == manifest["files"]


# --- the app in recorded mode -------------------------------------------------------------------

@pytest.fixture
def client(tmp_path: Path, recorded_dir: Path) -> Iterator[TestClient]:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test", model_mode="recorded",
                        recorded_dir=recorded_dir)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def new_project(client: TestClient, files: list[tuple[str, bytes]]) -> int:
    response = client.post("/enquiries", data={"name": "Recorded"}, follow_redirects=False)
    project_id = int(response.headers["location"].split("/")[2])
    client.post(f"/enquiries/{project_id}/documents", files=[("files", f) for f in files], follow_redirects=False)
    return project_id


def test_app_uses_the_matching_recording_and_shows_its_label(client: TestClient) -> None:
    letter = (SHOWCASE / "requirements.docx").read_bytes()
    project_id = new_project(client, [("specification.pdf", SPEC), ("requirements.docx", letter)])
    with client.app.state.sessions() as session:
        docs = {d.original_name: d for d in session.scalars(select(Document))}
        assert "fake test recording" in docs["specification.pdf"].model_run
        assert docs["requirements.docx"].model_run is None  # no recording for these bytes
        assert "No recorded model run matches" in docs["requirements.docx"].note
        spec_rows = [v for v in session.scalars(select(ExtractedValueRow))
                     if v.document_id == docs["specification.pdf"].id]
        assert "agree" in {v.agreement for v in spec_rows}
        agreed = next(v for v in spec_rows if v.agreement == "agree")
        spec_id, agreed_page = agreed.document_id, agreed.page
        actions = [e.action for e in session.scalars(select(AuditEvent))]
        assert "llm_values_rejected" in actions
    page = client.get(f"/enquiries/{project_id}/proof?doc={spec_id}&page={agreed_page}").text
    assert f"Read with rules + {FAKE_MODEL} (recorded " in page and "(fake test recording)" in page  # header line
    assert "Read by the rules; the model read the same" in page


def test_rules_mode_shows_no_model_run(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'r.sqlite').as_posix()}",
                        storage_dir=tmp_path / "s", environment="test")
    with TestClient(create_app(settings)) as c:
        project_id = new_project(c, [("specification.pdf", SPEC)])
        page = c.get(f"/enquiries/{project_id}/check").text
        assert "<span>Read with rules</span>" in page
        assert "recorded" not in page and "Stage 3" not in page


@pytest.fixture(scope="module")
def injected_spec(tmp_path_factory) -> bytes:
    """Test project T08 (the planted instruction line), built small."""
    job = sets.testset_jobs(tmp_path_factory.mktemp("t08"))[7]
    build_project(job.item_id, job.seed, job.purpose, job.out, list(job.plan), dpi=60.0)
    return (job.out / "specification.pdf").read_bytes()


def test_planted_instruction_is_flagged_on_check_and_proof(client: TestClient, injected_spec: bytes) -> None:
    project_id = new_project(client, [("specification.pdf", injected_spec)])
    with client.app.state.sessions() as session:
        doc = session.scalars(select(Document)).one()
        flagged = next(e for e in session.scalars(select(AuditEvent)) if e.action == "instruction_text_flagged")
        page_no = flagged.detail["flags"][0]["page"]
        assert doc.status == "done"
    proof = client.get(f"/enquiries/{project_id}/proof?doc={doc.id}&page={page_no}").text
    assert "Instruction-like text" in proof and 'class="mark--flag"' in proof
    assert "ignore all previous instructions" in proof
    check = client.get(f"/enquiries/{project_id}/check").text
    assert "Instruction-like text was found" in check and "It was not followed" in check
    # Not obeyed: nothing was approved and no value came from the instruction line.
    with client.app.state.sessions() as session:
        rows = list(session.scalars(select(ExtractedValueRow)))
        assert rows and all(r.review_status == "extracted" for r in rows)
        assert not any("ignore all previous" in (r.source_text or "") for r in rows)
