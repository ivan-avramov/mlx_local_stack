"""P371 phase 3a (plan 3.1 `chain_core`): THE chain core. The tg1 chain (C147 / M63 / P340 / P364 / P311-lite) moved here from
`chains/c147/run_tg1_chain.py` and generalized over a `run_config.ChainConfig`; the chain ENTRY is a thin CLI + out-root rules
that builds the config and the ops.

What the core owns: the lifecycle freeze (the entry's static import closure + the serialized ChainConfig + the A4 gate + the
launchers, R15, frozen in chain.json at creation and verified before every launch, barrier, validation, resume and at exit),
the C179 campaign-core check, the frozen prompt date, the probe-derived policy sha, STOP, the run loop, loads / legs /
invocations, the first-manifest barrier ack, supervision (idle predicate, escalation, watch log), validation + pinning,
archive / restart, quarantine, the persisted progress inventory (`bench.chain_rows`), and chain-side web evidence.

Layout (plan 4 A8): ONE immutable rows file per leg INVOCATION, `<session>/<stem>.L<leg>.<phase>.a<n>.jsonl` (+ manifest, +
`.log` / `.json` / `.CANCEL` / `.ACK`); a full invocation runs exactly the cell minus the pilot's validated slots. Every
invocation is registered in `chain.json.progress.invocations` (status `running`) BEFORE the probe is spawned, and its sha256
is recorded after validation. `resume_policy = restart_load` (tg1): an interrupted load's never-validated files go to
`quarantine/` (sha manifest first), the rest of the load is archived (sha manifest recorded in chain.json FIRST), its records
are marked `archived`, and the load reruns from leg 0 with `load_gen + 1`.

Seams for the M64 features (phase 3b, by configuration and small overrides, not by re-implementing the loop):
  * `plan()` normalizes a schedule into loads -> legs -> invocations (`blocks` is the 3b builder);
  * `ChainConfig.transport_policy / resume_policy / arm_switch_ops` are read in `handle_incomplete` / `prepare_resume` /
    `arm_switch`; `incident_retry`, `new_segment`, arm switches and DNF rows are the 3b branches of those methods;
  * `record_layout()` serializes `pinned` / `policies` flat (tg1) or per arm (3b); `extra_record()` adds keys;
  * `before_invocation()` / `after_invocation()` are the places the item-barrier hooks (`chain_hooks`) run;
  * `evidence_namespace` / `web_rules()` name the arm's evidence directory and extraction rules.
Exit codes: 0 done, 2 chain abort (listing printed, nothing killed), 3 STOP latch honoured, 1 unexpected error."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import arm_specs
from . import chain_hooks
from . import chain_ops as co
from . import chain_rows as cr
from . import datefreeze
from . import schedules
from . import web_evidence as we

PICK1, PICK2 = co.PICK1, co.PICK2
SCAFFOLD = co.SCAFFOLD
PRED_S = {("python", PICK1): 244, ("go", PICK1): 300, ("python", PICK2): 267, ("go", PICK2): 360}   # M59 table
PILOT_N = 5
# P279 --smoke: a short live rehearsal of the real schedule (rows are rehearsal evidence only, never graded or pooled)
SMOKE_PILOT_N, SMOKE_FULL_N, SMOKE_ARM_IDLE_S = 1, 2, 60.0
NAMED_LIFECYCLE = ("runner", "chain_ops", "gate", "launcher", "launch_tg1")     # the pre-P371 chain.json lifecycle names


class RecordInvalid(co.ChainAbort):
    """An existing chain.json is not a complete valid record: refuse and leave it untouched (L4)."""


class Stopped(Exception):
    pass


class Refused(SystemExit):
    """M63 (M6): a refusal before anything is written; exits with the documented abort code 2, message kept."""

    def __init__(self, msg):
        super().__init__(msg)
        self.code = 2


@dataclass
class Timers:
    poll_s: float = 1.0
    watch_s: float = 300.0
    idle_sample_s: float = 60.0
    hb_age_s: float = 900.0
    idle_needed: int = 3
    manifest_alarm_s: float = 120.0
    term_wait_s: float = 120.0
    kill_wait_s: float = 30.0
    barrier_exit_wait_s: float = 330.0
    t_coop_scale: float = 1.0


# --------------------------------------------------------------------------- helpers
class Heartbeat:
    def __init__(self, logpath, clock, t0):
        self.path, self.clock, self.seen, self.line, self.data = Path(logpath), clock, t0, None, {}

    def poll(self):
        try:
            with self.path.open("rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 262144))
                text = f.read().decode(errors="replace")
        except OSError:
            return
        lines = [ln for ln in text.splitlines() if '"m62_watch"' in ln]
        if lines and lines[-1] != self.line:
            self.line = lines[-1]
            self.seen = self.clock()
            try:
                self.data = json.loads(self.line)
            except ValueError:
                self.data = {}

    def age(self):
        return self.clock() - self.seen

    def watch(self):
        return self.data.get("m62_watch") or {}

    def last_prompt(self):
        return self.watch().get("last_prompt_tokens") or 0


def dir_bytes(root):
    total = 0
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            try:
                total += os.stat(os.path.join(dp, f)).st_size
            except OSError:
                pass
    return total


def receipt_from_manifest(man):
    """The probe's cleanup receipt: TOP-LEVEL manifest `cleanup_status` on every abort (one location, both sides)."""
    cs = man.get("cleanup_status")
    return cs if isinstance(cs, dict) else None


def quantile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fsync_json(path, obj):
    """Atomic JSON write with the file and its directory fsynced: the progress inventory is durable before the next action."""
    import tempfile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def lifecycle_member_files(repo, entry, named, gate="scripts/session_pinning_gate.py"):
    """`{name: path}` of a chain entry's lifecycle (plan 5, R15): the entry's static import closure (`identity_closure`), the
    A4 gate script and the launchers (`named`: {name: repo-relative path}, e.g. `runner`, `chain_ops`, `launcher`). Closure
    members that are not named are keyed by their repo-relative path."""
    from . import identity_closure as ic
    repo = Path(repo)
    base = {name: repo / rel for name, rel in named.items()}
    base["gate"] = repo / gate
    files = {name: base[name] for name in NAMED_LIFECYCLE if name in base}      # the pre-P371 member order first
    files.update({name: path for name, path in base.items() if name not in files})
    known = {p.resolve() for p in files.values()}
    for path in ic.python_closure(repo / entry, repo):
        if path.resolve() not in known:
            files[path.resolve().relative_to(repo.resolve()).as_posix()] = path
    return files


# --------------------------------------------------------------------------- probe command
def build_cmd(py, probe, leg, step, receipt, cancel, ack, *, scaffold, universe=None, frozen=None, out=None, attempt=None,
              rerun_index=None, epoch=None):
    ids = [f"{leg['lang']}/{n}" for n in step["names"]]
    cmd = [str(py), str(probe), "--model", leg["model"], "--items", ",".join(step["names"]), "--lang", leg["lang"],
           "--seed-base", str(leg["seed_base"]), "--out", str(out if out is not None else leg["out"]),
           "--scaffold", scaffold, "--expect-items", ",".join(ids), "--a4-v2-receipt", str(receipt),
           "--sampling-profile", "deployed", "--cancel-file", str(cancel), "--manifest-ack", str(ack)]
    if step.get("limit"):
        cmd += ["--limit", str(step["limit"])]
    if universe:                                    # P351: the probe grades against the chain's universe
        cmd += ["--universe", str(universe)]
    if frozen:                                      # P364: the date the model is shown, frozen with the epoch
        cmd += ["--frozen-prompt-date", frozen]
    if epoch:
        cmd += ["--epoch-id", epoch]
    if attempt is not None:                         # P371 A8: the invocation's attempt number (worker receipt attempt id)
        cmd += ["--attempt", str(attempt), "--attempt-rerun-index", str(rerun_index or 0)]
    return cmd


# --------------------------------------------------------------------------- the chain
class Chain:
    evidence_namespace = "opencode_transcripts"

    def __init__(self, config, args, ops, timers, log, *, repo, out_root, names, lifecycle_files, campaign=None, hooks=None):
        self.config = config
        self.repo = Path(repo)
        self.a, self.ops, self.tm, self.log = args, ops, timers, log
        self.lifecycle_files = dict(lifecycle_files)
        self.campaign = campaign
        self.hooks = hooks or chain_hooks.ChainHooks()
        self.campaign_core = None             # {tag, commit, probe_closure_sha256, chain_closure_sha256} or None (C179)
        self.lifecycle = None                 # frozen at chain creation (init_lifecycle), never recomputed
        self.arms = {}                        # "<model>|<predictor>" -> arm_identity_sha256, frozen at the first manifest
        self.out_root, self.stop_path = Path(out_root), Path(out_root) / "STOP"
        self.names = names
        self.clock = time.monotonic
        self.py = Path(args.python)
        self.probe = Path(args.probe)
        self.wd = Path(ops.wd)
        # a key is present once pinned; a pinned None (e.g. agent_system_sha256 without an overlay) is a value
        self.expected_policy = None           # P362: derived from the probe's --print-identity at chain start, frozen
        self.frozen = None                    # P364: the date opencode shows the model; epoch metadata, frozen in chain.json
        self.frozen_source = None
        self.pinned = {}
        self.universe = Path(args.universe).resolve() if args.universe else None
        if args.probe_code_sha:
            self.pinned["probe_code_sha256"] = args.probe_code_sha
        if getattr(args, "generation_sha", None):
            self.pinned["generation_identity_sha256"] = args.generation_sha
        self.attempts, self.restarts, self.stop_info = [], [], None
        self.attempt_no, self.seen_run_ids, self.block_workers = {}, set(), []
        self.progress = dict(loads=[], invocations=[], slot_attempts=[], pre_spawn=[])
        self.loaded = None
        self.rc = None
        self.pred, self.explicit_pred = dict(PRED_S), {}
        for spec in args.pred_s or []:
            key, val = spec.rsplit("=", 1)
            lang, model = key.split(":", 1)
            self.explicit_pred[(lang, model)] = float(val)

    # -- the chain config's arm
    @property
    def arm(self):
        return self.config.arms[0]

    def web_rules(self):
        return arm_specs.spec_for(self.arm.arm_spec).web_evidence_rules

    # -- lifecycle freeze (P24, R15) and the chain.json record (L4)
    def record_problem(self, doc):
        """Why an existing chain.json is not a complete valid record (None when it is)."""
        hexed = lambda v: isinstance(v, str) and bool(co.HEX64.match(v))      # noqa: E731
        if not isinstance(doc, dict):
            return "not a JSON object"
        lc = doc.get("lifecycle")
        want = set(self.lifecycle_files) | {"chain_config"}
        if not (isinstance(lc, dict) and set(lc) == want and all(hexed(v) for v in lc.values())):
            return "lifecycle absent or incomplete"
        arms = doc.get("arms")
        if not (isinstance(arms, dict) and all(isinstance(k, str) and hexed(v) for k, v in arms.items())):
            return "arms absent or malformed"
        pinned = doc.get("pinned")
        if not isinstance(pinned, dict):
            return "pinned absent or malformed"
        if "generation_identity_sha256" in pinned and not hexed(pinned["generation_identity_sha256"]):
            return "pinned generation_identity_sha256 malformed"
        if not hexed(doc.get("policy_sha256")):
            return "policy_sha256 absent, null or malformed"
        if pinned.get("scaffold_policy_sha256") != doc["policy_sha256"]:
            return "pinned scaffold_policy_sha256 missing or differs from policy_sha256"
        if not datefreeze.valid(doc.get("frozen_prompt_date")):
            return "frozen_prompt_date absent or malformed"
        if not isinstance(doc.get("chain_config"), dict):
            return "chain_config absent or malformed"
        try:
            cr.validate_progress(doc)
        except cr.ChainRowsError as exc:
            return f"progress inventory invalid ({exc})"
        if not isinstance(doc.get("artifacts"), dict) or "campaign_core" not in doc["artifacts"]:
            return "artifacts.campaign_core absent"
        return None

    def resolve_frozen(self, previous):
        """P364: the epoch's frozen prompt date. A new epoch takes it from the reference epoch's chain.json
        (`--frozen-date-from`) or states it explicitly (`--frozen-prompt-date`); it is NEVER defaulted to today (that
        would defeat cross-day reference reuse). A resumed chain keeps its recorded date; a differing argument refuses."""
        given = getattr(self.a, "frozen_prompt_date", None)
        ref = getattr(self.a, "frozen_date_from", None)
        if given is not None and ref is not None:
            raise RecordInvalid("give --frozen-prompt-date OR --frozen-date-from, not both")
        date, source = given, (dict(kind="explicit") if given is not None else None)
        if ref is not None:
            try:
                raw = Path(ref).read_bytes()
                doc = json.loads(raw)
            except (OSError, ValueError) as exc:
                raise RecordInvalid(f"--frozen-date-from {Path(ref).name} unreadable ({type(exc).__name__})") from None
            date = doc.get("frozen_prompt_date") if isinstance(doc, dict) else None
            if not datefreeze.valid(date):
                raise RecordInvalid(f"--frozen-date-from {Path(ref).name} has no valid frozen_prompt_date "
                                    "(a reference epoch from before P364 cannot be reused)")
            source = dict(kind="reference", chain_json=Path(ref).parent.name + "/" + Path(ref).name,
                          chain_json_sha256=co.hashlib.sha256(raw).hexdigest(),
                          reference_policy_sha256=doc.get("policy_sha256"))
        if given is not None and not datefreeze.valid(given):
            raise RecordInvalid(f"--frozen-prompt-date {given!r} is not 'Www Mmm DD YYYY'")
        if previous is not None:
            if date is not None and date != previous["frozen_prompt_date"]:
                raise RecordInvalid(f"frozen prompt date {date!r} differs from the chain's frozen "
                                    f"{previous['frozen_prompt_date']!r} (a changed chain needs a new out-root)")
            self.frozen = previous["frozen_prompt_date"]
            self.frozen_source = previous.get("frozen_prompt_date_source")
            return
        if date is None:
            raise RecordInvalid("a new epoch needs --frozen-prompt-date or --frozen-date-from (never defaulted to today)")
        self.frozen, self.frozen_source = date, source

    def init_lifecycle(self):
        """Freeze the sha256 of the chain's own code at chain creation, or verify it against the frozen record of an
        existing chain.json (resume). An existing chain.json must be a COMPLETE valid record, else the run refuses
        (never re-freezes or overwrites it: a new out-root is needed). Drift aborts and leaves the record untouched. A
        resumed chain keeps its frozen arm identities, pinned composite, expected policy, progress and campaign core."""
        path = self.out_root / "chain.json"
        if path.exists():
            try:
                previous = json.loads(path.read_text())
            except (OSError, ValueError) as exc:
                raise RecordInvalid(f"existing chain.json unreadable ({type(exc).__name__}); use a new out-root")
            problem = self.record_problem(previous)
            if problem:
                raise RecordInvalid(f"existing chain.json is not a complete valid record ({problem}); use a new out-root")
            if previous["chain_config"] != self.config.as_dict() or previous["lifecycle"]["chain_config"] != self.config.sha256():
                raise RecordInvalid("chain_config differs from the chain's frozen chain_config (a changed chain needs a "
                                    "new out-root)")
            self.lifecycle = previous["lifecycle"]
            self.arms = dict(previous["arms"])
            self.load_record(previous)
            composite = previous["pinned"].get("generation_identity_sha256")
            if composite and "generation_identity_sha256" not in self.pinned:
                self.pinned["generation_identity_sha256"] = composite
            self.expected_policy = previous["policy_sha256"]
            self.resolve_frozen(previous)
            self.resume_campaign(previous["artifacts"]["campaign_core"])
            self.verify_lifecycle("resume")
            return
        self.resolve_frozen(None)                       # before anything is frozen or written
        self.create_campaign()
        fresh = co.lifecycle_shas(self.lifecycle_files)
        if any(v is None for v in fresh.values()):
            raise co.ChainAbort("lifecycle file unreadable at chain creation: "
                                + ", ".join(k for k, v in fresh.items() if v is None))
        self.lifecycle = dict(fresh, chain_config=self.config.sha256())

    def load_record(self, previous):
        """What a resumed chain takes over from the record (the progress inventory and the run history)."""
        self.progress = previous["progress"]
        self.attempts = list(previous.get("attempts") or [])
        self.restarts = list(previous.get("restarts") or [])
        self.block_workers = list(previous.get("block_workers") or [])
        for rec in self.progress["invocations"]:
            stem, n = self.stem_attempt(rec)
            if stem is not None:
                self.attempt_no[stem] = max(self.attempt_no.get(stem, 0), n)

    @staticmethod
    def stem_attempt(rec):
        name = Path(rec["file"]).name
        m = cr.FILE_RE.search(name)
        if not m:
            return None, 0
        stem = name[:m.start()]
        return stem, int(rec["attempt"])

    # -- C179 campaign core
    def create_campaign(self):
        ref = getattr(self.a, "campaign_core", None)
        if ref is None:
            self.campaign_core = None
            return
        if self.campaign is None:
            raise RecordInvalid("--campaign-core needs the campaign helper (none configured)")
        from . import campaign_core as cc
        try:
            at = self.campaign.at_ref(ref)
            self.campaign.require_equal(at, self.campaign.current())
        except cc.CampaignError as exc:
            raise RecordInvalid(str(exc)) from None
        self.campaign_core = dict(at)
        self.log(f"campaign core {at['tag']} ({str(at['commit'])[:12]}): probe and chain closures equal the current ones")

    def resume_campaign(self, recorded):
        ref = getattr(self.a, "campaign_core", None)
        if ref is not None and (recorded is None or recorded.get("tag") != ref):
            raise RecordInvalid(f"--campaign-core {ref!r} differs from the chain's frozen campaign core "
                                f"{(recorded or {}).get('tag')!r} (a campaign core is set at chain creation only)")
        self.campaign_core = recorded

    def campaign_problem(self):
        if self.campaign_core is None:
            return None
        from . import campaign_core as cc
        try:
            self.campaign.require_equal(self.campaign_core, self.campaign.current())
        except cc.CampaignError as exc:
            return str(exc)
        return None

    def derive_policy(self):
        """P362: the expected scaffold_policy_sha256 is what the configured probe reports for THIS box (its policy embeds
        the grader image id and toolchain lock), asked with the chain's --universe. A supplied --policy-sha is an
        assertion against it; a frozen value (resume) must still equal it."""
        cmd = [str(self.py), str(self.probe), "--print-identity"] + (["--universe", str(self.universe)] if self.universe else [])
        try:
            got = subprocess.run(cmd, cwd=str(self.repo), env=self.ops.env_base(), capture_output=True, text=True,
                                 timeout=300, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise co.ChainAbort(f"probe --print-identity could not run ({type(exc).__name__})") from None
        lines = [ln for ln in got.stdout.splitlines() if ln.strip()]
        try:
            value = json.loads(lines[-1]).get("scaffold_policy_sha256") if got.returncode == 0 and lines else None
        except (ValueError, AttributeError):
            value = None
        if not (isinstance(value, str) and co.HEX64.match(value)):
            raise co.ChainAbort(f"probe --print-identity gave no valid scaffold_policy_sha256 (rc {got.returncode})")
        if self.a.policy_sha and self.a.policy_sha != value:
            raise co.ChainAbort(f"supplied --policy-sha {self.a.policy_sha} != the probe's policy {value}")
        if self.expected_policy and self.expected_policy != value:
            raise co.ChainAbort(f"frozen policy {self.expected_policy} != the probe's policy now {value} (toolchain or "
                                f"universe changed; a changed chain needs a new out-root)")
        self.expected_policy = value
        self.pinned["scaffold_policy_sha256"] = value
        self.log(f"policy: scaffold_policy_sha256 {value} derived from the probe's --print-identity")

    def lifecycle_problems(self):
        """Closure members (or the chain_config) that drifted since chain creation, then a campaign core drift."""
        out = []
        drift = co.lifecycle_drift(self.lifecycle, self.lifecycle_files)
        if drift:
            out.append(f"{', '.join(drift)} changed since chain creation")
        config = getattr(self, "config", None)
        if config is not None and self.lifecycle and self.lifecycle.get("chain_config") != config.sha256():
            out.append("chain_config changed since chain creation")
        return out

    def verify_lifecycle(self, where):
        problems = self.lifecycle_problems()
        if problems:
            raise co.ChainAbort(f"lifecycle drift at {where}: {'; '.join(problems)} (a changed chain needs a new out-root)")
        problem = self.campaign_problem() if getattr(self, "campaign_core", None) is not None else None
        if problem:
            raise co.ChainAbort(f"{problem} (at {where})")

    # -- chain.json
    def sha256_block(self):
        lc = self.lifecycle or {}
        return dict({n: lc.get(n) for n in NAMED_LIFECYCLE}, overlay=self.ops.overlay_sha())

    def record_layout(self):
        """The per-arm identity keys of the record. tg1 (one arm): flat `policy_sha256` / `pinned`."""
        return dict(policy_sha256=self.expected_policy, pinned=self.pinned)

    def write_json(self, status=None):
        doc = dict(status=status, mode=self.a.mode, argv=sys.argv[1:], updated=co.utc_stamp(),
                   sha256=self.sha256_block(), lifecycle=self.lifecycle, arms=self.arms,
                   frozen_prompt_date=self.frozen, frozen_prompt_date_source=self.frozen_source,
                   probe=str(self.probe), probe_code_sha=self.a.probe_code_sha,
                   attempts=self.attempts, restarts=self.restarts, stop=self.stop_info, rc=self.rc,
                   block_workers=self.block_workers, smoke=getattr(self.a, "smoke", False),
                   predictor=getattr(self.a, "predictor", "off"), chain_config=self.config.as_dict(),
                   progress=self.progress, artifacts=dict(campaign_core=self.campaign_core), **self.record_layout())
        fsync_json(self.out_root / "chain.json", doc)

    # -- STOP
    def stop_requested(self):
        if self.stop_path.exists():
            if self.stop_info is None:
                self.stop_info = dict(at=co.utc_stamp())
                self.log("STOP latched")
            return True
        return False

    def check_stop(self, where):
        if self.stop_requested():
            self.stop_info["where"] = where
            raise Stopped(where)

    # -- plan: the schedule normalized into loads -> legs -> invocations
    def plan(self):
        builder = self.config.schedule["builder"]
        if builder != "tg1":
            raise NotImplementedError(f"schedule builder {builder!r} is a phase 3b configuration")
        sched = schedules.tg1(self.a.mode, self.a.sessions, self.names, smoke=getattr(self.a, "smoke", False),
                              predictor=getattr(self.a, "predictor", "off"))
        loads = []
        for idx, block in enumerate(sched["blocks"]):
            legs = []
            for li, leg in enumerate(block["legs"]):
                legs.append(dict(
                    leg, li=li, load=idx, arm=self.arm.arm, label=self.arm.label, items=list(leg["full_names"]),
                    slot_base=f"{self.config.config_id}|{self.arm.arm}|{leg['model']}|{leg['session']}|{leg['lang']}",
                    invocations=[dict(kind=i["phase"], phase=i["phase"], names=list(i["names"]), limit=i["limit"],
                                      expect=list(i["expect"])) for i in leg["invocations"]]))
            loads.append(dict(idx=idx, key=f"{block['session']}|{block['model']}", session=block["session"],
                              model=block["model"], seed_base=block["seed_base"], legs=legs,
                              pilot_only=block.get("pilot_only", False)))
        return loads

    # -- run
    def run(self):
        try:
            self.init_lifecycle()
        except RecordInvalid as e:                       # never touch an invalid existing record
            self.log(f"CHAIN ABORT: {e}")
            self.rc = e.code
            return self.rc
        except co.ChainAbort as e:                       # drift on resume: nothing was started, the record stays frozen
            self.log(f"CHAIN ABORT: {e}")
            self.rc = e.code
            self.write_json("aborted")
            return self.rc
        try:
            self.derive_policy()
        except co.ChainAbort as e:                       # nothing is written: no half-formed or re-derived record
            self.log(f"CHAIN ABORT: {e}")
            self.rc = e.code
            return self.rc
        self.write_json("starting")
        if self.stop_requested():
            self.stop_info["where"] = "start"
            self.log("STOP present at start: nothing launched")
            self.rc = 3
            return 3
        try:
            self.ops.ensure_overlay()
            self.pinned["registry_sha256"] = self.ops.overlay_sha()
            if not self.ops.power_ok():
                raise co.ChainAbort("power gate FAIL")
            predictor = getattr(self.a, "predictor", "off")
            loads = self.plan()
            if any(leg["lang"] == "go" for load in loads for leg in load["legs"]) and not self.ops.docker_ok():
                raise co.ChainAbort("docker gate FAIL: Go grading needs a reachable docker daemon")   # P290
            self.ops.start_router()
            self.log(f"START {self.a.mode} predictor={predictor} blocks={[(b['session'], b['model']) for b in loads]}")
            try:
                for load in loads:
                    self.run_load(load)
                if self.loaded and not self.ops.unload(self.loaded):
                    raise co.ChainAbort("final unload failed")
                self.loaded = None
                self.verify_lifecycle("exit")
                self.rc = 0
                self.log("ALL LEGS DONE")
            except Stopped as s:
                self.stop_info["where"] = self.stop_info.get("where") or str(s)
                self.log(f"STOP honoured at {self.stop_info['where']}: exit 3")
                self.rc = 3
        except co.ChainAbort as e:
            self.log(f"CHAIN ABORT: {e}")
            self.rc = e.code
        finally:
            self.write_json("finished")
            try:
                self.ops.stop_stack()
            finally:
                self.write_json("finished")
        return self.rc

    # -- loads (a block: one model within one session, both languages)
    def session_dir(self, load):
        return self.out_root / load["session"]

    def load_rec(self, load):
        for rec in self.progress["loads"]:
            if rec.get("key") == load["key"] and rec.get("load") == load["idx"]:
                return rec
        rec = dict(load=load["idx"], key=load["key"], session=load["session"], model=load["model"], status="pending",
                   load_gen=0, workers=[], cursor=dict(leg_index=0, phase=None), archives=[])
        self.progress["loads"].append(rec)
        return rec

    def run_load(self, load):
        rec = self.load_rec(load)
        load["rec"] = rec
        if rec["status"] == "done":
            self.log(f"SKIP load {load['session']}/{load['model']}: done")
            return
        if rec["status"] == "running" or any(i["load_gen"] == rec["load_gen"] and i["leg_key"][0] == load["idx"]
                                              and i["status"] != "archived" for i in self.progress["invocations"]):
            self.prepare_resume(load, rec)
        restarted = False
        while True:
            self.prepare(load, restarted)
            if self.execute_load(load) == "ok":
                rec["status"] = "done"
                self.write_json("load-done")
                return
            if restarted:
                raise co.ChainAbort(f"block {load['session']}/{load['model']} incomplete twice")
            dest = self.archive_load(load)
            restarted = True
            self.restarts.append(dict(session=load["session"], model=load["model"], archive=str(dest),
                                      at=co.utc_stamp()))
            self.log(f"RESTART block {load['session']}/{load['model']}: archived to {dest}")
            self.write_json("restarting")

    def prepare_resume(self, load, rec):
        """`restart_load` (tg1): an interrupted load of a previous run is quarantined (never-validated files) and archived
        (the rest), its records marked, and the load reruns from leg 0 with load_gen + 1."""
        if self.config.resume_policy != "restart_load":
            raise NotImplementedError(f"resume_policy {self.config.resume_policy!r} is a phase 3b configuration")
        running = [i for i in self.progress["invocations"] if i["leg_key"][0] == load["idx"]
                   and i["load_gen"] == rec["load_gen"] and i["status"] == "running"]
        if running:
            self.quarantine(running)
        dest = self.archive_load(load, resume=True)
        self.log(f"RESUME load {load['session']}/{load['model']}: interrupted load archived to {dest}")

    def prepare(self, load, restart=False):
        self.check_stop("restart preparation" if restart else "block boundary")
        unloaded = False
        if self.loaded:
            if not self.ops.unload(self.loaded):
                raise co.ChainAbort(f"unload of {self.loaded} not verified")
            self.loaded, unloaded = None, True
        if unloaded:
            self.arm_idle()
        self.check_stop("restart preparation" if restart else "block boundary")
        st = self.ops.start_state()
        self.log(f"START STATE {load['session']}/{load['model']}: {json.dumps(st, default=str)}")
        if not self.ops.power_ok():
            raise co.ChainAbort("power gate FAIL before load")
        ident = self.ops.load(load["model"])
        self.loaded = load["model"]
        key = (ident["pid"], ident["create_time"])
        if any(key == (w["pid"], w["create_time"]) for w in self.block_workers):
            raise co.ChainAbort("worker identity reused across blocks")
        n = len(self.block_workers)
        self.block_workers.append(dict(pid=ident["pid"], create_time=ident["create_time"], cmdline=ident.get("cmdline"),
                                       session=load["session"], model=load["model"]))
        load["worker"], load["manifest_worker"] = dict(pid=ident["pid"], create_time=ident["create_time"]), None
        load["receipt"] = self.ops.a4_gate(load["model"], f"{load['session']}_{n}_{load['model']}")
        rec = load["rec"]
        rec["status"] = "running"
        rec["cursor"] = dict(leg_index=0, phase=None)
        rec["workers"].append(dict(n=len(rec["workers"]), pid=ident["pid"], create_time=ident["create_time"],
                                   a4_receipt_sha256=co.file_sha(load["receipt"])))
        self.write_json("block-loaded")

    def arm_idle(self):
        end = self.clock() + self.a.arm_idle_s
        self.log(f"ARM idle {self.a.arm_idle_s}s")
        while self.clock() < end:
            self.check_stop("block boundary")
            time.sleep(min(self.tm.poll_s, max(0.0, end - self.clock())))

    def execute_load(self, load):
        for leg in load["legs"]:
            for inv in leg["invocations"]:
                self.check_stop("before launch")
                load["rec"]["cursor"] = dict(leg_index=leg["li"], phase=inv["phase"])
                if self.run_invocation(load, leg, inv) != "ok":
                    return "incomplete"
        self.require_load_complete(load)
        return "ok"

    def require_load_complete(self, load):
        """The cell is complete only when `chain_rows` scores every expected slot of the load (sha re-checked)."""
        doc = dict(progress=self.progress, dnf=[])
        try:
            table = cr.load_slots(doc, self.out_root)
        except cr.ChainRowsError as exc:
            raise co.ChainAbort(f"the progress inventory does not load: {exc}") from None
        expected = [cr.slot_for(leg["slot_base"], i) for leg in load["legs"] for inv in leg["invocations"]
                    for i in inv["expect"]]
        missing = table.unscored(expected)
        if missing:
            raise co.ChainAbort(f"load {load['session']}/{load['model']} complete but {len(missing)} slots are unscored: "
                                f"{missing[:3]}")

    # -- archive / quarantine
    def _stamp(self):
        return time.strftime("%Y%m%dT%H%M%S", time.gmtime())

    def _move_prefix(self, sdir, prefix, dest):
        dest.mkdir(parents=True, exist_ok=True)
        for f in sorted(sdir.iterdir()):
            if f.is_file() and f.name.startswith(prefix):
                shutil.move(str(f), str(dest / f.name))
        return dest

    def _relpath(self, path):
        return Path(path).relative_to(self.out_root).as_posix()

    def _repoint(self, records, files_by_name, dest, status):
        """Rewrite the `file` / `manifest` of the records whose files moved to `dest`, set `status`."""
        for rec in records:
            base = Path(rec["file"]).name[:-len(".jsonl")] + "."
            if any(n.startswith(base) for n in files_by_name):          # a probe that never wrote its rows file moved too
                for key in ("file", "manifest"):
                    rec[key] = self._relpath(Path(dest) / Path(rec[key]).name)
            rec["status"] = status

    def _mark_archived(self, load, rec, dest, names):
        gen = rec["load_gen"]
        mine = [i for i in self.progress["invocations"] if i["leg_key"][0] == load["idx"] and i["load_gen"] == gen
                and i["status"] not in ("archived", "quarantined")]
        self._repoint(mine, names, dest, "archived")
        for key in ("slot_attempts", "pre_spawn"):
            for r in self.progress[key]:
                if r.get("load") == load["idx"] and r.get("load_gen") == gen:
                    r["status"] = "archived"

    def archive_load(self, load, resume=False):
        """`restart_load`: the load's files go to `<session>/incomplete/<model>.<ts>/`. The sha manifest is recorded in
        chain.json (fsynced) BEFORE the first file moves; the load's records are marked `archived` (paths rewritten to the
        archive, shas kept), they leave the active inventory, and the load's generation advances."""
        rec = load["rec"]
        sdir = self.session_dir(load)
        dest = sdir / "incomplete" / f"{load['model']}.{self._stamp()}"
        prefix = f"{load['model']}.{load['session']}.opencode_"
        files = [f for f in sorted(sdir.iterdir()) if f.is_file() and f.name.startswith(prefix)] if sdir.exists() else []
        manifest = {f.name: sha_file(f) for f in files}
        rec["archives"].append(dict(dir=self._relpath(dest), at=co.utc_stamp(), files=manifest, load_gen=rec["load_gen"]))
        self.write_json("archiving")
        self._move_prefix(sdir, prefix, dest)
        self._mark_archived(load, rec, dest, manifest)
        rec["load_gen"] += 1
        rec["status"] = "pending"
        rec["cursor"] = dict(leg_index=0, phase=None)
        self.write_json("archived")
        return dest

    def quarantine(self, records):
        """Never-validated invocation files -> `quarantine/<ts>/` with a sha256 manifest written FIRST."""
        dest = self.out_root / "quarantine" / self._stamp()
        files = {}
        for rec in records:
            base = (self.out_root / rec["file"]).name[:-len(".jsonl")]
            for f in sorted((self.out_root / rec["file"]).parent.glob(base + ".*")) if (self.out_root / rec["file"]).parent.exists() else []:
                if f.is_file():
                    files[f.name] = f
        dest.mkdir(parents=True, exist_ok=True)
        fsync_json(dest / "MANIFEST.json", dict(at=co.utc_stamp(), files={n: sha_file(f) for n, f in files.items()}))
        for name, f in files.items():
            shutil.move(str(f), str(dest / name))
        self._repoint(records, files, dest, "quarantined")
        self.write_json("quarantined")
        return dest

    def archive_stopped(self, load, leg):
        sdir = self.session_dir(load)
        dest = sdir / "stopped" / f"{leg['stem']}.{self._stamp()}"
        names = {f.name for f in sdir.iterdir() if f.is_file() and f.name.startswith(leg["stem"] + ".")}
        self._move_prefix(sdir, leg["stem"] + ".", dest)
        mine = [i for i in self.progress["invocations"] if i["leg_key"][:2] == [load["idx"], leg["lang"]]
                and i["load_gen"] == load["rec"]["load_gen"] and i["status"] in ("running", "validated")]
        for rec in mine:
            was = rec["status"]
            self._repoint([rec], names, dest, "quarantined" if was == "running" else "archived")
        return dest

    # -- invocation (a leg attempt)
    def invocation_paths(self, load, leg, inv):
        n = self.attempt_no.get(leg["stem"], 0) + 1
        sdir = self.session_dir(load)
        rows = sdir / cr.rows_name(leg["stem"], leg["li"], inv["phase"], n)
        base = Path(str(rows)[:-len(".jsonl")])
        return n, sdir, rows, base

    def register_invocation(self, load, leg, inv, n, rows, ids):
        rec = dict(leg_key=[load["idx"], leg["lang"], leg["li"]], phase=inv["phase"], attempt=n,
                   worker_n=len(load["rec"]["workers"]) - 1, file=self._relpath(rows),
                   manifest=self._relpath(rows.with_suffix(".manifest.json")), status="running",
                   expected_slots=[cr.slot_for(leg["slot_base"], i) for i in ids], accepted_slots=[], sha256=None,
                   load_gen=load["rec"]["load_gen"], slot_base=leg["slot_base"])
        self.progress["invocations"].append(rec)
        return rec

    def prior_rows(self, load, leg):
        """Validated rows files of this leg's earlier invocations (for the watch log's cell totals)."""
        files, ids = [], []
        for rec in self.progress["invocations"]:
            if (rec["leg_key"] == [load["idx"], leg["lang"], leg["li"]] and rec["load_gen"] == load["rec"]["load_gen"]
                    and rec["status"] in cr.COUNTED_STATUSES):
                files.append(self.out_root / rec["file"])
                ids += [s.split("|")[-1] for s in rec["expected_slots"]]
        return files, ids

    def before_invocation(self, load, leg, inv):
        """Seam (3b): the place the chain hooks / arm switch run before a probe is spawned."""

    def run_invocation(self, load, leg, inv):
        self.verify_lifecycle("launch")
        n, sdir, out, base = self.invocation_paths(load, leg, inv)
        sdir.mkdir(parents=True, exist_ok=True)
        self.attempt_no[leg["stem"]] = n
        cancel, ack = Path(str(base) + ".CANCEL"), Path(str(base) + ".ACK")
        logp, ajson = Path(str(base) + ".log"), Path(str(base) + ".json")
        if cancel.exists() or ack.exists():
            raise co.ChainAbort(f"stale cancel/ack file for attempt path {base.name}")
        if out.exists() or out.with_suffix(".manifest.json").exists():
            raise co.ChainAbort(f"stale rows file or manifest for attempt path {out.name} (rows files are immutable)")
        cur = self.ops.worker_ident(leg["model"])
        if not cur or (cur["pid"], cur["create_time"]) != (load["worker"]["pid"], load["worker"]["create_time"]):
            raise co.ChainAbort("worker identity changed before launch")
        if not self.ops.power_ok():
            raise co.ChainAbort("power gate FAIL before launch")
        if leg["lang"] == "go" and not self.ops.docker_ok():
            raise co.ChainAbort("docker gate FAIL before launch")                                    # P290
        self.before_invocation(load, leg, inv)
        ids = list(inv["expect"])
        view = dict(leg, out=str(out), model=leg["model"], phase=inv["phase"], model_load=load["idx"])
        view["prior_files"], view["prior_ids"] = self.prior_rows(load, leg)
        step = dict(inv, names=list(inv["names"]))
        cmd = build_cmd(self.py, self.probe, view, step, load["receipt"], cancel, ack, scaffold=self.arm.label,
                        universe=self.universe, frozen=self.frozen, attempt=n, rerun_index=0)
        att = dict(attempt=n, step=inv["phase"], stem=leg["stem"], argv=cmd, cancel=str(cancel), ack=str(ack),
                   log=str(logp), worker=dict(load["worker"]), started=co.utc_stamp(), rc=None,
                   cleanup_status=None, run_id=None, probe_pid=None, probe_create_time=None, outcome=None)
        rec = self.register_invocation(load, leg, inv, n, out, ids)
        self.attempts.append(att)
        self.write_json("running")                      # the invocation is in the inventory BEFORE its probe exists
        self.log(f"START {leg['stem']} attempt {n} ({inv['phase']}, {len(ids)} items): {' '.join(cmd[2:])}")
        with logp.open("ab") as lf:
            proc = subprocess.Popen(cmd, cwd=str(self.repo), env=self.ops.env_base(), stdout=lf,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        att["probe_pid"] = proc.pid
        try:
            att["probe_create_time"] = self.ops.create_time(proc.pid)
        except Exception:  # noqa: BLE001
            pass
        co.atomic_json(ajson, att)
        self.write_json("running")
        sup = self.supervise(att, proc, view, step, load)
        att["rc"] = proc.returncode
        man = self._manifest(view)
        if man and att["run_id"] and man.get("run_id") == att["run_id"]:
            att["cleanup_status"] = receipt_from_manifest(man)
            att["cancelled_item"] = man.get("cancelled_item")
            att["transport_abort"] = man.get("transport_abort")
        att["outcome"] = sup["state"]
        co.atomic_json(ajson, att)
        self.log(f"END {leg['stem']} attempt {n} rc={att['rc']} state={sup['state']}")
        self.write_json("attempt-ended")
        if sup["state"] == "barrier_mismatch":
            self.listing(att, view)
            raise co.ChainAbort("first-manifest mismatch: " + "; ".join(sup["reasons"]))
        self.verify_lifecycle("validation")
        vleg = dict(session=leg["session"], model=leg["model"], lang=leg["lang"], seed_base=leg["seed_base"],
                    expected_ids=ids, out=str(out), rc=att["rc"], draft_kind=leg.get("draft_kind", "off"),
                    arm_identity_sha256=self.arms.get(self.arm_key(leg)))
        why = co.validate_leg(vleg, self.pinned, self.ops.wd, policy_sha=self.expected_policy,
                              frozen_prompt_date=self.frozen)
        if not why:
            self.pin_from(view)
            att["outcome"] = "validated"
            co.atomic_json(ajson, att)
            self.accept_invocation(load, leg, inv, rec, out)
            return "ok"
        for w in why:
            self.log(f"INCOMPLETE {leg['stem']} attempt {n}: {w}")
        if sup["stop"]:
            dest = self.archive_stopped(load, leg)
            self.log(f"STOP: partial leg archived to {dest}")
            self.stop_info["where"] = "leg"
            self.write_json("stopped")
            raise Stopped("leg")
        self.check_restart_eligible(att, view, load)
        return self.handle_incomplete(load, leg, inv, rec, att, why)

    def handle_incomplete(self, load, leg, inv, rec, att, why):
        """`abort_restart` (tg1): the whole load is archived once and rerun, then the chain aborts."""
        if self.config.transport_policy != "abort_restart":
            raise NotImplementedError(f"transport_policy {self.config.transport_policy!r} is a phase 3b configuration")
        return "incomplete"

    def accept_invocation(self, load, leg, inv, rec, out):
        """A validated invocation: sha256 recorded AFTER validation (fsynced), then the chain-side web evidence."""
        rows = cr.read_rows(out)
        rec["accepted_slots"] = list(rec["expected_slots"])
        rec["sha256"] = sha_file(out)
        rec["status"] = "validated"
        self.write_json("invocation-validated")
        self.after_invocation(load, leg, inv, rec, rows)

    def after_invocation(self, load, leg, inv, rec, rows):
        """Chain-side web evidence for every row with a stored transcript; the sha256 is recorded per slot attempt."""
        rules = self.web_rules()
        for row in rows:
            slot = cr.slot_for(rec["slot_base"], row["id"])
            tp = row.get("transcript_path")
            path = co.resolve_portable(tp, self.wd) if tp else None
            dest = path.with_name(path.stem + ".web.jsonl") if path is not None else None
            w = self.web_record(row, rules, dest)
            self.progress["slot_attempts"].append(dict(
                slot=slot, rerun_index=0, disposition="accepted", load=load["idx"], load_gen=rec["load_gen"],
                output_tokens=(row.get("gate") or {}).get("output_tokens_completed"), web_evidence=w))
        self.write_json("web-evidence")

    def web_record(self, row, rules, dest):
        """`web_evidence.extract` for one row (the transcript's sha256 re-verified first); no transcript -> `unavailable`."""
        tp = row.get("transcript_path")
        path = co.resolve_portable(tp, self.wd) if tp else None
        sha = (row.get("evidence_sha256") or {}).get("export")
        try:
            out = we.extract(rules, path, sha, dest)
        except (we.TranscriptShaMismatch, we.WebEvidenceError) as exc:
            raise co.ChainAbort(f"web evidence: {exc}") from None
        if "path" in out:
            out = dict(out, path=self._portable(out["path"]))
        return out

    def _portable(self, path):
        s = str(path)
        w = str(self.wd)
        return "$STACK_WORKDIR" + s[len(w):] if s.startswith(w) else s

    def pin_from(self, leg):
        man = self._manifest(leg) or {}
        bad = co.malformed_identity(man)
        if bad:
            raise co.ChainAbort(f"first complete leg has absent/null/malformed identity fields: {bad}")
        missing = []
        ident = co.runtime_identity(man)                 # P276: where the real probe writes each pinned field
        for k in co.RUNTIME_PINNED:
            if k in self.pinned:
                continue
            if k in ident:
                self.pinned[k] = ident[k]
            else:
                missing.append(k)
        if "serving_path" not in self.pinned:
            sp = (man.get("git") or {}).get("serving_path")
            if sp:
                self.pinned["serving_path"] = sp
            else:
                missing.append("serving_path")
        if missing:
            raise co.ChainAbort(f"first complete leg lacks pinned identity fields: {missing}")

    def _manifest(self, leg):
        try:
            return json.loads(Path(leg["out"]).with_suffix(".manifest.json").read_text())
        except (OSError, ValueError):
            return None

    def listing(self, att, leg):
        for line in self.ops.leftovers([str(self.ops.tmpdir)], [att.get("run_id")] if att.get("run_id") else []):
            self.log("LEFTOVER (listed, not killed): " + line)

    def check_restart_eligible(self, att, leg, block):
        why = []
        cs = att.get("cleanup_status")
        # P276b: the real probe writes `cleanup_status` only on an abort; a clean exit (rc 0, `exited`, no transport
        # abort) is reachable only after a completed, certain cleanup, so it is its own receipt
        clean_exit = (att.get("rc") == 0 and att.get("outcome") == "exited" and not att.get("transport_abort"))
        if not isinstance(cs, dict):
            if not clean_exit:
                why.append("cleanup uncertain: no cleanup_status recorded")
        else:
            if cs.get("survivors"):
                why.append("cleanup uncertain: survivors recorded")
            if cs.get("containers_remaining"):
                why.append("cleanup uncertain: containers remaining")
            if cs.get("uncertain") is not False:
                why.append("cleanup uncertain: uncertain flag set")
        fl = co.in_flight(self.ops.worker_metrics() or {})
        if fl != 0:
            why.append(f"worker health: metrics unreadable or in_flight={fl}")
        ident = self.ops.worker_ident(leg["model"])
        if not ident or (ident["pid"], ident["create_time"]) != (block["worker"]["pid"], block["worker"]["create_time"]):
            why.append("worker health: identity changed or worker gone")
        if why:
            self.listing(att, leg)
            raise co.ChainAbort("restart refused: " + "; ".join(why))

    # -- barrier
    @staticmethod
    def arm_key(leg):
        return f"{leg['model']}|{leg.get('draft_kind', 'off')}"

    def verify_manifest(self, man, leg, block):
        why = []
        problems = self.lifecycle_problems()
        if problems:
            why.append(f"lifecycle drift at barrier: {'; '.join(problems)}")
        problem = self.campaign_problem() if getattr(self, "campaign_core", None) is not None else None
        if problem:
            why.append(f"{problem} (at barrier)")
        frozen_arm = self.arms.get(self.arm_key(leg))
        if frozen_arm is not None and (man.get("runtime") or {}).get("arm_identity_sha256") != frozen_arm:
            why.append(f"arm_identity_sha256: {(man.get('runtime') or {}).get('arm_identity_sha256')!r} != frozen "
                       f"{frozen_arm!r} for {self.arm_key(leg)}")
        rt, wk = man.get("runtime") or {}, man.get("worker")
        chk = [("scaffold", rt.get("scaffold"), self.arm.label),
               ("scaffold_policy_sha256", rt.get("scaffold_policy_sha256"), self.expected_policy),
               ("frozen_prompt_date", rt.get("frozen_prompt_date"), self.frozen),
               ("draft_kind", rt.get("draft_kind"), leg.get("draft_kind", "off")),
               ("seed_base", rt.get("seed_base"), leg["seed_base"]),
               ("lang", rt.get("lang"), leg["lang"]), ("model", man.get("model"), leg["model"]),
               ("sampling_profile", rt.get("sampling_profile", man.get("sampling_profile")), "deployed"),
               ("registry.sha256", (man.get("registry") or {}).get("sha256"), self.ops.overlay_sha())]
        ident = co.runtime_identity(man)
        for k in co.RUNTIME_PINNED:
            if k in self.pinned:
                chk.append((k, ident.get(k, "<absent>"), self.pinned[k]))
        if self.pinned.get("serving_path") is not None:
            chk.append(("git.serving_path", (man.get("git") or {}).get("serving_path"), self.pinned["serving_path"]))
        for k, got, want in chk:
            if got != want:
                why.append(f"{k}: {got!r} != {want!r}")
        if self.a.probe_code_sha is None and self.pinned.get("probe_code_sha256") is None and not rt.get("probe_code_sha256"):
            why.append("probe_code_sha256 absent")
        if not co.typed_worker(wk):
            why.append("worker identity untyped")
        else:
            if (wk["pid"], wk["create_time"]) != (block["worker"]["pid"], block["worker"]["create_time"]):
                why.append("worker identity differs from the block's loaded instance")
            if block.get("manifest_worker") and wk != block["manifest_worker"]:
                why.append("worker identity differs from the block's first manifest")
            if wk["registry_sha256"] != self.ops.overlay_sha():
                why.append("worker registry_sha256 differs from the overlay")
        if man.get("transport_abort"):
            why.append("manifest already records transport_abort")
        why += [f"{f}_invalid" for f in co.malformed_identity(man)]
        return why

    def _barrier(self, att, leg, block, st, t_spawn):
        mp = Path(leg["out"]).with_suffix(".manifest.json")
        man = None
        try:
            man = json.loads(mp.read_text())
        except (OSError, ValueError):
            pass
        if not man or not man.get("run_id") or man["run_id"] in self.seen_run_ids:
            return
        why = self.verify_manifest(man, leg, block)
        self.seen_run_ids.add(man["run_id"])
        att["run_id"] = man["run_id"]
        if why:
            st["reasons"] = why
            self.log(f"BARRIER MISMATCH {leg['stem']}: {'; '.join(why)} -- no ack")
            return
        if self.a.probe_code_sha is None and self.pinned.get("probe_code_sha256") is None:
            self.pinned["probe_code_sha256"] = (man["runtime"] or {}).get("probe_code_sha256")
            self.log(f"pilot: probe_code_sha256 pinned from first manifest {self.pinned['probe_code_sha256']}")
        runtime = man["runtime"] or {}
        if "generation_identity_sha256" not in self.pinned:       # P311-lite: the shared composite, at the first manifest
            self.pinned["generation_identity_sha256"] = runtime.get("generation_identity_sha256")
            self.log(f"generation_identity_sha256 pinned from first manifest {self.pinned['generation_identity_sha256']}")
        if self.arm_key(leg) not in self.arms:                    # one arm identity per (model, predictor)
            self.arms[self.arm_key(leg)] = runtime.get("arm_identity_sha256")
            self.log(f"arm {self.arm_key(leg)}: arm_identity_sha256 frozen from first manifest "
                     f"{self.arms[self.arm_key(leg)]}")
        self.write_json("barrier-ok")
        block["manifest_worker"] = block.get("manifest_worker") or man["worker"]
        Path(att["ack"]).write_text("ack\n")
        st["barrier_done"] = True
        att["worker_full"] = man["worker"]
        self.log(f"BARRIER ok {leg['stem']} run_id={man['run_id']}: ack created")

    # -- supervise
    def evidence_root(self, leg, att):
        if not att.get("run_id"):
            return None
        return Path(self.ops.wd) / self.evidence_namespace / leg["model"] / f"{Path(leg['out']).stem}.{att['run_id']}"

    def _signals(self, att, leg, block):
        """Activity inputs for the idle predicate and the escalation re-evaluation."""
        root = self.evidence_root(leg, att)
        ev = dir_bytes(root) if root and root.exists() else 0
        out = Path(leg["out"])
        try:
            s = out.stat()
            rows_sig = (s.st_size, s.st_mtime_ns)
        except OSError:
            rows_sig = None
        metrics = self.ops.worker_metrics()
        ident = self.ops.worker_ident(leg["model"])
        key = (ident["pid"], ident["create_time"]) if ident else None
        if key and key != (block["worker"]["pid"], block["worker"]["create_time"]):
            self.log("ALARM worker identity changed during the leg")
            key = None
        return dict(events_bytes=ev, rows_sig=rows_sig, metrics=metrics, ident=key)

    def _cancel(self, att, st, reason, hb, leg, tcoop=None):
        Path(att["cancel"]).write_text(reason + "\n")
        t = tcoop if tcoop is not None else co.t_coop(hb.last_prompt(), leg["lang"]) * self.tm.t_coop_scale
        st["cancel_at"], st["tcoop"], st["stage"] = self.clock(), t, 0
        st["deadline"] = st["cancel_at"] + t
        st["base"] = None
        st["cancel_reason"] = reason
        if reason == "STOP":
            st["stop"] = True
        self.log(f"CANCEL file written ({reason}) for {Path(att['cancel']).name}; T_coop={t:.0f}s "
                 f"(last_prompt_tokens={hb.last_prompt()}, lang={leg['lang']})")

    def _escalate(self, att, proc, st, hb, leg, block):
        now = self.clock()
        hb.poll()
        if st["base"] is None:
            st["base"], st["base_hb"] = self._signals(att, leg, block), hb.line
        if now < st["deadline"]:
            return
        cur = self._signals(att, leg, block)
        fl = co.in_flight(cur["metrics"]) if cur["metrics"] is not None else None
        if cur["ident"] is None or fl is None:
            self.listing(att, leg)
            raise co.ChainAbort("restart refused: worker identity drift or unreadable metrics at escalation; "
                                "no signal sent")
        resumed = (cur["events_bytes"] != st["base"]["events_bytes"] or cur["rows_sig"] != st["base"]["rows_sig"]
                   or fl != 0 or hb.line != st["base_hb"])
        if resumed:
            self.log(f"ESCALATION HELD (stage {st['stage']}): activity resumed (events/rows/heartbeat changed or "
                     f"in_flight={fl}); waiting another {st['tcoop']:.0f}s")
            st["base"], st["base_hb"], st["deadline"] = cur, hb.line, now + st["tcoop"]
            return
        if st["stage"] == 0:
            self.log(f"ESCALATE SIGTERM probe pid {proc.pid} (cleanup-only path)")
            os.kill(proc.pid, signal.SIGTERM)
            st["stage"], st["deadline"] = 1, now + self.tm.term_wait_s
        elif st["stage"] == 1:
            self.log(f"ESCALATE SIGKILL probe pid {proc.pid}")
            os.kill(proc.pid, signal.SIGKILL)
            st["stage"], st["deadline"] = 2, now + self.tm.kill_wait_s
        else:
            raise co.ChainAbort(f"probe pid {proc.pid} survived SIGKILL")
        st["base"], st["base_hb"] = cur, hb.line

    def supervise(self, att, proc, leg, step, block):
        clock, tm = self.clock, self.tm
        t0 = clock()
        hb = Heartbeat(att["log"], clock, t0)
        idle = co.IdlePredicate(tm.idle_sample_s, tm.hb_age_s, tm.idle_needed)
        st = dict(barrier_done=False, reasons=None, cancel_at=None, tcoop=None, stage=0, deadline=None, base=None,
                  stop=False, cancel_reason=None)
        halt = threading.Event()

        def loop():
            while not halt.wait(tm.watch_s):
                try:
                    self.stop_requested()
                    self.watch_tick(att, leg, step, block, hb, st, t0)
                except Exception as e:  # noqa: BLE001
                    self.log(f"WATCH error {type(e).__name__}: {e}")

        th = threading.Thread(target=loop, daemon=True)
        th.start()
        last_idle = t0
        try:
            while proc.poll() is None:
                now = clock()
                hb.poll()
                # P308: once a cancel is pending the probe may write its abort manifest (transport_abort) before it
                # exits; that is the cancel's outcome, validated after exit, never a first-manifest mismatch
                if not st["barrier_done"] and st["reasons"] is None and st["cancel_at"] is None:
                    self._barrier(att, leg, block, st, t0)
                    if st["reasons"] is not None:
                        self._cancel(att, st, "barrier mismatch", hb, leg, tcoop=tm.barrier_exit_wait_s)
                if st["cancel_at"] is None and self.stop_requested():
                    self._cancel(att, st, "STOP", hb, leg)
                if st["cancel_at"] is None and st["barrier_done"] and now - last_idle >= tm.idle_sample_s:
                    last_idle = now
                    sg = self._signals(att, leg, block)
                    if idle.sample(now, hb_age=hb.age(), **sg):
                        hb.poll()
                        if idle.recheck(hb_age=hb.age(), **self._signals(att, leg, block)):
                            self._cancel(att, st, "idle", hb, leg)
                        else:
                            self.log("idle predicate recheck failed: activity resumed, no cancel")
                if st["cancel_at"] is not None:
                    self._escalate(att, proc, st, hb, leg, block)
                time.sleep(tm.poll_s)
        finally:
            halt.set()
            th.join(5)
        state = "barrier_mismatch" if st["reasons"] else ("cancelled" if st["cancel_at"] is not None else "exited")
        return dict(state=state, reasons=st["reasons"] or [], stop=st["stop"], cancel_reason=st["cancel_reason"])

    # -- watcher
    def watch_rows(self, leg, step):
        """(rows, ids) the watch log counts: the leg's earlier validated invocations plus this one's file."""
        ids = list(leg.get("prior_ids") or []) + [f"{leg['lang']}/{x}" for x in step["names"]]
        rows = []
        for f in leg.get("prior_files") or []:
            try:
                rows += self.ops.rows(f)
            except Exception:  # noqa: BLE001
                pass
        try:
            rows += self.ops.rows(leg["out"])
        except Exception:  # noqa: BLE001
            pass
        return [r for r in rows if r.get("id") in ids], ids

    def watch_tick(self, att, leg, step, block, hb, st, t0):
        rows, ids = self.watch_rows(leg, step)
        n, total = len(rows), len(ids)
        walls = [r.get("wall_s") or 0 for r in rows]
        mean = sum(walls) / n if n else None
        key = (leg["lang"], leg["model"])
        if key in self.explicit_pred:
            pred = self.explicit_pred[key]
        elif n >= PILOT_N:
            pred = sum(walls[:PILOT_N]) / PILOT_N       # default: the pilot mean once >= 5 rows exist
        else:
            pred = self.pred.get(key, 250)
        m = mean if mean is not None else pred
        remaining = total - n
        eta = remaining * m
        ratio = (eta / (remaining * pred)) if remaining and pred else (m / pred if pred else 0)
        kinds = {}
        for r in rows:
            k = r.get("nonconv_kind") or "ok"
            kinds[k] = kinds.get(k, 0) + 1
        conv = (sum(bool(r.get("converged")) for r in rows) / n) if n else None
        toks = [((r.get("gate") or {}).get("output_tokens_completed") or 0) for r in rows]
        bhits = sum(1 for r in rows if "budget" in str(r.get("nonconv_kind")) or "budget" in str(r.get("nonconv_flags")))
        ps = self.ops.power_state()
        free = self.ops.free_mem_mb()
        hb.poll()
        w = hb.watch()
        elapsed = self.clock() - t0
        alarm = co.alarm_s(remaining, m, max(walls) if walls else 0)
        try:
            logtext = Path(att["log"]).read_text(errors="replace")
        except OSError:
            logtext = ""
        aborts = "TransportAbort" in logtext or "REFUSED" in logtext
        flags = []
        if ratio > 1.5 or aborts:
            flags.append("CORRECTION?")
        if elapsed > alarm:
            flags.append(f"ALARM elapsed={elapsed:.0f}s>{alarm:.0f}s")
        if not st["barrier_done"] and elapsed > self.tm.manifest_alarm_s and st["reasons"] is None:
            flags.append(f"ALARM manifest missing/unacked after {elapsed:.0f}s")
        self.log(
            f"WATCH {leg['stem']} a{att['attempt']}: {n}/{total} passed={sum(bool(r.get('passed')) for r in rows)} "
            f"mean={m:.0f}s eta={eta/60:.0f}min pred={pred:.0f}s ratio={ratio:.2f} kinds={kinds} "
            f"conv={'n/a' if conv is None else f'{conv:.0%}'} out_tok_p50/p90/max={quantile(toks,.5)}/{quantile(toks,.9)}/"
            f"{max(toks) if toks else None} budget_hits={bhits} adapter={ps['watts']}W {ps['volts']}V "
            f"batt={ps['batt']}% free_mem_mb={free} hb_age={hb.age():.0f}s hb={json.dumps(w, sort_keys=True)} "
            f"hb_elapsed={hb.data.get('elapsed_s')} {' '.join(flags)}".rstrip())
