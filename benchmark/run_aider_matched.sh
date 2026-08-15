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
# Each invocation is bounded by a WATCHDOG: upstream sets sendchat.RETRY_TIMEOUT to 24 HOURS
# ("Don't give up when benchmarking"), so one bad request can otherwise consume a whole day.
# The bound is implemented here rather than with `timeout` because these are macOS boxes: `timeout`
# is GNU coreutils and is NOT present (nor `gtimeout`, nor coreutils). An unguarded `timeout ...`
# fails with "command not found", which under `if ! cmd` looks exactly like a benchmark failure —
# it silently "completed" all 5 languages in under a second on the first attempt. The watchdog
# kills the docker container BY NAME, because run_aider_docker.sh `exec`s `docker run`, so killing
# only the shell would leave the container running.
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

# PREFLIGHT. Every precondition is checked BEFORE any model time is spent, because a missing one
# reads exactly like a fast benchmark failure: the first attempt at this run "completed" all five
# languages in under one second (missing `timeout`) and would have been reported as 0 solved.
AIDER_REPO_CHECK="${AIDER_REPO:-$HOME/aider}"
POLYGLOT_CHECK="${POLYGLOT_DIR:-$HOME/polyglot-benchmark}"
SETTINGS_CHECK="${AIDER_SETTINGS:-$PWD/aider_config/aider.model.settings.yml}"
preflight_fail() { echo "PREFLIGHT FAILED: $1" >&2; exit 1; }
docker info >/dev/null 2>&1 || preflight_fail "docker is not available"
docker image inspect aider-benchmark >/dev/null 2>&1 \
  || preflight_fail "image aider-benchmark missing (build it: cd \$AIDER_REPO && bash benchmark/docker_build.sh)"
[ -d "$AIDER_REPO_CHECK/benchmark" ] || preflight_fail "no aider clone at $AIDER_REPO_CHECK (set AIDER_REPO)"
[ -d "$POLYGLOT_CHECK" ] || preflight_fail "no polyglot exercises at $POLYGLOT_CHECK (set POLYGLOT_DIR)"
[ -f "$SETTINGS_CHECK" ] || preflight_fail "settings file not found: $SETTINGS_CHECK"
# The settings file is what carries our tuned sampling. Without an entry for THIS model, aider
# silently falls back to litellm defaults and the row measures a config we never chose.
grep -q -- "$MODEL" "$SETTINGS_CHECK" \
  || preflight_fail "no entry for $MODEL in $SETTINGS_CHECK — it would run at aider's default sampling"
grep -q -- "$MODEL" "$AIDER_REPO_CHECK/aider/resources/model-metadata.json" 2>/dev/null \
  || preflight_fail "no model-metadata entry for $MODEL — aider would not know the context window"

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

# Mirrors run_aider_docker.sh's CNAME so the watchdog can kill the right container.
_container_name() { printf 'aider-%s' "$(printf '%s' "$1" | tr '/:.' '___')"; }

run_one_language() {  # lang keywords num_tests -> exit status of the run (124 if watchdog fired)
  local lang="$1" kw="$2" n="$3" child waited=0 rc=0
  # num-tests == n: keywords already fixed the set, so the shuffle only reorders it.
  AIDER_LANGUAGES="$lang" AIDER_KEYWORDS="$kw" \
    "$HERE/run_aider_docker.sh" "$MODEL" "$n" diff "$PREFIX-$lang" &
  child=$!
  while kill -0 "$child" 2>/dev/null; do
    if [ "$waited" -ge "$PER_LANG_TIMEOUT" ]; then
      echo "!!! $lang exceeded ${PER_LANG_TIMEOUT}s — killing container then child"
      docker kill "$(_container_name "$MODEL")" >/dev/null 2>&1 || true
      kill "$child" 2>/dev/null || true
      wait "$child" 2>/dev/null || true
      return 124
    fi
    sleep 10; waited=$((waited + 10))
  done
  wait "$child" && rc=0 || rc=$?
  return "$rc"
}

while IFS= read -r row; do
  LANG_NAME="${row%%|*}"; KEYWORDS="${row#*|}"
  N=$(awk -F, '{print NF}' <<<"$KEYWORDS")
  echo "=== [$(date +%H:%M:%S)] $LANG_NAME ($N exercises) ==="
  # `if ! cmd` would make $? always 0 inside the branch, reporting every failure as "rc=0".
  set +e; run_one_language "$LANG_NAME" "$KEYWORDS" "$N"; RC=$?; set -e
  if [ "$RC" -ne 0 ]; then
    echo "!!! [$(date +%H:%M:%S)] $LANG_NAME FAILED (rc=$RC) — continuing to the next language"
    # Do NOT abort: a per-language failure must not discard the languages already completed,
    # and the partial results stay on disk for recovery (the m1g java recovery worked this way).
  else
    echo "=== [$(date +%H:%M:%S)] $LANG_NAME done ==="
  fi
done <<<"$PLAN"
echo "=== [$(date +%H:%M:%S)] all languages attempted ==="
