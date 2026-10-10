import glob, os, re, subprocess, time
OUT = os.environ["STACK_WORKDIR"] + "/nemo_ladder"; W = open(f"{OUT}/watch.log", "a", buffering=1)
def worker():
    ps = subprocess.run(["ps", "-eo", "pid,pcpu,etime,command"], capture_output=True, text=True).stdout
    for l in ps.splitlines():
        if "mlx_vlm.server" in l and "--model" in l: return l.split()[1] + "%cpu etime=" + l.split()[2]
    return "NONE"
n0 = len(open(f"{OUT}/orchestrator.log").read().splitlines()); pid0 = int(open(f"{OUT}/orchestrator.pid").read()); os.kill(pid0, 0); W.write(f"SELFTEST ok: orchestrator.log has {n0} lines; orchestrator pid {pid0} is alive at arm time\n")
while True:
    pid = int(open(f"{OUT}/orchestrator.pid").read())
    try: os.kill(pid, 0); alive = True
    except OSError: alive = False
    prog = {}
    for f in sorted(glob.glob(f"{OUT}/ladder_*.log") + glob.glob(f"{OUT}/hep_*.log")):
        txt = open(f).read(); done = txt.count("rung done") if "ladder" in f else len(re.findall(r"\bdone\b|\[gen\]", txt))
        prog[os.path.basename(f)] = (done, txt.strip().splitlines()[-1][-110:] if txt.strip() else "-")
    last = open(f"{OUT}/orchestrator.log").read().strip().splitlines()[-1]
    W.write(f"[{time.strftime('%m-%d %H:%M')}] orch_alive={alive} worker={worker()} progress={prog} last: {last}\n")
    if not alive: W.write("===== ORCHESTRATOR GONE — watch stopping =====\n"); break
    time.sleep(300)
