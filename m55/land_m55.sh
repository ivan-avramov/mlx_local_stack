#!/bin/bash
# Land M55: rows+manifests -> benchmark/results/<model>/opencode_<lang>.m55.s{1,2}.{jsonl,manifest.json}; report -> benchmark/results/m55_polyglot_gap_report.md. Scrubs placeholders.
set -e
M=$STACK_WORKDIR/m55; R=$STACK_REPO
/usr/bin/grep -q "ALL LEGS DONE" $M/RUNLOG.md || { echo "chain not complete"; exit 1; }
for s in s1 s2; do for m in Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed Qwen3.8-27B-mlx-uniform-4bit Ornith-1.0-35B-mlx-uniform-4bit; do for l in rust java javascript; do
  f=$M/$s/$m.opencode_$l.jsonl; [ "$(wc -l < $f | tr -d ' ')" = "22" ] || { echo "$f not 22 rows"; exit 1; }
  cp $f $R/benchmark/results/$m/opencode_$l.m55.$s.jsonl; cp ${f%.jsonl}.manifest.json $R/benchmark/results/$m/opencode_$l.m55.$s.manifest.json
done; done; done
cd $R && .venv-bench/bin/python $M/m55_report.py benchmark/results/m55_polyglot_gap_report.md
for f in benchmark/results/*/opencode_*.m55.* benchmark/results/m55_polyglot_gap_report.md; do
  sed -i '' -e 's#$STACK_WORKDIR#$STACK_WORKDIR#g' -e 's#$STACK_REPO#$STACK_REPO#g' -e 's#$HOME#$HOME#g' "$f"; done
/usr/bin/grep -lE "/Users/|<user>" benchmark/results/*/opencode_*.m55.* benchmark/results/m55_polyglot_gap_report.md && { echo "PII REMAINS"; exit 1; } || echo "scrub clean"
echo LANDED; ls benchmark/results/*/opencode_*.m55.*.jsonl | wc -l
