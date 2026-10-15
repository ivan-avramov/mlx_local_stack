#!/usr/bin/env python3
"""P294 (operator 2026-10-14): the P201 blind web audit with Cursor `gpt-5.6-sol-high` as the auditor.

This wrapper reuses `web_audit.py`'s payload, `web_audit_prompt.md`, parser and append-only sidecar and swaps only the
auditor call, label and version probe (the version is recorded as provenance; it never gates scoring, P299).
Records carry `auditor: "cursor:gpt-5.6-sol-high"`. The auditor runs in an empty temporary workspace (blind: no repo),
read-only (`--mode ask`, sandbox on). An empty answer is an auditor failure (`audit_error`, retry with
`--retry-errors`), never a label. Usage: web_audit_cursor.py <rows.jsonl> [...] [--retry-errors] [--timeout S]"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import web_audit  # noqa: E402
from bench import paths  # noqa: E402

MODEL = "gpt-5.6-sol-high"
AUDITOR = "cursor:" + MODEL


def cursor_version() -> str:
    version = subprocess.run(["cursor-agent", "--version"], text=True, capture_output=True,
                             check=True, timeout=30).stdout.strip()
    if not version:
        raise ValueError("empty cursor-agent --version")
    return version


def cursor_auditor(prompt: str, *, timeout: float = 300) -> str:
    root = paths.stack_workdir() / "m61/tmp"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="web-auditor-", dir=root) as directory:
        result = subprocess.run(
            ["cursor-agent", "-p", "--output-format", "text", "--model", MODEL, "--mode", "ask",
             "--sandbox", "enabled", "--trust", "--workspace", directory, prompt],
            text=True, capture_output=True, check=True, timeout=timeout, cwd=directory)
        answer = result.stdout.strip()
        if not answer:
            raise subprocess.SubprocessError("empty auditor answer")
        return answer


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rows", type=Path, nargs="+")
    parser.add_argument("--polyglot-root", type=Path)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--retry-errors", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    web_audit.AUDITOR = AUDITOR                    # the label audit_rows writes into every record
    web_audit.auditor_version = cursor_version     # the version audit_rows records as provenance (P299)
    for rows in args.rows:
        print(web_audit.audit_rows(rows, polyglot_root=args.polyglot_root,
                                   auditor=lambda prompt: cursor_auditor(prompt, timeout=args.timeout),
                                   retry_errors=args.retry_errors))


if __name__ == "__main__":
    main()
