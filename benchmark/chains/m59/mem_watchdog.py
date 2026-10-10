# FROZEN copy (P229, 2026-10-10) of $STACK_WORKDIR/m59/mem_watchdog.py, the driver behind the opencode_v2_*.m59.* (M59) rows.
# Only change: absolute home paths -> $STACK_WORKDIR / $STACK_REPO. See benchmark/chains/README.md.
"""P183 memory watchdog for the M59 chain (operator go 2026-10-08). Every POLL_S seconds:
  A) SIGKILL any process whose cwd (or command line) is under SCRATCH with RSS > LIMIT_GB;
  B) SIGKILL any process whose cwd is under SCRATCH but whose item dir no longer exists (orphan of a finished item).
Never touches the model server, the router or opencode itself. Logs every kill and a 10-minute heartbeat to RUNLOG.md.
Exits when STOP_FILE exists. Usage: mem_watchdog.py [--once --root R --limit-gb X --log L]"""
import argparse, os, sys, time
from pathlib import Path
import psutil

WD = Path(os.environ.get("STACK_WORKDIR") or (Path.home() / "ws/mlx_local_stack_workdir"))
ap = argparse.ArgumentParser()
ap.add_argument("--root", default=str(WD / "scratch" / "octmp.noindex"))
ap.add_argument("--limit-gb", type=float, default=8.0)
ap.add_argument("--poll-s", type=float, default=2.0)
ap.add_argument("--log", default=str(WD / "m59" / "RUNLOG.md"))
ap.add_argument("--stop-file", default=str(WD / "m59" / "after_chain.rc"))
ap.add_argument("--once", action="store_true")
a = ap.parse_args()
ROOT = os.path.realpath(a.root)
LIMIT = int(a.limit_gb * 1024 ** 3)
PROTECTED = ("mlx_vlm.server", "mlx-serve", "/opencode", "run_m59.py", "mem_watchdog.py", "run_opencode_probe_v2.py")


def log(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} WATCHDOG {msg}"
    print(line, flush=True)
    with open(a.log, "a") as f:
        f.write("- " + line + "\n")


def under_root(path):
    return path == ROOT or path.startswith(ROOT + os.sep)


def item_dir(cwd):
    rel = os.path.relpath(cwd, ROOT).split(os.sep)
    return os.path.join(ROOT, rel[0]) if rel and rel[0] not in (".", "..") else None


def sweep():
    killed, max_rss = 0, 0
    for pid in psutil.pids():
        try:
            if pid == os.getpid():
                continue
            p = psutil.Process(pid)
            p.info = {"cmdline": p.cmdline(), "memory_info": p.memory_info()}
            cmd = " ".join(p.info["cmdline"] or [])
            if any(x in cmd for x in PROTECTED):
                continue
            try:
                cwd = p.cwd()
            except (psutil.AccessDenied, psutil.ZombieProcess, FileNotFoundError, OSError):
                cwd = ""
            in_scratch = (cwd and under_root(os.path.realpath(cwd))) or (ROOT in cmd)
            if not in_scratch:
                continue
            rss = p.info["memory_info"].rss if p.info["memory_info"] else 0
            max_rss = max(max_rss, rss)
            rule = None
            if rss > LIMIT:
                rule = f"A rss {rss / 1024 ** 3:.1f}GB > {LIMIT / 1024 ** 3:.0f}GB"
            elif cwd and under_root(os.path.realpath(cwd)):
                idir = item_dir(os.path.realpath(cwd))
                if idir and not os.path.isdir(idir):
                    rule = "B orphan of a finished item"
            if rule:
                p.kill()
                killed += 1
                log(f"KILL pid {p.pid} ({rule}) cwd={cwd.replace(str(WD), '$STACK_WORKDIR')} cmd={cmd.replace(str(WD), '$STACK_WORKDIR').replace(str(Path.home()), '~')[:200]}")
        except Exception:  # noqa: BLE001 — a process exiting mid-read (psutil raises SystemError on macOS) must never stop the sweep
            continue
    return killed, max_rss


if a.once:
    sweep()
    sys.exit(0)
log(f"armed root={ROOT.replace(str(WD), '$STACK_WORKDIR')} limit={a.limit_gb}GB poll={a.poll_s}s")
last_beat = 0
while not os.path.exists(a.stop_file):
    k, m = sweep()
    if time.time() - last_beat > 600:
        log(f"alive (max scratch-process RSS this sweep {m / 1024 ** 2:.0f}MB)")
        last_beat = time.time()
    time.sleep(a.poll_s)
log("stop file present -> exiting")
