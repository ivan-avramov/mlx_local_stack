"""CLI: run the mixed-family code-quality judge panel over a model's execution-PASSING
coding outputs.

  # ANTHROPIC_API_KEY set + codex on PATH; records.jsonl = {task, output, reference?} per line:
  cd benchmark && uv run python -m bench.run_judge --model Qwen3.6-27B-UD-MLX-6bit --records passing.jsonl

Writes benchmark/results/<model>/judge.json."""
import argparse
import json
import os

from .judge import judge_one, aggregate

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")


def _read_records(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mixed-family code-quality judge panel.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--records", required=True, help="JSONL of {task, output, reference?}")
    args = ap.parse_args(argv)

    records_in = _read_records(args.records)
    judged = [judge_one(r["task"], r["output"], r.get("reference")) for r in records_in]
    agg = aggregate(judged)
    result = {"model": args.model, "axis": "code_quality", "n_records": agg["n_records"],
              "overall": agg["overall"], "per_axis": agg["per_axis"],
              "low_confidence": agg["low_confidence"], "records": judged}

    print(f"[judge] {args.model} overall={agg['overall']} per_axis={agg['per_axis']} "
          f"n={agg['n_records']} low_confidence={agg['low_confidence']}", flush=True)
    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "judge.json"), "w") as f:
        json.dump(result, f, indent=2)
    print(f"[judge] wrote {os.path.join(out_dir, 'judge.json')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
