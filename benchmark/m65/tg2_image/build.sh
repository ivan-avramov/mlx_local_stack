#!/usr/bin/env bash
# Build the tg2 grader image (tagged tg2-grader:m65-v1) and print + record its id and reproducibility metadata.
# Network is allowed here only. The corpus checkout must be exactly the pinned polyglot_sha and clean.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.orbstack/bin:$PATH"
corpus="${POLYGLOT_DIR:-${STACK_WORKDIR:?STACK_WORKDIR or POLYGLOT_DIR required}/polyglot-benchmark}"
tag="tg2-grader:m65-v1"
python="${PYTHON:-python3}"
rm -rf "$here/ctx"; trap 'rm -rf "$here/ctx"' EXIT
polyglot_sha="$("$python" -I "$here/verify_corpus.py" "$corpus" "$here/polyglot_sha")"
"$python" -I "$here/stage_context.py" "$corpus" "$here/ctx"
context_sha="$("$python" -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import stage_context as s; print(s.context_digest(sys.argv[2]))' "$here" "$here/ctx")"
nice -n 19 docker build --pull=false --provenance=false -t "$tag" \
  --build-arg "POLYGLOT_SHA=$polyglot_sha" --build-arg "CONTEXT_SHA256=$context_sha" "$here"
digest="$(docker image inspect --format '{{.Id}}' "$tag")"
sha() { shasum -a 256 "$@" | shasum -a 256 | cut -d' ' -f1; }
{
  printf '%s\n' "$digest"
  printf 'polyglot_sha=%s\n' "$polyglot_sha"
  printf 'context_sha256=%s\n' "$context_sha"
  printf 'js_lock_sha256=%s\n' "$(sha "$here/locks/js/package-lock.json")"
  printf 'cargo_locks_sha256=%s\n' "$(cd "$here/locks/rust" && find . -name Cargo.lock | LC_ALL=C sort | xargs shasum -a 256 | shasum -a 256 | cut -d' ' -f1)"
} > "$here/IMAGE_ID"
echo "$tag $digest"
