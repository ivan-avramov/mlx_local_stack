#!/bin/bash
# Wait for the Ornith s1 unload (no item running), then move scratch/octmp -> octmp.noindex + symlink back.
M=$STACK_WORKDIR/m55; W=$STACK_WORKDIR
until /usr/bin/grep -q "unload Ornith-1.0-35B-mlx-uniform-4bit ok" $M/RUNLOG.md; do sleep 20; done
if [ -L $W/scratch/octmp ]; then echo "already a symlink"; exit 0; fi
pgrep -f "run_opencode_prob[e]" >/dev/null && { echo "probe still running at swap?! abort"; exit 1; }
mv $W/scratch/octmp $W/scratch/octmp.noindex && ln -s octmp.noindex $W/scratch/octmp && echo "$(date -u +%FT%TZ) scratch/octmp -> octmp.noindex (+symlink) applied at the Ornith s1 unload" | tee -a $M/RUNLOG.md
