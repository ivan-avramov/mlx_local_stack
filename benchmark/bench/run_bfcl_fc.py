"""CLI: run BFCL v4 generation+evaluation against mlx-serve's OpenAI-compatible endpoint
using the vendored NATIVE-FC handler (bfcl_handler.py) — raw messages+tools posted to
/v1/chat/completions, server applies the served model's own chat template. This is a
SEPARATE path from `run_bfcl.py`/`bfcl_adapter.py` (subprocess `bfcl generate`/`evaluate`
CLI calls + benchmark/bfcl_shim/'s per-arch prompt-mode handlers over the legacy
/v1/completions text endpoint) — see bfcl_handler.py's module docstring for the template
confound that motivates keeping them distinct rather than editing the existing one in
place. Both remain available; an architect call on whether to retire the older path is
open (flagged, not resolved, in this session's report).

  cd benchmark && ../.venv-bench/bin/python -m bench.run_bfcl_fc \\
      --model Qwen3.6-27B-Opus-Distill-OptiQ-4bit \\
      --test-category simple_python,multiple --limit 5 --out /tmp/bfcl_fc_smoke

Writes <out>/result/, <out>/score/, and <out>/bfcl.json (same normalized-summary shape as
bfcl_adapter.parse_scores, reused here — this module only replaces the GENERATION
transport, not score parsing). Default --out is benchmark/bfcl_runs_fc — deliberately NOT
benchmark/results/: point --out at benchmark/results/<model>/ explicitly for a run whose
result the operator wants kept there.

NEVER run this against a router that may be serving another job — AGENTS.md: one resident
model per machine, always.
"""
import argparse
import json
import os
from types import SimpleNamespace

from . import bfcl_handler as H
from .bfcl_adapter import (
    AST_CATEGORIES,
    _write_run_ids_file,
    find_poisoned_rows,
    parse_scores,
)

_DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "bfcl_runs_fc")


def _write_result(out_root: str, result: dict) -> str:
    """Write <out_root>/bfcl.json. A failed run (acc is None) must never clobber a real
    prior score — same defect class documented in run_bfcl.py / test_run_bfcl_guard.py."""
    path = os.path.join(out_root, "bfcl.json")
    if result.get("acc") is None and os.path.exists(path):
        try:
            with open(path) as f:
                prev = json.load(f)
        except (json.JSONDecodeError, OSError):
            prev = {}
        if prev.get("acc") is not None:
            print(
                f"[bfcl_fc] REFUSING to overwrite {path}: this run produced no acc "
                f"({str(result.get('note'))[:70]}) — keeping acc={prev['acc']} "
                f"n={prev.get('n')}",
                flush=True,
            )
            return path
    os.makedirs(out_root, exist_ok=True)
    with open(path, "w") as f:
        json.dump(result, f, indent=2)
    return path


def _apply_poison_guard(result: dict, result_dir: str, model: str) -> dict:
    """O41 grader tripwire: refuse to summarize a tree containing inference-error rows.
    Those items never reached the model — grading them as wrong answers is how the
    2026-08-24 contaminations entered scored results. Nulls `acc`, names the ids (they
    are surgically re-runnable via run_ids), and leaves everything else intact so the
    per-category detail stays inspectable."""
    poisoned = find_poisoned_rows(result_dir, model)
    if not poisoned:
        return result
    n_bad = sum(len(v) for v in poisoned.values())
    return {
        **result,
        "acc": None,
        "poisoned_items": poisoned,
        "note": (
            f"REFUSED to grade: {n_bad} result row(s) are inference-error strings — the "
            f"model was never asked. Re-run these ids via run_ids, then re-score. "
            f"(O41; ids in poisoned_items)"
        ),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="mlx-serve registry name, e.g. Qwen3.6-27B-Opus-Distill-OptiQ-4bit")
    ap.add_argument("--test-category", default=",".join(AST_CATEGORIES), help="comma list of BFCL v4 categories")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--limit", type=int, default=None, help="per-category item cap (smoke runs)")
    ap.add_argument("--num-threads", type=int, default=1)
    ap.add_argument("--out", default=_DEFAULT_OUT,
                     help="run root (holds result/, score/, bfcl.json). NOT benchmark/results/ "
                          "by default — pass it explicitly to keep a real run's result there.")
    args = ap.parse_args(argv)

    out_root = os.path.abspath(args.out)
    os.makedirs(out_root, exist_ok=True)

    # MUST happen before bfcl_eval (or bfcl_eval.constants.eval_config specifically) is
    # imported ANYWHERE in this process — PROJECT_ROOT/RESULT_PATH/SCORE_PATH/
    # TEST_IDS_TO_GENERATE_PATH are module-level constants computed ONCE from
    # os.getenv("BFCL_PROJECT_ROOT", ...) at that first import (verified: a bare
    # `import bfcl_eval` with the env var unset creates result/score/.file_locks/ dirs
    # inside bfcl_eval's OWN site-packages install — already happened once in this repo's
    # .venv-bench). Reassigning the env var after that first import has no effect.
    os.environ["BFCL_PROJECT_ROOT"] = out_root

    categories = tuple(c.strip() for c in args.test_category.split(",") if c.strip())

    if not H.bfcl_eval_available():
        result = {"model": args.model, "axis": "tool_calling", "categories": list(categories),
                   "acc": None, "n": 0, "skipped": True,
                   "note": "bfcl-eval not importable; pip install bfcl-eval where this runs"}
        print(f"[bfcl_fc] SKIPPED: {result['note']}", flush=True)
        _write_result(out_root, result)
        return 0

    H.register_model(args.model, host=args.host, port=args.port)

    result_dir = os.path.join(out_root, "result")
    score_dir = os.path.join(out_root, "score")

    if args.limit is not None:
        _write_run_ids_file(out_root, categories, args.limit)

    gen_args = SimpleNamespace(
        model=[args.model],
        test_category=list(categories),
        temperature=0.001,  # ignored: MlxServeFCHandler overrides from the deployed profile
        include_input_log=False,
        exclude_state_log=False,
        num_gpus=1,
        num_threads=args.num_threads,
        gpu_memory_utilization=0.9,
        backend="vllm",          # irrelevant: never reached — our handler isn't an OSSHandler
        skip_server_setup=True,  # irrelevant, same reason
        local_model_path=None,
        result_dir=result_dir,
        allow_overwrite=True,
        run_ids=args.limit is not None,
        enable_lora=False,
        max_lora_rank=None,
        lora_modules=None,
    )

    try:
        from bfcl_eval._llm_response_generation import main as generation_main
        from bfcl_eval.eval_checker.eval_runner import main as evaluation_main

        generation_main(gen_args)
        evaluation_main([args.model], list(categories), result_dir, score_dir,
                         partial_eval=args.limit is not None)
    except SystemExit:
        # O41.1: the handler escalates transport failures as SystemExit (BaseException)
        # precisely so no `except Exception` — bfcl_eval's or THIS one — can convert
        # them into gradeable output. Name the situation for the operator and re-raise;
        # deliberately NO bfcl.json write: a transport failure is not a result.
        print(
            f"[bfcl_fc] ABORTED by transport-failure escalation for {args.model} — see "
            f"the TRANSPORT FAILURE line above. Nothing was graded; root-cause the "
            f"harness/runner/server, then re-run the affected categories.",
            flush=True,
        )
        raise
    except Exception as e:  # noqa: BLE001 — never crash the batch; degrade with a note
        note = f"bfcl_fc run raised: {type(e).__name__}: {str(e)[:200]}"
        print(f"[bfcl_fc] {note}", flush=True)
        _write_result(out_root, {"model": args.model, "axis": "tool_calling",
                                  "categories": list(categories), "acc": None, "n": 0,
                                  "skipped": False, "note": note})
        return 1

    result = {"model": args.model, "axis": "tool_calling", "categories": list(categories),
              **parse_scores(score_dir, args.model, categories), "skipped": False}
    result = _apply_poison_guard(result, result_dir, args.model)
    print(f"[bfcl_fc] {args.model} acc={result.get('acc')} n={result.get('n')} "
          f"per_category={result.get('per_category')}", flush=True)
    _write_result(out_root, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
