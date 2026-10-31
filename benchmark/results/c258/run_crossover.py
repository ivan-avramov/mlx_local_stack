"""C258 crossover (P568): MTP ON vs OFF decode at 128K / 192K (+ a 256K anchor) per entry, `bench.run_capacity` over HTTP.

  .venv-bench/bin/python benchmark/results/c258/run_crossover.py --entry <name> --grid 131072,196608[,256000] --tag <tag> [--smoke]

One ABBA block (OFF, ON, ON, OFF) for one entry. Both arms are lean routers started from the main checkout (AGENTS lean start:
`.env` sourced, `MLX_VLM_CACHE_SESSION_MAX=1`); they differ only in `MLX_SERVE_CONFIG`: ON = the main checkout's
`main_models.yaml`, OFF = `$STACK_WORKDIR/worktrees/stack-c258x-off/main_models.yaml` (all four MTP entries OFF). 600 s idle
before every arm after the first; a tick every 300 s logs `pmset -g ac` / battery and the driver's liveness; the worker cmdline
is recorded per arm. Any failure stops the block nonzero; `--smoke` = no idle, rows tagged `<tag>-smoke`.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WD = Path(os.environ["STACK_WORKDIR"])
OFF_CONFIG = WD / "worktrees" / "stack-c258x-off" / "main_models.yaml"
ON_CONFIG = REPO / "main_models.yaml"
ORDER = (("1", "off"), ("2", "on"), ("3", "on"), ("4", "off"))
IDLE_S, TICK_S = 600, 300
BASE = "http://127.0.0.1:8000"


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sh(argv, timeout=60):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout).stdout


def power():
    """Watts / volts / battery only (the full `pmset -g ac` dump carries the adapter's serial string)."""
    ac = {k.strip(): v.strip() for k, v in (line.split("=", 1) for line in sh(["pmset", "-g", "ac"]).splitlines() if "=" in line)}
    batt = re.search(r"(\d+)%; ([a-zA-Z ]+);", sh(["pmset", "-g", "batt"]))
    out = dict(watts=ac.get("Wattage"), millivolts=ac.get("Voltage"), battery_pct=int(batt.group(1)) if batt else None,
               battery_state=batt.group(2).strip() if batt else None)
    out["ok"] = out["watts"] == "140W" and out["millivolts"] == "28000mV" and (out["battery_pct"] or 0) > 20
    return out


def portable(text):
    return str(text).replace(str(WD), "$STACK_WORKDIR").replace(str(REPO), "<REPO>").replace(str(Path.home()), "$HOME")


class Log:
    def __init__(self, path):
        self.path = path

    def __call__(self, event, **kw):
        line = json.dumps(dict(t=now(), event=event, **kw))
        with open(self.path, "a") as f:
            f.write(line + "\n")
        print(line, flush=True)


def port_owner():
    out = sh(["lsof", "-nP", "-iTCP:8000", "-sTCP:LISTEN", "-t"]).split()
    return out[0] if out else None


def worker_cmdline():
    """The model worker's argv (the process carrying `--model`, spawned by the router), for the record."""
    rows = [line.strip() for line in sh(["ps", "-axo", "pid=,command="]).splitlines()]
    return [portable(r) for r in rows if " --model " in r and "--port" in r and "run_crossover" not in r]


def ready(timeout_s=900):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(BASE + "/v1/models", timeout=10) as r:
                if r.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(5)
    return False


def stop_router(log):
    rc = subprocess.run([str(REPO / "scripts" / "stack_stop.sh")], cwd=REPO, capture_output=True, text=True, timeout=300).returncode
    for _ in range(120):
        if port_owner() is None:
            log("router_stopped", stop_rc=rc)
            return rc == 0
        time.sleep(5)
    log("router_did_not_stop", stop_rc=rc)
    return False


def run_arm(a, n, arm, log, logs_dir):
    config = ON_CONFIG if arm == "on" else OFF_CONFIG
    if port_owner() is not None:
        log("refused_port_busy", arm=arm, owner=port_owner())
        return 2
    log("arm_start", n=n, arm=arm, config=portable(config), power=power())
    router_log = open(logs_dir / f"router-{n}-{arm}.log", "ab")
    start = f'set -a; . ./.env; set +a; exec env MLX_VLM_CACHE_SESSION_MAX=1 MLX_SERVE_CONFIG="{config}" uv run mlx-serve start'
    router = subprocess.Popen(["/bin/bash", "-c", start], cwd=REPO, stdin=subprocess.DEVNULL, stdout=router_log,
                              stderr=subprocess.STDOUT, start_new_session=True)
    if not ready():
        log("router_not_ready", arm=arm)
        stop_router(log)
        return 3
    log("router_ready", arm=arm, router_pid=router.pid, owner=port_owner())
    tag = f"{a.tag}-{n}-{arm}" + ("-smoke" if a.smoke else "")
    env = dict(os.environ, MLX_SERVE_CONFIG=str(config))
    driver = subprocess.Popen([str(REPO / ".venv-bench/bin/python"), "-m", "bench.run_capacity", "--model", a.entry, "--grid", a.grid,
                               "--sampling-profile", "deployed", "--out-tag", tag, "--seed", str(a.seed)],
                              cwd=REPO / "benchmark", env=env, stdin=subprocess.DEVNULL,
                              stdout=open(logs_dir / f"capacity-{n}-{arm}.log", "ab"), stderr=subprocess.STDOUT)
    done = threading.Event()
    seen = {}

    def tick():
        while not done.wait(TICK_S if seen else 60):
            w = worker_cmdline()
            if w and "worker" not in seen:
                seen["worker"] = w
                log("worker_cmdline", arm=arm, worker=w)
            seen.setdefault("first", True)
            log("tick", arm=arm, driver_alive=driver.poll() is None, power=power())
    t = threading.Thread(target=tick, daemon=True)
    t.start()
    try:
        rc = driver.wait(timeout=a.arm_timeout_s)
    except subprocess.TimeoutExpired:
        log("driver_timeout_silent", arm=arm, pid=driver.pid)  # never killed here: the operator decides (AGENTS)
        done.set()
        return 5
    done.set()
    t.join(timeout=5)
    if "worker" not in seen:
        log("worker_cmdline", arm=arm, worker=worker_cmdline())
    log("arm_end", n=n, arm=arm, driver_rc=rc, power=power())
    if not stop_router(log):
        return 4
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", required=True)
    ap.add_argument("--grid", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--seed", type=int, default=2580)
    ap.add_argument("--arm-timeout-s", type=float, default=4 * 3600)
    ap.add_argument("--smoke", action="store_true", help="ON then OFF, no idle (instrument check, not a measurement)")
    a = ap.parse_args(argv)
    logs_dir = WD / "c258x" / f"{a.tag}{'-smoke' if a.smoke else ''}-{a.entry}"
    logs_dir.mkdir(parents=True, exist_ok=False)
    log = Log(logs_dir / "block.jsonl")
    log("block_start", entry=a.entry, grid=a.grid, tag=a.tag, smoke=a.smoke, repo_head=sh(["git", "-C", str(REPO), "rev-parse", "HEAD"]).strip(),
        off_head=sh(["git", "-C", str(OFF_CONFIG.parent), "rev-parse", "HEAD"]).strip())
    order = (("1", "on"), ("2", "off")) if a.smoke else ORDER
    for i, (n, arm) in enumerate(order):
        if i and not a.smoke:
            log("idle", seconds=IDLE_S)
            time.sleep(IDLE_S)
        rc = run_arm(a, n, arm, log, logs_dir)
        if rc != 0:
            log("block_stopped", n=n, arm=arm, rc=rc)
            return 1
    log("block_done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
