import glob, os, subprocess, time
WD = "$STACK_WORKDIR/m11"
OUT = open(f"{WD}/m11_watch.log", "a", buffering=1)
while True:
    alive = subprocess.run(["pgrep", "-f", "m11_orchestrator_v3"], capture_output=True).returncode == 0
    prog = {}
    for f in glob.glob(f"{WD}/m11_*.log"):
        name = os.path.basename(f)[4:-4]
        if name in ("orchestrator", "watch"): continue
        txt = open(f).read()
        rungs = [l for l in txt.splitlines() if "[reasoning] rung done" in l]
        prog[name[:12]] = (len(rungs), rungs[-1].split("] ")[1] if rungs else "-")
    last = open(f"{WD}/m11_orchestrator.log").read().strip().splitlines()[-1] if os.path.exists(f"{WD}/m11_orchestrator.log") else "(no log)"
    OUT.write(f"[{time.strftime('%m-%d %H:%M')}] alive={alive} rungs_done={prog} last: {last}\n")
    if not alive:
        OUT.write("===== ORCHESTRATOR GONE — watch stopping =====\n"); break
    time.sleep(300)
