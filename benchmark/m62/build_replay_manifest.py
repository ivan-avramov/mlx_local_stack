#!/usr/bin/env python3
"""M62 V2: freeze the offline-replay manifest of identity-matched v2 rows (spec §6)."""
import hashlib, json, os, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INVALID = {"go/counter"}  # C145
FIXTURES = [  # pre-registered expectations (spec §6 V2)
    ("Qwen3.8-27B-mlx-uniform-4bit", "opencode_v2_go.m61.s2.jsonl", "go/kindergarten-garden", "looping@request15"),
    ("Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "opencode_v2_go.m59.s1.jsonl", "go/alphametics", "stalled@completed_request40"),
    ("Qwen3.8-27B-mlx-uniform-4bit", "opencode_v2_go.m61.s2.jsonl", "go/book-store", "no_stop"),
]


def _sha(placeholder, wd):
    if not placeholder:
        return None
    p = Path(placeholder.replace("$STACK_WORKDIR", str(wd)))
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def main():
    wd = Path(os.environ["STACK_WORKDIR"])
    entries = []
    for f in sorted((REPO / "benchmark/results").glob("*/opencode_v2_*.jsonl")):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            r = json.loads(line)
            if not str(r.get("scaffold", "")).startswith("opencode-v2"):
                continue
            p = Path(r["events_path"].replace("$STACK_WORKDIR", str(wd)))
            data = p.read_bytes()
            sess = None
            for ev in data.decode(errors="replace").splitlines():
                try:
                    sess = json.loads(ev).get("sessionID")
                except ValueError:
                    continue
                if sess:
                    break
            matched = sess == r.get("session_id")
            entries.append({
                "rows": f.relative_to(REPO).as_posix(), "line": n, "model": r["model"], "id": r["id"],
                "passed": r.get("passed"), "stop_reason": r.get("stop_reason"),
                "events_path": r["events_path"], "events_sha256": hashlib.sha256(data).hexdigest(),
                "transcript_path": r.get("transcript_path"),
                "export_sha256": _sha(r.get("transcript_path"), wd),
                "identity_matched": matched, "valid_item": r["id"] not in INVALID,
                "fixture": next((x for m, rf, i, x in FIXTURES
                                 if m == r["model"] and f.name == rf and i == r["id"]), None),
            })
    use = [e for e in entries if e["identity_matched"]]
    summary = {
        "rows": len(entries), "identity_matched": len(use),
        "misattributed": len(entries) - len(use),
        "passing_matched": sum(e["passed"] is True for e in use),
        "passing_matched_valid": sum(e["passed"] is True and e["valid_item"] for e in use),
    }
    doc = {"spec": "docs/specs/m62-token-turn-gate.md §6 V2", "summary": summary, "entries": entries}
    out = REPO / "benchmark/m62/replay_manifest.json"
    out.write_text(json.dumps(doc, indent=1) + "\n")
    print(json.dumps(summary), hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    sys.exit(main())
