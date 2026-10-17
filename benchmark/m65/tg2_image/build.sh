#!/usr/bin/env bash
# Build the tg2 grader image (tagged tg2-grader:m65-v1) and print + record its digest. Network is allowed here only.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.orbstack/bin:$PATH"
corpus="${POLYGLOT_DIR:-${STACK_WORKDIR:?STACK_WORKDIR or POLYGLOT_DIR required}/polyglot-benchmark}"
tag="tg2-grader:m65-v1"
python="${PYTHON:-python3}"
rm -rf "$here/ctx"; trap 'rm -rf "$here/ctx"' EXIT
"$python" -I "$here/stage_context.py" "$corpus" "$here/ctx"
nice -n 19 docker build --pull=false --provenance=false -t "$tag" "$here"
digest="$(docker image inspect --format '{{.Id}}' "$tag")"
printf '%s\n' "$digest" > "$here/IMAGE_ID"
echo "$tag $digest"
