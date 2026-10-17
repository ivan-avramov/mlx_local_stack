"""The ONE fail-closed join between tg1 rows and their scoring sidecar (P311-lite, spec 1).

A tg1 row carries no web-audit / answer-key-contact fields: the probe does generation only. `bench.tg1_score` derives
them from the row's stored transcript into `<rows>.score.jsonl`; this module is the only reader. A row is SCORED when
exactly one sidecar record matches its key (model, id, sample, session_id) under the CURRENT scoring code and the
record's transcript sha256 equals the row's `evidence_sha256.export`. Anything else (no record, a record from older
scoring code, a stale transcript, duplicates, an unreadable sidecar) leaves the row UNSCORED: the readers exclude it
from strict scoring and count it, they never read it as "no contact". Legacy rows (`is_legacy`: complete in-row scoring
schema, no composite identity fields; M63/P223/C144) pass through as the same objects. A partial in-row schema is unscored."""
from __future__ import annotations

import json
from pathlib import Path

from . import identity_closure

REPO = Path(__file__).resolve().parents[2]
SCORE_FIELDS = ("web_fetches", "net_shell", "web_denied", "subagent_calls", "web_audit_incomplete",
                "answer_key_contact", "answer_key_evidence")
OPTIONAL_FIELDS = ("web_audit_error",)
SCORING_ENTRY = "benchmark/bench/tg1_score.py"
SCORING_DATA = ("benchmark/web_audit_prompt.md",)
SCHEMA = 1


class Unscored(ValueError):
    """Rows without a current, matching score record cannot be audited or reported as scored."""


def sidecar_path(rows_path):
    return Path(str(rows_path) + ".score.jsonl")


def row_key(row):
    """One attempt: the model, the item, the sample and the session that produced it."""
    return (row.get("model"), row.get("id"), row.get("sample", 0), row.get("session_id"))


IDENTITY_FIELDS = ("generation_identity_sha256", "arm_identity_sha256")


def is_tg1(row):
    return str(row.get("scaffold", "")).startswith("opencode-v2-web-tg1")


def is_legacy(row):
    """The explicit legacy discriminator (review L7): a tg1 row from before P311-lite carries NO composite identity
    field AND the complete in-row scoring schema (all seven fields the old probe always wrote). Anything else, a
    partial row, a current-epoch row, a sidecar-merged copy, is not legacy and must come through the join."""
    return (is_tg1(row) and not any(k in row for k in IDENTITY_FIELDS)
            and all(k in row for k in SCORE_FIELDS))


def needs_sidecar(row):
    """A tg1 row that is not a complete legacy row. The standard v2 probe still scores in-process, so a standard row is
    read from its own fields."""
    return is_tg1(row) and not is_legacy(row)


def scoring_code_sha256(repo=None):
    """The scoring tool's import closure plus the audit prompt (recorded in every score record)."""
    return identity_closure.closure_sha256(SCORING_ENTRY, repo or REPO, data=SCORING_DATA)


def load_records(path):
    """The sidecar's records; a missing file is no records, a torn or malformed line raises ValueError."""
    path = Path(path) if path is not None else None
    if path is None or not path.exists():
        return []
    records = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"{path.name} line {number}: not JSON") from exc
        if (not isinstance(record, dict) or record.get("schema") != SCHEMA
                or not isinstance(record.get("row_key"), list) or not isinstance(record.get("fields"), dict)):
            raise ValueError(f"{path.name} line {number}: not a score record")
        records.append(record)
    return records


def effective_rows(rows, sidecar=None, *, scoring_sha=None):
    """Rows as the readers must see them. Legacy rows (and rows of other scaffolds) are the SAME objects; a scored
    tg1 row is a copy with the sidecar fields merged in (`score_source: sidecar`); an unscored one is a copy with
    `score_unscored` naming why (missing, stale_scoring, stale_transcript, duplicate, unreadable)."""
    rows = list(rows)
    if not any(needs_sidecar(r) for r in rows):
        return rows
    try:
        records = load_records(sidecar)
        unreadable = None
    except (OSError, ValueError):
        records, unreadable = [], "unreadable"
    sha = scoring_sha or scoring_code_sha256()
    by_key = {}
    for record in records:
        by_key.setdefault(tuple(record["row_key"]), []).append(record)
    out = []
    for row in rows:
        if not needs_sidecar(row):
            out.append(row)
            continue
        out.append(_join_one(row, by_key.get(row_key(row), []), sha, unreadable))
    return out


def _join_one(row, candidates, sha, unreadable):
    def unscored(reason):
        return {**row, "score_unscored": reason}
    if unreadable:
        return unscored(unreadable)
    if not candidates:
        return unscored("missing")
    current = [r for r in candidates if r.get("scoring_code_sha256") == sha]
    if not current:
        return unscored("stale_scoring")
    if len(current) > 1:
        return unscored("duplicate")
    record = current[0]
    evidence = (row.get("evidence_sha256") or {}).get("export")
    if not isinstance(evidence, str) or record.get("transcript_sha256") != evidence:
        return unscored("stale_transcript")
    return {**row, **record["fields"], "score_source": "sidecar"}
