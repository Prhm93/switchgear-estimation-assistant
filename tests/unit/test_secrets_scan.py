"""Stage 8: a secrets scan over every committed file finds nothing, and does find planted examples."""

from __future__ import annotations

from tools.secrets_scan import scan_text, scan_repo


def test_planted_secrets_are_found() -> None:
    fake_key = "AKIA" + "ABCDEFGHIJKLMNOP"
    assert scan_text("aws = '" + fake_key + "'")
    assert scan_text("-----BEGIN " + "RSA PRIVATE KEY-----")
    assert scan_text('password = "' + "hunter2hunter2" + '"')
    assert scan_text("token: ghp_" + "a" * 36)
    assert scan_text("postgresql://user:" + "s3cretpass" + "@db.example.org/x")


def test_local_only_placeholders_and_code_are_not_secrets() -> None:
    assert not scan_text("POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-sea-local-only}")
    assert not scan_text("password = Field(default=None)")
    assert not scan_text("postgresql+pg8000://sea:sea@localhost:5432/sea_test")


def test_the_committed_files_hold_no_secrets() -> None:
    assert scan_repo() == []
