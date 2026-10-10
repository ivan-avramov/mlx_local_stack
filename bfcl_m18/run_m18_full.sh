#!/bin/zsh
# M18 first recorded BFCL run — three pick-relevant models, full D1 AST categories.
# Sequential; the router swaps the resident model on demand. Sized from the 5-item
# pilot (mean ~8s/item incl. thinking): ~2.2h/model.
set -e
cd "$HOME/ws/mlx_local_stack/benchmark"
CATS="simple_python,multiple,parallel,parallel_multiple"
for MODEL in Qwen3.6-27B-Opus-Distill-OptiQ-4bit Ornith-1.0-35B-mlx-uniform-4bit NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit; do
  echo "=== M18 START $MODEL $(date +%H:%M:%S) ==="
  set +e
  PYTHONPATH=. ../.venv-bench/bin/python -m bench.run_bfcl_fc \
    --model "$MODEL" --test-category "$CATS" \
    --out "results/$MODEL/bfcl_fc" \
    > "$HOME/ws/mlx_local_stack_workdir/bfcl_m18/full_$MODEL.log" 2>&1
  RC=$?
  set -e
  echo "=== M18 DONE $MODEL rc=$RC $(date +%H:%M:%S) ==="
  grep -E "^\[bfcl_fc\]" "$HOME/ws/mlx_local_stack_workdir/bfcl_m18/full_$MODEL.log" | tail -1
done
echo "=== M18 ALL DONE $(date +%H:%M:%S) ==="
