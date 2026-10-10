import os, time, glob, datetime
PID = 77840
WD = "$STACK_WORKDIR/m9"
DEADLINE = time.time() + 64800
def alive(pid):
    try: os.kill(pid, 0); return True
    except OSError: return False
while time.time() < DEADLINE:
    ts = datetime.datetime.now().strftime("%m-%d %H:%M")
    rows = {os.path.basename(f).split(".opencode_")[0][:9]+":"+f.split(".opencode_")[1].replace(".s2.jsonl",""): sum(1 for _ in open(f))
            for f in glob.glob(WD+"/*.s2.jsonl")}
    try: tail = open(WD+"/m26_orchestrator.log").read().strip().splitlines()[-1]
    except Exception: tail = "(no log)"
    a = alive(PID)
    with open(WD+"/m26_watch.log","a") as f:
        f.write(f"[{ts}] alive={a} rows={rows} last: {tail}\n")
    if not a: break
    time.sleep(300)
