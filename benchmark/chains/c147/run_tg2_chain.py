"""M76 B4b-1 (docs/specs/m76-b4b-tg2-runner.md v5, §2): the tg2 chain entry — ONE P426 leg of lever kv over the pinned tg2 draw
(Rust / JavaScript / Java / C++), run by the shared chain core under `ChainConfig` `tg2-p426` (builder `tg2_p426`).

  run_tg2_chain.py --leg pilot|s1|s2|reload --p426 --lever kv --kv-arm <arm> --models <entry> --predictor mtp --out-root R
                   --probe-code-sha S --policy-sha S --frozen-prompt-date D --campaign-core C --frozen-record F [--pair-receipt P]
  run_tg2_chain.py --rehearsal r2|r3 ...      the R2 (reconciliation mismatch, on X) / R3 (probe kill, on N16) rehearsal legs

`--leg pilot` is the shared core's `pilot` mode (no sessions, record `p426_v8_base`); `--leg s1|s2|reload` its `chain` mode with
that one session (record `p426_timeout_amendment`); `--rehearsal` its `chain s1` rehearsal (record `p426_rehearsal`, the R2 / R3
injection on the first Rust item). The KV after-load checks (worker argv, arm receipt, pair gate) are the tg1 chain's.
Exit codes: 0 done, 2 refused / chain abort, 3 STOP latch honoured, 1 unexpected error."""
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
from bench import corpus_tg2  # noqa: E402
from bench import datefreeze  # noqa: E402
from bench import p426_freeze as fz  # noqa: E402
from bench import run_config as rc  # noqa: E402
from bench import schedules  # noqa: E402
from chains.c147 import run_tg1_chain as t1  # noqa: E402

Timers, Refused = core.Timers, core.Refused
SCAFFOLD = rc.SCAFFOLD_TG2
LANGS = ("rust", "javascript", "java", "cpp")
LEGS = ("pilot", "s1", "s2", "reload")
REHEARSALS = {"r2": dict(inject="reconcile-mismatch", arm="x"), "r3": dict(inject="stall-kill", arm="n16")}
INJECT_LANGS = dict(r2="rust", r3="rust")             # the R2 / R3 injections fire on the first Rust item
DEFAULT_DRAW = REPO / "benchmark/m65/tg2_draw.json"
REHEARSAL_DIR = ("m76", "p426", "rehearsal.tg2")
_HERE = "/".join(("benchmark", "chains", "c147"))          # in parts: this module reads no chain rows (test_p371_chain_rows)
NAMED_LIFECYCLE = {"runner": f"{_HERE}/run_tg2_chain.py", "chain_ops": "benchmark/bench/chain_ops.py",
                   "launcher": f"{_HERE}/drive_chain.sh", "launch_tg1": f"{_HERE}/launchers/launch_tg1.sh"}
# C179 / C178: the campaign core = the tg2 probe's closure + the tg2 generation data, and this entry's closure (which includes
# the tg1 chain module it reuses: a shared-core edit rotates both).
CORE_SPECS = dict(probe_entry="benchmark/run_tg2_probe.py",
                  probe_data=("benchmark/opencode_plugins/toolbounds.js", "benchmark/opencode_plugins/noretry.js",
                              "benchmark/opencode_plugins/datefreeze.js", "benchmark/opencode_bench_v2_web_tg2.json"),
                  chain_entry=f"{_HERE}/run_tg2_chain.py", chain_data=())
ATTEMPT_NAME = t1.ATTEMPT_NAME


def probe_entry(a):
    given = getattr(a, "probe", None)
    return core.probe_rel(REPO, given) if given else CORE_SPECS["probe_entry"]


def core_specs(a):
    return dict(CORE_SPECS, probe_entry=probe_entry(a))


def lifecycle_files(repo):
    return core.lifecycle_member_files(repo, NAMED_LIFECYCLE["runner"], NAMED_LIFECYCLE)


def leg_name(a):
    """`tg2-m76-<arm>-<leg>` or `tg2-m76-<arm>-rehearsal-<r>` (spec §2)."""
    return f"tg2-m76-{a.kv_arm}-" + (f"rehearsal-{a.tg2_leg}" if a.rehearsal else a.tg2_leg)


def record_kind(a):
    """The frozen-record kind the leg runs under (E2)."""
    if a.rehearsal:
        return fz.KIND_REHEARSAL
    return fz.KIND_V8 if a.mode == "pilot" else fz.KIND_AMENDMENT


def tg2_config(a):
    """The `tg2-p426` ChainConfig: one model, builder `tg2_p426` (the leg's table row), the P426 transport policy, the tg2 probe
    and carrier label."""
    params = dict(models=list(a.models), p426=True, tg2_leg=a.tg2_leg, langs=list(LANGS), generic_pred_s=core.GENERIC_PRED_S)
    return rc.ChainConfig(
        config_id=rc.TG2_P426_CONFIG_ID,
        arms=(rc.ArmBinding(arm="oc", probe=probe_entry(a), label=SCAFFOLD, arm_spec="oc", probe_data=CORE_SPECS["probe_data"]),),
        schedule={"builder": "tg2_p426", "params": params}, out_root_family="m63", predictor=a.predictor, arm_switch_ops=(),
        transport_policy="p426_continue", resume_policy="restart_load", snapshot_complete_required=False, contract_artifacts=())


class Chain(core.Chain):
    """The tg2 leg on the shared core; the KV arm name and after-load checks are the tg1 chain's (`run_tg1_chain.Chain`)."""

    def __init__(self, args, ops, timers, log, names, out_root, lifecycle=None, campaign=None):
        corpus = corpus_tg2.Tg2Corpus()
        super().__init__(tg2_config(args), args, ops, timers, log, repo=REPO, out_root=out_root, names=names,
                         lifecycle_files=lifecycle if lifecycle else lifecycle_files(REPO),
                         campaign=campaign if campaign is not None else campaign_core.Campaign(REPO, **core_specs(args)),
                         needs_docker=corpus.needs_docker, inject_langs=INJECT_LANGS, docker_images=corpus.docker_images,
                         grader_timeout_s=corpus.grader_timeouts())

    p426_arm_name = t1.Chain.p426_arm_name
    p426_after_load = t1.Chain.p426_after_load

    def record_layout(self):
        """`chain.json` also records the normalised sessions and the tg2 leg (the mode is the core's)."""
        out = super().record_layout()
        out.update(sessions=list(self.a.sessions), tg2_leg=self.a.tg2_leg, corpus="tg2")
        return out


def load_names():
    """{lang: sorted bare names} of the universe's valid items (the chain's item universe)."""
    corpus = corpus_tg2.Tg2Corpus()
    return {lang: sorted(i.split("/", 1)[1] for i in corpus.items(lang)) for lang in LANGS}


class RefusingParser(t1.RefusingParser):
    pass


def parse_args(argv):
    ap = RefusingParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--leg", choices=LEGS, help="the tg2 leg (table of spec §2)")
    which.add_argument("--rehearsal", choices=sorted(REHEARSALS), help="R2 (on X) / R3 (on N16): s1's first Rust item")
    ap.add_argument("--p426", action="store_true", required=True)
    ap.add_argument("--models", required=True, metavar="NAME")
    ap.add_argument("--predictor", choices=["off", "mtp"], default="off")
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--probe", default=str(REPO / "benchmark/run_tg2_probe.py"))
    ap.add_argument("--python", default=str(REPO / ".venv-bench/bin/python"))
    ap.add_argument("--probe-code-sha", required=True)
    ap.add_argument("--policy-sha", required=True)
    ap.add_argument("--frozen-prompt-date", required=True, metavar="'Www Mmm DD YYYY'")
    ap.add_argument("--campaign-core", required=True, metavar="TAG_OR_COMMIT")
    ap.add_argument("--frozen-record", required=True, metavar="PATH")
    ap.add_argument("--pair-receipt", default=None, metavar="PATH")
    ap.add_argument("--lever", required=True, choices=["kv"])
    ap.add_argument("--kv-arm", required=True, choices=list(fz.TG2_PAIR))        # change review L6: the tg2 pair's arms
    ap.add_argument("--tg2-draw", default=str(DEFAULT_DRAW), help="the pinned tg2 draw (default benchmark/m65/tg2_draw.json)")
    a = ap.parse_args(argv)
    t1.parse_models(ap, a)
    if len(a.models) != 1:
        ap.error("--models: a tg2 leg runs exactly one model")
    if a.predictor != "mtp":
        ap.error("--lever kv is MTP ON (--predictor mtp, C323)")
    if not co.HEX64.match(a.policy_sha) or not co.HEX64.match(a.probe_code_sha):
        ap.error("--policy-sha / --probe-code-sha must be 64 lowercase hex")
    if not datefreeze.valid(a.frozen_prompt_date):
        ap.error("--frozen-prompt-date must be 'Www Mmm DD YYYY' (e.g. 'Sat Oct 17 2026')")
    if not a.campaign_core.strip():
        ap.error("--campaign-core must name a git tag or commit")
    if a.rehearsal:                                              # E2: the core's `chain s1` rehearsal with its injection
        if a.kv_arm != REHEARSALS[a.rehearsal]["arm"]:
            ap.error(f"--rehearsal {a.rehearsal} runs on {REHEARSALS[a.rehearsal]['arm']}, not {a.kv_arm}")
        if a.pair_receipt:
            ap.error("a rehearsal leg has no pair receipt")
        a.tg2_leg, a.mode, a.sessions, a.inject = a.rehearsal, "chain", ["s1"], REHEARSALS[a.rehearsal]["inject"]
        a.rehearsal = True
    else:
        a.tg2_leg, a.inject, a.rehearsal = a.leg, None, False
        a.mode, a.sessions = ("pilot", []) if a.leg == "pilot" else ("chain", [a.leg])
    # what the shared core reads of a tg1-shaped namespace (none of it is a tg2 flag)
    a.smoke, a.pred_s, a.generation_sha, a.frozen_date_from = False, [], None, None
    a.universe, a.occurrences, a.arm_idle_s = None, None, 600.0
    return a


def check_out_root(a, out_root):
    """The out-root is this leg's attempt `<leg name>.a<n>`."""
    want = leg_name(a)
    if not re.fullmatch(re.escape(want) + r"\.a[1-9][0-9]*", Path(out_root).name):
        raise Refused(f"REFUSED: --out-root {Path(out_root).name} is not {want}.a<n>")


def check_frozen_record(a):
    """tg1's checks (kind for the mode, self-hash, lever kv, the arm in the pair), the record names corpus tg2 and its pair is
    the tg2 pair (change review L6)."""
    rec = t1.check_frozen_record(a)
    if rec["base"].get("corpus") != "tg2":
        raise Refused("REFUSED: --frozen-record does not name corpus tg2: a tg2 leg runs only under the tg2 records")
    try:
        fz.check_tg2_pair(rec["base"].get("arms"))
    except fz.Refusal as exc:
        raise Refused(f"REFUSED: --frozen-record: {exc}") from None
    return rec


def main(argv=None, ops=None, timers=None, log_out=None, lifecycle_files=None, campaign=None, registry=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    wd = Path(ops.wd) if ops is not None else Path(os.environ["STACK_WORKDIR"])
    out_root = t1.resolve_out_root(a, wd)
    if os.environ.get("C147_OVERLAY"):
        raise Refused("REFUSED: the C147_OVERLAY override is retired (C221): the committed main_models.yaml is served verbatim")
    check_out_root(a, out_root)
    if out_root.exists():
        raise Refused(f"REFUSED: --out-root {out_root.name} exists (a P426 leg runs on a fresh out-root)")
    if a.rehearsal:
        reh = Path(wd).joinpath(*REHEARSAL_DIR).resolve()
        if reh not in out_root.resolve().parents:
            raise Refused(f"REFUSED: --rehearsal writes only under $STACK_WORKDIR/{'/'.join(REHEARSAL_DIR)}/")
    check_frozen_record(a)
    if a.pair_receipt:
        t1.check_pair_receipt(a.pair_receipt)
    try:
        import json
        schedules.tg2_p426(json.loads(Path(a.tg2_draw).read_text()), a.tg2_leg, a.models[0], a.predictor)
    except (OSError, ValueError, schedules.TransportAbort) as exc:
        raise Refused(f"REFUSED: the tg2 draw: {exc}") from None
    if not (REPO / probe_entry(a)).is_file():
        raise Refused(f"REFUSED: the probe entry {probe_entry(a)} does not exist")
    served = t1.served_registry(registry, ops)
    try:
        co.require_served_entries(served, a.models, a.predictor)
    except co.ChainAbort as e:
        raise Refused(f"REFUSED: {e}") from None
    lock = t1.take_leg_lock(wd)
    try:
        out_root.mkdir(parents=True, exist_ok=False)
        log = co.RunLog(out_root / "RUNLOG.md", out=log_out)
        if ops is None:
            ops = t1.make_ops(a.predictor, wd, out_root, served, log)
        chain = Chain(a, ops, timers or Timers(), log, load_names(), out_root, lifecycle_files, campaign)
        try:
            chain.p426_entry_row()
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
        lock.release()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as e:
        print(e.args[0], file=sys.stderr)
        sys.exit(2)
