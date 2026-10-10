"""Waits for the M33 chain to exit; if it finished clean, lands the submodule bumps (operator queue rule: bumps BEFORE any
new arm) and launches the M32 chain on the fresh M32 overlay. Operator GO for M32: 2026-09-05 (P2)."""
import os, subprocess, sys, time
WD = os.environ["STACK_WORKDIR"]; REPO = os.environ["STACK_REPO"]
LOG = open(f"{WD}/m32/waiter.log", "a", buffering=1)
def log(m): LOG.write(f"[{time.strftime('%m-%d %H:%M:%S')}] {m}\n")
def sh(cmd, **kw): return subprocess.run(cmd, capture_output=True, text=True, **kw)
VLM, SERVE = "420c01e1", "0ccc6842"
pid = int(open(f"{WD}/m33/m33.pid").read().strip()); log(f"waiting on m33_chain pid {pid}")
while True:
    try: os.kill(pid, 0)
    except OSError: break
    time.sleep(60)
log("m33_chain exited"); time.sleep(10)
tail = open(f"{WD}/m33/m33.log").read()[-4000:]
if "=== M33 DONE ===" not in tail:
    log("M33 did NOT log DONE — not bumping, not launching M32. Tail:\n" + tail[-1500:]); sys.exit(1)
if sh(["pgrep", "-f", "run.py generate|bench_watch"]).stdout.strip(): log("WARN: a driver/watch is still alive after chain exit"); time.sleep(60)
for sub, sha in (("src/mlx-vlm", VLM), ("src/mlx-serve", SERVE)):
    r = sh(["git", "-C", f"{REPO}/{sub}", "checkout", "-q", sha])
    if r.returncode: log(f"FATAL checkout {sub} {sha}: {r.stderr}"); sys.exit(2)
    log(f"BUMP {sub} -> {sh(['git','-C',f'{REPO}/{sub}','rev-parse','--short=8','HEAD']).stdout.strip()}")
msg = ("chore(stack): bump src/mlx-vlm -> 420c01e1 (M34 layer-scoped MoE expert expansion + verifier fixes), "
       "src/mlx-serve -> 0ccc684 (moe_expand forwarding)\n\nSubmodules bumped after M33 ended, before the M32 arm, so every "
       "later row carries the new serving-path hash consistently (handoff queue item 1).\n\n"
       "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n"
       "Claude-Session: https://claude.ai/code/session_01JUyHrWyQp9ZXnrvv8JEBqB")
sh(["git", "-C", REPO, "add", "src/mlx-vlm", "src/mlx-serve"])
r = sh(["git", "-C", REPO, "commit", "-q", "-m", msg])
log(f"BUMP COMMIT rc={r.returncode} {sh(['git','-C',REPO,'log','--oneline','-1']).stdout.strip()} {r.stderr[-300:]}")
if r.returncode: sys.exit(3)
env = dict(os.environ); env.pop("APC_ENABLED", None)
env["M32_OVERLAY"] = f"{WD}/m32/bench_overlay_m32.yaml"; env["M32_PIN"] = VLM
log("LAUNCH m32_chain.py")
with open(f"{WD}/m32/chain.nohup", "a") as nf:
    p = subprocess.Popen([f"{REPO}/.venv-bench/bin/python", f"{WD}/m32/m32_chain.py"], cwd=REPO, env=env,
                         stdout=nf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
open(f"{WD}/m32/m32.pid", "w").write(str(p.pid)); log(f"m32_chain pid={p.pid}")
rc = p.wait(); log(f"m32_chain exited rc={rc}")
