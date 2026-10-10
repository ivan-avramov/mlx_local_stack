"""C139(b) re-record under opencode-v2-web (operator go 2026-10-08): k=2 sessions (fresh instance per model per session),
both B picks, Python + Go 22 items, 48K-token allowance (probe default), seed bases 1001/2002 as M59, chain pilot of 5,
P202 cheat procedure after every leg: synchronous web audit, then same-instance same-seed re-runs with the source denied
(cap 2, then cheat_unresolved). Outputs $STACK_WORKDIR/m61/rr/<model>.rr.<s>.opencode_<lang>.jsonl (unique stems: the
transcript area is keyed by the out stem). Usage: run_m61_rr.py [s1 s2]"""
import json, random, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "m59"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_m59 as R
R.OUT = R.WD / "m61"
import run_m61 as M          # a4_gate(model, tag, gate_args)
sys.path.insert(0, str(R.REPO / "benchmark"))
import web_audit as WA

WEB = ("--scaffold", "opencode-v2-web")
RR = R.OUT / "rr"


def out_for(s, model, lang):
    return RR / f"{model}.rr.{s}.opencode_{lang}.jsonl"


def rerun_item(model, lang, job, seed_base, out, deny):
    """One P202 re-run on the loaded instance (run_leg would SKIP: the leg file is already complete). --limit 1: no A4
    receipt needed (its carrier would differ by the deny overlay); M50 and the env check still run inside the probe."""
    if not R.power_ok():
        raise SystemExit("gate FAIL -- ABORT")
    cmd = [str(R.PY), str(R.PROBE), "--model", model, "--items", job["item"].split("/", 1)[1], "--lang", lang,
           "--seed-base", str(seed_base), "--out", str(out), "--chain-total", "88", "--limit", "1", *WEB,
           "--extra-deny-file", str(deny), "--rerun-of", job["session_id"], "--rerun-index", str(job["rerun_index"])]
    R.log(f"RERUN {job['item']} #{job['rerun_index']} deny={len(job['extra_deny'])} patterns -> {out.name}")
    with out.with_suffix(".log").open("a") as lf:
        rc = subprocess.run(cmd, cwd=str(R.REPO), env=R.env_base(), stdout=lf, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, timeout=R.LEG_TIMEOUT_S).returncode
    last = R.rows(out)[-1]
    R.log(f"RERUN END {job['item']} rc={rc} passed={last.get('passed')} rerun_index={last.get('rerun_index')} "
          f"fetches={len(last.get('web_fetches') or [])}")
    if rc != 0:
        raise SystemExit(1)


def audit_and_rerun(model, lang, s, out):
    for rnd in range(3):
        rc = subprocess.run([str(R.PY), str(R.REPO / "benchmark/web_audit.py"), str(out)], cwd=str(R.REPO), env=R.env_base(),
                            stdout=open(out.with_suffix(".audit.log"), "a"), stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, timeout=7200).returncode
        if rc != 0:
            R.log(f"FATAL web_audit rc={rc} on {out.name}")
            raise SystemExit(4)
        jobs = WA.cheats_to_rerun(out)       # raises AuditMissing (fail closed) if any entry is unaudited/stale
        review = [j for j in jobs if j.get("needs_operator")]
        jobs = [j for j in jobs if not j.get("needs_operator")]
        if review:
            R.log(f"CHEAT REVIEW (operator) {out.name}: {[(j['item'], j.get('urls'), j.get('dropped_urls')) for j in review]}")
        R.log(f"AUDIT {out.name} round {rnd}: {len(jobs)} cheat re-run(s) {[ (j['item'], j['rerun_index'], j['urls'][:2]) for j in jobs]}")
        if not jobs:
            return
        for j in jobs:
            deny = out.parent / f"{out.stem}.deny.{j['item'].replace('/', '_')}.{j['rerun_index']}.json"
            deny.write_text(json.dumps(j["extra_deny"]))
            rerun_item(model, lang, j, R.SEEDS[s], out, deny)
    R.log(f"FATAL {out.name}: cheat loop did not settle after 3 audit rounds")
    raise SystemExit(5)


def chain(sessions):
    RR.mkdir(parents=True, exist_ok=True)
    R.log(f"START m61 re-record sessions={sessions} scaffold=opencode-v2-web")
    R.start_router()
    try:
        prev = None
        for s in sessions:
            if prev is not None:
                if not R.unload(prev):
                    raise SystemExit(3)
                prev = None
                R.log(f"session boundary -> fresh load for {s}")
            for model, lang in R.LEGS[s]:
                out = out_for(s, model, lang)
                if prev != model:
                    if prev is not None and not R.unload(prev):
                        raise SystemExit(3)
                    R.load(model)
                    M.a4_gate(model, f"rr_{s}_{model}", WEB)
                    prev = model
                if lang == R.LEGS[s][0][1] and not R.rows(out):
                    R.run_leg(model, lang, random.Random(R.SEEDS[s]).sample(sorted(R.ITEMS[lang]), 5), R.SEEDS[s], out,
                              limit=5, chain_total=88, extra_args=WEB)
                R.run_leg(model, lang, R.ITEMS[lang], R.SEEDS[s], out, chain_total=88, extra_args=WEB)
                audit_and_rerun(model, lang, s, out)
        if prev:
            R.unload(prev)
    finally:
        R.stop_stack()
    R.log("M61 RE-RECORD DONE")


if __name__ == "__main__":
    chain(sys.argv[1:] or ["s1", "s2"])
