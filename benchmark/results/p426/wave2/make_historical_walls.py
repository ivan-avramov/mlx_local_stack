"""P566: the Wave-2 `--historical-walls` JSON (spec 10.2 / 16.8), generated from committed sources — never typed.

  .venv-bench/bin/python benchmark/results/p426/wave2/make_historical_walls.py slice --log logs/mlx_vlm.log --out <stage file>
  .venv-bench/bin/python benchmark/results/p426/wave2/make_historical_walls.py make --out <walls.json>   # reads the `evidence` ref

For `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`:
- `w_python_s` / `w_go_s`: the largest item `wall_s` per language over the M63 rows (`m63/{s1,s2,reload}/`) and the P456 rehearsal
  rows (`p426/tg1-rehearsal-20261023/`). Not counted: `m63/archive.*` (aborted attempts) and P486 (`…-20261024`, another stack).
- `max_request_elapsed_s`: the largest single-request `elapsed=` of the worker log's `Request completed` lines (the quantity B2
  records, `p426_reconcile`) for the counted rows' sessions (slice `p426/historical/mlx_vlm.request-completed.log`), and for P499
  (2026-10-27; its rows and server log were lost in the C260 cleanup) the client-side proxy `time.streamed − time.created` per
  assistant message of the opencode item exports (calibrated 15–50 ms above the server value); errored messages are excluded (B2
  records a failed request's elapsed as None). Every counted session must have log lines, else refused.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
SLICE = "p426/historical/mlx_vlm.request-completed.log"
ROW_RE = re.compile(rf"^(m63/(s1|s2|reload)|p426/tg1-rehearsal-20261023/[^/]+)/{re.escape(MODEL)}\.[^/]*opencode_(python|go)[^/]*\.jsonl$")
P499_RE = re.compile(rf"^opencode_transcripts/{re.escape(MODEL)}/{re.escape(MODEL)}\.[^/]*\.20261027T[^/]*/[^/]+\.json$")
LINE_RE = re.compile(r"Request completed: .*\bmodel=(\S+) .*\bsession=(\S+) .*\belapsed=([\d.]+)s")


def parse_line(line):
    m = LINE_RE.search(line)
    return dict(model=m.group(1), session=m.group(2), elapsed=float(m.group(3))) if m else None


def _rows(paths, read):
    for path in paths:
        if ROW_RE.match(path):
            lang = ROW_RE.match(path).group(3)
            for line in read(path).decode().splitlines():
                if line.strip():
                    row = json.loads(line)
                    if row.get("model") == MODEL:
                        yield path, lang, row


def counted_sessions(paths, read):
    return {row["session_id"]: ("m63" if path.startswith("m63/") else "p456") for path, _, row in _rows(paths, read)}


def slice_lines(lines, sessions):
    out = []
    for line in lines:
        p = parse_line(line)
        if p and p["model"] == f"caslca/{MODEL}" and p["session"] in sessions:
            out.append(line)
    return out


def derive(paths, read):
    sources, walls = set(), {"python": None, "go": None}
    for path, lang, row in _rows(paths, read):
        sources.add(path)
        walls[lang] = max(walls[lang] or 0.0, float(row["wall_s"]))
    sessions = counted_sessions(paths, read)
    if SLICE not in paths:
        raise SystemExit(f"refused: the log slice {SLICE} is not in the source tree")
    sources.add(SLICE)
    by = {"m63": None, "p456": None, "p499_client_proxy": None}
    seen = set()
    for line in read(SLICE).decode().splitlines():
        p = parse_line(line)
        if p and p["model"] == f"caslca/{MODEL}" and p["session"] in sessions:
            src = sessions[p["session"]]
            by[src] = max(by[src] or 0.0, p["elapsed"])
            seen.add(p["session"])
    missing = sorted(set(sessions) - seen)
    if missing:
        raise SystemExit(f"refused: no Request completed lines for {len(missing)} counted session(s): {missing[:5]}")
    for path in paths:
        if not P499_RE.match(path):
            continue
        doc = json.loads(read(path))
        if "messages" not in doc:
            continue
        sources.add(path)
        for m in doc["messages"]:
            t = m.get("time") or {}
            if m.get("type") == "assistant" and not m.get("error") and "streamed" in t:
                by["p499_client_proxy"] = max(by["p499_client_proxy"] or 0.0, (t["streamed"] - t["created"]) / 1000)
    if walls["python"] is None or walls["go"] is None or None in by.values():
        raise SystemExit(f"refused: a source set is empty (walls {walls}, request elapsed {by})")
    return dict(model=MODEL, w_python_s=walls["python"], w_go_s=walls["go"], max_request_elapsed_s=max(by.values()),
                max_request_elapsed_by_source=by,
                sources=[dict(path=p, sha256=hashlib.sha256(read(p)).hexdigest()) for p in sorted(sources)])


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("slice")
    s.add_argument("--log", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--ref", default="evidence")
    mk = sub.add_parser("make")
    mk.add_argument("--out", required=True)
    mk.add_argument("--ref", default="evidence")
    a = ap.parse_args(argv)
    commit = git("rev-parse", a.ref).decode().strip()
    paths = git("ls-tree", "-r", "--name-only", commit).decode().splitlines()

    def read(path):
        return git("show", f"{commit}:{path}")
    if a.cmd == "slice":
        sessions = counted_sessions(paths, read)
        with open(a.log, errors="surrogateescape") as f:
            lines = slice_lines(f, sessions)
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "x") as f:
            f.writelines(lines)
        print(f"{len(lines)} lines for {len({parse_line(x)['session'] for x in lines})} / {len(sessions)} sessions -> {out}")
        return 0
    doc = dict(derive(paths, read), evidence_commit=commit)
    with open(a.out, "x") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    print(json.dumps({k: doc[k] for k in ("w_python_s", "w_go_s", "max_request_elapsed_s", "max_request_elapsed_by_source")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
