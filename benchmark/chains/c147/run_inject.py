"""C147 injected-positive driver (spec docs/specs/c147-tg1-chain-clearance.md section 2, "Driver"). Operator-run, ~30 min.

Lean draft-OFF router, load Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed, A4 gate, three single-item legs (kinds stall,
loop, alloc; a different seeded-random Python item per kind; attempt n uses seed base 1001/2002/3003 and the same
item), `benchmark/m62/inject_verify.py --run <dir>` after each leg (exit 4: re-run that kind on the next seed, up to
three attempts; exit 1: stop), a final suite verdict over the run directory, unload, stack_stop.

Exit: 0 suite verdict PASS; 1 verifier FAIL; 2 driver abort (transport failure, gate, memory); 4 retries exhausted or
suite not cleared. Detached launch: drive_inject.sh.
"""
import argparse
import json
import os
import random
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "benchmark"))
from bench import chain_ops as co  # noqa: E402

KINDS = ("stall", "loop", "alloc")
SEED_BASES = (1001, 2002, 3003)
ITEM_DRAW_SEED = 147          # random.Random(147).sample(sorted(python), 3): the three inject items (one per kind)
MIN_FREE_MB = 4096


def pick_items(names):
    return dict(zip(KINDS, random.Random(ITEM_DRAW_SEED).sample(sorted(names["python"]), 3)))


def build_cmd(py, probe, kind, item, seed, out, receipt):
    return [str(py), str(probe), "--model", co.PICK1, "--items", item, "--lang", "python", "--seed-base", str(seed),
            "--out", str(out), "--scaffold", co.SCAFFOLD, "--expect-items", f"python/{item}",
            "--a4-v2-receipt", str(receipt), "--sampling-profile", "deployed", "--tg1-inject", kind]


def verdict_for(stdout, stem):
    """The verifier prints one line per row; the line naming this attempt decides, else None (fall back to rc)."""
    for line in stdout.splitlines():
        if stem in line:
            for tag, word in (("PASS", "PASS"), ("FAIL", "FAIL"), ("not_observed", "retry"), ("competing_trigger", "retry")):
                if tag in line:
                    return word
    return None


def run_verify(py, verify, out_dir, env=None, timeout=600):
    p = subprocess.run([str(py), str(verify), "--run", str(out_dir)], capture_output=True, text=True, timeout=timeout,
                       stdin=subprocess.DEVNULL, env=env)
    return p.returncode, p.stdout


def main(argv=None, ops=None, log_out=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", default=str(REPO / "benchmark/run_opencode_probe_v2.py"))
    ap.add_argument("--python", default=str(REPO / ".venv-bench/bin/python"))
    ap.add_argument("--verify", default=str(REPO / "benchmark/m62/inject_verify.py"))
    ap.add_argument("--out-dir")
    ap.add_argument("--universe")
    ap.add_argument("--min-free-mb", type=int, default=MIN_FREE_MB)
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    wd = Path(ops.wd) if ops is not None else Path(os.environ["STACK_WORKDIR"])
    out_dir = Path(a.out_dir or wd / "m62/inject")
    out_dir.mkdir(parents=True, exist_ok=True)
    log = co.RunLog(out_dir / "RUNLOG.md", out=log_out)
    if ops is None:
        overlay = os.environ.get("C147_OVERLAY") or str(wd / "c147/overlay_c147_draft_off.yaml")
        ops = co.ChainOps(REPO, wd, overlay, log)
    uni = json.loads(Path(a.universe or REPO / "benchmark/m62/universe.json").read_text())["items"]
    names = {"python": [k.split("/", 1)[1] for k in uni if k.startswith("python/")]}
    items = pick_items(names)
    rc = 2
    try:
        log(f"START inject items={items} seeds={SEED_BASES}")
        ops.ensure_overlay()
        if not ops.power_ok():
            raise co.ChainAbort("power gate FAIL")
        ops.start_router()
        ops.load(co.PICK1)
        receipt = ops.a4_gate(co.PICK1, "inject")
        for kind in KINDS:
            for n, seed in enumerate(SEED_BASES, 1):
                free = ops.free_mem_mb()
                fl = co.in_flight(ops.worker_metrics() or {})
                if free is None or free < a.min_free_mb or fl != 0:
                    raise co.ChainAbort(f"pre-leg check failed: free_mem_mb={free} in_flight={fl}")
                stem = f"{kind}.attempt{n}"
                out = out_dir / f"{stem}.jsonl"
                if out.exists():
                    raise co.ChainAbort(f"stale attempt file {out.name}")
                cmd = build_cmd(a.python, a.probe, kind, items[kind], seed, out, receipt)
                log(f"START {stem} item={items[kind]} seed={seed}: {' '.join(cmd[2:])}")
                with (out_dir / f"{stem}.log").open("ab") as lf:
                    prc = subprocess.Popen(cmd, cwd=str(REPO), env=ops.env_base(), stdout=lf,
                                           stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                           start_new_session=True).wait()
                log(f"END {stem} probe rc={prc}")
                if prc != 0:
                    raise co.ChainAbort(f"probe rc {prc} on {stem} (transport failure aborts)")
                vrc, vout = run_verify(a.python, a.verify, out_dir, ops.env_base())
                for line in vout.splitlines():
                    log("VERIFY " + line)
                word = verdict_for(vout, stem)
                log(f"verifier rc={vrc} verdict for {stem}: {word}")
                if word == "FAIL" or (word is None and vrc == 1):
                    log(f"FAIL on {stem}: stop")
                    rc = 1
                    return rc
                if word == "PASS" or (word is None and vrc == 0):
                    break
                if word == "retry" or (word is None and vrc == 4):
                    if n == len(SEED_BASES):
                        log(f"BUILD FINDING: {kind} not cleared after {n} attempts")
                        rc = 4
                        return rc
                    continue
                raise co.ChainAbort(f"unexpected verifier rc {vrc} on {stem}")
        vrc, vout = run_verify(a.python, a.verify, out_dir, ops.env_base())
        for line in vout.splitlines():
            log("SUITE " + line)
        log(f"SUITE verdict rc={vrc}")
        rc = vrc
        return rc
    except co.ChainAbort as e:
        log(f"INJECT ABORT: {e}")
        rc = e.code
        return rc
    finally:
        try:
            if ops.loaded:
                ops.unload(co.PICK1)
        finally:
            ops.stop_stack()
            log(f"DONE rc={rc}")


if __name__ == "__main__":
    sys.exit(main())
