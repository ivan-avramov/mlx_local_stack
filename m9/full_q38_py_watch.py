import os, time, datetime
PID = 34098
ROWS = "$STACK_REPO/benchmark/results/Qwen3.8-27B-mlx-uniform-4bit/opencode.jsonl"
LOG = "$STACK_WORKDIR/m9/full_q38_python.log"
OUT = "$STACK_WORKDIR/m9/full_q38_python.watch.log"
DEADLINE = time.time() + 16200
def alive(pid):
    try: os.kill(pid, 0); return True
    except OSError: return False
while time.time() < DEADLINE:
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    try: nrows = sum(1 for _ in open(ROWS))
    except OSError: nrows = -1
    try: tail = open(LOG).read().strip().splitlines()[-1]
    except Exception: tail = "(no log yet)"
    a = alive(PID)
    with open(OUT, "a") as f:
        f.write(f"[{ts}] alive={a} rows={nrows}/22 last: {tail}\n")
    if not a: break
    time.sleep(300)
