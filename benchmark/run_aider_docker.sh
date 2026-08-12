#!/usr/bin/env bash
# Dockerized Aider polyglot agentic-edit benchmark against the local mlx-serve endpoint.
#
# WHY DOCKER: aider's benchmark.py is designed to run inside its container — it hardcodes
# /aider/benchmark/*.sh test scripts for cpp/js, needs all 6 language toolchains, sets
# AIDER_DOCKER, and lays the repo out at /aider. Running on the host hits all of those; the
# container (built by the aider clone's benchmark/docker_build.sh) handles them wholesale.
#
# ONE-TIME SETUP (per box):
#   1. Clone Aider-AI/aider + the polyglot-benchmark exercises (defaults: ~/aider, ~/polyglot-benchmark).
#   2. Build the image from the aider clone:  cd ~/aider && bash benchmark/docker_build.sh   (-> aider-benchmark:latest)
#   3. Add a model-metadata entry for the SERVED name to ~/aider/aider/resources/model-metadata.json
#      (so aider knows the context window and doesn't truncate), e.g.:
#        "openai/<served-model>": {"max_input_tokens":98304,"max_output_tokens":32768,"max_tokens":32768,
#                                  "input_cost_per_token":0,"output_cost_per_token":0,"litellm_provider":"openai","mode":"chat"}
#      (that file is inside the aider clone; the run mounts it into the container.)
#   4. mlx-serve must serve <served-model> on 0.0.0.0:8000 (container reaches it via host.docker.internal).
#
# Usage: run_aider_docker.sh <served-model> [num_tests] [edit_format] [run_name]
#   run_aider_docker.sh gemma-4-31b-it-6bit 25 diff
# Env overrides: AIDER_REPO, POLYGLOT_DIR, AIDER_ENDPOINT, AIDER_SETTINGS,
#                AIDER_LANGUAGES (comma list), AIDER_KEYWORDS (comma list).
# NB ~15 min/case for a dense 31B (thinking + 2 tries) -> the full 225-set is infeasible; use a subset.
#
# ⚠️ THREE UPSTREAM BEHAVIOURS THAT INVALIDATE A NAIVE RUN (read benchmark/benchmark.py, verified
#    at clone 5dc9490 / v0.86.3.dev, and identical in v0.86.2):
#
# 1. `--num-tests N` IS AN UNSEEDED RANDOM SAMPLE, NOT A PREFIX:
#        test_dnames = sorted(...); random.shuffle(test_dnames); test_dnames[:num_tests]
#    There is no seed, so two invocations select DIFFERENT exercises. `--num-tests` alone can
#    therefore NEVER produce the matched item sets a paired comparison requires — and the campaign's
#    historical "Ornith n=34 vs distill n=16" rows were two unrelated random subsets of the 225, not
#    nested prefixes. To pin an item set, pass AIDER_KEYWORDS with the exact exercise names: the
#    keyword filter runs BEFORE the shuffle, so the shuffle only reorders a set you already fixed.
#
# 2. `sendchat.RETRY_TIMEOUT` is set to 24 HOURS ("Don't give up when benchmarking"), so ONE bad
#    request can silently consume a whole day. Bound every invocation externally (`timeout`).
#
# 3. Aider feeds the test harness's stderr back into the next prompt. A g++ template-error cascade
#    on a cpp exercise produced a 165k-token prompt on the first case we tried — past the model's
#    input budget. cpp cases measure the C++ toolchain as much as the model; treat them separately.
set -euo pipefail
MODEL="${1:?usage: run_aider_docker.sh <served-model> [num_tests] [edit_format] [run_name]}"
N="${2:-25}"; EF="${3:-diff}"; RUN="${4:-${MODEL}-run}"
AIDER_REPO="${AIDER_REPO:-$HOME/aider}"
POLYGLOT="${POLYGLOT_DIR:-$HOME/polyglot-benchmark}"
ENDPOINT="${AIDER_ENDPOINT:-http://host.docker.internal:8000/v1}"
SETTINGS="${AIDER_SETTINGS:-$PWD/aider_config/aider.model.settings.yml}"
CNAME="aider-$(printf '%s' "$MODEL" | tr '/:.' '___')"
EXTRA=()
[ -n "${AIDER_LANGUAGES:-}" ] && EXTRA+=(--languages "$AIDER_LANGUAGES")
[ -n "${AIDER_KEYWORDS:-}" ] && EXTRA+=(--keywords "$AIDER_KEYWORDS")

mkdir -p "$AIDER_REPO/benchmark/tmp.benchmarks"
exec docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  -v "$AIDER_REPO:/aider" \
  -v "$AIDER_REPO/benchmark/tmp.benchmarks:/benchmarks" \
  -v "$POLYGLOT:/polyglot" \
  -v "$SETTINGS:/settings.yml" \
  -e OPENAI_API_KEY=sk-local \
  -e OPENAI_API_BASE="$ENDPOINT" \
  -e AIDER_DOCKER=1 -e AIDER_BENCHMARK_DIR=/benchmarks \
  --name "$CNAME" \
  aider-benchmark \
  python3 /aider/benchmark/benchmark.py "$RUN" --model "openai/$MODEL" \
  --edit-format "$EF" --threads 1 --exercises-dir /polyglot --read-model-settings /settings.yml \
  --new --num-tests "$N" ${EXTRA[@]+"${EXTRA[@]}"}
