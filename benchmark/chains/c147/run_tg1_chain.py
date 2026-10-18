"""C147 tg1 chain runner entry (spec docs/specs/c147-tg1-chain-clearance.md section 3; P371 phase 3a: the chain itself is
`bench/chain_core.py`, this file is the CLI, the out-root rules (P340, ON / OFF predictor separation) and the tg1
`ChainConfig`).

  run_tg1_chain.py pilot                      one block: pick 1 python, first 5 seeded-random items, s1 seed
  run_tg1_chain.py chain [s1 s2 reload] --probe-code-sha <sha>
  run_tg1_chain.py chain ... --predictor mtp  M63 ON arm (spec docs/specs/m63-mtp-on-tg1-arm.md): out-root m63/
  run_tg1_chain.py chain ... --campaign-core <tag>   C179: refuse unless the core closures equal the closures at <tag>

P311-lite: the probe is `benchmark/run_tg1_probe.py` (generation only; `--print-identity` prints its closure identity).
The shared generation composite is pinned at the first manifest (or `--generation-sha`), one arm identity per
(model, predictor) is frozen at that arm's first manifest, and the chain's own lifecycle code (this entry's import closure,
the serialized ChainConfig, the A4 gate, the launchers) is frozen in chain.json at creation and verified before every launch,
barrier, validation, resume and at exit; drift aborts with rc 2 and never rewrites the frozen record.

P371 A8 / P376: every pilot / full invocation writes its own immutable rows file `<stem>.L<leg>.<phase>.a<n>.jsonl`; the full
invocation runs the cell minus the pilot's validated slots. Scored slots come only from `bench.chain_rows`.

Exit codes: 0 done, 2 chain abort (listing printed, nothing killed), 3 STOP latch honoured, 1 unexpected error.
Cancellation is cooperative only: the idle predicate (chain_ops.IdlePredicate) or `<out-root>/STOP`.
Detached launch: drive_chain.sh. Tests inject `ops` (chain_ops.ChainOps-shaped), `timers` and `campaign`.
"""
import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "benchmark"))
from bench import campaign_core  # noqa: E402
from bench import chain_core as core  # noqa: E402
from bench import chain_ops as co  # noqa: E402
from bench import datefreeze  # noqa: E402
from bench import run_config as rc  # noqa: E402
from bench import schedules  # noqa: E402

Timers, RecordInvalid, Stopped, Refused = core.Timers, core.RecordInvalid, core.Stopped, core.Refused
Heartbeat, dir_bytes, receipt_from_manifest, quantile = core.Heartbeat, core.dir_bytes, core.receipt_from_manifest, core.quantile
PICK1, PICK2 = co.PICK1, co.PICK2
SCAFFOLD = co.SCAFFOLD
SEEDS = {"s1": 1001, "s2": 2002, "reload": 1001}
LEGS = {"s1": [(PICK1, "python"), (PICK1, "go"), (PICK2, "python"), (PICK2, "go")],
        "s2": [(PICK2, "python"), (PICK2, "go"), (PICK1, "python"), (PICK1, "go")],
        "reload": [(PICK1, "python")]}
PRED_S = core.PRED_S
PILOT_N = core.PILOT_N
SMOKE_PILOT_N, SMOKE_FULL_N, SMOKE_ARM_IDLE_S = core.SMOKE_PILOT_N, core.SMOKE_FULL_N, core.SMOKE_ARM_IDLE_S

# the chain's own lifecycle (plan 5, R15): this entry's static import closure + the serialized ChainConfig + the A4 gate +
# the launchers. `runner` is this file; the closure members (chain_core, chain_rows, schedules, run_config, web_evidence,
# campaign_core ...) are keyed by their repo-relative path.
NAMED_LIFECYCLE = {"runner": "benchmark/chains/c147/run_tg1_chain.py", "chain_ops": "benchmark/bench/chain_ops.py",
                   "launcher": "benchmark/chains/c147/drive_chain.sh",
                   "launch_tg1": "benchmark/chains/c147/launchers/launch_tg1.sh"}
# C179: the campaign core = the probe entry's closure (probe_code_sha256 recipe: closure + the generation data files) and
# this entry's closure. Equal to `tg1_runner.GENERATION_DATA` (tested).
CORE_SPECS = dict(probe_entry="benchmark/run_tg1_probe.py",
                  probe_data=("benchmark/opencode_plugins/toolbounds.js", "benchmark/opencode_plugins/noretry.js",
                              "benchmark/opencode_plugins/datefreeze.js", "benchmark/opencode_bench_v2_web_tg1.json"),
                  chain_entry="benchmark/chains/c147/run_tg1_chain.py", chain_data=())


def probe_entry(a):
    """F7: the resolved probe entry (repo-relative; `--probe` may override the default)."""
    given = getattr(a, "probe", None)
    return core.probe_rel(REPO, given) if given else CORE_SPECS["probe_entry"]


def core_specs(a):
    """The campaign core specs of THIS invocation: `CORE_SPECS` with the resolved probe entry."""
    return dict(CORE_SPECS, probe_entry=probe_entry(a))


def lifecycle_files(repo):
    return core.lifecycle_member_files(repo, NAMED_LIFECYCLE["runner"], NAMED_LIFECYCLE)


def tg1_config(a):
    """The tg1 `ChainConfig` (plan 3.2): abort_restart / restart_load, no arm switches, no contract artifacts. Run
    selection (`pilot` / `chain`, the session list, `--smoke`) is NOT part of it, so a pilot and the chain after it share
    one frozen record; the predictor is (ON and OFF never share an out-root)."""
    predictor = getattr(a, "predictor", "off")
    return rc.ChainConfig(
        config_id="tg1",
        arms=(rc.ArmBinding(arm="oc", probe=probe_entry(a), label=SCAFFOLD, arm_spec="oc",
                            probe_data=CORE_SPECS["probe_data"]),),
        schedule={"builder": "tg1", "params": dict(seeds=SEEDS, legs={k: [list(x) for x in v] for k, v in LEGS.items()},
                                                   pilot_n=PILOT_N, smoke_pilot_n=SMOKE_PILOT_N,
                                                   smoke_full_n=SMOKE_FULL_N)},
        out_root_family="m63" if predictor == "mtp" else "c147", predictor=predictor, arm_switch_ops=(),
        transport_policy="abort_restart", resume_policy="restart_load", snapshot_complete_required=False,
        contract_artifacts=())


class Chain(core.Chain):
    """The tg1 chain with the pre-P371 constructor (`Chain(args, ops, timers, log, names, out_root, lifecycle_files)`)."""

    def __init__(self, args, ops, timers, log, names, out_root, lifecycle=None, campaign=None):
        super().__init__(tg1_config(args), args, ops, timers, log, repo=REPO, out_root=out_root, names=names,
                         lifecycle_files=lifecycle if lifecycle else lifecycle_files(REPO),
                         campaign=campaign if campaign is not None else campaign_core.Campaign(REPO, **core_specs(args)))


# --------------------------------------------------------------------------- schedule
def load_universe(path=None):
    import json
    d = json.loads(Path(path or REPO / "benchmark/m62/universe.json").read_text())["items"]
    names = {"python": [], "go": []}
    for k in d:
        lang, name = k.split("/", 1)
        names[lang].append(name)
    return {k: sorted(v) for k, v in names.items()}


def schedule(mode, sessions, names, out_root, smoke=False, predictor="off"):
    """List of blocks: {session, model, seed_base, legs}. A block = one model within one session (both languages). Thin
    wrapper over `schedules.tg1`; each leg also carries its pre-P371 shared `out` path (informational)."""
    sched = schedules.tg1(mode, sessions, names, smoke=smoke, predictor=predictor)
    return [dict(session=b["session"], model=b["model"], seed_base=b["seed_base"], pilot_only=b["pilot_only"],
                 legs=[dict(leg, out=str(Path(out_root) / b["session"] / (leg["stem"] + ".jsonl"))) for leg in b["legs"]])
            for b in sched["blocks"]]


def steps_for(block, idx):
    """The PRE-P371 steps of leg `idx`: a pilot, then (first leg, pilot != cell) a full step over the WHOLE cell; later legs
    one full step. Kept for the A14 baseline mapping and tests: the chain itself runs the disjoint `invocations`."""
    leg = block["legs"][idx]
    pilot = dict(kind="pilot", names=leg["pilot_names"], limit=len(leg["pilot_names"]))
    full = dict(kind="full", names=leg["full_names"], limit=None)
    if block.get("pilot_only"):
        return [pilot]
    if idx > 0:
        return [full]
    return [pilot] if leg["pilot_names"] == leg["full_names"] else [pilot, full]


def build_cmd(py, probe, leg, step, receipt, cancel, ack, universe=None, frozen=None, out=None, attempt=None,
              rerun_index=None):
    return core.build_cmd(py, probe, leg, step, receipt, cancel, ack, scaffold=SCAFFOLD, universe=universe, frozen=frozen,
                          out=out, attempt=attempt, rerun_index=rerun_index)


# --------------------------------------------------------------------------- entry
def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["pilot", "chain"])
    ap.add_argument("sessions", nargs="*")
    ap.add_argument("--pred-s", action="append", default=[], metavar="LANG:MODEL=SECONDS")
    ap.add_argument("--arm-idle-s", type=float, default=None)
    ap.add_argument("--smoke", action="store_true",
                    help="P279 rehearsal: 1-item pilot + 2-item legs, 60 s arm idle, own out-root (chain mode only)")
    ap.add_argument("--probe-code-sha")
    ap.add_argument("--generation-sha", help="optional: pin the generation composite (generation_identity_sha256, "
                    "64 hex) up front; otherwise it is pinned from the first manifest")
    ap.add_argument("--predictor", choices=["off", "mtp"], default="off",
                    help="M63: mtp = the shipped MTP overlay, own out-root $STACK_WORKDIR/m63[-smoke]")
    ap.add_argument("--out-root")
    ap.add_argument("--probe", default=str(REPO / "benchmark/run_tg1_probe.py"))
    ap.add_argument("--python", default=str(REPO / ".venv-bench/bin/python"))
    ap.add_argument("--universe")
    ap.add_argument("--frozen-prompt-date", default=None, metavar="'Www Mmm DD YYYY'",
                    help="P364: the date opencode shows the model, frozen for the epoch (a new epoch states it or takes "
                         "--frozen-date-from; never defaulted to today; a resumed chain keeps its recorded date)")
    ap.add_argument("--frozen-date-from", default=None, metavar="CHAIN_JSON",
                    help="P364: take the frozen date from a reference epoch's chain.json (cross-day reference reuse)")
    ap.add_argument("--policy-sha", default=None,
                    help="P362: an ASSERTION of scaffold_policy_sha256 (64 hex); the expected value is derived from the "
                         "probe's --print-identity at chain start and frozen in chain.json")
    ap.add_argument("--campaign-core", default=None, metavar="TAG_OR_COMMIT",
                    help="C179 / P377: the campaign's frozen core. The chain refuses unless the probe and chain entry "
                         "closures equal their closures at this git tag / commit (at creation, every launch, resume and "
                         "exit); recorded in chain.json artifacts.campaign_core")
    a = ap.parse_args(argv)
    if a.policy_sha is not None and not co.HEX64.match(a.policy_sha):
        ap.error("--policy-sha must be 64 lowercase hex")
    if a.frozen_prompt_date is not None and not datefreeze.valid(a.frozen_prompt_date):
        ap.error("--frozen-prompt-date must be 'Www Mmm DD YYYY' (e.g. 'Sat Oct 17 2026')")
    if a.generation_sha is not None and not co.HEX64.match(a.generation_sha):
        ap.error("--generation-sha must be 64 lowercase hex")
    if a.campaign_core is not None and not a.campaign_core.strip():
        ap.error("--campaign-core must name a git tag or commit")
    if a.smoke and a.mode != "chain":
        ap.error("--smoke is for chain mode")
    if a.arm_idle_s is None:
        a.arm_idle_s = SMOKE_ARM_IDLE_S if a.smoke else 600.0
    if a.mode == "chain":
        if not a.probe_code_sha:
            ap.error("--probe-code-sha is required for chain")
        a.sessions = a.sessions or ["s1", "s2", "reload"]
        bad = [s for s in a.sessions if s not in LEGS]
        if bad:
            ap.error(f"unknown session {bad}")
    return a


def resolve_out_root(a, wd):
    """`$STACK_WORKDIR/c147` for the real chain, `$STACK_WORKDIR/c147-smoke` for a smoke rehearsal; a smoke run is
    refused inside the real chain directory. M63 `--predictor mtp`: `m63` / `m63-smoke`; ON and OFF never share
    a directory."""
    on = getattr(a, "predictor", "off") == "mtp"
    base = "m63" if on else "c147"
    root = Path(a.out_root) if a.out_root else Path(wd) / (base + "-smoke" if a.smoke else base)
    root = root.expanduser().absolute()       # P340 review: subprocesses run with cwd=REPO; never a relative root
    if a.smoke and root.resolve() == (Path(wd) / base).resolve():
        raise Refused("REFUSED: --smoke must not write into the real chain directory")
    if inside_other_arm(root, wd, on):
        raise Refused(f"REFUSED: predictor {'mtp' if on else 'off'} must not write into {root}")
    return root


def inside_other_arm(path, wd, on):
    """M63: True when `path` (symlinks resolved) is, or lies under, a directory of the other predictor arm."""
    p = Path(path).resolve()
    for d in (("c147", "c147-smoke") if on else ("m63", "m63-smoke")):
        other = (Path(wd) / d).resolve()
        if p == other or other in p.parents:
            return True
    return False


def make_ops(predictor, wd, out_root, overlay, log):
    """M63: the ON arm keeps its router TMPDIR and A4 logs under its out-root. P340: so does an OFF arm whose out-root
    is not the default `$STACK_WORKDIR/c147` (it used to write into P223's c147/ dir); the default OFF chain is unchanged."""
    wd, out_root = Path(wd), Path(out_root)
    if predictor == "mtp":
        return co.ChainOps(REPO, wd, overlay, log, predictor="mtp", out_root=out_root)
    if out_root.resolve() != (wd / "c147").resolve():
        return co.ChainOps(REPO, wd, overlay, log, out_root=out_root)
    return co.ChainOps(REPO, wd, overlay, log)


def main(argv=None, ops=None, timers=None, log_out=None, lifecycle_files=None, campaign=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    wd = Path(ops.wd) if ops is not None else Path(os.environ["STACK_WORKDIR"])
    out_root = resolve_out_root(a, wd)
    on = a.predictor == "mtp"
    if ops is None:
        overlay = os.environ.get("C147_OVERLAY") or str(
            out_root / "overlay_m63_mtp.yaml" if on else wd / "c147/overlay_c147_draft_off.yaml")
        if inside_other_arm(overlay, wd, on):       # refused before anything is created (M6)
            raise Refused(f"REFUSED: predictor {a.predictor} overlay {overlay} lies in the other arm's directory")
    out_root.mkdir(parents=True, exist_ok=True)
    log = co.RunLog(out_root / "RUNLOG.md", out=log_out)
    if ops is None:
        ops = make_ops(a.predictor, wd, out_root, overlay, log)
    chain = Chain(a, ops, timers or Timers(), log, load_universe(a.universe), out_root, lifecycle_files, campaign)
    try:
        return chain.run()
    except BaseException:
        chain.rc = 1
        chain.write_json("crashed")
        raise


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as e:
        print(e.args[0], file=sys.stderr)
        sys.exit(2)
