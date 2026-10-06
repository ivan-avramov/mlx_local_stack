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

M58 (AC11): `run` refuses duplicate frozen keys, aborts on a malformed response, sends
`Authorization: Bearer $MLX_API_KEY` when set, and records per request the payload+seed hash, the
draft and `verify_*` counters, the v8 runtime slice and the worker flags. `compare` reports
identical / differing / missing per key; exit 1 on any difference, 2 on any missing key or
integrity problem (duplicate / malformed row).
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

_VALID_FINISH = ("stop", "length", "tool_calls")
FLOOR_DECODE_TPS = 8.0  # conservative decode floor on this box for both deployed picks
HEADROOM_S = 900.0


def _sha(s: str) -> str:
    return hashlib.sha256((s or "").encode()).hexdigest()


def _post(payload: dict, timeout: float) -> dict:
    headers = {"Content-Type": "application/json", **client.auth_headers()}   # router bearer auth
    req = urllib.request.Request(
        client.BASE + "/v1/chat/completions", data=json.dumps(payload).encode(),
        headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _payload_sha(payload: dict, seed) -> str:
    """Identity of what was asked: the verbatim payload plus the explicit seed."""
    return _sha(json.dumps({"payload": payload, "seed": seed}, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False))


def _malformed(resp) -> str | None:
    """None for a well-formed chat completion, else why not: an object without `error`, a
    `choices[0].message` object, a string finish reason, NON-EMPTY content OR a finish reason, and
    integer usage. (Empty content with a finish reason is valid: a budget hit with reasoning only.)"""
    if not isinstance(resp, dict):
        return f"body is {type(resp).__name__}, not an object"
    if resp.get("error"):
        return "error envelope"
    choices = resp.get("choices")
    if not choices or not isinstance(choices, list) or not isinstance(choices[0], dict):
        return "no choices"
    ch = choices[0]
    msg = ch.get("message")
    if not isinstance(msg, dict):
        return "no message"
    finish = ch.get("finish_reason")
    if finish is not None and finish not in _VALID_FINISH:
        return f"finish_reason {finish!r}"
    if not (msg.get("content") or finish):
        return "empty content and no finish_reason"
    us = resp.get("usage")
    for k in ("prompt_tokens", "completion_tokens"):
        v = (us or {}).get(k)
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            return f"usage.{k} missing or not a non-negative integer ({v!r})"
    return None


def _row_malformed(row) -> str | None:
    """The same test over a persisted row (compare reads rows, not responses)."""
    if not isinstance(row, dict):
        return "row is not an object"
    finish = row.get("finish_reason")
    if finish is not None and finish not in _VALID_FINISH:
        return f"finish_reason {finish!r}"
    if not (row.get("content") or finish):
        return "empty content and no finish_reason"
    for k in ("prompt_tokens", "completion_tokens"):
        v = row.get(k)
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            return f"{k} missing or not a non-negative integer ({v!r})"
    return None


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


def _key(r) -> tuple:
    return (r["model"], r["bench"], r["id"])


def _abort(out, status_doc, error, rows, router=None, check_exit=True) -> int:
    """Failure-safe finalization: write the aborted journal with the ORIGINAL error, after a C106
    exit verification whose own failure (drift or crash) is recorded beside it, never instead of it."""
    doc = {**status_doc, "status": "aborted", "error": error, "rows": rows}
    if router is not None and check_exit:
        try:
            doc["router_exit"] = provenance.assert_served_config_unchanged(router, client.BASE)
        except Exception as e:  # noqa: BLE001 - recorded; the original failure still decides
            try:
                doc["served_config_drift"] = provenance.served_config_drift_record(
                    router, client.BASE, e)
            except Exception:  # noqa: BLE001
                doc["served_config_drift"] = {"error": str(e)}
    json.dump(doc, open(out, "w"), indent=1)
    return 2


def run(a) -> int:
    try:  # M50: refuse before anything is written or requested unless :port serves this registry
        router = provenance.assert_served_config(client.BASE)
    except RuntimeError as e:
        print(f"[parity_replay] REFUSED: {e}", file=sys.stderr, flush=True)
        return 2
    reqs = load_requests(a.frozen, a.models.split(",") if a.models else None)
    if not reqs:  # S2: an empty selection (e.g. a --models typo) is never a replay
        print("[parity_replay] REFUSED: empty request selection", file=sys.stderr, flush=True)
        return 2
    keys = [_key(r) for r in reqs]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:  # AC11: every frozen key must be unique, or "present exactly once" is meaningless
        print(f"[parity_replay] REFUSED: duplicate frozen key(s) {dupes}", file=sys.stderr, flush=True)
        return 2
    hashes = {_key(r): _payload_sha(r["payload"], r["seed"]) for r in reqs}
    entry_state = {}
    try:  # B3: the served scan must be resolved, in the closed set and agree with the worker NOW
        for m in sorted({r["model"] for r in reqs}):
            entry_state[m] = provenance.assert_serving_state(m)
    except provenance.ServedConfigError as e:
        print(f"[parity_replay] REFUSED: {e}", file=sys.stderr, flush=True)
        return 2
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    rows = []; history = []
    if out.exists() and a.resume:
        prev_doc = json.load(open(out))
        rows = prev_doc["rows"]
        row_keys = [_key(r) for r in rows]
        if len(set(row_keys)) != len(row_keys):
            print(f"[parity_replay] REFUSED: the journal {out} holds a duplicate row", file=sys.stderr,
                  flush=True)
            return 2
        for r in rows:  # B2: a resumed row must answer THE frozen request (payload + seed hash)
            if hashes.get(_key(r)) is None or r.get("payload_sha256") != hashes[_key(r)]:
                print(f"[parity_replay] REFUSED: journal row {_key(r)} does not match the frozen "
                      f"payload+seed hash", file=sys.stderr, flush=True)
                return 2
        prev = prev_doc.get("router"); history = list(prev_doc.get("router_history") or [])
        if isinstance(prev, dict) and prev.get("config") and prev.get("config") != router["config"]:
            print(f"[parity_replay] REFUSED: resuming {out} produced under served config "
                  f"{prev['config']!r} with a router serving {router['config']!r}", file=sys.stderr, flush=True)
            return 2
        if isinstance(prev, dict) and prev.get("pid") is not None and prev.get("pid") != router["pid"]:
            history.append(prev)          # rows above were produced by THAT router
    done = {_key(r) for r in rows}
    todo = [r for r in reqs if _key(r) not in done]
    print(f"{len(todo)} requests to run ({len(done)} already done) tag={a.tag}", flush=True)
    base = {"tag": a.tag, "base": client.BASE, "router": router, "router_history": history,
            "frozen": a.frozen, "expected_keys": [list(k) for k in keys]}
    cur_model = None
    for i, r in enumerate(todo, 1):
        if r["model"] != cur_model:
            try:
                client.preload(r["model"])
                provenance.assert_serving_state(r["model"], expect=entry_state[r["model"]])
            except Exception as e:  # noqa: BLE001 - never leaves a half-written run unfinalised
                print(f"[parity_replay] PRELOAD/RE-RESOLVE FAILED {r['model']}: {e}", file=sys.stderr,
                      flush=True)
                return _abort(out, base, f"preload: {type(e).__name__}: {e}", rows, router)
            cur_model = r["model"]
        mt = int(r["payload"].get("max_tokens") or 102400)
        timeout = mt / FLOOR_DECODE_TPS + HEADROOM_S
        t0 = time.perf_counter()
        try:
            resp = _post(r["payload"], timeout)
        except Exception as e:  # transport: escalate
            print(f"[{i}/{len(todo)}] TRANSPORT FAILURE {r['bench']} {r['id']}: {type(e).__name__}: {e}", flush=True)
            return _abort(out, base, f"transport: {type(e).__name__}: {e}", rows, router)
        wall = time.perf_counter() - t0
        bad = _malformed(resp)
        if bad:  # a malformed 200 is never graded: abort like a transport failure
            print(f"[{i}/{len(todo)}] MALFORMED RESPONSE {r['bench']} {r['id']}: {bad}", flush=True)
            return _abort(out, base, f"malformed response for {_key(r)}: {bad}", rows, router)
        try:  # the served state AT this request (v8 runtime slice + worker flags); drift refuses
            runtime = provenance._runtime_block(None, model=r["model"])
            worker = provenance.worker_serving_facts(r["model"])
            scan = provenance.check_mtp_verify_scan_value(runtime.get("mtp_verify_scan"),
                                                          "parity_replay row")
            if scan != entry_state[r["model"]]["mtp_verify_scan"]:
                raise provenance.ServingStateError(
                    f"M58: mtp_verify_scan {scan!r} at {_key(r)} differs from the entry value "
                    f"{entry_state[r['model']]['mtp_verify_scan']!r}")
            if not worker:  # S3: a null worker command line is refused, never recorded silently
                raise provenance.ServingStateError(
                    f"M58: no worker command line observable for {r['model']!r} while it serves "
                    f"requests; refusing to record unattributed rows")
        except provenance.ServedConfigError as e:
            print(f"[parity_replay] REFUSED: {e}", file=sys.stderr, flush=True)
            return _abort(out, base, f"{e}", rows, router)
        ch = resp["choices"][0]
        msg = ch.get("message") or {}
        us = resp.get("usage") or {}
        tm = resp.get("timings") or {}
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""
        row = {"model": r["model"], "bench": r["bench"], "id": r["id"], "seed": r["seed"],
               "payload_sha256": hashes[_key(r)],
               "finish_reason": ch.get("finish_reason"), "prompt_tokens": us.get("prompt_tokens"),
               "completion_tokens": us.get("completion_tokens"),
               "cached_tokens": (us.get("prompt_tokens_details") or {}).get("cached_tokens"),
               "content_sha256": _sha(content), "reasoning_sha256": _sha(reasoning),
               "content": content, "reasoning_len": len(reasoning), "wall_s": round(wall, 1),
               "decode_tps": tm.get("predicted_per_second"),
               "draft": {k: tm.get(k) for k in
                         ("draft_kind", "draft_rounds", "draft_n", "draft_n_accepted")},
               "verify": {k: v for k, v in tm.items() if k.startswith("verify_")},
               "runtime": runtime, "worker": worker}
        rows.append(row)
        print(f"[{i}/{len(todo)}] {r['bench']:14s} {r['id'][:28]:28s} finish={row['finish_reason']} "
              f"ctok={row['completion_tokens']} wall={row['wall_s']}s", flush=True)
        json.dump({**base, "status": "running",
                   "when": datetime.now().isoformat(timespec="seconds"), "rows": rows}, open(out, "w"), indent=1)
    got = [_key(r) for r in rows]
    if sorted(got) != sorted(keys):  # AC11: complete only with every frozen key exactly once
        return _abort(out, base, f"rows {sorted(set(keys) ^ set(got))} do not match the frozen keys",
                      rows, router)
    try:  # C106: complete only if the served runtime is unchanged since entry
        exit_blk = provenance.assert_served_config_unchanged(router, client.BASE)
    except provenance.ServedConfigError as e:
        print(f"[parity_replay] REFUSED: {e}", file=sys.stderr, flush=True)
        return _abort(out, base, f"{e}", rows, router, check_exit=False)
    json.dump({**base, "status": "complete", "router_exit": exit_blk,
               "when": datetime.now().isoformat(timespec="seconds"), "rows": rows}, open(out, "w"), indent=1)
    print(f"complete: {len(rows)} rows -> {out}")
    return 0


_IDENTITY = ("finish_reason", "completion_tokens", "content_sha256", "reasoning_sha256", "draft")


def _audit(doc) -> tuple[dict, list]:
    """(rows by key, integrity problems) for one replay: duplicates, malformed rows, missing
    identity fields and a missing request hash."""
    by, problems, seen = {}, [], set()
    for r in doc.get("rows") or []:
        try:
            k = _key(r)
        except (KeyError, TypeError):
            problems.append(f"row without a (model, bench, id) key: {str(r)[:60]}")
            continue
        if k in seen:
            problems.append(f"duplicate row {k}")
            continue
        seen.add(k)
        bad = _row_malformed(r)
        if bad:
            problems.append(f"malformed row {k}: {bad}")
        for f in _IDENTITY + ("payload_sha256",):
            if f not in r:
                problems.append(f"row {k} lacks the mandatory field {f}")
        by[k] = r
    return by, problems


def _expected(doc, side, problems):
    raw = doc.get("expected_keys")
    if not isinstance(raw, list) or not raw:
        problems.append(f"{side}: expected_keys missing or empty")
        return None
    keys = [tuple(k) for k in raw]
    if len(set(keys)) != len(keys):
        problems.append(f"{side}: duplicate entries in expected_keys")
    return set(keys)


def compare(a) -> int:
    A = json.load(open(a.a)); B = json.load(open(a.b))
    ka, pa = _audit(A)
    kb, pb = _audit(B)
    integrity = [f"A: {p}" for p in pa] + [f"B: {p}" for p in pb]
    legacy = "expected_keys" not in A or "expected_keys" not in B
    ea = eb = None
    if not legacy:
        ea, eb = _expected(A, "A", integrity), _expected(B, "B", integrity)
        if ea is not None and eb is not None and ea != eb:
            integrity.append(f"expected-key sets differ ({len(ea ^ eb)} keys)")
        for side, d, st in (("A", ka, A), ("B", kb, B)):
            if st.get("status") != "complete":
                integrity.append(f"{side}: journal status is {st.get('status')!r}, not 'complete'")
        for side, d, e in (("A", ka, ea), ("B", kb, eb)):
            if e is not None:
                for k in sorted(set(d) - e):
                    integrity.append(f"{side}: unexpected row {k} (not in expected_keys)")
    expected = (ea or set()) | (eb or set()) if not legacy else (set(ka) | set(kb))
    same = diff = miss = 0; statuses = []; details = []
    for k in sorted(expected | set(ka) | set(kb)):
        absent = [n for n, d in (("A", ka), ("B", kb)) if k not in d]
        if absent:
            miss += 1
            statuses.append({"key": list(k), "status": "missing", "missing_in": absent})
            continue
        x, y = ka[k], kb[k]
        if x.get("payload_sha256") != y.get("payload_sha256"):
            integrity.append(f"request hash differs for {k}: the two sides did not answer the same request")
        ident = all(x.get(f) == y.get(f) for f in _IDENTITY)
        same += ident; diff += not ident
        statuses.append({"key": list(k), "status": "identical" if ident else "differing"})
        if not ident:
            details.append({"key": list(k), "a": {f: x.get(f) for f in _IDENTITY},
                            "b": {f: y.get(f) for f in _IDENTITY}})
    if same + diff == 0 and not legacy:
        integrity.append("no comparable pairs (pairs == 0)")
    joint = {n: sum(1 for r in d.values()
                    if (r.get("verify") or {}).get("verify_blocks_joint_v1", 0) > 0)
             for n, d in (("A", ka), ("B", kb))}
    print(f"pairs={same + diff} identical={same} differing={diff} missing={miss} "
          f"(A={A.get('tag')} B={B.get('tag')}) joint_rows A={joint['A']} B={joint['B']}")
    for d in details:
        print(" DIFF", tuple(d["key"]), "A:", d["a"]["finish_reason"], d["a"]["completion_tokens"],
              "B:", d["b"]["finish_reason"], d["b"]["completion_tokens"])
    for s_ in statuses:
        if s_["status"] == "missing":
            print(" MISSING", tuple(s_["key"]), "in", ",".join(s_["missing_in"]))
    for p in integrity:
        print(" INTEGRITY", p)
    if legacy:
        print("NON-GATING: a replay without expected_keys (pre-M58 form) cannot establish exact "
              "key coverage; this comparison is informational only (exit 3).")
    if a.out:
        json.dump({"a": A.get("tag"), "b": B.get("tag"), "pairs": same + diff, "identical": same,
                   "differing": diff, "missing": miss, "statuses": statuses, "details": details,
                   "integrity": integrity, "joint_rows": joint, "legacy": legacy},
                  open(a.out, "w"), indent=1)
    if miss or integrity:
        return 2
    if legacy:
        return 3
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
