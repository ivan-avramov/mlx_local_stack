"""CLI: run the reasoning ladder (variable-tracking) for one model on the box under test.

  cd benchmark && uv run python -m bench.run_reasoning --model Qwen3.6-27B-UD-MLX-6bit

Writes benchmark/results/<model>/reasoning.json."""
import argparse
import json
import os
import sys

from . import client, provenance
from .driver import MlxServeDriver
from .instrument import MemorySampler, await_model_pid, system_used_gb
from .model_params import params_for
from .reasoning import run_reasoning_ladder, REASONING_GRID

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")

_CAL_FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "


def calibrate_cpt(driver, model: str) -> float:
    """Calibrate chars-per-token for the model."""
    out = driver.complete(model, [{"role": "user", "content": _CAL_FILLER * 200}],
                          {"max_tokens": 1, "temperature": 0.0}, timeout=120)
    chars = len(_CAL_FILLER * 200)
    pt = out.get("prompt_tokens") or 1
    return chars / pt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Reasoning ladder (variable-tracking multi-hop probe)."
    )
    ap.add_argument("--model", required=True)
    ap.add_argument("--grid", default=",".join(str(g) for g in REASONING_GRID))
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--chain-len", type=int, default=4)
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--sampling-profile", required=True,
                    choices=["coding", "deployed", "official", "production"],
                    help="params profile (O36: explicit on every run; 'deployed' for all new axes)")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="Override profile max_tokens (default: use the profile's value)")
    ap.add_argument("--temp", type=float, default=None,
                    help="provenance-tracked temperature override (reasoning-axis temperature OFAT; "
                         "enters the persistence key, so rungs at different temps never pool)")
    ap.add_argument("--out-tag", default=None,
                    help="write reasoning.<tag>.json / reasoning.<tag>.partial.jsonl instead of the "
                         "untagged files (keeps the deployed-tune result intact)")
    ap.add_argument("--thinking-budget", type=int, default=None,
                    help="Override profile thinking_budget (default: use the profile's value)")
    ap.add_argument("--request-timeout", type=float, default=9600.0,
                    help="per-request HTTP timeout, DERIVED not SDK-default (O41): 81920-token "
                         "budget at ~12 tok/s at depth + ~20 min prefill at 156K, with headroom")
    ap.add_argument("--no-preload", action="store_true")
    ap.add_argument("--deep-from", type=int, default=None,
                    help="ctx (tokens) from which the deep-rung design applies")
    ap.add_argument("--deep-samples", type=int, default=None,
                    help="samples per rung at ctx >= --deep-from (default: --samples)")
    ap.add_argument("--early-stop-budget-hits", type=int, default=0,
                    help="deep rungs only: if the first N samples ALL hit the thinking budget, score "
                         "the rung from them and stop (0 = off)")
    ap.add_argument("--resume", action="store_true",
                    help="reuse rungs persisted in reasoning.partial.jsonl by an earlier attempt of "
                         "the SAME design (grid/profile/samples/chain/threshold/params key)")
    args = ap.parse_args(argv)

    grid = tuple(int(x) for x in args.grid.split(","))

    # M50: the process owning the router port must serve THIS driver's registry; checked before
    # anything is read, written or requested (the serving-state precheck below already reads).
    router = provenance.assert_served_config(client.BASE)
    # Everything after the entry check runs under the shared exit protocol (C106 re-verification,
    # quarantine + drift stamp on a refused run, original exception always preserved).
    guard = provenance.ExitGuard(router, client.BASE, label="reasoning")
    with guard:
        return _run(args, grid, router, guard)


def _journal_sidecar_doc(args, grid, router, serving, history, manifest_overrides):
    """What the journal's rows were produced under (C1): router block incl. the served file's
    sha256, the driver registry's sha256, the cheap manifest of the run (`fingerprint` is its
    config fingerprint) and the resolved serving controls."""
    from . import paths
    doc = {"router": router, "router_history": history,
           "registry_sha256": provenance._file_sha256(str(paths.registry_path())),
           "manifest": None, "fingerprint": None, "serving_controls": serving}
    try:
        lite = provenance.current_manifest_lite(
            args.model, args.sampling_profile, overrides=manifest_overrides,
            runtime={"probe": "reasoning", "grid": list(grid), "samples": args.samples,
                     "chain_len": args.chain_len})
        doc["manifest"], doc["fingerprint"] = lite, repr(provenance.config_fingerprint(lite))
    except provenance.ServedConfigError:
        raise
    except Exception as e:  # noqa: BLE001 — a sidecar without a manifest can never be resumed from
        doc["manifest_error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return doc


def _check_resume_sidecar(sidecar_path, current):
    """C1: a journal may only be resumed by a run whose served runtime is the one that wrote it.
    Returns the router history to carry forward; raises ServedConfigError otherwise."""
    if not os.path.exists(sidecar_path):
        raise provenance.ServedConfigError(
            f"C1 resume refused: {os.path.basename(sidecar_path)} is missing next to the journal; "
            f"its rows carry no router/registry/serving identity. Start a fresh --out-tag.")
    try:
        with open(sidecar_path) as f:
            old = json.load(f)
        old_sha = old["router"]["config_sha256"]
    except Exception as e:  # noqa: BLE001
        raise provenance.ServedConfigError(
            f"C1 resume refused: unreadable journal sidecar {sidecar_path}: {type(e).__name__}: {e}")
    if old_sha != current["router"].get("config_sha256"):
        raise provenance.ServedConfigError(
            f"C1 resume refused: the journal was produced under served config sha256 "
            f"{str(old_sha)[:12]}, this router serves {str(current['router'].get('config_sha256'))[:12]}.")
    if not provenance.is_compatible(old.get("manifest"), current["manifest"]):
        raise provenance.ServedConfigError(
            "C1 resume refused: the journal's manifest is not compatible with this run "
            "(sampling / KV / draft / serving controls / code differ).")
    hist = list(old.get("router_history") or [])
    prev = old["router"]
    if prev.get("pid") != current["router"].get("pid"):
        hist.append(prev)
    return hist


def _write_sidecar(path, doc):
    # Plain write: a torn sidecar is unreadable, which REFUSES a resume (safe direction).
    with open(path, "w") as f:
        json.dump(doc, f, indent=2, default=str)


def _run(args, grid, router, guard) -> int:
    # D1: a fresh (non---resume) run never appends to, or re-stamps, an existing journal: its
    # rows were produced under unknown controls. Refuse before anything is requested or created.
    _stem = "reasoning" if not args.out_tag else f"reasoning.{args.out_tag}"
    _journal = os.path.join(RESULTS, args.model, f"{_stem}.partial.jsonl")
    if not args.resume and (os.path.exists(_journal) or os.path.exists(_journal + ".provenance.json")):
        raise SystemExit(f"REFUSED: a journal already exists for {_stem!r} ({_journal}); a run without "
                         f"--resume would mix its rows with a different design/serving state. Use "
                         f"--resume or a fresh --out-tag.")
    serving_entry = provenance.assert_serving_state(args.model)   # M57: before the first model request
    try:    # provenance preflight: refuse now rather than fail to publish after the ladder
        provenance.preflight_gather(args.model, profile=args.sampling_profile, router=router,
                                    label="reasoning")
    except provenance.ProvenancePreflightError as e:
        print(f"[reasoning] REFUSED: {e}", file=sys.stderr, flush=True)
        return 3
    driver = MlxServeDriver()

    if not args.no_preload:
        driver.preload(args.model)

    # Find the model server subprocess (best-effort; reasoning doesn't gate on memory)
    model_pid = await_model_pid()
    if model_pid is None:
        print("[reasoning] WARNING: model server process not found; "
              "memory sampling disabled", flush=True)

    cpt = calibrate_cpt(driver, args.model)
    serving = provenance.assert_serving_state(args.model, expect=serving_entry)   # M57/M58: re-resolve once loaded

    # Build profile params; apply any CLI overrides
    params = params_for(args.model, profile=args.sampling_profile)
    if args.max_tokens is not None:
        params["max_tokens"] = args.max_tokens
    if args.thinking_budget is not None:
        params["thinking_budget"] = args.thinking_budget
    if args.temp is not None:
        params["temperature"] = args.temp

    print(f"[reasoning] {args.model} cpt={cpt:.2f} grid={grid} "
          f"threshold={args.threshold} samples={args.samples} "
          f"chain_len={args.chain_len}", flush=True)
    print(f"[reasoning] params: temp={params.get('temperature')} "
          f"top_p={params.get('top_p')} "
          f"thinking_budget={params.get('thinking_budget')} "
          f"max_tokens={params.get('max_tokens')}", flush=True)

    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    stem = "reasoning" if not args.out_tag else f"reasoning.{args.out_tag}"
    partial_path = os.path.join(out_dir, f"{stem}.partial.jsonl")
    base_design = {
        "grid": list(grid), "profile": args.sampling_profile, "samples": args.samples,
        "chain_len": args.chain_len, "threshold": args.threshold,
        "params": {k: params.get(k) for k in ("temperature", "top_p", "top_k", "min_p",
                                              "max_tokens", "thinking_budget")},
    }

    def key_for(ctx: int) -> str:
        # Rungs below --deep-from keep the base key, so shallow rungs persisted before a deep
        # redesign still resume; deep rungs carry the deep-design fields.
        d = dict(base_design)
        if args.deep_from is not None and ctx >= args.deep_from:
            d.update({"deep_from": args.deep_from, "deep_samples": args.deep_samples,
                      "early_stop_budget_hits": args.early_stop_budget_hits})
        return json.dumps(d, sort_keys=True)

    # F4 (review defect 10): overrides = CLI deltas only, not the full resolved params
    # dict -- a run with only --temp 0.7 must not report top_p/top_k/etc as overridden.
    manifest_overrides = {k: v for k, v in (
        ("max_tokens", args.max_tokens),
        ("thinking_budget", args.thinking_budget),
        ("temperature", args.temp),
    ) if v is not None}
    # C1: what this journal's rows are produced under travels beside it. A resume is accepted
    # only against a compatible sidecar (same served config sha256 + compatible manifest).
    sidecar_path = partial_path + ".provenance.json"
    history = []
    sidecar = _journal_sidecar_doc(args, grid, router, serving, history, manifest_overrides)
    if args.resume and os.path.exists(partial_path):
        history = _check_resume_sidecar(sidecar_path, sidecar)
        sidecar["router_history"] = history
    guard.track(partial_path)
    guard.track(sidecar_path)
    _write_sidecar(sidecar_path, sidecar)

    resume = None
    if args.resume and os.path.exists(partial_path):
        resume = {}
        with open(partial_path) as f:
            for line in f:
                row = json.loads(line)
                ctx = row["record"]["ctx"]
                if row.get("key") == key_for(ctx):
                    resume[ctx] = row["record"]
        print(f"[reasoning] resume: {sorted(resume)} rungs persisted for this design", flush=True)

    def persist(rec):
        with open(partial_path, "a") as f:
            f.write(json.dumps({"key": key_for(rec["ctx"]), "record": rec}) + "\n")
        print(f"[reasoning] rung done ctx={rec['ctx']} acc={rec['accuracy']} errors={rec['errors']}",
              flush=True)

    records = run_reasoning_ladder(
        driver, args.model, cpt,
        model_pid=model_pid,
        params=params,
        grid=grid,
        threshold=args.threshold,
        samples=args.samples,
        chain_len=args.chain_len,
        sampler_factory=MemorySampler,
        request_timeout=args.request_timeout,
        on_rung=persist,
        resume=resume,
        deep_from=args.deep_from,
        deep_samples=args.deep_samples,
        early_stop_budget_hits=args.early_stop_budget_hits,
    )

    for r in records:
        print(
            f"[reasoning] ctx={r['ctx']} acc={r['accuracy']} "
            f"samples={r['samples']} errors={r['errors']}",
            flush=True,
        )

    # Compute reasoning_effective_ctx: largest ctx with accuracy >= threshold
    passing = [r["ctx"] for r in records if r["accuracy"] >= args.threshold]
    reasoning_effective_ctx = max(passing) if passing else None

    result = {
        "model": args.model,
        "axis": "reasoning",
        "task": "vartrack",
        "threshold": args.threshold,
        "grid": list(grid),
        "params": base_design["params"],
        "records": records,
        "reasoning_effective_ctx": reasoning_effective_ctx,
    }

    final_path = os.path.join(out_dir, f"{stem}.json")
    stage_path = final_path + f".pending-{os.getpid()}"     # never overwrites an older result
    guard.track(stage_path, final_path)
    with open(stage_path, "w") as f:
        json.dump(result, f, indent=2)

    # Provenance beside the ladder (same pattern as run_retrieval.py T1.6 / run_capacity.py).
    # C116 (2026-10-06): no longer best-effort — a failed gather leaves the result staged, rc 3.
    man = None
    try:
        man = provenance.gather(args.model, profile=args.sampling_profile,
                                overrides=manifest_overrides,
                                runtime={"probe": "reasoning", "grid": list(grid),
                                         "samples": args.samples,
                                         "chain_len": args.chain_len},
                                router=router)
    except provenance.ServedConfigError:
        # M57: a late serving-state refusal is never swallowed; the guard sets the new result, this
        # run's journal and its sidecar aside under an explicit refused marker; an older manifest
        # is untouched.
        raise
    except Exception as e:  # noqa: BLE001
        # Codex review 10 B1: a result published WITHOUT its manifest would stand beside an OLDER
        # manifest under canonical names — the mixed pair the digest exists to prevent. The ladder
        # is not lost: it stays staged as `.pending-<pid>` for inspection; the run exits nonzero so
        # a queue never treats it as complete. Recovery: `--resume` (the journal has every rung);
        # a hand re-gather would stamp the wrong git/registry/router state.
        print(f"[reasoning] ERROR: provenance gather failed ({e}); result left staged at {stage_path}, "
              f"nothing published", flush=True)
        return 3
    # C106: publish only if the served runtime is still the one verified at entry (a drift
    # raises; the guard stamps `served_config_drift` and quarantines result, journal, sidecar).
    exit_blk = guard.verify()
    if man is not None:
        man["router_exit"] = exit_blk
        if history:
            man["router_history"] = history
    # Stage the manifest too (it names the sha256 of the result it describes), then publish the
    # pair back to back. Anything raised before publication leaves only .pending-<pid> files.
    manifest_final = os.path.join(out_dir, f"{stem}.manifest.json")
    manifest_stage = None
    if man is not None:
        man["result_file"] = os.path.basename(final_path)
        man["result_sha256"] = provenance.result_digest(stage_path)
        manifest_stage = manifest_final + f".pending-{os.getpid()}"
        with open(manifest_stage, "w") as f:
            json.dump(man, f, indent=2)
    provenance.publish_pair(stage_path, final_path, manifest_stage, manifest_final)

    print(f"[reasoning] REASONING_EFFECTIVE_CTX={reasoning_effective_ctx}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
