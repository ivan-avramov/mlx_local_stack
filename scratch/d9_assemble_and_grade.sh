#!/bin/bash
# D9 smoke: assemble the Haiku answer into a depth-tune row, grade via the real docker path.
set -e
cd ~/ws/mlx_local_stack/benchmark
export MLX_BENCH_RESULTS=$HOME/ws/mlx_local_stack_workdir/scratch/d9_smoke_results
../.venv-bench/bin/python - <<'PYEOF'
import json, os, pathlib
content = open(os.path.expanduser("~/ws/mlx_local_stack_workdir/scratch/d9_smoke_answer.txt")).read()
root = pathlib.Path(os.environ["MLX_BENCH_RESULTS"]) / "haiku-4-5-smoke"
root.mkdir(parents=True, exist_ok=True)
row = {"id": "HumanEval/0", "sample": 0, "schema_version": 2, "bench": "humanevalplus",
       "model": "haiku-4-5-smoke", "content": content, "reasoning": "",
       "prompt_tokens": 12218, "completion_tokens": 120, "thinking_budget": 81920,
       "finish_reason": "stop", "wall_s": 1.0}
(root / "humanevalplus.d12k.jsonl").write_text(json.dumps(row) + "\n")
print("row written under isolated root:", root)
PYEOF
../.venv-bench/bin/python run.py grade --models haiku-4-5-smoke --benches humanevalplus --tune d12k 2>&1 | grep -iE "haiku|acc|pass|error" | head -5
../.venv-bench/bin/python -c "
import json, os
d=json.load(open(os.path.expanduser('~/ws/mlx_local_stack_workdir/scratch/d9_smoke_results/haiku-4-5-smoke/humanevalplus.d12k.score.json')))
print('SMOKE SCORE:', {k: d.get(k) for k in ('n','acc','acc_strict','errors')})
"
