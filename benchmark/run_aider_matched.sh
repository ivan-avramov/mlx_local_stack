#!/usr/bin/env bash
# Run the aider polyglot benchmark on MODEL over the EXACT item set of a reference run.
#
# WHY THIS EXISTS. `run_aider_docker.sh` passes `--num-tests N`, which upstream implements as
#   test_dnames = sorted(...); random.shuffle(test_dnames); test_dnames[:num_tests]
# with no seed. So two invocations select DIFFERENT exercises, and a new arm can never be paired
# against an existing one — the campaign already has historical rows ("Ornith n=34 vs distill n=16")
# that were two unrelated random subsets. The only upstream lever that pins an item set is
# `--keywords`, which filters BEFORE the shuffle.
#
# The item set is DERIVED FROM THE REFERENCE ROWS, never hand-copied: the polyglot exercises differ
# per language (the campaign's 110-item set is 5 languages x a random 22, with only 3 exercises
# common to all five), so a hand-typed list is both long and silently wrong if one name drifts.
#
# It runs ONE INVOCATION PER LANGUAGE because that is how the reference run (m1f) was produced, and
# because `--keywords` is matched against exercise names, not language/name pairs: passing all 57
# distinct names at once would select every (language, name) pair that exists, a superset of the
# reference set.
#
# Each invocation is wrapped in `timeout`: upstream sets sendchat.RETRY_TIMEOUT to 24 HOURS
# ("Don't give up when benchmarking"), so one bad request can otherwise consume a whole day.
#
# Usage: run_aider_matched.sh <served-model> <reference-results.jsonl> [run-prefix] [per-lang-timeout]
#   run_aider_matched.sh NVIDIA-... benchmark/results/Ornith-.../aider.jsonl m1h-nemotron 14400
set -euo pipefail
MODEL="${1:?usage: run_aider_matched.sh <served-model> <reference-results.jsonl> [run-prefix] [timeout]}"
REF="${2:?need a reference aider.jsonl whose item set defines the matched set}"
PREFIX="${3:-matched-$MODEL}"
PER_LANG_TIMEOUT="${4:-14400}"
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-$HERE/../.venv-bench/bin/python}"

[ -f "$REF" ] || { echo "reference rows not found: $REF" >&2; exit 1; }
[ -x "$PY" ] || { echo "python not found: $PY" >&2; exit 1; }

# lang|comma-separated exercise names, derived from the reference rows' `id` fields ("lang/exercise")
PLAN="$("$PY" - "$REF" <<'PY'
import json, sys, collections
by = collections.defaultdict(set)
with open(sys.argv[1]) as f:
    for line in f:
        try: r = json.loads(line)
        except json.JSONDecodeError: continue
        rid = r.get("id")
        if not rid or "/" not in rid: continue
        lang, ex = rid.split("/", 1)
        by[lang].add(ex)
for lang in sorted(by):
    print(f"{lang}|{','.join(sorted(by[lang]))}")
PY
)"
[ -n "$PLAN" ] || { echo "derived an EMPTY item set from $REF — refusing to run" >&2; exit 1; }

echo "== matched aider run: model=$MODEL prefix=$PREFIX ref=$REF"
# zsh does NOT word-split unquoted vars, so iterate with read, never `for x in $PLAN`.
TOTAL=0
while IFS= read -r row; do
  LANG_NAME="${row%%|*}"; KEYWORDS="${row#*|}"
  N=$(awk -F, '{print NF}' <<<"$KEYWORDS")
  TOTAL=$((TOTAL + N))
  echo "== $LANG_NAME: $N exercises"
done <<<"$PLAN"
echo "== total matched items: $TOTAL"

while IFS= read -r row; do
  LANG_NAME="${row%%|*}"; KEYWORDS="${row#*|}"
  N=$(awk -F, '{print NF}' <<<"$KEYWORDS")
  echo "=== [$(date +%H:%M:%S)] $LANG_NAME ($N exercises) ==="
  # num-tests == N: keywords already fixed the set, so the shuffle only reorders it.
  if ! AIDER_LANGUAGES="$LANG_NAME" AIDER_KEYWORDS="$KEYWORDS" \
       timeout "$PER_LANG_TIMEOUT" "$HERE/run_aider_docker.sh" \
         "$MODEL" "$N" diff "$PREFIX-$LANG_NAME"; then
    rc=$?
    echo "!!! $LANG_NAME FAILED/TIMED OUT (rc=$rc) — continuing to the next language"
    # Do NOT abort: a per-language failure must not discard the languages already completed,
    # and the partial results stay on disk for recovery (the m1g java recovery worked this way).
  fi
done <<<"$PLAN"
echo "=== [$(date +%H:%M:%S)] all languages attempted ==="
