#!/bin/bash
# launch_tg1.sh <out-root-name> <runner args...>: detached tg1 chain into $STACK_WORKDIR/<out-root-name>
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
R="$(cd "$(dirname "$0")/../../.." && pwd)"
export PATH="$HOME/.orbstack/bin:$PATH"
D="$STACK_WORKDIR/$1"; shift
mkdir -p "$D"; /bin/rm -f "$D/driver.chain.rc"
cd "$R" && "$R/.venv-bench/bin/python" "$R/benchmark/chains/c147/run_tg1_chain.py" "$@" --out-root "$D" > "$D/driver.chain.out" 2>&1 < /dev/null; rc=$?
echo $rc > "$D/driver.chain.rc"
exit $rc
