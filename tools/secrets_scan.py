"""A small secrets scan over the committed files (Stage 8). No external tool; patterns are listed below.

Usage (PowerShell, from the repo folder)::

    .venv\\Scripts\\python.exe -m tools.secrets_scan

It looks for cloud and code-host keys, private key blocks, passwords or tokens written as quoted strings, and
database URLs with a password for a host that is not local. The demo's own database password
(``sea-local-only``, for a database reachable only inside Docker or on the laptop) is allowed on purpose.
Limits: patterns only, so a secret in an unusual format is not found; binary files are skipped.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BINARY = {".pdf", ".png", ".jpg", ".jpeg", ".woff2", ".docx", ".npz", ".ico", ".zip", ".gif"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "db", "host.docker.internal"}
ALLOWED_VALUES = {"sea-local-only", "sea", "postgres"}

PATTERNS = {
    "cloud access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "code-host token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "chat token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "password or token in a string": re.compile(
        r"(?i)\b(password|passwd|secret|api_?key|token)\b\s*[:=]\s*[\"']([^\"'\s$]{8,})[\"']"),
}
URL = re.compile(r"\b[a-z][a-z0-9+.-]*://([^:/\s@]+):([^@\s/]+)@([^/:\s]+)")


def scan_text(text: str) -> list[str]:
    """What looks like a secret in one text, as short descriptions."""
    found = []
    for name, pattern in PATTERNS.items():
        for m in pattern.finditer(text):
            value = m.group(m.lastindex) if m.lastindex else m.group(0)
            if value not in ALLOWED_VALUES:
                found.append(name)
    for m in URL.finditer(text):
        password, host = m.group(2), m.group(3)
        if host not in LOCAL_HOSTS and password not in ALLOWED_VALUES and not password.startswith("$"):
            found.append("password in a URL")
    return found


def scan_repo(root: Path = REPO) -> list[str]:
    """``path: what`` for every committed text file with a finding (empty when clean)."""
    files = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout.split()
    out = []
    for name in files:
        path = root / name
        if path.suffix.lower() in BINARY or not path.is_file() or name == "tools/secrets_scan.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        out += [f"{name}: {what}" for what in scan_text(text)]
    return out


def main() -> int:
    findings = scan_repo()
    print("\n".join(findings) if findings else "No secrets found in the committed files.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
