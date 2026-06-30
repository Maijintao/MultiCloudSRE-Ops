import ipaddress
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


SKIPPED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "state",
    ".private-release-backup",
}

TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".service",
    ".sh",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
    "",
}

SECRET_PATTERNS = [
    re.compile(r"BEGIN (?:OPENSSH|RSA|DSA|EC|PRIVATE) KEY"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bclient-(?:key|certificate)-data\s*:"),
    re.compile(r"\bcertificate-authority-data\s*:"),
    re.compile(r"exam-credentials\.txt", re.IGNORECASE),
    re.compile(r"token-plan-cn|xiaomimimo|mimo-v2\.5|Admin@2026|sztu1034", re.IGNORECASE),
]

IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def iter_public_files():
    for path in ROOT.rglob("*"):
        if any(part in SKIPPED_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path == Path(__file__).resolve():
            continue
        if path.is_file():
            yield path


class OpenSourceHygieneTests(unittest.TestCase):
    def test_no_runtime_state_or_backup_artifacts_are_present(self):
        forbidden = [
            ROOT / ".private-release-backup",
            ROOT / "static" / "app.remote.bak.js",
            ROOT / "static" / "app.js",
        ]
        for path in forbidden:
            self.assertFalse(path.exists(), str(path))
        for path in iter_public_files():
            self.assertNotIn(".sqlite3", path.name)
            self.assertFalse(path.name.endswith((".pyc", ".bak", ".tmp")), str(path))

    def test_frontend_uses_native_modules(self):
        index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<script type="module" src="/static/app/main.js"></script>', index_html)
        self.assertNotIn("/static/app.js", index_html)
        for path in (ROOT / "static" / "app").glob("*.js"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("window.OJApp", text, str(path))
            self.assertNotIn("Object.assign(OJApp", text, str(path))
            self.assertFalse(text.lstrip().startswith("(function () {"), str(path))
            self.assertNotRegex(text, r"\son[a-z]+\s*=", str(path))

    def test_no_secret_markers_or_real_public_ips_are_present(self):
        failures = []
        for path in iter_public_files():
            if path.suffix not in TEXT_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            relative = path.relative_to(ROOT)
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    failures.append(f"{relative}: secret marker {pattern.pattern}")
            for match in IPV4_PATTERN.finditer(text):
                try:
                    address = ipaddress.ip_address(match.group(0))
                except ValueError:
                    continue
                if address.is_global:
                    failures.append(f"{relative}: global IPv4 address {address}")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
