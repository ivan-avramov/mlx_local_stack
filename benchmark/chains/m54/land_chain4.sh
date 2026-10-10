#!/bin/bash
# FROZEN copy (P229, 2026-10-10) of $STACK_WORKDIR/m54/land_chain4.sh, the driver behind the agentbench_os.v1.chain* (M54) rows.
# Only change: absolute home paths -> $STACK_WORKDIR / $STACK_REPO. See benchmark/chains/README.md.
# Land chain 4 (clean capture): arms 1-2 from arms_aac939b_redo, arms 3-5 from arms_aac939b. Run AFTER the redo prints ALL ARMS COMPLETE.
set -e
M=$STACK_WORKDIR/m54; R=$STACK_REPO; WT=$M/wt-aac939b/benchmark; PY=$R/.venv-bench/bin/python
src(){ case "$1" in Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed|Qwen3.8-27B-mlx-uniform-4bit) echo arms_aac939b_redo;; *) echo arms_aac939b;; esac; }
ORDER="Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed Qwen3.8-27B-mlx-uniform-4bit Ornith-1.0-35B-mlx-uniform-4bit Qwen3.6-27B-Opus-Distill-OptiQ-4bit NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"
/usr/bin/grep -q "ALL ARMS COMPLETE" $M/arms_aac939b_redo/RUNLOG.md || { echo "redo not complete"; exit 1; }
args=(); for m in $ORDER; do f=$M/$(src $m)/$m/agentbench_os.v1.jsonl; [ "$(wc -l < $f | tr -d " ")" = "142" ] || { echo "$m has $(wc -l < $f) rows"; exit 1; }; args+=(--rows "$m=$f" --manifest "$m=${f%.jsonl}.manifest.json"); done
cd $WT && PYTHONPATH=. $PY -m bench.agentbench_compare "${args[@]}" --out $M/compare_chain4.md
cp $M/compare_chain4.md $R/benchmark/results/agentbench_os_compare_chain4.md; [ -f $M/compare_chain4.json ] && cp $M/compare_chain4.json $R/benchmark/results/agentbench_os_compare_chain4.json
for m in $ORDER; do d=$M/$(src $m)/$m; for ext in jsonl manifest.json summary.json; do cp $d/agentbench_os.v1.$ext $R/benchmark/results/$m/agentbench_os.v1.chain4.$ext; done; done
cd $R && for f in benchmark/results/*/agentbench_os.v1.chain4.* benchmark/results/agentbench_os_compare_chain4.*; do
  sed -i '' -e "s#${STACK_WORKDIR}#\$STACK_WORKDIR#g" -e "s#${STACK_REPO}#\$STACK_REPO#g" -e "s#${HOME}#\$HOME#g" "$f"; done
/usr/bin/grep -lE "/Users/|$USER" benchmark/results/*/agentbench_os.v1.chain4.* benchmark/results/agentbench_os_compare_chain4.* && { echo "PII REMAINS"; exit 1; } || echo "scrub clean"
echo LANDED; ls benchmark/results/*/agentbench_os.v1.chain4.jsonl | wc -l
