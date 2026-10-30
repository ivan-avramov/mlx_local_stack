"""C147 tg1 chain runner entry (spec docs/specs/c147-tg1-chain-clearance.md section 3; P371 phase 3a: the chain itself is
`bench/chain_core.py`, this file is the CLI, the out-root rules (P340, ON / OFF predictor separation) and the tg1
`ChainConfig`).

  run_tg1_chain.py pilot --models a[,b...]    one block: the first model's python, first 5 seeded-random items, s1 seed
  run_tg1_chain.py chain [s1 s2 reload] --models a[,b...] --probe-code-sha <sha>
  run_tg1_chain.py chain ... --predictor mtp  M63 ON arm (spec docs/specs/m63-mtp-on-tg1-arm.md): out-root m63/
  run_tg1_chain.py chain ... --campaign-core <tag>   C179: refuse unless the core closures equal the closures at <tag>
  run_tg1_chain.py {pilot|chain <session>} --p426 ...   B2 (docs/specs/p426-b2-tg1-wave2.md): one model, one leg, a fresh out-root

C221 (every mode): `--models` is REQUIRED (each a `models:` entry of the served registry; s1 runs them in the given order, s2
reversed, reload the first); the worktree's committed `main_models.yaml` is served verbatim (no overlay is generated; a
`C147_OVERLAY` environment override is refused) and `--predictor` ASSERTS the entries' committed state (mtp: all three C177 keys,
off: none).

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
import re
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
SCAFFOLD = co.SCAFFOLD
SEEDS = {"s1": 1001, "s2": 2002, "reload": 1001}
LANGS = ("python", "go")
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
    one frozen record; the predictor is (ON and OFF never share an out-root). C221: it records the `--models` list and the
    generic prediction default. `--p426` selects the distinct `tg1-p426` config (one model, the seeded schedule, spec 2)."""
    predictor = getattr(a, "predictor", "off")
    models, p426 = list(a.models), bool(getattr(a, "p426", False))
    params = dict(seeds=SEEDS, legs={k: [list(x) for x in v] for k, v in schedules.tg1_legs_table(models, LANGS, p426).items()},
                  pilot_n=PILOT_N, smoke_pilot_n=SMOKE_PILOT_N, smoke_full_n=SMOKE_FULL_N, models=models,
                  generic_pred_s=core.GENERIC_PRED_S)       # spec 2 / 16.1: recorded in chain.json via the ChainConfig
    if p426:
        params["p426"] = True
    return rc.ChainConfig(
        config_id=rc.P426_CONFIG_ID if p426 else "tg1",
        arms=(rc.ArmBinding(arm="oc", probe=probe_entry(a), label=SCAFFOLD, arm_spec="oc",
                            probe_data=CORE_SPECS["probe_data"]),),
        schedule={"builder": "tg1", "params": params},
        out_root_family="m63" if predictor == "mtp" else "c147", predictor=predictor, arm_switch_ops=(),
        transport_policy="p426_continue" if p426 else "abort_restart", resume_policy="restart_load", snapshot_complete_required=False,
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


def schedule(mode, sessions, names, out_root, *, models, smoke=False, predictor="off", p426=False):
    """List of blocks: {session, model, seed_base, legs}. A block = one model within one session (both languages). Thin
    wrapper over `schedules.tg1` (`models` = the required `--models` list); each leg also carries its pre-P371 shared `out`
    path (informational)."""
    sched = schedules.tg1(mode, sessions, names, picks=tuple(models), smoke=smoke, predictor=predictor, p426=p426)
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
              rerun_index=None, evidence=None):
    return core.build_cmd(py, probe, leg, step, receipt, cancel, ack, scaffold=SCAFFOLD, universe=universe, frozen=frozen,
                          out=out, attempt=attempt, rerun_index=rerun_index, evidence=evidence)


# --------------------------------------------------------------------------- entry
def parse_models(ap, a):
    """C221 / B2 6.1: `--models` -> a list; empty names and duplicates are refused (usage error, exit 2)."""
    names = a.models.split(",")
    if any(not n.strip() or n != n.strip() for n in names):
        ap.error("--models must be comma-separated model names, none empty or padded with whitespace")
    if len(set(names)) != len(names):
        ap.error("--models must not repeat a model")
    a.models = names


def check_p426(ap, a):
    """B2 spec 2: the refusals of `--p426` that need only the arguments (the out-root, environment, registry and record checks
    run in `main`, before anything is written)."""
    excluded = [flag for flag, given in (("--smoke", a.smoke), ("--pred-s", a.pred_s), ("--generation-sha", a.generation_sha),
                                         ("--frozen-date-from", a.frozen_date_from)) if given]
    if excluded:
        ap.error(f"--p426 refuses {', '.join(excluded)}")
    missing = [flag for flag, given in (("--out-root", a.out_root), ("--campaign-core", a.campaign_core),
                                        ("--frozen-prompt-date", a.frozen_prompt_date), ("--probe-code-sha", a.probe_code_sha),
                                        ("--policy-sha", a.policy_sha), ("--frozen-record", a.frozen_record)) if not given]
    if missing:
        ap.error(f"--p426 requires {', '.join(missing)}")
    if len(a.models) != 1:
        ap.error("--models: --p426 runs exactly one model")
    if a.mode == "chain" and len(a.sessions) != 1:
        ap.error("--p426 chain runs exactly one session leg (s1, s2 or reload)")
    if a.mode == "makeup" and a.sessions:
        ap.error("--p426 makeup takes no session (the occurrences file is its plan)")
    if a.mode == "makeup" and not a.occurrences:
        ap.error("--p426 makeup requires --occurrences")
    if a.rehearsal and a.mode != "chain":
        ap.error("--rehearsal is for chain mode")


ATTEMPT_NAME = re.compile(r"^.+\.a[1-9][0-9]*$")


def check_frozen_record(a):
    """B2 spec 16.1: `--frozen-record` is read once at entry; its `kind` must fit the mode (`--rehearsal` -> p426_rehearsal,
    `pilot` -> p426_v8_base, `chain` -> p426_timeout_amendment, whose `v8_base_sha256` must equal the self-hash of the
    `v8_base.json` beside it); a missing file, a bad self-hash, a wrong kind or a mismatched amendment refuses. The chain
    re-reads it through the same `p426_record.load` before every invocation."""
    from bench import p426_record
    try:
        return p426_record.load(a.frozen_record, mode=a.mode, rehearsal=a.rehearsal)
    except p426_record.RecordError as e:
        raise Refused(f"REFUSED: --frozen-record {e}") from None


def check_pair_receipt(path):
    """B2 spec 6.5: the first leg's receipt must exist, parse and verify its self-hash, or the leg is refused before anything is
    written. Only the shape is checked here; the comparison runs in the chain after load."""
    import json
    from bench import p426_hooks
    try:
        doc = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        raise Refused(f"REFUSED: --pair-receipt {Path(path).name} is missing, unreadable or not JSON") from None
    if not p426_hooks.sealed_ok(doc):
        raise Refused(f"REFUSED: --pair-receipt {Path(path).name}: its sha256 does not verify (not an arm-equality receipt)")


class RefusingParser(argparse.ArgumentParser):
    """Spec 16: every refusal, argparse's own included, prints one stderr line `REFUSED: <reason>` and exits 2."""

    def error(self, message):
        print(f"REFUSED: {message}", file=sys.stderr)
        sys.exit(2)


def parse_args(argv):
    ap = RefusingParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["pilot", "chain", "makeup"])
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
    ap.add_argument("--models", required=True, metavar="NAME[,NAME...]",
                    help="C221: the models to run (>= 1, comma-separated, no duplicates, each a `models:` entry of the served "
                         "committed registry); s1 runs them in this order, s2 reversed, reload the first")
    ap.add_argument("--p426", action="store_true",
                    help="B2 (docs/specs/p426-b2-tg1-wave2.md): one model, one session leg, a fresh out-root, the seeded "
                         "frozen schedule; refuses --smoke / --pred-s / --generation-sha / --frozen-date-from / C147_OVERLAY")
    ap.add_argument("--frozen-record", default=None, metavar="PATH", help="--p426 only: the frozen record this leg runs under")
    ap.add_argument("--rehearsal", action="store_true",
                    help="--p426 only: a pre-freeze rehearsal leg (accepts only a rehearsal manifest; behaviour: spec 1)")
    ap.add_argument("--inject", choices=["reconcile-mismatch", "stall-kill"], default=None,
                    help="--rehearsal only: the R2 / R3 rehearsal injection (spec 1)")
    ap.add_argument("--occurrences", default=None, metavar="FILE",
                    help="makeup mode only (spec 5.5): the JSON-lines occurrences this fresh-load leg re-runs (its plan)")
    ap.add_argument("--pair-receipt", default=None, metavar="PATH",
                    help="--p426 only: the first leg's arm-equality receipt; this leg's receipt is compared with it after load, "
                         "before item one (spec 6.5); any difference outside the closed allowed list is systemic")
    a = ap.parse_args(argv)
    if a.inject is not None and not a.rehearsal:
        ap.error("--inject exists only with --rehearsal")
    if a.occurrences is not None and a.mode != "makeup":
        ap.error("--occurrences is for makeup mode")
    if a.mode == "makeup" and not a.p426:
        ap.error("makeup mode is for --p426")
    parse_models(ap, a)
    if a.p426:
        check_p426(ap, a)
    elif a.frozen_record is not None:
        ap.error("--frozen-record is for --p426")
    elif a.rehearsal:
        ap.error("--rehearsal is for --p426")
    elif a.pair_receipt is not None:
        ap.error("--pair-receipt is for --p426")
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
    if a.mode in ("chain", "makeup"):
        if not a.probe_code_sha:
            ap.error(f"--probe-code-sha is required for {a.mode}")
    if a.mode == "chain":
        a.sessions = a.sessions or ["s1", "s2", "reload"]
        bad = [s for s in a.sessions if s not in SEEDS]
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


def make_ops(predictor, wd, out_root, served, log):
    """M63: the ON arm keeps its router TMPDIR and A4 logs under its out-root. P340: so does an OFF arm whose out-root
    is not the default `$STACK_WORKDIR/c147` (it used to write into P223's c147/ dir); the default OFF chain is unchanged.
    C221: `served` is the committed registry the router serves verbatim (`MLX_SERVE_CONFIG`); nothing is generated."""
    wd, out_root = Path(wd), Path(out_root)
    if predictor == "mtp":
        return co.ChainOps(REPO, wd, served, log, predictor="mtp", out_root=out_root, registry=served)
    if out_root.resolve() != (wd / "c147").resolve():
        return co.ChainOps(REPO, wd, served, log, out_root=out_root, registry=served)
    return co.ChainOps(REPO, wd, served, log, registry=served)


def take_leg_lock(wd):
    """B2 spec 9: the chain's own `p426/LEG.lock` under the arbiter; an opposing `gate/RUNNING` (or a second leg) is a refusal,
    taken before anything is created."""
    from bench import p426_locks
    try:
        return p426_locks.acquire("chain", wd)
    except p426_locks.LockRefused as e:
        raise Refused(f"REFUSED: {e}") from None


def served_registry(registry, ops):
    """The registry the router serves: `ChainOps.overlay` (spec 3: in tg1 mode it IS the worktree's committed
    `main_models.yaml`, served verbatim); without ops, the worktree's file."""
    return Path(registry or getattr(ops, "overlay", None) or REPO / "main_models.yaml")


def main(argv=None, ops=None, timers=None, log_out=None, lifecycle_files=None, campaign=None, registry=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    wd = Path(ops.wd) if ops is not None else Path(os.environ["STACK_WORKDIR"])
    out_root = resolve_out_root(a, wd)
    # every refusal below happens before anything is created (M6)
    if os.environ.get("C147_OVERLAY"):
        raise Refused("REFUSED: the C147_OVERLAY override is retired (C221): the committed main_models.yaml is served verbatim")
    if a.p426 and not ATTEMPT_NAME.match(out_root.name):
        raise Refused(f"REFUSED: --out-root {out_root.name} must be named <leg>.a<n> (n from 1)")
    if a.p426 and out_root.exists():
        raise Refused(f"REFUSED: --out-root {out_root.name} exists (a --p426 leg runs on a fresh out-root)")
    if a.rehearsal:                                                  # spec 1 / 16.3: a rehearsal writes only under the rehearsal directory
        reh = (Path(wd) / "p426" / "rehearsal").resolve()
        if reh not in out_root.resolve().parents:
            raise Refused(f"REFUSED: --rehearsal writes only under $STACK_WORKDIR/p426/rehearsal/ (--out-root {out_root.name})")
    if a.p426:
        check_frozen_record(a)
    if a.pair_receipt:
        check_pair_receipt(a.pair_receipt)
    served = served_registry(registry, ops)
    try:
        co.require_served_entries(served, a.models, a.predictor)
    except co.ChainAbort as e:
        raise Refused(f"REFUSED: {e}") from None
    lock = take_leg_lock(wd) if a.p426 else None                   # B2 spec 9: `p426/LEG.lock`, held for the leg's lifetime
    try:
        out_root.mkdir(parents=True, exist_ok=not a.p426)
        log = co.RunLog(out_root / "RUNLOG.md", out=log_out)
        if ops is None:
            ops = make_ops(a.predictor, wd, out_root, served, log)
        chain = Chain(a, ops, timers or Timers(), log, load_universe(a.universe), out_root, lifecycle_files, campaign)
        if a.p426:
            try:
                chain.p426_entry_row()                             # B2 spec 3 Entry: refuses (NOT_STARTED, rc 2) before the router
            except core.EntryRefused as e:
                log(f"REFUSED: {e}")
                raise Refused(f"REFUSED: {e}") from None
        try:
            return chain.run()
        except BaseException:
            chain.rc = 1
            chain.write_json("crashed")
            raise
    finally:
        if lock is not None:
            lock.release()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as e:
        print(e.args[0], file=sys.stderr)
        sys.exit(2)
