#!/bin/zsh
# Commit every harvested-but-uncommitted S′ Wave-1 leg (dossier + rows), one data(bench) commit per leg, hooks on.
set -u
cd $STACK_REPO || exit 2
E=benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed; W=benchmark/results/p426/wave1.s2
L="$STACK_WORKDIR/p426/wave1.s2/sequence.log"
for leg in $(grep -oE "HARVESTED [a-z0-9]+-p426s2-[a-z0-9-]+" "$L" | awk '{print $2}' | awk '!s[$0]++'); do
  [ -d "$W/$leg" ] || continue
  [ -n "$(git status --porcelain -- "$W/$leg")" ] || continue
  axis=${leg%%-*}; tune=${leg#*-}; pre=$axis; [ "$axis" = vision ] && pre=vision_gate
  v=$(grep -E " END $leg: " "$L" | tail -1 | grep -oE "verdict [A-Z_]+" | cut -d' ' -f2)
  rows=(${(f)"$(ls $E/$pre.$tune.* 2>/dev/null)"})
  git add "$W/$leg" ${rows[@]} && git commit -q -m "data(bench): P426 Wave 1 on S′ — $leg $v (harvested dossier + rows)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" && echo "$leg $v committed" || echo "$leg COMMIT FAILED"
done
