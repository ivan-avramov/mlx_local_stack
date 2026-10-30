"""B2 slice s8, part 2 (spec docs/specs/p426-b2-tg1-wave2.md v3.2, sections 1, 5.1, 5.5, 6.4-6.7, 7, 8, 9, 10, 11.4, 16.5-16.7):
`bench.p426_wave2` - the Wave-2 sequencer. Hermetic: `ops` is a fake (it "launches" a chain by materializing its leg root and answering
`alive` for a scripted number of polls; no process, no router, no worker, no probe, no network), time is a fake clock, the locks are
real flocks under `tmp_path`. No registry is read."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import p426_freeze as fz
from bench import p426_hooks as ph
from bench import p426_locks as pl
from bench import p426_plan
from bench import p426_receipt as pr
from bench import p426_wave2 as w2
from bench.tests import b2_s8_support as S

BUILD = p426_plan.EXPECTED_BUILDS["s2"]
OFF_HEAD, ON_HEAD = "1" * 40, "2" * 40
DATE = "Tue Oct 27 2026"
T0 = 1_800_000_000.0
LEGS = ["tg1-p426-off-pilot", "tg1-p426-on-pilot", "tg1-p426-off-s1", "tg1-p426-on-s1", "tg1-p426-on-s2", "tg1-p426-off-s2",
        "tg1-p426-on-reload", "tg1-p426-off-reload"]
ITEMS = {"pilot": 5, "s1": 43, "s2": 43, "reload": 5}


def flocked(path):
    path = Path(path)
    if not path.exists():
        return False
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


class Clock:
    def __init__(self, t=T0):
        self.t, self.sleeps, self.hook = t, [], None

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s
        if self.hook:
            self.hook(self)


class SeqOps:
    """The sequencer's `ops` (spec 16.4 / 16.6) faked: `launch` materializes the leg root the chain would leave and the handle answers
    `alive` for `polls` polls; the watcher journal is written at its launch."""

    def __init__(self, wd, clock, off, on, scenario=None):
        self.wd, self.clock, self.scenario = Path(wd), clock, scenario or {}
        gl = {"src/mlx-vlm": BUILD["mlx_vlm"], "src/mlx-serve": BUILD["mlx_serve"]}
        self.state = {str(off): dict(head=OFF_HEAD, clean=True, gitlinks=dict(gl)), str(on): dict(head=ON_HEAD, clean=True, gitlinks=dict(gl))}
        self.ident = {k: v for k, v in zip(fz.IDENTITY_KEYS, ("d" * 64, "e" * 64, "f" * 64))}
        self.walls = dict(w_python_s=400.0, w_go_s=500.0, max_request_elapsed_s=60.0)
        self.events, self.launches, self.launch_times, self.life, self.next_pid = [], [], {}, {}, 1000
        self.watcher_argvs = []
        self.harvest_rc, self.pw = 0, dict(watts=140, volts=28, battery=90, on_battery_intervals=[])
        self.published_dossiers, self.published_run_files, self.notes, self.on_launch = [], [], [], None

    # -- freeze seams
    def worktree_state(self, path):
        return self.state[str(path)]

    def identity(self, path):
        return dict(self.ident)

    def historical_walls(self):
        return dict(self.walls)
    # -- sequencer seams
    def launch(self, argv, *, cwd, pass_fds):
        assert tuple(pass_fds) == (), "a spawned child holds no lock (spec 9): nothing is passed"
        self.next_pid += 1
        h = SimpleNamespace(pid=self.next_pid, start=float(self.next_pid), argv=list(argv))
        if any(str(a).endswith("bench_watch.py") for a in argv):
            self.launch_watcher(h, argv)
        else:
            self.launch_chain(h, argv)
        return h

    def launch_chain(self, h, argv):
        root = Path(argv[argv.index("--out-root") + 1])
        name = root.name.rsplit(".a", 1)[0]
        self.events.append(("launch", root.name))
        self.launches.append(dict(name=name, root=root, argv=h.argv))
        self.launch_times[root.name] = self.clock()
        if self.on_launch:
            self.on_launch(self, name, root)
        sc = dict(rc=0, polls=3, items=None, dnf=0)
        sc.update(self.scenario.get(name, {}))
        self.life[h.pid] = sc["polls"]
        h.rc, h.root, h.name = sc["rc"], root, name
        if sc.get("no_root"):
            return
        arm = "on" if argv[argv.index("--predictor") + 1] == "mtp" else "off"
        kind = next((k for k in ("pilot", "s1", "s2", "reload") if name.endswith("-" + k)), None)
        items = sc.get("items") or (ITEMS[kind] - sc["dnf"] if kind else 3)
        S.write_leg_root(root, arm=arm, leg=name, items=items, dnf=sc["dnf"], rc=sc["rc"], status=sc.get("status", "finished"),
                         invalid=sc.get("invalid"), engagement_ok=sc.get("engagement_ok", True), verdict=sc.get("verdict", "reconciled"),
                         with_leg=False, receipt_doc=S.receipt(arm, env_extra=sc.get("env_extra")), kill=sc.get("kill", False),
                         session=sc.get("session", "s1"), slots=sc.get("slots"), planned=sc.get("planned"))

    def launch_watcher(self, h, argv):
        self.watcher_argvs.append(list(argv))
        root =Path(argv[argv.index("--out") + 1]).parent
        name = root.name.rsplit(".a", 1)[0]
        sc = self.scenario.get(name, {})
        self.events.append(("watcher", root.name))
        chain_pid = int(argv[argv.index("--driver-pid") + 1])
        self.life[h.pid] = sc.get("watcher_polls", self.life.get(chain_pid, 3) + 2)
        ok = sc.get("speed_valid", True)
        lines = [dict(tick=i, t=T0 + 300 * i, interval_s=300.0, watts=140 if ok else 100, volts=28, battery=90, power_ok=ok,
                      driver_alive=True) for i in range(2)]
        lines.append(dict(exit_state="driver_exited", t=T0 + 600, interval_s=300.0, ticks=2, battery_intervals=[]))
        (root / "watch.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))

    def alive(self, pid, start):
        left = self.life.get(pid, 0)
        if left > 0:
            self.life[pid] = left - 1
            return True
        return False

    def wait(self, h):
        return getattr(h, "rc", 0)

    def power(self):
        return dict(self.pw)

    def operator_emails(self):
        return ["operator@example.invalid"]

    def harvest_path(self, attempt):
        return self.wd / "harvest" / attempt                      # spec 16.8: the attempt's destination DIRECTORY

    def harvest(self, root, *, emails):
        self.events.append(("harvest", Path(root).name))
        path = self.harvest_path(Path(root).name) / "HARVEST.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(leg=Path(root).name)))
        return dict(rc=self.harvest_rc, harvest_json=str(path), harvest_sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    def publish_dossier(self, path, *, emails):
        self.events.append(("dossier", Path(path).name))
        self.published_dossiers.append(Path(path))
        return dict(published=[], harvest_sha256="0" * 64)

    def publish_run_files(self, paths, *, emails):
        self.events.append(("run_files", [Path(p).name for p in paths]))
        self.published_run_files.append([Path(p) for p in paths])
        return dict(published=[], harvest_sha256="0" * 64)

    def notify(self, message):
        self.notes.append(message)

    def names(self, kind="launch"):
        return [n.rsplit(".a", 1)[0] for k, n in self.events if k == kind]


@pytest.fixture
def world(tmp_path, monkeypatch):
    wd = tmp_path / "wd"
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    off, on = wd / "p426" / "stack-p426-off", wd / "p426" / "stack-p426-on"
    off.mkdir(parents=True)
    on.mkdir(parents=True)
    rec = wd / "p426" / "record"
    base = dict(kind="p426_v8_base", build="s2", off_commit=OFF_HEAD, on_commit=ON_HEAD, off_worktree="$STACK_WORKDIR/p426/stack-p426-off",
                on_worktree="$STACK_WORKDIR/p426/stack-p426-on", gitlinks={"mlx_vlm": BUILD["mlx_vlm"], "mlx_serve": BUILD["mlx_serve"]},
                production_ref=BUILD["production_ref"], probe_code_sha256="d" * 64, scaffold_policy_sha256="e" * 64,
                generation_identity_sha256="f" * 64, pins_sha256="a" * 64, grader_image_id="sha256:" + "b" * 64, frozen_prompt_date=DATE,
                pilot_deadline_s=100000.0, settle_bound_s=900.0, generic_pred_s=250, volatile_env_keys=list(fz.VOLATILE_ENV_KEYS),
                r1_env_difference=[], rehearsal_manifest_sha256="c" * 64, stack_suite_receipt_sha256="c" * 64, created="t")
    ph.write_exclusive(rec / "v8_base.json", base)
    clock = Clock()
    return SimpleNamespace(wd=wd, off=off, on=on, rec=rec, out=wd / "p426" / "wave2", clock=clock, ops=SeqOps(wd, clock, off, on),
                           seq=wd / "p426" / "wave2" / "sequence.json", base=base)


def argv_for(w, cmd="run", *extra):
    return [cmd, "--record-dir", str(w.rec), "--worktree-off", str(w.off), "--worktree-on", str(w.on), "--out-base", str(w.out), *extra]


def go(w, *extra, cmd="run"):
    return w2.main(argv_for(w, cmd, *extra), ops=w.ops, clock=w.clock, sleep=w.clock.sleep)


def seq(w):
    return json.loads(w.seq.read_text())


def leg_doc(w, attempt):
    return json.loads((w.out / attempt / "leg.json").read_text())


# ----------------------------------------------------------------------------------------------- leg_argv
WT = {"off": Path("/wt/off"), "on": Path("/wt/on")}


def write_records(tmp_path, *, amendment=True):
    base = dict(kind="p426_v8_base", off_commit=OFF_HEAD, on_commit=ON_HEAD, probe_code_sha256="d" * 64, scaffold_policy_sha256="e" * 64,
                frozen_prompt_date=DATE, settle_bound_s=900.0)
    b = ph.write_exclusive(tmp_path / "rec" / "v8_base.json", base)
    out = dict(v8=tmp_path / "rec" / "v8_base.json")
    if amendment:
        ph.write_exclusive(tmp_path / "rec" / "amendment.json", dict(kind="p426_timeout_amendment", v8_base_sha256=b["sha256"], w_python_s=1.0,
                                                                     w_go_s=1.0, leg_deadline_s={}, settle_bound_s=900.0))
        out["amendment"] = tmp_path / "rec" / "amendment.json"
    return out


EXPECTED_MODES = {
    "tg1-p426-off-pilot": ("off", ["pilot"], "v8"), "tg1-p426-on-pilot": ("on", ["pilot"], "v8"),
    "tg1-p426-off-s1": ("off", ["chain", "s1"], "amendment"), "tg1-p426-on-s1": ("on", ["chain", "s1"], "amendment"),
    "tg1-p426-on-s2": ("on", ["chain", "s2"], "amendment"), "tg1-p426-off-s2": ("off", ["chain", "s2"], "amendment"),
    "tg1-p426-on-reload": ("on", ["chain", "reload"], "amendment"), "tg1-p426-off-reload": ("off", ["chain", "reload"], "amendment"),
}


@pytest.mark.parametrize("leg", LEGS)
def test_leg_argv_is_the_p426_chain_invocation_of_the_arm(tmp_path, leg):
    arm, head, rec = EXPECTED_MODES[leg]
    records = write_records(tmp_path)
    argv = w2.leg_argv(leg, 1, worktrees=WT, record_path=records[rec], out_base=tmp_path / "out")
    wt = WT[arm]
    commit = OFF_HEAD if arm == "off" else ON_HEAD
    assert argv == [str(wt / ".venv-bench/bin/python"), str(wt / "benchmark/chains/c147/run_tg1_chain.py"), *head, "--p426",
                    "--models", S.MODEL, "--predictor", "mtp" if arm == "on" else "off", "--out-root", str(tmp_path / "out" / f"{leg}.a1"),
                    "--probe-code-sha", "d" * 64, "--policy-sha", "e" * 64, "--frozen-prompt-date", DATE, "--campaign-core", commit,
                    "--frozen-record", str(records[rec])]


def test_leg_argv_attempt_and_pair_receipt_and_forbidden_flags(tmp_path):
    records = write_records(tmp_path)
    a = w2.leg_argv("tg1-p426-on-s1", 3, worktrees=WT, record_path=records["amendment"], out_base=tmp_path / "o",
                    pair_receipt=tmp_path / "first" / "receipt.json")
    assert a[a.index("--out-root") + 1] == str(tmp_path / "o" / "tg1-p426-on-s1.a3")
    assert a[a.index("--pair-receipt") + 1] == str(tmp_path / "first" / "receipt.json")
    plain = w2.leg_argv("tg1-p426-on-s1", 1, worktrees=WT, record_path=records["amendment"], out_base=tmp_path / "o")
    assert "--pair-receipt" not in plain
    for flag in ("--smoke", "--pred-s", "--generation-sha", "--frozen-date-from", "--rehearsal", "--inject", "--occurrences"):
        assert flag not in a
    with pytest.raises(ValueError):
        w2.leg_argv("tg1-p426-nope", 1, worktrees=WT, record_path=records["amendment"], out_base=tmp_path)
    with pytest.raises(ValueError):
        w2.leg_argv("tg1-p426-on-s1", 0, worktrees=WT, record_path=records["amendment"], out_base=tmp_path)


def test_makeup_leg_argv_names_its_occurrences_file_and_namespace(tmp_path):
    records = write_records(tmp_path)
    occ = tmp_path / "o" / "makeup" / "occurrences.off.jsonl"
    a = w2.leg_argv("tg1-p426-off-makeup", 1, worktrees=WT, record_path=records["amendment"], out_base=tmp_path / "o", occurrences=occ)
    assert a[2] == "makeup" and a[a.index("--occurrences") + 1] == str(occ)
    assert a[a.index("--out-root") + 1] == str(tmp_path / "o" / "tg1-p426-off-makeup.a1")           # §16.8: flat like every attempt
    assert a[a.index("--predictor") + 1] == "off"
    with pytest.raises(ValueError):
        w2.leg_argv("tg1-p426-off-makeup", 1, worktrees=WT, record_path=records["amendment"], out_base=tmp_path / "o")


@pytest.mark.parametrize("leg,arm,tail", [
    ("tg1-p426-rehearsal-off", "off", ["--rehearsal"]), ("tg1-p426-rehearsal-on", "on", ["--rehearsal"]),
    ("tg1-p426-rehearsal-mismatch", "on", ["--rehearsal", "--inject", "reconcile-mismatch"]),
    ("tg1-p426-rehearsal-kill", "off", ["--rehearsal", "--inject", "stall-kill"])])
def test_rehearsal_leg_argv(tmp_path, leg, arm, tail):
    manifest = ph.write_exclusive(tmp_path / "m.json", dict(kind="p426_rehearsal", off_commit=OFF_HEAD, on_commit=ON_HEAD, rehearsal=True))
    ident = dict(probe_code_sha256="d" * 64, scaffold_policy_sha256="e" * 64, frozen_prompt_date=DATE)
    a = w2.leg_argv(leg, 1, worktrees=WT, record_path=tmp_path / "m.json", out_base=tmp_path / "rehearsal", identity=ident)
    assert a[2:4] == ["chain", "s1"] and a[a.index("--predictor") + 1] == ("mtp" if arm == "on" else "off")
    assert a[a.index("--frozen-record") + 1] == str(tmp_path / "m.json") and a[-len(tail):] == tail
    assert a[a.index("--campaign-core") + 1] == (ON_HEAD if arm == "on" else OFF_HEAD)
    assert manifest["sha256"]
    with pytest.raises(ValueError):
        w2.leg_argv(leg, 1, worktrees=WT, record_path=tmp_path / "m.json", out_base=tmp_path)           # no identity for a manifest


# ----------------------------------------------------------------------------------------------- deadlines and make-up groups
def test_deadline_s_is_one_and_a_half_times_the_items_walls_plus_1800():
    am = dict(kind="p426_timeout_amendment", w_python_s=700.0, w_go_s=500.0, leg_deadline_s={"s1": 1.5 * (22 * 700 + 21 * 500) + 1800})
    assert w2.deadline_s("s1", {"python": 22, "go": 21}, am) == 1.5 * (22 * 700 + 21 * 500) + 1800 == am["leg_deadline_s"]["s1"]
    assert w2.deadline_s("s2", {"go": 21, "python": 22}, am) == am["leg_deadline_s"]["s1"]                 # one value for both arms of a session
    assert w2.deadline_s("reload", {"python": 5}, am) == 1.5 * 5 * 700 + 1800
    assert w2.deadline_s("makeup", {"python": 3, "go": 2}, am) == 1.5 * (3 * 700 + 2 * 500) + 1800
    with pytest.raises(ValueError):
        w2.deadline_s("s1", {"rust": 1}, am)
    with pytest.raises(ValueError):
        w2.deadline_s("s9", {"python": 1}, am)


def occ(session, lang, item, n, arm="off", seed=None):
    return dict(session=session, language=lang, item=item, seed=seed or {"s1": 1001, "s2": 2002}[session], arm_of_dnf=arm, occurrence=n)


def test_makeup_groups_are_session_seed_language_groups_in_s1_then_s2_and_original_order():
    occs = [occ("s2", "go", "gB", 1), occ("s2", "python", "p1", 2, "on"), occ("s1", "go", "g1", 0), occ("s1", "python", "p2", 1),
            occ("s2", "go", "gA", 0, "on"), occ("s1", "python", "p1", 0), occ("s1", "python", "p1", 0, "on")]      # p1 twice: both arms DNF'd it
    groups = w2.makeup_groups(occs)
    assert groups == [dict(session="s1", seed=1001, language="python", items=["p1", "p2"]),
                      dict(session="s1", seed=1001, language="go", items=["g1"]),
                      dict(session="s2", seed=2002, language="go", items=["gA", "gB"]),
                      dict(session="s2", seed=2002, language="python", items=["p1"])]        # p1 again, under s2's own seed
    assert w2.makeup_groups(list(reversed(occs))) == groups                                  # an unordered set, canonicalized
    assert w2.makeup_groups([]) == []


def test_canonical_occurrences_merge_the_arms_of_one_slot():
    canon = w2.canonical_occurrences([occ("s1", "python", "p1", 0, "off"), occ("s1", "python", "p1", 0, "on"), occ("s2", "python", "p1", 0)])
    assert [(c["session"], c["item"], c["seed"], c["arm_of_dnf"]) for c in canon] == [("s1", "p1", 1001, ["off", "on"]),
                                                                                    ("s2", "p1", 2002, ["off"])]


# ----------------------------------------------------------------------------------------------- classification
def root_of(tmp_path, name="tg1-p426-off-s1.a1", **kw):
    return S.write_leg_root(tmp_path / name, with_leg=False, **dict(dict(arm="off", leg=name.rsplit(".a", 1)[0]), **kw))


def test_classify_valid_and_valid_with_dnf(tmp_path):
    assert w2.classify_leg(root_of(tmp_path), 0, arm="off")["state"] == "VALID"
    got = w2.classify_leg(root_of(tmp_path, "b.a1", items=4, dnf=1), 0, arm="off")
    assert got["state"] == "VALID_WITH_DNF" and got["class"] == "dnf"
    got = w2.classify_leg(root_of(tmp_path, "c.a1", items=2, dnf=3), 0, arm="off")          # more than 2 DNF: systemic
    assert got["state"] == "INVALID" and got["class"] == "systemic" and "DNF" in got["reason"]


@pytest.mark.parametrize("kw,rc,needle", [
    (dict(status="crashed"), 1, "rc 1"), (dict(status="finished"), 2, "rc 2"),
    (dict(invalid=[dict(stage="done", slot="s", reason="reconciliation mismatch", at="t")], status="invalidated"), 2, "reconciliation mismatch"),
    (dict(verdict="invalid"), 0, "reconciled"), (dict(engagement_ok=False, arm="on"), 0, "request"),
    (dict(items=4, planned=5), 0, "ledger"),
])
def test_classify_systemic_causes(tmp_path, kw, rc, needle):
    arm = kw.pop("arm", "off")
    got = w2.classify_leg(root_of(tmp_path, arm=arm, **kw), rc, arm=arm)
    assert got["state"] == "INVALID" and got["class"] == "systemic" and needle in got["reason"]


def test_classify_reads_the_planned_slots_from_the_frozen_schedule_never_a_constant(tmp_path):
    """P63: the plan is the leg's own frozen schedule (`schedule.json`, its sha256 in `chain.json`)."""
    assert w2.classify_leg(root_of(tmp_path, "a.a1", items=7), 0, arm="off")["state"] == "VALID"                 # 7 / 7, not a constant 5 / 43
    got = w2.classify_leg(root_of(tmp_path, "b.a1", items=4, planned=6), 0, arm="off")
    assert got["state"] == "INVALID" and "4" in got["reason"] and "6" in got["reason"]
    got = w2.classify_leg(root_of(tmp_path, "c.a1", items=5, schedule_sha="0" * 64), 0, arm="off")
    assert got["state"] == "INVALID" and "schedule" in got["reason"]
    got = w2.classify_leg(root_of(tmp_path, "d.a1", items=5, schedule=False), 0, arm="off")
    assert got["state"] == "INVALID" and "schedule" in got["reason"]


def test_classify_a_missing_chain_json_is_not_started_after_an_entry_refusal(tmp_path):
    (tmp_path / "x.a1").mkdir()
    assert w2.classify_leg(tmp_path / "x.a1", 2, arm="off")["state"] == "NOT_STARTED"
    assert w2.classify_leg(tmp_path / "nowhere.a1", 2, arm="off")["state"] == "NOT_STARTED"
    assert w2.classify_leg(tmp_path / "x.a1", 1, arm="off")["state"] == "INVALID"


# ----------------------------------------------------------------------------------------------- the pilot gate
def gate_roots(tmp_path, off=None, on=None, **both):
    kw = dict(klass="valid")
    a = S.write_leg_root(tmp_path / "tg1-p426-off-pilot.a1", arm="off", leg="tg1-p426-off-pilot", **{**kw, **both, **(off or {})})
    b = S.write_leg_root(tmp_path / "tg1-p426-on-pilot.a1", arm="on", leg="tg1-p426-on-pilot", **{**kw, **both, **(on or {})})
    return a, b


def test_pilot_gate_passes_when_every_condition_holds(tmp_path):
    assert w2.pilot_gate(*gate_roots(tmp_path)) == []


@pytest.mark.parametrize("off,on,needle", [
    (dict(state="INVALID", klass="systemic"), None, "VALID"), (None, dict(state="INVALID", klass="systemic"), "VALID"),
    (dict(state="VALID_WITH_DNF", items=4, dnf=1), None, "DNF"), (None, dict(state="VALID_WITH_DNF", items=4, dnf=1), "DNF"),
    (dict(items=4), None, "5"), (None, dict(verdict="invalid"), "reconciled"), (None, dict(engagement_ok=False), "request"),
    (dict(speed_valid=False), None, "speed"), (None, dict(speed_valid=False), "speed")])
def test_pilot_gate_each_failing_condition_is_named(tmp_path, off, on, needle):
    got = w2.pilot_gate(*gate_roots(tmp_path, off=off, on=on))
    assert got and any(needle in g for g in got)


def test_pilot_gate_needs_the_five_item_pilot_schedule(tmp_path):
    got = w2.pilot_gate(*gate_roots(tmp_path, off=dict(items=6)))
    assert any("6" in g and "5" in g for g in got)


def test_pilot_gate_fails_on_a_pair_gate_mismatch(tmp_path):
    got = w2.pilot_gate(*gate_roots(tmp_path, on=dict(receipt_doc=S.receipt("on", env_extra={"MLX_X": "1"}))))
    assert any("pair gate" in g for g in got)


# ----------------------------------------------------------------------------------------------- the sequence
def test_full_sequence_runs_legs_1_to_8_in_order_and_stops(world):
    assert go(world) == 0
    assert world.ops.names() == LEGS
    assert world.ops.names("harvest") == LEGS                                       # every leg is harvested right after it ends
    assert [(l["leg"], l["attempt"], l["state"]) for l in seq(world)["legs"]] == [(n, 1, "VALID") for n in LEGS]
    assert not (world.out / "tg1-p426-off-makeup.a1").exists() and not list(world.out.glob("*makeup*"))     # the sequencer stops after leg 8
    assert (world.rec / "amendment.json").is_file()


def test_argv_of_every_launched_chain_pins_the_record_and_pair_receipts(world):
    go(world)
    by = {l["name"]: l["argv"] for l in world.ops.launches}
    for name, argv in by.items():
        arm, head, rec = EXPECTED_MODES[name]
        assert argv[2:2 + len(head)] == head and argv[argv.index("--frozen-record") + 1] == str(world.rec / {"v8": "v8_base.json", "amendment": "amendment.json"}[rec])
        assert argv[argv.index("--out-root") + 1] == str(world.out / f"{name}.a1")
    firsts = {"tg1-p426-on-pilot": "tg1-p426-off-pilot", "tg1-p426-on-s1": "tg1-p426-off-s1", "tg1-p426-off-s2": "tg1-p426-on-s2",
              "tg1-p426-off-reload": "tg1-p426-on-reload"}
    for second, first in firsts.items():
        assert by[second][by[second].index("--pair-receipt") + 1] == str(world.out / f"{first}.a1" / "receipt.json")
    for first in ("tg1-p426-off-pilot", "tg1-p426-off-s1", "tg1-p426-on-s2", "tg1-p426-on-reload"):
        assert "--pair-receipt" not in by[first]


def test_events_order_harvest_before_next_launch_dossier_after_second_harvest(world):
    go(world)
    ev = world.ops.events
    def at(kind, name):
        return next(i for i, e in enumerate(ev) if e == (kind, name))
    assert at("harvest", "tg1-p426-off-pilot.a1") < at("launch", "tg1-p426-on-pilot.a1")
    assert at("harvest", "tg1-p426-on-pilot.a1") < at("dossier", "pilot__off-a1__on-a1.json")
    assert at("dossier", "pilot__off-a1__on-a1.json") < at("launch", "tg1-p426-off-s1.a1")                   # the gate follows the pair
    assert [e[1] for e in ev if e[0] == "dossier"] == ["pilot__off-a1__on-a1.json", "s1__off-a1__on-a1.json", "s2__off-a1__on-a1.json",
                                                      "reload__off-a1__on-a1.json"]


def test_pair_dossiers_are_written_per_pair_attempt_and_keyed_by_arm(world):
    go(world)
    d = json.loads((world.out / "pairs" / "s2__off-a1__on-a1.json").read_text())
    assert ph.sealed_ok(d) and d["pair"] == "s2" and d["verdict"] == "PASS"
    assert d["arms"]["off"]["attempt"] == "tg1-p426-off-s2.a1" and d["arms"]["on"]["attempt"] == "tg1-p426-on-s2.a1"
    assert d["arms"]["on"]["receipt_sha256"] == hashlib.sha256((world.out / "tg1-p426-on-s2.a1" / "receipt.json").read_bytes()).hexdigest()
    assert d["arms"]["off"]["harvest_sha256"] == hashlib.sha256((world.ops.harvest_path("tg1-p426-off-s2.a1") / "HARVEST.json").read_bytes()).hexdigest()
    assert {e["field"] for e in d["differences"]} == {"argv.worker", "snapshots.drafter"}
    assert [p.name for p in world.ops.published_dossiers] == [f"{p}__off-a1__on-a1.json" for p in ("pilot", "s1", "s2", "reload")]
    assert [p["pair"] for p in seq(world)["pairs"]] == ["pilot", "s1", "s2", "reload"]
    assert seq(world)["pairs"][2]["dossier"] == "pairs/s2__off-a1__on-a1.json"


def test_run_files_are_published_at_the_end(world):
    go(world)
    names = [[p.name for p in paths] for paths in world.ops.published_run_files][-1]
    assert "sequence.json" in names and "v8_base.json" in names and "amendment.json" in names


def test_the_pilot_gate_writes_the_amendment_from_both_pilots(world):
    world.ops.scenario["tg1-p426-on-pilot"] = {}
    go(world, "--through", "tg1-p426-on-pilot")
    assert (world.rec / "amendment.json").is_file()
    am = json.loads((world.rec / "amendment.json").read_text())
    assert ph.sealed_ok(am) and am["kind"] == "p426_timeout_amendment"
    assert am["v8_base_sha256"] == json.loads((world.rec / "v8_base.json").read_text())["sha256"]
    assert am["w_python_s"] == max(400.0, 104.0)                                                  # the S fixture's walls are 100..104


@pytest.mark.parametrize("scenario,needle", [
    (dict(dnf=1), "DNF"), (dict(speed_valid=False), "speed"), (dict(env_extra={"MLX_X": "1"}), "pair gate")])
def test_a_failing_gate_condition_stops_for_the_operator_without_the_amendment(world, capsys, scenario, needle):
    world.ops.scenario["tg1-p426-on-pilot"] = scenario
    assert go(world) == 1
    assert not (world.rec / "amendment.json").exists()
    assert world.ops.names() == LEGS[:2]
    assert needle in (world.out / "sequence.log").read_text()


def test_a_pair_gate_mismatch_writes_a_failed_dossier_and_stops(world):
    world.ops.scenario["tg1-p426-on-pilot"] = dict(env_extra={"MLX_X": "1"})
    assert go(world) == 1
    d = json.loads((world.out / "pairs" / "pilot__off-a1__on-a1.json").read_text())
    assert d["verdict"] == "FAIL" and any(e["field"] == "pair_gate" for e in d["differences"])


def test_amendment_is_written_only_once_and_reused_on_resume(world):
    go(world, "--through", "tg1-p426-on-pilot")
    first = (world.rec / "amendment.json").read_bytes()
    assert go(world) == 0
    assert (world.rec / "amendment.json").read_bytes() == first


# -- failure classes
def test_a_systemic_failure_stops_the_sequence_and_is_still_harvested(world):
    world.ops.scenario["tg1-p426-off-s1"] = dict(rc=2, status="invalidated", invalid=[dict(stage="done", slot="s", reason="engagement", at="t")])
    assert go(world) == 1
    assert world.ops.names() == LEGS[:3]
    assert world.ops.names("harvest") == LEGS[:3]
    d = leg_doc(world, "tg1-p426-off-s1.a1")
    assert d["state"] == "INVALID" and d["class"] == "systemic" and "engagement" in d["reason"] and d["chain_rc"] == 2
    assert seq(world)["legs"][-1] == dict(leg="tg1-p426-off-s1", attempt=1, state="INVALID")


def test_a_valid_with_dnf_session_leg_continues(world):
    world.ops.scenario["tg1-p426-off-s1"] = dict(dnf=2)
    assert go(world) == 0
    assert leg_doc(world, "tg1-p426-off-s1.a1")["state"] == "VALID_WITH_DNF"
    assert world.ops.names() == LEGS


def test_a_leg_the_chain_refused_before_the_router_is_not_started(world):
    world.ops.scenario["tg1-p426-off-pilot"] = dict(rc=2, no_root=True)
    assert go(world) == 1
    d = leg_doc(world, "tg1-p426-off-pilot.a1")
    assert d["state"] == "NOT_STARTED" and ph.sealed_ok(d)
    assert world.ops.names() == LEGS[:1] and world.ops.names("harvest") == LEGS[:1]


def test_leg_record_fields_and_speed_block(world):
    world.ops.scenario["tg1-p426-on-pilot"] = dict(speed_valid=False)
    go(world)
    d = leg_doc(world, "tg1-p426-off-pilot.a1")
    for k in ("leg", "attempt", "state", "class", "reason", "chain_rc", "started", "ended", "speed_valid", "speed_reason"):
        assert k in d
    assert d["speed_valid"] is True and d["leg"] == "tg1-p426-off-pilot" and d["attempt"] == 1 and ph.sealed_ok(d)
    assert leg_doc(world, "tg1-p426-on-pilot.a1")["speed_valid"] is False


def test_a_dead_watcher_marks_the_leg_speed_invalid_and_never_the_quality(world):
    world.ops.scenario["tg1-p426-off-pilot"] = dict(watcher_polls=1, polls=6)
    assert go(world, "--through", "tg1-p426-off-pilot") == 0
    d = leg_doc(world, "tg1-p426-off-pilot.a1")
    assert d["state"] == "VALID" and d["speed_valid"] is False and "watcher" in d["speed_reason"]


def test_the_watcher_is_launched_for_the_chain_with_its_pid_and_journal(world):
    go(world, "--through", "tg1-p426-off-pilot")
    w = next(e for e in world.ops.events if e[0] == "watcher")
    assert w == ("watcher", "tg1-p426-off-pilot.a1")
    assert "--planned" not in world.ops.watcher_argvs[0]                            # P63: no constant plan is handed to the watcher
    assert "--chain-json" in world.ops.watcher_argvs[0] and "--driver-pid" in world.ops.watcher_argvs[0]


def test_a_session_leg_with_a_different_frozen_plan_is_valid_when_its_ledger_matches(world):
    """P63: 45 frozen slots in s1 (not the constant 43) -> VALID; a ledger that falls short of its own schedule -> INVALID."""
    world.ops.scenario["tg1-p426-off-s1"] = dict(items=45)
    assert go(world, "--through", "tg1-p426-off-s1") == 0
    assert leg_doc(world, "tg1-p426-off-s1.a1")["state"] == "VALID"


def test_a_ledger_short_of_the_frozen_schedule_is_invalid(world):
    world.ops.scenario["tg1-p426-off-s1"] = dict(items=40, planned=43)
    assert go(world) == 1
    d = leg_doc(world, "tg1-p426-off-s1.a1")
    assert d["state"] == "INVALID" and "ledger" in d["reason"]


@pytest.mark.parametrize("seam", ["launch", "alive", "wait", "power", "harvest", "harvest_path", "publish_dossier", "publish_run_files",
                                  "operator_emails", "worktree_state", "identity", "historical_walls"])
def test_a_missing_ops_seam_is_a_refusal_never_a_traceback(world, capsys, seam):
    """P59 / §16.8: every seam the sequencer calls; checked before the lock is taken and before anything is launched."""
    ops = Without(world.ops, seam)
    rc = w2.main(argv_for(world), ops=ops, clock=world.clock, sleep=world.clock.sleep)
    err = capsys.readouterr().err
    assert rc == 2 and err.startswith("REFUSED:") and seam in err and err.count("\n") == 1
    assert world.ops.launches == [] and not flocked(world.wd / pl.SEQUENCER)


class Without:
    """`ops` with one seam missing."""

    def __init__(self, ops, name):
        self._ops, self._name = ops, name

    def __getattr__(self, attr):
        if attr == self._name:
            raise AttributeError(attr)
        return getattr(self._ops, attr)


# -- deadlines, overrun
def test_overrun_pauses_without_killing_and_holds_the_locks(world):
    ph_base = json.loads((world.rec / "v8_base.json").read_text())
    (world.rec / "v8_base.json").unlink()
    ph.write_exclusive(world.rec / "v8_base.json", dict({k: v for k, v in ph_base.items() if k != "sha256"}, pilot_deadline_s=100.0))
    world.ops.scenario["tg1-p426-off-pilot"] = dict(polls=10)               # 10 polls x 30 s > T = 100 s
    held = []
    orig = world.ops.alive

    def alive(pid, start):
        if (world.out / "OVERRUN_PAUSED").exists():
            held.append((flocked(world.wd / pl.SEQUENCER), flocked(world.wd / pl.LEG)))
        return orig(pid, start)
    world.ops.alive = alive
    assert go(world) == 3
    doc = json.loads((world.out / "OVERRUN_PAUSED").read_text())
    assert doc["leg"] == "tg1-p426-off-pilot" and doc["attempt"] == 1 and doc["deadline_s"] == 100.0 and doc["at"]
    assert held and all(h == (True, False) for h in held)                  # SEQUENCER.lock kept, LEG.lock never taken by the sequencer
    assert world.ops.notes and "OVERRUN" in world.ops.notes[0]
    assert not hasattr(world.ops, "kill") and world.ops.names() == LEGS[:1]
    assert leg_doc(world, "tg1-p426-off-pilot.a1")["overrun"] is True
    assert world.ops.names("harvest") == LEGS[:1]                          # when the chain exits it is classified and harvested
    assert go(world) == 1 and "OVERRUN_PAUSED" in (world.out / "sequence.log").read_text()      # an unremoved pause refuses a restart


def test_a_leg_that_finishes_before_its_deadline_has_no_overrun(world):
    go(world, "--through", "tg1-p426-off-pilot")
    assert not (world.out / "OVERRUN_PAUSED").exists() and leg_doc(world, "tg1-p426-off-pilot.a1")["overrun"] is False


def test_session_legs_use_the_amendments_deadline_and_both_arms_share_it(world):
    seen = []
    world.ops.on_launch = lambda ops, name, root: seen.append(name)
    go(world)
    am = json.loads((world.rec / "amendment.json").read_text())
    assert w2.deadline_s("s1", {"python": 22, "go": 21}, am) == am["leg_deadline_s"]["s1"]
    assert w2.leg_deadline(am, json.loads((world.rec / "v8_base.json").read_text()), "tg1-p426-on-s1") == am["leg_deadline_s"]["s1"] \
        == w2.leg_deadline(am, json.loads((world.rec / "v8_base.json").read_text()), "tg1-p426-off-s1")
    assert w2.leg_deadline(None, json.loads((world.rec / "v8_base.json").read_text()), "tg1-p426-on-pilot") == 100000.0
    assert len(seen) == 8


# -- LAST_LEG_END, the idle gap, PAUSE
def test_last_leg_end_is_written_after_every_leg_and_the_gap_is_honoured(world):
    ends = []
    orig = world.ops.harvest

    def harvest(root, *, emails):
        ends.append(pl.read_last_leg_end(world.wd))                     # already written when the harvest runs
        return orig(root, emails=emails)
    world.ops.harvest = harvest
    assert go(world) == 0
    assert len(ends) == 8 and ends == sorted(ends) and len(set(ends)) == 8
    last = pl.read_last_leg_end(world.wd)
    assert last == ends[-1] and (world.wd / pl.LAST_LEG_END).read_text().strip() == str(float(last))
    times = [world.ops.launch_times[f"{n}.a1"] for n in LEGS]
    for end, nxt in zip(ends, times[1:]):
        assert nxt - end >= pl.IDLE_GAP_S
    assert times[0] == T0                                               # nothing precedes the first leg


def test_a_recent_last_leg_end_delays_the_first_launch(world):
    (world.wd / "p426").mkdir(parents=True, exist_ok=True)
    (world.wd / pl.LAST_LEG_END).write_text(str(T0 - 100.0))
    go(world, "--through", "tg1-p426-off-pilot")
    assert world.ops.launch_times["tg1-p426-off-pilot.a1"] >= T0 - 100.0 + 600.0


def test_an_unreadable_last_leg_end_stops_before_any_launch(world):
    (world.wd / "p426").mkdir(parents=True, exist_ok=True)
    (world.wd / pl.LAST_LEG_END).write_text("not a number")
    assert go(world) == 1 and world.ops.launches == []


def test_pause_holds_at_the_boundary_and_restarts_the_gap(world):
    pause = world.out / "PAUSE"
    pause.parent.mkdir(parents=True, exist_ok=True)
    pause.write_text("")
    released = []

    def hook(clock):
        if len(clock.sleeps) == 4 and pause.exists():
            pause.unlink()
            released.append(clock.t)
    world.clock.hook = hook
    go(world, "--through", "tg1-p426-off-pilot")
    assert released and world.ops.launch_times["tg1-p426-off-pilot.a1"] >= released[0] + pl.IDLE_GAP_S
    assert world.ops.launch_times["tg1-p426-off-pilot.a1"] > released[0]


def test_custom_pause_file_is_honoured(world):
    pause = world.wd / "custom-pause"
    pause.write_text("")
    world.clock.hook = lambda c: pause.unlink() if len(c.sleeps) == 2 and pause.exists() else None
    go(world, "--pause-file", str(pause), "--through", "tg1-p426-off-pilot")
    assert not pause.exists() and world.ops.launch_times["tg1-p426-off-pilot.a1"] > T0 + 60


def test_low_power_before_a_launch_stops_without_consuming_an_attempt(world):
    world.ops.pw = dict(watts=96, volts=20, battery=90, on_battery_intervals=[])
    assert go(world) == 1 and world.ops.launches == [] and not list(world.out.glob("*.a1"))


# -- locks
def test_sequencer_lock_is_held_for_the_whole_sequence_and_refuses_a_concurrent_gate_or_sequencer(world, capsys):
    probes = []

    def on_launch(ops, name, root):
        probes.append((name, flocked(world.wd / pl.SEQUENCER), flocked(world.wd / pl.LEG)))
        with pytest.raises(pl.LockRefused):
            pl.acquire("gate", world.wd)
        assert go(world) == 2                                          # a second sequencer: REFUSED
        assert "REFUSED" in capsys.readouterr().err
    world.ops.on_launch = on_launch
    go(world, "--through", "tg1-p426-on-pilot")
    assert probes and all(p[1:] == (True, False) for p in probes)
    assert not flocked(world.wd / pl.SEQUENCER)                        # released at the end
    pl.acquire("gate", world.wd).release()


def test_lock_is_released_when_the_sequence_stops_on_a_failure(world):
    world.ops.scenario["tg1-p426-off-pilot"] = dict(rc=1, status="crashed")
    assert go(world) == 1
    assert not flocked(world.wd / pl.SEQUENCER)


def test_a_held_gate_refuses_the_sequencer(world, capsys):
    held = pl.acquire("gate", world.wd)
    try:
        assert go(world) == 2 and "gate/RUNNING" in capsys.readouterr().err and world.ops.launches == []
    finally:
        held.release()


# -- records
def test_the_sequencer_refuses_a_tampered_or_drifted_record_before_launching(world, capsys):
    world.ops.state[str(world.off)]["head"] = "9" * 40
    assert go(world) == 1 and world.ops.launches == [] and "HEAD" in (world.out / "sequence.log").read_text()
    world.ops.state[str(world.off)]["head"] = OFF_HEAD
    p = world.rec / "v8_base.json"
    p.write_text(p.read_text().replace("s2", "s7", 1))
    assert go(world) == 2 and "sha256" in capsys.readouterr().err and world.ops.launches == []


def test_a_missing_record_dir_refuses(world, capsys):
    (world.rec / "v8_base.json").unlink()
    assert go(world) == 2 and "v8_base.json" in capsys.readouterr().err and world.ops.launches == []


def test_a_drift_between_legs_stops_before_the_next_launch(world):
    def drift(ops, name, root):
        if name == "tg1-p426-off-pilot":
            ops.state[str(world.on)]["clean"] = False
    world.ops.on_launch = drift
    assert go(world) == 1
    assert world.ops.names() == LEGS[:1]


# -- attempts, resume, reruns
def test_resume_skips_only_valid_harvested_legs_and_resumes_the_pair_from_the_persisted_receipt(world):
    assert go(world, "--through", "tg1-p426-off-s1") == 0
    assert world.ops.names() == LEGS[:3]
    world.clock.t += 3600
    assert go(world) == 0
    assert world.ops.names() == LEGS                                      # legs 1-3 were not relaunched
    argv = world.ops.launches[3]["argv"]
    assert argv[argv.index("--pair-receipt") + 1] == str(world.out / "tg1-p426-off-s1.a1" / "receipt.json")
    assert all(l["attempt"] == 1 for l in seq(world)["legs"])


def test_resume_harvests_a_valid_leg_that_was_never_harvested(world):
    world.ops.harvest_rc = 5
    assert go(world) == 4                                                 # a harvest failure stops the run
    assert world.ops.names() == LEGS[:1]
    world.ops.harvest_rc = 0
    world.clock.t += 3600
    assert go(world) == 0
    assert world.ops.names() == LEGS and world.ops.names("harvest").count("tg1-p426-off-pilot") == 2     # harvested again, not rerun


def test_an_invalid_leg_is_never_rerun_without_the_operator(world, capsys):
    world.ops.scenario["tg1-p426-off-s1"] = dict(rc=2, status="invalidated", invalid=[dict(stage="done", slot="s", reason="x", at="t")])
    assert go(world) == 1
    world.ops.scenario["tg1-p426-off-s1"] = {}
    world.clock.t += 3600
    assert go(world) == 1 and world.ops.names() == LEGS[:3]               # still stopped: a rerun is the operator's decision
    assert "rerun" in (world.out / "sequence.log").read_text()


def test_a_labelled_rerun_is_a_new_attempt_on_a_fresh_out_root_and_a_new_dossier(world):
    world.ops.scenario["tg1-p426-off-s1"] = dict(rc=2, status="invalidated", invalid=[dict(stage="done", slot="s", reason="x", at="t")])
    go(world)
    first_root = world.out / "tg1-p426-off-s1.a1"
    before = {p.name: p.read_bytes() for p in first_root.rglob("*") if p.is_file()}
    world.ops.scenario["tg1-p426-off-s1"] = {}
    world.clock.t += 3600
    assert go(world, "--rerun", "tg1-p426-off-s1", "--rerun-reason", "operator: disk was full") == 0
    assert (world.out / "tg1-p426-off-s1.a2").is_dir()
    assert {p.name: p.read_bytes() for p in first_root.rglob("*") if p.is_file()} == before          # nothing of attempt 1 reused or touched
    argv = [l["argv"] for l in world.ops.launches if l["name"] == "tg1-p426-off-s1"][-1]
    assert argv[argv.index("--out-root") + 1].endswith("tg1-p426-off-s1.a2")
    assert (world.out / "pairs" / "s1__off-a2__on-a1.json").is_file()
    assert [(l["leg"], l["attempt"], l["state"]) for l in seq(world)["legs"] if l["leg"] == "tg1-p426-off-s1"] == [
        ("tg1-p426-off-s1", 1, "INVALID"), ("tg1-p426-off-s1", 2, "VALID")]
    assert seq(world)["reruns"][0]["reason"] == "operator: disk was full"


def test_an_attempt_directory_already_on_disk_is_never_reused(world):
    (world.out / "tg1-p426-off-pilot.a1").mkdir(parents=True)
    (world.out / "tg1-p426-off-pilot.a1" / "stale").write_text("x")
    go(world, "--through", "tg1-p426-off-pilot")
    assert (world.out / "tg1-p426-off-pilot.a2").is_dir() and (world.out / "tg1-p426-off-pilot.a1" / "stale").read_text() == "x"


def test_a_leg_left_running_by_a_dead_sequencer_stops_the_run(world):
    go(world, "--through", "tg1-p426-off-pilot")
    doc = seq(world)
    doc["legs"].append(dict(leg="tg1-p426-on-pilot", attempt=1, state="RUNNING"))
    w2.write_sequence(world.out, doc)
    assert go(world) == 1 and world.ops.names() == LEGS[:1] and "RUNNING" in (world.out / "sequence.log").read_text()


def test_sequence_json_names_the_hash_of_the_version_a_restart_found(world):
    go(world, "--through", "tg1-p426-off-pilot")
    found = world.seq.read_bytes()
    assert json.loads(found)["previous_sha256"]                                    # every version after the first names its predecessor
    seen = []
    world.ops.on_launch = lambda ops, name, root: seen.append(seq(world))
    world.clock.t += 3600
    go(world, "--through", "tg1-p426-on-pilot")
    assert seen[0]["previous_sha256"] == hashlib.sha256(found).hexdigest()         # the first write of the restart replaces `found`
    assert seen[0]["legs"][-1]["state"] == "RUNNING"


def test_write_sequence_records_the_previous_versions_hash_and_replaces_atomically(tmp_path):
    w2.write_sequence(tmp_path, dict(legs=[], pairs=[]))
    p = tmp_path / "sequence.json"
    v1 = p.read_bytes()
    assert json.loads(v1)["previous_sha256"] is None
    w2.write_sequence(tmp_path, dict(legs=[dict(leg="a", attempt=1, state="VALID")], pairs=[]))
    assert json.loads(p.read_text())["previous_sha256"] == hashlib.sha256(v1).hexdigest()
    assert not list(tmp_path.glob("*.tmp*"))
    assert w2.read_sequence(tmp_path)["legs"][0]["leg"] == "a"
    assert w2.read_sequence(tmp_path / "none") == dict(legs=[], pairs=[], harvested=[], reruns=[])


def test_the_rerun_flag_must_name_a_known_leg(world, capsys):
    assert go(world, "--rerun", "tg1-p426-nope", "--rerun-reason", "x") == 2 and "--rerun" in capsys.readouterr().err
    assert go(world, "--rerun", "tg1-p426-off-s1") == 2                                           # a rerun is labelled


def test_through_names_a_leg_or_its_number(world, capsys):
    assert go(world, "--through", "2") == 0 and world.ops.names() == LEGS[:2]
    assert go(world, "--through", "tg1-p426-off-s1") == 0 and world.ops.names() == LEGS[:3]
    assert go(world, "--through", "9") == 2 and "--through" in capsys.readouterr().err


# ----------------------------------------------------------------------------------------------- make-up legs
def write_occurrences(path, occs):
    path.write_text("".join(json.dumps(o) + "\n" for o in occs))
    return path


def makeup_world(world, occs):
    go(world)
    world.ops.events.clear()
    world.ops.launches.clear()
    world.clock.t += 3600
    f = write_occurrences(world.wd / "occ.jsonl", occs)
    return f


MK = [occ("s2", "go", "gB", 1), occ("s1", "python", "p2", 1), occ("s1", "python", "p1", 0, "on"), occ("s1", "python", "p1", 0)]


def test_makeup_runs_both_arms_off_then_on_over_the_whole_union(world):
    f = makeup_world(world, MK)
    world.ops.scenario["tg1-p426-off-makeup"] = dict(items=3, session="s1")
    world.ops.scenario["tg1-p426-on-makeup"] = dict(items=3, session="s1")
    assert go(world, "--occurrences", str(f), cmd="makeup") == 0
    assert world.ops.names() == ["tg1-p426-off-makeup", "tg1-p426-on-makeup"]
    canon = [json.loads(x) for x in (world.out / "makeup" / "occurrences.off.jsonl").read_text().splitlines()]
    assert canon == w2.canonical_occurrences(MK) and [c["item"] for c in canon] == ["p1", "p2", "gB"]
    assert (world.out / "makeup" / "occurrences.on.jsonl").read_bytes() == (world.out / "makeup" / "occurrences.off.jsonl").read_bytes()
    argv = world.ops.launches[1]["argv"]
    assert argv[2] == "makeup" and argv[argv.index("--occurrences") + 1] == str(world.out / "makeup" / "occurrences.on.jsonl")
    assert argv[argv.index("--pair-receipt") + 1] == str(world.out / "tg1-p426-off-makeup.a1" / "receipt.json")
    assert argv[argv.index("--out-root") + 1] == str(world.out / "tg1-p426-on-makeup.a1") and not (world.out / "makeup" / "tg1-p426-on-makeup.a1").exists()
    assert argv[argv.index("--frozen-record") + 1] == str(world.rec / "amendment.json")
    assert (world.out / "pairs" / "makeup__off-a1__on-a1.json").is_file()
    assert [l["leg"] for l in seq(world)["legs"]][-2:] == ["tg1-p426-off-makeup", "tg1-p426-on-makeup"]


def test_a_makeup_leg_that_stops_early_records_its_unrun_occurrences(world):
    f = makeup_world(world, MK)
    world.ops.scenario["tg1-p426-off-makeup"] = dict(slots=[S.slot("off", "s1", "x").replace("itemx", "p1")], rc=2, status="invalidated",
                                                     invalid=[dict(stage="done", slot="s", reason="engagement", at="t")])
    assert go(world, "--occurrences", str(f), cmd="makeup") == 1
    d = leg_doc_makeup(world, "tg1-p426-off-makeup.a1")
    assert d["state"] == "INVALID" and [(n["session"], n["item"]) for n in d["not_run"]] == [("s1", "p2"), ("s2", "gB")]
    assert world.ops.names() == ["tg1-p426-off-makeup"]


def leg_doc_makeup(w, attempt):
    return json.loads((w.out / attempt / "leg.json").read_text())


def test_makeup_refuses_a_missing_or_empty_occurrences_file_and_a_missing_amendment(world, capsys):
    assert go(world, cmd="makeup") == 2                                                          # --occurrences is required
    f = write_occurrences(world.wd / "empty.jsonl", [])
    assert go(world, "--occurrences", str(f), cmd="makeup") == 2 and "occurrences" in capsys.readouterr().err
    f = write_occurrences(world.wd / "occ.jsonl", MK)
    assert go(world, "--occurrences", str(f), cmd="makeup") == 2 and "amendment" in capsys.readouterr().err        # the gate has not run
    assert world.ops.launches == []


# ----------------------------------------------------------------------------------------------- rehearsal
@pytest.fixture
def rehearsal(world):
    base = world.wd / "p426" / "rehearsal"
    manifest = base / "manifest.json"
    ph.write_exclusive(manifest, dict(kind="p426_rehearsal", off_commit=OFF_HEAD, on_commit=ON_HEAD, rehearsal=True,
                                      off_worktree="$STACK_WORKDIR/p426/stack-p426-off", on_worktree="$STACK_WORKDIR/p426/stack-p426-on",
                                      out_root="$STACK_WORKDIR/p426/rehearsal/stage", created="t", frozen_prompt_date=DATE,
                                      probe_code_sha256="7" * 64, scaffold_policy_sha256="8" * 64, generation_identity_sha256="9" * 64))
    world.out = base / "run"
    return SimpleNamespace(manifest=manifest, w=world)


def go_rehearsal(r, *extra, date=True):
    w = r.w
    argv = ["rehearsal", "--manifest", str(r.manifest), "--worktree-off", str(w.off), "--worktree-on", str(w.on), "--out-base", str(w.out), *extra]
    if date and "--frozen-prompt-date" not in extra:
        argv += ["--frozen-prompt-date", DATE]
    return w2.main(argv, ops=w.ops, clock=w.clock, sleep=w.clock.sleep)


def test_rehearsal_requires_the_frozen_prompt_date_and_it_must_be_the_manifests(rehearsal, capsys):
    w = rehearsal.w
    assert go_rehearsal(rehearsal, date=False) == 2 and "--frozen-prompt-date" in capsys.readouterr().err
    assert go_rehearsal(rehearsal, "--frozen-prompt-date", "Wed Oct 28 2026") == 2
    assert "manifest" in capsys.readouterr().err and w.ops.launches == []


def test_rehearsal_legs_take_the_date_and_probe_identity_the_manifest_recorded(rehearsal):
    w = rehearsal.w
    w.ops.identity = lambda path: (_ for _ in ()).throw(AssertionError("the rehearsal reads the manifest's identity, not the probe"))
    go_rehearsal(rehearsal)
    argv = w.ops.launches[0]["argv"]
    assert argv[argv.index("--probe-code-sha") + 1] == "7" * 64 and argv[argv.index("--policy-sha") + 1] == "8" * 64
    assert argv[argv.index("--frozen-prompt-date") + 1] == DATE


R_LEGS = ["tg1-p426-rehearsal-off", "tg1-p426-rehearsal-on", "tg1-p426-rehearsal-mismatch", "tg1-p426-rehearsal-kill"]


def test_rehearsal_runs_r1_pair_r2_r3_with_their_injections_and_never_pairs_r2_r3(rehearsal):
    w = rehearsal.w
    w.ops.scenario["tg1-p426-rehearsal-mismatch"] = dict(rc=2, status="invalidated", items=1,
                                                         invalid=[dict(stage="done", slot="s", reason="reconcile mismatch injected", at="t")])
    assert go_rehearsal(rehearsal) == 0
    assert w.ops.names() == R_LEGS
    by = {l["name"]: l["argv"] for l in w.ops.launches}
    assert "--rehearsal" in by[R_LEGS[0]] and by[R_LEGS[0]][by[R_LEGS[0]].index("--frozen-record") + 1] == str(rehearsal.manifest)
    assert by[R_LEGS[1]][by[R_LEGS[1]].index("--pair-receipt") + 1] == str(w.out / "tg1-p426-rehearsal-off.a1" / "receipt.json")
    assert by[R_LEGS[2]][by[R_LEGS[2]].index("--inject") + 1] == "reconcile-mismatch"
    assert by[R_LEGS[3]][by[R_LEGS[3]].index("--inject") + 1] == "stall-kill"
    assert "--pair-receipt" not in by[R_LEGS[2]] and "--pair-receipt" not in by[R_LEGS[3]]
    assert (w.out / "pairs" / "r1__off-a1__on-a1.json").is_file() and w.ops.published_dossiers == []          # never published
    assert leg_doc(w, "tg1-p426-rehearsal-mismatch.a1")["state"] == "INVALID"
    assert w.ops.names("harvest") == R_LEGS                                                         # harvested into the scratch stage


def test_rehearsal_runs_from_a_manifest_written_by_p426_freeze(world, capsys):
    """Item 0: the real `p426_freeze rehearsal` manifest (date + identity) drives `p426_wave2 rehearsal`: the four legs in order."""
    from bench import p426_freeze as fz
    from bench.tests import test_b2_s8_freeze as F
    fops = F.FOps(world.wd, world.off, world.on)
    manifest = world.wd / "p426" / "rehearsal" / "manifest.json"
    pins = world.off / "src/mlx-vlm/dev/p369_phase2/pins.json"
    pins.parent.mkdir(parents=True)
    pins.write_text("{}")
    rc = fz.main(["rehearsal", "--off-worktree", str(world.off), "--on-worktree", str(world.on), "--out-root",
                  str(world.wd / "p426/rehearsal/stage"), "--out", str(manifest), "--frozen-prompt-date", DATE], ops=fops,
                 checks=lambda kind, **kw: [])
    assert rc == 0, capsys.readouterr().err
    world.out = world.wd / "p426" / "rehearsal" / "run"
    rc = w2.main(["rehearsal", "--manifest", str(manifest), "--worktree-off", str(world.off), "--worktree-on", str(world.on),
                  "--out-base", str(world.out), "--frozen-prompt-date", DATE], ops=world.ops, clock=world.clock, sleep=world.clock.sleep)
    log = (world.out / "sequence.log").read_text() if (world.out / "sequence.log").exists() else capsys.readouterr().err
    assert world.ops.names() == R_LEGS, (rc, log[-1500:])


@pytest.mark.parametrize("shape", ["date-only", "nested-identity"])
def test_rehearsal_identity_comes_from_the_manifest_or_else_from_ops_identity(world, shape):
    """Item 0: a manifest that records the date but not the identity keys (or nests them) still runs: `ops.identity(off_worktree)`."""
    body = dict(kind="p426_rehearsal", off_commit=OFF_HEAD, on_commit=ON_HEAD, rehearsal=True, created="t", frozen_prompt_date=DATE,
                off_worktree="$STACK_WORKDIR/p426/stack-p426-off", on_worktree="$STACK_WORKDIR/p426/stack-p426-on",
                out_root="$STACK_WORKDIR/p426/rehearsal/stage")
    if shape == "nested-identity":
        body["identity"] = {"probe_code_sha256": "7" * 64, "scaffold_policy_sha256": "8" * 64, "generation_identity_sha256": "9" * 64}
    manifest = world.wd / "p426" / "rehearsal" / "manifest.json"
    ph.write_exclusive(manifest, body)
    world.out = world.wd / "p426" / "rehearsal" / "run"
    rc = w2.main(["rehearsal", "--manifest", str(manifest), "--worktree-off", str(world.off), "--worktree-on", str(world.on),
                  "--out-base", str(world.out), "--frozen-prompt-date", DATE], ops=world.ops, clock=world.clock, sleep=world.clock.sleep)
    assert world.ops.names() == R_LEGS, rc
    argv = world.ops.launches[0]["argv"]
    want = ("7" * 64) if shape == "nested-identity" else world.ops.ident["probe_code_sha256"]
    assert argv[argv.index("--probe-code-sha") + 1] == want


def test_rehearsal_stops_when_r1_is_not_valid(rehearsal):
    w = rehearsal.w
    w.ops.scenario["tg1-p426-rehearsal-off"] = dict(rc=2, status="invalidated", invalid=[dict(stage="ready", slot="s", reason="x", at="t")])
    assert go_rehearsal(rehearsal) == 1 and w.ops.names() == R_LEGS[:1]


def test_rehearsal_accepts_only_a_rehearsal_manifest_and_stays_under_the_rehearsal_directory(world, rehearsal, capsys):
    w = rehearsal.w
    rc = w2.main(["rehearsal", "--manifest", str(w.rec / "v8_base.json"), "--worktree-off", str(w.off), "--worktree-on", str(w.on),
                  "--out-base", str(w.out), "--frozen-prompt-date", DATE], ops=w.ops, clock=w.clock, sleep=w.clock.sleep)
    assert rc == 2 and "rehearsal" in capsys.readouterr().err
    w.out = w.wd / "p426" / "wave2"
    assert go_rehearsal(rehearsal) == 2 and "--out-base" in capsys.readouterr().err and w.ops.launches == []


def test_run_and_makeup_refuse_an_out_base_inside_the_rehearsal_directory(world, capsys):
    world.out = world.wd / "p426" / "rehearsal" / "x"
    assert go(world) == 2 and "--out-base" in capsys.readouterr().err and world.ops.launches == []


def test_rehearsal_checks_the_arm_commits_of_the_manifest(rehearsal, capsys):
    rehearsal.w.ops.state[str(rehearsal.w.off)]["head"] = "9" * 40
    assert go_rehearsal(rehearsal) == 1 and rehearsal.w.ops.launches == []


# ----------------------------------------------------------------------------------------------- other
def test_every_cli_refusal_is_one_stderr_line_with_exit_2(world, capsys):
    for argv in (["bogus"], ["run"], ["run", "--record-dir", "x"]):
        assert w2.main(argv, ops=world.ops, clock=world.clock, sleep=world.clock.sleep) == 2
        err = capsys.readouterr().err
        assert err.startswith("REFUSED: ") and err.count("\n") == 1


def test_the_sequencer_refuses_without_stack_workdir(world, monkeypatch, capsys):
    monkeypatch.delenv("STACK_WORKDIR")
    world.ops.wd = None
    assert go(world) == 2 and "STACK_WORKDIR" in capsys.readouterr().err


def test_the_module_never_takes_leg_lock_nor_kills_and_uses_the_start_time_identity():
    src = Path(w2.__file__).read_text()
    assert 'acquire("chain"' not in src and "os.kill" not in src and ".terminate(" not in src and "killpg" not in src
    assert "psutil" not in src and ".create_time()" not in src                    # C151: process identity is the start time the ops report
