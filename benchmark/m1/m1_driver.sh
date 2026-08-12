#!/usr/bin/env bash
# M1 GATE — matched agentic H2H on the single worker (M5). Ornith vs the Opus-distill.
#
# ITEM SET IS PINNED BY NAME, not by --num-tests: aider does an UNSEEDED random.shuffle before
# truncating, so --num-tests alone gives each model a DIFFERENT random subset (which is exactly how
# the historical n=34 vs n=16 rows ended up being unrelated samples). Keywords filter BEFORE the
# shuffle, so both models see byte-identical exercises. --languages is also required: keywords match
# the whole relative path and would otherwise pull the same exercise name from every language.
#
# 5 langs x 22 = 110 matched cases -> MDE +-11.9pp. cpp is EXCLUDED from the headline: a g++
# template-error cascade fed back into the prompt produced 165k input tokens on the first cpp case,
# i.e. that axis measures the C++ toolchain. It runs later as a sub-study.
#
# WATCHDOG: aider sets RETRY_TIMEOUT to 24h, so one bad request can eat a day. M5 has no
# timeout(1)/gtimeout, so each batch is backgrounded and killed at CAP_PER_CASE * N.
set -u
export PATH=/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH
R=${REPO:?set REPO}
cd "$R"
export AIDER_REPO=${AIDER_REPO:?set AIDER_REPO}
export POLYGLOT_DIR=${POLYGLOT_DIR:?set POLYGLOT_DIR}
export AIDER_SETTINGS=/tmp/aider.bench.settings.yml   # weak_model -> self (shipped one 404s)
LOG=/tmp/m1_run.log
N=22
CAP_PER_CASE=1500          # 25 min/case ceiling; a batch is killed past N*CAP

K_python="affine-cipher,beer-song,book-store,bottle-song,bowling,connect,dominoes,dot-dsl,food-chain,forth,go-counting,grade-school,grep,hangman,list-ops,paasio,phone-number,pig-latin,poker,pov,proverb,react"
K_javascript="affine-cipher,alphametics,beer-song,binary,book-store,bottle-song,bowling,complex-numbers,connect,food-chain,forth,go-counting,grade-school,grep,house,killer-sudoku-helper,ledger,list-ops,meetup,ocr-numbers,palindrome-products,parallel-letter-frequency"
K_go="alphametics,beer-song,book-store,bottle-song,bowling,connect,counter,crypto-square,dnd-character,dominoes,error-handling,food-chain,forth,hexadecimal,kindergarten-garden,ledger,markdown,matrix,octal,paasio,palindrome-products,pig-latin"
K_rust="accumulate,acronym,alphametics,book-store,bowling,decimal,dot-dsl,doubly-linked-list,fizzy,forth,gigasecond,grade-school,grep,luhn-from,macros,nucleotide-codons,ocr-numbers,parallel-letter-frequency,pig-latin,poker,react,robot-name"
K_java="affine-cipher,all-your-base,alphametics,bank-account,book-store,bottle-song,bowling,change,circular-buffer,connect,custom-set,dominoes,food-chain,forth,go-counting,hangman,house,kindergarten-garden,ledger,mazy-mice,ocr-numbers,palindrome-products"

say() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }

run_batch() {
  local model="$1" fmt="$2" tag="$3" lang="$4" kw="$5"
  local cname="aider-$(printf '%s' "$model" | tr '/:.' '___')"
  local cap=$(( CAP_PER_CASE * N ))
  say "--- BATCH $tag/$lang n=$N cap=${cap}s"
  AIDER_LANGUAGES="$lang" AIDER_KEYWORDS="$kw" \
    bash benchmark/run_aider_docker.sh "$model" "$N" "$fmt" "m1-$tag-$lang" \
    >> "/tmp/m1_${tag}_${lang}.log" 2>&1 &
  local pid=$!
  local t=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 60; t=$((t+60))
    if [ "$t" -ge "$cap" ]; then
      say "!!! WATCHDOG kill $tag/$lang after ${t}s (aider RETRY_TIMEOUT is 24h)"
      docker kill "$cname" >/dev/null 2>&1; kill "$pid" 2>/dev/null; break
    fi
  done
  say "--- BATCH $tag/$lang ended after ${t}s"
}

run_model() {
  local model="$1" fmt="$2" tag="$3"
  say "=== START $model ($fmt)"
  for lang in python javascript go rust java; do
    eval "kw=\$K_$lang"
    run_batch "$model" "$fmt" "$tag" "$lang" "$kw"
  done
  say "=== DONE $model"
  curl -s -m 300 -X POST localhost:8000/v1/models/unload \
       -H 'Content-Type: application/json' -d "{\"model\":\"$model\"}" >/dev/null 2>&1
  say "=== unloaded $model"
}

say "M1 start: 5 langs x $N pinned-by-name, APC=1, deployed sampling, cap ${CAP_PER_CASE}s/case"
run_model Ornith-1.0-35B-mlx-uniform-4bit diff ornith
run_model Qwen3.6-27B-Opus-Distill-OptiQ-4bit diff distill
say "M1 DRIVER COMPLETE"
