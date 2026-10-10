# FROZEN copy (P229, 2026-10-10) of $STACK_WORKDIR/m55/pilot.py, the driver behind the opencode_*.m55.* (M55) rows.
# Only change: absolute home paths -> $STACK_WORKDIR / $STACK_REPO. See benchmark/chains/README.md.
"""M55 pilot: 5 seeded random (lang,item) pairs across the 66, run twice on the loaded first pick; report discordance."""
import json, random, subprocess, os, sys, time
WD=os.environ["STACK_WORKDIR"]; REPO=os.environ["STACK_REPO"]; OUT=f"{WD}/m55/pilot"
draws=json.load(open(f"{WD}/m9/c37_draws.json")); LANGS=["rust","java","javascript"]
pairs=sorted((l,i) for l in LANGS for i in draws[l]); pick=random.Random(20261003).sample(pairs,5)
print("pilot draw:",pick, flush=True)
MODEL="Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
env=dict(os.environ); env["TMPDIR"]=f"{WD}/scratch/octmp"; env["STACK_WORKDIR"]=WD; env["MLX_SERVE_CONFIG"]=f"{WD}/m54/overlay_m54_draft_off.yaml"
for run in sys.argv[1:] or ["a","b"]:
    for lang in LANGS:
        items=[i for l,i in pick if l==lang]
        if not items: continue
        out=f"{OUT}/{run}.{lang}.jsonl"; t=time.time()
        rc=subprocess.run([f"{REPO}/.venv-bench/bin/python",f"{REPO}/benchmark/run_opencode_probe.py","--model",MODEL,"--items",",".join(items),"--lang",lang,"--out",out],cwd=REPO,env=env,stdout=open(f"{OUT}/{run}.{lang}.log","a"),stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL).returncode
        print(f"{run} {lang} items={items} rc={rc} {time.time()-t:.0f}s", flush=True)
