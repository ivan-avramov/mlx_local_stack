"""P371 phase 3a / 3b (plan 3.1 `chain_core`): THE chain core. The tg1 chain (C147 / M63 / P340 / P364 / P311-lite) and the M64
chain (spec 8) run on it, generalized over a `run_config.ChainConfig`; a chain ENTRY is a thin CLI + out-root rules that builds
the config and the ops.

What the core owns: the lifecycle freeze (the entry's static import closure + the serialized ChainConfig + the A4 gate + the
launchers, R15, frozen in chain.json at creation and verified before every launch, barrier, validation, resume and at exit),
the C179 campaign-core check, the frozen prompt date, the probe-derived policy sha, the A5 epoch / snapshots, immutable A4
receipts per worker (re)load and arm (A10), STOP, the run loop, loads / legs / invocations, the first-manifest barrier ack,
the item barrier answered with `ChainHooks` (R13 R23 R25 R29), supervision (idle predicate, escalation, watch log), validation +
pinning, the transport policy, archive / quarantine / resume, the persisted progress inventory (`bench.chain_rows`) and the
chain-side web evidence.

Layout (plan 4 A8): ONE immutable rows file per leg INVOCATION, `<session>/<stem>.L<leg>.<phase>.a<n>.jsonl` (+ manifest, +
`.log` / `.json` / `.CANCEL` / `.ACK`, + `.item<k>.<kind>` barrier files). Every invocation is registered in
`chain.json.progress.invocations` (status `running`) BEFORE the probe is spawned, and its sha256 is recorded after validation.

Configurations (plan 3.2):
  * tg1 (`abort_restart` / `restart_load`, builder `tg1`, flat record): an interrupted load's never-validated files go to
    `quarantine/` (sha manifest first), the rest of the load is archived (sha manifest recorded in chain.json FIRST), its
    records are marked `archived`, and the load reruns from leg 0 with `load_gen + 1`; a transport failure archives and
    restarts the load once, then aborts.
  * M64 (`incident_retry` / `new_segment`, builder `blocks`, per-arm record): a leg is one (block, arm) over the items of the
    block. A transport incident (`chain_incident`: router + worker checked independently, then the client's cause; the EXACT
    cleanup schema; the partial rows validated -> `partial_incident` with the accepted prefix) recovers the worker (unload +
    reload, A4 per arm, cache reset, warm-up) and retries the SAME slot in a new `retry` invocation; a second incident in a slot
    is a `transport_dnf` row (sidecar + chain.json copy). A hook disposition (`rerun_same_slot`) is a one-slot `rerun`
    invocation (index + 1, max 2, then the slot is `exhausted`: a strict fail); `block` stops the chain for the operator.
    A resume takes a FRESH worker and continues at the progress cursor with only the unaccepted slots; partial / never-validated
    invocation files are quarantined (sha manifest first) unless the persisted dispositions prove an accepted prefix.
  * tg2 (`tg2_tier`, flat record, tg1 semantics): the frozen seed-6501 draw artifact (sha + tier in schedule.json and the
    ChainConfig) is verified at every leg.
Exit codes: 0 done, 2 chain abort (listing printed, nothing killed), 3 STOP latch honoured, 1 unexpected error."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from . import arm_adapter as aa
from . import arm_specs
from . import atomic_publish
from . import chain_hooks
from . import chain_incident as ci
from . import chain_ops as co
from . import chain_rows as cr
from . import contract_artifact as ca
from . import datefreeze
from . import run_config
from . import schedules
from . import web_evidence as we
from .chain_incident import (CLEANUP_KEYS, INCIDENT_CAUSES, classify_incident_cause, cleanup_problems, dnf_row,  # noqa: F401
                             incident_tokens, slot_key, slot_tokens, validate_dnf_row)

PICK1, PICK2 = co.PICK1, co.PICK2
SCAFFOLD = co.SCAFFOLD
PRED_S = {("python", PICK1): 244, ("go", PICK1): 300, ("python", PICK2): 267, ("go", PICK2): 360}   # M59 table (M64 / tg2 only)
GENERIC_PRED_S = 250       # C221: the tg1 chain's per-item prediction for a model with no pilot mean yet (recorded in its ChainConfig)
PILOT_N = 5
# P279 --smoke: a short live rehearsal of the real schedule (rows are rehearsal evidence only, never graded or pooled)
SMOKE_PILOT_N, SMOKE_FULL_N, SMOKE_ARM_IDLE_S = 1, 2, 60.0
NAMED_LIFECYCLE = ("runner", "chain_ops", "gate", "launcher", "launch_tg1")     # the pre-P371 chain.json lifecycle names
TG1_SEEDS_ORDER = ("s1", "s2", "reload")
# B2 spec 3: the manifest of every invocation of `tg1-p426` carries exactly this evidence policy (= the probe's
# `tg1_runner.TG1_P426_EVIDENCE`; a test pins the equality, the chain never imports a probe module)
P426_SETTLE_BOUND_S = 900.0     # B2 spec 4.2: the floor of the settle bound (v8 base raises it from the rehearsal walls)
# B2 s5: the ChainOps seams the receipt, the pair gate, the snapshot checks and the busy census need (spec 16.2 / 16.5)
P426_SEAMS = ("proc_argv", "proc_environ", "interpreter_inventory", "loaded_images", "snapshot_hashes", "expected_worker_argv",
              "busy_procs", "descendants", "create_time", "worktree_state",
              "interpreter_inventory_at")      # spec 16.2 / 16.4 / 16.6 (+ the path form for an interpreter without a process)
P426_ENTRY_SEAMS = ("last_leg_end", "power_state", "start_state", "listeners")   # B2 s7: the ChainOps seams of the Entry row (spec 16.4); never skipped
P426_POWER = dict(watts=140, volts=28, batt_above=20)                  # spec 8 / AGENTS: 140 W / 28 V, battery > 20 %
P426_EVIDENCE_POLICY = run_config.EvidencePolicy(namespace="opencode_transcripts", web_evidence=True, final_tree=True,
                                                 worker_receipts="absent", item_barrier="on").as_dict()


class RecordInvalid(co.ChainAbort):
    """An existing chain.json is not a complete valid record: refuse and leave it untouched (L4)."""


class EntryRefused(co.ChainAbort):
    """B2 (P426): an entry check failed before the router started (NOT_STARTED, spec 5.1): logged as `REFUSED: <reason>`
    (spec 16), rc 2, nothing launched."""


class LegInvalid(co.ChainAbort):
    """B2 (P426): an `invalidate` disposition (or a systemic hook error) stopped the leg: it is INVALID, rc 2."""


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


_PORTABLE_TOKENS = re.compile(r"<OUT>|<WT>|\$STACK_WORKDIR|\$HOME")


def portable_doc(obj, *, out_root, workdir, worktree, home=None):
    """B2 spec 16.8 (portable `chain.json`): `obj` with every string's `out_root` / `worktree` / `workdir` / `home` path replaced by
    `<OUT>` / `<WT>` / `$STACK_WORKDIR` / `$HOME` (longest root first, at a path boundary), so a `main` record carries no absolute
    path of this box. Paths and other path-likes become strings; other scalars pass unchanged."""
    from bench.p426_receipt import Canon
    canon = Canon(worktree, out_root, workdir=workdir, home=home)

    def walk(v):
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [walk(x) for x in v]
        if isinstance(v, os.PathLike):
            v = os.fspath(v)
        return canon.text(v) if isinstance(v, str) else v
    return walk(obj)


def expand_doc(obj, *, out_root, workdir, worktree, home=None):
    """The inverse of `portable_doc` for a resumed chain: the tokens back to this box's paths."""
    roots = {"<OUT>": out_root, "<WT>": worktree, "$STACK_WORKDIR": workdir, "$HOME": home}

    def sub(m):
        root = roots[m.group(0)]
        return str(root) if root else m.group(0)

    def walk(v):
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return _PORTABLE_TOKENS.sub(sub, v) if isinstance(v, str) else v
    return walk(obj)


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


def probe_rel(repo, given):
    """F7: the repo-relative POSIX path of a probe entry (`--probe`). A relative path is the repository's (the chain spawns the
    probe with cwd = the repository); an entry that is not a file inside the repository refuses (its closure could not be
    named in the campaign core)."""
    repo = Path(repo).resolve()
    path = Path(given)
    path = (path if path.is_absolute() else repo / path).resolve()
    if not path.is_relative_to(repo) or not path.is_file():
        raise Refused(f"REFUSED: --probe must name a file inside the repository (got {Path(given).name!r})")
    return path.relative_to(repo).as_posix()


# --------------------------------------------------------------------------- probe command
INJECT_STALL_S = 30             # spec 16.8: the lowered stall limit of the rehearsal's `stall-kill` injection


def build_cmd(py, probe, leg, step, receipt, cancel, ack, *, scaffold, universe=None, frozen=None, out=None, attempt=None,
              rerun_index=None, epoch=None, nonce=None, evidence=None, inject_stall=None):
    ids =[f"{leg['lang']}/{n}" for n in step["names"]]
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
    if nonce:                                       # P384: the chain-issued per-invocation binding nonce
        cmd += ["--invocation-nonce", nonce]
    if attempt is not None:                         # P371 A8: the invocation's attempt number (worker receipt attempt id)
        cmd += ["--attempt", str(attempt), "--attempt-rerun-index", str(rerun_index or 0)]
    if evidence:                                    # B2: the probe's evidence policy (P426 mode only)
        cmd += ["--evidence", evidence]
    if inject_stall:                                # B2 spec 16.8: `--inject stall-kill`: (`<lang>/<item>`, seconds), one item only
        cmd += ["--inject-stall-item", inject_stall[0], "--inject-stall-s", str(inject_stall[1])]
    return cmd


def barrier_signal(path, payload=None):
    """The chain's side of `bench.item_barrier`: `.go` / `.continue` / `.stop` are created exclusively and written COMPLETE
    before they become visible (the probe never reads a partial file). `payload` (a JSON object) is the `.stop` disposition."""
    path = Path(path)
    body = b"" if payload is None else (json.dumps(payload, sort_keys=True) + "\n").encode()
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(body)
    try:
        os.link(tmp, path)
    except FileExistsError:
        raise co.ChainAbort(f"barrier file {path.name} already exists") from None
    finally:
        tmp.unlink(missing_ok=True)


# --------------------------------------------------------------------------- the chain
class Chain:
    def __init__(self, config, args, ops, timers, log, *, repo, out_root, names, lifecycle_files, campaign=None, hooks=None,
                 needs_docker=None):
        self.config = config
        self.repo = Path(repo)
        self.a, self.ops, self.tm, self.log = args, ops, timers, log
        self.lifecycle_files = dict(lifecycle_files)
        self.campaign = campaign
        self.hooks = hooks or self.default_hooks(config, args, ops, out_root)
        self.needs_docker = needs_docker or (lambda lang: lang == "go")
        self.builder = config.schedule["builder"]
        self.per_arm = self.builder == "blocks"                 # per-arm record layout (M64); tg1 / tg2 keep the flat one
        self.arm_ids = [b.arm for b in config.arms]
        self.bindings = {b.arm: b for b in config.arms}
        self.specs = {}                       # arm -> ArmSpec (per-arm layout only; tg1 keeps the pre-P371 constants)
        self.campaign_core = None             # {tag, commit, probe_closure_sha256, chain_closure_sha256} or None (C179)
        self.lifecycle = None                 # frozen at chain creation (init_lifecycle), never recomputed
        self.arms = {}                        # "<model>|<predictor>" -> arm_identity_sha256, frozen at the first manifest
        self.out_root, self.stop_path = Path(out_root), Path(out_root) / "STOP"
        self.names = names
        self.clock = time.monotonic
        self.py = Path(args.python)
        self.wd = Path(ops.wd)
        # a key is present once pinned; a pinned None (e.g. agent_system_sha256 without an overlay) is a value
        self.expected_policy = None           # flat: P362, derived from the probe's --print-identity at chain start, frozen
        self.policies = {}                    # per-arm: arm -> scaffold_policy_sha256
        self.frozen = None                    # P364: the date the client shows the model; epoch metadata, frozen in chain.json
        self.frozen_source = None
        self.pinned = {}                      # flat layout
        self.pinned_by_arm = {}               # per-arm layout: arm -> pinned fields; shared: serving_path, registry_sha256
        self.pinned_shared = {}
        self.snapshots = {}                   # arm -> {sha256, complete} (A5), frozen at chain creation
        self.epoch_id = None                  # computed from every arm's snapshot (A5)
        self.universe = Path(args.universe).resolve() if args.universe else None
        if self.per_arm:
            self.probe = None
            self.pinned_by_arm = {arm: {"probe_code_sha256": self.arm_arg("probe_code_sha", arm)} for arm in self.arm_ids}
        else:
            self.probe = self.repo / config.arms[0].probe
            if args.probe_code_sha:
                self.pinned["probe_code_sha256"] = args.probe_code_sha
            if getattr(args, "generation_sha", None):
                self.pinned["generation_identity_sha256"] = args.generation_sha
        self.attempts, self.restarts, self.stop_info = [], [], None
        self.attempt_no, self.seen_run_ids, self.block_workers = {}, set(), []
        self.progress = dict(loads=[], invocations=[], slot_attempts=[], pre_spawn=[], txns=[], abort_evidence=[])
        self.incidents, self.dnf, self.realized = [], [], []
        self.p426_dnf, self.p426_ledger, self.p426_invalid = [], [], []      # `p426_continue`: DNF records, ledger, INVALID records
        self.schedule, self.schedule_sha = None, None
        self.loads, self.snapshot_tools = [], {}
        self.loaded = None
        self.rc = None
        # C221: the tg1 chain has no per-model table (models come from --models): the pilot mean, else GENERIC_PRED_S
        self.pred, self.explicit_pred = ({} if self.builder == "tg1" else dict(PRED_S)), {}
        for spec in args.pred_s or []:
            key, val = spec.rsplit("=", 1)
            lang, model = key.split(":", 1)
            self.explicit_pred[(lang, model)] = float(val)

    # -- the chain config's arms
    @property
    def arm(self):
        return self.config.arms[0]

    def arm_arg(self, name, arm):
        """An entry argument that is per-arm in the per-arm layout (a dict ARM -> value) and one value in the flat one."""
        value = getattr(self.a, name, None)
        return value.get(arm) if isinstance(value, dict) else value

    def probe_of(self, arm):
        # F12: always the resolved repo-relative entry frozen in the ChainConfig, never the raw `--probe` path (a symlink
        # retargeted after init would otherwise launch code outside the frozen closure)
        return self.repo / self.bindings[arm].probe

    def label_of(self, arm):
        return self.bindings[arm].label

    def spec_of(self, arm):
        return self.specs.get(arm)

    def pinned_for(self, arm):
        return {**self.pinned_by_arm[arm], **self.pinned_shared} if self.per_arm else self.pinned

    def policy_for(self, arm):
        return self.policies[arm] if self.per_arm else self.expected_policy

    def runtime_pinned(self, arm):
        return self.specs[arm].runtime_pinned if self.per_arm else co.RUNTIME_PINNED

    def web_rules(self, arm=None):
        return arm_specs.spec_for(self.bindings[arm or self.arm_ids[0]].arm_spec).web_evidence_rules

    def resolve_specs(self):
        """Per-arm layout: refuse an arm that has no chain spec BEFORE anything starts."""
        if self.per_arm:
            for arm in self.arm_ids:
                self.specs[arm] = arm_specs.spec_for(self.bindings[arm].arm_spec)

    def contract_refs(self):
        return {a.arm: dict(path=a.path, sha256=a.sha256) for a in self.config.contract_artifacts}

    def contract_problems(self):
        """A13 / R8 / P374: why an arm's contract artifact must be refused NOW (a list; empty = every arm's is accepted).
        Only the per-arm layout (M64) runs against contract artifacts; tg1 / tg2 name none. A non-smoke chain needs an
        artifact with verdict `pass` for EVERY arm; a smoke chain may run an arm with no artifact named or an `incomplete`
        one, but never a failed, missing, malformed or drifted one. The artifact must be of the arm's frozen snapshot, and its
        file sha256 must still be the one frozen at chain creation (a replacement mid-chain is drift, valid or not)."""
        if not self.per_arm:
            return []
        smoke = bool(getattr(self.a, "smoke", False))
        refs = {r.arm: r for r in self.config.contract_artifacts}
        out = []
        for arm in self.arm_ids:
            ref = refs.get(arm)
            if ref is None:
                if not smoke:
                    out.append(f"no contract artifact named for arm {arm} (--contract-artifact {arm}=PATH; "
                               f"benchmark/m64/contract_artifact.py --arm {arm})")
                continue
            out += ca.problems(ref.path, arm=arm, file_sha256_frozen=ref.sha256, smoke=smoke,
                               snapshot_sha256=(self.snapshots.get(arm) or {}).get("sha256"))
        return out

    def verify_contract(self, where):
        problems = self.contract_problems()
        if problems:
            raise co.ChainAbort(f"contract artifact check failed at {where}: {'; '.join(problems)}")

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
        if self.per_arm:
            for key in ("arm_generations", "policies"):
                if not isinstance(doc.get(key), dict):
                    return f"{key} absent or malformed"
            if not all(hexed(v) for v in {**doc["arm_generations"], **doc["policies"]}.values()):
                return "an identity is absent, null or malformed"
            if not hexed(doc.get("epoch_id")) or not hexed(doc.get("schedule_sha256")):
                return "epoch_id or schedule_sha256 absent or malformed"
            for key in ("incidents", "dnf", "realized"):
                if not isinstance(doc.get(key), list):
                    return f"{key} absent"
        else:
            if "generation_identity_sha256" in pinned and not hexed(pinned["generation_identity_sha256"]):
                return "pinned generation_identity_sha256 malformed"
            if not hexed(doc.get("policy_sha256")):
                return "policy_sha256 absent, null or malformed"
            if pinned.get("scaffold_policy_sha256") != doc["policy_sha256"]:
                return "pinned scaffold_policy_sha256 missing or differs from policy_sha256"
            if self.freezes_schedule and not hexed(doc.get("schedule_sha256")):
                return "schedule_sha256 absent or malformed"
        if not isinstance(doc.get("snapshots"), dict) or "epoch_id" not in doc:
            return "snapshots / epoch_id absent"
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

    @staticmethod
    def default_hooks(config, args, ops, out_root):
        """B2: `tg1-p426` installs the P426 reconciliation hooks (spec 16.2); every other chain keeps the no-op hooks."""
        if config.transport_policy != "p426_continue":
            return chain_hooks.ChainHooks()
        from bench import p426_hooks              # lazy: only P426 mode needs it
        arm = "ON" if str(getattr(args, "predictor", "off")).lower() in ("on", "mtp") else "OFF"
        return p426_hooks.P426Hooks(ops=ops, out_root=out_root, arm=arm, settle_bound_s=Chain.p426_settle_bound(args),
                                    inject=getattr(args, "inject", None))

    @staticmethod
    def p426_settle_bound(args):
        """Spec 4.2: the settle bound of the frozen record the leg runs under: the timeout amendment's, else the v8 base's; a
        rehearsal manifest (or no readable record) carries none, so the 900 s floor holds."""
        path = getattr(args, "frozen_record", None)
        if path:
            from bench import p426_record
            try:
                rec = p426_record.load(path, mode=args.mode, rehearsal=bool(getattr(args, "rehearsal", False)))
            except p426_record.RecordError as exc:           # a bad record refuses, never the 900 s floor (P41)
                raise Refused(f"REFUSED: --frozen-record {exc}") from None
            bound = rec["doc"].get("settle_bound_s") or rec["base"].get("settle_bound_s")      # the amendment, else v8 base
            if bound:
                return float(bound)
        return getattr(args, "settle_bound_s", None) or P426_SETTLE_BOUND_S

    # -- B2 whole-leg log boundaries (spec 4.2)
    def p426_open_log_bounds(self):
        """`log_bounds.json`, exclusive-created BEFORE the router starts: path, device, inode and byte offset of the worker
        log and the main-model log (an absent file is created empty so its identity is fixed before the router appends)."""
        from bench.p426_hooks import portable_log
        path = Path(self.ops.server_log_path())
        files = []
        self.p426_bound_paths = {}
        for p in (path, path.with_name("main_model.log")):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()
            st = p.stat()
            portable = portable_log(p)                       # a `main` record: `<WT>/logs/<name>` (spec 16.7)
            self.p426_bound_paths[portable] = p
            files.append(dict(path=portable, device=st.st_dev, inode=st.st_ino, offset_start=st.st_size, offset_end=None))
        target = self.out_root / "log_bounds.json"
        try:
            with open(target, "x") as f:
                json.dump(dict(files=files, created=co.utc_stamp(), finalized=None), f, indent=1)
        except FileExistsError:
            raise co.ChainAbort(f"{target.name} exists: a leg runs on a fresh out-root (log boundaries are exclusive-created)") from None
        self.p426_bounds_open = True

    def p426_close_log_bounds(self):
        """Finalize `log_bounds.json` after teardown: `offset_end` per file, or null + `problems` for a truncated or replaced
        file (the leg is then INVALID, rc 2; the harvest refuses it)."""
        if not getattr(self, "p426_bounds_open", False):
            return
        target = self.out_root / "log_bounds.json"
        doc, problems = json.loads(target.read_text()), []
        for entry in doc["files"]:
            try:
                st = os.stat(self.p426_bound_paths[entry["path"]])
            except OSError as exc:
                entry["offset_end"] = None
                problems.append(f"{entry['path']} is gone: {exc}")
                continue
            if (st.st_dev, st.st_ino) != (entry["device"], entry["inode"]) or st.st_size < entry["offset_start"]:
                entry["offset_end"] = None
                problems.append(f"{entry['path']} was replaced or truncated during the leg")
            else:
                entry["offset_end"] = st.st_size
        doc["finalized"] = co.utc_stamp()
        if problems:
            doc["problems"] = problems
        co.atomic_json(target, doc)
        if problems:
            self.log("LOG BOUNDS: " + "; ".join(problems))
            if not self.rc:
                self.rc = 2

    # -- B2 receipt, pair gate, snapshot checks and busy census (spec 3, 6.3 - 6.5, 16.5); every failure is systemic (ChainAbort)
    def p426_require_seams(self):
        """In P426 mode a ChainOps seam the checks need that is missing is systemic, never a skip (spec 16.7)."""
        missing = [n for n in P426_SEAMS if not callable(getattr(self.ops, n, None))]
        if missing:
            raise co.ChainAbort(f"TRIPWIRE: P426 mode needs the ChainOps seams {missing}; a missing seam is systemic, never skipped")

    def p426_log_offset(self):
        return os.stat(self.ops.server_log_path()).st_size

    def p426_check_a4_window(self, start, receipt_path):
        """Spec 4.3: the worker-log window of the A4 gate run (3 `anon:*` requests + its own 4-request `ses_*` session) equals
        the A4 run's `gate.json` (`<STACK_WORKDIR>/c102a/gate.json`, the gate's default workdir) and its A4 receipt."""
        from bench import p426_reconcile as prc
        try:
            path = self.ops.server_log_path()
            window = self.ops.read_log(path, start, os.stat(path).st_size)
            receipt = json.loads(Path(receipt_path).read_text())
            gate = json.loads((Path(self.ops.wd) / "c102a" / "gate.json").read_text())
            problems = prc.a4_window_problems(prc.parse_log(window), receipt, gate)
        except (OSError, ValueError) as exc:             # includes the log parse error: an unparseable line is systemic
            raise co.ChainAbort(f"A4 window: its evidence is unreadable ({type(exc).__name__}: {exc})") from None
        if problems:
            raise co.ChainAbort("A4 window: " + "; ".join(problems))

    def p426_roots(self):
        return dict(out_root=self.out_root, workdir=getattr(self.ops, "wd", None),
                    worktree=getattr(self.ops, "repo", None) or getattr(self, "repo", None), home=Path.home())

    def p426_persist(self, doc):
        """A record the chain writes under the out-root: portable in P426 mode (spec 16.8; a `main` record), as is otherwise."""
        return portable_doc(doc, **self.p426_roots()) if self.p426 else doc

    def p426_worktree(self):
        """The served worktree: the one the ops serve (`ChainOps.repo`), never the chain's own checkout under injected ops."""
        return Path(getattr(self.ops, "repo", None) or self.repo)

    def p426_bind_router(self, pid):
        """The owned router's identity `(pid, ChainOps.create_time(pid))`, taken when this process starts it (spec 3 / 16.6)
        and compared at every checkpoint; the hooks compare the same identity at each barrier."""
        if type(pid) is not int:
            raise co.ChainAbort("TRIPWIRE: start_router gave no owned router pid (P426 needs it for the identity checks)")
        self.p426_router = dict(pid=pid, start=self.ops.create_time(pid))
        bind = getattr(self.hooks, "bind_router", None)
        if bind is not None:
            bind(pid, self.p426_router["start"])
        bind_ready = getattr(self.hooks, "bind_ready_checks", None)
        if bind_ready is not None:
            bind_ready(self.p426_ready_problems)

    def p426_router_problems(self):
        from bench.p426_hooks import same_identity
        r = getattr(self, "p426_router", None)
        if r is None:
            return ["no owned router identity was recorded"]
        return [] if same_identity(self.ops, r["pid"], r["start"]) else ["owned router identity changed or the router is gone"]

    def p426_state_problems(self, entry=False):
        """The entry checks that hold for the life of the leg (spec 3, 'Before every invocation'): the frozen record's kind and
        self-hash, the worktree at the record's arm commit, clean and with the fork gitlinks the record names, the registry sha,
        the probe's live identity. At `entry` nothing is pinned yet: the registry only has to be readable (it is pinned next)."""
        from bench import p426_record
        try:
            rec = p426_record.load(self.a.frozen_record, mode=self.a.mode, rehearsal=bool(getattr(self.a, "rehearsal", False)))
        except p426_record.RecordError as exc:
            return [f"frozen record: {exc}"]
        base, problems = rec["base"], []
        want = base.get(f"{self.p426_arm_name()}_commit")
        st = self.ops.worktree_state(self.p426_worktree())
        if want and st.get("head") != want:
            problems.append(f"worktree HEAD {str(st.get('head'))[:12]} != the record's {self.p426_arm_name()} commit {want[:12]}")
        if st.get("clean") is not True:
            problems.append("worktree is not clean (git status, submodules at their gitlinks)")
        links, have = base.get("gitlinks"), st.get("gitlinks") or {}
        for key, path in (("mlx_vlm", "src/mlx-vlm"), ("mlx_serve", "src/mlx-serve")):
            if isinstance(links, dict) and links.get(key) and have.get(path) != links[key]:
                problems.append(f"gitlink {path} {str(have.get(path))[:12]} != the record's {str(links[key])[:12]}")
        sha = self.ops.overlay_sha()
        if entry:
            if not (isinstance(sha, str) and co.HEX64.match(sha)):
                problems.append("the served registry is unreadable (no sha256)")
        elif sha != self.pinned.get("registry_sha256"):
            problems.append("the served registry's sha256 changed since the chain started")
        ident = self.print_identity(self.arm_ids[0])
        for key in ("probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256"):
            if base.get(key) and ident.get(key) != base[key]:
                problems.append(f"probe identity {key} differs from the record's")
        return problems

    def p426_arm_name(self):
        return "on" if getattr(self.a, "predictor", "off") == "mtp" else "off"

    def p426_snapshot_checks(self, snapshots, where):
        from bench import p426_receipt as pr
        try:
            problems = pr.snapshot_problems(snapshots, pr.load_pins(self.p426_worktree()), self.a.models[0], self.p426_arm_name())
        except pr.ReceiptError as exc:
            problems = [str(exc)]
        if problems:
            raise co.ChainAbort(f"snapshots {where}: " + "; ".join(problems))

    def p426_entry_row(self):
        """Spec 3 Entry row, before anything starts (the CLI calls it before `run`, holding `LEG.lock`): every seam exists (never a
        skip), the frozen record (kind, self-hash), the worktree (HEAD == the record's arm commit, clean, gitlinks), the registry
        sha, the probe's live identity, >= 600 s since `LAST_LEG_END`, no foreign busy process (that includes `session_cache_probe` /
        `opencode run` survivors), no :8000 listener, power. Any failure is `EntryRefused` (NOT_STARTED, rc 2) naming every problem.
        The snapshots against the pins and the log boundaries stay in `run` (`p426_entry_checks`, `p426_open_log_bounds`)."""
        from bench import p426_locks
        try:
            self.p426_require_seams()
            absent = [n for n in P426_ENTRY_SEAMS if not callable(getattr(self.ops, n, None))]
            if absent:
                raise co.ChainAbort(f"TRIPWIRE: P426 mode needs the ChainOps seams {absent}; a missing seam is systemic, never skipped")
            problems = self.p426_state_problems(entry=True)
            gap = p426_locks.idle_gap_problem(self.ops.last_leg_end(), time.time())
            if gap:
                problems.append(gap)
            busy = list((self.ops.start_state() or {}).get("busy") or [])
            if busy:
                problems.append("foreign busy process before the router: " + "; ".join(busy)[:300])
            listening = list(self.ops.listeners() or [])
            if listening:
                problems.append(f":8000 already has a listener {listening}")
            ps = self.ops.power_state() or {}
            if not (ps.get("watts") == P426_POWER["watts"] and ps.get("volts") == P426_POWER["volts"]
                    and ps.get("batt") is not None and ps["batt"] > P426_POWER["batt_above"]):
                problems.append(f"power: adapter {ps.get('watts')} W / {ps.get('volts')} V, battery {ps.get('batt')} % "
                                f"(needs {P426_POWER['watts']} W / {P426_POWER['volts']} V, battery > {P426_POWER['batt_above']} %)")
        except EntryRefused:
            raise
        except co.ChainAbort as exc:
            raise EntryRefused(str(exc)) from None
        if problems:
            raise EntryRefused("; ".join(problems))

    def p426_ready_problems(self):
        """Spec 3, Item `ready` row (besides the owned identities, which the hooks check): the registry sha equals the one pinned
        at entry, the lifecycle hash (the chain's code and ChainConfig) has not drifted, the worktree is still clean."""
        problems = []
        if self.ops.overlay_sha() != self.pinned.get("registry_sha256"):
            problems.append("the served registry's sha256 changed since the chain started")
        problems += [f"lifecycle: {p}" for p in self.lifecycle_problems()]
        if self.ops.worktree_state(self.p426_worktree()).get("clean") is not True:
            problems.append("worktree is not clean (git status, submodules at their gitlinks)")
        return problems

    def p426_entry_checks(self):
        """Entry (before the router): every seam the P426 checks need exists (never a skip); the target (and, ON, drafter)
        snapshot revisions and file hashes equal the fork's pins."""
        try:
            self.p426_require_seams()
            self.p426_snapshot_checks(self.ops.snapshot_hashes(self.a.models[0]), "at entry")
        except EntryRefused:
            raise
        except co.ChainAbort as exc:
            raise EntryRefused(str(exc)) from None

    def p426_census(self, where, load=None):
        """No foreign busy process: the owned router / worker are exempt by (pid, start), the chain's own descendants by
        `ChainOps.descendants`; a worker process is exempt ONLY as the owned worker (a descendant `mlx_vlm.server` is foreign)."""
        from bench.p426_hooks import same_identity
        owned = {}
        router = getattr(self, "p426_router", None)
        if router and same_identity(self.ops, router["pid"], router["start"]):
            owned[router["pid"]] = "router"
        worker = (load or {}).get("worker")
        if worker and same_identity(self.ops, worker["pid"], worker["create_time"]):
            owned[worker["pid"]] = "worker"
        kids = set(self.ops.descendants(os.getpid()))
        foreign = []
        for line in self.ops.busy_procs():
            head = line.split(None, 1)
            pid = int(head[0]) if head and head[0].isdigit() else None
            is_worker = "mlx_vlm.server" in line or "mlx_vlm/server" in line
            if pid in owned and (owned[pid] == "worker") == is_worker:
                continue
            if pid in kids and not is_worker:
                continue
            marker = next((m for m in co.BUSY if m in line), "busy")
            foreign.append(f"pid {pid} ({marker})")
        if foreign:
            raise co.ChainAbort(f"TRIPWIRE: foreign busy process {where}: " + "; ".join(foreign))

    def p426_after_load(self, load, ident):
        """After load (spec 3), before the A4 gate: the foreign-process census, the worker argv exact (6.3), the arm-equality
        receipt (6.4, exclusive-created at `<out-root>/receipt.json`), the receipt's snapshots against the pins, and for the
        second leg of a pair the comparison with the first leg's receipt (6.5)."""
        from bench import p426_hooks as ph
        from bench import p426_receipt as pr
        arm = self.p426_arm_name()
        router = getattr(self, "p426_router", None)
        if not router or self.p426_router_problems():
            raise co.ChainAbort("owned router identity changed or missing after load (systemic)")
        self.p426_census("after load", load)
        problems = pr.worker_argv_problems(self.ops.proc_argv(ident["pid"]),
                                           self.ops.expected_worker_argv(self.ops.overlay, load["model"]), arm)
        if problems:
            raise co.ChainAbort("worker argv: " + "; ".join(problems))
        launch = dict(argv=[str(self.py), str(self.probe_of(self.arm_ids[0]))], env=self.ops.env_base())
        try:
            receipt = pr.arm_receipt(self.ops, worktree=self.p426_worktree(), out_root=self.out_root, model=load["model"], probe_launch=launch,
                                     pids=dict(router=router["pid"], worker=ident["pid"], probe=None))
        except pr.ReceiptError as exc:
            raise co.ChainAbort(f"arm-equality receipt: {exc}") from None
        try:
            ph.write_exclusive(self.out_root / "receipt.json", receipt)
        except FileExistsError:
            raise co.ChainAbort("receipt.json exists: a leg runs on a fresh out-root (the receipt is exclusive-created)") from None
        self.log(f"RECEIPT {arm} sha256={receipt['sha256'][:16]} credential keys={ {p: len(k) for p, k in receipt['credential_keys'].items()} }")
        self.p426_snapshot_checks(receipt["snapshots"], "after load")
        first_path = getattr(self.a, "pair_receipt", None)
        if first_path:
            try:
                first = json.loads(Path(first_path).read_text())
            except (OSError, ValueError):
                raise co.ChainAbort("pair gate: the first leg's receipt is unreadable") from None
            diff = pr.pair_problems(first, receipt)
            if diff:
                raise co.ChainAbort("pair gate: " + "; ".join(diff))
            self.log(f"PAIR GATE passed (observed differences: {pr.observed_differences(first, receipt)})")

    def p426_before_invocation(self, load):
        """Before every invocation (spec 3): the entry checks except router absence, the idle gap and power - the frozen record's
        kind and self-hash, the worktree HEAD and cleanliness, the registry sha, the probe's identity, the snapshots against
        the pins - the owned router / worker identities `(pid, create_time(pid))`, and no foreign busy process."""
        problems = self.p426_state_problems() + self.p426_router_problems()
        cur = self.ops.worker_ident(load["model"])
        if not cur or (cur["pid"], cur["create_time"]) != (load["worker"]["pid"], load["worker"]["create_time"]):
            problems.append("owned worker identity changed or the worker is gone")
        if problems:
            raise co.ChainAbort("before launch (systemic): " + "; ".join(problems))
        self.p426_census("before launch", load)
        self.p426_snapshot_checks(self.ops.snapshot_hashes(self.a.models[0]), "before launch")

    @property
    def p426(self):
        """The `p426_continue` transport policy (only `tg1-p426` uses it): its own flat-layout leg loop, DNF records, ledger."""
        return self.config.transport_policy == "p426_continue"

    @property
    def freezes_schedule(self):
        return self.builder in ("blocks", "tg2_tier") or self.config.config_id == run_config.P426_CONFIG_ID

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
            if self.p426:
                previous = expand_doc(previous, **self.p426_roots())          # written portable (spec 16.8): back to this box's paths
            problem = self.record_problem(previous)
            if problem:
                raise RecordInvalid(f"existing chain.json is not a complete valid record ({problem}); use a new out-root")
            if previous["chain_config"] != self.config.as_dict() or previous["lifecycle"]["chain_config"] != self.config.sha256():
                raise RecordInvalid("chain_config differs from the chain's frozen chain_config (a changed chain needs a "
                                    "new out-root)")
            self.lifecycle = previous["lifecycle"]
            self.arms = dict(previous["arms"])
            self.load_record(previous)
            self.expected_policy = previous.get("policy_sha256")
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
        self.progress.setdefault("txns", [])
        self.progress.setdefault("abort_evidence", [])
        self.attempts = list(previous.get("attempts") or [])
        self.seen_run_ids = (set(self.progress.get("seen_run_ids") or [])
                             | {a["run_id"] for a in self.attempts if a.get("run_id")})      # F16: rebuilt + verified at resume
        self.restarts = list(previous.get("restarts") or [])
        self.block_workers = list(previous.get("block_workers") or [])
        self.snapshots = dict(previous["snapshots"])
        self.epoch_id = previous["epoch_id"]
        if self.per_arm or self.freezes_schedule:
            self.schedule_sha = previous.get("schedule_sha256")
            self.realized = list(previous.get("realized") or [])
        if self.per_arm:
            self.policies = dict(previous["policies"])
            for arm, pinned in previous["pinned"].items():
                if arm == "shared":
                    self.pinned_shared = dict(pinned)
                elif arm in self.pinned_by_arm:
                    self.pinned_by_arm[arm].update(pinned)
        else:
            composite = previous["pinned"].get("generation_identity_sha256")
            if composite and "generation_identity_sha256" not in self.pinned:
                self.pinned["generation_identity_sha256"] = composite
        if self.config.transport_policy == "incident_retry":
            self.incidents, self.dnf = list(previous.get("incidents") or []), list(previous.get("dnf") or [])
        elif self.p426:
            self.p426_dnf, self.p426_ledger = list(previous.get("p426_dnf") or []), list(previous.get("p426_ledger") or [])
            self.p426_invalid = list(previous.get("p426_invalid") or [])
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

    # -- identities: the probe's policy (P362) and snapshot (A5)
    def print_identity(self, arm):
        """The arm's probe `--print-identity` document (read-only: no router, worker or model is touched)."""
        cmd = [str(self.py), str(self.probe_of(arm)), "--print-identity"]
        if self.per_arm:
            cmd += ["--scaffold", self.label_of(arm)]
        if self.universe:
            cmd += ["--universe", str(self.universe)]
        who = f"{arm}: " if self.per_arm else ""
        try:
            got = subprocess.run(cmd, cwd=str(self.repo), env=self.ops.env_base(), capture_output=True, text=True,
                                 timeout=300, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise co.ChainAbort(f"{who}probe --print-identity could not run ({type(exc).__name__})") from None
        lines = [ln for ln in got.stdout.splitlines() if ln.strip()]
        try:
            doc = json.loads(lines[-1]) if got.returncode == 0 and lines else None
        except ValueError:
            doc = None
        if not isinstance(doc, dict):
            doc = {}
        if not (isinstance(doc.get("scaffold_policy_sha256"), str) and co.HEX64.match(doc["scaffold_policy_sha256"])):
            raise co.ChainAbort(f"{who}probe --print-identity gave no valid scaffold_policy_sha256 (rc {got.returncode}"
                                + (f": {(got.stderr or got.stdout)[-200:].strip()}" if self.per_arm else "") + ")")
        return doc

    def derive_policy(self):
        """P362: the expected scaffold_policy_sha256 is what the configured probe reports for THIS box (its policy embeds
        the grader image id and toolchain lock), asked with the chain's --universe. A supplied --policy-sha is an
        assertion against it; a frozen value (resume) must still equal it. A5: every arm's snapshot and the epoch computed
        from them are frozen / verified here too."""
        docs = {arm: self.print_identity(arm) for arm in self.arm_ids}
        for arm, doc in docs.items():
            value = doc["scaffold_policy_sha256"]
            who = f"{arm}: " if self.per_arm else ""
            asserted = self.arm_arg("policy_sha", arm)
            if asserted and asserted != value:
                raise co.ChainAbort(f"{who}supplied --policy-sha {asserted} != the probe's policy {value}")
            frozen = self.policies.get(arm) if self.per_arm else self.expected_policy
            if frozen and frozen != value:
                raise co.ChainAbort(f"{who}frozen policy {frozen} != the probe's policy now {value}" + (
                    "" if self.per_arm else " (toolchain or universe changed; a changed chain needs a new out-root)"))
            if self.per_arm:
                self.policies[arm] = value
                self.pinned_by_arm[arm]["scaffold_policy_sha256"] = value
                self.log(f"policy[{arm}]: scaffold_policy_sha256 {value} derived from the probe's --print-identity")
            else:
                self.expected_policy = value
                self.pinned["scaffold_policy_sha256"] = value
                self.log(f"policy: scaffold_policy_sha256 {value} derived from the probe's --print-identity")
        self.freeze_snapshots(docs)

    @staticmethod
    def parse_snapshot(arm, doc):
        sha = doc.get("snapshot_sha256")
        if sha is None:
            return None
        if not (isinstance(sha, str) and co.HEX64.match(sha) and isinstance(doc.get("snapshot_complete"), bool)
                and isinstance(doc.get("snapshot_tool"), str) and doc["snapshot_tool"]):
            raise co.ChainAbort(f"{arm}: probe --print-identity reports a malformed snapshot")
        return dict(tool=doc["snapshot_tool"], sha256=sha, complete=doc["snapshot_complete"])

    def epoch_of(self, snaps):
        return aa.epoch_id([SimpleNamespace(tool=s["tool"], sha256=s["sha256"]) for s in snaps.values()])

    def freeze_snapshots(self, docs):
        """A5: the epoch is COMPUTED from every arm's snapshot; `--epoch-id` is an assertion. At creation the snapshots are
        frozen (an incomplete one refuses unless the config allows it); a resume refuses any change."""
        snaps = {arm: self.parse_snapshot(arm, doc) for arm, doc in docs.items()}
        absent = sorted(arm for arm, s in snaps.items() if s is None)
        if absent and (self.per_arm or self.config.snapshot_complete_required):
            raise co.ChainAbort(f"probe --print-identity of {absent} reports no snapshot (the client binary is missing?)")
        if self.config.snapshot_complete_required:
            incomplete = sorted(arm for arm, s in snaps.items() if s and not s["complete"])
            if incomplete:
                raise co.ChainAbort(f"snapshot of {incomplete} is incomplete: a registered epoch needs the complete "
                                    "snapshot (the snapshot tooling is owed; only --smoke may run without it)")
        now = {arm: (dict(sha256=s["sha256"], complete=s["complete"]) if s else dict(sha256=None, complete=None))
               for arm, s in snaps.items()}
        for arm, frozen in self.snapshots.items():
            if arm in now and now[arm]["sha256"] != frozen["sha256"]:
                raise co.ChainAbort(f"snapshot of arm {arm} changed since chain creation "
                                    f"({str(frozen['sha256'])[:12]} -> {str(now[arm]['sha256'])[:12]}; a changed chain needs "
                                    "a new out-root)")
        epoch = None if absent else self.epoch_of(snaps)
        asserted = getattr(self.a, "epoch_id", None)
        if asserted and asserted != epoch:
            raise co.ChainAbort(f"--epoch-id {asserted} differs from the epoch computed from the arms' snapshots {epoch}")
        if self.snapshots and self.epoch_id != epoch:
            raise co.ChainAbort(f"epoch {epoch} differs from the chain's frozen epoch {self.epoch_id}")
        self.snapshots, self.epoch_id = now, epoch
        self.snapshot_tools = {arm: s["tool"] for arm, s in snaps.items() if s}

    def verify_snapshots(self, where):
        """A5 at exit: every arm's probe is asked again; a changed snapshot aborts."""
        for arm in self.arm_ids:
            s = self.parse_snapshot(arm, self.print_identity(arm))
            frozen = (self.snapshots.get(arm) or {}).get("sha256")
            if frozen is not None and (s is None or s["sha256"] != frozen):
                raise co.ChainAbort(f"snapshot of arm {arm} changed during the chain (at {where}: {frozen[:12]} -> "
                                    f"{(s or {}).get('sha256', 'unavailable')[:12]})")

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
        self.verify_contract(where)

    # -- chain.json
    def sha256_block(self):
        lc = self.lifecycle or {}
        names = [n for n in NAMED_LIFECYCLE if n in self.lifecycle_files]
        return dict({n: lc.get(n) for n in names}, overlay=self.ops.overlay_sha())

    def record_layout(self):
        """The per-arm identity keys of the record. tg1 / tg2 (flat): `policy_sha256` / `pinned`; M64 (per-arm): `policies`,
        `pinned` per arm + `shared`, `arm_generations`, the frozen schedule, the incident / DNF / realized state."""
        if not self.per_arm:
            out = dict(policy_sha256=self.expected_policy, pinned=self.pinned, probe=str(self.probe))
            if self.freezes_schedule:
                out.update(schedule_sha256=self.schedule_sha, realized=self.realized)
            if self.p426:
                out.update(p426_dnf=self.p426_dnf, p426_ledger=self.p426_ledger, p426_invalid=self.p426_invalid,
                           frozen_record=self.p426_frozen_record_ref(), inject=getattr(self.a, "inject", None))
                if getattr(getattr(self, "a", None), "mode", None) == "makeup":
                    out["p426_not_run"] = self.p426_not_run()
            return out
        gens = {arm: p["generation_identity_sha256"] for arm, p in self.pinned_by_arm.items()
                if p.get("generation_identity_sha256")}
        return dict(policies=self.policies, pinned={**self.pinned_by_arm, "shared": self.pinned_shared},
                    arm_generations=gens, schedule_sha256=self.schedule_sha, arm_ids=self.arm_ids,
                    probes={arm: str(self.probe_of(arm)) for arm in self.arm_ids}, incidents=self.incidents, dnf=self.dnf,
                    realized=self.realized)

    def write_json(self, status=None):
        self.progress["seen_run_ids"] = sorted(self.seen_run_ids)         # F16: persisted, verified at resume
        doc = dict(status=status, mode=self.a.mode, argv=sys.argv[1:], updated=co.utc_stamp(),
                   sha256=self.sha256_block(), lifecycle=self.lifecycle, arms=self.arms,
                   frozen_prompt_date=self.frozen, frozen_prompt_date_source=self.frozen_source,
                   probe_code_sha=self.a.probe_code_sha,
                   attempts=self.attempts, restarts=self.restarts, stop=self.stop_info, rc=self.rc,
                   block_workers=self.block_workers, smoke=getattr(self.a, "smoke", False),
                   predictor=getattr(self.a, "predictor", "off"), chain_config=self.config.as_dict(),
                   progress=self.progress, epoch_id=self.epoch_id, snapshots=self.snapshots,
                   artifacts=dict(campaign_core=self.campaign_core, contract=self.contract_refs()), **self.record_layout())
        fsync_json(self.out_root / "chain.json", self.p426_persist(doc))

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

    # -- schedule: frozen and hashed before the first launch (blocks, tg2_tier), then normalized into loads -> legs
    def freeze_schedule(self):
        """Hash the schedule BEFORE launch; a resumed chain must regenerate exactly the frozen one. `blocks` (M64) and
        `tg2_tier` (the frozen draw artifact) and the tg1 chain in P426 mode (B2 spec 7: one leg = one session, its whole order);
        the legacy tg1 / pilot schedules depend on the run selection and are not frozen."""
        if not self.freezes_schedule:
            return
        sched = self.build_schedule()
        path = self.out_root / "schedule.json"
        if self.schedule_sha is not None:
            try:
                schedules.require_frozen(sched, self.schedule_sha)
            except ValueError as exc:
                raise co.ChainAbort(str(exc)) from None
        else:
            self.schedule_sha = schedules.schedule_sha256(sched)
            co.atomic_json(path, sched)
        self.schedule = sched
        self.write_json("schedule-frozen")

    def tg1_schedule(self):
        """The tg1 schedule of THIS invocation over the recorded `--models` (C221); P426 mode: the seeded order (spec 7)."""
        params = self.config.schedule["params"]
        try:
            if self.a.mode == "makeup":                       # spec 5.5: the occurrences file IS the plan (one fresh-load leg)
                return schedules.tg1_makeup(self.occurrence_records(), self.names, picks=tuple(params["models"]),
                                            predictor=getattr(self.a, "predictor", "off"))
            return schedules.tg1(self.a.mode, self.a.sessions, self.names, smoke=getattr(self.a, "smoke", False),
                                 predictor=getattr(self.a, "predictor", "off"), picks=tuple(params["models"]),
                                 p426=params.get("p426") is True, rehearsal=bool(getattr(self.a, "rehearsal", False)))
        except ValueError as exc:
            raise co.ChainAbort(f"the schedule cannot be built: {exc}") from None

    def p426_inject_stall(self, leg, step):
        """`--inject stall-kill` (rehearsal only, spec 16.8): the probe flags go to the ONE invocation holding the first Python item
        of the rehearsal schedule; every other invocation runs without them."""
        if not (self.p426 and getattr(self.a, "inject", None) == "stall-kill" and leg.get("lang") == "python"):
            return None
        first = next((l["full_names"][0] for b in (self.schedule or {}).get("blocks", []) for l in b["legs"]
                      if l["lang"] == "python" and l["full_names"]), None)
        return (f"python/{first}", INJECT_STALL_S) if first is not None and first in step["names"] else None

    def occurrence_records(self):
        """The make-up leg's occurrences (JSON lines, spec 16.7); an unreadable file aborts before anything launches."""
        try:
            records = [json.loads(x) for x in Path(self.a.occurrences).read_text().splitlines() if x.strip()]
        except (OSError, ValueError, TypeError):
            raise co.ChainAbort("the occurrences file is missing, unreadable or not JSON lines") from None
        if not records or not all(isinstance(r, dict) for r in records):
            raise co.ChainAbort("the occurrences file holds no occurrence records")
        return records

    def p426_not_run(self):
        """A make-up leg's slots with no entry in the realized ledger (a row or a DNF both count as run), in the frozen schedule's
        order: what an early stop leaves unrun (spec 5.5)."""
        done = {tuple(e["slot"].split("|")[3:6]) for e in self.p426_ledger}
        return [dict(session=leg["session"], language=leg["lang"], item=item, seed=leg["seed_base"])
                for block in (self.schedule or {}).get("blocks", []) for leg in block["legs"] for item in leg["full_names"]
                if (leg["session"], leg["lang"], item) not in done]

    def build_schedule(self):
        params = self.config.schedule["params"]
        if self.builder == "tg1":
            return self.tg1_schedule()
        if self.builder == "blocks":
            sessions = list(self.a.sessions)
            return schedules.blocks(
                self.arm_ids, self.names, picks=tuple(params.get("picks") or (PICK1, PICK2)),
                sessions=[s for s in sessions if s != "reload"], reload_control="reload" in sessions,
                langs=tuple(params.get("langs") or ("python", "go")),
                reload_langs=tuple(params.get("reload_langs") or ("python",)), smoke=getattr(self.a, "smoke", False))
        doc = self.tg2_draw_doc()
        try:
            return schedules.tg2_tier(doc, self.config.schedule["draw_sha256"], self.config.schedule["tier"],
                                      acknowledged=tuple(getattr(self.a, "tg2_acknowledged", ()) or ()))
        except schedules.TransportAbort as exc:
            raise co.ChainAbort(str(exc)) from None

    def tg2_draw_doc(self):
        try:
            return json.loads(Path(self.a.tg2_draw).read_text())
        except (OSError, ValueError, AttributeError) as exc:
            raise co.ChainAbort(f"the tg2 draw artifact cannot be read ({type(exc).__name__})") from None

    def verify_schedule(self, leg):
        """A1: a tg2 leg's items are re-derived from the frozen draw artifact at EVERY launch (never redrawn)."""
        if self.builder != "tg2_tier":
            return
        try:
            schedules.check_tg2_membership(self.schedule, self.tg2_draw_doc(), self.config.schedule["draw_sha256"],
                                           leg=dict(session=leg["session"], lang=leg["lang"],
                                                    items=[f"{leg['lang']}/{n}" for n in leg["items"]]))
        except schedules.TransportAbort as exc:
            raise co.ChainAbort(f"the tg2 draw artifact check failed at a leg: {exc}") from None

    def plan(self):
        """The schedule normalized into loads -> legs -> invocations (the per-builder 'plan')."""
        if self.builder == "tg1":
            return self.plan_tg1()
        if self.builder == "blocks":
            return self.plan_blocks()
        if self.builder == "tg2_tier":
            return self.plan_tg2()
        raise NotImplementedError(f"schedule builder {self.builder!r}")

    def plan_tg1(self):
        sched = self.schedule if self.freezes_schedule else self.tg1_schedule()       # P426: the FROZEN schedule
        loads = []
        for idx, block in enumerate(sched["blocks"]):
            legs = []
            for li, leg in enumerate(block["legs"]):
                legs.append(dict(
                    leg, li=li, pos=li, load=idx, arm=self.arm.arm, label=self.arm.label, items=list(leg["full_names"]),
                    slot_base=f"{self.config.config_id}|{self.arm.arm}|{leg['model']}|{leg['session']}|{leg['lang']}",
                    invocations=[dict(kind=i["phase"], phase=i["phase"], names=list(i["names"]), limit=i["limit"],
                                      expect=list(i["expect"])) for i in leg["invocations"]]))
                if self.freezes_schedule:        # P426: the leg-level ledger key (the per-item ledger is a later slice)
                    legs[-1]["realized_key"] = schedules.leg_key(dict(block=idx, lang=leg["lang"], model=block["model"],
                                                                      session=block["session"], items=leg["full_names"]))
            loads.append(dict(idx=idx, key=f"{block['session']}|{block['model']}", session=block["session"],
                              model=block["model"], seed_base=block["seed_base"], legs=legs,
                              pilot_only=block.get("pilot_only", False)))
        return loads

    def plan_blocks(self):
        """M64 (spec 8.1): one load per (session, pick); a leg is one (block, arm) = ONE planned `block` invocation over the
        block's items (incidents / re-runs split it dynamically at run time, `run_block_leg`)."""
        by_load = {}
        for sleg in schedules.legs(self.schedule):
            by_load.setdefault(sleg["load"], []).append(sleg)
        loads = []
        for li, sload in enumerate(self.schedule["loads"]):
            legs = []
            for pos, sleg in enumerate(by_load.get(li, [])):
                arm, lang, names = sleg["arm"], sleg["lang"], list(sleg["items"])
                legs.append(dict(
                    li=sleg["block"], pos=pos, load=li, block=sleg["block"], arm=arm, label=self.label_of(arm),
                    model=sleg["pick"], pick=sleg["pick"], session=sleg["session"], lang=lang,
                    seed_base=sleg["seed_base"], stem=f"{sleg['pick']}.{sleg['session']}.{arm}_{lang}", draft_kind="off",
                    items=names, residual=sleg["residual"], sched_leg=sleg, realized_key=schedules.leg_key(sleg),
                    slot_base=f"{self.epoch_id}|{arm}|{sleg['pick']}|{sleg['session']}|{lang}",
                    invocations=[dict(kind="block", phase="block", names=names, limit=None,
                                      expect=[f"{lang}/{n}" for n in names])]))
            loads.append(dict(idx=li, key=f"{sload['session']}|{sload['pick']}", session=sload["session"],
                              model=sload["pick"], seed_base=sload["seed_base"], legs=legs, pilot_only=False))
        return loads

    def plan_tg2(self):
        """tg2 (tg1 semantics): per session the picks in the tg1 order, one `full` invocation per (language) cell."""
        picks = tuple(self.config.schedule["params"].get("picks") or (PICK1, PICK2))
        order = {"s1": picks, "s2": tuple(reversed(picks)), "reload": picks[:1]}
        loads = []
        arm = self.arm
        for sess in self.schedule["sessions"]:
            for model in order[sess["session"]]:
                legs = []
                for li, cell in enumerate(sess["cells"]):
                    lang = cell["lang"]
                    names = [i.split("/", 1)[1] for i in cell["items"]]
                    legs.append(dict(
                        li=li, pos=li, load=len(loads), arm=arm.arm, label=arm.label, model=model, session=sess["session"],
                        lang=lang, seed_base=sess["seed_base"], stem=schedules.flat_stem(model, sess["session"], lang),
                        draft_kind=getattr(self.a, "predictor", "off"), items=names, full_names=names,
                        realized_key=schedules.leg_key(dict(session=sess["session"], lang=lang, items=cell["items"])) + [model],
                        slot_base=f"{self.config.config_id}|{arm.arm}|{model}|{sess['session']}|{lang}",
                        invocations=[dict(kind="full", phase="full", names=names, limit=None,
                                          expect=[f"{lang}/{n}" for n in names])]))
                loads.append(dict(idx=len(loads), key=f"{sess['session']}|{model}", session=sess["session"], model=model,
                                  seed_base=sess["seed_base"], legs=legs, pilot_only=False))
        return loads

    # -- run
    def run(self):
        try:
            self.resolve_specs()
        except aa.ArmRefused as e:
            self.log(f"CHAIN ABORT: {e}")
            self.rc = 2
            return 2
        try:
            self.init_lifecycle()
            self.recover_txns()                          # F4: an interrupted archive / quarantine completes before anything reads
            self.adopt_receipts()                        # F10: an A4 receipt created but never referenced
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
            self.verify_contract("entry")                # A13: the arms' contract artifacts (snapshots are known now)
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
            if self.builder != "tg1":                    # C221: the tg1 chain serves the committed registry verbatim, no overlay
                self.ops.ensure_overlay()
            (self.pinned_shared if self.per_arm else self.pinned)["registry_sha256"] = self.ops.overlay_sha()
            if not self.ops.power_ok():
                raise co.ChainAbort("power gate FAIL")
            predictor = getattr(self.a, "predictor", "off")
            self.freeze_schedule()
            loads = self.loads = self.plan()
            if any(self.needs_docker(leg["lang"]) for load in loads for leg in load["legs"]) and not self.ops.docker_ok():
                raise co.ChainAbort("docker gate FAIL: grading needs a reachable docker daemon")   # P290
            if self.config.arm_switch_ops:
                self.ops.require_arm_ops()
            if self.p426:
                self.p426_entry_checks()                 # B2 spec 3: the snapshots against the fork's pins, before the router
                self.p426_open_log_bounds()              # B2 spec 4.2: BEFORE the router starts
            router_pid = self.ops.start_router()
            if self.p426:
                self.p426_bind_router(router_pid)        # B2 spec 3: the owned identity `(pid, create_time(pid))`
            if self.per_arm:
                self.log(f"START chain arms={self.arm_ids} epoch={str(self.epoch_id)[:12]} loads="
                         f"{[(b['session'], b['model']) for b in loads]}")
            else:
                self.log(f"START {self.a.mode} predictor={predictor} blocks={[(b['session'], b['model']) for b in loads]}")
            try:
                for load in loads:
                    self.run_load(load)
                if self.loaded and not self.ops.unload(self.loaded):
                    raise co.ChainAbort("final unload failed")
                self.loaded = None
                if self.p426 and self.p426_router_problems():
                    raise co.ChainAbort("exit (systemic): " + "; ".join(self.p426_router_problems()))
                self.verify_snapshots("exit")
                self.check_realized()
                self.verify_lifecycle("exit")
                self.rc = 0
                self.log("ALL LEGS DONE")
            except Stopped as s:
                self.stop_info["where"] = self.stop_info.get("where") or str(s)
                self.log(f"STOP honoured at {self.stop_info['where']}: exit 3")
                self.rc = 3
        except co.ChainAbort as e:
            self.log(f"{'REFUSED' if isinstance(e, EntryRefused) else 'CHAIN ABORT'}: {e}")
            if isinstance(e, EntryRefused):                   # spec 16: every refusal prints one stderr line `REFUSED: <reason>`
                print(f"REFUSED: {e}", file=sys.stderr, flush=True)
            self.rc = e.code
        finally:
            self.write_json("finished")
            try:
                self.ops.stop_stack()
            finally:
                try:
                    if self.p426:
                        self.p426_close_log_bounds()     # B2 spec 4.2: finalized after teardown, also when teardown raised
                finally:
                    self.write_json("finished")
        return self.rc

    def check_realized(self):
        """The realized leg order equals the frozen schedule's (`blocks`); a tg2 chain runs each cell once per pick, so its
        expected order is the plan's (each leg's `realized_key`: the schedule's key + the model)."""
        if not self.freezes_schedule:
            return
        try:
            if self.builder == "blocks":
                schedules.check_realized(self.schedule, self.realized)
            elif [list(r) for r in self.realized] != [leg["realized_key"] for load in self.loads for leg in load["legs"]]:
                raise ValueError(f"realized order differs from the frozen schedule ({len(self.realized)} legs run, "
                                 f"{sum(len(load['legs']) for load in self.loads)} scheduled)")
        except ValueError as exc:
            raise co.ChainAbort(str(exc)) from None
        if self.p426:
            self.check_p426_ledger()

    def check_p426_ledger(self):
        """B2 spec 7: the per-item realized ledger (slot -> row | DNF, in order) equals the plan slot for slot; every DNF entry
        is a recorded `p426_dnf` and the other way round."""
        want = [s for load in self.loads for leg in load["legs"] for s in self.leg_slots(leg)]
        got = [e.get("slot") for e in self.p426_ledger]
        if got != want:
            missing = [s for s in want if s not in got]
            extra = sorted({s for s in got if got.count(s) > 1 or s not in want})
            raise co.ChainAbort(f"per-item ledger differs from the plan ({len(got)} entries, {len(want)} planned; "
                                f"missing {missing[:3]}, duplicated/unplanned {extra[:3]}, or reordered)")
        ledger_dnf = [e["slot"] for e in self.p426_ledger if e.get("kind") == "dnf"]
        if sorted(ledger_dnf) != sorted(d["slot"] for d in self.p426_dnf):
            raise co.ChainAbort("per-item ledger: its DNF entries differ from the p426_dnf records")

    def record_realized(self, leg):
        """Appended ONCE per leg key, in schedule order, when the leg's slots are all accounted."""
        key = leg.get("realized_key")
        if self.freezes_schedule and key is not None and key not in self.realized:
            self.realized.append(key)
            self.write_json("leg-done")

    # -- loads (a block: one model within one session, all its languages / arms)
    def session_dir(self, load):
        return self.out_root / load["session"]

    def load_rec(self, load):
        """The progress record of a load, found by its key (`<session>|<model>`) or created with the next load ordinal. The
        ordinal (`load["idx"]`, the first element of every invocation's `leg_key`) is the CREATION order in this chain.json,
        so a pilot and the chain after it (one out-root) never share a load id."""
        for rec in self.progress["loads"]:
            if rec.get("key") == load["key"]:
                load["idx"] = rec["load"]
                return rec
        rec = dict(load=len(self.progress["loads"]), key=load["key"], session=load["session"], model=load["model"],
                   status="pending", load_gen=0, workers=[], cursor=dict(leg_index=0, phase=None), archives=[])
        self.progress["loads"].append(rec)
        load["idx"] = rec["load"]
        return rec

    def run_load(self, load):
        rec = self.load_rec(load)
        load["rec"] = rec
        if rec["status"] == "done":
            self.log(f"SKIP load {load['session']}/{load['model']}: done")
            for leg in load["legs"]:
                self.record_realized(leg)
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
        (the rest), its records marked, and the load reruns from leg 0 with load_gen + 1. `new_segment` (M64): the load
        continues in a FRESH worker at the progress cursor with only the unaccepted slots; the persisted dispositions of a
        crashed invocation are replayed (an accepted prefix is salvaged), the rest of its files is quarantined."""
        running = [i for i in self.progress["invocations"] if i["leg_key"][0] == load["idx"]
                   and i["load_gen"] == rec["load_gen"] and i["status"] == "running"]
        self.hydrate_running(load, running)               # F17: before any salvage / quarantine / archive moves the files
        if self.config.resume_policy == "new_segment":
            self.check_cursor(load, rec)
            running = self.salvage_hook_stops(load, running)
            for r in running:
                self.abandoned_web_evidence(r, self.out_root / r["file"])
            if running:
                self.quarantine(running)
            self.sync_dnf_sidecars()
            self.log(f"RESUME load {load['session']}/{load['model']}: new worker, continuing at leg "
                     f"{rec['cursor']['leg_index']} ({rec['cursor']['phase']}), only the unaccepted slots")
            return
        if running:
            self.quarantine(running)
        dest = self.archive_load(load, resume=True)
        self.log(f"RESUME load {load['session']}/{load['model']}: interrupted load archived to {dest}")

    def hydrate_running(self, load, running):
        """F17: a crash after the probe exited but before `attempt-ended` leaves a `running` invocation whose cleanup receipt and
        abort evidence were never read; each is hydrated from its own final manifest (the F16 validation), idempotently."""
        for r in running:
            if r.get("manifest_hydrated"):
                continue                                   # hydrated already (F20: set only when hydration completed)
            want = str(self.out_root / r["file"])
            att = next((a for a in self.attempts if "--out" in a.get("argv", [])
                        and a["argv"][a["argv"].index("--out") + 1] == want), None)
            if att is None:
                continue
            view = self.leg_of(load, r)
            self.sweep_running_evidence(view, att, Path(view["out"]), r)       # F23 / F29
            self.hydrate_from_manifest(att, view, Path(view["out"]), r)
            att["outcome"] = att.get("outcome") or "exited_before_attempt_end"
            self.write_json("resume-hydrated")

    def sweep_running_evidence(self, view, att, out, rec):
        """F23 / F29: remove the publish temps under the crashed invocation's evidence root. The run id comes from the attempt
        when the barrier saw it, else from the final manifest ONLY when it is bound to this invocation (F16 / P384)."""
        run_id = att.get("run_id")
        if not run_id:
            man = self._manifest(view)
            if self._manifest_problem(att, view, out, man, rec) is None:
                run_id = man["run_id"]
        root = self.evidence_root(view, dict(att, run_id=run_id)) if run_id else None
        return self.sweep_temps(root, recursive=True) if root is not None and root.exists() else []

    def check_cursor(self, load, rec):
        """The persisted progress cursor must be consistent with what is scored: every leg BEFORE it is complete."""
        pos = rec["cursor"]["leg_index"]
        if pos > len(load["legs"]):
            raise co.ChainAbort(f"progress cursor leg {pos} is beyond the load's {len(load['legs'])} legs")
        table = self.slot_table()
        for leg in load["legs"][:pos]:
            if table.unscored(self.leg_slots(leg)):
                raise co.ChainAbort(f"progress cursor at leg {pos} but leg {leg['pos']} ({leg['stem']}) is not complete")

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
        rec = load["rec"]
        rec["status"] = "running"
        rec["cursor"] = dict(leg_index=0, phase=None) if not self.per_arm else rec["cursor"]
        self.load_worker(load)
        self.write_json("block-loaded")

    def load_worker(self, load):
        """Load the model (a NEW worker identity), then A4 per arm on it (A10): each gate receipt is copied to an immutable
        `<out_root>/a4/<load>.<worker_n>.<arm>.json` bound to the worker; the probes get that path."""
        ident = self.ops.load(load["model"])
        self.loaded = load["model"]
        key = (ident["pid"], ident["create_time"])
        if any(key == (w["pid"], w["create_time"]) for w in self.block_workers):
            raise co.ChainAbort("worker identity reused across blocks")
        n = len(self.block_workers)
        self.block_workers.append(dict(pid=ident["pid"], create_time=ident["create_time"], cmdline=ident.get("cmdline"),
                                       session=load["session"], model=load["model"]))
        load["worker"], load["manifest_worker"], load["last_arm"] = (
            dict(pid=ident["pid"], create_time=ident["create_time"]), None, None)
        if self.p426:
            self.p426_after_load(load, ident)            # B2 spec 3: census, worker argv, arm-equality receipt, pair gate - before A4
        rec = load["rec"]
        wn = len(rec["workers"])
        receipts, refs = {}, {}
        # F10: the worker record names the receipts it is about to create and is durable BEFORE the gate runs, so a crash
        # between a receipt's creation and its reference leaves a reserved name a resume can adopt (`adopt_receipts`)
        worker = dict(n=wn, pid=ident["pid"], create_time=ident["create_time"], a4_receipts=refs,
                      a4_reserved={arm: self._relpath(self.receipt_path(load, wn, arm)) for arm in self.arm_ids})
        rec["workers"].append(worker)
        self.write_json("worker-reserved")
        for arm in self.arm_ids:
            tag = f"{load['session']}_{n}_{load['model']}" + (f"_{arm}" if self.per_arm else "")
            a4_from = self.p426_log_offset() if self.p426 else None
            latest = (self.ops.a4_gate(load["model"], tag, scaffold=self.label_of(arm)) if self.per_arm
                      else self.ops.a4_gate(load["model"], tag))
            if self.p426:
                self.p426_check_a4_window(a4_from, latest)      # B2 spec 4.3: per load, before the first item
            path, sha = self.bind_receipt(latest, load, wn, arm)
            receipts[arm], refs[arm] = str(path), dict(path=self._relpath(path), sha256=sha)
            self.write_json("a4-bound")                  # the reference is durable before the next arm's gate
        load["receipts"], load["receipt_refs"] = receipts, refs
        load["receipt"] = receipts[self.arm_ids[0]]
        if not self.per_arm:
            worker["a4_receipt_sha256"] = refs[self.arm_ids[0]]["sha256"]

    def receipt_path(self, load, wn, arm):
        return self.out_root / "a4" / f"{load['idx']}.{wn}.{arm}.json"

    def adopt_receipts(self):
        """Resume (F10): an A4 receipt a crash left created but unreferenced is adopted into its reserved worker record once its
        binding (load, worker, arm) and the worker identity the record names are verified; anything else aborts."""
        changed = False
        self.sweep_temps(self.out_root / "a4")                              # F13: a receipt that never reached its destination
        for load in self.progress["loads"]:
            for worker in load["workers"]:
                for arm, rel in (worker.get("a4_reserved") or {}).items():
                    path = self.out_root / rel
                    if arm in worker["a4_receipts"] or not path.is_file():
                        continue
                    try:
                        binding = (json.loads(path.read_text()) or {}).get("bench_binding")
                    except (OSError, ValueError, AttributeError):
                        binding = None
                    want = dict(worker=dict(pid=worker["pid"], create_time=worker["create_time"]), load=load["load"],
                                worker_n=worker["n"], arm=arm)
                    if not isinstance(binding, dict) or {k: binding.get(k) for k in want} != want:
                        raise co.ChainAbort(f"orphaned A4 receipt {rel} does not match its reserved worker record "
                                            "(binding differs or unreadable)")
                    worker["a4_receipts"][arm] = dict(path=rel, sha256=sha_file(path))
                    worker["adopted"] = True
                    changed = True
                    self.log(f"RESUME: adopted the orphaned A4 receipt {rel}")
        if changed:
            self.write_json("a4-adopted")

    def bind_receipt(self, latest, load, wn, arm):
        """A10: copy the gate's `latest` receipt to its immutable per-(load, worker, arm) path (exclusive create) with the
        worker identity it belongs to; returns (path, sha256)."""
        try:
            doc = json.loads(Path(latest).read_text())
        except (OSError, ValueError) as exc:
            raise co.ChainAbort(f"A4 receipt of {arm} unreadable ({type(exc).__name__}: {Path(latest).name})") from None
        if not isinstance(doc, dict):
            raise co.ChainAbort(f"A4 receipt of {arm} is not a JSON object")
        doc = dict(doc, bench_binding=dict(worker=dict(load["worker"]), load=load["idx"], worker_n=wn, arm=arm,
                                           load_gen=load["rec"]["load_gen"]))
        raw = (json.dumps(doc, sort_keys=True, indent=1) + "\n").encode()
        dest = self.receipt_path(load, wn, arm)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            atomic_publish.publish_exclusive(dest, raw)          # F13 / F23 / F26: absent or complete, own temp grammar
        except FileExistsError:
            raise co.ChainAbort(f"A4 receipt {self._relpath(dest)} exists (A4 receipts are immutable: a new out-root is "
                                "needed)") from None
        return dest, hashlib.sha256(raw).hexdigest()

    def verify_receipt(self, load, arm):
        ref = load["receipt_refs"][arm]
        path = self.out_root / ref["path"]
        if co.file_sha(path) != ref["sha256"]:
            raise co.ChainAbort(f"A4 receipt {ref['path']} differs from its recorded sha256 (receipts are immutable)")

    def arm_idle(self):
        end = self.clock() + self.a.arm_idle_s
        self.log(f"ARM idle {self.a.arm_idle_s}s")
        while self.clock() < end:
            self.check_stop("block boundary")
            time.sleep(min(self.tm.poll_s, max(0.0, end - self.clock())))

    def execute_load(self, load):
        if self.per_arm:
            for leg in load["legs"]:
                if self.run_block_leg(load, leg) != "ok":
                    return "incomplete"
                self.record_realized(leg)
            self.require_load_complete(load)
            return "ok"
        for leg in load["legs"]:
            if self.p426:
                if self.run_p426_leg(load, leg) != "ok":
                    return "incomplete"
                self.record_realized(leg)
                continue
            for inv in leg["invocations"]:
                self.check_stop("before launch")
                load["rec"]["cursor"] = dict(leg_index=leg["li"], phase=inv["phase"])
                if self.run_invocation(load, leg, inv) != "ok":
                    return "incomplete"
            self.record_realized(leg)
        self.require_load_complete(load)
        return "ok"

    # -- the slot table: `chain_rows` is the only reader
    def chain_doc(self):
        return dict(progress=self.progress, dnf=self.dnf)

    def slot_table(self):
        try:
            return cr.load_slots(self.chain_doc(), self.out_root)
        except cr.ChainRowsError as exc:
            raise co.ChainAbort(f"the progress inventory does not load: {exc}") from None

    def leg_slots(self, leg):
        return [cr.slot_for(leg["slot_base"], i) for i in leg["invocations"][0]["expect"]] if self.per_arm else \
            [cr.slot_for(leg["slot_base"], i) for inv in leg["invocations"] for i in inv["expect"]]

    def require_load_complete(self, load):
        """The cell is complete only when `chain_rows` scores every expected slot of the load (sha re-checked)."""
        table = self.slot_table()
        expected = [s for leg in load["legs"] for s in self.leg_slots(leg)]
        missing = table.unscored(expected)
        if self.p426:                                    # a recorded item DNF accounts for its slot (not a row)
            dnf = {d["slot"] for d in self.p426_dnf}
            missing = [s for s in missing if s not in dnf]
        if missing:
            raise co.ChainAbort(f"load {load['session']}/{load['model']} complete but {len(missing)} slots are unscored: "
                                f"{missing[:3]}")

    # -- archive / quarantine
    def _stamp(self):
        return time.strftime("%Y%m%dT%H%M%S", time.gmtime())

    def _relpath(self, path):
        return Path(path).relative_to(self.out_root).as_posix()

    # -- two-phase file moves (F4): intent (src -> dst + sha256, the record repoints) fsynced BEFORE the first move, idempotent
    # moves, then the commit; a resume completes a transaction a crash left open
    def _repoint_ops(self, records, names, dest, status):
        """One `repoint` op per record: where its `file` / `manifest` go (when any of its files moves) and its new `status`."""
        ops = []
        for rec in records:
            base = Path(rec["file"]).name[:-len(".jsonl")] + "."
            moved = any(n.startswith(base) for n in names)           # a probe that never wrote its rows file moved too
            ops.append(dict(op="repoint", old=rec["file"], status=status,
                            file=self._relpath(Path(dest) / Path(rec["file"]).name) if moved else None,
                            manifest=self._relpath(Path(dest) / Path(rec["manifest"]).name) if moved else None))
        return ops

    def run_txn(self, kind, moves, ops):
        """`moves`: [(src, dst)] absolute paths; `ops`: the record changes the commit applies (JSON, replayable)."""
        txn = dict(id=len(self.progress["txns"]), kind=kind, status="intent", at=co.utc_stamp(), ops=ops,
                   files=[dict(src=self._relpath(src), dst=self._relpath(dst), sha256=sha_file(src)) for src, dst in moves])
        self.progress["txns"].append(txn)
        self.write_json("txn-intent")                    # durable BEFORE the first file moves
        self.complete_txn(txn)
        return txn

    def complete_txn(self, txn):
        for f in txn["files"]:
            self._move_one(self.out_root / f["src"], self.out_root / f["dst"], f["sha256"], txn["id"])
        for op in txn["ops"]:
            self.apply_txn_op(op)
        txn["status"] = "committed"
        self.write_json("txn-committed")

    @staticmethod
    def _move_one(src, dst, sha, tid):
        """Idempotent: a file already at `dst` (its sha256 verified) is done; a file in neither place or one that changed
        since the intent aborts (never guessed)."""
        if dst.exists():
            if sha_file(dst) != sha:
                raise co.ChainAbort(f"file-move transaction {tid}: {dst.name} at its destination differs from the intent sha256")
            if src.exists():
                if sha_file(src) != sha:
                    raise co.ChainAbort(f"file-move transaction {tid}: {src.name} exists at both ends with different content")
                src.unlink()
            return
        if not src.exists():
            raise co.ChainAbort(f"file-move transaction {tid}: {src.name} is at neither end (lost)")
        if sha_file(src) != sha:
            raise co.ChainAbort(f"file-move transaction {tid}: {src.name} changed since the intent was recorded")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        if sha_file(dst) != sha:
            raise co.ChainAbort(f"file-move transaction {tid}: {dst.name} differs from the intent sha256 after the move")

    def apply_txn_op(self, op):
        kind = op["op"]
        if kind == "repoint":
            for rec in self.progress["invocations"]:
                if rec["file"] in (op["old"], op["file"]):
                    if op["file"] is not None:
                        rec["file"], rec["manifest"] = op["file"], op["manifest"]
                    rec["status"] = op["status"]
            if op["file"] is not None:                    # F22: the abort-evidence references follow the move in the same txn
                for r in self.progress.get("abort_evidence", []):
                    if r.get("invocation") == op["old"]:
                        r["invocation"] = op["file"]
        elif kind == "archive_attempts":
            self._archive_attempts(set(op["files"]))
        elif kind == "mark_archived_records":
            for key in ("slot_attempts", "pre_spawn"):
                for r in self.progress[key]:
                    if r.get("load") == op["load"] and r.get("load_gen") == op["gen"]:
                        r["status"] = "archived"
        elif kind == "advance_load":
            rec = next(r for r in self.progress["loads"] if r["load"] == op["load"])
            if rec["load_gen"] != op["gen"]:
                return                                   # already advanced (an idempotent replay)
            if op.get("dnf_slots") is not None and self.p426:
                raise co.ChainAbort("p426_continue: an advance_load op never carries dnf_slots (no load rerun)")
            if op.get("dnf_slots") is not None:          # incident_retry: the load reruns from scratch
                self.dnf = [r for r in self.dnf if r["slot"] not in set(op["dnf_slots"])]
                self.realized = [r for r in self.realized if r[0] != op["sched_idx"]]
            rec["load_gen"] += 1
            rec["status"] = "pending"
            rec["cursor"] = dict(leg_index=0, phase=None)
        else:
            raise co.ChainAbort(f"file-move transaction: unknown op {kind!r}")

    def recover_txns(self):
        """Resume: roll every open (`intent`) transaction forward, before anything reads the inventory."""
        for txn in self.progress["txns"]:
            if txn["status"] == "intent":
                self.log(f"RESUME: completing the interrupted file-move transaction {txn['id']} ({txn['kind']}, "
                         f"{len(txn['files'])} files)")
                self.complete_txn(txn)

    def archive_load(self, load, resume=False):
        """`restart_load`: the load's files go to `<session>/incomplete/<model>.<ts>/`. The sha manifest is recorded in
        chain.json (fsynced) BEFORE the first file moves; the moves are one transaction (F4); the load's records are marked
        `archived` (paths rewritten to the archive, shas kept), they leave the active inventory, and the load's generation
        advances."""
        if self.p426:
            raise co.ChainAbort("p426_continue never archives or reloads a load (an item DNF continues on the same load; "
                                "anything else is systemic)")
        rec = load["rec"]
        sdir = self.session_dir(load)
        dest = sdir / "incomplete" / f"{load['model']}.{self._stamp()}"
        prefix = f"{load['model']}.{load['session']}."
        files = [f for f in sorted(sdir.iterdir()) if f.is_file() and f.name.startswith(prefix)] if sdir.exists() else []
        manifest = {f.name: sha_file(f) for f in files}
        gen = rec["load_gen"]
        rec["archives"].append(dict(dir=self._relpath(dest), at=co.utc_stamp(), files=manifest, load_gen=gen))
        mine = [i for i in self.progress["invocations"] if i["leg_key"][0] == load["idx"] and i["load_gen"] == gen
                and i["status"] not in ("archived", "quarantined")]
        ops = self._repoint_ops(mine, manifest, dest, "archived")
        ops.append(dict(op="mark_archived_records", load=load["idx"], gen=gen))
        advance = dict(op="advance_load", load=load["idx"], gen=gen)
        if self.config.transport_policy == "incident_retry":
            dnf = [r for r in self.dnf if r["slot"].split("|")[2:4] == [load["model"], load["session"]]]
            rec["archives"][-1]["dnf"] = dnf
            advance.update(dnf_slots=[r["slot"] for r in dnf], sched_idx=self.sched_load_index(load))
        ops.append(advance)
        self.run_txn("archive_load", [(f, dest / f.name) for f in files], ops)
        self.write_json("archived")
        return dest

    def sched_load_index(self, load):
        for i, sload in enumerate((self.schedule or {}).get("loads", [])):
            if (sload["session"], sload["pick"]) == (load["session"], load["model"]):
                return i
        return None

    def quarantine(self, records):
        """Never-validated invocation files -> `quarantine/<ts>/` with a sha256 manifest written FIRST, then ONE move
        transaction (F4). The ACCEPTED slot attempts persisted for those files are archived (their rows no longer count); a
        persisted cheat / unclear disposition stays (it is what makes the slot re-run, with its tokens)."""
        stamp = self._stamp()
        dest = self.out_root / "quarantine" / stamp
        n = 0
        while dest.exists():
            n += 1
            dest = self.out_root / "quarantine" / f"{stamp}.{n}"
        files = {}
        for rec in records:
            base = (self.out_root / rec["file"]).name[:-len(".jsonl")]
            for f in sorted((self.out_root / rec["file"]).parent.glob(base + ".*")) if (self.out_root / rec["file"]).parent.exists() else []:
                if f.is_file():
                    files[f.name] = f
        dest.mkdir(parents=True, exist_ok=True)
        fsync_json(dest / "MANIFEST.json", dict(at=co.utc_stamp(), files={n_: sha_file(f) for n_, f in files.items()}))
        ops = [dict(op="archive_attempts", files=[r["file"] for r in records])]
        ops += self._repoint_ops(records, files, dest, "quarantined")
        self.run_txn("quarantine", [(f, dest / name) for name, f in files.items()], ops)
        self.write_json("quarantined")
        return dest

    def archive_stopped(self, load, leg, rec=None):
        """STOP during a leg: the partial leg's files go to `<session>/stopped/` (tg1: every file of the leg's stem; M64: only the
        stopped invocation's own files, its siblings are other blocks' accepted rows). One move transaction (F4)."""
        sdir = self.session_dir(load)
        own = self.per_arm and rec is not None
        prefix = (Path(rec["file"]).name[:-len(".jsonl")] if own else leg["stem"]) + "."
        dest = sdir / "stopped" / f"{leg['stem']}.{self._stamp()}"
        files = [f for f in sorted(sdir.iterdir()) if f.is_file() and f.name.startswith(prefix)]
        names = {f.name for f in files}
        if own:
            mine = [rec]
        else:
            mine = [i for i in self.progress["invocations"] if Path(i["file"]).name.startswith(leg["stem"] + ".")
                    and Path(i["file"]).parent.name == load["session"] and i["load_gen"] == load["rec"]["load_gen"]
                    and i["status"] in ("running", "validated", "partial_incident", "hook_stopped")]
        ops = [dict(op="archive_attempts", files=[r["file"] for r in mine])]
        for r in mine:
            ops += self._repoint_ops([r], names, dest, "quarantined" if r["status"] == "running" else "archived")
        self.run_txn("archive_stopped", [(f, dest / f.name) for f in files], ops)
        return dest

    def _archive_attempts(self, files):
        """The ACCEPTED / exhausted slot attempts persisted for invocation files that leave the inventory are archived (their
        rows no longer count); a persisted cheat / unclear disposition stays (it is what makes the slot re-run)."""
        for a in self.progress["slot_attempts"]:
            if a.get("invocation") in files and a.get("disposition") in ("accepted", "exhausted"):
                a["status"] = "archived"

    # -- invocation (a leg attempt)
    def invocation_paths(self, load, leg, inv):
        n = self.attempt_no.get(leg["stem"], 0) + 1
        sdir = self.session_dir(load)
        rows = sdir / cr.rows_name(leg["stem"], leg["li"], inv["phase"], n)
        base = Path(str(rows)[:-len(".jsonl")])
        return n, sdir, rows, base

    def leg_key(self, load, leg):
        return [load["idx"], leg["lang"], leg["li"]] + ([leg["arm"]] if self.per_arm else [])

    def register_invocation(self, load, leg, inv, n, rows, ids):
        rec = dict(leg_key=self.leg_key(load, leg), phase=inv["phase"], attempt=n,
                   worker_n=len(load["rec"]["workers"]) - 1, file=self._relpath(rows),
                   manifest=self._relpath(rows.with_suffix(".manifest.json")), status="running",
                   expected_slots=[cr.slot_for(leg["slot_base"], i) for i in ids], accepted_slots=[], sha256=None,
                   load_gen=load["rec"]["load_gen"], slot_base=leg["slot_base"])
        if inv["phase"] == "rerun":
            rec["rerun_index"] = inv["rerun_index"]
        self.progress["invocations"].append(rec)
        return rec

    def prior_rows(self, load, leg):
        """Validated rows files of this leg's earlier invocations (for the watch log's cell totals)."""
        files, ids = [], []
        for rec in self.progress["invocations"]:
            if (rec["leg_key"] == self.leg_key(load, leg) and rec["load_gen"] == load["rec"]["load_gen"]
                    and rec["status"] in cr.COUNTED_STATUSES):
                files.append(self.out_root / rec["file"])
                ids += [s.split("|")[-1] for s in rec["expected_slots"]]
        return files, ids

    def before_invocation(self, load, leg, inv):
        """Arm switches (M64 spec 5.5 / 8.1): the search service restarts before EVERY invocation; an arm switch (or a re-run)
        resets the cache session and sends one unscored warm-up request."""
        ops = self.config.arm_switch_ops
        if not ops:
            return
        if "search_restart" in ops:
            self.ops.search_restart(leg)
        if load.get("last_arm") != leg["arm"] or inv["phase"] == "rerun":
            if "cache_reset" in ops:
                self.ops.reset_cache_session(load["model"])
            if "warmup" in ops:
                self.ops.warmup(load["model"])
        load["last_arm"] = leg["arm"]

    def epoch_arg(self):
        return self.epoch_id if self.per_arm else None

    def run_invocation(self, load, leg, inv):
        """One probe invocation. Returns "ok" (validated), "hook" (a hook disposition stopped it after an accepted prefix:
        the leg loop re-derives what is left), "incident" (a transport incident was recovered, the same slot retries) or
        "incomplete" (the load is archived and restarted once)."""
        self.verify_lifecycle("launch")
        self.verify_schedule(leg)
        arm = leg["arm"]
        self.verify_receipt(load, arm)
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
        if self.p426:
            self.p426_before_invocation(load)            # B2 spec 3: router identity, foreign-process census, snapshots
        if not self.ops.power_ok():
            raise co.ChainAbort("power gate FAIL before launch")
        if self.needs_docker(leg["lang"]) and not self.ops.docker_ok():
            raise co.ChainAbort("docker gate FAIL before launch")                                    # P290
        self.before_invocation(load, leg, inv)
        ids = list(inv["expect"])
        view = dict(leg, out=str(out), model=leg["model"], phase=inv["phase"], model_load=load["idx"])
        view["prior_files"], view["prior_ids"] = self.prior_rows(load, leg)
        step = dict(inv, names=list(inv["names"]))
        nonce = secrets.token_hex(32)                    # P384: persisted in the invocation record BEFORE the launch
        cmd = build_cmd(self.py, self.probe_of(arm), view, step, load["receipts"][arm], cancel, ack, scaffold=leg["label"],
                        universe=self.universe, frozen=self.frozen, attempt=n, rerun_index=inv.get("rerun_index", 0),
                        epoch=self.epoch_arg(), nonce=nonce,
                        evidence="p426" if self.config.config_id == run_config.P426_CONFIG_ID else None,
                        inject_stall=self.p426_inject_stall(leg, step))
        att = dict(attempt=n, step=inv["phase"], stem=leg["stem"], argv=cmd, cancel=str(cancel), ack=str(ack),
                   log=str(logp), worker=dict(load["worker"]), started=co.utc_stamp(), rc=None,
                   cleanup_status=None, run_id=None, probe_pid=None, probe_create_time=None, outcome=None)
        if self.per_arm:
            att["arm"] = arm
        rec = self.register_invocation(load, leg, inv, n, out, ids)
        rec["nonce"] = nonce
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
        co.atomic_json(ajson, self.p426_persist(att))
        self.write_json("running")
        sup = self.supervise(att, proc, view, step, load, rec=rec, inv=inv, base=base)
        att["rc"] = proc.returncode
        self.hydrate_from_manifest(att, view, out, rec)
        att["outcome"] = sup["state"]
        co.atomic_json(ajson, self.p426_persist(att))
        self.log(f"END {leg['stem']} attempt {n} rc={att['rc']} state={sup['state']}")
        self.write_json("attempt-ended")
        if sup["state"] == "barrier_mismatch":
            self.listing(att, view)
            raise co.ChainAbort("first-manifest mismatch: " + "; ".join(sup["reasons"]))
        self.verify_lifecycle("validation")
        hook = sup.get("hook")
        expect_ids = ids if not hook else (ids[:hook["k"]] if hook["kind"] == "before" else ids[:hook["k"] + 1])
        vleg = dict(session=leg["session"], model=leg["model"], lang=leg["lang"], seed_base=leg["seed_base"],
                    expected_ids=expect_ids, out=str(out), rc=att["rc"], draft_kind=leg.get("draft_kind", "off"),
                    arm_identity_sha256=self.arms.get(self.arm_key(leg)))
        why = co.validate_leg(vleg, self.pinned_for(arm), self.ops.wd, policy_sha=self.policy_for(arm),
                              frozen_prompt_date=self.frozen, spec=self.spec_of(arm))
        if self.per_arm:
            why += self.arm_row_problems(view, out) + self.hook_manifest_problems(view, hook)
        if not why:
            self.pin_from(view)
            att["outcome"] = "validated"
            co.atomic_json(ajson, self.p426_persist(att))
            return self.accept_invocation(load, leg, inv, rec, out, hook, att=att, view=view)
        for w in why:
            self.log(f"INCOMPLETE {leg['stem']} attempt {n}: {w}")
        self.abandoned_web_evidence(rec, out)
        if sup["stop"]:
            dest = self.archive_stopped(load, leg, rec)
            self.log(f"STOP: partial leg archived to {dest}")
            self.stop_info["where"] = "leg"
            self.write_json("stopped")
            raise Stopped("leg")
        return self.handle_incomplete(load, leg, inv, rec, att, why, sup=sup, view=view)

    def _manifest_problem(self, att, view, out, man, rec=None):
        """F16: why `man` (read ONCE by the caller) is not THIS invocation's manifest, or None. Its binding (model, language,
        seed base, scaffold label, arm, the worker at launch) must match the invocation, its run id must not be one already seen
        in this chain (a copied-in or reused manifest), and it must match the run id the barrier observed. The manifest carries
        no attempt / phase / rerun fields (adding them would change the A14 manifest shape): the invocation's own immutable
        path binds those."""
        if man is None:
            return "missing" if not Path(out).with_suffix(".manifest.json").exists() else "invalid"
        if not isinstance(man, dict) or not isinstance(man.get("run_id"), str) or not man["run_id"]:
            return "invalid"
        nonce = (rec or {}).get("nonce")               # F16 / P384: the chain-issued per-invocation nonce, REQUIRED (fail closed)
        if not (isinstance(nonce, str) and re.fullmatch("[0-9a-f]{64}", nonce)):
            return "invocation record has no nonce"
        rt, wk, launch = man.get("runtime") or {}, man.get("worker") or {}, att.get("worker") or {}
        checks = [("model", man.get("model"), view.get("model")), ("lang", rt.get("lang"), view.get("lang")),
                  ("seed_base", rt.get("seed_base"), view.get("seed_base")), ("scaffold", rt.get("scaffold"), view.get("label")),
                  ("worker", (wk.get("pid"), wk.get("create_time")), (launch.get("pid"), launch.get("create_time")))]
        if self.per_arm:
            checks.append(("arm", rt.get("arm"), view.get("arm")))
        checks.append(("invocation_nonce", rt.get("invocation_nonce"), nonce))
        bad = [name for name, got, want in checks if got != want]
        if bad:
            return "binding differs: " + ", ".join(bad)
        if att.get("run_id"):
            return "run_id differs" if man["run_id"] != att["run_id"] else None
        if man["run_id"] in self.seen_run_ids:
            return "run_id already seen"
        return None

    def _record_abort_evidence(self, out, att, found):
        """One `progress.abort_evidence` record per (invocation, attempt): a second hydration replaces, never duplicates."""
        inv = self._relpath(out)
        records = [r for r in self.progress.setdefault("abort_evidence", [])
                   if not (r.get("invocation") == inv and r.get("attempt") == att["attempt"])]
        records.append(dict(invocation=inv, attempt=att["attempt"], **found))
        self.progress["abort_evidence"] = records

    def unusable_attribution(self, view, out, rec):
        """F21: the slot an unusable-manifest `unavailable` belongs to: the first UNCOMMITTED expected slot, proven from the
        invocation's immutable rows file (its rows must be exactly the expected prefix). `(slot, None)` or `(None, reason)`."""
        expected = list((rec or {}).get("expected_slots") or [])
        try:
            ids = [r["id"] for r in cr.rows_if_present(out)]
        except (cr.ChainRowsError, TypeError, KeyError):
            return None, "attribution unproven"
        # F24 / F25: the EXACT expected row ids (`<lang>/<item>`, strings) are compared before any slot is derived
        want = [f"{view['lang']}/{s.rsplit('|', 1)[-1]}" for s in expected]
        if (not expected or not all(isinstance(i, str) for i in ids) or ids != want[:len(ids)] or len(ids) >= len(expected)):
            return None, "attribution unproven"
        return expected[len(ids)], None

    def hydrate_from_manifest(self, att, view, out, rec=None):
        """F14: after the probe exits, ALWAYS read the invocation's own final manifest (its path is the invocation's rows file
        stem, unique per invocation) and hydrate the cleanup receipt, cancelled item, abort stamp and abort evidence from it,
        whether or not the barrier observed it. A missing / invalid / foreign manifest hydrates nothing (restart eligibility
        keeps refusing without a receipt). F20: `manifest_hydrated` (and the observed / problem state) is set on the
        invocation record only AFTER everything, evidence extraction included, completed, so a crash in the middle is retried
        at resume; an extraction failure is recorded in `hydration_failure` before it propagates."""
        if rec is not None and rec.get("manifest_hydrated"):
            return
        observed = bool(att.get("run_id"))
        man = self._manifest(view)
        problem = self._manifest_problem(att, view, out, man, rec)
        try:
            if problem:
                # F18 / F21: no usable manifest (e.g. a cancel before the probe wrote one): an explicit `unavailable`
                reason = ("no manifest (pre-manifest exit)" if problem == "missing"
                          else f"the invocation's manifest is not usable ({problem})")
                slot, why = self.unusable_attribution(view, out, rec)
                found = dict(slot=slot, evidence=None, web_evidence=we.unavailable(reason))
                if why:
                    found["reason"] = why
                if self.per_arm:
                    att["abort_evidence"] = found
                self._record_abort_evidence(out, att, found)
            else:
                att["run_id"] = att.get("run_id") or man["run_id"]
                att["cleanup_status"] = receipt_from_manifest(man)
                att["cancelled_item"] = man.get("cancelled_item")
                att["transport_abort"] = man.get("transport_abort")
                if att["transport_abort"] is not None:
                    found = self.abort_evidence(att, view, out)
                    if self.per_arm:
                        att["abort_evidence"] = found
                    # one record per aborted attempt in the inventory for EVERY configuration (tg1 attempts keep their shape)
                    self._record_abort_evidence(out, att, found)
                self.seen_run_ids.add(man["run_id"])
        except co.ChainAbort as exc:
            if rec is not None:
                rec["hydration_failure"] = str(exc)[:300]
                self.write_json("hydration-failed")
            raise
        # the per-arm attempts carry the state; every configuration's inventory record carries it (tg1 attempts keep their shape)
        if self.per_arm:
            att["manifest_observed"], att["manifest_problem"] = observed, problem
        if rec is not None:
            rec["manifest_observed"], rec["manifest_problem"] = observed, problem
            rec["manifest_hydrated"] = True
            rec.pop("hydration_failure", None)

    def sweep_temps(self, directory, recursive=False):
        """F23 / F27: remove leftover publish temps (EXACTLY `.<name>.tmp.<pid>.<16 hex>`: a process died before it linked its
        evidence file; no other dotfile); each is listed in the log. Returns the names."""
        names = []
        for tmp in atomic_publish.leftover_temps(directory, recursive):
            self.log(f"RESUME: removed leftover evidence temp file {tmp.name}")
            tmp.unlink(missing_ok=True)
            names.append(tmp.name)
        return names

    def _reverify_extraction(self, view, path, sha, dest):
        """The extraction file already exists (a crash after it was written): accept it only when re-extracting the transcript
        (sha256 re-verified) yields byte-identical content."""
        tmp = dest.with_name(dest.name + ".verify")
        tmp.unlink(missing_ok=True)
        try:
            again = we.extract(self.web_rules(view["arm"]), path, sha, tmp)
            if "path" not in again or tmp.read_bytes() != dest.read_bytes():
                raise we.WebEvidenceError(f"{dest.name} exists and differs from the transcript's extraction")
        finally:
            tmp.unlink(missing_ok=True)
        return dict(path=str(dest), sha256=again["sha256"], count=again["count"])

    def abort_evidence(self, att, view, out):
        """A12 (F6): the evidence of the slot an abort (incident, cancel, STOP) hit BEFORE its row was committed: the probe's
        abort stamp names the item's evidence files with their sha256; the exported transcript's web evidence is extracted
        (sha256 re-verified) or recorded `unavailable` with the reason. A slot whose row was committed is covered by the
        row's own evidence (the barrier extracted it) and is never extracted twice."""
        stamp = att.get("transport_abort") or {}
        ev = stamp.get("evidence") if isinstance(stamp.get("evidence"), dict) else None
        if ev is not None and ev.get("boundary"):         # F19: a cancel between items belongs to no slot
            return dict(slot=None, evidence=ev, boundary=True, after=ev.get("after"))
        item = (ev or {}).get("id") or (att.get("cancelled_item") or {}).get("id")
        slot = cr.slot_for(view["slot_base"], item) if item else None
        try:
            committed = {r["id"] for r in cr.rows_if_present(out)}
        except cr.ChainRowsError:
            committed = set()
        if item in committed:
            return dict(slot=slot, evidence=ev, covered="row")
        if ev is None:
            return dict(slot=slot, evidence=None, web_evidence=we.unavailable(
                "the abort stamp carries no evidence for the failing slot"))
        export = (ev.get("files") or {}).get("export") or {}
        path = co.resolve_portable(export["path"], self.wd) if export.get("sha256") and export.get("path") else None
        dest = path.with_name(path.stem + ".web.jsonl") if path is not None else None
        if dest is not None:
            self.sweep_temps(dest.parent)
        try:
            if dest is not None and dest.exists():
                web = self._reverify_extraction(view, path, export.get("sha256"), dest)     # F20: a retry after a crash
            else:
                web = we.extract(self.web_rules(view["arm"]), path, export.get("sha256"), dest)
        except (we.TranscriptShaMismatch, we.WebEvidenceError) as exc:
            raise co.ChainAbort(f"web evidence: {exc}") from None
        if "path" in web:
            web = dict(web, path=self._portable(web["path"]))
        return dict(slot=slot, evidence=ev, web_evidence=web)

    def arm_row_problems(self, leg, out):
        """Arm-identifying fields every row and the manifest must carry (rows: arm, epoch_id, snapshot_sha256) and the frozen
        snapshot of the arm (A5)."""
        why = []
        man = self._manifest(leg) or {}
        rt = man.get("runtime") or {}
        frozen = (self.snapshots.get(leg["arm"]) or {}).get("sha256")
        for key, want in (("arm", leg["arm"]), ("epoch_id", self.epoch_id)):
            if rt.get(key) != want:
                why.append(f"runtime_{key}: {rt.get(key)!r} != {want!r}")
        if frozen is not None and rt.get("snapshot_sha256") != frozen:
            why.append(f"runtime_snapshot_sha256: {rt.get('snapshot_sha256')!r} != frozen {frozen!r}")
        try:
            rows = cr.rows_if_present(out)
        except cr.ChainRowsError:
            rows = []
        for r in rows:
            for key, want in (("arm", leg["arm"]), ("epoch_id", self.epoch_id), ("snapshot_sha256", rt.get("snapshot_sha256"))):
                if r.get(key) != want or not want:
                    why.append(f"row_{key}: {r.get('id')} {r.get(key)!r} != {want!r}")
        return why

    def hook_manifest_problems(self, leg, hook):
        """The probe's recorded `hook_stop` must be exactly the stop the chain wrote (and none without one)."""
        man = self._manifest(leg) or {}
        got = man.get("hook_stop")
        if hook is None:
            return [] if got is None else [f"hook_stop: the manifest records {got!r} but the chain wrote no stop"]
        item = f"{leg['lang']}/{hook['name']}"
        want = dict(before_slot=item) if hook["kind"] == "before" else dict(after_slot=item, disposition=hook["disposition"])
        return [] if got == want else [f"hook_stop: the manifest records {got!r}, the chain wrote {want!r}"]

    def require_certain_cleanup(self, att, view, what):
        """A7 (F5): the exact `ProcessGuard.status()` receipt (certain, completed, empty) before ANY retry / restart: the hook
        re-run, the pre-spawn retry and the restart of a hook-stopped invocation take the same validator as an incident."""
        problems = cleanup_problems((att or {}).get("cleanup_status"))
        if problems:
            self.listing(att or {}, view)
            raise co.ChainAbort(f"{what} refused: cleanup is not certain and complete: " + "; ".join(problems))

    def accept_invocation(self, load, leg, inv, rec, out, hook=None, att=None, view=None):
        """A validated invocation: sha256 recorded AFTER validation (fsynced), then the chain-side web evidence. A hook-stopped
        invocation is accepted for the prefix it ran (`hook_stopped`)."""
        rows = cr.rows_if_present(out)
        rec["accepted_slots"] = ([cr.slot_for(rec["slot_base"], r["id"]) for r in rows] if hook
                                 else list(rec["expected_slots"]))
        rec["sha256"] = sha_file(out) if Path(out).exists() else None
        rec["status"] = "hook_stopped" if hook else "validated"
        if hook:
            rec["hook_stop"] = (dict(before_slot=hook["slot"]) if hook["kind"] == "before"
                                else dict(after_slot=hook["slot"], disposition=hook["disposition"]))
        self.write_json("invocation-validated")
        self.after_invocation(load, leg, inv, rec, rows)
        if not hook:
            return "ok"
        if hook.get("disposition") == "invalidate":          # B2: a barrier check failed; the cleanup is verified, the leg INVALID
            self.require_certain_cleanup(att, view, "invalidate")
            raise LegInvalid(f"leg INVALID at {hook['slot']}: {hook.get('reason')}")
        if hook["kind"] == "before":
            if self.p426:
                raise co.ChainAbort("p426_continue: a before_attempt pre-spawn incident cannot occur (a hook "
                                    "infrastructure error is systemic)")
            if self.config.transport_policy != "incident_retry":
                self.require_certain_cleanup(att, view, "restart")
                return "incomplete"                       # abort_restart: the load restarts
            self.require_certain_cleanup(att, view, "retry")
            self.recover(load, leg, hook["cause"])
            return "incident"
        if hook["disposition"] == "unclear":
            raise co.ChainAbort(f"slot {hook['slot']} is blocked for the operator (unclear disposition: "
                                f"{hook.get('reason') or 'no reason recorded'})")
        self.require_certain_cleanup(att, view, "retry")
        return "hook"

    def abandoned_web_evidence(self, rec, out):
        """A12: an invocation that did not validate (cut, cancelled, aborted ...) still has stored transcripts for the rows it
        wrote; their web evidence is extracted (and hashed in the invocation record) before the files are archived. Rows
        whose evidence the item barrier already extracted keep that record."""
        try:
            rows = cr.rows_if_present(out)
        except cr.ChainRowsError as exc:
            self.log(f"web evidence: partial rows file {Path(out).name} unreadable ({exc}); nothing extracted")
            return
        if not rows:
            return
        rules = self.web_rules(rec["slot_base"].split("|")[1])
        known = {(a["slot"], a["rerun_index"]) for a in self.progress["slot_attempts"]}
        found = {}
        for row in rows:
            try:
                slot = cr.slot_for(rec["slot_base"], row["id"])
            except cr.ChainRowsError as exc:                 # a row that is not this leg's (F24 / F28): no evidence is guessed
                self.log(f"web evidence: row skipped in {Path(out).name} ({exc})")
                continue
            if (slot, rec.get("rerun_index", 0)) in known:
                continue
            tp = row.get("transcript_path")
            path = co.resolve_portable(tp, self.wd) if tp else None
            found[slot] = self.web_record(row, rules, path.with_name(path.stem + ".web.jsonl") if path is not None else None)
        if found:
            rec["web_evidence"] = found
            self.write_json("web-evidence-partial")

    def after_invocation(self, load, leg, inv, rec, rows):
        """Chain-side web evidence for every row with a stored transcript; the sha256 is recorded per slot attempt. Rows
        the item barrier already decided (a persisted slot attempt at their re-run index) are not extracted twice."""
        rules = self.web_rules(rec["slot_base"].split("|")[1])
        rindex = rec.get("rerun_index", 0)
        known = {(a["slot"], a["rerun_index"]) for a in self.progress["slot_attempts"] if a.get("status") != "archived"}
        for row in rows:
            slot = cr.slot_for(rec["slot_base"], row["id"])
            if (slot, rindex) in known:
                continue
            tp = row.get("transcript_path")
            path = co.resolve_portable(tp, self.wd) if tp else None
            dest = path.with_name(path.stem + ".web.jsonl") if path is not None else None
            w = (rec.get("web_evidence") or {}).get(slot) or self.web_record(row, rules, dest)    # evidence is immutable
            self.progress["slot_attempts"].append(dict(
                slot=slot, rerun_index=rindex, disposition="accepted", load=load["idx"], load_gen=rec["load_gen"],
                invocation=rec["file"], output_tokens=(row.get("gate") or {}).get("output_tokens_completed"),
                web_evidence=w))
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
        arm = leg.get("arm") or self.arm_ids[0]
        man = self._manifest(leg) or {}
        spec = self.spec_of(arm)
        bad = co.malformed_identity(man, spec)
        if bad:
            raise co.ChainAbort(f"first complete leg has absent/null/malformed identity fields: {bad}")
        missing = []
        ident = co.runtime_identity(man, None if spec is None else spec.runtime_pinned)      # P276: where the real probe writes each pinned field
        pinned = self.pinned_by_arm[arm] if self.per_arm else self.pinned
        for k in self.runtime_pinned(arm):
            if k in pinned:
                continue
            if k in ident:
                pinned[k] = ident[k]
            else:
                missing.append(k)
        shared = self.pinned_shared if self.per_arm else self.pinned
        if "serving_path" not in shared:
            sp = (man.get("git") or {}).get("serving_path")
            if sp:
                shared["serving_path"] = sp
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
            if self.config.transport_policy in ("incident_retry", "p426_continue"):
                # A7 (F5): the M64 layout's every retry / restart takes the EXACT receipt; tg1 (`abort_restart`) keeps the
                # C147 rule (a receipt's `orphans_unattributed` are diagnostics there, and its probe predates the six keys)
                why += [f"cleanup receipt not exact / certain / complete: {p}" for p in cleanup_problems(cs)]
        fl = co.in_flight(self.ops.worker_metrics() or {})
        if fl != 0:
            why.append(f"worker health: metrics unreadable or in_flight={fl}")
        ident = self.ops.worker_ident(leg["model"])
        if not ident or (ident["pid"], ident["create_time"]) != (block["worker"]["pid"], block["worker"]["create_time"]):
            why.append("worker health: identity changed or worker gone")
        if why:
            self.listing(att, leg)
            raise co.ChainAbort("restart refused: " + "; ".join(why))

    # -- M64: a leg is run until every one of its slots is accounted for (scored attempt, DNF row)
    def run_block_leg(self, load, leg):
        """The dynamic leg loop (A8): each iteration derives what is left from the slot table (`chain_rows`), runs ONE
        invocation (`block`; `retry` after an incident of its head slot; a one-slot `rerun` for a cheat) and re-derives. So a
        fresh run, an incident, a hook stop and a resume are the same code."""
        names = leg["items"]
        mine = {n: cr.slot_for(leg["slot_base"], f"{leg['lang']}/{n}") for n in names}
        while True:
            self.check_stop("before launch")
            self.settle_dnf(load, leg)
            table = self.slot_table()
            blocked = [s for s in mine.values() if s in table.blocked]
            if blocked:
                raise co.ChainAbort(f"slot {blocked[0]} is blocked for the operator (its latest attempt has an unclear "
                                    "disposition); resolve it before the chain continues")
            todo = [n for n in names if mine[n] not in table.scored]
            if not todo:
                return "ok"
            head = mine[todo[0]]
            reruns = dict(table.pending_reruns)
            if head in reruns:
                inv = dict(kind="rerun", phase="rerun", names=[todo[0]], limit=None, expect=[f"{leg['lang']}/{todo[0]}"],
                           rerun_index=reruns[head])
            else:
                phase = "retry" if self.incident_count(head, load) else "block"
                inv = dict(kind=phase, phase=phase, names=list(todo), limit=None,
                           expect=[f"{leg['lang']}/{n}" for n in todo])
            load["rec"]["cursor"] = dict(leg_index=leg["pos"], phase=inv["phase"])
            if self.run_invocation(load, leg, inv) == "incomplete":
                return "incomplete"

    def incident_count(self, slot, load):
        gen = load["rec"]["load_gen"]
        return sum(1 for i in self.incidents if i["slot"] == slot and i.get("load_gen") == gen)

    def settle_dnf(self, load, leg):
        """Spec 8.3: a slot whose second incident is recorded and that has no scored attempt becomes a `transport_dnf` row
        (chain.json first, then the sidecar; a resume re-creates a missing sidecar from chain.json)."""
        gen = load["rec"]["load_gen"]
        table = None
        for n in leg["items"]:
            slot = cr.slot_for(leg["slot_base"], f"{leg['lang']}/{n}")
            mine = [i for i in self.incidents if i["slot"] == slot and i.get("load_gen") == gen]
            if len(mine) < ci.MAX_INCIDENTS or any(r["slot"] == slot for r in self.dnf):
                continue
            table = table or self.slot_table()
            if slot in table.scored:
                continue
            arm = leg["arm"]
            row = dnf_row(slot=slot, arm=arm, label=leg["label"], pick=leg["model"], session=leg["session"],
                          lang=leg["lang"], item=n, seed_base=leg["seed_base"], incidents=mine[:ci.MAX_INCIDENTS],
                          worker=mine[-1].get("worker_full") or mine[-1]["worker"], frozen=self.frozen,
                          epoch=self.epoch_id, runtime=dict(
                              self.pinned_for(arm), arm_identity_sha256=self.arms.get(self.arm_key(leg))))
            why = validate_dnf_row(row, arm=arm, slot=slot)
            if why:
                raise co.ChainAbort("; ".join(why))
            self.dnf.append(row)
            self.write_json("dnf")
            self.sync_dnf_sidecars()
            self.log(f"DNF {slot}: transport_dnf row written; the schedule continues")

    def sync_dnf_sidecars(self):
        """The DNF sidecar of every leg with a DNF row equals the chain.json copy (chain.json is the record: it is written
        first, a sidecar a crash left missing or stale is rewritten from it)."""
        by_path = {}
        for r in self.dnf:
            epoch, arm, pick, session, lang, _item = r["slot"].split("|")
            by_path.setdefault(cr.dnf_path(self.out_root, session, f"{pick}.{session}.{arm}_{lang}"), []).append(r)
        for path, rows in by_path.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            want = "".join(json.dumps(r) + "\n" for r in rows)
            if not path.exists() or path.read_text() != want:
                path.write_text(want)

    # -- the transport policy
    def handle_incomplete(self, load, leg, inv, rec, att, why, sup=None, view=None):
        """`abort_restart` (tg1): the whole load is archived once and rerun, then the chain aborts. `incident_retry` (M64):
        a classified transport incident is recorded, its partial rows accepted, the worker recovered and the same slot
        retried; anything else restarts the load once like tg1. `p426_continue` (tg1-p426): an item DNF is recorded and the
        leg continues on the same load; everything else is systemic (the chain aborts, the leg is INVALID)."""
        if self.p426:
            return self.handle_p426_incomplete(load, leg, inv, rec, att, sup, view)
        if self.config.transport_policy == "abort_restart" or view is None:
            self.check_restart_eligible(att, view, load)
            return "incomplete"
        cause = self.classify_incident(att, sup, load, view)
        if cause is None:
            self.check_restart_eligible(att, view, load)
            return "incomplete"
        self.record_incident(load, leg, inv, rec, att, view, cause)
        self.recover(load, leg, cause)
        return "incident"

    # -- B2 `p426_continue` (spec 5.1 - 5.3)
    def p426_accounted(self, slots):
        """The planned `slots` that are a scored row (`chain_rows`) or a recorded item DNF."""
        table, dnf = self.slot_table(), {d["slot"] for d in self.p426_dnf}
        return {s for s in slots if s in table.scored or s in dnf}

    def run_p426_leg(self, load, leg):
        """The flat-layout leg loop of `p426_continue` (the shape of `run_block_leg`): per planned invocation (the in-load
        pilot phase, then the rest), derive the unaccounted slots from the per-item ledger state, run ONE invocation over them
        on the same loaded instance (no reload), re-derive. An item DNF is accounted by `handle_incomplete`."""
        for inv in leg["invocations"]:
            while True:
                self.check_stop("before launch")
                slots = {e: cr.slot_for(leg["slot_base"], e) for e in inv["expect"]}
                done = self.p426_accounted(slots.values())
                todo = [e for e in inv["expect"] if slots[e] not in done]
                if not todo:
                    break
                step = dict(inv, names=[e.split("/", 1)[1] for e in todo], expect=todo,
                            limit=len(todo) if inv.get("limit") is not None else None)
                load["rec"]["cursor"] = dict(leg_index=leg["li"], phase=step["phase"])
                res = self.run_invocation(load, leg, step)
                if res not in ("ok", "dnf"):
                    raise co.ChainAbort(f"p426_continue: the invocation ended {res!r}")
                if len(self.p426_accounted(slots.values())) <= len(done):
                    raise co.ChainAbort(f"p426_continue: the invocation of {leg['stem']} accounted for no slot")
        return "ok"

    def p426_dnf_eligible(self, att, load, leg, cause, slot=None):
        """None when the abort is an eligible item DNF, else the reason it is systemic: the owned worker identity is
        unchanged, the cleanup certain and, when the hooks reconcile (`dnf_problems`, spec 4.3's DNF rows), the DNF
        window of `slot` settled and reconciled against the abort manifest (its item record is kept in `p426_dnf_item`)."""
        problems = cleanup_problems((att or {}).get("cleanup_status"))
        if problems:
            return "cleanup is not certain and complete: " + "; ".join(problems)
        cur = self.ops.worker_ident(leg["model"])
        if not cur or (cur["pid"], cur["create_time"]) != (load["worker"]["pid"], load["worker"]["create_time"]):
            return "owned worker identity changed or worker gone"
        self.p426_dnf_item = None
        reconcile = getattr(self.hooks, "dnf_problems", None)
        if reconcile is None:
            return None
        if slot is None:
            return "the DNF slot is unknown: section 4.3 cannot be reconciled"
        try:
            manifest = json.loads(Path(leg["out"]).with_suffix(".manifest.json").read_text())
        except (OSError, ValueError) as exc:
            return f"the abort manifest is unreadable: {exc}"
        try:
            found, record = reconcile(slot, manifest)
        except chain_hooks.HookInfrastructureError as exc:
            return f"hook infrastructure error: {exc.cause}"
        self.p426_dnf_item = record
        if found:
            return "section 4.3 DNF row does not hold: " + "; ".join(found)[:600]
        return None

    def handle_p426_incomplete(self, load, leg, inv, rec, att, sup, view):
        if self.p426_invalid:
            raise LegInvalid(f"leg INVALID: {self.p426_invalid[-1]['reason']}")
        if view is None:
            raise co.ChainAbort("p426_continue: an incomplete invocation without its leg view is systemic")
        cur = self.ops.worker_ident(view["model"])
        worker_ok = bool(cur) and (cur["pid"], cur["create_time"]) == (load["worker"]["pid"], load["worker"]["create_time"])
        router_ok = not self.p426_router_problems()          # `(pid, create_time(pid))`, not liveness or a config sha
        stamp = att.get("transport_abort") or {}
        if not (worker_ok and router_ok):
            self.listing(att, view)
            raise co.ChainAbort("p426_continue: owned router / worker identity changed at the incident (systemic)")
        cause = ci.classify_p426_dnf_cause(stamp_cause=stamp.get("cause"), worker_ok=worker_ok, router_ok=router_ok)
        if cause is None:
            self.listing(att, view)
            raise co.ChainAbort(f"p426_continue: an abort without a DNF cause is systemic (stamp cause "
                                f"{stamp.get('cause')!r}, not one of {ci.P426_DNF_CAUSES})")
        if len(self.p426_dnf) >= ci.MAX_P426_DNF:            # the limit is per LEG (both languages), spec 5.1
            raise co.ChainAbort(f"p426_continue: more than {ci.MAX_P426_DNF} DNF in the leg is systemic")
        tentative = list(inv["expect"])[len(self.partial_ids(Path(view["out"])))] if len(
            self.partial_ids(Path(view["out"]))) < len(inv["expect"]) else None
        why = self.p426_dnf_eligible(att, load, view, cause,
                                     slot=cr.slot_for(rec["slot_base"], tentative) if tentative is not None else None)
        if why:
            self.listing(att, view)
            raise co.ChainAbort(f"p426_continue: the abort is not an eligible item DNF: {why}")
        fl = co.in_flight(self.ops.worker_metrics() or {})
        if fl != 0:
            raise co.ChainAbort(f"p426_continue: the worker did not settle (in_flight={fl}); systemic")
        out = Path(view["out"])
        ids = self.partial_ids(out)
        expected = list(inv["expect"])
        if ids != expected[:len(ids)] or len(ids) >= len(expected):
            raise co.ChainAbort(f"p426_continue: the aborted attempt's rows {ids} are not a proper prefix of {expected}")
        self.validate_partial(view, out, ids, who="DNF")
        rec["accepted_slots"] = [cr.slot_for(rec["slot_base"], i) for i in ids]
        rec["sha256"] = sha_file(out) if out.exists() else None
        rec["status"] = "partial_incident"
        failing = cr.slot_for(rec["slot_base"], expected[len(ids)])
        after = self.ops.worker_ident(view["model"])
        owned = dict(worker=dict(cur), router_ok=router_ok)
        record = dict(slot=failing, item=failing.split("|")[-1], session=view["session"], language=view["lang"],
                      seed=view["seed_base"], arm=self.p426_arm_name(), pick=view["model"],     # the predictor arm (spec 16.8)
                      load=load["idx"], load_gen=load["rec"]["load_gen"], attempt=self.p426_attempt_no(att),
                      invocation=next(n for n, r in enumerate(self.progress["invocations"]) if r is rec),     # §16.1: its index
                      invocation_file=rec["file"],
                      abort=dict(cause=cause, error=str(stamp.get("error"))[:200],
                                 evidence=(att.get("abort_evidence") or {}).get("evidence")),
                      owned_at_incident=owned, owned_after=dict(worker=dict(after or {}),
                                                                router_ok=not self.p426_router_problems()),
                      settle=dict(in_flight=fl, settled=True), item_record=self.p426_item_pointer(failing), at=co.utc_stamp())
        from bench import p426_hooks as ph
        record = ph.seal(self.p426_persist(record))       # an immutable record (spec 16): the self-hash covers the portable form
        self.p426_dnf.append(record)                      # chain.json first (with the ledger entry), then the sidecar
        self.p426_ledger.append(dict(slot=failing, kind="dnf", invocation=rec["file"], index=len(self.p426_ledger)))
        self.write_json("p426-dnf")
        side = self.out_root / view["session"] / "p426_dnf" / (cr.slot_file(failing) + ".json")
        ph.write_exclusive(side, record)                  # exclusive-created, the same sealed record
        self.log(f"DNF {failing}: cause={cause}; the leg continues on the same load")
        self.after_invocation(load, leg, inv, rec, cr.rows_if_present(out))
        return "dnf"

    def p426_frozen_record_ref(self):
        """`{path, sha256}` of the frozen record this leg runs under (what a rehearsal / v8 binding checks, fix round 3 item 7);
        the path is persisted portably with the rest of `chain.json`."""
        ref = getattr(self, "_frozen_record_ref", None)
        if ref is None:
            try:
                from bench import p426_record
                ref = dict(path=str(self.a.frozen_record), sha256=p426_record.read_sealed(self.a.frozen_record)["sha256"])
            except Exception:  # noqa: BLE001 — a bare chain / an unreadable record: the leg records none (and then binds to nothing)
                return None
            self._frozen_record_ref = ref
        return ref

    def p426_attempt_no(self, att):
        """§16.1: the `n` of the out-root's name `<leg>.a<n>` (the chain requires that name in P426 mode); the per-stem probe
        counter only when a bare chain has no such name. (The invocation records keep the per-stem counter: it names their
        immutable rows files and restores the counters at resume.)"""
        m = re.search(r"\.a([1-9][0-9]*)$", Path(self.out_root).name)
        return int(m.group(1)) if m else att["attempt"]

    def p426_item_pointer(self, slot):
        """The DNF record's `item_record`: the path string `items/<slot_file>.dnf.json` of the reconciled DNF item record
        (None without hooks that reconcile)."""
        rec = getattr(self, "p426_dnf_item", None)
        if not rec:
            return None
        return f"items/{cr.slot_file(slot)}.dnf.json"

    def p426_hook_context(self, bar, slot, name, stage, row=None):
        """What a P426 hook receives besides the slot (and, at `done`, the payload): the item's ready record, its full row
        (done) and the load context."""
        load = bar["load"]
        return dict(stage=stage, slot=slot, item=name, k=bar["k"], ready=bar.get("ready_record") or {}, row=row,
                    load=dict(idx=load["idx"], load_gen=load["rec"]["load_gen"], worker=dict(load["worker"]),
                              session=bar["view"]["session"], model=bar["view"]["model"], arm=bar["view"]["arm"]))

    def p426_invalidate(self, bar, slot, name, stage, reason):
        """`invalidate`: persisted in chain.json BEFORE the `.stop`; the probe exits cleanup-only, the invocation is accepted
        for its prefix, the cleanup verified and the leg is INVALID (`accept_invocation` raises `LegInvalid`, rc 2)."""
        self.p426_invalid.append(dict(stage=stage, slot=slot, reason=reason, at=co.utc_stamp()))
        if isinstance(bar.get("rec"), dict):                 # a ready-stage stop has no `hook_stop.disposition`: persist it here
            bar["rec"]["hook_disposition"] = "invalidate"
        self.write_json("invalidated")
        barrier_signal(self.barrier_path(bar, "stop"), {"disposition": "invalidate"})
        bar["stage"] = "stopped"
        bar["stop"] = dict(kind="before" if stage == "ready" else "after", k=bar["k"], name=name, slot=slot,
                           disposition="invalidate", reason=reason)
        self.log(f"INVALIDATE {slot} at {stage}: {reason}")

    def classify_incident(self, att, sup, load, leg):
        """A6: the router and the worker are checked INDEPENDENTLY first, then the probe's own cause."""
        cur = self.ops.worker_ident(leg["model"])
        worker_ok = bool(cur) and (cur["pid"], cur["create_time"]) == (load["worker"]["pid"], load["worker"]["create_time"])
        check = getattr(self.ops, "router_ok", None)
        router_ok = True if check is None else bool(check())
        stamp = att.get("transport_abort") or {}
        return classify_incident_cause(
            stamp_cause=stamp.get("cause"), cancelled_idle=bool(sup and sup.get("state") == "cancelled"
                                                                 and sup.get("cancel_reason") == "idle"),
            worker_ok=worker_ok, router_ok=router_ok)

    def partial_ids(self, out):
        try:
            return [r["id"] for r in cr.rows_if_present(out)]
        except cr.ChainRowsError as exc:
            raise co.ChainAbort(f"incident refused: the rows file of the failed attempt is unreadable ({exc})") from None

    def validate_partial(self, leg, out, ids, *, who="incident"):
        """The rows a failed attempt wrote before it failed must validate (everything but the abort itself): config, arm,
        epoch, snapshot and the row schema. Anything wrong there is not an incident."""
        vleg = dict(session=leg["session"], model=leg["model"], lang=leg["lang"], seed_base=leg["seed_base"],
                    expected_ids=list(ids), out=str(out), rc=0, draft_kind=leg.get("draft_kind", "off"),
                    arm_identity_sha256=self.arms.get(self.arm_key(leg)))
        bad = [w for w in co.validate_leg(vleg, self.pinned_for(leg["arm"]), self.ops.wd,
                                          policy_sha=self.policy_for(leg["arm"]), frozen_prompt_date=self.frozen,
                                          spec=self.spec_of(leg["arm"]))
               if not w.startswith(("manifest_abort", "rc_nonzero"))]
        if self.per_arm:                                   # a flat (tg1) leg's rows carry no `arm` / `epoch_id`
            bad += self.arm_row_problems(leg, out)
        if bad:
            raise co.ChainAbort(f"{who} refused: the rows of the failed attempt do not validate: " + "; ".join(bad[:3]))

    def record_incident(self, load, leg, inv, rec, att, view, cause):
        """A7 + A9: the exact cleanup schema, the validated partial rows (`partial_incident`, accepted prefix) and the
        incident record (cause, the failed attempt's tokens, the slot's attempt number)."""
        problems = cleanup_problems(att.get("cleanup_status"))
        if problems:
            self.listing(att, view)
            raise co.ChainAbort("incident refused: cleanup is not certain and complete: " + "; ".join(problems))
        out = Path(view["out"])
        ids = self.partial_ids(out)
        expected = list(inv["expect"])
        if ids != expected[:len(ids)] or len(ids) >= len(expected):
            raise co.ChainAbort(f"incident refused: the failed attempt's rows {ids} are not a proper prefix of {expected}")
        self.validate_partial(view, out, ids)
        rec["accepted_slots"] = [cr.slot_for(rec["slot_base"], i) for i in ids]
        rec["sha256"] = sha_file(out) if out.exists() else None
        rec["status"] = "partial_incident"
        failing = cr.slot_for(rec["slot_base"], expected[len(ids)])
        stamp = att.get("transport_abort") or {}
        tokens, gate_tokens, receipt_tokens = incident_tokens(stamp)
        n = self.incident_count(failing, load) + 1
        self.incidents.append(dict(
            cause=cause, output_tokens=tokens, gate_output_tokens=gate_tokens, receipt_output_tokens=receipt_tokens,
            requests=((stamp.get("gate") or {}).get("requests_completed")), attempt_file=str(att["log"]),
            manifest=rec["manifest"], worker=dict(load["worker"]), worker_full=att.get("worker_full"),
            error=str(stamp.get("error"))[:200], evidence=(att.get("abort_evidence") or {}).get("evidence"),
            web_evidence=(att.get("abort_evidence") or {}).get("web_evidence"), slot=failing, attempt=n, arm=leg["arm"], pick=leg["model"],
            session=leg["session"], lang=leg["lang"], item=failing.split("|")[-1], at=co.utc_stamp(),
            load_gen=load["rec"]["load_gen"], load=load["idx"], invocation=rec["file"], pre_spawn=False))
        self.log(f"INCIDENT {leg['stem']} {failing.split('|')[-1]} attempt {n}: cause={cause} tokens={tokens}")
        self.write_json("incident")
        self.after_invocation(load, leg, inv, rec, cr.rows_if_present(out))

    def recover(self, load, leg, cause):
        """Spec 8.3 recovery before the next attempt: unload + reload the worker (a new identity recorded, A4 per arm),
        cache-session reset, one warm-up request. A dead router needs the ops' `restart_router` (an operator action else)."""
        if cause == "router_error":
            restart = getattr(self.ops, "restart_router", None)
            if restart is None:
                raise co.ChainAbort("recovery: the router is gone or replaced (router_error) and restarting it is an "
                                    "operator action; the incident is recorded")
            restart()
        if self.loaded and not self.ops.unload(self.loaded):
            raise co.ChainAbort(f"recovery: unload of {self.loaded} not verified")
        self.loaded = None
        self.load_worker(load)
        ops = self.config.arm_switch_ops
        if "cache_reset" in ops:
            self.ops.reset_cache_session(load["model"])
        if "warmup" in ops:
            self.ops.warmup(load["model"])
        load["last_arm"] = leg["arm"]
        self.write_json("recovered")

    # -- hooks at the item barrier (R13 R23 R25 R29)
    def item_barrier_on(self, man, arm):
        """The manifest's evidence policy says whether the probe waits at the item barrier; the per-arm layout verifies the
        whole policy against the arm spec (the chain answers exactly what the arm was built for)."""
        return ((man.get("runtime") or {}).get("evidence_policy") or {}).get("item_barrier") == "on"

    def new_barrier(self, rec, inv, base, view, load):
        return dict(k=0, stage="ready", stop=None, rec=rec, inv=inv, base=str(base), view=view, load=load,
                    names=list(inv["names"]), rindex=inv.get("rerun_index", 0))

    def barrier_path(self, bar, kind):
        return Path(f"{bar['base']}.item{bar['k']}.{kind}")

    def pump_barrier(self, bar):
        """One poll of the item barrier: answer `.ready` with `.go` after `run_before(slot)` and `.done` with `.continue`
        after the item's web evidence was extracted and `run_after(slot, done)` decided. Every disposition is persisted in
        chain.json BEFORE the barrier file that acts on it is written."""
        if bar["stage"] == "stopped" or bar["k"] >= len(bar["names"]):
            return
        view, load, rec = bar["view"], bar["load"], bar["rec"]
        name = bar["names"][bar["k"]]
        slot = cr.slot_for(view["slot_base"], f"{view['lang']}/{name}")
        if bar["stage"] == "ready":
            if not self.barrier_path(bar, "ready").exists():
                return
            if self.p426:
                bar["ready_record"] = self.p426_read_json(self.barrier_path(bar, "ready"))
                try:
                    disp = self.hooks.run_before(slot, context=self.p426_hook_context(bar, slot, name, "ready"),
                                                 systemic=True)
                except chain_hooks.HookInfrastructureError as exc:   # B2: systemic, never a `pre_spawn_incident`
                    self.p426_invalidate(bar, slot, name, "ready", f"hook infrastructure error: {exc.cause}")
                    return
                if disp.kind == "invalidate":
                    self.p426_invalidate(bar, slot, name, "ready", disp.reason)
                    return
            else:
                disp = self.hooks.run_before(slot)
            if disp.kind == "pre_spawn_incident":
                self.persist_pre_spawn(bar, slot, name, disp.cause)
                barrier_signal(self.barrier_path(bar, "stop"), {"disposition": "pre_spawn_incident"})
                bar["stage"], bar["stop"] = "stopped", dict(kind="before", k=bar["k"], name=name, slot=slot, cause=disp.cause)
            else:
                barrier_signal(self.barrier_path(bar, "go"))
                bar["stage"] = "done"
            return
        if not self.barrier_path(bar, "done").exists():
            return
        done = json.loads(self.barrier_path(bar, "done").read_text())
        row = next((r for r in cr.read_rows(view["out"]) if r["id"] == done["id"]), None)
        if row is None:
            raise co.ChainAbort(f"item barrier: the row of {done['id']} is not in {Path(view['out']).name} at its done barrier")
        tp = row.get("transcript_path")
        path = co.resolve_portable(tp, self.wd) if tp else None
        web = self.web_record(row, self.web_rules(view["arm"]),
                              path.with_name(path.stem + ".web.jsonl") if path is not None else None)
        done = dict(done, web_evidence=web)
        if self.p426:
            try:
                disp = self.hooks.run_after(slot, done, context=self.p426_hook_context(bar, slot, name, "done", row=row))
            except chain_hooks.HookInfrastructureError as exc:       # B2: systemic
                self.p426_invalidate(bar, slot, name, "done", f"hook infrastructure error: {exc.cause}")
                return
            if disp.kind == "invalidate":
                self.p426_invalidate(bar, slot, name, "done", disp.reason)
                return
        else:
            disp = self.hooks.run_after(slot, done)
        rindex = bar["rindex"]
        if disp.kind != "accept" and not self.per_arm:
            raise co.ChainAbort(f"{disp.kind} for {slot}: this configuration has no same-slot re-run (tg2 step)")
        disposition = chain_hooks.slot_disposition(disp)
        if disp.kind == "rerun_same_slot" and rindex >= cr.MAX_RERUNS:
            disposition = "exhausted"                                  # P201: cheating at the last attempt is a strict fail
        att_rec = dict(slot=slot, rerun_index=rindex, disposition=disposition, load=load["idx"],
                       load_gen=rec["load_gen"], invocation=rec["file"],
                       output_tokens=(row.get("gate") or {}).get("output_tokens_completed"), web_evidence=web)
        if disp.reason:
            att_rec["reason"] = disp.reason
        self.progress["slot_attempts"].append(att_rec)
        self.write_json("slot-disposition")
        if disposition in ("accepted", "exhausted"):
            if self.p426:                       # B2 spec 7: the ledger is persisted at the barrier answer, BEFORE `.continue`
                self.p426_ledger.append(dict(slot=slot, kind="row", invocation=rec["file"], index=len(self.p426_ledger)))
                self.write_json("ledger")
            barrier_signal(self.barrier_path(bar, "continue"))
            bar["k"], bar["stage"] = bar["k"] + 1, "ready"
        else:
            barrier_signal(self.barrier_path(bar, "stop"), {"disposition": disposition})
            bar["stage"], bar["stop"] = "stopped", dict(kind="after", k=bar["k"], name=name, slot=slot,
                                                         disposition=disposition, reason=disp.reason)

    @staticmethod
    def p426_read_json(path):
        """The probe's `.ready` payload (the ready record's probe-side part); `{}` when it carries none."""
        try:
            doc = json.loads(Path(path).read_text() or "{}")
        except (OSError, ValueError):
            return {}
        return doc if isinstance(doc, dict) else {}

    def persist_pre_spawn(self, bar, slot, name, cause):
        """R13: a `before_attempt` failure is a transport incident of the slot (no tokens): the pre-spawn record AND the
        incident are persisted together, THEN the probe is stopped before it spawns anything."""
        view, load, rec = bar["view"], bar["load"], bar["rec"]
        n = self.incident_count(slot, load) + 1
        self.progress["pre_spawn"].append(dict(slot=slot, disposition="pre_spawn_incident", cause=cause, load=load["idx"],
                                               load_gen=rec["load_gen"], invocation=rec["file"], at=co.utc_stamp()))
        self.incidents.append(dict(
            cause=cause, output_tokens=0, gate_output_tokens=0, receipt_output_tokens=None, requests=0,
            attempt_file=None, manifest=rec["manifest"], worker=dict(load["worker"]), worker_full=None, error=None,
            slot=slot, attempt=n, arm=view["arm"], pick=view["model"], session=view["session"], lang=view["lang"],
            item=name, at=co.utc_stamp(), load_gen=rec["load_gen"], load=load["idx"], invocation=rec["file"],
            pre_spawn=True))
        self.log(f"PRE-SPAWN INCIDENT {slot}: {cause}")
        self.write_json("pre-spawn-incident")

    def salvage_hook_stops(self, load, running):
        """Resume: an invocation a crash left `running` whose persisted dispositions prove a hook stop (a cheat / unclear
        slot attempt, or a pre-spawn record) and whose rows file is exactly the prefix that stop implies is finalized as
        `hook_stopped`; everything else stays for the quarantine. Returns the records still `running`."""
        left = []
        for rec in running:
            stop = self.persisted_stop(rec)
            path = self.out_root / rec["file"]
            if stop is None:
                left.append(rec)
                continue
            kind, slot, disposition = stop
            expected = rec["expected_slots"]
            if slot not in expected:
                left.append(rec)
                continue
            cut = expected.index(slot)
            want = expected[:cut] if kind == "before" else expected[:cut + 1]
            try:
                rows = cr.rows_if_present(path)
            except cr.ChainRowsError:
                left.append(rec)
                continue
            try:
                got = [cr.slot_for(rec["slot_base"], r["id"]) for r in rows]
            except cr.ChainRowsError as exc:                     # F28: e.g. a row of another language: not salvageable
                self.log(f"resume: {exc}; the invocation is quarantined instead")
                left.append(rec)
                continue
            if got != want:
                left.append(rec)
                continue
            leg = self.leg_of(load, rec)
            try:
                self.validate_partial(leg, path, [r["id"] for r in rows], who="resume")
            except co.ChainAbort as exc:
                self.log(f"resume: {exc}; the invocation is quarantined instead")
                left.append(rec)
                continue
            rec["accepted_slots"] = want
            rec["sha256"] = sha_file(path) if path.exists() else None
            if kind == "after" and disposition in ("accepted", "exhausted") and want == expected:
                rec["status"] = "validated"             # F9: the whole invocation was decided, only its `.continue` was lost
            else:
                rec["status"] = "hook_stopped"
                rec["hook_stop"] = (dict(before_slot=slot) if kind == "before"
                                    else dict(after_slot=slot, disposition=disposition))
            self.write_json("hook-stop-salvaged")
            self.log(f"RESUME: {rec['file']} finalized as hook_stopped from its persisted disposition ({kind} {slot})")
        return left

    def persisted_stop(self, rec):
        for a in self.progress["slot_attempts"]:
            if a.get("invocation") == rec["file"] and a.get("disposition") in ("cheat", "unclear") \
                    and a.get("status") != "archived":
                return "after", a["slot"], a["disposition"]
        for p in self.progress["pre_spawn"]:
            if p.get("invocation") == rec["file"] and p.get("status") != "archived":
                return "before", p["slot"], None
        # F9: the latest persisted accepted / exhausted decision of the invocation WHOSE `.continue` was never linked (the crash
        # fell between the decision and the barrier file that acts on it); the caller proves the prefix against the rows file
        decided = [a for a in self.progress["slot_attempts"] if a.get("invocation") == rec["file"]
                   and a.get("disposition") in ("accepted", "exhausted") and a.get("status") != "archived"
                   and a["slot"] in rec["expected_slots"]]
        if decided:
            last = max(decided, key=lambda a: rec["expected_slots"].index(a["slot"]))
            base = str(self.out_root / rec["file"])[:-len(".jsonl")]
            if not Path(f"{base}.item{rec['expected_slots'].index(last['slot'])}.continue").exists():
                return "after", last["slot"], last["disposition"]
        return None

    def leg_of(self, load, rec):
        for leg in load["legs"]:
            if rec["leg_key"] == self.leg_key(load, leg):
                return dict(leg, out=str(self.out_root / rec["file"]))
        raise co.ChainAbort(f"progress record {rec['file']} names no leg of this load")

    # -- barrier
    @staticmethod
    def arm_key(leg):
        return f"{leg['model']}|{leg.get('draft_kind', 'off')}"

    def verify_manifest(self, man, leg, block, nonce=None):
        arm = leg.get("arm") or self.arm_ids[0]
        spec = self.spec_of(arm)
        why = []
        problems = self.lifecycle_problems()
        if problems:
            why.append(f"lifecycle drift at barrier: {'; '.join(problems)}")
        problem = self.campaign_problem() if getattr(self, "campaign_core", None) is not None else None
        if problem:
            why.append(f"{problem} (at barrier)")
        why.extend(f"{p} (at barrier)" for p in self.contract_problems())
        frozen_arm = self.arms.get(self.arm_key(leg))
        if frozen_arm is not None and (man.get("runtime") or {}).get("arm_identity_sha256") != frozen_arm:
            why.append(f"arm_identity_sha256: {(man.get('runtime') or {}).get('arm_identity_sha256')!r} != frozen "
                       f"{frozen_arm!r} for {self.arm_key(leg)}")
        rt, wk = man.get("runtime") or {}, man.get("worker")
        chk = [("scaffold", rt.get("scaffold"), self.label_of(arm)),
               ("scaffold_policy_sha256", rt.get("scaffold_policy_sha256"), self.policy_for(arm)),
               ("frozen_prompt_date", rt.get("frozen_prompt_date"), self.frozen),
               ("draft_kind", rt.get("draft_kind"), leg.get("draft_kind", "off")),
               ("seed_base", rt.get("seed_base"), leg["seed_base"]),
               ("lang", rt.get("lang"), leg["lang"]), ("model", man.get("model"), leg["model"]),
               ("sampling_profile", rt.get("sampling_profile", man.get("sampling_profile")), "deployed"),
               ("registry.sha256", (man.get("registry") or {}).get("sha256"), self.ops.overlay_sha())]
        if not (isinstance(nonce, str) and re.fullmatch("[0-9a-f]{64}", nonce)):
            why.append("invocation record has no nonce")
        else:
            chk.append(("invocation_nonce", rt.get("invocation_nonce"), nonce))
        frozen_snapshot = (self.snapshots.get(arm) or {}).get("sha256")
        if frozen_snapshot is not None:
            chk.append(("snapshot_sha256", rt.get("snapshot_sha256"), frozen_snapshot))
        if self.per_arm:
            chk += [("arm", rt.get("arm"), arm), ("epoch_id", rt.get("epoch_id"), self.epoch_id)]
            if not spec.evidence_policy:
                why.append(f"evidence_policy: the arm spec of {arm} states none")
            else:
                chk.append(("evidence_policy", rt.get("evidence_policy"), spec.evidence_policy))
            if self.config.snapshot_complete_required and rt.get("snapshot_complete") is not True:
                why.append("snapshot_complete: the arm's snapshot is incomplete (a real chain needs the registered epoch)")
        pinned = self.pinned_for(arm)
        ident = co.runtime_identity(man, None if spec is None else spec.runtime_pinned)
        for k in self.runtime_pinned(arm):
            if k in pinned:
                chk.append((k, ident.get(k, "<absent>"), pinned[k]))
        if pinned.get("serving_path") is not None:
            chk.append(("git.serving_path", (man.get("git") or {}).get("serving_path"), pinned["serving_path"]))
        for k, got, want in chk:
            if got != want:
                why.append(f"{k}: {got!r} != {want!r}")
        if self.probe_code_arg(arm) is None and pinned.get("probe_code_sha256") is None and not rt.get("probe_code_sha256"):
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
        why += self.evidence_policy_problems(man)
        if man.get("transport_abort"):
            why.append("manifest already records transport_abort")
        why += [f"{f}_invalid" for f in co.malformed_identity(man, spec)]
        return why

    def evidence_policy_problems(self, man):
        """B2 spec 3: in `tg1-p426` the manifest of every invocation states exactly `TG1_P426_EVIDENCE` (unconditional; the
        per-arm layout compares its arm spec's policy instead)."""
        if not self.p426:
            return []
        got = (man.get("runtime") or {}).get("evidence_policy")
        return [] if got == P426_EVIDENCE_POLICY else [
            f"evidence_policy: {got!r} != {P426_EVIDENCE_POLICY!r} (tg1-p426 requires TG1_P426_EVIDENCE)"]

    def probe_code_arg(self, arm):
        return self.arm_arg("probe_code_sha", arm) if self.per_arm else self.a.probe_code_sha

    def _barrier(self, att, leg, block, st, t_spawn):
        mp = Path(leg["out"]).with_suffix(".manifest.json")
        man = None
        try:
            man = json.loads(mp.read_text())
        except (OSError, ValueError):
            pass
        if not man or not man.get("run_id") or man["run_id"] in self.seen_run_ids:
            return
        arm = leg.get("arm") or self.arm_ids[0]
        why = self.verify_manifest(man, leg, block, nonce=((st.get("ctx") or {}).get("rec") or {}).get("nonce"))
        self.seen_run_ids.add(man["run_id"])
        att["run_id"] = man["run_id"]
        if why:
            st["reasons"] = why
            self.log(f"BARRIER MISMATCH {leg['stem']}: {'; '.join(why)} -- no ack")
            return
        pinned = self.pinned_by_arm[arm] if self.per_arm else self.pinned
        runtime = man["runtime"] or {}
        if self.probe_code_arg(arm) is None and pinned.get("probe_code_sha256") is None:
            pinned["probe_code_sha256"] = runtime.get("probe_code_sha256")
            self.log(f"pilot: probe_code_sha256 pinned from first manifest {pinned['probe_code_sha256']}")
        if "generation_identity_sha256" not in pinned:            # P311-lite: the composite, at the arm's first manifest
            pinned["generation_identity_sha256"] = runtime.get("generation_identity_sha256")
            self.log(f"arm {arm}: generation_identity_sha256 frozen from first manifest {pinned['generation_identity_sha256']}"
                     if self.per_arm else
                     f"generation_identity_sha256 pinned from first manifest {pinned['generation_identity_sha256']}")
        if self.arm_key(leg) not in self.arms:                    # one worker identity per (model, predictor)
            self.arms[self.arm_key(leg)] = runtime.get("arm_identity_sha256")
            self.log(f"arm {self.arm_key(leg)}: arm_identity_sha256 frozen from first manifest "
                     f"{self.arms[self.arm_key(leg)]}")
        self.write_json("barrier-ok")
        block["manifest_worker"] = block.get("manifest_worker") or man["worker"]
        Path(att["ack"]).write_text("ack\n")
        st["barrier_done"] = True
        att["worker_full"] = man["worker"]
        if self.item_barrier_on(man, arm) and st.get("ctx"):
            st["bar"] = self.new_barrier(st["ctx"]["rec"], st["ctx"]["inv"], st["ctx"]["base"], leg, block)
        self.log(f"BARRIER ok {leg['stem']} run_id={man['run_id']}: ack created")

    # -- supervise
    def evidence_namespace(self, leg):
        return self.specs[leg["arm"]].evidence_dir if self.per_arm else "opencode_transcripts"

    def evidence_root(self, leg, att):
        if not att.get("run_id"):
            return None
        return Path(self.ops.wd) / self.evidence_namespace(leg) / leg["model"] / f"{Path(leg['out']).stem}.{att['run_id']}"

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

    def supervise(self, att, proc, leg, step, block, rec=None, inv=None, base=None):
        clock, tm = self.clock, self.tm
        t0 = clock()
        hb = Heartbeat(att["log"], clock, t0)
        idle = co.IdlePredicate(tm.idle_sample_s, tm.hb_age_s, tm.idle_needed)
        st = dict(barrier_done=False, reasons=None, cancel_at=None, tcoop=None, stage=0, deadline=None, base=None,
                  stop=False, cancel_reason=None, bar=None, ctx=(dict(rec=rec, inv=inv, base=base) if rec is not None else None))
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
                if st["bar"] is not None and st["cancel_at"] is None:
                    self.pump_barrier(st["bar"])
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
        return dict(state=state, reasons=st["reasons"] or [], stop=st["stop"], cancel_reason=st["cancel_reason"],
                    hook=(st["bar"] or {}).get("stop"))

    # -- watcher
    def watch_rows(self, leg, step):
        """(rows, ids) the watch log counts: the leg's earlier validated invocations plus this one's file."""
        # P469: `prior_rows` keeps the bare item names while row ids are `lang/item`; unprefixed, the earlier invocations'
        # rows were filtered out (a validated pilot of 1 row beside a running full invocation read 0)
        prior = [x if "/" in x else f"{leg['lang']}/{x}" for x in leg.get("prior_ids") or []]
        ids = prior + [f"{leg['lang']}/{x}" for x in step["names"]]
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

    def prediction_s(self, key, walls):
        """Per-item seconds predicted for `key` = (lang, model): an explicit `--pred-s`, else the pilot mean once >= 5 rows
        exist, else the builder's table entry, else GENERIC_PRED_S."""
        if key in self.explicit_pred:
            return self.explicit_pred[key]
        if len(walls) >= PILOT_N:
            return sum(walls[:PILOT_N]) / PILOT_N
        return self.pred.get(key, GENERIC_PRED_S)

    def watch_tick(self, att, leg, step, block, hb, st, t0):
        rows, ids = self.watch_rows(leg, step)
        n, total = len(rows), len(ids)
        walls = [r.get("wall_s") or 0 for r in rows]
        mean = sum(walls) / n if n else None
        pred = self.prediction_s((leg["lang"], leg["model"]), walls)
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
