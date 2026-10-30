"""P426 B2 frozen tests, delivery 2d: one failing case per finding the s1-s5 fix pass reports fixed (C239,
`.b2-fix-report.md`).

Class: every test here is [FIX] (reproduces a failure the specification fixes): it fails on the s1-s5 candidates as
reviewed (parts a, b, c) and passes once the finding is fixed. Hermetic: the frozen P426 world (`b2_frozen_fix_support`),
the reconcile / receipt fixtures of `b2_frozen_support`; no network, GPU, model, server or real opencode.
Findings without a test here (R6, R7, P18, P32) are listed in the delivery report with the reason."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bench.tests import b2_frozen_add_support as A
from bench.tests import b2_frozen_fix_support as F
from bench.tests import b2_frozen_support as S
from bench.tests import test_b2_frozen_s4_reconcile as T4


def REC():
    from bench import p426_receipt
    return p426_receipt


def R4():
    from bench import p426_reconcile
    return p426_reconcile


# ------------------------------------------------------------------------------------------------ s1-s3 review
def test_fix_r2_a_frozen_record_whose_seal_does_not_verify_refuses_at_entry(tmp_path, monkeypatch):
    """§16.1: `--frozen-record` is read once at entry; a bad self-hash refuses before the router (R2: it was never read)."""
    def tamper(env):
        p = env["records"]["v8"]
        doc = json.loads(p.read_text())
        doc["settle_bound_s"] = 1.0                       # changed after sealing
        p.write_text(json.dumps(doc))
    rc, env = F.leg(tmp_path, monkeypatch, adjust=tamper)
    assert rc == 2 and not env["ops"].names("start_router")
    assert any("REFUSED: " in ln and "--frozen-record" in ln for ln in env["lines"]), env["lines"][-10:]


def test_fix_r3_the_dnf_limit_counts_the_whole_leg_across_languages(tmp_path, monkeypatch):
    """§5.1: more than two DNF in the LEG is systemic — two Python DNF and one Go DNF in one s1 leg stop it (R3: the limit
    was counted per (session, language, arm), so this leg ran on)."""
    aborts = {"p1": "boundary", "p2": "boundary", "g1": "boundary"}
    rc, env = F.leg(tmp_path, monkeypatch, mode=("chain", "s1"), probe_env={"B2_ABORTS": json.dumps(aborts)})
    assert rc == 2, F.text(env)[-2000:]
    assert len(F.chain_json(env).get("p426_dnf") or []) == 2                     # the third is not a DNF: it is systemic


def test_fix_r4_a_router_replaced_with_the_same_config_after_load_is_systemic(tmp_path, monkeypatch):
    """§3 / §16.7: owned identities are `(pid, ChainOps.create_time(pid))`; a router restarted on the same pid with the same
    config is another process (R4: the check compared the config sha)."""
    def replace_router_after_load(env):
        ops = env["ops"]
        loader, create_time = ops.load, ops.create_time
        state = {"replaced": False}

        def load(model):
            ident = loader(model)
            state["replaced"] = True                      # the router (pid 1) restarts while the worker loads
            return ident
        ops.load = load
        ops.create_time = lambda pid: 2.0 if (pid == 1 and state["replaced"]) else create_time(pid)
    rc, env = F.leg(tmp_path, monkeypatch, adjust=replace_router_after_load)
    assert rc == 2 and env["ops"].names("load") and not F.started_any(env)


def test_fix_r5_predictor_mtp_reads_the_served_registry_ops_overlay(tmp_path, monkeypatch):
    """§3: `ChainOps.overlay` IS the served registry; `--predictor mtp` asserts ITS entry (R5: the repo's file was read)."""
    env = S.chain_env(tmp_path, monkeypatch, registry=S.registry_text((S.MODEL, S.MODEL2), on=(S.MODEL,)), out="m63")
    env["ops"].extra_env["FAKE_SERVED_REGISTRY"] = env["ops"].overlay
    try:
        assert S.run_chain(env, ["pilot", "--models", S.MODEL, "--predictor", "mtp"]) == 0
    finally:
        env["ops"].cancel()


@pytest.mark.parametrize("drop", ["--models", "--out-root"])
def test_fix_an_argparse_refusal_prints_one_refused_line_naming_the_flag(tmp_path, monkeypatch, drop):
    """§16: every refusal prints one `REFUSED: <reason>` line naming the offending flag and exits 2 (argparse's own
    `error:` lines did not)."""
    env = S.p426_world(tmp_path, monkeypatch)
    argv = S.p426_argv(env)[0]
    i = argv.index(drop)
    del argv[i:i + 2]
    try:
        rc, out = S.main_refusal(argv, env["ops"], campaign=S.fake_campaign(env["commit"]))
    finally:
        env["ops"].cancel()
    refused = [ln for ln in out.splitlines() if ln.startswith("REFUSED: ")]
    assert rc == 2 and len(refused) == 1 and drop in refused[0], out[-1500:]


def test_fix_inject_without_rehearsal_refuses_naming_inject(tmp_path, monkeypatch):
    env = S.p426_world(tmp_path, monkeypatch)
    argv = S.p426_argv(env, ("chain", "s1"))[0] + ["--inject", "stall-kill"]
    try:
        rc, out = S.main_refusal(argv, env["ops"], campaign=S.fake_campaign(env["commit"]))
    finally:
        env["ops"].cancel()
    assert rc == 2 and any(ln.startswith("REFUSED: ") and "--inject" in ln for ln in out.splitlines())
    assert "unrecognized arguments" not in out                                  # the flag exists (it was unknown)


def test_fix_a_rehearsal_leg_is_parsed(tmp_path, monkeypatch):
    """§1 / §16.1: `--rehearsal` exists (it was an unrecognized argument)."""
    env = S.p426_world(tmp_path, monkeypatch, rehearsal=True)
    argv = S.p426_argv(env, ("chain", "s1", "--rehearsal"))[0]
    try:
        rc = S.run_p426(env, argv)
    finally:
        env["ops"].cancel()
    assert not any("unrecognized arguments" in ln for ln in env["lines"]), env["lines"][-10:]
    assert rc == 0, F.text(env)[-1500:]


def test_fix_the_generic_prediction_is_recorded_in_chain_json(tmp_path, monkeypatch):
    env = S.chain_env(tmp_path, monkeypatch)
    try:
        assert S.run_chain(env, ["pilot", "--models", S.MODEL]) == 0
        assert 250 in list(_find(S.chain_json(env), "generic_pred_s"))
    finally:
        env["ops"].cancel()


def _find(doc, key):
    if isinstance(doc, dict):
        if key in doc:
            yield doc[key]
        for v in doc.values():
            yield from _find(v, key)
    elif isinstance(doc, list):
        for v in doc:
            yield from _find(v, key)


def test_fix_p426_invalid_is_a_list_of_records(tmp_path, monkeypatch):
    """§16.5: `p426_invalid` is list-shaped like the ledger (it was one dict)."""
    skew = S.p426_order([f"p{i}" for i in range(1, 7)], 1001)[2]
    rc, env = F.leg(tmp_path, monkeypatch, probe_env={"B2_SKEW_ITEMS": skew})
    inv = F.chain_json(env).get("p426_invalid")
    assert rc == 2 and isinstance(inv, list) and len(inv) == 1 and inv[0]["stage"] == "done" and skew in json.dumps(inv)


# ------------------------------------------------------------------------------------------------ s4 review
def test_fix_p16_a_normal_row_whose_termination_has_kill_key_names_is_not_a_kill():
    """§4.3: the outcome comes from the structured fields; the real row's `termination` has the KEYS `killed` and
    `in_flight_at_kill` (empty / null) on every row (P16: a substring search made every row a kill)."""
    r = T4.row()
    assert set(r["termination"]) >= {"killed", "in_flight_at_kill"} and not r["termination"]["killed"]
    rep = R4().reconcile_item(r, T4.lines_of(S.item_window(T4.SESSION, T4.USAGE)), T4.BEFORE, T4.after())
    assert rep.ok is True and rep.case == "completed"


def test_fix_p16_a_failed_line_on_a_normally_completed_item_is_a_problem():
    lines = S.item_window(T4.SESSION, T4.USAGE) + [S.started_line(), S.failed_line()]
    rep = T4.outcome(R4().reconcile_item, T4.row(), T4.lines_of(lines), T4.BEFORE, T4.after(failed=1))
    assert T4.not_ok(rep)


@pytest.mark.parametrize("in_flight,case", [(None, "dnf_boundary"), ("msg_c", "dnf_inflight_failed")])
def test_fix_p17_a_dnf_reconciles_against_the_abort_manifest_the_probe_writes(in_flight, case):
    """§16.1: `transport_abort.gate.request_usage`, `.session_id`, `.in_flight.message_id` (P17: the top-level keys were
    read, so every DNF window failed `boundary_count`)."""
    m = S.abort_manifest(T4.USAGE[:2], in_flight=in_flight)
    assert "gate" not in m and m["transport_abort"]["gate"]["request_usage"]
    lines = S.item_window(T4.D_SESSION, T4.USAGE[:2]) + ([S.started_line(), S.failed_line()] if in_flight else [])
    rep = R4().reconcile_dnf(m, T4.lines_of(lines), T4.BEFORE, T4.after(T4.USAGE[:2], failed=1 if in_flight else 0))
    assert rep.ok is True and rep.case == case, rep.problems


def test_fix_p19_an_a4_window_that_differs_from_gate_json_stops_the_leg_before_item_one(tmp_path, monkeypatch):
    """§3 / §4.3: per load, before the first item, the A4 window equals the A4 run's `gate.json` (P19: never checked)."""
    def drift_gate(env):
        ops = env["ops"]
        gate = ops.a4_gate

        def a4_gate(model, tag, **kw):
            path = gate(model, tag, **kw)
            g = Path(env["wd"]) / S.GATE_JSON
            doc = json.loads(g.read_text())
            doc["A6_bare_anonymous"]["requests"][0]["prompt"] += 1
            g.write_text(json.dumps(doc))
            return path
        ops.a4_gate = a4_gate
    rc, env = F.leg(tmp_path, monkeypatch, adjust=drift_gate)
    assert rc == 2 and env["ops"].names("load") and not F.started_any(env)


def test_fix_p21_p22_an_invalidated_done_writes_its_item_record_with_the_ready_files_sha256(tmp_path, monkeypatch):
    """§4.5: the item record is written before the barrier answer on every `done`, an `invalidate` included (P21: an
    identity failure returned without a record). post-reveal 3h (§16.8 after the strict verify round 1): `ready_sha256` is
    the ready record's SELF-HASH (it was the ready file's sha256, P22); the test name is kept for the finding id."""
    from bench import chain_rows as cr
    h, env, slot, ctx, run_item = T4.hooks(tmp_path, monkeypatch)
    try:
        assert h.before_attempt(slot, ctx("ready")).kind == "accept"
        rp = Path(env["out"]) / "items" / (cr.slot_file(slot) + ".ready.json")
        ready = json.loads(rp.read_text())
        r = run_item()
        env["state"]["worker_shift"] = 1                  # the owned worker is replaced before `done`
        done = dict(id="python/p1", attempt_id="python/p1#1.0", passed=True, nonconv_kind=None, evidence={}, receipts=None,
                    final_tree=None)
        d = h.after_attempt(slot, done, ctx("done", ready=ready, row_=r))
        assert d.kind == "invalidate"
        doc = json.loads((Path(env["out"]) / "items" / (cr.slot_file(slot) + ".json")).read_text())
        assert doc["verdict"] == "invalid" and doc["ready_sha256"] == S.self_hashed(json.loads(rp.read_text()))["sha256"]
    finally:
        env["ops"].cancel()


def test_fix_p23_a_dnf_records_its_item_record_as_the_path_string(tmp_path, monkeypatch):
    """§16.1: the `p426_dnf` record's `item_record` names `items/<slot_file>.dnf.json` (P23: a dict {path, sha256})."""
    first = S.p426_order([f"p{i}" for i in range(1, 7)], 1001)[1]
    rc, env = F.leg(tmp_path, monkeypatch, probe_env={"B2_ABORTS": json.dumps({first: "boundary"})})
    assert rc == 0, F.text(env)[-2000:]
    (d,) = F.chain_json(env)["p426_dnf"]
    assert isinstance(d["item_record"], str) and d["item_record"].startswith("items/") and d["item_record"].endswith(".dnf.json")


def test_fix_p24_log_bounds_are_portable_and_finalized_when_the_teardown_raises(tmp_path, monkeypatch):
    """§4.2 / §16.7: `log_bounds.json` paths are `<WT>/logs/…` (P24: absolute) and it is finalized after teardown even when
    `stop_stack` raises (P24: the finalization was skipped)."""
    def failing_teardown(env):
        ops = env["ops"]
        stop = ops.stop_stack

        def stop_stack(*a, **kw):
            stop(*a, **kw)
            raise RuntimeError("teardown failed")
        ops.stop_stack = stop_stack
    try:
        F.leg(tmp_path, monkeypatch, adjust=failing_teardown)
    except RuntimeError:
        pass
    doc = json.loads((tmp_path / "p426/wave2/tg1-p426-off-pilot.a1/log_bounds.json").read_text())
    assert doc["finalized"] and all(f["path"].startswith("<WT>/logs/") for f in doc["files"])
    assert str(tmp_path) not in json.dumps(doc)


def test_fix_p25_hooks_without_a_context_raise_hook_infrastructure_error(tmp_path, monkeypatch):
    from bench import chain_hooks as ch
    h, env, slot, ctx, run_item = T4.hooks(tmp_path, monkeypatch)
    try:
        with pytest.raises(ch.HookInfrastructureError):
            h.before_attempt(slot)
    finally:
        env["ops"].cancel()


def test_fix_p26_log_field_values_stay_strings_as_logged():
    (ln,) = R4().parse_log(S.window([S.completed_line(session=T4.SESSION, prompt_tokens=99, generated_tokens=7)]))
    assert (ln.fields["prompt_tokens"], ln.fields["generated_tokens"]) == ("99", "7")


def test_fix_p27_a_passing_pairing_check_names_no_failure():
    rep = R4().reconcile_item(T4.row(), T4.lines_of(S.item_window(T4.SESSION, T4.USAGE)), T4.BEFORE, T4.after())
    assert rep.checks["pairing"]["ok"] is True and "fail" not in rep.checks["pairing"]["detail"]


# ------------------------------------------------------------------------------------------------ s5 review
def test_fix_p29_a_missing_seam_is_systemic_never_a_skip(tmp_path, monkeypatch):
    """§16.7: a missing check seam is systemic (P29: every s5 check was skipped and the leg ran VALID)."""
    def remove(env):
        monkeypatch.delattr(env["ops"], "loaded_images")
    rc, env = F.leg(tmp_path, monkeypatch, adjust=remove)
    assert rc == 2 and not F.started_any(env) and "loaded_images" in F.text(env)


def test_fix_p31_a_worktree_that_turns_dirty_between_invocations_stops_the_next_one(tmp_path, monkeypatch):
    """§3 'Before every invocation': the entry checks hold for the life of the leg — a worktree that is dirty before the Go
    invocation stops the leg before it starts (P31: only the census and the snapshots were re-checked)."""
    # post-reveal (3b): the worktree turns dirty only once the first invocation's last item has continued (its probe is done);
    # flipped at the first invocation's start it was caught by the Item `ready` row (§3, s7) before any item ran — correct, but
    # not the between-invocations case this test is for
    def dirty_after_first_invocation(env):
        ops, state = env["ops"], env["state"]
        base = ops.worktree_state
        out = Path(env["out"])

        def worktree_state(*a):
            if any(out.rglob("*opencode_python*.item4.continue")):
                state["clean"] = False
            return base(*a)
        ops.worktree_state = worktree_state
    rc, env = F.leg(tmp_path, monkeypatch, mode=("chain", "s1"), adjust=dirty_after_first_invocation)
    assert F.python_invocation_started(env), F.text(env)[-1500:]          # the leg ran up to the Go invocation
    assert rc == 2 and not F.go_invocation_started(env), F.text(env)[-1500:]


def test_fix_p31_a_frozen_record_changed_between_invocations_stops_the_next_one(tmp_path, monkeypatch):
    def tamper_after_first_invocation(env):
        ops = env["ops"]
        base = ops.worktree_state
        marker = Path(ops.state) / "invocations.jsonl"
        am = env["records"]["am"]

        def worktree_state(*a):
            if marker.exists() and marker.read_text().strip():
                doc = json.loads(am.read_text())
                if doc.get("w_go_s") != 1.0:
                    doc["w_go_s"] = 1.0                   # the record changes after sealing
                    am.write_text(json.dumps(doc))
            return base(*a)
        ops.worktree_state = worktree_state
    rc, env = F.leg(tmp_path, monkeypatch, mode=("chain", "s1"), adjust=tamper_after_first_invocation)
    assert F.python_invocation_started(env), F.text(env)[-1500:]          # the leg ran up to the Go invocation
    assert rc == 2 and not F.go_invocation_started(env), F.text(env)[-1500:]


@pytest.mark.parametrize("prefix", [["/usr/bin/arch", "-arm64"], ["/usr/bin/env"]], ids=["arch", "env"])
def test_fix_p33_a_worker_argv_with_extra_leading_tokens_is_systemic(tmp_path, monkeypatch, prefix):
    """§6.3 / §16.7: exact (P33: up to two leading tokens were tolerated)."""
    def prefixed(env):
        ops = env["ops"]
        base = ops.proc_argv
        ops.proc_argv = lambda pid: prefix + base(pid) if ops.ident and pid == ops.ident["pid"] else base(pid)
    rc, env = F.leg(tmp_path, monkeypatch, adjust=prefixed)
    assert rc == 2 and env["ops"].names("load") and not F.started_any(env)


def test_fix_p34_pair_problems_takes_two_receipts_and_write_dossier_the_arm_specs(tmp_path):
    """§16.7: `pair_problems(first, second)`; `write_dossier(path, *, pair, off, on, differences, verdict)` with `receipt` /
    `harvest` paths and `<leg>.a<n>` attempts (P34: keyword lists and positional receipts)."""
    off, on = S.arm_receipt_doc("off"), S.arm_receipt_doc("on")
    assert REC().pair_problems(off, on) == []
    ro = S.write_record(tmp_path / "off.a1/receipt.json", off)
    rn = S.write_record(tmp_path / "on.a1/receipt.json", on)
    ho = S.write_record(tmp_path / "off.a1/HARVEST.json", S.self_hashed({"leg": "tg1-p426-off-pilot", "attempt": 1}))
    hn = S.write_record(tmp_path / "on.a1/HARVEST.json", S.self_hashed({"leg": "tg1-p426-on-pilot", "attempt": 1}))
    doc = REC().write_dossier(tmp_path / "pairs/pilot__off-a1__on-a1.json", pair="pilot",
                              off=dict(attempt="tg1-p426-off-pilot.a1", receipt=ro, harvest=ho),
                              on=dict(attempt="tg1-p426-on-pilot.a1", receipt=rn, harvest=hn), differences=[], verdict="PASS")
    assert doc["arms"]["off"]["receipt_sha256"] == S.sha256_file(ro) and doc["arms"]["on"]["harvest_sha256"] == S.sha256_file(hn)


# ------------------------------------------------------------------------------------------------ 2e: s6 (P510) and P38
@pytest.mark.parametrize("intervals", [[["2026-10-27T00:00:00Z", "2026-10-27T00:01:00Z"]], [[1.0]], ["junk"], [{"from": 1}], "x"],
                         ids=["iso-strings", "short-pair", "not-a-pair", "dict", "not-a-list"])
def test_fix_p510_a_malformed_on_battery_interval_leaves_the_watcher_alive_to_write_its_exit_state(tmp_path, monkeypatch,
                                                                                                  intervals):
    """§8 / §16.1 (P510, queued defect): a malformed or unparseable `on_battery_intervals` never crashes the watcher — it
    still writes its single closing `exit_state` line, and the window is not proven off-battery (the leg is speed-invalid;
    the leg verdict itself is the sequencer's, s8). Pinned format: [[start, end], ...] in epoch seconds."""
    from bench.tests import test_b2_frozen_s6_watch as T6
    rc, lines = T6._watch(tmp_path, monkeypatch, lambda: {"watts": 140, "volts": 28, "battery": 80,
                                                          "on_battery_intervals": intervals})
    assert rc == 0 and "exit_state" in lines[-1] and sum("exit_state" in x for x in lines) == 1
    claimed = {k: v for k, v in lines[-1].items() if "interval" in k and "battery" in k}
    assert all(v != [] for v in claimed.values()), claimed          # never recorded as a proven off-battery window


def test_fix_p38_a_snapshot_that_drifts_after_load_stops_the_leg_before_item_one(tmp_path, monkeypatch):
    """§3 (after load; before every invocation): the snapshots equal the fork pins at entry AND after load — a snapshot that
    changes once the worker has loaded (a hub-cache refresh) stops the leg before item one."""
    def drift_after_load(env):
        ops = env["ops"]
        loader, hashes = ops.load, ops.snapshot_hashes
        state = {"loaded": False}

        def load(model):
            ident = loader(model)
            state["loaded"] = True
            return ident

        def snapshot_hashes(model):
            snaps = hashes(model)
            if state["loaded"]:
                snaps = dict(snaps, target=dict(snaps["target"], revision="0" * 40))
            return snaps
        ops.load, ops.snapshot_hashes = load, snapshot_hashes
    rc, env = F.leg(tmp_path, monkeypatch, adjust=drift_after_load)
    assert rc == 2 and env["ops"].names("load") and not F.started_any(env), F.text(env)[-1500:]


def test_inv_p38_a_legacy_chain_runs_none_of_the_receipt_checks(tmp_path, monkeypatch):
    """[INV] §3 / §16.2: the P426 checks (receipt, pair gate, census, argv, snapshots) run in P426 mode only — a legacy tg1 chain
    runs to completion without calling any of their seams and writes no P426 record."""
    env = S.chain_env(tmp_path, monkeypatch)
    called = []
    for seam in ("proc_argv", "proc_environ", "interpreter_inventory", "loaded_images", "snapshot_hashes",
                 "expected_worker_argv", "busy_procs", "descendants"):
        setattr(env["ops"], seam, (lambda name: lambda *a, **k: called.append(name))(seam))
    try:
        assert S.run_chain(env, ["pilot", "--models", S.MODEL]) == 0
    finally:
        env["ops"].cancel()
    assert called == []
    out = Path(env["out"])
    assert not (out / "receipt.json").exists() and not (out / "log_bounds.json").exists()
    assert not list(out.rglob("items/*.ready.json"))


# ------------------------------------------------------------------------------------------------ 3c: P536 chain-side gaps
def _invs(env):
    """(lang, seed, [items]) of every probe invocation, in launch order (the fake probe's invocations.jsonl)."""
    out = []
    for inv in S.invocations(env):
        a = inv["argv"]
        out.append((a[a.index("--lang") + 1], int(a[a.index("--seed-base") + 1]),
                    [x for x in a[a.index("--items") + 1].split(",") if x]))
    return out


def test_fix_p536_a_makeup_leg_runs_one_invocation_per_group_in_the_canonical_order(tmp_path, monkeypatch):
    """post-reveal 3c (P536): §1 legs 9-10 / §5.5 — `makeup --p426 --occurrences <file>` (the sequencer's canonical file)
    runs one invocation per (session, seed, language) group, s1 then s2, each session in its language order (s1 Python then
    Go, s2 Go then Python), items in their order, under the session's own seed; every occurrence is a ledger slot."""
    env = A.world(tmp_path, monkeypatch, out_name="tg1-p426-off-makeup.a1")
    occ = tmp_path / "occurrences.off.jsonl"
    occs = [S.occurrence("s1", "python", "p2", 1001, "off"), S.occurrence("s1", "go", "g3", 1001, "on"),
            S.occurrence("s2", "go", "g1", 2002, "off"), S.occurrence("s2", "python", "p4", 2002, "on")]
    occ.write_text("".join(json.dumps(o) + "\n" for o in occs))
    argv = S.p426_argv(env, ("makeup", "--occurrences", str(occ)))[0]
    try:
        rc = S.run_p426(env, argv)
    finally:
        env["ops"].cancel()
    assert rc == 0, F.text(env)[-2000:]
    assert _invs(env) == [("python", 1001, ["p2"]), ("go", 1001, ["g3"]), ("go", 2002, ["g1"]), ("python", 2002, ["p4"])]
    assert len(F.chain_json(env).get("p426_ledger") or []) == 4


def test_fix_p536_the_r2_injection_invalidates_the_rehearsal_leg_for_the_reconciliation_mismatch(tmp_path, monkeypatch):
    """post-reveal 3c (P536): §1 R2 — `chain s1 --rehearsal --inject reconcile-mismatch` stops the leg after the injected
    item, INVALID for that reason (one `invalidate` at `done`); without the injection the same leg is VALID (frozen s7)."""
    env = S.p426_world(tmp_path, monkeypatch, rehearsal=True)
    argv = S.p426_argv(env, ("chain", "s1", "--rehearsal", "--inject", "reconcile-mismatch"))[0]
    try:
        rc = S.run_p426(env, argv)
    finally:
        env["ops"].cancel()
    invalid = F.chain_json(env).get("p426_invalid") or []
    assert rc == 2 and len(invalid) == 1 and invalid[0]["stage"] == "done", F.text(env)[-2000:]
    assert invalid[0]["reason"] == "reconciliation mismatch (injected)"             # post-reveal 3d (§16.8): the exact reason
    first = S.p426_order([f"p{i}" for i in range(1, 7)], 1001)[0]                  # the first item of the rehearsal schedule
    assert invalid[0]["slot"].endswith("|" + first)
    assert S.invocations(env), "the leg never reached the probe"
    assert F.chain_json(env).get("inject") == "reconcile-mismatch"      # post-reveal 3h (§16.8): the rehearsal binding


# ------------------------------------------------------------------------------------------------ post-reveal 3d (§16.8)
def test_fix_p536_the_r3_stall_injection_kills_the_first_python_item_and_scores_it(tmp_path, monkeypatch):
    """post-reveal 3d (§16.8): `chain s1 --rehearsal --inject stall-kill` passes `--inject-stall-item <lang>/<item>
    --inject-stall-s 30` to the probe invocation holding the first Python item of the rehearsal schedule (and to no other);
    the probe applies that limit to that item only; the kill is a scored strict fail with its failed-line case recorded and
    the leg is VALID (§1 R3), never a DNF."""
    env = S.p426_world(tmp_path, monkeypatch, rehearsal=True)
    argv = S.p426_argv(env, ("chain", "s1", "--rehearsal", "--inject", "stall-kill"))[0]
    try:
        rc = S.run_p426(env, argv)
    finally:
        env["ops"].cancel()
    first = S.p426_order([f"p{i}" for i in range(1, 7)], 1001)[0]
    invs = S.invocations(env)
    flagged = [i["argv"] for i in invs if "--inject-stall-item" in i["argv"]]
    assert len(flagged) == 1, [i["argv"][-6:] for i in invs]
    a = flagged[0]
    assert a[a.index("--inject-stall-item") + 1] == f"python/{first}" and a[a.index("--inject-stall-s") + 1] == "30"
    assert first in a[a.index("--items") + 1].split(",")
    cj = F.chain_json(env)
    assert rc == 0 and not cj.get("p426_dnf") and not cj.get("p426_invalid"), F.text(env)[-2000:]
    assert cj.get("inject") == "stall-kill"                              # post-reveal 3h (§16.8): the rehearsal binding
    cases = [json.loads(p.read_text()).get("case") for p in Path(env["out"]).rglob("items/*.json")
             if not p.name.endswith((".ready.json", ".dnf.json"))]
    assert sum(1 for c in cases if str(c).startswith("kill_")) == 1


def _topology_pilot(tmp_path, monkeypatch):
    T = F.Topology(tmp_path, monkeypatch)
    T.records()
    rc, err = T.run(T.argv("run", "--through", "tg1-p426-on-pilot"))
    return T, rc, err


def test_fix_p536_topology_the_real_sequencer_runs_the_pilot_pair_through_the_real_chain(tmp_path, monkeypatch):
    """post-reveal 3d (§16.8 / §13): in-process — the real `Sequencer` launches the real `run_tg1_chain.main(argv,
    ops=FakeOps)` on a thread with the fake probe (real argv, locks, records, `chain.json`, `LAST_LEG_END`, watcher contract;
    no router / worker / model): both pilots VALID and speed-valid, the pair dossier PASS, the timeout amendment written."""
    T, rc, err = _topology_pilot(tmp_path, monkeypatch)
    base = tmp_path / "p426/wave2"
    assert rc == 0, (err, "\n".join(T.lines[-30:]))
    assert [Path(A.arg(h.argv, "--out-root")).name for h in T.chains()] == ["tg1-p426-off-pilot.a1", "tg1-p426-on-pilot.a1"]
    for leg in ("tg1-p426-off-pilot.a1", "tg1-p426-on-pilot.a1"):
        rec = json.loads((base / leg / "leg.json").read_text())
        assert rec["state"] == "VALID" and rec["speed_valid"] is True, rec
        watch = [json.loads(x) for x in (base / leg / "watch.jsonl").read_text().splitlines() if x.strip()]
        assert watch and "exit_state" in watch[-1]
        assert (base / leg / "schedule.json").exists() and (base / leg / "receipt.json").exists()
    on = T.chains()[1]
    assert A.arg(on.argv, "--pair-receipt") == str(base / "tg1-p426-off-pilot.a1/receipt.json")
    dossier = json.loads((base / "pairs/pilot__off-a1__on-a1.json").read_text())
    assert dossier["verdict"] == "PASS" and T.dossiers
    assert (tmp_path / "records/amendment.json").exists() and float((tmp_path / "p426/LAST_LEG_END").read_text())
    assert not S.is_flocked(tmp_path / "p426/SEQUENCER.lock") and not S.is_flocked(tmp_path / "p426/LEG.lock")


def test_fix_p536_topology_one_makeup_leg_runs_through_the_real_chain(tmp_path, monkeypatch):
    """post-reveal 3d (§16.8 / §13): after the pilot pair, `makeup --occurrences` launches the real chain's make-up leg (OFF,
    then ON) over the canonical occurrences; the OFF make-up leg is VALID with one ledger slot per occurrence."""
    T, rc, err = _topology_pilot(tmp_path, monkeypatch)
    assert rc == 0, err
    order = S.p426_order([f"p{i}" for i in range(1, 7)], 1001)
    occ = tmp_path / "occ.jsonl"
    occ.write_text("".join(json.dumps(o) + "\n" for o in (S.occurrence("s1", "python", order[1], 1001, "on", 1),
                                                            S.occurrence("s1", "go", "g2", 1001, "off", 0))))
    rc, err = T.run(T.argv("makeup", "--occurrences", str(occ)))
    root = tmp_path / "p426/wave2/tg1-p426-off-makeup.a1"
    assert (root / "leg.json").exists(), (rc, err, "\n".join(T.lines[-30:]))
    rec = json.loads((root / "leg.json").read_text())
    assert rec["state"] == "VALID", rec
    assert len(json.loads((root / "chain.json").read_text())["p426_ledger"]) == 2


def test_fix_p536_topology_a_makeup_leg_that_stops_early_records_its_unrun_occurrences(tmp_path, monkeypatch):
    """post-reveal 3e: §5.5 — a make-up leg that stops early records its unrun occurrences `not_run` in its leg record: the
    first occurrence invalidates at `done` (a server count that differs from the client). post-reveal 3f (§16.8 after
    delivery 3e): `not_run` = no scored ledger row — the invalidated first occurrence AND the never-launched second, in order."""
    T, rc, err = _topology_pilot(tmp_path, monkeypatch)
    assert rc == 0, err
    order = S.p426_order([f"p{i}" for i in range(1, 7)], 1001)
    occ = tmp_path / "occ.jsonl"
    occ.write_text("".join(json.dumps(o) + "\n" for o in (S.occurrence("s1", "python", order[1], 1001, "on", 1),
                                                            S.occurrence("s1", "python", order[3], 1001, "off", 3))))
    T.worlds["off"]["ops"].extra_env["B2_SKEW_ITEMS"] = order[1]             # the first make-up item fails its reconciliation
    rc, err = T.run(T.argv("makeup", "--occurrences", str(occ)))
    root = tmp_path / "p426/wave2/tg1-p426-off-makeup.a1"
    rec = json.loads((root / "leg.json").read_text())
    assert rc == 1 and rec["state"] == "INVALID", (rc, rec)
    assert [(o["session"], o["language"], o["item"], o["seed"]) for o in rec["not_run"]] == [
        ("s1", "python", order[1], 1001), ("s1", "python", order[3], 1001)]
