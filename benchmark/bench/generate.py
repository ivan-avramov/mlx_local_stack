"""Chunked, resumable generation loop.

- Model-OUTER ordering: each model loads once (one swap), runs all its items.
- Every completed item is appended to results/<model>/<bench>.jsonl immediately, so
  Ctrl+C / closing the laptop loses at most the in-flight item. Rerun = resume.
- Work runs in ~chunk-minutes time boxes; at each breakpoint we print progress + ETA.
  `chunks="all"` runs to completion; `chunks=N` auto-runs N chunks then stops (runway).
"""
import json
import time
from pathlib import Path

from . import benchmarks, client, convergence, model_params

RESULTS = Path("benchmark/results")


def _safe(model: str) -> str:
    return model.replace("/", "__")


def result_path(model: str, bench: str) -> Path:
    return RESULTS / _safe(model) / f"{bench}.jsonl"


def done_ids(model: str, bench: str) -> set:
    """IDs already generated without error (errors are retried on resume)."""
    p = result_path(model, bench)
    if not p.exists():
        return set()
    out = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("id") is not None and not row.get("error"):
            out.add(row["id"])
    return out


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _conv_row(p, params):
    return {"finish_reason": p.get("finish_reason"),
            "completion_tokens": p.get("completion_tokens"),
            "thinking_budget": params.get("thinking_budget")}


def probe_with_recovery(model, messages, params, *, probe_fn, restart_fn=None, preload_fn=None):
    """Probe once; if it looped/truncated AND restart_fn is given, restart the router and
    re-probe ONCE. Returns (probe_result, recovery):
      None            -> converged (or N/A); no restart needed
      'recovered'     -> looped, then converged after a fresh router => stale-router state
      'loop_persisted'-> looped AGAIN on a fresh router => genuine quant/model loop
    Auto-distinguishes the two root causes (stale router vs quant) without a human in loop."""
    p = probe_fn(model, messages, params)
    if restart_fn is None or convergence.is_converged(_conv_row(p, params)) is not False:
        return p, None
    restart_fn()
    if preload_fn is not None:
        preload_fn(model)
    p2 = probe_fn(model, messages, params)
    recovery = "recovered" if convergence.is_converged(_conv_row(p2, params)) is not False \
        else "loop_persisted"
    return p2, recovery


def build_queue(models, benches, limits, seed, order="roundrobin"):
    """order='roundrobin' (default): item-major — every model gets item i of each bench
    before any model gets item i+1, so any stopping prefix is a balanced comparison.
    order='model': model-major — each model finishes all its items before the next
    (fewest swaps; complete one model at a time)."""
    cache = {}
    for b in benches:
        try:
            cache[b] = benchmarks.load(b, limits.get(b), seed)
        except Exception as e:  # noqa: BLE001 — gated/missing dataset or package
            print(f"  [skip] benchmark {b!r} unavailable: {type(e).__name__}: {str(e)[:80]}", flush=True)
    counts = {b: len(v) for b, v in cache.items()}
    done = {(m, b): done_ids(m, b) for m in models for b in cache}
    queue = []
    if order == "model":
        for model in models:
            for b in cache:
                for it in cache[b]:
                    if it["id"] not in done[(model, b)]:
                        queue.append((model, b, it))
    else:                                       # roundrobin (item-major)
        maxn = max((len(v) for v in cache.values()), default=0)
        for i in range(maxn):
            for model in models:                # group a model's item-i across benches => 1 swap/round
                for b in cache:
                    if i < len(cache[b]):
                        it = cache[b][i]
                        if it["id"] not in done[(model, b)]:
                            queue.append((model, b, it))
    return queue, counts


def _fmt_eta(seconds: float) -> str:
    if seconds < 0 or seconds != seconds:  # nan guard
        return "?"
    h, rem = divmod(int(seconds), 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h{m:02d}m"


def run(models, benches, limits, seed=0, chunk_minutes=30.0, chunks="all", overrides=None,
        order="roundrobin", restart_fn=None):
    overrides = overrides or {}  # global param overrides on top of each model's config params
    queue, counts = build_queue(models, benches, limits, seed, order=order)
    total = sum(counts.values()) * len(models)
    if not queue:
        print(f"[generate] nothing to do — all {total} items already generated.", flush=True)
        return
    print(f"[generate] {len(queue)} items remaining of {total} "
          f"({len(models)} models x {benches}). chunk={chunk_minutes}min, runway={chunks}.", flush=True)

    # Provenance: stamp every (model, bench) with its exact config (box, code SHAs, quant
    # effective-bits, KV config, sampling) so results are never silently cross-compared.
    from . import provenance  # lazy (provenance imports generate)
    for m, b, _ in queue:
        mp = result_path(m, b).with_suffix(".manifest.json")
        if not mp.exists():
            try:
                provenance.write(m, b)
            except Exception as e:  # noqa: BLE001 — never block a run on provenance
                print(f"  [provenance] skipped {m}/{b}: {type(e).__name__}: {str(e)[:60]}", flush=True)

    per_item = {}                       # model -> list of per-item seconds (rolling)
    cur_model = None
    chunk_idx = 0
    chunk_start = time.perf_counter()
    chunk_items = 0
    i = 0
    try:
        while i < len(queue):
            model, b, it = queue[i]
            if model != cur_model:
                load_s = client.preload(model)
                print(f"  >> loaded {model} ({load_s}s)", flush=True)
                cur_model = model
            t0 = time.perf_counter()
            try:
                params = model_params.params_for(model)
                params.update(overrides)
                p, recovery = probe_with_recovery(
                    model, benchmarks.build_messages(b, it), params,
                    probe_fn=client.probe, restart_fn=restart_fn, preload_fn=client.preload)
                if recovery:
                    print(f"  [loop-recovery] {model}/{b}/{it['id']}: {recovery}", flush=True)
                row = {"id": it["id"], "bench": b, "model": model, "recovery": recovery,
                       "answer_gold": it.get("answer"), "options": it.get("options"),
                       "content": client.strip_thinking(p["content"]),
                       "completion_tokens": p["completion_tokens"], "prompt_tokens": p["prompt_tokens"],
                       "decode_tps": p["decode_tps"], "peak_mem_gb": p["peak_mem_gb"],
                       "finish_reason": p["finish_reason"], "wall_s": p["wall_s"],
                       "temperature": params.get("temperature"), "thinking_budget": params.get("thinking_budget")}
                # Convergence guard: a thinking-budget / max_tokens hit is NOT convergence
                # even though finish_reason can be "stop". Recorded per item; a run with any
                # non-converged item is flagged INVALID at grade time (never silently scored).
                row["converged"] = convergence.is_converged(row)
            except Exception as e:  # noqa: BLE001 — network/OOM; record & continue
                row = {"id": it["id"], "bench": b, "model": model, "error": str(e)[:200]}
            _append(result_path(model, b), row)
            dt = time.perf_counter() - t0
            per_item.setdefault(model, []).append(dt)
            i += 1
            chunk_items += 1

            if (time.perf_counter() - chunk_start) >= chunk_minutes * 60:
                chunk_idx += 1
                # ETA: remaining items per model x that model's rolling avg item time
                rem = {}
                for m, bb, _ in queue[i:]:
                    rem[m] = rem.get(m, 0) + 1
                eta = sum(n * (sum(per_item.get(m, [dt])) / len(per_item.get(m, [dt]))) for m, n in rem.items())
                print(f"  --- breakpoint: chunk {chunk_idx} done | {i}/{len(queue)} items "
                      f"({chunk_items} this chunk) | ETA to finish ~{_fmt_eta(eta)} | "
                      f"safe to stop (Ctrl+C); rerun to resume ---", flush=True)
                if chunks != "all" and chunk_idx >= int(chunks):
                    print(f"[generate] chunk runway ({chunks}) reached — stopping. "
                          f"{len(queue) - i} items left; rerun the same command to continue.", flush=True)
                    return
                chunk_start = time.perf_counter()
                chunk_items = 0
        print(f"[generate] COMPLETE — {i} items generated. Run `grade` next.", flush=True)
    except KeyboardInterrupt:
        print(f"\n[generate] interrupted at {i}/{len(queue)} — progress saved. "
              f"Rerun the same command to resume.", flush=True)
