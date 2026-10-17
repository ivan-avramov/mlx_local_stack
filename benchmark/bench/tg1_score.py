"""Post-hoc scoring of tg1 rows: web fetches, net-shell commands and answer-key contact (P311-lite, spec 1).

The tg1 probe stores raw evidence only. This tool derives the labels the probe used to compute in-process from each
row's stored transcript (sha256-verified against the row's `evidence_sha256.export`) and the recorded corpus: the
contact reference files (`.meta/example*`, `exemplar*`, `proof*`) are read from the git tree of the row's
`polyglot_sha` (`git show <sha>:<path>`), never the live checkout. One record per row key goes to
`<rows>.score.jsonl`; `bench.row_scores` is the only reader. Idempotent: a row with a record under the current scoring
code is skipped; new scoring code appends replacements, never edits.

    python benchmark/bench/tg1_score.py ROWS.jsonl [--polyglot-root DIR]"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))        # runnable as a script and importable as bench.tg1_score
from bench import answer_key, opencode_common, paths, row_scores, web_scan  # noqa: E402

REFERENCE_PREFIXES = ("example", "exemplar", "proof")


class ScoringError(ValueError):
    """A row cannot be scored (evidence mismatch, unreadable corpus tree)."""


def _git(corpus, *args):
    try:
        return subprocess.run(["git", "-C", str(corpus), *args], check=True, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ScoringError(f"git {args[0]} failed in the recorded corpus: {type(exc).__name__}") from exc


def tree_references(corpus_root, polyglot_sha, lang, name):
    """[(relpath under the item, text)] of the item's reference files as committed at `polyglot_sha`, ordered like the
    on-disk detector (`sorted` over paths)."""
    item = f"{lang}/exercises/practice/{name}"
    listing = _git(corpus_root, "ls-tree", "-r", "--name-only", polyglot_sha, "--", item + "/.meta")
    found = []
    for full in listing.decode("utf-8", errors="replace").splitlines():
        rel = PurePosixPath(full).relative_to(item)
        if rel.name.startswith(REFERENCE_PREFIXES):
            found.append((rel, full))
    refs = []
    for rel, full in sorted(found, key=lambda pair: pair[0].parts):
        text = _git(corpus_root, "show", f"{polyglot_sha}:{full}").decode("utf-8", errors="replace")
        refs.append((rel.as_posix(), text))
    return refs


def reference_digest(refs):
    return hashlib.sha256(json.dumps([[rel, hashlib.sha256(text.encode()).hexdigest()] for rel, text in refs],
                                     sort_keys=True).encode()).hexdigest()


def _transcript(row, workdir):
    value = row.get("transcript_path")
    prefix = "$STACK_WORKDIR/"
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ScoringError("row has no portable transcript_path")
    path = (workdir / value[len(prefix):]).resolve()
    if not path.is_relative_to((workdir / "opencode_transcripts").resolve()):
        raise ScoringError("transcript outside the transcript area")
    return path


def score_rows(rows_path, *, polyglot_root=None, scoring_sha=None):
    """Score every tg1 row of `rows_path` that has no current record. Returns {'written', 'skipped', 'errors'}."""
    rows_path = Path(rows_path)
    sidecar = row_scores.sidecar_path(rows_path)
    refusal = paths.confine_path(sidecar, what="score sidecar")
    if refusal:
        raise ValueError(refusal)
    workdir = Path(paths.stack_workdir()).resolve()
    rows = [json.loads(line) for line in rows_path.read_text().splitlines() if line.strip()]
    manifest = json.loads(rows_path.with_suffix(".manifest.json").read_text())
    polyglot_sha = (manifest.get("runtime") or {}).get("polyglot_sha")
    if not isinstance(polyglot_sha, str) or not polyglot_sha:
        raise ScoringError("the rows' manifest records no polyglot_sha")
    corpus = Path(polyglot_root) if polyglot_root is not None else Path(
        os.environ.get("POLYGLOT_DIR") or workdir / "polyglot-benchmark")
    sha = scoring_sha or row_scores.scoring_code_sha256()
    existing = {(tuple(r["row_key"]), r["scoring_code_sha256"]) for r in row_scores.load_records(sidecar)}
    result = {"written": 0, "skipped": 0, "errors": []}
    with sidecar.open("a", encoding="utf-8") as stream:
        for row in rows:
            if not row_scores.needs_sidecar(row):
                continue
            key = row_scores.row_key(row)
            if (key, sha) in existing:
                result["skipped"] += 1
                continue
            try:
                record = _score_one(row, key, corpus, polyglot_sha, sha, workdir)
            except (ScoringError, OSError, ValueError) as exc:
                result["errors"].append(f"{row.get('id')}: {type(exc).__name__}: {exc}")
                continue
            stream.write(opencode_common._scrub_pii(json.dumps(record, ensure_ascii=False)) + "\n")
            stream.flush()
            existing.add((key, sha))
            result["written"] += 1
    if not sidecar.stat().st_size:
        sidecar.unlink()
    return result


def _score_one(row, key, corpus, polyglot_sha, sha, workdir):
    path = _transcript(row, workdir)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != (row.get("evidence_sha256") or {}).get("export"):
        raise ScoringError("transcript does not match the row's evidence_sha256.export")
    export = json.loads(data)
    lang, name = row["id"].split("/", 1)
    if "/" in name or name in (".", "..") or lang in (".", ".."):
        raise ScoringError("invalid item id")
    refs = tree_references(corpus, polyglot_sha, lang, name)
    fields = web_scan.web_audit(export, Path(corpus) / lang / "exercises/practice" / name, path,
                                scaffold=row.get("scaffold", ""),
                                contact_fn=lambda _item, texts: answer_key.contact_refs(refs, texts))
    return {"schema": row_scores.SCHEMA, "row_key": list(key), "transcript_sha256": row["evidence_sha256"]["export"],
            "scoring_code_sha256": sha, "polyglot_sha": polyglot_sha, "reference_digest": reference_digest(refs),
            "fields": fields}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rows", type=Path)
    ap.add_argument("--polyglot-root", type=Path)
    args = ap.parse_args(argv)
    result = score_rows(args.rows, polyglot_root=args.polyglot_root)
    print(json.dumps(result))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
