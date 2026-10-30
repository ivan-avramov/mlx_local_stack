"""B2 (P426) Wave-2 sequencer (docs/specs/p426-b2-tg1-wave2.md sections 1, 5.5, 6.7, 8, 9, 10, 16.5, 16.6):

  python -m bench.p426_wave2 run      --record-dir D --worktree-off W --worktree-on W --out-base B [--through LEG] [--pause-file F]
  python -m bench.p426_wave2 makeup   --record-dir D --worktree-off W --worktree-on W --out-base B --occurrences FILE
  python -m bench.p426_wave2 rehearsal --manifest M  --worktree-off W --worktree-on W --out-base B

`run` launches legs 1-8 in order (pilot pair, the pilot gate, s1 off/on, s2 on/off, reload on/off) and stops after leg 8; each leg is
ONE `run_tg1_chain.py --p426` invocation from its arm's worktree on a fresh out-root `<out-base>/<leg>.a<n>`. The sequencer owns
`SEQUENCER.lock` for the whole sequence (never `LEG.lock`; each chain takes its own), writes `LAST_LEG_END` when a leg ends and waits
600 s before the next, supervises the chain and its watcher without ever killing either, writes `OVERRUN_PAUSED` at the leg's
deadline, classifies and harvests every leg (any state), writes one immutable pair dossier per pair attempt and publishes it. A
systemic failure stops the sequence; a rerun is the operator's decision (`--rerun LEG --rerun-reason TEXT`: a new attempt on a fresh
out-root). `<out-base>/sequence.json` is the state file: resume = the same command. `ops` supplies everything that touches the box:
`launch`, `alive`, `wait`, `power`, `harvest`, `harvest_path`, `publish_dossier`, `publish_run_files`, `operator_emails`, and
(delegated to `bench.p426_freeze`) `worktree_state`, `identity`, `historical_walls`. Process identity is the start time the ops report
(`ChainOps.create_time`, C151)."""
from __future__ import annotations

import argparse
import datetime
import getpass
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from . import chain_ops as co
from . import p426_freeze as fz
from . import p426_hooks as ph
from . import p426_ids
from . import p426_locks as pl
from . import p426_receipt as pr
from . import p426_record

ENTRY = p426_ids.ENTRY
POLL_S = 30.0                                        # the supervision tick: chain, watcher and deadline
WATCH_INTERVAL_S = 300.0                             # the watcher's own interval (spec 8)
WATCHER_GRACE_S = 3 * WATCH_INTERVAL_S               # how long after the chain's exit a watcher may take to finalize
REHEARSAL_DEADLINE_S = 6 * 3600.0                    # rehearsal legs are not in a frozen record: a generous fixed supervision bound
POWER = dict(watts=140, volts=28, battery_above=20)  # spec 8 / AGENTS: checked before a launch (the chain checks it again at entry)
VALID_STATES = ("VALID", "VALID_WITH_DNF")
MAX_DNF = 2                                          # spec 5.1: more than 2 DNF in a leg is systemic
SESSIONS = ("s1", "s2", "reload", "pilot", "makeup")
SESSION_ORDER = ("s1", "s2")
LANG_ORDER = {"s1": ("python", "go"), "s2": ("go", "python")}      # spec 7: s2 reverses the language order
SESSION_SEED = {"s1": 1001, "s2": 2002}
OVERRUN_FILE, SEQUENCE_FILE, LOG_FILE = "OVERRUN_PAUSED", "sequence.json", "sequence.log"
WAVE2_DIR, REHEARSAL_DIR = "p426/wave2", "p426/rehearsal"
CHAIN_ENTRY = ("benchmark", "chains", "c147", "run_tg1_chain.py")          # in parts: this module reads no chain rows (test_p371_chain_rows)
SEAMS = ("launch", "alive", "wait", "power", "harvest", "harvest_path", "publish_dossier", "publish_run_files", "operator_emails",
         "worktree_state", "identity")                 # `notify` is optional; `historical_walls` is needed by `run` only (the amendment)


class Stop(Exception):
    """The sequence stops here with exit code `rc` (1 a leg / gate / pair / drift, 3 an overrun, 4 a harvest); the reason is logged."""

    def __init__(self, rc, message):
        super().__init__(message)
        self.rc = rc


# ----------------------------------------------------------------------------------------------- the leg table (spec 1)
def _leg(n, name, arm, head, kind, pair=None, role=None, record="amendment", extra=(), expect="VALID"):
    """A leg's plan (how many slots it realizes) is never kept here: it is read from the leg's own frozen schedule (spec 16.8)."""
    return dict(n=n, name=name, arm=arm, head=list(head), kind=kind, pair=pair, role=role, record=record, extra=list(extra), expect=expect)


RUN_LEGS = (
    _leg(1, "tg1-p426-off-pilot", "off", ["pilot"], "pilot", "pilot", "first", "v8"),
    _leg(2, "tg1-p426-on-pilot", "on", ["pilot"], "pilot", "pilot", "second", "v8"),
    _leg(3, "tg1-p426-off-s1", "off", ["chain", "s1"], "s1", "s1", "first"),
    _leg(4, "tg1-p426-on-s1", "on", ["chain", "s1"], "s1", "s1", "second"),
    _leg(5, "tg1-p426-on-s2", "on", ["chain", "s2"], "s2", "s2", "first"),
    _leg(6, "tg1-p426-off-s2", "off", ["chain", "s2"], "s2", "s2", "second"),
    _leg(7, "tg1-p426-on-reload", "on", ["chain", "reload"], "reload", "reload", "first"),
    _leg(8, "tg1-p426-off-reload", "off", ["chain", "reload"], "reload", "reload", "second"),
)
MAKEUP_LEGS = (
    _leg(9, "tg1-p426-off-makeup", "off", ["makeup"], "makeup", "makeup", "first"),
    _leg(10, "tg1-p426-on-makeup", "on", ["makeup"], "makeup", "makeup", "second"),
)
REHEARSAL_LEGS = (
    _leg("R1", "tg1-p426-rehearsal-off", "off", ["chain", "s1"], "rehearsal", "r1", "first", "manifest", extra=["--rehearsal"]),
    _leg("R1", "tg1-p426-rehearsal-on", "on", ["chain", "s1"], "rehearsal", "r1", "second", "manifest", extra=["--rehearsal"]),
    _leg("R2", "tg1-p426-rehearsal-mismatch", "on", ["chain", "s1"], "rehearsal", record="manifest",
         extra=["--rehearsal", "--inject", "reconcile-mismatch"], expect="INVALID"),
    _leg("R3", "tg1-p426-rehearsal-kill", "off", ["chain", "s1"], "rehearsal", record="manifest",
         extra=["--rehearsal", "--inject", "stall-kill"]),
)
BY_NAME = {leg["name"]: leg for leg in (*RUN_LEGS, *MAKEUP_LEGS, *REHEARSAL_LEGS)}
PREDICTOR = {"off": "off", "on": "mtp"}


def spec_of(leg):
    spec = leg if isinstance(leg, dict) else BY_NAME.get(leg)
    if spec is None:
        raise ValueError(f"unknown leg {leg!r}")
    return spec


def pair_legs(pair):
    """{arm: leg spec} of one pair, from the table."""
    return {leg["arm"]: leg for leg in BY_NAME.values() if leg["pair"] == pair}


def out_root_of(leg, attempt, out_base) -> Path:
    spec = spec_of(leg)
    return Path(out_base) / f"{spec['name']}.a{attempt}"                 # flat for every attempt, make-up included (spec 16.8)


def leg_argv(leg, attempt, *, worktrees, record_path, out_base, pair_receipt=None, occurrences=None, identity=None) -> list:
    """The chain argv of one leg attempt (spec 6.7): the arm's own venv python and `run_tg1_chain.py` from its worktree, the common
    flags, then (second legs) `--pair-receipt`, (make-up) `--occurrences`. `record_path` is the record the leg runs under (v8 base for
    legs 1-2, the timeout amendment for 3-10, the rehearsal manifest for R1-R3); a manifest carries no probe identity, so
    `identity` {probe_code_sha256, scaffold_policy_sha256, frozen_prompt_date} is required for it."""
    spec = spec_of(leg)
    if not (isinstance(attempt, int) and not isinstance(attempt, bool) and attempt >= 1):
        raise ValueError(f"attempt must be an integer >= 1, not {attempt!r}")
    if spec["kind"] == "makeup" and occurrences is None:
        raise ValueError("a make-up leg needs its occurrences file")
    rehearsal = spec["record"] == "manifest"
    rec = p426_record.load(record_path, mode="pilot" if spec["head"] == ["pilot"] else "chain", rehearsal=rehearsal)
    base = dict(rec["base"])
    if rehearsal:
        base.update(identity or {})                          # the manifest records the identity and the date (spec 16.8)
        if not all(base.get(k) for k in ("probe_code_sha256", "scaffold_policy_sha256", "frozen_prompt_date")):
            raise ValueError("a rehearsal leg needs the probe identity and the frozen date (the manifest carries none)")
    arm = spec["arm"]
    wt = Path(worktrees[arm])
    argv = [str(wt / ".venv-bench/bin/python"), str(wt.joinpath(*CHAIN_ENTRY)), *spec["head"], "--p426",
            "--models", ENTRY, "--predictor", PREDICTOR[arm], "--out-root", str(out_root_of(spec, attempt, out_base)),
            "--probe-code-sha", base["probe_code_sha256"], "--policy-sha", base["scaffold_policy_sha256"],
            "--frozen-prompt-date", base["frozen_prompt_date"], "--campaign-core", base[f"{arm}_commit"],
            "--frozen-record", str(record_path), *spec["extra"]]
    if pair_receipt is not None:
        argv += ["--pair-receipt", str(pair_receipt)]
    if occurrences is not None:
        argv += ["--occurrences", str(occurrences)]
    return argv


# ----------------------------------------------------------------------------------------------- deadlines (spec 10.2)
def deadline_s(session, langs, amendment) -> float:
    """`T = 1.5 x sum_lang n_lang x w_lang + 1800 s` with the amendment's walls; `langs` = {lang: n}."""
    if session not in SESSIONS:
        raise ValueError(f"unknown session {session!r}")
    return fz.deadline_formula(langs, {"python": amendment["w_python_s"], "go": amendment["w_go_s"]})


def leg_deadline(amendment, base, leg, langs=None) -> float:
    """The supervision deadline of one leg: the v8 base's pilot deadline, the amendment's per-session value (one value for both
    arms of a session), a make-up leg's from its occurrences' languages, a rehearsal leg's fixed bound."""
    spec = spec_of(leg)
    kind = spec["kind"]
    if kind == "pilot":
        return float(base["pilot_deadline_s"])
    if kind == "rehearsal":
        return REHEARSAL_DEADLINE_S
    if kind == "makeup":
        return deadline_s("makeup", langs, amendment)
    return float(amendment["leg_deadline_s"][kind])


# ----------------------------------------------------------------------------------------------- make-up (spec 5.5)
def canonical_occurrences(occurrences) -> list:
    """The union of the occurrences, one record per (session, language, item, seed) with the DNF'd arms merged, in the section 5.5
    order: s1 then s2, the session's language order, `occurrence` (the 0-based position in the leg's frozen order), item. One
    implementation, shared with the chain's make-up schedule (`schedules.makeup_canonical`)."""
    from . import schedules
    return schedules.makeup_canonical(occurrences)


def makeup_groups(occurrences) -> list:
    """One group per (session, seed, language), in the canonical order, items in their original order (a chain invocation each)."""
    groups = {}
    for m in canonical_occurrences(occurrences):
        groups.setdefault((m["session"], m["seed"], m["language"]), []).append(m["item"])
    return [dict(session=s, seed=seed, language=lang, items=items) for (s, seed, lang), items in groups.items()]


def not_run(root, canonical) -> list:
    """The occurrences with no slot in the leg's realized ledger (a row or a DNF both count as run)."""
    try:
        ledger = fz.read_chain(root).get("p426_ledger") or []
    except fz.Refusal:
        ledger = []
    done = {tuple(e["slot"].split("|")[3:6]) for e in ledger}
    return [m for m in canonical if (m["session"], m["language"], m["item"]) not in done]


# ----------------------------------------------------------------------------------------------- classification (spec 5.1)
def planned_slots(root, chain=None) -> int:
    """The leg's plan: the slots of its frozen schedule (`schedule.json`, whose sha256 `chain.json` records), never a constant
    (spec 16.8). ValueError when the schedule is missing, unreadable, malformed or not the frozen one."""
    return fz.planned_slots(root, chain)


def classify_leg(root, rc, *, arm) -> dict:
    """`{state, class, reason}` of an ended leg from the chain's rc and its `chain.json`, the realized ledger against the leg's
    own frozen schedule, and the item records."""
    root = Path(root)
    try:
        chain = fz.read_chain(root)
    except fz.Refusal:
        if rc == 2:
            return dict(state="NOT_STARTED", **{"class": "entry"}, reason="the chain refused before the router started (no chain.json)")
        return dict(state="INVALID", **{"class": "systemic"}, reason=f"chain rc {rc} and no chain.json")

    def invalid(reason):
        return dict(state="INVALID", **{"class": "systemic"}, reason=reason)
    if chain.get("p426_invalid"):
        return invalid(str(chain["p426_invalid"][-1].get("reason")))
    if rc != 0 or chain.get("status") != "finished":
        return invalid(f"chain rc {rc}, status {chain.get('status')!r}")
    open_inv = [i for i in (chain.get("progress") or {}).get("invocations") or [] if i.get("status") in ("running", "quarantined")]
    if open_inv:
        return invalid(f"{len(open_inv)} invocation(s) still {open_inv[0]['status']}")
    ledger = chain.get("p426_ledger") or []
    try:
        planned = planned_slots(root, chain)
    except ValueError as exc:
        return invalid(str(exc))
    if len(ledger) != planned:
        return invalid(f"the realized ledger has {len(ledger)} slots, the frozen schedule {planned}")
    dnf = len(chain.get("p426_dnf") or [])
    if dnf > MAX_DNF:
        return invalid(f"{dnf} DNF in the leg (more than {MAX_DNF})")
    problems = fz.leg_items_problems(root, arm)
    if problems:
        return invalid(problems[0])
    if dnf:
        return dict(state="VALID_WITH_DNF", **{"class": "dnf"}, reason=f"{dnf} transport DNF, settled")
    return dict(state="VALID", **{"class": "valid"}, reason="")


def pilot_gate(off_root, on_root) -> list:
    """Spec 1: both legs VALID, 5 / 5 items reconciled, zero DNF, ON engagement proven on every eligible request, both speed-valid,
    the pair gate passed. Returns the failed conditions (empty = the gate passes)."""
    return fz.pilot_gate_problems(off_root, on_root)          # owned by `write_amendment` (fix round 3, item 6)


# ----------------------------------------------------------------------------------------------- sequence.json (spec 16.7)
def read_sequence(out_base) -> dict:
    path = Path(out_base) / SEQUENCE_FILE
    doc = json.loads(path.read_text()) if path.is_file() else {}
    for key in ("legs", "pairs", "harvested", "reruns"):
        doc.setdefault(key, [])
    return doc


def write_sequence(out_base, doc) -> dict:
    """Atomic replace; the new version names the sha256 of the version it replaces (null for the first)."""
    path = Path(out_base) / SEQUENCE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    doc = dict(doc, previous_sha256=previous)
    tmp = path.with_name(SEQUENCE_FILE + ".tmp")
    with open(tmp, "w") as f:
        f.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return doc


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def speed_of(path) -> dict:
    """`{valid, reason}` of a leg's speed block from its `watch.jsonl` (the watcher's own verdict function)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "m1"))
    try:
        import bench_watch
    finally:
        sys.path.pop(0)
    return bench_watch.speed_verdict(path)


# ----------------------------------------------------------------------------------------------- the sequencer
class Sequencer:
    def __init__(self, a, ops, clock, sleep, wd):
        self.a, self.ops, self.clock, self.sleep, self.wd = a, ops, clock, sleep, Path(wd)
        self.out = Path(a.out_base)
        self.worktrees = {"off": Path(a.worktree_off), "on": Path(a.worktree_on)}
        self.pause = Path(a.pause_file) if a.pause_file else self.out / "PAUSE"
        self.record_dir = Path(a.record_dir) if getattr(a, "record_dir", None) else None
        self.seq = read_sequence(self.out)
        self.emails = ()
        self.run_files_done = False
        self.run_files_failed = False
        self.identity = None
        self.canon = None

    # -- state and log
    def log(self, message):
        stamp = datetime.datetime.fromtimestamp(self.clock(), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self.out.mkdir(parents=True, exist_ok=True)
        with (self.out / LOG_FILE).open("a") as f:
            f.write(f"{stamp} {message}\n")
        print(f"{stamp} {message}", flush=True)

    def save(self):
        self.seq = write_sequence(self.out, self.seq)

    def entries(self, name):
        return [e for e in self.seq["legs"] if e["leg"] == name]

    def harvested(self, entry):
        return any(h["attempt"] == f"{entry['leg']}.a{entry['attempt']}" for h in self.seq["harvested"])

    def selected(self, name):
        """The leg's latest VALID attempt that is harvested (the one a pair names)."""
        done = [e for e in self.entries(name) if e["state"] in VALID_STATES and self.harvested(e)]
        return done[-1] if done else None

    def root(self, spec, attempt):
        return out_root_of(spec, attempt, self.out)

    # -- records (spec 10.1, 16.1)
    def load_records(self):
        """Read and verify the records this command runs under. A refusal (rc 2) at the start; a Stop (rc 1) between legs."""
        a = self.a
        if a.cmd == "rehearsal":
            try:
                self.record = p426_record.load(a.manifest, mode="chain", rehearsal=True)
            except p426_record.RecordError as exc:
                raise fz.Refusal(f"--manifest {exc}") from None
            self.base, self.amendment = self.record["doc"], None
            if self.base.get("frozen_prompt_date") != a.frozen_prompt_date:
                raise fz.Refusal(f"--frozen-prompt-date {a.frozen_prompt_date!r} is not the manifest's "
                                 f"{self.base.get('frozen_prompt_date')!r} (the date is frozen when the manifest is written)")
            return
        try:
            base = p426_record.read_sealed(self.record_dir / "v8_base.json")
        except p426_record.RecordError as exc:
            raise fz.Refusal(f"v8_base.json: {exc}") from None
        if base.get("kind") != fz.KIND_V8:
            raise fz.Refusal(f"v8_base.json: kind {base.get('kind')!r} is not {fz.KIND_V8}")
        self.base, self.amendment = base, None
        path = self.record_dir / "amendment.json"
        if path.exists():
            try:
                self.amendment = p426_record.load(path, mode="chain")["doc"]
            except p426_record.RecordError as exc:
                raise fz.Refusal(f"amendment.json: {exc}") from None
        elif a.cmd == "makeup":
            raise fz.Refusal(f"{path.name} is missing: the pilot gate has not written the timeout amendment")

    def record_path(self, spec):
        if spec["record"] == "manifest":
            return Path(self.a.manifest)
        return self.record_dir / ("v8_base.json" if spec["record"] == "v8" else "amendment.json")

    def verify_world(self):
        """Before every launch: the records still verify and the live worktrees are the ones they name."""
        try:
            self.load_records()
        except fz.Refusal as exc:
            raise Stop(1, f"STOP: a record changed: {exc}") from None
        if self.a.cmd == "rehearsal":
            problems = []
            for arm in ("off", "on"):
                st = self.ops.worktree_state(self.worktrees[arm])
                if st.get("head") != self.base[f"{arm}_commit"]:
                    problems.append(f"the {arm} worktree HEAD {str(st.get('head'))[:12]} != the manifest's {self.base[f'{arm}_commit'][:12]}")
                if st.get("clean") is not True:
                    problems.append(f"the {arm} worktree is not clean")
        else:
            problems = fz.live_problems(self.base, self.ops, self.wd)
        if problems:
            raise Stop(1, "STOP: drift against the frozen record: " + "; ".join(problems))

    def check_power(self):
        p = self.ops.power() or {}
        ok = (p.get("watts") == POWER["watts"] and p.get("volts") == POWER["volts"]
              and p.get("battery") is not None and p["battery"] > POWER["battery_above"])
        if not ok:
            raise Stop(1, f"STOP: power {p.get('watts')} W / {p.get('volts')} V, battery {p.get('battery')} % before a launch "
                          f"(needs {POWER['watts']} W / {POWER['volts']} V, battery > {POWER['battery_above']} %)")

    # -- the boundary: PAUSE and the idle gap (spec 1, 9)
    def last_leg_end(self):
        try:
            return pl.read_last_leg_end(self.wd)
        except ValueError as exc:
            raise Stop(1, f"STOP: {exc}") from None

    def wait_boundary(self):
        held, released = False, None
        while True:
            if self.pause.exists():
                if not held:
                    self.log(f"PAUSE: holding at the leg boundary ({self.pause})")
                    held = True
                self.sleep(POLL_S)
                continue
            if held:
                held, released = False, self.clock()
                self.log("PAUSE removed: the idle gap restarts")
            refs = [t for t in (self.last_leg_end(), released) if t is not None]
            if not refs:
                return
            since = self.clock() - max(refs)
            if since >= pl.IDLE_GAP_S:
                return
            self.sleep(min(pl.IDLE_GAP_S - since, POLL_S))

    # -- one leg
    def next_attempt(self, spec):
        nums = [e["attempt"] for e in self.entries(spec["name"])]
        base = out_root_of(spec, 1, self.out).parent
        if base.is_dir():
            nums += [int(m.group(1)) for p in base.iterdir() if (m := re.fullmatch(re.escape(spec["name"]) + r"\.a([1-9][0-9]*)", p.name))]
        return max(nums + [0]) + 1

    def partner_receipt(self, spec):
        """The first leg's receipt for the second leg of a pair (spec 6.5); a restart between the legs resumes from the persisted file."""
        if spec["role"] != "second":
            return None
        first = pair_legs(spec["pair"])
        first = next(s for s in first.values() if s["role"] == "first")
        entry = self.selected(first["name"])
        if entry is None:
            raise Stop(1, f"STOP: no VALID harvested attempt of {first['name']} to pair {spec['name']} with")
        path = self.root(first, entry["attempt"]) / "receipt.json"
        if not path.is_file():
            raise Stop(1, f"STOP: {first['name']}.a{entry['attempt']} left no receipt.json for the pair gate")
        return path

    def deadline(self, spec):
        langs = None
        if spec["kind"] == "makeup":
            langs = {}
            for m in self.canon:
                langs[m["language"]] = langs.get(m["language"], 0) + 1
        return leg_deadline(self.amendment, self.base, spec, langs)

    def start_watcher(self, spec, root, handle):
        wt = self.worktrees[spec["arm"]]
        argv = [str(wt / ".venv-bench/bin/python"), str(wt / "benchmark/m1/bench_watch.py"), "--chain-json", str(root / "chain.json"),
                "--driver-pid", str(handle.pid), "--out", str(root / "watch.jsonl"), "--interval", str(int(WATCH_INTERVAL_S)),
                "--pred-s", str(self.base.get("generic_pred_s", 250))]
        return self.ops.launch(argv, cwd=wt, pass_fds=())

    def supervise(self, spec, attempt, root, handle):
        """Wait for the chain; poll the watcher; write `OVERRUN_PAUSED` at the deadline. Nothing is ever signalled."""
        deadline, t0 = self.deadline(spec), self.clock()
        watcher, watcher_dead, overrun = None, None, False
        while self.ops.alive(handle.pid, handle.start):
            if watcher is None and root.exists():
                watcher = self.start_watcher(spec, root, handle)
                self.log(f"watcher PID {watcher.pid} bound to chain PID {handle.pid}")
            if watcher is not None and watcher_dead is None and not self.ops.alive(watcher.pid, watcher.start):
                watcher_dead = self.clock()
                self.log(f"{spec['name']}.a{attempt}: the watcher died while the chain was running (the leg is speed-invalid)")
            if not overrun and self.clock() - t0 >= deadline:
                overrun = True
                atomic_text(self.out / OVERRUN_FILE, json.dumps(dict(leg=spec["name"], attempt=attempt, deadline_s=deadline,
                                                                    at=co.utc_stamp(self.clock())), sort_keys=True) + "\n")
                message = f"OVERRUN_PAUSED: {spec['name']}.a{attempt} passed its {deadline:.0f} s deadline; never killed, the operator decides"
                self.log(message)
                if getattr(self.ops, "notify", None):
                    self.ops.notify(message)
            self.sleep(POLL_S)
        rc = self.ops.wait(handle)
        return rc, t0, watcher, watcher_dead, overrun

    def finish_watcher(self, watcher):
        """After the chain's exit the watcher finalizes its journal; wait for its exit (bounded, never killed)."""
        if watcher is None:
            return True
        since = self.clock()
        while self.ops.alive(watcher.pid, watcher.start):
            if self.clock() - since > WATCHER_GRACE_S:
                return False
            self.sleep(POLL_S)
        return True

    def run_leg(self, spec):
        self.wait_boundary()
        self.verify_world()
        self.check_power()
        attempt = self.next_attempt(spec)
        name = f"{spec['name']}.a{attempt}"
        root = self.root(spec, attempt)
        first_receipt = self.partner_receipt(spec)
        occurrences = None
        if spec["kind"] == "makeup":
            occurrences = self.out / "makeup" / f"occurrences.{spec['arm']}.jsonl"
            atomic_text(occurrences, "".join(json.dumps(m, sort_keys=True) + "\n" for m in self.canon))
        argv = leg_argv(spec, attempt, worktrees=self.worktrees, record_path=self.record_path(spec), out_base=self.out,
                        pair_receipt=first_receipt, occurrences=occurrences, identity=self.identity)
        entry = dict(leg=spec["name"], attempt=attempt, state="RUNNING")
        self.seq["legs"].append(entry)
        self.save()
        self.log(f"START {name}: " + json.dumps(argv))
        handle = self.ops.launch(argv, cwd=self.worktrees[spec["arm"]], pass_fds=())
        self.log(f"chain PID {handle.pid}")
        rc, t0, watcher, watcher_dead, overrun = self.supervise(spec, attempt, root, handle)
        ended = self.clock()
        atomic_text(self.wd / pl.LAST_LEG_END, repr(float(ended)) + "\n")
        cls = classify_leg(root, rc, arm=spec["arm"])
        if overrun and cls["state"] == "INVALID" and not self.finished_cleanly(root):
            cls = dict(cls, state="OVERRUN")
        settled = self.finish_watcher(watcher)
        if watcher is None:
            speed = dict(valid=False, reason="no watcher was started (the leg never created its out-root)")
        elif watcher_dead is not None:
            speed = dict(valid=False, reason="the watcher died before the chain exited")
        elif not settled:
            speed = dict(valid=False, reason="the watcher did not finalize its journal")
        else:
            speed = speed_of(root / "watch.jsonl")
        root.mkdir(parents=True, exist_ok=True)
        doc = dict(leg=spec["name"], attempt=attempt, state=cls["state"], reason=cls["reason"], chain_rc=rc,
                   started=co.utc_stamp(t0), ended=co.utc_stamp(ended), speed_valid=bool(speed["valid"]),
                   speed_reason=speed["reason"], overrun=overrun, **{"class": cls["class"]})
        if spec["kind"] == "makeup" and cls["state"] not in VALID_STATES:
            doc["not_run"] = not_run(root, self.canon)
        ph.write_exclusive(root / "leg.json", doc)
        entry["state"] = cls["state"]
        self.save()
        self.log(f"END {name}: rc {rc} state {cls['state']}" + (f" ({cls['reason']})" if cls["reason"] else ""))
        if not settled:
            raise Stop(1, f"STOP: the watcher of {name} is still alive {WATCHER_GRACE_S:.0f} s after the chain exited (not killed)")
        self.harvest(spec, entry)
        if overrun:
            raise Stop(3, f"STOP: {name} overran its deadline (OVERRUN_PAUSED); remove {OVERRUN_FILE} to resume")
        return entry

    @staticmethod
    def finished_cleanly(root):
        try:
            chain = fz.read_chain(root)
        except fz.Refusal:
            return False
        return bool(chain.get("p426_invalid")) or chain.get("status") == "finished"

    def harvest(self, spec, entry):
        name = f"{entry['leg']}.a{entry['attempt']}"
        res = self.ops.harvest(self.root(spec, entry["attempt"]), emails=self.emails)
        if res.get("rc") != 0:
            line = " ".join(str(res.get("message") or "").split())[:600]       # the harvest's own `REFUSED:` / `ERROR:` line (no values)
            if line:
                self.log(f"harvest {name}: {line}")
            raise Stop(4, f"STOP: the harvest of {name} failed (rc {res.get('rc')}); a rerun of the same command retries it")
        self.seq["harvested"].append(dict(attempt=name, harvest_sha256=res["harvest_sha256"]))
        self.save()
        self.log(f"HARVESTED {name}")

    # -- pairs and the pilot gate
    def ensure_dossier(self, spec):
        legs = pair_legs(spec["pair"])
        sel = {arm: self.selected(s["name"]) for arm, s in legs.items()}
        if None in sel.values():
            return
        attempts = {arm: f"{legs[arm]['name']}.a{sel[arm]['attempt']}" for arm in sel}
        path = self.out / "pairs" / f"{spec['pair']}__off-a{sel['off']['attempt']}__on-a{sel['on']['attempt']}.json"
        record = next((p for p in self.seq["pairs"] if p["off"] == attempts["off"] and p["on"] == attempts["on"]), None)
        # the verdict is always recomputed from the current receipts: a stored dossier (or `sequence.json` record) is verified, never trusted
        roots = {arm: self.root(legs[arm], sel[arm]["attempt"]) for arm in sel}
        off, on = fz.read_receipt(roots["off"]), fz.read_receipt(roots["on"])
        problems = pr.pair_problems(off, on)
        differences = pr.observed_differences(off, on) if not problems else [
            dict(process="-", field="pair_gate", off=None, on=p) for p in problems]
        verdict = "PASS" if not problems else "FAIL"
        harvests = {arm: Path(self.ops.harvest_path(attempts[arm])) / "HARVEST.json" for arm in sel}
        if path.exists():
            self.verify_dossier(path, spec["pair"], attempts, roots, harvests, differences, verdict)
        else:
            pr.write_dossier(path, pair=spec["pair"],
                             off=dict(attempt=attempts["off"], receipt=roots["off"] / "receipt.json", harvest=harvests["off"]),
                             on=dict(attempt=attempts["on"], receipt=roots["on"] / "receipt.json", harvest=harvests["on"]),
                             differences=differences, verdict=verdict)
        if record is None:
            record = dict(pair=spec["pair"], off=attempts["off"], on=attempts["on"], dossier=f"pairs/{path.name}", verdict=verdict)
            self.log(f"DOSSIER {path.name}: {verdict}" + ("" if verdict == "PASS" else " — " + "; ".join(problems)[:600]))
            self.publish_dossier_or_stop(path)               # published BEFORE the pair state records it (a failure is exit 4)
            record["published"] = self.a.cmd != "rehearsal"        # a rehearsal publishes nothing
            self.seq["pairs"].append(record)
            self.save()
        elif not record.get("published") and self.a.cmd != "rehearsal":
            self.publish_dossier_or_stop(path)
            record["published"] = True
            self.save()
        if verdict != "PASS":
            raise Stop(1, f"STOP: the pair gate failed for {spec['pair']} (dossier {path.name}); the operator decides")

    def publish_dossier_or_stop(self, path):
        """Publish one pair dossier (idempotent: the same bytes are done); a rehearsal publishes nothing. A failure is exit 4."""
        if self.a.cmd == "rehearsal":
            return
        try:
            self.ops.publish_dossier(path, emails=self.emails)
        except Exception as exc:  # noqa: BLE001
            raise Stop(4, f"STOP: the pair dossier {Path(path).name} was NOT published ({type(exc).__name__}: {exc}); "
                          "a rerun of the same command retries") from None

    def republish_dossiers(self):
        """Resume: every recorded pair dossier not yet published is published now, idempotently (same bytes = done)."""
        for record in self.seq["pairs"]:
            if record.get("published") or self.a.cmd == "rehearsal":
                continue
            self.reverify_recorded_dossier(record)            # never publish a dossier the current receipts no longer back
            self.publish_dossier_or_stop(self.out / record["dossier"])
            record["published"] = True
            self.save()

    def reverify_recorded_dossier(self, record):
        """A recorded pair dossier is re-verified with `verify_dossier` against the CURRENT receipts / harvests of its two attempts
        (verdict recomputed, nothing trusted); a mismatch stops (rc 1). Returns the recomputed verdict."""
        attempts = dict(off=record["off"], on=record["on"])
        roots = {arm: self.out / attempts[arm] for arm in attempts}
        path = self.out / record["dossier"]
        try:
            off, on = fz.read_receipt(roots["off"]), fz.read_receipt(roots["on"])
        except fz.Refusal as exc:
            raise Stop(1, f"STOP: the pair dossier {path.name} cannot be re-verified: {exc} (the operator decides)") from None
        problems = pr.pair_problems(off, on)
        differences = pr.observed_differences(off, on) if not problems else [
            dict(process="-", field="pair_gate", off=None, on=p) for p in problems]
        verdict = "PASS" if not problems else "FAIL"
        harvests = {arm: Path(self.ops.harvest_path(attempts[arm])) / "HARVEST.json" for arm in attempts}
        self.verify_dossier(path, record["pair"], attempts, roots, harvests, differences, verdict)
        return verdict

    @staticmethod
    def verify_dossier(path, pair, attempts, roots, harvests, differences, verdict):
        """An existing dossier equals what the current records give (self-hash, pair, arms, receipt / harvest hashes, differences,
        verdict); the first mismatch stops the sequence (rc 1) naming the field."""
        def stop(field):
            raise Stop(1, f"STOP: the pair dossier {Path(path).name} does not match the leg records: {field} "
                          f"(never trusted; the operator decides)")

        def sha(p):
            try:
                return hashlib.sha256(Path(p).read_bytes()).hexdigest()
            except OSError:
                return None
        try:
            doc = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            stop("file (unreadable)")
        if not ph.sealed_ok(doc):
            stop("sha256 (missing or not the self-hash)")
        if doc.get("pair") != pair:
            stop("pair")
        arms = doc.get("arms") if isinstance(doc.get("arms"), dict) else {}
        for arm in ("off", "on"):
            got = arms.get(arm) if isinstance(arms.get(arm), dict) else {}
            for field, want in (("attempt", attempts[arm]), ("receipt_sha256", sha(roots[arm] / "receipt.json")),
                                ("harvest_sha256", sha(harvests[arm]))):
                if want is None or got.get(field) != want:
                    stop(f"arms.{arm}.{field}")
        if doc.get("differences") != differences:
            stop("differences")
        if doc.get("verdict") != verdict:
            stop("verdict")

    def ensure_amendment(self):
        """After legs 1-2: the pilot gate; all conditions pass -> the timeout amendment is written (once)."""
        path = self.record_dir / "amendment.json"
        off, on = (self.selected(n) for n in ("tg1-p426-off-pilot", "tg1-p426-on-pilot"))
        roots = [self.root(BY_NAME[n], e["attempt"]) for n, e in (("tg1-p426-off-pilot", off), ("tg1-p426-on-pilot", on))]
        if path.exists():
            self.verify_amendment(path, off, on, roots)
            return
        try:                                                  # the pilot gate runs inside `write_amendment`
            fz.write_amendment(self.record_dir / "v8_base.json", roots[0], roots[1], path, self.ops)
        except fz.Refusal as exc:
            raise Stop(1, f"STOP: pilot gate FAILED, the operator decides (no timeout amendment written): {exc}"[:1700]) from None
        self.load_records()
        self.log(f"pilot gate PASSED: the timeout amendment is written ({path.name})")

    def verify_existing_amendment(self):
        """Every command that consumes an existing amendment (`run`, `makeup`) re-verifies it against the selected pilots first."""
        path = self.record_dir / "amendment.json"
        if not path.exists():
            return
        off, on = (self.selected(n) for n in ("tg1-p426-off-pilot", "tg1-p426-on-pilot"))
        if off is None or on is None:
            raise Stop(1, f"STOP: the timeout amendment {path.name} exists but the pilots it was gated on are not recorded "
                          "in sequence.json (the operator decides)")
        roots = [self.root(BY_NAME[n], e["attempt"]) for n, e in (("tg1-p426-off-pilot", off), ("tg1-p426-on-pilot", on))]
        self.verify_amendment(path, off, on, roots)

    def verify_amendment(self, path, off, on, roots):
        """An existing amendment is re-verified, never trusted: its self-hash, its kind, the v8 base it links, and that the pilot
        dossier it was gated on is the selected pilots' PASS dossier (the sha256 it records)."""
        def stop(what):
            raise Stop(1, f"STOP: the timeout amendment {path.name} does not verify: {what} (the operator decides)")
        try:
            doc = p426_record.read_sealed(path)
            base = p426_record.read_sealed(self.record_dir / "v8_base.json")
        except p426_record.RecordError as exc:
            stop(str(exc))
        if doc.get("kind") != "p426_timeout_amendment":
            stop(f"kind {doc.get('kind')!r}")
        if doc.get("v8_base_sha256") != base["sha256"]:
            stop("v8_base_sha256 is not the v8 base's sha256")
        names = (f"tg1-p426-off-pilot.a{off['attempt']}", f"tg1-p426-on-pilot.a{on['attempt']}")
        pair = next((p for p in self.seq["pairs"] if p["pair"] == "pilot" and (p["off"], p["on"]) == names), None)
        if pair is None or pair.get("verdict") != "PASS":
            stop("the selected pilots have no PASS pilot dossier")
        if self.reverify_recorded_dossier(pair) != "PASS":    # freshly verified against the current receipts, not the stored verdict
            stop("the pilot dossier no longer verifies as a PASS against the current receipts")
        dossier = fz.pilot_dossier_path(*roots)
        try:
            sha = hashlib.sha256(dossier.read_bytes()).hexdigest()
        except OSError:
            stop(f"the pilot dossier {dossier.name} is missing")
        if doc.get("pilot_dossier_sha256") != sha:
            stop("pilot_dossier_sha256 is not the selected pilot dossier's sha256")

    def after_leg(self, spec, entry):
        """What follows a finished, harvested leg (also on resume): its state, its pair dossier, the pilot gate."""
        if entry["state"] not in VALID_STATES:
            if entry["state"] == spec["expect"]:
                self.log(f"{spec['name']}: {entry['state']} as the rehearsal expects")
                return
            raise Stop(1, f"STOP: {spec['name']}.a{entry['attempt']} is {entry['state']} (a rerun is an operator decision)")
        if spec["pair"] and spec["role"] == "second":
            self.ensure_dossier(spec)
        if spec["name"] == "tg1-p426-on-pilot":
            self.ensure_amendment()

    def process(self, spec):
        latest = (self.entries(spec["name"]) or [None])[-1]
        rerun = spec["name"] in (self.a.rerun or []) and not any(
            r["leg"] == spec["name"] and latest and r["attempt"] == latest["attempt"] for r in self.seq["reruns"])
        if latest and not rerun:
            if latest["state"] == "RUNNING":
                raise Stop(1, f"STOP: {spec['name']}.a{latest['attempt']} was RUNNING when the sequencer last stopped (the operator decides)")
            done = latest["state"] in VALID_STATES or latest["state"] == spec["expect"]
            if not done:
                raise Stop(1, f"STOP: {spec['name']}.a{latest['attempt']} is {latest['state']}; a rerun is an operator decision "
                              f"(--rerun {spec['name']} --rerun-reason TEXT)")
            if not self.harvested(latest):
                self.harvest(spec, latest)
            else:
                self.log(f"{spec['name']}.a{latest['attempt']}: {latest['state']}, harvested, skipped")
            return self.after_leg(spec, latest)
        if rerun and latest:
            self.seq["reruns"].append(dict(leg=spec["name"], attempt=latest["attempt"] + 1, reason=self.a.rerun_reason,
                                           at=co.utc_stamp(self.clock())))
        entry = self.run_leg(spec)
        self.after_leg(spec, entry)

    # -- the command
    def legs(self):
        if self.a.cmd == "rehearsal":
            return list(REHEARSAL_LEGS)
        if self.a.cmd == "makeup":
            return list(MAKEUP_LEGS)
        return list(RUN_LEGS)

    def run(self):
        self.load_records()
        if self.a.cmd == "makeup":
            self.canon = canonical_occurrences(read_occurrences(self.a.occurrences))
        if (self.out / OVERRUN_FILE).exists():
            raise Stop(1, f"STOP: {OVERRUN_FILE} exists: the operator removes it to resume")
        self.emails = tuple(self.ops.operator_emails())
        if not self.emails:                                  # spec 16.8: never "no operator address" (unset user.email, a failing read)
            raise fz.Refusal("the operator email set is empty (the main checkout's `git config user.email` is unset or unreadable): "
                             "the harvest cannot refuse the operator's address")
        if self.a.cmd in ("run", "makeup"):
            self.verify_existing_amendment()
        self.republish_dossiers()
        if self.a.cmd == "rehearsal":
            self.identity = self.rehearsal_identity()
        self.log(f"sequencer {self.a.cmd}: {len(self.legs())} legs, out-base {self.out}")
        for spec in self.legs():
            self.process(spec)
            if getattr(self.a, "through", None) and spec["name"] == self.a.through:
                self.publish_run_files_or_stop()
                self.log(f"through {spec['name']}: stopping as asked")
                return 0
        self.publish_run_files_or_stop()
        self.log("DONE: every leg of this command is complete")
        return 0

    def publish_run_files_or_stop(self):
        """The frozen records and `sequence.json` are published before the sequence reports success: a failure is exit code 4."""
        try:
            self.publish_run_files()
        except Exception as exc:  # noqa: BLE001
            self.run_files_done = True                       # not retried (and logged twice) by the exit path
            self.run_files_failed = True
            raise Stop(4, f"STOP: the run files were NOT published ({type(exc).__name__}: {exc}); a rerun of the same command retries") from None

    def rehearsal_identity(self):
        """The manifest's recorded probe identity (flat keys or an `identity` object); one that records none takes
        `ops.identity(off_worktree)` (spec 16.8); the date is the manifest's, checked against `--frozen-prompt-date`."""
        nested = self.base.get("identity") if isinstance(self.base.get("identity"), dict) else {}
        found = {k: self.base.get(k) or nested.get(k) for k in ("probe_code_sha256", "scaffold_policy_sha256")}
        if not all(found.values()):
            live = self.ops.identity(self.worktrees["off"])
            found = {k: live[k] for k in found}
        return dict(found, frozen_prompt_date=self.base["frozen_prompt_date"])

    def publish_run_files(self):
        if self.run_files_done or self.a.cmd == "rehearsal" or not self.seq["harvested"]:
            return
        paths = sorted(p for p in self.record_dir.iterdir() if p.is_file()) + [self.out / SEQUENCE_FILE]
        self.ops.publish_run_files(paths, emails=self.emails)
        self.run_files_done = True


def read_occurrences(path) -> list:
    try:
        lines = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    except (OSError, ValueError):
        raise fz.Refusal(f"--occurrences {Path(path).name} is missing, unreadable or not JSON lines") from None
    if not lines:
        raise fz.Refusal(f"--occurrences {Path(path).name} holds no occurrences")
    try:
        canonical_occurrences(lines)
    except (KeyError, ValueError, TypeError) as exc:
        raise fz.Refusal(f"--occurrences {Path(path).name}: {exc}") from None
    return lines


# ----------------------------------------------------------------------------------------------- the box's ops
class BoxSeqOps(fz.BoxOps):
    """The real `ops`: subprocess launch (nothing inherited: `pass_fds=()`, stdin closed, output to a file), start-time identity
    (`ChainOps.create_time`), `pmset` power, and the harvest / publication of `bench.p426_harvest` (s9)."""

    def __init__(self, workdir, *, main_root, evidence_stage, historical_walls=None, build_inputs=None):
        super().__init__(workdir, build_inputs, historical_walls)
        self.main_root, self.evidence_stage = Path(main_root), Path(evidence_stage)
        self._procs = {}

    def launch(self, argv, *, cwd, pass_fds):
        if "--out-root" in argv:
            out = Path(argv[argv.index("--out-root") + 1])
            log = out.parent / "logs" / (out.name + ".stdout")             # spec 16.8: never inside the fresh out-root
        else:
            log = Path(argv[argv.index("--out") + 1]).with_name("watcher.stdout")
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "ab") as f:
            proc = subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT,
                                    pass_fds=tuple(pass_fds), close_fds=True)
        self._procs[proc.pid] = proc
        return SimpleNamespace(pid=proc.pid, start=co.default_create_time(proc.pid), argv=list(argv))

    def alive(self, pid, start):
        proc = self._procs.get(pid)
        if proc is not None and proc.poll() is not None:
            return False
        try:
            return co.default_create_time(pid) == start
        except Exception:  # noqa: BLE001  (no such process)
            return False

    def wait(self, handle):
        proc = self._procs.get(handle.pid)
        return proc.wait() if proc is not None else 0

    def power(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "m1"))
        try:
            import bench_watch
        finally:
            sys.path.pop(0)
        return bench_watch.pmset_power()

    def operator_emails(self):
        """The main checkout's `git config user.email`; unset, empty or unreadable is a refusal, never an empty set (spec 16.8)."""
        try:
            run = subprocess.run(["git", "-C", str(self.main_root), "config", "user.email"], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            raise fz.Refusal("the operator email cannot be read: `git config user.email` failed in the main checkout") from None
        emails = tuple(x for x in run.stdout.split() if x) if run.returncode == 0 else ()
        if not emails:
            raise fz.Refusal("the operator email is unset or unreadable: `git config user.email` of the main checkout gave none")
        return emails

    def harvest_path(self, attempt):
        return self.main_root / "benchmark/results/p426/wave2" / attempt                  # the destination directory (spec 16.8)

    def harvest(self, root, *, emails):
        argv = [sys.executable, "-m", "bench.p426_harvest", "wave2", "--leg-root", str(root), "--main-root", str(self.main_root),
                "--evidence-stage", str(self.evidence_stage)]
        for e in emails:
            argv += ["--operator-email", e]
        run = subprocess.run(argv, cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True, timeout=3600,
                             stdin=subprocess.DEVNULL)
        path = self.harvest_path(Path(root).name) / "HARVEST.json"
        sha = hashlib.sha256(path.read_bytes()).hexdigest() if run.returncode == 0 and path.is_file() else None
        message = next((ln.strip() for ln in run.stderr.splitlines() if ln.startswith(("REFUSED:", "ERROR:"))), "")
        return dict(rc=run.returncode if sha or run.returncode else 1, harvest_json=str(path), harvest_sha256=sha, message=message)

    def _scrub(self, emails, secrets=None):
        from . import p426_harvest
        host = socket.gethostname()
        return p426_harvest, p426_harvest.Scrub(workdir=self.wd, repo=self.main_root, home=Path.home(), user=getpass.getuser(),
                                                hosts=tuple({host, host.split(".")[0]}), emails=tuple(emails),
                                                secrets=dict(secrets or {}))

    env_files = ()                                       # the arm worktrees' `.env` files (set by `main`), a credential source like the harvest's

    def _credentials(self):
        """The same in-memory credential values the leg harvest scans for (same sources); never logged."""
        from . import p426_harvest
        return p426_harvest.load_credentials(environ=os.environ, home=Path.home(), env_files=self.env_files)

    def publish_dossier(self, path, *, emails):
        mod, scrub = self._scrub(emails, secrets=self._credentials())
        return mod.publish_dossier(path, main_root=self.main_root, evidence_stage=self.evidence_stage, scrub=scrub)

    def publish_run_files(self, paths, *, emails):
        mod, scrub = self._scrub(emails, secrets=self._credentials())
        return mod.publish_run_files(paths, main_root=self.main_root, scrub=scrub)

    def notify(self, message):
        print(message, file=sys.stderr, flush=True)


# ----------------------------------------------------------------------------------------------- CLI
class RefusingParser(argparse.ArgumentParser):
    def error(self, message):
        raise fz.Refusal(message)


def parse_args(argv):
    ap = RefusingParser(prog="bench.p426_wave2", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "makeup", "rehearsal"):
        p = sub.add_parser(name)
        p.add_argument("--worktree-off", required=True)
        p.add_argument("--worktree-on", required=True)
        p.add_argument("--out-base", required=True)
        p.add_argument("--pause-file", default=None, help="default <out-base>/PAUSE")
        p.add_argument("--rerun", action="append", default=[], metavar="LEG", help="the operator's labelled rerun: a new attempt of LEG")
        p.add_argument("--rerun-reason", default=None)
        p.add_argument("--main-root", default=None, help="default ops: the checkout the harvest publishes into")
        p.add_argument("--evidence-stage", default=None, help="default ops: the evidence stage directory")
        p.add_argument("--historical-walls", default=None, metavar="JSON", help="default ops: the historical per-item walls")
        if name != "rehearsal":
            p.add_argument("--record-dir", required=True)
        if name == "run":
            p.add_argument("--through", default=None, metavar="LEG")
        if name == "makeup":
            p.add_argument("--occurrences", required=True)
        if name == "rehearsal":
            p.add_argument("--manifest", required=True)
            p.add_argument("--frozen-prompt-date", required=True, metavar="'Www Mmm DD YYYY'",
                           help="must be the date the rehearsal manifest recorded")
    return ap.parse_args(argv)


def check_args(a, wd):
    base = Path(a.out_base).resolve()
    rehearsal_dir = (Path(wd) / REHEARSAL_DIR).resolve()
    inside = base == rehearsal_dir or rehearsal_dir in base.parents
    if a.cmd == "rehearsal" and not inside:
        raise fz.Refusal(f"--out-base must lie under $STACK_WORKDIR/{REHEARSAL_DIR}/")
    if a.cmd != "rehearsal" and (inside or (Path(wd) / "p426").resolve() not in base.parents):
        raise fz.Refusal(f"--out-base must lie under $STACK_WORKDIR/p426/ and not in {REHEARSAL_DIR}/")
    names = [s["name"] for s in {"run": RUN_LEGS, "makeup": MAKEUP_LEGS, "rehearsal": REHEARSAL_LEGS}[a.cmd]]
    for flag in a.rerun:
        if flag not in names:
            raise fz.Refusal(f"--rerun {flag!r} is not a leg of this command ({', '.join(names)})")
    if a.rerun and not a.rerun_reason:
        raise fz.Refusal("--rerun needs --rerun-reason (a rerun is labelled)")
    if a.cmd == "run" and a.through is not None:
        by_number = {str(s["n"]): s["name"] for s in RUN_LEGS}
        if a.through not in names and a.through not in by_number:
            raise fz.Refusal(f"--through {a.through!r} is neither a leg name nor a number 1-8")
        a.through = by_number.get(a.through, a.through)


def frozen_env_files(a, wd):
    """The arm worktrees' `.env` files named by the FROZEN record (`v8_base.json` of `--record-dir`, or the rehearsal manifest) — the
    credential sources of the leg harvest — never the `--worktree-*` arguments. [] when the record cannot be read."""
    try:
        record = Path(a.manifest) if a.cmd == "rehearsal" else Path(a.record_dir) / "v8_base.json"
        doc = json.loads(record.read_text())
        out = []
        for arm in ("off", "on"):
            value = doc.get(f"{arm}_worktree")
            tree = fz.expand(value, wd) if value else None
            if tree:
                env = Path(tree) / ".env"
                if env.exists() or os.path.islink(env):
                    out.append(env)
        return out
    except (OSError, ValueError, AttributeError, TypeError):
        return []


def build_box_ops(a, wd):
    """The real ops of one command: the main checkout, the evidence stage and the credential sources of the frozen record."""
    scratch = Path(a.out_base) / "scratch"
    main_root = Path(a.main_root) if a.main_root else (scratch / "main" if a.cmd == "rehearsal" else Path(__file__).resolve().parents[2])
    ops = BoxSeqOps(wd, main_root=main_root, evidence_stage=a.evidence_stage or scratch / "evidence", historical_walls=a.historical_walls)
    ops.env_files = tuple(frozen_env_files(a, wd))
    return ops


def main(argv=None, *, ops=None, clock=None, sleep=None):
    clock, sleep = clock or time.time, sleep or time.sleep
    held = None
    try:
        a = parse_args(sys.argv[1:] if argv is None else argv)
        wd = getattr(ops, "wd", None) or os.environ.get("STACK_WORKDIR")
        if not wd:
            raise fz.Refusal("$STACK_WORKDIR is not set")
        check_args(a, wd)
        if ops is None:
            ops = build_box_ops(a, wd)
        fz.need(ops, *SEAMS, *(("historical_walls",) if a.cmd == "run" else ()))      # spec 16.8: a refusal, before the lock
        try:
            held = pl.acquire("sequencer", wd)
        except pl.LockRefused as exc:
            raise fz.Refusal(str(exc)) from None
        seq = Sequencer(a, ops, clock, sleep, wd)
        publish_failed = False
        try:
            rc = seq.run()
        except Stop as stop:
            seq.log(str(stop))                               # the original stop reason stays in the log
            rc = stop.rc
        except fz.Refusal:
            raise
        finally:
            try:
                seq.publish_run_files()
            except Exception as exc:  # noqa: BLE001
                publish_failed = True
                seq.log(f"run files NOT published: {type(exc).__name__}: {exc}")
        if publish_failed or seq.run_files_failed:           # an attempted run-file publication that failed is exit 4, whatever stopped
            rc = 4
        return rc
    except fz.Refusal as exc:
        print("REFUSED: " + " ".join(str(exc).split()), file=sys.stderr)
        return 2
    finally:
        if held is not None:
            held.release()


if __name__ == "__main__":
    sys.exit(main())
