"""M58 sustained long-context decode runner (spec: docs/specs/m58-joint-verification-scan.md,
"Qualification", instrument 2). Lives in $STACK_WORKDIR/m58 (out of repo).

Per rung (cached-context length) it sends N seeded prompts, each a cold long context built with the
capacity ladder's filler + needle approach (length calibrated via calibrate_cpt) followed by a
question that elicits a long answer; max_tokens = min_emitted_tokens * 1.5, so a healthy completion
ends at the cap (finish_reason "length" is expected, not a failure). Records per request the actual
prompt tokens, completion tokens, decode tok/s (timings.predicted_per_second), prefill s, every
draft_* / verify_* / sdpa_* counter, wall. Rows below --min-emitted-tokens are marked short:true and
are reported, never pooled.

Provenance API (code is written against the m58-provenance worktree module, NOT main's):
  assert_served_config (M50), assert_serving_state(model, expect=entry) (M58 form with `expect`),
  preflight_gather, gather(..., runtime=, router=), assert_served_config_unchanged (C106),
  served_config_drift_record, ServedConfigError. Run with
  PYTHONPATH=<m58 worktree>/benchmark. ExitGuard is NOT used: one local finaliser journals,
  verifies C106 and stamps drift in place.

  PYTHONPATH=<worktree>/benchmark python decode_probe.py run --model M --sampling-profile deployed \
      --tag A1 --seed-base 0 --out $STACK_WORKDIR/m58/decode/A1.json --watch-log .../A1.watch.log
  python decode_probe.py compare --a A1.json A2.json --b B1.json B2.json [--out cmp.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics as st
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from bench import client, provenance, rowschema  # noqa: F401 (provenance is monkeypatchable)

HEADROOM_S = 900.0
HEARTBEAT_S = 300.0
COUNTER_PREFIXES = ("draft_", "verify_", "sdpa_")
DEFAULT_CONTEXTS = "65536,131072,262144"
QUESTION = ("The document above contains {n} secret codes, each stated once. First list all {n} codes, "
            "separated by commas. Then write a long, detailed, numbered analysis (at least 3000 words) "
            "of how the document is structured, quoting each code in the order they appear and "
            "explaining step by step how you found it. Do not stop early.")


class ProbeAbort(RuntimeError):
    """Transport failure / malformed response / refused state: abort nonzero, never grade."""


def derive_timeout(ctx: int, max_tokens: int, floor_tps: float, prefill_floor_tps: float,
                   headroom_s: float = HEADROOM_S) -> float:
    """Prefill at the floor prefill rate + generation at the floor decode rate + headroom."""
    return ctx / prefill_floor_tps + max_tokens / floor_tps + headroom_s


def seed_for(ctx: int, i: int, seed_base: int) -> int:
    return rowschema.sample_seed(f"decode:{ctx}:{i}", 0, base=seed_base)


def build_prompt(ctx: int, i: int, seed_base: int, cpt: float) -> tuple[str, list[str], int]:
    from bench.retrieval import build_context
    seed = seed_for(ctx, i, seed_base)
    context, needles = build_context(ctx, cpt, seed=seed)
    return context + "\n\n" + QUESTION.format(n=len(needles)), needles, seed


def counters_from(timings: dict) -> dict:
    return {k: v for k, v in (timings or {}).items() if k.startswith(COUNTER_PREFIXES)}


def make_row(ctx, i, seed, out, params, min_tokens) -> dict:
    tm = out.get("raw_timings") or {}
    tps = tm.get("predicted_per_second")
    if isinstance(tps, bool) or not isinstance(tps, (int, float)) or not math.isfinite(tps) or tps <= 0:
        raise client.MalformedResponseError(f"timings.predicted_per_second missing/invalid: {tps!r}")
    wall = out.get("wall_s") or 0.0
    pred_ms = tm.get("predicted_ms") or 0.0
    pms = tm.get("prompt_ms")
    prefill_s = round(pms / 1000, 2) if isinstance(pms, (int, float)) and pms > 0 else \
        round(max(wall - pred_ms / 1000, 0.01), 2)
    ctoks = out["completion_tokens"]
    c = counters_from(tm)
    rounds, dn, da = c.get("draft_rounds"), c.get("draft_n"), c.get("draft_n_accepted")
    return {"ctx": ctx, "i": i, "seed": seed, "prompt_tokens": out["prompt_tokens"],
            "completion_tokens": ctoks, "finish_reason": out["finish_reason"],
            "decode_tps": tps, "prefill_s": prefill_s, "wall_s": wall,
            "rounds": rounds, "tokens_per_round": round(ctoks / rounds, 3) if rounds else None,
            "acceptance": round(da / dn, 4) if dn and da is not None else None,
            "short": ctoks < min_tokens, "max_tokens": params["max_tokens"],
            "thinking_budget": params.get("thinking_budget"), "counters": c}


def _median(v):
    return st.median(v) if v else None


def summarize(rows: list[dict]) -> dict:
    out = {}
    for ctx in sorted({r["ctx"] for r in rows}):
        rr = [r for r in rows if r["ctx"] == ctx]
        ok = [r for r in rr if not r["short"]]
        tps = [r["decode_tps"] for r in ok]
        dn = sum((r["counters"].get("draft_n") or 0) for r in ok)
        da = sum((r["counters"].get("draft_n_accepted") or 0) for r in ok)
        out[str(ctx)] = {"n": len(rr), "n_pooled": len(ok), "n_short": len(rr) - len(ok),
                         "decode_tps_median": _median(tps), "decode_tps_min": min(tps) if tps else None,
                         "decode_tps_max": max(tps) if tps else None,
                         "rounds_median": _median([r["rounds"] for r in ok if r["rounds"] is not None]),
                         "acceptance": round(da / dn, 4) if dn else None,
                         "short_rows": [{"i": r["i"], "completion_tokens": r["completion_tokens"]}
                                        for r in rr if r["short"]]}
    return out


def _power() -> dict:
    d = {}
    for k, args in (("ac", ["pmset", "-g", "ac"]), ("batt", ["pmset", "-g", "batt"])):
        try:
            d[k] = " ".join(subprocess.run(args, capture_output=True, text=True, timeout=10).stdout.split())[:160]
        except Exception as e:  # noqa: BLE001
            d[k] = f"unavailable: {type(e).__name__}"
    return d


class Watch:
    """Progress line per request + a heartbeat every `interval` s (bench_watch style): progress,
    mean-based ETA, errors, in-flight age, power. Heartbeat runs in a daemon thread."""

    def __init__(self, total: int, log_path: str | None, interval: float = HEARTBEAT_S, power=_power):
        self.total, self.path, self.interval, self.power = total, log_path, interval, power
        self.done = 0; self.walls: list[float] = []; self.errors = 0
        self.inflight_since: float | None = None; self.inflight_label = ""
        self._stop = threading.Event(); self._t = None; self.t0 = time.monotonic()

    def emit(self, msg: str) -> None:
        line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
        print(line, flush=True)
        if self.path:
            with open(self.path, "a") as f:
                f.write(line + "\n")

    def start_request(self, label: str) -> None:
        self.inflight_since, self.inflight_label = time.monotonic(), label

    def end_request(self, row: dict | None, error: str | None = None) -> None:
        self.inflight_since = None
        if error:
            self.errors += 1
            self.emit(f"[decode_probe] ERROR {error}")
            return
        self.done += 1; self.walls.append(row["wall_s"])
        self.emit(f"[decode_probe] {self.done}/{self.total} ctx={row['ctx']} i={row['i']} "
                  f"ptok={row['prompt_tokens']} ctok={row['completion_tokens']} fin={row['finish_reason']} "
                  f"tps={row['decode_tps']:.2f} prefill_s={row['prefill_s']} wall={row['wall_s']}s "
                  f"rounds={row['rounds']} acc={row['acceptance']} short={row['short']}")

    def heartbeat(self) -> str:
        left = self.total - self.done
        mean = (sum(self.walls) / len(self.walls)) if self.walls else None
        eta = f"{left * mean / 60:.0f}min (mean-based lower bound)" if mean else "unknown"
        inflight = (f"in-flight {self.inflight_label} for {time.monotonic() - self.inflight_since:.0f}s"
                    if self.inflight_since is not None else "idle")
        msg = (f"[decode_probe] HEARTBEAT {self.done}/{self.total} errors={self.errors} eta={eta} {inflight} "
               f"elapsed={time.monotonic() - self.t0:.0f}s power={self.power() if self.power else None}")
        self.emit(msg)
        return msg

    def __enter__(self):
        def loop():
            while not self._stop.wait(self.interval):
                self.heartbeat()
        self._t = threading.Thread(target=loop, daemon=True); self._t.start()
        return self

    def __exit__(self, *a):
        self._stop.set()
        return False


def _dump(path: Path, doc: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=1, allow_nan=False)
    os.replace(tmp, path)


def run_signature(a) -> dict:
    return {"model": a.model, "contexts": [int(x) for x in a.contexts.split(",")],
            "prompts_per_rung": a.prompts_per_rung, "seed_base": a.seed_base,
            "min_emitted_tokens": a.min_emitted_tokens, "sampling_profile": a.sampling_profile}


def run(a, power=_power) -> int:
    from bench.model_params import params_for, registry_context_limit
    try:    # M50 before anything is read, written or requested
        router = provenance.assert_served_config(client.BASE)
    except RuntimeError as e:
        print(f"[decode_probe] REFUSED: {e}", file=sys.stderr, flush=True)
        return 2
    sig = run_signature(a)
    out = Path(a.out)
    rows, history = [], []
    if out.exists():
        if not a.resume:
            print(f"[decode_probe] REFUSED: {out} exists; use --resume or a fresh --out", file=sys.stderr, flush=True)
            return 2
        prev = json.load(open(out))
        prr = prev.get("router") or {}
        reasons = []
        if prev.get("status") == "complete":
            reasons.append("journal is already complete")
        if "served_config_drift" in prev:
            reasons.append("journal carries a served_config_drift stamp")
        if prev.get("signature") != sig:
            reasons.append("run signature (model/contexts/prompts/seed-base/min-tokens/profile) differs")
        if prev.get("tag") != a.tag:
            reasons.append("tag differs")
        if prr.get("config") and prr.get("config") != router["config"]:
            reasons.append(f"served config {prr.get('config')!r} != {router['config']!r}")
        if prr.get("config_sha256") and prr.get("config_sha256") != router["config_sha256"]:
            reasons.append("served config sha256 differs (registry edited since the journal)")
        if reasons:
            print(f"[decode_probe] REFUSED resume of {out}: " + "; ".join(reasons), file=sys.stderr, flush=True)
            return 2
        rows = prev["rows"]; history = list(prev.get("router_history") or [])
        if prr.get("pid") is not None and prr.get("pid") != router["pid"]:
            history.append(prr)
    out.parent.mkdir(parents=True, exist_ok=True)
    state = {"status": "running", "error": None, "drift": None, "serving": None, "manifest": None}
    done = {(r["ctx"], r["i"]) for r in rows}

    def doc(extra=None):
        d = {"status": state["status"], "tag": a.tag, "base": client.BASE, "signature": sig,
             "router": router, "router_history": history, "serving_state": state["serving"],
             "when": datetime.now().isoformat(timespec="seconds"), "rows": rows, "summary": summarize(rows)}
        if state["error"]:
            d["error"] = state["error"]
        if state["drift"]:
            d["served_config_drift"] = state["drift"]
        if state["manifest"]:
            d["manifest"] = state["manifest"]
        if extra:
            d.update(extra)
        return d

    def finalise(status: str, error: str | None, code: int) -> int:
        """The ONE exit path: C106 verification (also after an abort), drift stamp, journal."""
        exit_blk = None
        try:
            exit_blk = provenance.assert_served_config_unchanged(router, client.BASE)
        except provenance.ServedConfigError as e:
            state["drift"] = provenance.served_config_drift_record(router, client.BASE, e)
            error = f"{error + '; ' if error else ''}{e}"
            status, code = "aborted", 2
        except Exception as e:  # noqa: BLE001
            error = f"{error + '; ' if error else ''}C106 verification failed: {type(e).__name__}: {e}"
            status, code = "aborted", 2
        state["status"], state["error"] = status, error
        _dump(out, doc({"router_exit": exit_blk}))
        if status == "complete":
            _dump(out.with_name(out.name + ".manifest.json"), state["manifest"])
            print(f"[decode_probe] complete: {len(rows)} rows -> {out}", flush=True)
        else:
            print(f"[decode_probe] ABORTED ({error})", file=sys.stderr, flush=True)
        return code

    try:
        params = {**params_for(a.model, profile=a.sampling_profile),
                  "max_tokens": int(a.min_emitted_tokens * 1.5)}
        if a.thinking_budget is not None:
            params["thinking_budget"] = a.thinking_budget
        params["enable_thinking"] = True
        ctxs = sig["contexts"]
        limit = registry_context_limit(a.model)
        if limit and any(c + params["max_tokens"] > limit for c in ctxs):
            raise ProbeAbort(f"context + max_tokens exceeds the registry context limit {limit}")
        entry_state = provenance.assert_serving_state(a.model)
        state["serving"] = entry_state
        try:
            provenance.preflight_gather(a.model, profile=a.sampling_profile, router=router,
                                        label="decode_probe")
        except provenance.ProvenancePreflightError as e:
            raise ProbeAbort(f"provenance preflight: {e}") from e
        pending = [(c, i) for c in ctxs for i in range(a.prompts_per_rung) if (c, i) not in done]
        total = len(pending)
        _dump(out, doc())
        watch = Watch(total, a.watch_log, a.heartbeat_s, power=power if a.power else None)
        watch.emit(f"[decode_probe] start tag={a.tag} model={a.model} {total} requests "
                   f"({len(done)} done) scan={entry_state.get('mtp_verify_scan')}")
        with watch:
            if not a.no_preload:
                try:
                    client.preload(a.model)
                except Exception as e:  # noqa: BLE001
                    raise ProbeAbort(f"preload failed: {type(e).__name__}: {e}") from e
            from bench.driver import MlxServeDriver
            from bench.run_capacity import calibrate_cpt
            try:
                cpt = a.cpt if a.cpt else calibrate_cpt(MlxServeDriver(), a.model)
            except Exception as e:  # noqa: BLE001
                raise ProbeAbort(f"calibration failed: {type(e).__name__}: {e}") from e
            try:    # once loaded: the resolved scan must still be the entry one
                state["serving"] = provenance.assert_serving_state(a.model, expect=entry_state)
            except provenance.ServedConfigError as e:
                raise ProbeAbort(f"serving state: {e}") from e
            watch.emit(f"[decode_probe] cpt={cpt:.3f} params max_tokens={params['max_tokens']} "
                       f"thinking_budget={params.get('thinking_budget')}")
            first_checked = bool(rows)
            for n, (ctx, i) in enumerate(pending, 1):
                text, needles, seed = build_prompt(ctx, i, a.seed_base, cpt)
                body_params = {**params, "seed": seed}
                timeout = derive_timeout(ctx, params["max_tokens"], a.timeout_floor_tps,
                                         a.prefill_floor_tps, a.headroom_s)
                watch.start_request(f"ctx={ctx} i={i}")
                try:
                    res = client.probe(a.model, [{"role": "user", "content": text}], body_params,
                                       timeout=timeout)
                    row = make_row(ctx, i, seed, res, params, a.min_emitted_tokens)
                except Exception as e:  # noqa: BLE001 transport / malformed: escalate, never grade
                    msg = f"ctx={ctx} i={i}: {type(e).__name__}: {e}"
                    watch.end_request(None, error=msg)
                    raise ProbeAbort(msg) from e
                row["timeout_s"] = round(timeout, 1)
                row["needles"] = needles
                rows.append(row)
                watch.end_request(row)
                _dump(out, doc())
                if not first_checked:   # first manifest: draft_kind + registry sha before item two
                    first_checked = True
                    m = provenance.gather(a.model, profile=a.sampling_profile, router=router,
                                          overrides={k: body_params[k] for k in ("max_tokens", "seed")},
                                          runtime={"probe": "decode_probe_first"})
                    dk = (m.get("runtime") or {}).get("draft_kind")
                    rs = (m.get("registry") or {}).get("sha256")
                    if (a.expect_draft_kind and dk != a.expect_draft_kind) or not rs:
                        raise ProbeAbort(f"first manifest check: runtime.draft_kind={dk!r} "
                                         f"(expected {a.expect_draft_kind!r}) registry.sha256={rs!r}")
                    watch.emit(f"[decode_probe] first manifest ok draft_kind={dk} registry_sha256={rs[:12]}")
        agg = {}
        for r in rows:
            for k, v in r["counters"].items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    agg[k] = agg.get(k, 0) + v
        state["manifest"] = provenance.gather(
            a.model, profile=a.sampling_profile, router=router,
            overrides={"max_tokens": params["max_tokens"]},
            runtime={"probe": "decode_probe", "contexts": ctxs, "prompts_per_rung": a.prompts_per_rung,
                     "seed_base": a.seed_base, "min_emitted_tokens": a.min_emitted_tokens,
                     "timeout_floor_tps": a.timeout_floor_tps, "prefill_floor_tps": a.prefill_floor_tps,
                     "counters": agg, "tag": a.tag})
    except (ProbeAbort, provenance.ServedConfigError, provenance.ProvenancePreflightError) as e:
        return finalise("aborted", f"{type(e).__name__}: {e}", 2)
    except BaseException as e:  # noqa: BLE001 incl. KeyboardInterrupt: always journal + C106
        finalise("aborted", f"{type(e).__name__}: {e}", 2)
        raise
    return finalise("complete", None, 0)


# ---------------------------------------------------------------- compare
def bootstrap_ci(pairs: list[tuple[float, float]], n_boot: int = 10000, seed: int = 0, alpha: float = 0.05):
    """Percentile bootstrap over prompt pairs of median(B)/median(A) - 1 (percent)."""
    if not pairs:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(n_boot):
        s = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        vals.append((st.median(b for _, b in s) / st.median(a for a, _ in s) - 1) * 100)
    vals.sort()
    return [round(vals[int(alpha / 2 * n_boot)], 2), round(vals[min(int((1 - alpha / 2) * n_boot), n_boot - 1)], 2)]


def compare_docs(A: list[dict], B: list[dict], n_boot: int = 10000) -> dict:
    if len(A) != len(B):
        raise ValueError("--a and --b need the same number of sessions (session s pairs a[s] with b[s])")
    for d in A + B:
        if d.get("status") != "complete":
            raise ValueError(f"run {d.get('tag')!r} is not complete (status={d.get('status')!r})")
        if "served_config_drift" in d:
            raise ValueError(f"run {d.get('tag')!r} carries a served_config_drift stamp")
    sigs = [json.dumps(d["signature"], sort_keys=True) for d in A + B]
    if len(set(sigs)) != 1:
        raise ValueError("runs differ in signature (model/contexts/prompts/seed-base/min-tokens/profile)")
    per: dict[int, list] = {}
    skipped = []
    for s, (da, db) in enumerate(zip(A, B)):
        ka = {(r["ctx"], r["i"]): r for r in da["rows"]}
        kb = {(r["ctx"], r["i"]): r for r in db["rows"]}
        for k in sorted(set(ka) | set(kb)):
            x, y = ka.get(k), kb.get(k)
            why = ("missing in A" if x is None else "missing in B" if y is None else
                   "short row" if x["short"] or y["short"] else
                   "prompt_tokens differ" if x["prompt_tokens"] != y["prompt_tokens"] else None)
            if why:
                skipped.append({"session": s, "ctx": k[0], "i": k[1], "why": why})
                continue
            per.setdefault(k[0], []).append({"session": s, "i": k[1], "a": x["decode_tps"], "b": y["decode_tps"],
                                             "delta_pct": round((y["decode_tps"] / x["decode_tps"] - 1) * 100, 2),
                                             "rounds_a": x["rounds"], "rounds_b": y["rounds"],
                                             "acc_a": x["acceptance"], "acc_b": y["acceptance"]})
    rungs = {}
    for ctx, ps in sorted(per.items()):
        pairs = [(p["a"], p["b"]) for p in ps]
        rungs[str(ctx)] = {"n_pairs": len(ps), "median_a": st.median(p[0] for p in pairs),
                           "median_b": st.median(p[1] for p in pairs),
                           "median_delta_pct": round((st.median(p[1] for p in pairs) /
                                                      st.median(p[0] for p in pairs) - 1) * 100, 2),
                           "mean_paired_delta_pct": round(st.mean(p["delta_pct"] for p in ps), 2),
                           "paired_deltas_pct": [p["delta_pct"] for p in ps],
                           "ci95_median_ratio_pct": bootstrap_ci(pairs, n_boot),
                           "rounds_differ": sum(1 for p in ps if p["rounds_a"] != p["rounds_b"]),
                           "pairs": ps}
    return {"a_tags": [d["tag"] for d in A], "b_tags": [d["tag"] for d in B],
            "a_scan": [(d.get("serving_state") or {}).get("mtp_verify_scan") for d in A],
            "b_scan": [(d.get("serving_state") or {}).get("mtp_verify_scan") for d in B],
            "rungs": rungs, "skipped": skipped}


def compare(a) -> int:
    try:
        res = compare_docs([json.load(open(p)) for p in a.a], [json.load(open(p)) for p in a.b], a.n_boot)
    except ValueError as e:
        print(f"[decode_probe] compare REFUSED: {e}", file=sys.stderr, flush=True)
        return 2
    for ctx, r in res["rungs"].items():
        print(f"ctx={ctx} pairs={r['n_pairs']} A={r['median_a']:.2f} B={r['median_b']:.2f} "
              f"median_delta={r['median_delta_pct']:+.2f}% mean_paired={r['mean_paired_delta_pct']:+.2f}% "
              f"CI95={r['ci95_median_ratio_pct']} rounds_differ={r['rounds_differ']}")
    if res["skipped"]:
        print(f"skipped {len(res['skipped'])} pair(s): {res['skipped']}")
    if a.out:
        json.dump(res, open(a.out, "w"), indent=1)
    return 1 if any(r["rounds_differ"] for r in res["rungs"].values()) and a.strict_rounds else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--model", required=True)
    r.add_argument("--contexts", default=DEFAULT_CONTEXTS)
    r.add_argument("--prompts-per-rung", type=int, default=3)
    r.add_argument("--seed-base", type=int, default=0)
    r.add_argument("--min-emitted-tokens", type=int, default=1024)
    r.add_argument("--thinking-budget", type=int, default=None,
                   help="fixed generous budget; default = the deployed generation_defaults value")
    r.add_argument("--out", required=True)
    r.add_argument("--tag", required=True)
    r.add_argument("--sampling-profile", required=True, choices=["deployed"])
    r.add_argument("--timeout-floor-tps", type=float, default=8.0)
    r.add_argument("--prefill-floor-tps", type=float, default=100.0)
    r.add_argument("--headroom-s", type=float, default=HEADROOM_S)
    r.add_argument("--expect-draft-kind", default="mtp")
    r.add_argument("--watch-log", default=None)
    r.add_argument("--heartbeat-s", type=float, default=HEARTBEAT_S)
    r.add_argument("--no-power", dest="power", action="store_false")
    r.add_argument("--no-preload", action="store_true")
    r.add_argument("--cpt", type=float, default=None, help="skip calibration (tests/smoke only)")
    r.add_argument("--resume", action="store_true")
    c = sp.add_parser("compare")
    c.add_argument("--a", nargs="+", required=True); c.add_argument("--b", nargs="+", required=True)
    c.add_argument("--out", default=None); c.add_argument("--n-boot", type=int, default=10000)
    c.add_argument("--strict-rounds", action="store_true", help="exit 1 if draft_rounds differ on any pair")
    a = ap.parse_args(argv)
    if a.cmd == "compare":
        return compare(a)
    try:
        ctxs = [int(x) for x in a.contexts.split(",")]
        if (not ctxs or any(x <= 0 for x in ctxs) or a.prompts_per_rung < 1 or a.min_emitted_tokens < 1
                or a.timeout_floor_tps <= 0 or a.prefill_floor_tps <= 0):
            raise ValueError("contexts, counts and floor rates must be positive")
    except ValueError as e:
        ap.error(str(e))
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
