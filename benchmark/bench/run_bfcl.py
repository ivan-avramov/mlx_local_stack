"""CLI: run the BFCL tool-calling adapter against the live mlx-serve endpoint.

  # with bfcl-eval installed and mlx-serve serving <model> at :8000:
  cd benchmark && uv run python -m bench.run_bfcl --model Qwen3.6-27B-UD-MLX-6bit

Writes benchmark/results/<model>/bfcl.json."""
import argparse
import json
import os

from .bfcl_adapter import run_bfcl, AST_CATEGORIES

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")
_DEFAULT_RUNROOT = os.path.join(os.path.dirname(__file__), "..", "bfcl_runs")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="BFCL tool-calling adapter (AST single-turn).")
    ap.add_argument("--model", required=True)
    ap.add_argument("--categories", default=",".join(AST_CATEGORIES),
                    help="comma list of BFCL AST categories")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--limit", type=int, default=None, help="per-category item cap (smoke runs)")
    ap.add_argument("--result-dir", default=os.path.join(_DEFAULT_RUNROOT, "result"))
    ap.add_argument("--score-dir", default=os.path.join(_DEFAULT_RUNROOT, "score"))
    args = ap.parse_args(argv)
    categories = tuple(c.strip() for c in args.categories.split(",") if c.strip())

    result = run_bfcl(model=args.model, categories=categories, port=args.port,
                      result_dir=args.result_dir, score_dir=args.score_dir, limit=args.limit)

    if result.get("skipped"):
        print(f"[bfcl] SKIPPED: {result.get('note')}", flush=True)
    else:
        print(f"[bfcl] {args.model} acc={result.get('acc')} n={result.get('n')} "
              f"per_category={result.get('per_category')}", flush=True)

    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "bfcl.json")

    # ⚠️ A FAILED run must not null out a real score. This is a DOCUMENTED loss:
    # campaign-queue.md records "each failed run_bfcl clobbers bfcl.json to null — re-parse raw or
    # ignore", which is why Qwen3.6-27B-Opus-Distill-OptiQ-4bit's file reads acc=null with an
    # rc=1 traceback even though its real BFCL result (n=200, acc 0.94) had already been measured.
    # Same defect class as _write_pair_score overwriting a graded evalplus score with acc=None.
    if result.get("acc") is None and os.path.exists(path):
        try:
            with open(path) as f:
                prev = json.load(f)
        except (json.JSONDecodeError, OSError):
            prev = {}
        if prev.get("acc") is not None:
            print(f"[bfcl] REFUSING to overwrite {path}: this run produced no acc "
                  f"({str(result.get('note'))[:70]}) — keeping acc={prev['acc']} "
                  f"n={prev.get('n')}", flush=True)
            return 0

    with open(path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"[bfcl] wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
