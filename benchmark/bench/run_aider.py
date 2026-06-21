"""CLI: run the Aider polyglot benchmark against the live mlx-serve endpoint.

  # mlx-serve serving <model> at :8000; aider + polyglot-benchmark cloned:
  cd benchmark && uv run python -m bench.run_aider --model Qwen3.6-27B-UD-MLX-6bit \
      --aider-repo ~/aider --exercises-dir ~/polyglot-benchmark

Writes benchmark/results/<model>/aider.json."""
import argparse
import json
import os

from .aider_adapter import run_aider

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Aider polyglot agentic-edit benchmark.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--exercises-dir", required=True)
    ap.add_argument("--aider-repo", required=True)
    ap.add_argument("--edit-format", default="whole")
    ap.add_argument("--num-tests", type=int, default=None)
    ap.add_argument("--endpoint", default="http://localhost:8000/v1")
    ap.add_argument("--run-name", default="bake")
    args = ap.parse_args(argv)

    result = run_aider(model=args.model, exercises_dir=args.exercises_dir,
                       aider_repo=args.aider_repo, edit_format=args.edit_format,
                       num_tests=args.num_tests, endpoint=args.endpoint, run_name=args.run_name)
    if result.get("skipped"):
        print(f"[aider] SKIPPED: {result.get('note')}", flush=True)
    elif result.get("acc") is None:
        print(f"[aider] NO SCORE: {result.get('note')}", flush=True)
    else:
        print(f"[aider] {args.model} acc={result.get('acc')} "
              f"pass_rate_1={result.get('pass_rate_1')} pass_rate_2={result.get('pass_rate_2')}", flush=True)

    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "aider.json"), "w") as f:
        json.dump(result, f, indent=2)
    print(f"[aider] wrote {os.path.join(out_dir, 'aider.json')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
