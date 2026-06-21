"""CLI: run the SWE-bench-Verified-40 adapter for one model.

  # mlx-serve serving <model> at :8000; swebench installed + docker running:
  cd benchmark && uv run python -m bench.run_swebench --model Qwen3.6-27B-UD-MLX-6bit --n 40

Writes benchmark/results/<model>/swebench.json. NOTE: a real run needs the swebench harness +
docker + per-instance repo checkouts (a repo_provider) — that is wired at execution time."""
import argparse
import json
import os

from .driver import MlxServeDriver
from .model_params import params_for
from .swebench_adapter import run_swebench

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SWE-bench-Verified-40 agentic adapter.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dataset", default="princeton-nlp/SWE-bench_Verified")
    ap.add_argument("--run-id", default="bake")
    ap.add_argument("--max-turns", type=int, default=12)
    ap.add_argument("--no-preload", action="store_true")
    args = ap.parse_args(argv)

    driver = MlxServeDriver()
    if not args.no_preload:
        driver.preload(args.model)
    params = params_for(args.model)

    result = run_swebench(model=args.model, n=args.n, seed=args.seed, dataset=args.dataset,
                          run_id=args.run_id, driver=driver, params=params)
    if result.get("skipped"):
        print(f"[swebench] SKIPPED: {result.get('note')}", flush=True)
    elif result.get("acc") is None:
        print(f"[swebench] NO SCORE: {result.get('note')}", flush=True)
    else:
        print(f"[swebench] {args.model} resolve_rate={result.get('acc')} "
              f"({result.get('resolved')}/{result.get('total')})", flush=True)

    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "swebench.json"), "w") as f:
        json.dump(result, f, indent=2)
    print(f"[swebench] wrote {os.path.join(out_dir, 'swebench.json')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
