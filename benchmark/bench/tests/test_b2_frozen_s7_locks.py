"""P426 B2 frozen tests, s7 locks (spec v3.2 §9, §3 entry checks) and the chain-level `--p426` leg (§3, §4, §5, §7, §16.4).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour.
Gate side: `local_gate.main(["run", "--repo", "stack"])` in-process with git, the busy census and the clone faked
(`b2_frozen_support.gate_harness`). Chain side: a hermetic `--p426` leg (§16.4) = `run_tg1_chain.main(argv, ops=<FakeOps with
the §16.2 / §16.4 seams>, …, campaign=<fake>)` + the item-barrier fake probe + records written with the §16.1 recipe
(`b2_frozen_support.p426_world`). These tests live in s7 because a positive leg needs slices 1-7 (records, hooks,
reconciliation, the receipt, the locks)."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from bench import chain_rows as cr
from bench.tests import b2_frozen_support as S


@pytest.mark.parametrize("held", ["p426/SEQUENCER.lock", "p426/LEG.lock"])
def test_new_the_gate_refuses_while_an_opposing_p426_lock_is_held(tmp_path, monkeypatch, held):
    seen = S.gate_harness(monkeypatch, tmp_path)
    with S.held_flock(tmp_path / held):
        got = S.gate_main()
    assert got == 1 and seen["reached"] is False
    assert not S.is_flocked(tmp_path / "gate" / "RUNNING")


def test_new_the_gate_holds_its_own_running_lock_while_it_works(tmp_path, monkeypatch):
    seen = S.gate_harness(monkeypatch, tmp_path)
    got = S.gate_main()
    assert isinstance(got, S.GateReached) and seen["running_locked"] is True


def test_new_acquisition_is_serialized_by_the_arbiter(tmp_path, monkeypatch):
    """§9 [r3]: every actor takes `$STACK_WORKDIR/locks/ARBITER.lock` (blocking, bounded 30 s) for its acquisition step."""
    seen = S.gate_harness(monkeypatch, tmp_path)
    box = {}
    with S.held_flock(tmp_path / "locks" / "ARBITER.lock"):
        th = threading.Thread(target=lambda: box.update(got=S.gate_main()), daemon=True)
        th.start()
        time.sleep(1.0)
        assert seen["reached"] is False                         # waiting on the arbiter, not past it
    th.join(40)
    assert isinstance(box.get("got"), S.GateReached) and seen["reached"] is True


def test_new_a_gate_started_while_another_gate_runs_refuses(tmp_path, monkeypatch):
    """Own lock `gate/RUNNING` held by a running gate: a second actor that takes it finds it held (and the arbiter released)."""
    seen = S.gate_harness(monkeypatch, tmp_path)
    with S.held_flock(tmp_path / "gate" / "RUNNING"):
        got = S.gate_main()
    assert got == 1 and seen["reached"] is False
    assert not S.is_flocked(tmp_path / "locks" / "ARBITER.lock")


# ================================================================================================ the chain-level --p426 leg
PY = [f"p{i}" for i in range(1, 7)]
GO = [f"g{i}" for i in range(1, 7)]
PILOT = S.p426_order(PY, 1001)[:5]


def leg(tmp_path, monkeypatch, *, arm="off", mode=("pilot",), out_name=None, rehearsal=False, probe_env=None,
        before=None, timeout=120):
    env = S.p426_world(tmp_path, monkeypatch, arm=arm, out_name=out_name, rehearsal=rehearsal)
    env["ops"].extra_env.update(probe_env or {})
    if before:
        before(env)
    argv, rfd = S.p426_argv(env, mode)
    try:
        rc = S.run_p426(env, argv, rfd=rfd, timeout=timeout)
    finally:
        env["ops"].cancel()
    return rc, env


def invs(env):
    """(lang, [items]) of every probe invocation, in launch order (the fake probe's invocations.jsonl)."""
    out = []
    for inv in S.invocations(env):
        a = inv["argv"]
        out.append((a[a.index("--lang") + 1], [x for x in a[a.index("--items") + 1].split(",") if x]))
    return out


def barrier(env):
    return S.barrier_files(env["out"])


def has(env, suffix):
    return any(f.endswith(suffix) for f in barrier(env))


def refused(env):
    return [ln for ln in env["lines"] if "REFUSED: " in ln and "unrecognized arguments" not in ln]


def records(env, pattern):
    return sorted(Path(env["out"]).rglob(pattern))


# ------------------------------------------------------------------------------------------------ the positive leg
def test_new_a_hermetic_p426_pilot_leg_is_valid_with_ready_records_before_each_go(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch)
    assert rc == 0, "\n".join(env["lines"][-20:])
    assert invs(env) == [("python", PILOT)]                                  # §7: the first 5 of s1's P426 Python order
    ready = records(env, "items/*.ready.json")
    assert len(ready) == 5
    gos = {int(p.name.rsplit(".item", 1)[1].split(".")[0]): p for p in Path(env["out"]).rglob("*.item*.go")}
    for p in ready:
        doc = json.loads(p.read_text())
        assert {"slot", "item", "k", "log_cursor", "worker_snapshot", "owned", "at"} <= set(doc)
        assert p.name == cr.slot_file(doc["slot"]) + ".ready.json"
        assert p.stat().st_mtime_ns <= gos[doc["k"]].stat().st_mtime_ns          # written before its `.go`
        assert {"path", "device", "inode", "offset"} <= set(doc["log_cursor"])
    items = [p for p in records(env, "items/*.json") if not p.name.endswith((".ready.json", ".dnf.json"))]
    assert len(items) == 5 and all(json.loads(p.read_text())["verdict"] == "reconciled" for p in items)
    assert all(json.loads(p.read_text())["case"] == "completed" for p in items)


def test_new_the_p426_chain_passes_evidence_p426_to_the_probe(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch)
    assert rc == 0 and S.invocations(env), "\n".join(env["lines"][-10:])
    argv = S.invocations(env)[0]["argv"]
    assert argv[argv.index("--evidence") + 1] == "p426"


def test_new_the_leg_freezes_its_schedule_and_bounds_its_logs(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch)
    assert rc == 0
    cj = json.loads((Path(env["out"]) / "chain.json").read_text())
    assert isinstance(cj.get("schedule_sha256"), str) and len(cj["schedule_sha256"]) == 64
    (bounds,) = records(env, "log_bounds.json")
    doc = json.loads(bounds.read_text())
    assert doc["finalized"] and {Path(f["path"]).name for f in doc["files"]} == {"mlx_vlm.log", "main_model.log"}
    assert all(f["offset_end"] is not None and f["offset_end"] >= f["offset_start"] for f in doc["files"])


def test_new_the_receipt_is_written_after_load_and_never_holds_a_credential_value(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch, arm="on")
    assert rc == 0
    rec = json.loads((Path(env["out"]) / "receipt.json").read_text())
    assert S.self_hashed(rec)["sha256"] == rec["sha256"] and "credentials" not in rec          # C238: keys only
    assert all("HF_TOKEN" in rec["credential_keys"][who] for who in ("router", "worker", "probe"))
    assert all("HF_TOKEN" not in rec["env"][who] for who in ("router", "worker", "probe"))   # §16.7: absent from env
    assert S.FAKE_SECRET_40 not in S.all_output_text(env["out"])


def test_new_log_bounds_is_a_two_phase_record_created_before_the_router_and_finalized_once(tmp_path, monkeypatch):
    """[d2] §16 record classes: `log_bounds.json` is exclusive-created (offsets open) before the router starts, then finalized
    once by atomic replace."""
    seen = {}

    def spy(env):
        original = env["ops"].start_router

        def start():
            found = records(env, "log_bounds.json")
            seen["doc"] = json.loads(found[0].read_text()) if found else None
            return original()
        env["ops"].start_router = start
    rc, env = leg(tmp_path, monkeypatch, before=spy)
    assert rc == 0 and seen["doc"] is not None
    assert not seen["doc"]["finalized"] and all(f["offset_end"] is None for f in seen["doc"]["files"])
    (bounds,) = records(env, "log_bounds.json")
    final = json.loads(bounds.read_text())
    assert final["finalized"] and final["created"] == seen["doc"]["created"]
    assert [(f["path"], f["inode"], f["offset_start"]) for f in final["files"]] == [
        (f["path"], f["inode"], f["offset_start"]) for f in seen["doc"]["files"]]


def test_new_records_destined_for_main_carry_no_absolute_paths(tmp_path, monkeypatch):
    """[d2] §11.2: every path in a `main` record is written `$STACK_WORKDIR/…`, `<WT>/…` or `<OUT>/…`, never absolute."""
    rc, env = leg(tmp_path, monkeypatch, probe_env={"B2_ABORTS": json.dumps({PILOT[1]: "boundary"})})
    assert rc == 0
    recs = (records(env, "items/*.json") + records(env, "receipt.json") + records(env, "log_bounds.json")
            + records(env, "p426_dnf/*.json"))
    assert len(recs) >= 5 + 5 + 1 + 1 + 1
    for p in recs:
        assert str(tmp_path) not in p.read_text() and str(Path(tmp_path).resolve()) not in p.read_text(), p.name


def test_new_chain_json_is_portable(tmp_path, monkeypatch):
    """post-reveal 3f (§16.8 after delivery 3e): `chain.json` `argv`, `probe` and every recorded path are written
    `$STACK_WORKDIR/…`, `<WT>/…` or `<OUT>/…`; no DNF, so this holds apart from the flat-layout DNF item."""
    rc, env = leg(tmp_path, monkeypatch)
    assert rc == 0, "\n".join(env["lines"][-20:])
    text = (Path(env["out"]) / "chain.json").read_text()
    cj = json.loads(text)
    assert "argv" in cj and "probe" in cj
    assert str(tmp_path) not in text and str(Path(tmp_path).resolve()) not in text
    assert str(Path.home()) not in text


def test_new_the_p426_dnf_record_carries_the_section_16_1_fields(tmp_path, monkeypatch):
    """[d2] §16.1: `pick` = the leg's model; `load_gen` = the aborted invocation's load generation; `invocation` = its index in
    `chain.json` `progress.invocations`; `attempt` = the `n` of the out-root name `<leg>.a<n>`; `item_record` names the DNF's
    item record `items/<slot_file>.dnf.json`."""
    rc, env = leg(tmp_path, monkeypatch, probe_env={"B2_ABORTS": json.dumps({PILOT[1]: "boundary"})})
    assert rc == 0
    (side,) = records(env, "p426_dnf/*.json")
    dnf = json.loads(side.read_text())
    cj = json.loads((Path(env["out"]) / "chain.json").read_text())
    assert (dnf["pick"], dnf["attempt"], dnf["session"], dnf["language"], dnf["seed"], dnf["arm"]) == (
        S.MODEL, 1, "pilot", "python", 1001, "off")
    assert type(dnf["invocation"]) is int and type(dnf["load_gen"]) is int
    assert type(dnf.get("load")) is int                  # post-reveal 3h (§16.8 after the strict verify round 1): `load`
    assert [d for d in cj["p426_dnf"] if d["slot"] == dnf["slot"]] == [dnf]     # 3h: chain.json's entry equals its sidecar
    inv = cj["progress"]["invocations"][dnf["invocation"]]
    assert inv["load_gen"] == dnf["load_gen"] and dnf["slot"] in inv["expected_slots"]
    assert side.name == cr.slot_file(dnf["slot"]) + ".json"
    assert dnf["item_record"].endswith("items/" + cr.slot_file(dnf["slot"]) + ".dnf.json")
    assert S.self_hashed(dnf)["sha256"] == dnf["sha256"]                    # an immutable record ([d2] §16 classes)


def test_new_the_rehearsal_runs_the_smoke_shape_of_s1s_p426_python_order(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch, mode=("chain", "s1", "--rehearsal"), rehearsal=True)
    assert rc == 0, "\n".join(env["lines"][-20:])
    order = S.p426_order(PY, 1001)
    assert invs(env) == [("python", order[:1]), ("python", order[1:3])]
    assert "/p426/rehearsal/" in str(env["out"])
    # post-reveal 3h (§16.8 after the strict verify round 1, rehearsal binding): chain.json names the manifest and the inject
    cj = json.loads((Path(env["out"]) / "chain.json").read_text())
    reh = Path(env["records"]["reh"])
    assert cj["frozen_record"] == dict(path="$STACK_WORKDIR/records/rehearsal.json", sha256=json.loads(reh.read_text())["sha256"])
    assert cj["inject"] is None


def test_new_an_s2_leg_runs_go_first_then_python_in_the_p426_orders(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch, mode=("chain", "s2"), out_name="tg1-p426-off-s2.a1", timeout=240)
    assert rc == 0, "\n".join(env["lines"][-20:])
    got = invs(env)
    assert got, "no probe invocation"
    assert got[0] == ("go", S.p426_order(GO, 2002)[:5])                      # the in-load pilot phase: Go first
    go = [i for lang, items in got if lang == "go" for i in items]
    py = [i for lang, items in got if lang == "python" for i in items]
    assert go == S.p426_order(GO, 2002) and py == S.p426_order(PY, 2002)
    assert [lang for lang, _ in got] == sorted([lang for lang, _ in got], key=lambda x: x != "go")


# ------------------------------------------------------------------------------------------------ invalidate at ready / done
def test_new_a_failed_done_check_invalidates_after_that_item(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch, probe_env={"B2_SKEW_ITEMS": PILOT[2]})
    assert rc == 2
    assert has(env, ".item2.done") and has(env, ".item2.stop") and not has(env, ".item2.continue")
    assert not any(".item3." in f for f in barrier(env))
    invalid = [json.loads(p.read_text()) for p in records(env, "items/*.json") if not p.name.endswith(".ready.json")]
    assert [d["verdict"] for d in invalid].count("invalid") == 1
    assert "invalidate" in (Path(env["out"]) / "chain.json").read_text() and len(S.invocations(env)) == 1


def test_new_a_failed_ready_check_invalidates_before_the_items_go(tmp_path, monkeypatch):
    def dirty_after_item1(env):
        base = env["ops"].worktree_state

        def state(*a):
            doc = base(*a)
            if any(Path(env["out"]).rglob("*.item1.continue")):
                doc["clean"] = False                                           # a file changed in <WT> after item 1
            return doc
        env["ops"].worktree_state = state
    rc, env = leg(tmp_path, monkeypatch, before=dirty_after_item1)
    assert rc == 2
    assert has(env, ".item2.ready") and has(env, ".item2.stop") and not has(env, ".item2.go")
    assert "invalidate" in (Path(env["out"]) / "chain.json").read_text() and len(S.invocations(env)) == 1


def test_new_an_on_leg_without_drafter_counters_invalidates(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch, arm="on", probe_env={"B2_DRAFT": "0"})
    assert rc == 2 and has(env, ".item0.stop") and not any(".item1." in f for f in barrier(env))


# ------------------------------------------------------------------------------------------------ DNF (§5.1-5.3)
@pytest.mark.parametrize("mode,case", [("boundary", "dnf_boundary"), ("inflight_failed", "dnf_inflight_failed"),
                                       ("inflight_completed", "dnf_completed_unaccounted")])
def test_new_a_transport_dnf_is_recorded_and_the_remaining_items_run_in_order_on_the_same_load(tmp_path, monkeypatch,
                                                                                               mode, case):
    rc, env = leg(tmp_path, monkeypatch, probe_env={"B2_ABORTS": json.dumps({PILOT[1]: mode})})
    assert rc == 0, "\n".join(env["lines"][-20:])
    assert invs(env) == [("python", PILOT), ("python", PILOT[2:])]           # relaunched for the rest, in order
    assert len(env["ops"].names("load")) == 1                                  # no reload, retries 0
    (side,) = records(env, "p426_dnf/*.json")
    dnf = json.loads(side.read_text())
    assert dnf["item"].endswith(PILOT[1]) and dnf["abort"]["cause"] == "connection"
    item_rec = Path(env["out"]) / dnf["item_record"] if not Path(dnf["item_record"]).is_absolute() else Path(dnf["item_record"])
    assert item_rec.name.endswith(".dnf.json") and json.loads(item_rec.read_text())["case"] == case
    assert dnf["slot"] in (Path(env["out"]) / "chain.json").read_text()
    assert "invalidate" not in (Path(env["out"]) / "chain.json").read_text()  # a transport DNF never invalidates


def test_new_a_dnf_followed_by_a_normal_item_rebaselines_its_window(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch, probe_env={"B2_ABORTS": json.dumps({PILOT[1]: "inflight_failed"})})
    assert rc == 0
    after = [json.loads(p.read_text()) for p in records(env, "items/*.json")
             if not p.name.endswith((".ready.json", ".dnf.json"))]
    assert len(after) == 4 and all(d["verdict"] == "reconciled" and d["case"] == "completed" for d in after)


def test_new_the_third_dnf_of_a_leg_is_systemic(tmp_path, monkeypatch):
    aborts = {PILOT[0]: "boundary", PILOT[1]: "boundary", PILOT[2]: "boundary"}
    rc, env = leg(tmp_path, monkeypatch, probe_env={"B2_ABORTS": json.dumps(aborts)})
    assert rc == 2 and len(S.invocations(env)) == 3 and len(records(env, "p426_dnf/*.json")) <= 2


def test_new_a_changed_worker_with_a_dnf_stamp_is_systemic_never_a_dnf(tmp_path, monkeypatch):
    def worker_replaced_at_item1(env):
        base = env["ops"].worker_ident

        def ident(model):
            r = base(model)
            if r and any(Path(env["out"]).rglob("*.item1.go")):
                r = dict(r, pid=r["pid"] + 500)
            return r
        env["ops"].worker_ident = ident
    rc, env = leg(tmp_path, monkeypatch, probe_env={"B2_ABORTS": json.dumps({PILOT[1]: "boundary"})},
                  before=worker_replaced_at_item1)
    assert rc == 2 and len(S.invocations(env)) == 1 and has(env, ".item1.go")
    assert not records(env, "p426_dnf/*.json")


def test_new_an_abort_without_a_dnf_cause_is_systemic(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch, probe_env={"B2_ABORTS": json.dumps({PILOT[1]: "boundary"}),
                                                    "B2_ABORT_CAUSE": "server_error"})
    assert rc == 2 and len(S.invocations(env)) == 1 and has(env, ".item1.go")
    assert not records(env, "p426_dnf/*.json")


# ------------------------------------------------------------------------------------------------ manifest / entry checks
def test_new_the_chain_refuses_a_manifest_without_the_p426_evidence_policy(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch, probe_env={"B2_ITEM_BARRIER": "off"})
    assert rc == 2 and len(S.invocations(env)) == 1
    assert not list(Path(env["out"]).rglob("*.ACK")) and not list(Path(env["out"]).rglob("*.jsonl"))


def _entry(env_fn):
    def before(env):
        env_fn(env)
    return before


@pytest.mark.parametrize("name,setup", [
    ("busy", lambda env: setattr(env["ops"], "start_state", lambda: {
        "watts": 140, "volts": 28, "batt": 80, "free_mem_mb": 1, "orphans_clean": True,
        "busy": ["4242 python -m bench.run_lcb --model other"]})),
    ("idle_gap", lambda env: setattr(env["ops"], "last_leg_end", lambda: time.time() - 10.0)),
    ("power", lambda env: setattr(env["ops"], "power_state", lambda: {"watts": 96, "volts": 20, "batt": 80})),
    ("head", lambda env: env["state"].update(head="c" * 40)),
    ("dirty", lambda env: env["state"].update(clean=False)),
    ("identity", lambda env: env["ops"].extra_env.update(FAKE_PROBE_CODE_SHA="8" * 64)),
])
def test_new_a_failed_entry_check_refuses_before_the_router(tmp_path, monkeypatch, name, setup):
    rc, env = leg(tmp_path, monkeypatch, before=_entry(setup))
    assert rc == 2 and refused(env), env["lines"][-5:]
    assert not env["ops"].names("start_router") and not S.invocations(env)


# ------------------------------------------------------------------------------------------------ the chain's locks (§9)
def test_new_the_chain_refuses_while_the_gate_runs(tmp_path, monkeypatch):
    def hold(env):
        env["held"] = S.held_flock(tmp_path / "gate" / "RUNNING")
        env["held"].__enter__()
    try:
        rc, env = leg(tmp_path, monkeypatch, before=hold)
    finally:
        pass
    env["held"].__exit__(None, None, None)
    assert rc == 2 and refused(env) and not env["ops"].names("start_router")


def test_new_the_chain_holds_its_leg_lock_while_it_runs(tmp_path, monkeypatch):
    seen = []

    def spy(env):
        original = env["ops"].start_router

        def start():
            seen.append(S.is_flocked(tmp_path / "p426" / "LEG.lock"))
            return original()
        env["ops"].start_router = start
    rc, env = leg(tmp_path, monkeypatch, before=spy)
    assert rc == 0 and seen == [True]


def test_new_a_spawned_probe_holds_no_lock_fd(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch, probe_env={"B2_LOCK_PROBE": str(tmp_path / "p426" / "LEG.lock")})
    assert rc == 0
    assert json.loads((env["ops"].state / "lockcheck.json").read_text())["inherited_fds"] == []


def test_new_of_a_simultaneous_gate_and_chain_exactly_one_runs(tmp_path, monkeypatch):
    from bench import local_gate as lg
    env = S.p426_world(tmp_path, monkeypatch)
    seen = S.gate_harness(monkeypatch, tmp_path)
    done = threading.Event()

    def clone(live, sha, dest):                      # the gate holds its lock while it works, until the chain resolved
        seen["reached"] = True
        done.wait(60)
        raise S.GateReached()
    monkeypatch.setattr(lg, "clone_scratch", clone)
    argv, rfd = S.p426_argv(env, ("pilot",))

    def chain():
        try:
            return S.run_p426(env, argv, rfd=rfd)
        finally:
            done.set()
    try:
        gate_res, chain_rc = S.simultaneous(S.gate_main, chain, timeout=180)
    finally:
        env["ops"].cancel()
    chain_ran = bool(env["ops"].names("start_router"))
    gate_ran = seen["reached"] is True
    assert chain_ran != gate_ran, (gate_res, chain_rc)
    if gate_ran:
        assert chain_rc == 2 and refused(env)
    else:
        assert gate_res == 1 and chain_rc == 0
