"""Chunked, resumable generation loop.

- Model-OUTER ordering: each model loads once (one swap), runs all its items.
- Every completed item is appended to results/<model>/<bench>.jsonl immediately, so
  Ctrl+C / closing the laptop loses at most the in-flight item. Rerun = resume.
- Work runs in ~chunk-minutes time boxes; at each breakpoint we print progress + ETA.
  `chunks="all"` runs to completion; `chunks=N` auto-runs N chunks then stops (runway).
"""
import json
import os
import time
from pathlib import Path

from . import benchmarks, client, convergence, model_params, paths, rowschema, traces

# ABSOLUTE, resolved from the module location. It was Path("benchmark/results") — CWD-relative, so
# running from benchmark/ wrote a second invisible tree at benchmark/benchmark/results/. Same
# absolute value as a repo-root invocation, so existing trees are untouched. See bench/paths.py.
_DEFAULT_RESULTS = paths.default_results_root()
RESULTS = _DEFAULT_RESULTS          # module-level seam; tests monkeypatch this


def results_root() -> Path:
    """The single root of the results tree. Precedence:

        explicitly-overridden module RESULTS  >  $MLX_BENCH_RESULTS  >  the default

    "Explicitly overridden" = differs from the shipped default, which is what a test's
    ``monkeypatch.setattr(generate, "RESULTS", tmp_path)`` does and what normal operation never
    does. The monkeypatch has to WIN over the env var: otherwise an operator with
    MLX_BENCH_RESULTS exported would silently redirect every test's writes into the real tree.
    """
    if Path(RESULTS) != _DEFAULT_RESULTS:
        return Path(RESULTS)
    env = os.environ.get("MLX_BENCH_RESULTS")
    return Path(env) if env else Path(RESULTS)


def _safe(model: str) -> str:
    return model.replace("/", "__")


def result_path(model: str, bench: str) -> Path:
    return results_root() / _safe(model) / f"{bench}.jsonl"


def _read_rows(model: str, bench: str) -> list:
    p = result_path(model, bench)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def done_ids(model: str, bench: str) -> set:
    """IDs already generated without error (errors are retried on resume). Sample-blind — kept
    for existing callers; multi-sample resume uses done_keys()."""
    return {r["id"] for r in _read_rows(model, bench)
            if r.get("id") is not None and not r.get("error")}


def done_keys(model: str, bench: str) -> set:
    """(id, sample) pairs already generated without error.

    Resume identity must include the sample index: `done_ids` would consider an item finished
    after ONE of its k samples. A v1 row (no `sample` field) counts as sample 0 — that is how
    every result already on disk keeps resuming instead of regenerating.
    """
    return {rowschema.row_key(r) for r in _read_rows(model, bench)
            if r.get("id") is not None and not r.get("error")}


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
    re-probe ONCE. Returns (primary, recovery, secondary):
      recovery=None            -> converged (or N/A); no restart needed
      'genuine_nonconvergence' -> a clean budget-hit; NOT retried (see below)
      'recovered'              -> looped, then converged after a fresh router => stale-router state
      'loop_persisted'         -> looped AGAIN on a fresh router => genuine quant/model loop
    Auto-distinguishes the two root causes (stale router vs quant) without a human in the loop.

    `primary` is ALWAYS the FIRST probe, and `secondary` (the post-restart retry, or None) is
    returned alongside rather than replacing it. That asymmetry is the whole point:

      * Returning the SECOND probe as the datum — the original behaviour — grants an extra draw
        selectively to failures, inflating conv% for precisely the loop-prone models whose
        convergence is under investigation. The measurement drifts toward the hypothesis.
      * Returning the first probe and SCORING it is the opposite error: it is a known
        stale-router artifact, so pass@1 absorbs a corrupted generation.

    So the caller records the first probe as the convergence datum, keeps the second for
    diagnosis, and marks the row contaminated so grading can exclude it from pass@1 with a
    reported count. Neither number is quietly fabricated.
    """
    p = probe_fn(model, messages, params)
    if restart_fn is None or convergence.is_converged(_conv_row(p, params)) is not False:
        return p, None, None
    # Non-converged. A router restart only helps a DEGENERATE loop (the stale-router cause).
    # A clean budget-hit (genuine long reasoning that didn't finish) won't be helped — retrying
    # just burns another full generation on a slow model — so flag it and move on.
    if not convergence.looks_like_loop(p.get("reasoning")):
        return p, "genuine_nonconvergence", None
    restart_fn()
    if preload_fn is not None:
        preload_fn(model)
    p2 = probe_fn(model, messages, params)
    recovery = "recovered" if convergence.is_converged(_conv_row(p2, params)) is not False \
        else "loop_persisted"
    return p, recovery, p2


def provenance_precheck(models, benches, profile="production", clean_stale=False, overrides=None):
    """Guard against the stale-results contamination: an existing results file produced under
    a DIFFERENT config (sampling/profile/KV) than this run cannot be mixed in via done_ids
    resume. For each (model, bench) with existing results, compare its manifest to the current
    config; on mismatch either delete it (clean_stale) so it regenerates fresh, or warn loudly
    and keep it (default). Compatible (same-config) results are left to resume normally.
    `overrides` are CLI sampling overrides (e.g. --temperature) layered on the profile — they
    are folded into the current config so an OFAT sweep correctly treats prior-temperature
    results as stale. Returns a list of (model, bench, action) for the affected pairs."""
    from . import provenance
    actions = []
    for m in models:
        try:
            cur = provenance.current_manifest_lite(m, profile, overrides=overrides)
        except Exception as e:  # noqa: BLE001 — never block a run on the precheck
            print(f"  [provenance] precheck skipped {m}: {type(e).__name__}: {str(e)[:60]}", flush=True)
            continue
        for b in benches:
            jsonl = result_path(m, b)
            if not jsonl.exists():
                continue
            mp = jsonl.with_suffix(".manifest.json")
            existing = None
            if mp.exists():
                try:
                    existing = json.loads(mp.read_text())
                except Exception:  # noqa: BLE001
                    existing = None
            if provenance.is_compatible(existing, cur):
                continue
            if clean_stale:
                jsonl.unlink()
                if mp.exists():
                    mp.unlink()
                actions.append((m, b, "cleaned"))
                print(f"  [provenance] CLEANED stale {m}/{b} (config differs from this run) "
                      f"— regenerating fresh", flush=True)
            else:
                actions.append((m, b, "stale"))
                print(f"  [provenance] ⚠️  STALE {m}/{b}: existing results were produced under a "
                      f"DIFFERENT config — resume would MIX provenance. Re-run with --clean-stale "
                      f"(or delete the file).", flush=True)
    return actions


def build_queue(models, benches, limits, seed, order="roundrobin", samples: int = 1):
    """Build the work queue of (model, bench, item, sample) entries.

    order='roundrobin' (default): item-major — every model gets item i of each bench
    before any model gets item i+1, so any stopping prefix is a balanced comparison.
    order='model': model-major — each model finishes all its items before the next
    (fewest swaps; complete one model at a time).

    `samples` is the OUTERMOST loop in both orderings: a full sweep of every item at sample 0
    completes before any item reaches sample 1. Generation is interruptible by design, so a
    stopped prefix has to be a balanced measurement; the other nesting would leave a partial run
    holding 3 samples of item 1 and nothing of items 2..15, and a reliability number computed
    from a single item is worse than none.
    """
    cache = {}
    for b in benches:
        try:
            cache[b] = benchmarks.load(b, limits.get(b), seed)
        except Exception as e:  # noqa: BLE001 — gated/missing dataset or package
            print(f"  [skip] benchmark {b!r} unavailable: {type(e).__name__}: {str(e)[:80]}", flush=True)
    counts = {b: len(v) for b, v in cache.items()}
    done = {(m, b): done_keys(m, b) for m in models for b in cache}
    queue = []
    if order == "model":
        for model in models:
            for b in cache:
                for s in range(samples):
                    for it in cache[b]:
                        if rowschema.key(it["id"], s) not in done[(model, b)]:
                            queue.append((model, b, it, s))
    else:                                       # roundrobin (item-major)
        maxn = max((len(v) for v in cache.values()), default=0)
        for s in range(samples):
            for i in range(maxn):
                for model in models:            # group a model's item-i across benches => 1 swap/round
                    for b in cache:
                        if i < len(cache[b]):
                            it = cache[b][i]
                            if rowschema.key(it["id"], s) not in done[(model, b)]:
                                queue.append((model, b, it, s))
    return queue, counts


def _fmt_eta(seconds: float) -> str:
    if seconds < 0 or seconds != seconds:  # nan guard
        return "?"
    h, rem = divmod(int(seconds), 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h{m:02d}m"


def run(models, benches, limits, seed=0, chunk_minutes=30.0, chunks="all", overrides=None,
        order="roundrobin", restart_fn=None, sampling_profile="production", probe_timeout=3600,
        clean_stale=False, samples: int = 1, seed_base: int = 0):
    overrides = overrides or {}  # global param overrides on top of each model's config params
    # Per-probe HTTP timeout, bound via a closure so probe_with_recovery's (model, msg, params)
    # call signature is unchanged. The default 3600s is too short for a slow dense model whose
    # thinking budget implies >60min of generation (e.g. Qwen3.6-27B @ ~13.5 tok/s, 80K budget).
    def _probe(m, msg, pa):
        return client.probe(m, msg, pa, timeout=probe_timeout)
    # Provenance guard: never resume on top of results produced under a different config
    # (the stale-results contamination). Runs BEFORE build_queue so cleaned files don't leak
    # into done_ids. clean_stale deletes mismatched files; default just warns.
    provenance_precheck(models, benches, profile=sampling_profile, clean_stale=clean_stale,
                        overrides=overrides)
    queue, counts = build_queue(models, benches, limits, seed, order=order, samples=samples)
    total = sum(counts.values()) * len(models) * samples
    if not queue:
        print(f"[generate] nothing to do — all {total} items already generated.", flush=True)
        return
    print(f"[generate] {len(queue)} items remaining of {total} "
          f"({len(models)} models x {benches} x {samples} sample(s)). "
          f"chunk={chunk_minutes}min, runway={chunks}.", flush=True)

    # Provenance: stamp every (model, bench) with its exact config (box, code SHAs, quant
    # effective-bits, KV config, sampling) so results are never silently cross-compared.
    from . import provenance  # lazy (provenance imports generate)
    for m, b, _it, _s in queue:
        mp = result_path(m, b).with_suffix(".manifest.json")
        if not mp.exists():
            try:
                provenance.write(m, b, profile=sampling_profile, overrides=overrides)
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
            model, b, it, sample = queue[i]
            if model != cur_model:
                load_s = client.preload(model)
                print(f"  >> loaded {model} ({load_s}s)", flush=True)
                cur_model = model
            t0 = time.perf_counter()
            try:
                params = model_params.params_for(model, profile=sampling_profile)
                params.update(overrides)
                # EVERY draw carries an explicit seed. Measured on the live server: with no
                # seed, repeated identical requests return BYTE-IDENTICAL text (the sampler is
                # keyed deterministically per request, DEFAULT_SEED=0, and the shipped
                # suffix-decoding path keys off (seed, row_id, position)). So k unseeded samples
                # are k copies of one generation -- pass^k would collapse to pass@1 and
                # reliability would report perfect stability for every model. Seeding also makes
                # the draws reproducible, which is what distinguishes a resume from a re-draw.
                draw_seed = rowschema.sample_seed(it["id"], sample, base=seed_base)
                params["seed"] = draw_seed
                p, recovery, retry = probe_with_recovery(
                    model, benchmarks.build_messages(b, it), params,
                    probe_fn=_probe, restart_fn=restart_fn, preload_fn=client.preload)
                if recovery:
                    print(f"  [loop-recovery] {model}/{b}/{it['id']}: {recovery}", flush=True)
                row = {"id": it["id"], "sample": sample,
                       "schema_version": rowschema.SCHEMA_VERSION,
                       "sampler_seed": draw_seed, "seed_base": seed_base,
                       "bench": b, "model": model, "recovery": recovery,
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
                # Persist a COMPRESSED view of the thinking trace + its statistics. The full
                # text is dropped (an 82K-token meander would bloat the jsonl ~40x), but the
                # head, the tail and the repetition/novelty statistics are enough to classify a
                # non-convergence offline. Without this, typing a DNF meant re-running the model
                # under a bespoke live probe — which is how the campaign lost the ability to
                # tell "degenerate repetition" from "meander" on runs already completed.
                row.update(traces.compress_trace(p.get("reasoning")))
                row["reasoning_stats"] = traces.trace_stats(p.get("reasoning"))
                row["nonconv_kind"] = traces.classify(row)
                # A restart-retry is DIAGNOSTIC, not the datum. The first probe stays recorded
                # above; the retry is nested here and the row is flagged so grading excludes it
                # from pass@1 (scoring a known stale-router artifact would be the mirror-image
                # bias of letting the retry silently replace it). See probe_with_recovery.
                if retry is not None:
                    rp = {"content": client.strip_thinking(retry["content"]),
                          "completion_tokens": retry["completion_tokens"],
                          "finish_reason": retry["finish_reason"],
                          "wall_s": retry["wall_s"],
                          "thinking_budget": params.get("thinking_budget")}
                    rp["converged"] = convergence.is_converged(rp)
                    row["recovery_probe"] = rp
                    row["contaminated"] = "stale_router"
            except Exception as e:  # noqa: BLE001 — network/OOM; record & continue
                # An error row carries the same (id, sample) identity: resume retries errored
                # rows, and without `sample` it could not tell which draw to redo.
                row = {"id": it["id"], "sample": sample,
                       "schema_version": rowschema.SCHEMA_VERSION,
                       "sampler_seed": rowschema.sample_seed(it["id"], sample, base=seed_base),
                       "seed_base": seed_base,
                       "bench": b, "model": model, "error": str(e)[:200]}
            _append(result_path(model, b), row)
            dt = time.perf_counter() - t0
            per_item.setdefault(model, []).append(dt)
            i += 1
            chunk_items += 1

            if (time.perf_counter() - chunk_start) >= chunk_minutes * 60:
                chunk_idx += 1
                # ETA: remaining items per model x that model's rolling avg item time
                rem = {}
                for m, bb, _it2, _s2 in queue[i:]:
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
