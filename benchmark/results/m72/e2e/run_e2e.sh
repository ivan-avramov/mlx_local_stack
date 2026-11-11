#!/bin/zsh
# waits for the candidate gates (quiet CPU), then the end-to-end legs, order-balanced, 600 s idles
set -u
until grep -q STACK_RC= $STACK_WORKDIR/fe-m72p2s/gatelogs/stack.log 2>/dev/null; do sleep 30; done
echo "[$(date +%H:%M:%S)] gates done; idle 600 s" >> $STACK_WORKDIR/m72/e2e-s20/run.log; sleep 600
cd ~/ws/mlx_local_stack && export PYTHONPATH=../mlx-vlm:benchmark/spikes
uv run python benchmark/spikes/m72_e2e_prefill.py --tokens 131072 --legs native16 tq4_p2s:layer tq4_p2s:layer native16 --idle 600 --out $STACK_WORKDIR/m72/e2e-s20/e2e-131072.json >> $STACK_WORKDIR/m72/e2e-s20/run.log 2>&1 || exit 21
sleep 600
uv run python benchmark/spikes/m72_e2e_prefill.py --tokens 262144 --legs native16 tq4_p2s:layer tq4_p2s:layer native16 --idle 600 --out $STACK_WORKDIR/m72/e2e-s20/e2e-262144.json >> $STACK_WORKDIR/m72/e2e-s20/run.log 2>&1 || exit 22
echo "[$(date +%H:%M:%S)] ALL DONE" >> $STACK_WORKDIR/m72/e2e-s20/run.log
