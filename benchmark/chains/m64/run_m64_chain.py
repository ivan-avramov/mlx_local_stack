"""M64 chain entry (spec docs/specs/m64-scaffold-arms.md sections 4, 8): the arm-aware chain as a CONFIGURATION of the shared
chain core (`bench/chain_core.py`, P371 phase 3b).

  run_m64_chain.py chain [s1 s2 reload] --arms oc[,pi,dsh] --probe-code-sha oc=<sha> ... [--epoch-id <sha>] [--smoke]

This file is the CLI, the out-root rules (P340: always explicit and absolute) and the M64 `ChainConfig`; everything the chain
DOES lives in the core: the unit is a LEG = (block of <= 3 items, arm), one worker load serves a (session, pick) with all its
arms; the schedule (`schedules.blocks`: seeded order, balanced arm permutations, reload control) is hashed into
`schedule.json` before launch and checked against the realized order at the end; per-arm identities, the epoch COMPUTED from
every arm's snapshot (`--epoch-id` is only an assertion, A5), immutable A4 receipts per worker (re)load and arm (A10); per leg
the search service restarts, per arm switch the cache session is reset and one unscored warm-up is sent (`bench.arm_ops`
refuses for the real ops until the D2 service and the fork control endpoint exist); transport incidents (8.3) are classified,
recovered and the same slot retried, a second incident in a slot is a `transport_dnf` row (`incident_retry`); a resume takes a
fresh worker and the unaccepted slots only (`new_segment`); the chain answers the probes' item barrier with `ChainHooks`.

Exit codes: 0 done, 2 chain abort, 3 STOP latch honoured, 1 unexpected error."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "benchmark"))
from bench import arm_adapter as aa  # noqa: E402
from bench import arm_ops  # noqa: E402
from bench import arm_specs  # noqa: E402
from bench import campaign_core  # noqa: E402
from bench import chain_core as core  # noqa: E402
from bench import chain_ops as co  # noqa: E402
from bench import datefreeze  # noqa: E402
from bench import run_config as rc  # noqa: E402
from bench import schedules  # noqa: E402

Timers, RecordInvalid, Stopped, Refused = core.Timers, core.RecordInvalid, core.Stopped, core.Refused
SMOKE_ARM_IDLE_S = core.SMOKE_ARM_IDLE_S
LANGS = ("python", "go")
NAMED_LIFECYCLE = {"runner": "benchmark/chains/m64/run_m64_chain.py", "chain_ops": "benchmark/bench/chain_ops.py"}


def probe_entry(a, arm):
    """F7: the arm's resolved probe entry (repo-relative; `--probe ARM=PATH` overrides the arm spec's)."""
    given = (getattr(a, "probe", None) or {}).get(arm)
    return core.probe_rel(REPO, given) if given else arm_specs.spec_for(arm).probe


def core_specs(arms, a=None):
    """C179 (P377): the campaign core of an M64 chain = ONE probe closure per arm (the `probe_code_sha256` recipe: the arm
    probe entry's import closure (the RESOLVED entry, F7) + its generation data files, from the arm spec) and this entry's
    closure."""
    return dict(probes={arm: dict(entry=probe_entry(a, arm), data=tuple(arm_specs.spec_for(arm).generation_data))
                        for arm in arms},
                chain_entry=NAMED_LIFECYCLE["runner"], chain_data=())


def lifecycle_files(repo):
    """The M64 chain's lifecycle (plan 5, R15): this entry's static import closure (the core, `schedules`, `arm_specs`,
    `arm_ops`, `chain_rows`, ...) + the A4 gate script + the launcher names above."""
    return core.lifecycle_member_files(repo, NAMED_LIFECYCLE["runner"], NAMED_LIFECYCLE)


def m64_config(a, langs=None):
    """The M64 `ChainConfig` (plan 3.2): the `blocks` schedule over the languages, per-arm specs, `incident_retry` /
    `new_segment`, the arm-switch ops, snapshots complete unless `--smoke`, the contract artifacts named on the command line.
    Run selection (the session list, `--smoke`'s tiny cells) is NOT part of it, so the same chain resumes under any selection
    of its own sessions; the arms are."""
    bindings = []
    for arm in a.arms:
        spec = arm_specs.spec_for(arm)                   # refuses an arm without a chain spec (aa.ArmRefused)
        bindings.append(rc.ArmBinding(arm=arm, probe=probe_entry(a, arm), label=spec.label, arm_spec=arm,
                                      probe_data=spec.generation_data))
    params = dict(arms=list(a.arms), picks=[co.PICK1, co.PICK2], block_size=schedules.BLOCK_SIZE,
                  seeds=dict(schedules.SESSION_SEEDS, reload=schedules.RELOAD_SEED), langs=list(langs or LANGS),
                  reload_langs=["python"], reload_items=schedules.RELOAD_ITEMS, smoke_items=schedules.SMOKE_ITEMS,
                  derivation=schedules.DERIVATION)
    contract = tuple(rc.ContractArtifact(arm=arm, path=str(path), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
                     for arm, path in sorted((getattr(a, "contract_artifact", None) or {}).items()))
    return rc.ChainConfig(
        config_id="m64", arms=tuple(bindings), schedule=dict(builder="blocks", params=params), out_root_family="m64",
        predictor="off", arm_switch_ops=rc.ARM_SWITCH_OPS, transport_policy="incident_retry", resume_policy="new_segment",
        snapshot_complete_required=not getattr(a, "smoke", False), contract_artifacts=contract)


def load_universe(path=None):
    """`{lang: sorted item names}` of the universe file (the corpus the schedule draws its cells from)."""
    d = json.loads(Path(path or REPO / "benchmark/m62/universe.json").read_text())["items"]
    names = {}
    for k in d:
        lang, name = k.split("/", 1)
        names.setdefault(lang, []).append(name)
    return {k: sorted(v) for k, v in names.items()}


# --------------------------------------------------------------------------- entry
def _kv(values, what, ap, *, hexed=False):
    out = {}
    for item in values or []:
        arm, _, val = item.partition("=")
        if not val or not aa.valid_arm_id(arm):
            ap.error(f"{what} must be ARM=VALUE with a known arm, got {item!r}")
        if hexed and not co.HEX64.match(val):
            ap.error(f"{what} {arm} must be 64 lowercase hex")
        out[arm] = val
    return out


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["chain"])
    ap.add_argument("sessions", nargs="*")
    ap.add_argument("--arms", default="oc", help="comma-separated arms to schedule (oc, pi, dsh)")
    ap.add_argument("--probe-code-sha", action="append", default=[], metavar="ARM=SHA", help="required for every arm")
    ap.add_argument("--probe", action="append", default=[], metavar="ARM=PATH", help="override an arm's probe entry")
    ap.add_argument("--policy-sha", action="append", default=[], metavar="ARM=SHA",
                    help="an ASSERTION of the arm's scaffold_policy_sha256 (derived from its probe)")
    ap.add_argument("--epoch-id", default=None,
                    help="an ASSERTION of the epoch (64 hex): the chain COMPUTES it from every arm's snapshot (A5)")
    ap.add_argument("--contract-artifact", action="append", default=[], metavar="ARM=PATH",
                    help="the arm's contract artifact (path + sha256 frozen in chain.json; the refusal checks are phase 4)")
    ap.add_argument("--pred-s", action="append", default=[], metavar="LANG:MODEL=SECONDS")
    ap.add_argument("--arm-idle-s", type=float, default=None)
    ap.add_argument("--campaign-core", default=None, metavar="TAG_OR_COMMIT",
                    help="C179 / P377: the campaign's frozen core. The chain refuses unless every arm's probe closure and "
                         "this entry's closure equal their closures at this git tag / commit (at creation, every launch, "
                         "resume and exit); recorded in chain.json artifacts.campaign_core")
    ap.add_argument("--smoke", action="store_true", help="rehearsal: tiny cells, 60 s arm idle, own out-root")
    ap.add_argument("--out-root")
    ap.add_argument("--python", default=str(REPO / ".venv-bench/bin/python"))
    ap.add_argument("--universe")
    ap.add_argument("--frozen-prompt-date", default=None, metavar="'Www Mmm DD YYYY'")
    ap.add_argument("--frozen-date-from", default=None, metavar="CHAIN_JSON")
    return ap


def parse_args(argv):
    ap = build_parser()
    a = ap.parse_args(argv)
    a.arms = [x for x in a.arms.split(",") if x]
    if not a.arms or len(set(a.arms)) != len(a.arms) or any(not aa.valid_arm_id(x) for x in a.arms):
        ap.error(f"--arms must be distinct known arms of {aa.ARM_IDS}")
    a.probe_code_sha = _kv(a.probe_code_sha, "--probe-code-sha", ap, hexed=True)
    a.probe = _kv(a.probe, "--probe", ap)
    a.policy_sha = _kv(a.policy_sha, "--policy-sha", ap, hexed=True)
    a.contract_artifact = _kv(a.contract_artifact, "--contract-artifact", ap)
    for arm, path in a.contract_artifact.items():
        if arm not in a.arms or not Path(path).is_file():
            ap.error(f"--contract-artifact {arm}= must name a readable file of an arm this chain runs")
    missing = [x for x in a.arms if x not in a.probe_code_sha]
    if missing:
        ap.error(f"--probe-code-sha ARM=SHA is required for every arm (missing {missing})")
    if a.epoch_id is not None and not co.HEX64.match(a.epoch_id):
        ap.error("--epoch-id must be 64 lowercase hex")
    if a.frozen_prompt_date is not None and not datefreeze.valid(a.frozen_prompt_date):
        ap.error("--frozen-prompt-date must be 'Www Mmm DD YYYY' (e.g. 'Sat Oct 17 2026')")
    if a.campaign_core is not None and not a.campaign_core.strip():
        ap.error("--campaign-core must name a git tag or commit")
    if a.arm_idle_s is None:
        a.arm_idle_s = SMOKE_ARM_IDLE_S if a.smoke else 600.0
    a.sessions = a.sessions or ["s1", "s2", "reload"]
    bad = [s for s in a.sessions if s not in schedules.SESSION_SEEDS and s != "reload"]
    if bad:
        ap.error(f"unknown session {bad}")
    return a


def resolve_out_root(a, wd):
    """`$STACK_WORKDIR/m64` (real) or `m64-smoke`; absolute (P340: subprocesses run with cwd=REPO); a smoke run is
    refused inside the real directory, and neither may write inside another chain's directories."""
    root = Path(a.out_root) if a.out_root else Path(wd) / ("m64-smoke" if a.smoke else "m64")
    root = root.expanduser().absolute()
    if a.smoke and root.resolve() == (Path(wd) / "m64").resolve():
        raise Refused("REFUSED: --smoke must not write into the real chain directory")
    for d in ("c147", "c147-smoke", "m63", "m63-smoke"):
        other = (Path(wd) / d).resolve()
        if root.resolve() == other or other in root.resolve().parents:
            raise Refused(f"REFUSED: the M64 chain must not write into {other}")
    return root


def build_chain(a, ops, timers, log, names, out_root, lifecycle=None, hooks=None, campaign=None, config=None,
                needs_docker=None):
    return core.Chain(config or m64_config(a), a, ops, timers, log, repo=REPO, out_root=out_root, names=names,
                      lifecycle_files=lifecycle or lifecycle_files(REPO), campaign=campaign, hooks=hooks,
                      needs_docker=needs_docker)


def main(argv=None, ops=None, timers=None, log_out=None, lifecycle_files=None, hooks=None, campaign=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    wd = Path(ops.wd) if ops is not None else Path(os.environ["STACK_WORKDIR"])
    out_root = resolve_out_root(a, wd)
    out_root.mkdir(parents=True, exist_ok=True)
    log = co.RunLog(out_root / "RUNLOG.md", out=log_out)
    try:
        config = m64_config(a)
    except aa.ArmRefused as e:                          # an arm without a chain spec refuses before anything starts
        log(f"CHAIN ABORT: {e}")
        return 2
    if ops is None:
        overlay = os.environ.get("C147_OVERLAY") or str(out_root / "overlay_m64_draft_off.yaml")
        ops = arm_ops.M64ChainOps(REPO, wd, overlay, log, out_root=out_root)
    if campaign is None:
        campaign = campaign_core.Campaign(REPO, **core_specs(a.arms, a))
    chain = build_chain(a, ops, timers or Timers(), log, load_universe(a.universe), out_root, lifecycle_files, hooks,
                        campaign, config)
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
