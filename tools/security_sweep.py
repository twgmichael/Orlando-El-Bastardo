#!/usr/bin/env python3
"""
Security sweep — scan committed/staged files for PII, private paths,
credentials, and machine-specific information before pushing.

Usage:
  python tools/security_sweep.py            # scan all git-tracked files
  python tools/security_sweep.py --staged   # staged files only (pre-commit mode)

Private terms (hostnames, IPs, real names) go in docs/local/sweep-privates.txt,
one term per line, blank lines and # comments ignored. That file is gitignored.

To install as a pre-commit hook:
  echo '#!/bin/sh\npython tools/security_sweep.py --staged' > .git/hooks/pre-commit
  chmod +x .git/hooks/pre-commit

Exit codes: 0 = clean, 1 = findings, 2 = script error
"""

import re
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- Patterns applied to every tracked text file ---
UNIVERSAL_PATTERNS: list[tuple[str, str]] = [
    (r"(?<![A-Za-z]:)/Users/(?!Shared/)[A-Za-z][^/\s'\"]{1,64}/", "absolute macOS user path"),
    (r"/home/[A-Za-z][^/\s'\"]{1,64}/", "absolute Linux home path"),
    (r"192\.168\.\d{1,3}\.\d{1,3}", "private IP (192.168.x.x)"),
    (r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}", "private IP (10.x.x.x)"),
    (r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}", "private IP (172.16-31.x.x)"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "private key material"),
    (r"(?i)(?:password|passwd|secret|api_key)\s*=\s*[\"'][^\"']{4,}[\"']", "hardcoded credential"),
    (r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9]{20,}", "API key (sk- prefix)"),
    (r"xoxb-[A-Za-z0-9-]+", "Slack bot token"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub personal access token"),
]

# --- Extra patterns applied only to code/config files ---
CODE_EXTENSIONS = {
    ".py", ".sh", ".bash", ".js", ".ts",
    ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
}
CODE_EXTRA_PATTERNS: list[tuple[str, str]] = [
    (r"/Volumes/[A-Za-z][^/\s'\"]{1,64}/", "absolute /Volumes/ path in code"),
]

# --- File types to skip entirely ---
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp4", ".mp3", ".wav",
    ".glb", ".fbx", ".usdc", ".usda", ".blend", ".dxf",
    ".tga", ".tiff", ".tif",
    ".pyc", ".pyo", ".pyd",
    ".db", ".sqlite",
    ".bin", ".gz", ".zip", ".tar",
    ".lock",
}

# --- Path prefixes to skip (relative to repo root) ---
SKIP_PREFIXES = (
    "docs/local/",
    ".venv/",
    "worker/.venv/",
    "node_modules/",
)

# suppress individual lines with a trailing:  # sweep:ok
SUPPRESS_MARKER = "sweep:ok"


def git_files(staged_only: bool) -> list[str]:
    if staged_only:
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
    else:
        cmd = ["git", "ls-files"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        print(f"ERROR: git command failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return [f for f in result.stdout.splitlines() if f]


def load_privates() -> list[tuple[str, str]]:
    path = ROOT / "docs" / "local" / "sweep-privates.txt"
    if not path.exists():
        return []
    patterns = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append((re.escape(line), f"private term: {line!r}"))
    return patterns


def scan_file(
    rel_path: str,
    universal: list[tuple[re.Pattern, str]],
    code_extra: list[tuple[re.Pattern, str]],
    privates: list[tuple[re.Pattern, str]],
) -> list[tuple[int, str, str]]:
    path = ROOT / rel_path
    ext = path.suffix.lower()

    if ext in SKIP_EXTENSIONS:
        return []
    if any(rel_path.startswith(p) for p in SKIP_PREFIXES):
        return []

    try:
        text = path.read_text(errors="replace")
    except OSError:
        return []

    is_code = ext in CODE_EXTENSIONS
    patterns = universal + privates + (code_extra if is_code else [])

    findings: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if SUPPRESS_MARKER in line:
            continue
        for compiled, label in patterns:
            if compiled.search(line):
                snippet = line.strip()[:120]
                findings.append((lineno, label, snippet))
                break  # one finding per line is enough
    return findings


def compile_patterns(raw: list[tuple[str, str]]) -> list[tuple[re.Pattern, str]]:
    compiled = []
    for pattern, label in raw:
        try:
            compiled.append((re.compile(pattern), label))
        except re.error as e:
            print(f"WARNING: bad pattern {pattern!r}: {e}", file=sys.stderr)
    return compiled


def main() -> int:
    staged_only = "--staged" in sys.argv

    universal = compile_patterns(UNIVERSAL_PATTERNS)
    code_extra = compile_patterns(CODE_EXTRA_PATTERNS)
    privates = compile_patterns(load_privates())

    files = git_files(staged_only)
    if not files:
        print("No files to scan.")
        return 0

    total_findings = 0
    for rel_path in sorted(files):
        hits = scan_file(rel_path, universal, code_extra, privates)
        for lineno, label, snippet in hits:
            print(f"[FAIL] {rel_path}:{lineno}: {label}")
            print(f"       {snippet}")
            total_findings += 1

    print()
    if total_findings == 0:
        mode = "staged files" if staged_only else "all tracked files"
        print(f"Sweep PASSED — {len(files)} {mode} checked, 0 findings.")
        return 0
    else:
        print(f"Sweep FAILED — {total_findings} finding(s) in {len(files)} file(s) checked.")
        print("Fix findings or add  # sweep:ok  to suppress a known-safe line.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
