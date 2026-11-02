"""Small deterministic credential guard, not a substitute for a full secret audit."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "telegram_token": re.compile(rb"\b\d{7,15}:[A-Za-z0-9_-]{25,}\b"),
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
    "telegram_api_hash": re.compile(rb"(?im)^\s*api_hash\s*=\s*[\"']?[0-9a-f]{32}"),
}
names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
violations = []
for name in names:
    if not name:
        continue
    path = ROOT / name
    if not path.is_file():
        continue
    if path.suffix.lower() in {".session", ".db", ".sqlite", ".pem", ".key"}:
        violations.append((name, "private_state"))
    if path.stat().st_size > 2 * 1024 * 1024:
        continue
    data = path.read_bytes()
    if b"\0" in data:
        continue
    for kind, pattern in PATTERNS.items():
        if pattern.search(data):
            violations.append((name, kind))
for name, kind in violations:
    print(f"Credential guard: {name}: {kind}")
if violations:
    raise SystemExit(1)
print("Credential guard passed (tracked files, supported patterns only)")
