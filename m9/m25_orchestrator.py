import os, subprocess, sys, time
WD = "$STACK_WORKDIR"
REPO = "$STACK_REPO"
MODEL = "Qwen3.8-27B-OptiQ-4.5bpw-mixed"
PY_ITEMS = "affine-cipher,beer-song,book-store,bottle-song,bowling,connect,dominoes,dot-dsl,food-chain,forth,go-counting,grade-school,grep,hangman,list-ops,paasio,phone-number,pig-latin,poker,pov,proverb,react"
GO_ITEMS = "counter,dnd-character,forth,alphametics,crypto-square,beer-song,book-store,bottle-song,bowling,connect,dominoes,error-handling,food-chain,hexadecimal,kindergarten-garden,ledger,markdown,matrix,octal,paasio,palindrome-products,pig-latin"
env = dict(os.environ)
env["PATH"] = f"{WD}/o39/opencode-1.18.15:" + env["PATH"]
env["TMPDIR"] = f"{WD}/scratch/octmp"
env["MLX_SERVE_CONFIG"] = f"{WD}/m6b/bench_overlay_draft_off.yaml"
LOG = open(f"{WD}/m9/m25_orchestrator.log", "a", buffering=1)
def log(m): LOG.write(f"[{time.strftime('%m-%d %H:%M:%S')}] {m}\n")
legs = [
    ("python", PY_ITEMS, None),  # default out -> benchmark/results/<model>/opencode.jsonl
    ("go", GO_ITEMS, f"{WD}/m9/{MODEL}.opencode_go.jsonl"),
]
for lang, items, out in legs:
    log(f"START {MODEL} {lang} (22 items)")
    cmd = [f"{REPO}/.venv-bench/bin/python", f"{REPO}/benchmark/run_opencode_probe.py",
           "--model", MODEL, "--items", items, "--lang", lang]
    if out: cmd += ["--out", out]
    with open(f"{WD}/m9/m25_{MODEL}.{lang}.log", "a") as lf:
        try:
            rc = subprocess.run(cmd, cwd=REPO, env=env, stdout=lf,
                                stderr=subprocess.STDOUT, timeout=18000).returncode
        except subprocess.TimeoutExpired:
            log(f"TIMEOUT {lang} — ABORT"); sys.exit(2)
    log(f"END {MODEL} {lang} rc={rc}")
    if rc != 0:
        log(f"FATAL leg rc={rc} — ABORT"); sys.exit(1)
log("M25 BOTH LEGS DONE")
