#!/usr/bin/env bash
# Acceptance for the tg2 grader image: reference solutions per language, offline. Usage: acceptance.sh [corpus-dir]
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.orbstack/bin:$PATH"
corpus="${1:-${POLYGLOT_DIR:-${STACK_WORKDIR:?STACK_WORKDIR or POLYGLOT_DIR required}/polyglot-benchmark}}"
python="${PYTHON:-$here/../../../.venv-bench/bin/python}"
exec nice -n 19 "$python" "$here/acceptance.py" "$corpus"
