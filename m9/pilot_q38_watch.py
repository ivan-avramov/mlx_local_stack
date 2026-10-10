import os, time, subprocess, datetime
PID = 26948
ROWS = "$STACK_WORKDIR/m9/Qwen3.8-27B-mlx-uniform-4bit.opencode_go.jsonl"
LOG = "$STACK_WORKDIR/m9/pilot_q38_go.log"
OUT = "$STACK_WORKDIR/m9/pilot_q38_go.watch.log"
DEADLINE = time.time() + 6000
def alive(pid):
    try: os.kill(pid, 0); return True
    except OSError: return False
while time.time() < DEADLINE:
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    try:
        nrows = sum(1 for _ in open(ROWS))
    except OSError:
        nrows = -1
    try:
        tail = open(LOG).read().strip().splitlines()[-1]
    except Exception:
        tail = "(no log)"
    a = alive(PID)
    with open(OUT, "a") as f:
        f.write(f"[{ts}] alive={a} rows={nrows}/5 last: {tail}\n")
    if not a:
        break
    time.sleep(300)
