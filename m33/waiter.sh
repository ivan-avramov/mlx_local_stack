#!/bin/zsh
set -u
W=$STACK_WORKDIR
M31=$(cat $W/m31/m31.pid)
while kill -0 $M31 2>/dev/null; do sleep 120; done
sleep 30
echo "[$(date '+%m-%d %H:%M:%S')] WAITER: M31 pid $M31 exited (tail: $(tail -n1 $W/m31/m31.log)); launching M33" >> $W/m33/m33.log
cd $STACK_REPO || exit 1
unset APC_ENABLED
nohup .venv-bench/bin/python $W/m33/m33_chain.py > $W/m33/m33.nohup 2>&1 </dev/null &
echo $! > $W/m33/m33.pid
