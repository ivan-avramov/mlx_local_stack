#!/bin/bash
# FROZEN copy (P229, 2026-10-10) of $STACK_WORKDIR/m55/noindex_at_swap.sh, the driver behind the opencode_*.m55.* (M55) rows.
# Only change: absolute home paths -> $STACK_WORKDIR / $STACK_REPO. See benchmark/chains/README.md.
# Wait for the Ornith-1.0-35B-mlx-uniform-4bit s1 unload (no item running), then move scratch/octmp -> octmp.noindex + symlink back.
M=$STACK_WORKDIR/m55; W=$STACK_WORKDIR
until /usr/bin/grep -q "unload Ornith-1.0-35B-mlx-uniform-4bit ok" $M/RUNLOG.md; do sleep 20; done
if [ -L $W/scratch/octmp ]; then echo "already a symlink"; exit 0; fi
pgrep -f "run_opencode_prob[e]" >/dev/null && { echo "probe still running at swap?! abort"; exit 1; }
mv $W/scratch/octmp $W/scratch/octmp.noindex && ln -s octmp.noindex $W/scratch/octmp && echo "$(date -u +%FT%TZ) scratch/octmp -> octmp.noindex (+symlink) applied at the Ornith-1.0-35B-mlx-uniform-4bit s1 unload" | tee -a $M/RUNLOG.md
