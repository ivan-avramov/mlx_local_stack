import os, time, glob, datetime
PID = 38498
WD = "$STACK_WORKDIR/m9"
DEADLINE = time.time() + 90000
def alive(pid):
    try: os.kill(pid, 0); return True
    except OSError: return False
while time.time() < DEADLINE:
    ts = datetime.datetime.now().strftime("%m-%d %H:%M")
    rows = {os.path.basename(f).replace(".opencode_",":").replace(".jsonl",""): sum(1 for _ in open(f))
            for f in glob.glob(WD+"/*.opencode_{rust,java,javascript}.jsonl".replace("{rust,java,javascript}","*"))
            if any(l in f for l in ("rust","java","javascript"))}
    try: tail = open(WD+"/c37_orchestrator.log").read().strip().splitlines()[-1]
    except Exception: tail = "(no log)"
    a = alive(PID)
    with open(WD+"/c37_watch.log","a") as f:
        f.write(f"[{ts}] alive={a} rows={rows} last: {tail}\n")
    if not a: break
    time.sleep(300)
