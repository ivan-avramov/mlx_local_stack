"""P426 Wave-1 sequencer (`docs/specs/p426-fable-mtp-recert.md` §3–§4): 10 smokes (per axis OFF then ON), then 20 legs (per axis
block 1 OFF → ON, block 2 ON → OFF); each leg one `bench.p426_leg` run from the frozen worktree; ≥ 600 s idle before every leg;
stop at the first leg that is not VALID.

  .venv-bench/bin/python -m bench.p426_wave1 --build s --stack-root <frozen> --main-root <main checkout> \
      --workdir $STACK_WORKDIR --registry-on <overlay> --out <dir>
  .venv-bench/bin/python -m bench.p426_wave1 --build s2 --stack-root-off <WT_off> --stack-root-on <WT_on> \
      --main-root <main checkout> --workdir $STACK_WORKDIR --out <dir>            (T3 §4: arms as committed worktrees)

`--build` is required: the label names the serving build (`s` = S, historical; `s2` = S′) and every tune, leg name, receipt,
dossier and `--out` follows from it. Under a label other than `s` there is no overlay: each leg runs from its arm's worktree and
serves that worktree's committed registry; the record `frozen.<label>.json`, the expected build, both trees and the restore
diff between them are validated before any run file is harvested.

After every launched leg (VALID or not) its evidence is harvested into the main checkout (P437, `bench.p426_harvest`) before the
idle gap; a harvest failure stops the run. Resume: a leg with a VALID receipt AND a harvested dossier is skipped; any other
receipt (published or `.refused-*`), or a VALID one never harvested, stops the run before a launch — a rerun is an operator
decision. `<out>/PAUSE` holds the run at the next leg boundary (test windows; harvesting is already done); the idle gap restarts
when it is removed. A leg that overruns its timeout is never killed: the run stops and leaves it to the operator.
"""

import argparse
import getpass
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from bench import p426_plan
from bench.p426_harvest import HarvestError, Scrub, harvest_run_files, wave1_dir

AXES = ("math500", "cjudge", "vision", "reasoning", "m1")
ARMS = ("off", "on")
IDLE_S = 600.0
POLL_S = 30.0
LEG_TIMEOUT_S = 6 * 3600 + 5400  # p426_leg's driver timeout + router start / load / teardown headroom


class LegOverrun(RuntimeError):
    pass


def schedule(axes=AXES):
    unknown = [a for a in axes if a not in AXES]
    if unknown:
        raise ValueError(f"unknown axis {unknown}")
    axes = [a for a in AXES if a in axes]  # P452: the plan order, filtered
    legs = [(axis, arm, "smoke") for axis in axes for arm in ARMS]
    for axis in axes:
        legs += [(axis, "off", 1), (axis, "on", 1), (axis, "on", 2), (axis, "off", 2)]
    return legs


def leg_name(axis, arm, sel, build="s"):
    return p426_plan.leg_name(axis, arm, sel, build)


def leg_argv(stack_root, workdir, registry_on, receipt_dir, axis, arm, sel, build="s", stack_root_off=None):
    """Under `s` byte-identical to S's argv. Under a label: `stack_root` is the ARM's worktree, no `--registry-on`, an ON leg
    also names the OFF worktree."""
    select = ["--smoke"] if sel == "smoke" else ["--block", str(sel)]
    argv = [str(Path(stack_root) / ".venv-bench" / "bin" / "python"), "-m", "bench.p426_leg", "--axis", axis, "--arm", arm,
            *select, "--stack-root", str(stack_root), "--workdir", str(workdir)]
    if p426_plan.is_s(build):
        return [*argv, "--registry-on", str(registry_on), "--receipt-dir", str(receipt_dir)]
    return [*argv, "--receipt-dir", str(receipt_dir), "--build", build,
            *(["--stack-root-off", str(stack_root_off)] if arm == "on" else [])]


def claim_out(out, build):
    """T3 §4: the sequencer's `--out` belongs to one label. A marker naming another label refuses; under a label a first start
    writes it, and an `--out` holding receipts or a `sequence.log` without a marker refuses (an S run is never adopted)."""
    out = Path(out)
    marker = out / ".build"
    if marker.exists():
        have = marker.read_text().strip()
        return None if have == build else f"--out {out} belongs to build {have!r}, not {build!r}"
    if p426_plan.is_s(build):
        return None
    receipts = out / "receipts"
    if (out / "sequence.log").exists() or (receipts.is_dir() and any(receipts.glob("*.receipt.json"))):
        return f"--out {out} holds receipts or a sequence.log but no .build marker (another run's directory)"
    out.mkdir(parents=True, exist_ok=True)
    marker.write_text(build + "\n")
    return None


def label_problems(build, workdir, off_root, on_root):
    """The record of a label against its expected build and BOTH live worktrees (both trees clean, both heads, both venvs and
    locks) and the restore diff between them — everything the sequencer checks before it harvests a run file or launches."""
    path = p426_plan.frozen_path(workdir, build)
    if not path.is_file():
        return [f"frozen record {path} is missing"]
    try:
        record = json.loads(path.read_text())
    except ValueError as exc:
        return [f"{path.name}: not JSON ({exc})"]
    problems = p426_plan.record_problems(record, build)
    if problems:
        return problems
    for arm, root in (("off", off_root), ("on", on_root)):
        problems += p426_plan.arm_problems(record, arm, root)
    return problems + p426_plan.restore_diff_problems(off_root, on_root, p426_plan.p426_ids.ENTRY)


def receipt_verdict(receipt_dir, name):
    """None when the leg has no receipt; otherwise the worst verdict over its published and refused receipts."""
    d = Path(receipt_dir)
    paths = [d / f"{name}.receipt.json", *sorted(d.glob(f"{name}.refused-*.receipt.json"))]
    verdicts = []
    for p in paths:
        if not p.exists():
            continue
        try:
            verdicts.append(json.loads(p.read_text()).get("verdict") or "UNREADABLE")
        except (OSError, ValueError):
            verdicts.append("UNREADABLE")
    if not verdicts:
        return None
    bad = [v for v in verdicts if v != "VALID"]
    return bad[0] if bad else "VALID"


def _idle(sleep, clock, paused, log, idle_s):
    since = clock()
    held = False
    while True:
        if paused():
            if not held:
                log("PAUSE: holding at the leg boundary")
                held = True
            sleep(POLL_S)
            since = clock()  # the gap restarts after the test window
            continue
        if held:
            log("PAUSE removed: idle gap restarts")
            held = False
        remaining = idle_s - (clock() - since)
        if remaining <= 0:
            return
        sleep(min(remaining, POLL_S))


def run(legs, *, launch, read_verdict, sleep, clock, paused, log, harvest, harvested, idle_s=IDLE_S, build="s"):
    """0 = every leg VALID; 1 = stopped on a leg (or an existing receipt) that is not VALID; 3 = a leg overran;
    4 = a harvest failed."""
    for leg in legs:
        name = leg_name(*leg, build=build)
        before = read_verdict(name)
        if before == "VALID" and harvested(name):
            log(f"{name}: VALID receipt exists, harvested, skipped")
            continue
        if before == "VALID":
            log(f"STOP {name}: VALID receipt but no harvested dossier (the evidence is not in the repo)")
            return 1
        if before is not None:
            log(f"STOP {name}: existing receipt {before} (a rerun is an operator decision)")
            return 1
        _idle(sleep, clock, paused, log, idle_s)
        log(f"START {name}")
        try:
            rc = launch(leg)
        except LegOverrun as exc:
            log(f"STOP {name}: {exc}")
            return 3
        verdict = read_verdict(name)
        log(f"END {name}: rc {rc} verdict {verdict}")
        try:
            harvest(leg)
        except Exception as exc:  # noqa: BLE001 — evidence that cannot reach the repo stops the run
            log(f"STOP {name}: HARVEST failed: {type(exc).__name__}: {exc}")
            return 4
        log(f"HARVESTED {name}")
        if verdict != "VALID" or rc != 0:
            log(f"STOP {name}: not VALID (rc {rc}, verdict {verdict})")
            return 1
    log("DONE: every leg VALID")
    return 0


def wait_leg(proc, timeout_s):
    try:
        return proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        raise LegOverrun(f"leg PID {proc.pid} still running after {timeout_s:.0f} s — not killed") from None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", help="the build label (required): s = S, s2 = S′; grammar ^[a-z][a-z0-9]{0,7}$")
    ap.add_argument("--stack-root", help="build s: the frozen worktree")
    ap.add_argument("--stack-root-off", help="a label: the committed OFF worktree")
    ap.add_argument("--stack-root-on", help="a label: the ON worktree (the OFF head + the restore commit)")
    ap.add_argument("--main-root", required=True, help="the main checkout the evidence is harvested into (P437)")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--registry-on", help="build s: the ON overlay (retired under a label)")
    ap.add_argument("--out", required=True, help="sequence log, leg stdout and receipts/")
    ap.add_argument("--idle-s", type=float, default=IDLE_S)
    ap.add_argument("--axes", default=",".join(AXES), help="P452: comma list, run in the plan order")
    args = ap.parse_args(argv)
    configured = os.environ.get("STACK_WORKDIR")
    if not configured or Path(configured).resolve() != Path(args.workdir).resolve():
        print(f"[p426_wave1] --workdir {args.workdir} is not $STACK_WORKDIR ({configured})", file=sys.stderr)
        return 2
    if args.idle_s < IDLE_S:
        print(f"[p426_wave1] --idle-s {args.idle_s} < {IDLE_S} (plan §3)", file=sys.stderr)
        return 2
    if args.build is None:
        print("[p426_wave1] --build <label> is required (s = S, s2 = S′)", file=sys.stderr)
        return 2
    try:
        build = p426_plan.check_build(args.build)
    except ValueError as exc:
        print(f"[p426_wave1] {exc}", file=sys.stderr)
        return 2
    label = not p426_plan.is_s(build)
    wanted, refused = (("stack_root_off", "stack_root_on"), ("stack_root", "registry_on")) if label else (
        ("stack_root", "registry_on"), ("stack_root_off", "stack_root_on"))
    missing = [f"--{k.replace('_', '-')}" for k in wanted if not getattr(args, k)]
    given = [f"--{k.replace('_', '-')}" for k in refused if getattr(args, k)]
    if missing or given:
        print(f"[p426_wave1] build {build}: missing {missing}, not allowed {given}", file=sys.stderr)
        return 2
    from bench import p426_harvest

    roots = ({"off": Path(args.stack_root_off).resolve(), "on": Path(args.stack_root_on).resolve()} if label
             else {"off": Path(args.stack_root).resolve(), "on": Path(args.stack_root).resolve()})
    root, out = roots["off"], Path(args.out).resolve()
    main_root, workdir = Path(args.main_root).resolve(), Path(args.workdir).resolve()
    if main_root in roots.values():
        print("[p426_wave1] --main-root must be the main checkout, not a frozen worktree", file=sys.stderr)
        return 2
    if label and roots["off"] == roots["on"]:
        print("[p426_wave1] --stack-root-off and --stack-root-on are one directory (the arms are two worktrees)", file=sys.stderr)
        return 2
    claimed = claim_out(out, build)
    if claimed:
        print(f"[p426_wave1] {claimed}", file=sys.stderr)
        return 2
    receipts = out / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    frozen_json = p426_plan.frozen_path(workdir, build)
    host = socket.gethostname()
    scrub = Scrub(workdir=workdir, repo=main_root, home=Path.home(), user=getpass.getuser(),
                  hosts=tuple({host, host.split(".")[0]}))
    server_logs = {arm: r / "logs" / "mlx_vlm.log" for arm, r in roots.items()}
    offsets = {}

    def log(msg):
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        with (out / "sequence.log").open("a") as f:
            f.write(line + "\n")
        print(line, flush=True)

    def launch(leg):
        name, arm = leg_name(*leg, build=build), leg[1]
        argv = leg_argv(roots[arm], args.workdir, args.registry_on, receipts, *leg, build=build, stack_root_off=roots["off"])
        log("argv " + json.dumps(argv))
        server_log = server_logs[arm]
        offsets[name] = server_log.stat().st_size if server_log.exists() else 0
        with (out / f"{name}.stdout").open("ab") as f:
            proc = subprocess.Popen(argv, cwd=roots[arm] / "benchmark", stdin=subprocess.DEVNULL, stdout=f,
                                    stderr=subprocess.STDOUT)
            log(f"leg PID {proc.pid}")
            return wait_leg(proc, LEG_TIMEOUT_S)

    def harvest(leg):
        name = leg_name(*leg, build=build)
        axis, arm, sel = leg
        frozen = json.loads(frozen_json.read_text())
        plan = p426_plan.plan_leg(roots[arm], axis, arm, None if sel == "smoke" else sel, smoke=sel == "smoke", workdir=workdir,
                                  reviewed_head=frozen.get("mlx_vlm"), production_ref=frozen.get("production_ref"), build=build)
        server_log = server_logs[arm]
        data = server_log.read_bytes() if server_log.exists() else b""
        start = offsets.get(name, 0)
        if len(data) < start:
            log(f"{name}: server log shrank ({len(data)} < {start}); the whole file is the slice")
            start = 0
        stdout = out / f"{name}.stdout"
        p426_harvest.harvest(name, plan, main_root=main_root, receipts=receipts, log_slice=data[start:], scrub=scrub,
                             stdout=stdout.read_bytes() if stdout.exists() else b"", build=build)
        harvest_run_files([out / "sequence.log"], main_root=main_root, scrub=scrub, overwrite=("sequence.log",), build=build)

    if label:
        log(f"sequencer PID {os.getpid()} build {build} stack_root_off {roots['off']} stack_root_on {roots['on']} "
            f"main_root {main_root}")
    else:
        log(f"sequencer PID {os.getpid()} stack_root {root} main_root {main_root} registry_on {args.registry_on}")
    if label:  # the record, both trees and the restore diff are validated BEFORE any run file is harvested
        problems = label_problems(build, workdir, roots["off"], roots["on"])
        if problems:
            log("STOP: build " + build + " refused, nothing launched: " + "; ".join(problems)[:1500])
            return 1
    try:
        harvest_run_files([frozen_json] + ([] if label else [Path(args.registry_on)]), main_root=main_root, scrub=scrub, build=build)
    except (OSError, HarvestError) as exc:
        log(f"STOP: run files not harvested: {type(exc).__name__}: {exc}")
        return 4
    try:
        legs = schedule(axes=tuple(a for a in args.axes.split(",") if a))
    except ValueError as exc:
        log(f"STOP: {exc}")
        return 2
    log(f"axes {','.join(a for a in AXES if a in args.axes.split(','))}: {len(legs)} legs")
    return run(legs, launch=launch, read_verdict=lambda n: receipt_verdict(receipts, n), sleep=time.sleep,
               clock=time.monotonic, paused=lambda: (out / "PAUSE").exists(), log=log, idle_s=args.idle_s,
               harvest=harvest, build=build,
               harvested=lambda n: (main_root / wave1_dir(build) / n / "SCRUB_MANIFEST.json").exists())


if __name__ == "__main__":
    sys.exit(main())
