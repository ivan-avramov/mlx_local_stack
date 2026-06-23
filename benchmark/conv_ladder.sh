#!/usr/bin/env bash
# Temp-ladder thinking-convergence probe (2026-06-22). Runs run_convergence at each temp,
# dropping 0.1 per "budget hit", until a rung has ZERO budget hits (natural convergence) or
# the temp floor is exhausted (genuine non-converger -> escalate to --set levers).
#
# Convergence signal is the FIXED harness: converged = finish=="stop" AND completion_tokens
# < thinking_budget. Probe budget is passed via --set thinking_budget=<BUDGET> (uniform 16384
# across models so the comparison is apples-to-apples; for the distill this is a reduction
# from its production 49152 — a stricter, faster bar that a true converger still clears).
#
# Usage (run FROM the benchmark dir):
#   conv_ladder.sh <venv_python> <model> <probe_budget> <agg_samples> <temp1> <temp2> ...
set -u
PY="$1"; MODEL="$2"; BUDGET="$3"; SAMPLES="$4"; shift 4
TEMPS=("$@")
echo "[ladder] model=$MODEL probe_budget=$BUDGET agg_samples=$SAMPLES temps=${TEMPS[*]}"
for T in "${TEMPS[@]}"; do
  echo "[ladder] ===== temp=$T ====="
  OUT=$(PYTHONPATH=. "$PY" -m bench.run_convergence --model "$MODEL" \
        --samples "$SAMPLES" --coding-samples 1 \
        --temperature "$T" --set thinking_budget="$BUDGET" 2>&1)
  echo "$OUT"
  SUMM=$(echo "$OUT" | grep -E "^\[conv\] SUMMARY" | tail -1 | sed 's/^\[conv\] SUMMARY //')
  read CR BH <<EOF
$(echo "$SUMM" | "$PY" -c "import sys,json; a=json.load(sys.stdin).get('aggregation',{}); print(a.get('converged_rate',0.0), a.get('budget_hit_rate',1.0))" 2>/dev/null || echo "0.0 1.0")
EOF
  echo "[ladder] >>> temp=$T converged_rate=$CR budget_hit_rate=$BH"
  if [ "$BH" = "0.0" ]; then
    echo "[ladder] CONVERGED at temp=$T (zero budget hits, converged_rate=$CR)."
    echo "[ladder] DONE model=$MODEL converged_temp=$T converged_rate=$CR"
    exit 0
  fi
done
echo "[ladder] EXHAUSTED temp floor without zero-budget-hit convergence -> NON-CONVERGER at these params (escalate to min_p/presence_penalty/rep_penalty)."
echo "[ladder] DONE model=$MODEL converged_temp=NONE"
exit 0
