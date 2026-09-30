"""Output-parity replay (M48 A5; reusable for any serving-path change).

Replays a FROZEN list of raw chat requests verbatim (payload + explicit seed) against the router
and records, per request: content, reasoning, sha256 of each, finish_reason, prompt/completion
tokens, wall. `compare` pairs two replays by (model, bench, id) and reports byte-identical /
differing outputs — the C84 form (5 seeded items on Math500 / HumanEvalPlus / MBPPPlus / cjudge
for each deployed model = 40 pairs) when fed `--frozen` = the C84 `frozen-after.json`.

Transport failures ESCALATE (abort, nonzero exit) — never graded (AGENTS.md). Timeout is
DERIVED (max_tokens / floor decode + headroom), retries 0. One resident model: requests are
grouped by model so the router swaps once.

  cd benchmark && PYTHONPATH=. ../.venv/bin/python -m bench.parity_replay run \
      --frozen $STACK_WORKDIR/upstream/2026-09-14-activation/quality-v2/frozen-after.json \
      --tag m48-before-mtp-on --out $STACK_WORKDIR/m48/parity/before_on.json
  ... --models Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed   (subset)
  cd benchmark && PYTHONPATH=. ../.venv/bin/python -m bench.parity_replay compare A.json B.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from bench import client, provenance

FLOOR_DECODE_TPS = 8.0  # conservative decode floor on this box for both deployed picks
HEADROOM_S = 900.0


def _sha(s: str) -> str:
    return hashlib.sha256((s or "").encode()).hexdigest()


def _post(payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        client.BASE + "/v1/chat/completions", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def load_requests(frozen_path: str, models: list[str] | None) -> list[dict]:
    d = json.load(open(frozen_path))
    out = []
    for arm in d["arms"].values():
        if models and arm["model"] not in models:
            continue
        for r in arm["requests"]:
            p = dict(r["payload"])
            p["model"] = arm["model"]
            p["stream"] = False
            out.append({"model": arm["model"], "bench": r["bench"], "id": r["id"],
                        "seed": r.get("seed"), "payload": p})
    return out


def run(a) -> int:
    try:  # M50: refuse before anything is written or requested unless :port serves this registry
        router = provenance.assert_served_config(client.BASE)
    except RuntimeError as e:
        print(f"[parity_replay] REFUSED: {e}", file=sys.stderr, flush=True)
        return 2
    reqs = load_requests(a.frozen, a.models.split(",") if a.models else None)
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    rows = []; history = []
    if out.exists() and a.resume:
        prev_doc = json.load(open(out))
        rows = prev_doc["rows"]
        prev = prev_doc.get("router"); history = list(prev_doc.get("router_history") or [])
        if isinstance(prev, dict) and prev.get("config") and prev.get("config") != router["config"]:
            print(f"[parity_replay] REFUSED: resuming {out} produced under served config "
                  f"{prev['config']!r} with a router serving {router['config']!r}", file=sys.stderr, flush=True)
            return 2
        if isinstance(prev, dict) and prev.get("pid") is not None and prev.get("pid") != router["pid"]:
            history.append(prev)          # rows above were produced by THAT router
    done = {(r["model"], r["bench"], r["id"]) for r in rows}
    reqs = [r for r in reqs if (r["model"], r["bench"], r["id"]) not in done]
    print(f"{len(reqs)} requests to run ({len(done)} already done) tag={a.tag}", flush=True)
    cur_model = None
    for i, r in enumerate(reqs, 1):
        if r["model"] != cur_model:
            client.preload(r["model"]); cur_model = r["model"]
        mt = int(r["payload"].get("max_tokens") or 102400)
        timeout = mt / FLOOR_DECODE_TPS + HEADROOM_S
        t0 = time.perf_counter()
        try:
            resp = _post(r["payload"], timeout)
        except Exception as e:  # transport: escalate
            print(f"[{i}/{len(reqs)}] TRANSPORT FAILURE {r['bench']} {r['id']}: {type(e).__name__}: {e}", flush=True)
            json.dump({"status": "aborted", "tag": a.tag, "router": router, "router_history": history, "rows": rows}, open(out, "w"), indent=1)
            return 2
        wall = time.perf_counter() - t0
        ch = (resp.get("choices") or [{}])[0]
        msg = ch.get("message") or {}
        us = resp.get("usage") or {}
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""
        row = {"model": r["model"], "bench": r["bench"], "id": r["id"], "seed": r["seed"],
               "finish_reason": ch.get("finish_reason"), "prompt_tokens": us.get("prompt_tokens"),
               "completion_tokens": us.get("completion_tokens"),
               "cached_tokens": (us.get("prompt_tokens_details") or {}).get("cached_tokens"),
               "content_sha256": _sha(content), "reasoning_sha256": _sha(reasoning),
               "content": content, "reasoning_len": len(reasoning), "wall_s": round(wall, 1),
               "decode_tps": (resp.get("timings") or {}).get("predicted_per_second")}
        rows.append(row)
        print(f"[{i}/{len(reqs)}] {r['bench']:14s} {r['id'][:28]:28s} finish={row['finish_reason']} "
              f"ctok={row['completion_tokens']} wall={row['wall_s']}s", flush=True)
        json.dump({"status": "running", "tag": a.tag, "base": client.BASE, "router": router, "router_history": history, "frozen": a.frozen,
                   "when": datetime.now().isoformat(timespec="seconds"), "rows": rows}, open(out, "w"), indent=1)
    try:  # C106: complete only if the served runtime is unchanged since entry
        exit_blk = provenance.assert_served_config_unchanged(router, client.BASE)
    except provenance.ServedConfigError as e:
        print(f"[parity_replay] REFUSED: {e}", file=sys.stderr, flush=True)
        json.dump({"status": "aborted", "tag": a.tag, "router": router, "router_history": history, "rows": rows,
                   "error": f"{e}"}, open(out, "w"), indent=1)
        return 2
    json.dump({"status": "complete", "tag": a.tag, "base": client.BASE, "router": router, "router_exit": exit_blk,
               "router_history": history, "frozen": a.frozen,
               "when": datetime.now().isoformat(timespec="seconds"), "rows": rows}, open(out, "w"), indent=1)
    print(f"complete: {len(rows)} rows -> {out}")
    return 0


def compare(a) -> int:
    A = json.load(open(a.a)); B = json.load(open(a.b))
    ka = {(r["model"], r["bench"], r["id"]): r for r in A["rows"]}
    kb = {(r["model"], r["bench"], r["id"]): r for r in B["rows"]}
    keys = sorted(set(ka) & set(kb))
    same = diff = 0; details = []
    for k in keys:
        x, y = ka[k], kb[k]
        ident = (x["content_sha256"] == y["content_sha256"] and x["reasoning_sha256"] == y["reasoning_sha256"]
                 and x["completion_tokens"] == y["completion_tokens"] and x["finish_reason"] == y["finish_reason"])
        same += ident; diff += not ident
        if not ident:
            details.append({"key": k, "a": {kk: x[kk] for kk in ("finish_reason", "completion_tokens", "content_sha256", "reasoning_sha256")},
                            "b": {kk: y[kk] for kk in ("finish_reason", "completion_tokens", "content_sha256", "reasoning_sha256")}})
    print(f"pairs={len(keys)} identical={same} differing={diff} (A={A['tag']} B={B['tag']}; "
          f"only-in-A={len(set(ka)-set(kb))} only-in-B={len(set(kb)-set(ka))})")
    for d in details:
        print(" DIFF", d["key"], "A:", d["a"]["finish_reason"], d["a"]["completion_tokens"], "B:", d["b"]["finish_reason"], d["b"]["completion_tokens"])
    if a.out:
        json.dump({"a": A["tag"], "b": B["tag"], "pairs": len(keys), "identical": same, "differing": diff,
                   "details": details}, open(a.out, "w"), indent=1)
    return 0 if diff == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run"); r.add_argument("--frozen", required=True); r.add_argument("--tag", required=True)
    r.add_argument("--out", required=True); r.add_argument("--models", default=None); r.add_argument("--resume", action="store_true")
    c = sp.add_parser("compare"); c.add_argument("a"); c.add_argument("b"); c.add_argument("--out", default=None)
    a = ap.parse_args()
    return run(a) if a.cmd == "run" else compare(a)


if __name__ == "__main__":
    sys.exit(main())
