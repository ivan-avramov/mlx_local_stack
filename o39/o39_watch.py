"""O39 5-minute assessment daemon (operator rule: report AND critically evaluate).

Answers the four questions each tick: progressing? rate vs prediction? output sane?
correction needed? Exits when the driver dies (checked BY PID each tick — the M18
watcher's lesson: its pgrep-based check kept it alive past its driver's death).
Busy discriminator: silent-but-BUSY (>10% CPU) is a runaway, never kill.
"""
import json, os, subprocess, sys, time

DRIVER_PID = int(sys.argv[1])
ROWS = sys.argv[2]
PRED_MEAN_S = float(sys.argv[3]) if len(sys.argv) > 3 else 187.0
TICK_S = 300

def driver_alive():
    try:
        os.kill(DRIVER_PID, 0)
        return True
    except OSError:
        return False

def worker_cpu():
    out = subprocess.run(["pgrep", "-f", "mlx_vlm.*server"], capture_output=True, text=True)
    pids = out.stdout.split()
    if not pids:
        return None
    cpu = subprocess.run(["ps", "-o", "pcpu=", "-p", pids[0]], capture_output=True, text=True)
    try:
        return float(cpu.stdout.strip())
    except ValueError:
        return None

last_n = -1
flat = 0
while True:
    if not driver_alive():
        print(f"WATCH-EXIT driver {DRIVER_PID} gone", flush=True)
        break
    try:
        rows = [json.loads(l) for l in open(ROWS)]
    except FileNotFoundError:
        rows = []
    n = len(rows)
    npass = sum(1 for r in rows if r.get("passed"))
    stalls = sum(1 for r in rows if r.get("stop_reason") == "stalled")
    tm = sum(1 for r in rows if r.get("test_modified"))
    walls = [r.get("wall_s", 0) for r in rows]
    mean_w = sum(walls) / n if n else 0
    cpu = worker_cpu()
    if n == last_n:
        flat += 1
    else:
        flat = 0
    verdict = "ok"
    if flat >= 2 and (cpu is None or cpu <= 10.0):
        verdict = "SUSPECTED WEDGE — 2 flat ticks and worker IDLE (<=10% CPU); investigate, kill only by PID after confirming"
    elif flat >= 2:
        verdict = f"flat x{flat} but worker BUSY ({cpu}% CPU) — runaway/long session, no action"
    print(f"[{time.strftime('%H:%M:%S')}] n={n} pass={npass} stalls={stalls} test_mod={tm} "
          f"mean_wall={mean_w:.0f}s (pred {PRED_MEAN_S:.0f}) worker_cpu={cpu} verdict={verdict}",
          flush=True)
    last_n = n
    time.sleep(TICK_S)
