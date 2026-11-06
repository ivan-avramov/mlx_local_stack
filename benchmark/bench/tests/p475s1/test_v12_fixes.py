"""Delivery 3: one failing-case test per adopted round-1 defect (contract v1.2). Each is red on the round-1 candidate
(`.p475-material/candidate.diff`) and green on the fixed one; the header of each says which clause it reproduces."""
import json
import re
import shutil
from types import SimpleNamespace

import pytest

from . import helpers as H
from .fakes import ARMS, OPERATOR_EMAIL, PICK, leg_name, strict_row

STARTED = ("stack", "start_router", "load", "spawn", "start_watch")
INSTRUMENT = ("bench/run_capacity.py", "bench/capacity_ladder.py", "bench/kv_line.py", "bench/data/p475_decode_carrier.txt",
              "m1/bench_watch.py")
LEG = leg_name("AF8", 1)


@pytest.fixture
def w(tmp_path, monkeypatch):
    w = H.world(tmp_path, monkeypatch)
    H.ready(w)
    return w


def invalid(w, arm="AF8", **kw):
    rec = H.run_leg(w, arm, **kw)
    assert rec["verdict"] == "INVALID", rec
    assert rec["problems"]
    return rec


def not_started(w, arm="AF8", **kw):
    rec = H.run_leg(w, arm, **kw)
    assert rec["verdict"] == "NOT_STARTED", rec
    assert not [n for n in w.names() if n in STARTED]
    return rec


# ------------------------------------------------------------------------------------------- Sol P1: the instrument files
@pytest.mark.parametrize("rel", INSTRUMENT)
def test_an_arm_instrument_file_that_differs_from_the_orchestrators_refuses(w, rel):
    # class: reproduces a failure the contract fixes (v1.2 Sol P1; red on round-1: the leg ran the arm's stale instrument)
    (w.wt("AF8") / "benchmark" / rel).write_text("# an older instrument\n")
    not_started(w)


@pytest.mark.parametrize("rel", INSTRUMENT)
def test_an_instrument_file_missing_in_the_arm_worktree_refuses(w, rel):
    # class: reproduces a failure the contract fixes (v1.2 Sol P1)
    (w.wt("AF8") / "benchmark" / rel).unlink()
    not_started(w)


def test_an_instrument_file_missing_in_the_orchestrator_checkout_refuses(w):
    # class: reproduces a failure the contract fixes (v1.2 Sol P1: a file absent on either side refuses)
    (w.main / "benchmark" / INSTRUMENT[0]).unlink()
    not_started(w)


def test_identical_instrument_files_start_the_leg(w):
    # class: preserves an invariant
    assert H.run_leg(w, "AF8")["verdict"] == "VALID"


# ------------------------------------------------------------------------------------------- Sol P2: N16 keeps the scheme line
def test_the_n16_arm_as_v1_2_defines_it_is_valid_end_to_end(w):
    # class: reproduces a failure the contract fixes (v1.2 Sol P2; red on round-1: its N16 expects the scheme line removed)
    assert w.arm_registry("N16").count("kv_quant_scheme: turboquant") == 1 and "kv_bits: 0" in w.arm_registry("N16")
    assert H.run_leg(w, "N16")["verdict"] == "VALID"


# ------------------------------------------------------------------------------------------- Sol P4: peak memory / decode rate
@pytest.mark.parametrize("key", ["peak_memory_gb_cumulative", "predicted_per_second"])
@pytest.mark.parametrize("bad", [None, 0, 0.0, -1.5, "n/a"], ids=["none", "zero", "zerof", "negative", "string"])
def test_a_rung_without_a_finite_positive_peak_or_decode_rate_makes_the_leg_invalid(w, key, bad):
    # class: reproduces a failure the contract fixes (v1.2 Sol P4; red on round-1: the leg was VALID with no memory number)
    w.row_mutate = lambda r, i, a, n: dict(r, **{key: bad}) if i == 1 else r
    invalid(w, "AF8")


@pytest.mark.parametrize("key", ["peak_memory_gb_cumulative", "predicted_per_second"])
def test_an_absent_peak_or_decode_rate_makes_the_leg_invalid(w, key):
    # class: reproduces a failure the contract fixes (v1.2 Sol P4)
    w.row_mutate = lambda r, i, a, n: {k: v for k, v in r.items() if k != key}
    invalid(w, "AF8")


def test_an_off_arm_without_a_peak_is_invalid_too(w):
    # class: reproduces a failure the contract fixes (v1.2 Sol P4: both predictor states)
    w.row_mutate = lambda r, i, a, n: dict(r, peak_memory_gb_cumulative=None)
    invalid(w, "TQ4-OFF")


# ------------------------------------------------------------------------------------------- Sol P5 / TW F3: process groups
def test_a_driver_child_left_after_a_normal_exit_is_signalled_and_the_group_emptied(w):
    # class: reproduces a failure the contract fixes (v1.2 Sol P5, TW F3; red on round-1: nothing signalled a group after a clean exit)
    w.driver_child = True
    rec = H.run_leg(w, "AF8")
    sim = w.drivers[0]
    assert sim.signals == ["SIGTERM"], "signalled while a member lives, also after the leader exited normally"
    assert not w.group_members.get(sim.pid)
    assert rec["verdict"] == "VALID", rec
    n = w.names()
    assert n.index("signal_group") < n.index("stop_watch") < n.index("stop_stack")


def test_a_child_that_ignores_sigterm_is_escalated_to_sigkill(w):
    # class: reproduces a failure the contract fixes (v1.2 Sol P5: escalated)
    w.driver_child, w.child_ignores_term = True, True
    rec = H.run_leg(w, "AF8")
    assert w.drivers[0].signals == ["SIGTERM", "SIGKILL"]
    assert rec["verdict"] == "VALID"


def test_a_child_that_survives_sigkill_makes_the_leg_invalid(w):
    # class: reproduces a failure the contract fixes (v1.2 Sol P5: verified empty or INVALID)
    w.driver_child, w.child_unkillable = True, True
    invalid(w, "AF8")
    assert "SIGKILL" in w.drivers[0].signals and "stop_stack" in w.names()


def test_an_empty_group_after_a_normal_exit_is_not_signalled(w):
    # class: preserves an invariant (nothing alive: no signal)
    H.run_leg(w, "AF8")
    assert w.drivers[0].signals == []


def test_an_unreadable_group_state_makes_the_leg_invalid(w):
    # class: reproduces a failure the contract fixes (v1.2 Sol P5: unprovable emptiness fails closed)
    w.group_raises = True
    invalid(w, "AF8")


def test_a_router_group_member_that_survives_the_stop_makes_the_leg_invalid(w):
    # class: reproduces a failure the contract fixes (v1.2 Sol P5: the router's process group verified empty)
    w.router_group_extra = True
    w.survivors = ("router_group",)
    invalid(w, "AF8")


def test_a_router_group_that_empties_with_the_stop_is_valid(w):
    # class: preserves an invariant
    w.router_group_extra = True
    assert H.run_leg(w, "AF8")["verdict"] == "VALID"


# ------------------------------------------------------------------------------------------- Sol P6: e-mail / operator gate
def _run_with_row_note(w, arm, note):
    w.row_mutate = lambda r, i, a, n: dict(r, note=note) if i == 0 else r
    try:
        return H.run_leg(w, arm)
    except Exception:           # noqa: BLE001 — a refused harvest may raise or return; nothing may be final either way
        return None


def test_a_foreign_email_address_in_a_dossier_file_refuses_the_harvest(w):
    # class: reproduces a failure the contract fixes (v1.2 Sol P6; red on round-1: e-mail addresses were not checked)
    _run_with_row_note(w, "AF8", "contact jane.doe@acme-corp.io for details")
    assert not H.dossier(w, LEG).exists()
    assert H.receipt_path(w, LEG).exists()


def test_a_reserved_example_address_is_allowed(w):
    # class: preserves an invariant (RFC 2606 names carry no person)
    _run_with_row_note(w, "AF8", "see someone@example.org")
    assert H.dossier(w, LEG).is_dir()


def test_the_operators_own_address_in_a_dossier_file_refuses(w):
    # class: reproduces a failure the contract fixes (v1.2 Sol P6)
    _run_with_row_note(w, "AF8", f"by {OPERATOR_EMAIL}")
    assert not H.dossier(w, LEG).exists()


def test_the_operators_address_in_an_evidence_log_refuses(w):
    # class: reproduces a failure the contract fixes (v1.2 Sol P6: evidence logs are gated as P426 gates them)
    w.worker_log_extra = f"2026-11-04 INFO user {OPERATOR_EMAIL} logged in"
    try:
        H.run_leg(w, "AF8")
    except Exception:           # noqa: BLE001
        pass
    assert not H.dossier(w, LEG).exists()


def test_a_refused_email_harvest_does_not_start_the_idle_clock(w):
    # class: reproduces a failure the contract fixes (R8 with Sol P6)
    before = (w.wd / "p475" / "LAST_LEG_END").read_text()
    _run_with_row_note(w, "AF8", "jane.doe@acme-corp.io")
    assert (w.wd / "p475" / "LAST_LEG_END").read_text() == before


# ------------------------------------------------------------------------------------------- TW F2: evidence-stage is a destination
def test_an_existing_evidence_stage_directory_refuses_the_leg(w):
    # class: reproduces a failure the contract fixes (v1.2 TW F2; red on round-1: the leg ran and overwrote it)
    (w.wd / "p475" / "evidence-stage" / LEG).mkdir(parents=True)
    not_started(w)


def test_a_replayed_harvest_never_overwrites_differing_evidence(w):
    # class: reproduces a failure the contract fixes (v1.2 TW F2: never overwritten; red on round-1: the replay rewrote it)
    w.row_mutate = lambda r, i, a, n: dict(r, note="/Users/jdoe/project/x.py") if (i == 0 and a == "N16") else r   # allow-pii-pattern
    try:
        H.run_leg(w, "N16", smoke=True)
    except Exception:           # noqa: BLE001
        pass
    smoke = "u4-n16-smoke.a1"
    assert not H.dossier(w, smoke).exists()
    ev = w.wd / "p475" / "evidence-stage" / smoke
    ev.mkdir(parents=True)
    (ev / "planted.txt").write_text("another operator's evidence")
    out = w.wd / "p475/legs" / smoke / "capacity" / f"capacity_ladder.p475-{smoke}.jsonl"   # C297: the leg dir, not the worktree
    out.write_text(json.dumps(strict_row("N16", 8192, prefix=f"p475-{smoke}")) + "\n")
    w.row_mutate = None
    assert H.run_all(w, smoke=True) != 0
    assert [p.name for p in ev.iterdir()] == ["planted.txt"]
    assert not H.dossier(w, smoke).exists()


# ------------------------------------------------------------------------------------------- TW F1: INVALID smoke is terminal
def test_an_invalid_tq4_smoke_stops_the_run_and_a_resume_stops_again(w):
    # class: reproduces a failure the contract fixes (v1.2 TW F1 on the TQ4 smoke leg)
    w.row_mutate = lambda r, i, a, n: dict(r, finish_reason="stop") if a == "TQ4" else r
    assert H.run_all(w, smoke=True) != 0
    rcs = H.receipts(w)
    assert rcs["u4-n16-smoke.a1"]["verdict"] == "VALID" and rcs["u4-tq4-smoke.a1"]["verdict"] == "INVALID"
    n = len(w.stacks)
    w.row_mutate = None
    assert H.run_all(w, smoke=True) != 0
    assert len(w.stacks) == n, "a resume stops at a standing INVALID leg; it does not supersede it"


def test_an_invalid_n16_smoke_stops_the_run_before_tq4(w):
    # class: reproduces a failure the contract fixes (v1.2: INVALID, smoke legs included, stops the run)
    w.row_mutate = lambda r, i, a, n: dict(r, finish_reason="stop") if a == "N16" else r
    assert H.run_all(w, smoke=True) != 0
    assert [s.arm for s in w.stacks] == ["N16"]


# ------------------------------------------------------------------------------------------- TW F6: unresolved instability
def test_an_unresolved_instability_exits_nonzero_and_is_labelled(w):
    # class: reproduces a failure the contract fixes (v1.2 TW F6; red on round-1: exit 0 with the flag undecided)
    w.metric_override = {("AF8", 1): {"dts": 39.9}, ("AF8", 2): {"dts": 42.1}}
    assert H.run_all(w, max_deciding=0) != 0
    assert not [n for n in H.receipts(w) if n.endswith("-b3.a1") or "-b3." in n], "no deciding block ran under a zero cap"
    t =(H.matrix_path(w)).read_text() if H.matrix_path(w).exists() else H.matrix_path(w, partial=True).read_text()
    assert re.search(r"UNRESOLVED", t), "the table labels a flag the deciding block never settled"


def test_a_flag_settled_by_the_deciding_block_exits_zero_unlabelled(w):
    # class: preserves an invariant
    w.metric_override = {("AF8", 1): {"dts": 39.9}, ("AF8", 2): {"dts": 42.1}}
    assert H.run_all(w) == 0
    assert "UNRESOLVED" not in H.matrix_path(w).read_text()


# ------------------------------------------------------------------------------------------- Sol P7: the block plan
def _interrupt_after_leg_two(w):
    seen = {"n": 0}

    def hook(s):
        seen["n"] += 1
        if seen["n"] == 2:
            raise KeyboardInterrupt
    w.sleep_hook = hook
    with pytest.raises(KeyboardInterrupt):
        H.run_all(w)
    w.sleep_hook = None


@pytest.mark.parametrize("blocks", [1, 3])
def test_a_changed_blocks_option_after_a_leg_exists_refuses(w, blocks):
    # class: reproduces a failure the contract fixes (v1.2 Sol P7; red on round-1: a RAISED --blocks was accepted)
    _interrupt_after_leg_two(w)
    n = len(w.stacks)
    assert H.run_all(w, blocks=blocks) == 2
    assert len(w.stacks) == n


def test_the_same_blocks_option_resumes(w):
    # class: preserves an invariant
    _interrupt_after_leg_two(w)
    assert H.run_all(w, blocks=2) == 0


# ------------------------------------------------------------------------------------------- Sol P3: arm re-committed mid-run
def test_an_arm_recommitted_after_its_first_leg_is_refused_for_its_later_legs(w):
    # class: reproduces a failure the contract fixes (v1.2 Sol P3; red on round-1: the arm's second leg ran on a different commit)
    seen = {"n": 0}

    def hook(s):
        seen["n"] += 1
        if seen["n"] == 2:                 # after N16 b1 and AF8 b1
            raise KeyboardInterrupt
    w.sleep_hook = hook
    with pytest.raises(KeyboardInterrupt):
        H.run_all(w)
    w.sleep_hook = None
    w.arm_commit["AF8"] = "c" * 40         # AF8 is re-committed (HEAD and branch agree, parent still the base: R1 alone passes)
    w.arm_head["AF8"] = "c" * 40
    assert H.run_all(w) != 0                # the same caps as the first invocation (a resume may not lower them)
    assert not [n for n in H.receipts(w) if n.startswith("u4-af8-b2") and H.read_receipt(w, n)["verdict"] == "VALID"]


# ------------------------------------------------------------------------------------------- finished-run fixtures (P3, P8)
@pytest.fixture(scope="module")
def finished(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("v12clean")
    with pytest.MonkeyPatch.context() as mp:
        w = H.world(tmp, mp)
        H.ready(w)
        rc = H.run_all(w)
        return SimpleNamespace(wd=w.wd, main=w.main, t=w.t, rc=rc)


@pytest.fixture
def cw(finished, tmp_path, monkeypatch):
    return H.clone(finished, tmp_path, monkeypatch)


def _partial(w):
    rc = H.matrix_rc(w)
    assert rc != 0
    return rc


def _edit_receipt(d, mutate):
    p = d / "receipt.json"
    doc = json.loads(p.read_text())
    mutate(doc)
    p.write_text(json.dumps(doc))
    H.resign(d)


def test_the_clean_finished_run_is_complete(finished):
    # class: preserves an invariant
    assert finished.rc == 0


@pytest.mark.parametrize("name,mutate", [
    ("model", lambda d: d.update(model="Some-Other-Model")),
    ("base", lambda d: d.update(base="c" * 40)),
    ("arm", lambda d: d.update(arm="AF8")),
    ("attempt", lambda d: d.update(attempt=7)),
    ("leg", lambda d: d.update(leg="u4-tq4-b2.a1")),
    ("gitlinks", lambda d: d["identity_entry"].update(gitlinks={"src/mlx-vlm": "0" * 40, "src/mlx-serve": "0" * 40})),
    ("arm_commit", lambda d: d["identity_entry"].update(arm_commit="d" * 40)),
])
def test_a_dossier_not_bound_to_this_run_is_not_counted(cw, name, mutate):
    # class: reproduces a failure the contract fixes (v1.2 Sol P3; red on round-1: any self-consistent dossier was accepted)
    _edit_receipt(H.dossier(cw, "u4-tq4-b1.a1"), mutate)
    H.matrix_path(cw).unlink()
    _partial(cw)
    assert H.matrix_path(cw, partial=True).is_file() and not H.matrix_path(cw).exists()


def test_a_second_usable_dossier_for_one_slot_refuses_both(cw):
    # class: reproduces a failure the contract fixes (v1.2 Sol P3; red on round-1: the later dossier silently replaced the first)
    src = H.dossier(cw, "u4-tq4-b1.a1")
    dup = src.with_name("u4-tq4-b1.a2")
    shutil.copytree(src, dup)
    for p in dup.glob("capacity_ladder.*.jsonl"):
        p.write_text(p.read_text().replace("b1.a1", "b1.a2"))          # the rungs' session ids carry the leg's own tag
        p.rename(p.with_name(p.name.replace("b1.a1", "b1.a2")))
    _edit_receipt(dup, lambda d: d.update(leg="u4-tq4-b1.a2", attempt=2))
    man = json.loads((dup / "SCRUB_MANIFEST.json").read_text())
    man["files"] = {k.replace("b1.a1", "b1.a2"): v for k, v in man["files"].items()}
    (dup / "SCRUB_MANIFEST.json").write_text(json.dumps(man))
    H.resign(dup)
    H.matrix_path(cw).unlink()
    _partial(cw)


# ------------------------------------------------------------------------------------------- P651 / C293: the watcher's rows file
def test_the_receipt_records_the_watcher_argv_with_the_legs_own_rows_file(w):
    # class: exercises new behaviour (P651: the watcher's `--capacity-rows` recorded; red on round-1 by reading its `run_leg`: the
    # receipt held only the watcher's verdict, never its argv. A MISMATCH cannot be produced through the Ops interface -- the code
    # builds the argv itself -- so the speed-problem branch is checked by the implementer's own monkeypatch tests only)
    assert H.run_leg(w, "AF8")["verdict"] == "VALID"
    text = H.receipt_path(w, LEG).read_text()
    rows = f"capacity_ladder.p475-{LEG}.jsonl"
    argv = w.watches[0]["argv"]
    assert argv[argv.index("--capacity-rows") + 1].endswith(rows)
    assert "--capacity-rows" in text and text.count(rows) >= 2, "recorded beside the receipt's own rows path"


# ------------------------------------------------------------------------------------------- Sol P8: exactly one table
def test_a_complete_table_is_replaced_by_the_partial_one_on_regeneration(cw):
    # class: reproduces a failure the contract fixes (v1.2 Sol P8; red on round-1: the stale canonical table survived)
    assert H.matrix_path(cw).exists()
    shutil.rmtree(H.dossier(cw, "u4-tq8-b2.a1"))
    _partial(cw)
    assert H.matrix_path(cw, partial=True).is_file()
    assert not H.matrix_path(cw).exists(), "exactly one of the two tables exists after any regeneration"


def test_a_partial_table_is_replaced_by_the_complete_one_on_regeneration(cw):
    # class: reproduces a failure the contract fixes (v1.2 Sol P8)
    held = H.dossier(cw, "u4-tq8-b2.a1")
    stash = held.with_name("stash-tq8")
    held.rename(stash)
    H.matrix_path(cw).unlink()
    _partial(cw)
    assert H.matrix_path(cw, partial=True).is_file()
    stash.rename(held)
    assert H.matrix_rc(cw) == 0
    assert H.matrix_path(cw).is_file() and not H.matrix_path(cw, partial=True).exists()
