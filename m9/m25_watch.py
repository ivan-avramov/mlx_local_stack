import os, time, datetime
PID = 75079
WD = "$STACK_WORKDIR/m9"
PY = "$STACK_REPO/benchmark/results/Qwen3.8-27B-OptiQ-4.5bpw-mixed/opencode.jsonl"
GO = WD + "/Qwen3.8-27B-OptiQ-4.5bpw-mixed.opencode_go.jsonl"
DEADLINE = time.time() + 36000
def alive(pid):
    try: os.kill(pid, 0); return True
    except OSError: return False
def rows(p):
    try: return sum(1 for _ in open(p))
    except OSError: return 0
while time.time() < DEADLINE:
    ts = datetime.datetime.now().strftime("%m-%d %H:%M")
    try: tail = open(WD+"/m25_orchestrator.log").read().strip().splitlines()[-1]
    except Exception: tail = "(no log)"
    a = alive(PID)
    with open(WD+"/m25_watch.log","a") as f:
        f.write(f"[{ts}] alive={a} py={rows(PY)}/22 go={rows(GO)}/22 last: {tail}\n")
    if not a: break
    time.sleep(300)
