#!/bin/zsh
# after the M32 chain exits, put the shipped daily-driver opencode config back (the running chain's exit handler removes the bench carrier)
while kill -0 37587 2>/dev/null; do sleep 30; done
sleep 5
/bin/cp -f $STACK_REPO/opencode_config/opencode.json $HOME/.config/opencode/opencode.json && echo "[$(date '+%m-%d %H:%M:%S')] daily-driver opencode.json restored" >> $STACK_WORKDIR/m32/m32.log
