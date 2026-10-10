"""M31b (operator question 2026-09-04: "will the 3.8-OptiQ also be put through the same test?"): ifeval arm for
Qwen3.8-27B-OptiQ-4.5bpw-mixed @t0.6 (deployed), tune m31, same seed-0 148-item draw as the M31 arms (paired by construction),
bound 7800 s, predictor OFF, M21 draft-OFF overlay, worktree 7330d3a6. Pilot 5 -> n=148 -> grade -> compare vs
Qwen3.8-27B-mlx-uniform-4bit@m31 and Qwen3.6-27B-Opus-Distill-OptiQ-4bit@m31. Purpose: the only cheap axis that can break the
M25 tie (opencode 18 vs 20 python, 16 vs 16 go). Read: prompt-level strict, paired; no re-rank on its own."""
import os, sys, time
WD = os.environ["STACK_WORKDIR"]
src = open(f"{WD}/m21/arms_chain.py").read().split("# ---------------------------------------------------------------- main")[0]
exec(src)  # noqa: S102
OUT = f"{WD}/m31"; LOG = open(f"{OUT}/m31b.log", "a", buffering=1)
BENCH = "ifeval"; TUNE = "m31"; N_FULL = 148; N_PILOT = 5; PIN = "7330d3a6"
OPT = "Qwen3.8-27B-OptiQ-4.5bpw-mixed"; BASE = "Qwen3.8-27B-mlx-uniform-4bit"; Q36 = "Qwen3.6-27B-Opus-Distill-OptiQ-4bit"
threading.Thread(target=mem_sampler, daemon=True).start()
log("=== M31b START ===")
nd = os.environ.get("NLTK_DATA", "")
if not nd.startswith(WD): fatal(f"NLTK_DATA={nd!r} is not under STACK_WORKDIR")
if not listeners(): start_router()
else:
    pid = listeners()[0]; e = sh(["ps","-Eww","-o","command=","-p",str(pid)]).stdout
    if ("MLX_SERVE_CONFIG=" + OVERLAY) not in e or "APC_ENABLED" in e: stop_router(); start_router()
    else: log(f"router already up pid={pid} on the M21 overlay")
pin = sh(["git","-C",f"{REPO}/src/mlx-vlm","rev-parse","--short=8","HEAD"]).stdout.strip(); log(f"src/mlx-vlm worktree = {pin} (expect {PIN})")
if pin != PIN: fatal(f"submodule worktree is not at {PIN}")
env = dict(os.environ); env.pop("APC_ENABLED", None); env["MLX_SERVE_CONFIG"] = OVERLAY
rc = run_generate([OPT], N_PILOT, f"pilot_{OPT}", probe_timeout=7800, extra=["--samples", "1"])
s = summarize(OPT, 5)
if s.get("n", 0) < 5 or s.get("errors"): fatal(f"pilot incomplete or errored: {s}")
log(f"PILOT SIZING {OPT}: mean {s['wall_mean_s']:.0f} s/item (max {s['wall_max_s']:.0f} s); nearest actual: the M31 base arm (same weights family) 4.5 h Σ wall for 148 with 1 loop. No abort on the pilot mean.")
rc = run_generate([OPT], N_FULL, f"full_{OPT}", probe_timeout=7800, extra=["--samples", "1"])
if rc != 0: log(f"WARN: driver rc={rc}")
rs = rows(OPT); log(f"ROWS {OPT} ifeval@m31: {len(rs)} rows, converged={sum(1 for r in rs if r.get('converged'))}, errors={[r['id'] for r in rs if r.get('error')]}")
summarize(OPT, N_FULL)
log(f"NEW non-converged/error set {OPT}: {sorted(r['id'] for r in rs if r.get('error') or not r.get('converged'))}")
g = sh([PY, f"{REPO}/benchmark/run.py", "grade", "--models", OPT, "--benches", BENCH, "--tune", TUNE], cwd=REPO, env=env)
open(f"{OUT}/grade_{OPT}.log", "a").write(g.stdout + g.stderr); log(f"END grade {OPT} rc={g.returncode}")
try:
    sc = json.load(open(f"{REPO}/benchmark/results/{OPT}/{BENCH}.{TUNE}.score.json"))
    log(f"SCORE {OPT} ifeval@m31: prompt_strict={sc.get('prompt_strict')} acc_strict={sc.get('acc_strict')} prompt_loose={sc.get('prompt_loose')} n={sc.get('n')} errors={sc.get('errors')} note={sc.get('note')}")
except Exception as ex: log(f"WARN: no score: {ex}")
for other, tag in ((BASE, "optiq_vs_base"), (Q36, "optiq_vs_q36")):
    for extra in ([], ["--intersect"]):
        c = sh([PY, f"{REPO}/benchmark/run.py", "compare", "--models", f"{OPT}@m31,{other}@m31", "--benches", BENCH] + extra, cwd=REPO, env=env)
        open(f"{OUT}/compare_{tag}{'_intersect' if extra else ''}.log", "a").write(c.stdout + c.stderr)
        log(f"END compare {tag}{' --intersect' if extra else ''} rc={c.returncode} :: {(c.stdout.strip().splitlines() or ['<no output>'])[-1][:200]}")
STOP.set(); log("=== M31b DONE ===")
