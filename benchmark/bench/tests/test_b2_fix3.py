"""B2 fix round 3 (the strict change review, round 1 of 3): one failing-first test per judged item.
Hermetic: no router, worker, model, network or GPU."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import p426_hooks as ph
from bench.tests import b2_frozen_add_support as A
from bench.tests import b2_frozen_support as S

PILOT = S.p426_order([f"p{i}" for i in range(1, 7)], 1001)[:5]


def p426_leg(tmp_path, monkeypatch, probe_env=None, *, out_name=None):
    env = A.world(tmp_path, monkeypatch, out_name=out_name)
    env["ops"].extra_env.update(probe_env or {})
    argv, r = S.p426_argv(env, ("pilot",))
    try:
        rc = S.run_p426(env, argv, rfd=r)
    finally:
        env["ops"].cancel()
    cj = Path(env["out"]) / "chain.json"
    return rc, (json.loads(cj.read_text()) if cj.exists() else {}), env


DNF = {"B2_ABORTS": json.dumps({PILOT[1]: "boundary"})}


# ------------------------------------------------------------------------------------------------ 1. p426_dnf load / attempt
def test_1_the_p426_dnf_record_carries_load_and_the_out_roots_attempt_number(tmp_path, monkeypatch):
    rc, cj, env = p426_leg(tmp_path, monkeypatch, DNF, out_name="tg1-p426-off-pilot.a2")
    assert rc == 0, "\n".join(env["lines"][-6:])
    d, = cj["p426_dnf"]
    assert d["attempt"] == 2 and type(d["load"]) is int and d["load"] == 0


# ------------------------------------------------------------------------------------------------ 3. credential keys
@pytest.mark.parametrize("name", ["KV_API_KEY", "TQ_TOKEN", "KV_SECRET", "TQ_KEY_BITS", "KV_AUTH_TOKEN", "KV_KEY_BITS_X"])
def test_3_a_kv_or_tq_name_the_stack_does_not_define_is_a_credential_when_it_matches_the_pattern(name):
    from bench import p426_secrets as ps
    assert ps.is_credential_key(name)


@pytest.mark.parametrize("name", ["KV_KEY_BITS", "KV_KEY_SCHEME", "KV_PREALLOC_TOKENS", "KV_BITS", "TQ_KV_QUANT_MODE", "TQ_FUSED_PREFILL"])
def test_3_the_names_the_stack_defines_are_not_credentials(name):
    from bench import p426_secrets as ps
    assert not ps.is_credential_key(name)
    assert name in ps.STACK_DEFINED_KV_TQ_NAMES


# ------------------------------------------------------------------------------------------------ 12. secrets parsing
def test_12_config_assignments_are_parsed_shell_style_first_token_with_comments():
    from bench import p426_secrets as ps
    text = ('export HF_TOKEN="abcdefghijklmnop1234" # the box token\nAPI_KEY=zzzzzzzzzzzz9999 # trailing\n'
            "OTHER_SECRET='quoted value here'\nPLAIN=1 2 3\n")
    got = ps.parse_assignments(text)
    assert got["HF_TOKEN"] == "abcdefghijklmnop1234" and got["API_KEY"] == "zzzzzzzzzzzz9999"
    assert got["OTHER_SECRET"] == "quoted value here" and got["PLAIN"] == "1"


def test_12_an_unparseable_credential_keyed_line_raises_secrets_error_without_the_value():
    from bench import p426_secrets as ps
    with pytest.raises(ps.SecretsError) as exc:
        ps.parse_assignments('MY_SECRET="unterminated value ZZZsecretvalueZZZ\n')
    assert "ZZZsecretvalueZZZ" not in str(exc.value) and "MY_SECRET" in str(exc.value)
    assert ps.parse_assignments('PLAIN="unterminated\n') == {}                 # not credential-keyed: skipped, never fatal


@pytest.mark.parametrize("text", ['Authorization: Bearer abcdef123456', '{"Authorization": "Bearer abcdef123456"}',
                                  "{'Authorization':'Bearer abcdef123456'}", 'authorization = "Bearer abcdef123456"'])
def test_12_the_bearer_format_matches_the_json_and_quoted_header_forms(text):
    from bench import p426_secrets as ps
    assert [f.kind for f in ps.scan(text)] == ["bearer"]


# ------------------------------------------------------------------------------------------------ harvest items (8, 10, 12)
from bench import p426_harvest as H  # noqa: E402
from bench.tests import test_b2_s9_harvest as T9  # noqa: E402

OPERATOR = "op.erator@corp-mail.example"


def strip_sha(path):
    doc = json.loads(Path(path).read_text())
    doc.pop("sha256", None)
    Path(path).write_text(json.dumps(doc))


@pytest.mark.parametrize("rel, dnf", [("leg.json", False), ("receipt.json", False), ("items/{sf}.ready.json", False),
                                      ("items/{sf}.json", False), ("items/{dsf}.dnf.json", True), ("s1/p426_dnf/{dsf}.json", True)])
def test_8_an_immutable_record_without_its_sha256_fails_the_harvest_like_a_wrong_one(tmp_path, rel, dnf):
    w = T9.World(tmp_path, state="VALID_WITH_DNF" if dnf else "VALID", dnf=dnf)
    path = w.root / rel.format(sf=T9.SLOT_FILE, dsf=f"e__off__{T9.MODEL}__s1__python__zzz")
    strip_sha(path)
    with pytest.raises(H.HarvestError, match=r"sha256") as exc:
        w.harvest(emails=(OPERATOR,))
    assert path.name in str(exc.value)
    T9.nothing_published(w)


def test_8_a_chain_json_dnf_entry_that_differs_from_its_sidecar_fails_the_harvest(tmp_path):
    w = T9.World(tmp_path, state="VALID_WITH_DNF", dnf=True)
    assert w.harvest(emails=(OPERATOR,))["state"] == "VALID_WITH_DNF"
    w2 = T9.World(tmp_path / "b", state="VALID_WITH_DNF", dnf=True)
    side, = list((w2.root / "s1" / "p426_dnf").glob("*.json"))
    doc = json.loads(side.read_text())
    side.write_text(json.dumps(T9.seal(dict({k: v for k, v in doc.items() if k != "sha256"}, item_record="items/other.dnf.json"))))
    with pytest.raises(H.HarvestError, match="p426_dnf.*sidecar|sidecar.*differ"):
        w2.harvest(emails=(OPERATOR,))


def test_10_a_manifest_run_id_that_resolves_to_no_directory_fails_the_harvest(tmp_path):
    import shutil
    w = T9.World(tmp_path)
    shutil.rmtree(w.run)
    shutil.rmtree(w.ev)
    with pytest.raises(H.HarvestError, match="run id|run directory"):
        w.harvest(emails=(OPERATOR,))
    T9.nothing_published(w)


def test_10_a_manifest_run_id_that_resolves_to_two_directories_fails_the_harvest(tmp_path):
    w = T9.World(tmp_path)
    twin = w.wd / "opencode-probe-v3" / f"run-{T9.RUN_ID}"
    T9.put(twin / "grading-private" / "x.json", "{}")
    with pytest.raises(H.HarvestError, match="more than one|two"):
        w.harvest(emails=(OPERATOR,))
    T9.nothing_published(w)


from bench.tests import test_b2_s8_wave2 as T8  # noqa: E402

world = T8.world                                           # the sequencer fixture (fake ops, fake clock)


def dossier_path(world):
    p, = list((world.out / "pairs").glob("pilot__*.json"))
    return p


def reseal(path, **changes):
    doc = json.loads(path.read_text())
    for k, v in changes.items():
        if k.startswith("arms."):
            _, arm, field = k.split(".")
            doc["arms"][arm][field] = v
        else:
            doc[k] = v
    path.write_text(json.dumps(ph.seal(doc)))


@pytest.mark.parametrize("changes, field", [
    (dict(verdict="FAIL"), "verdict"), (dict(differences=[]), "differences"),
    (dict(**{"arms.off.receipt_sha256": "0" * 64}), "receipt_sha256"), (dict(**{"arms.on.harvest_sha256": "1" * 64}), "harvest_sha256"),
    (dict(**{"arms.on.attempt": "tg1-p426-on-pilot.a9"}), "attempt")])
def test_2_a_resumed_sequencer_re_verifies_an_existing_dossier_against_the_current_records(world, changes, field):
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0
    reseal(dossier_path(world), **changes)
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 1
    last = (world.out / "sequence.log").read_text().splitlines()[-1]
    # a tampered pilot dossier is caught first by the amendment re-verification (fix round 4, item 3): its recorded sha256 differs
    assert field in last or "pilot_dossier_sha256" in last


def test_2_a_dossier_without_a_correct_self_hash_stops_the_sequence(world):
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0
    p = dossier_path(world)
    doc = json.loads(p.read_text())
    doc.pop("sha256")
    p.write_text(json.dumps(doc))
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 1
    assert "sha256" in (world.out / "sequence.log").read_text().splitlines()[-1]


def test_2_an_untouched_dossier_resumes_cleanly(world):
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0


def test_9_a_failure_to_publish_the_run_files_is_exit_code_4_and_no_done_line(world):
    def boom(paths, *, emails):
        raise OSError("disk full")
    world.ops.publish_run_files = boom
    assert T8.go(world, "--through", "tg1-p426-off-pilot") == 4
    log = (world.out / "sequence.log").read_text()
    assert "DONE" not in log and "through tg1-p426-off-pilot" not in log and "run files" in log and "OSError" in log


def test_9_done_is_reported_only_after_the_run_files_were_published(world):
    assert T8.go(world, "--through", "tg1-p426-off-pilot") == 0
    events = [k for k, _ in world.ops.events]
    assert events[-1] == "run_files"
    assert "through tg1-p426-off-pilot" in (world.out / "sequence.log").read_text()
    assert len([e for e in events if e == "run_files"]) == 1               # published once, not again in the exit path


# ------------------------------------------------------------------------------------------------ 5. in-flight DNF / kill cases
def _t4():
    from bench.tests import test_b2_s4_reconcile as T4
    return T4


def test_5_a_dnf_boundary_abort_with_a_trailing_failed_line_is_systemic():
    T4 = _t4()
    r = T4.dnf(T4.req() + [T4.started(), T4.failed()], [(100, 10)])                         # no in-flight marker in the manifest
    assert not r.ok and any("in flight" in p for p in r.problems)
    assert T4.dnf(T4.req() + [T4.started(), T4.failed()], [(100, 10)], in_flight="2").case == "dnf_inflight_failed"


def test_5_a_dnf_with_the_in_flight_marker_set_but_no_message_id_may_still_be_inflight_failed():
    T4 = _t4()
    rep = T4.pr.reconcile_dnf(dict(transport_abort=dict(
        session_id="ses_1", gate=dict(request_usage=[["1", 10, 100, 81920]]),
        in_flight=dict(in_flight=True, message_id=None, requests_started=2))), *_dnf_window(T4))
    assert rep.ok and rep.case == "dnf_inflight_failed"


def _dnf_window(T4):
    ls = T4.lines_of(*(T4.req() + [T4.started(), T4.failed()]))
    return ls, dict(T4.BEFORE), T4.after_of(ls)


def test_5_a_kill_with_a_trailing_failed_line_needs_the_structured_in_flight_evidence():
    T4 = _t4()
    raw = T4.req() + [T4.started(), T4.failed()]
    boundary = T4.item(raw, [(100, 10)], at_kill=1, kind="budget_hit_kill", termination=dict(in_flight_at_kill=0, killed=[{}], reason="x"))
    assert not boundary.ok                                                                  # a boundary kill cannot have a failed line
    flight = T4.item(raw, [(100, 10)], at_kill=1, kind="budget_hit_kill", termination=dict(in_flight_at_kill=1, killed=[{}], reason="x"))
    assert flight.ok and flight.case == "kill_inflight_failed"
    unknown = T4.item(raw, [(100, 10)], at_kill=1, kind="budget_hit_kill", termination=dict(in_flight_at_kill=None, killed=[{}], reason="x"))
    assert not unknown.ok


def test_5_a_kill_with_an_unaccounted_completed_line_needs_the_in_flight_evidence_too():
    T4 = _t4()
    raw = T4.req() + T4.req(prompt=300, gen=9)
    ok = T4.item(raw, [(100, 10)], at_kill=1, kind="budget_hit_kill", termination=dict(in_flight_at_kill=1, killed=[{}], reason="x"))
    assert ok.ok and ok.case == "kill_completed_unaccounted"
    assert not T4.item(raw, [(100, 10)], at_kill=1, kind="budget_hit_kill", termination=dict(in_flight_at_kill=0, killed=[{}], reason="x")).ok


# ------------------------------------------------------------------------------------------------ 4. engagement on DNF / degenerate ON
def test_4_a_dnf_items_completed_requests_are_judged_for_engagement_and_persisted(tmp_path):
    T4 = _t4()
    ops, hooks, out = T4.make_hooks(tmp_path, arm="ON")
    assert hooks.before_attempt(T4.SLOT, T4.ctx()).kind == "accept"
    ops.serve(*T4.req(prompt=100, gen=10))                                                  # ON request without draft counters
    problems, record = hooks.dnf_problems(T4.SLOT, T4.abort_of([(100, 10)]))
    assert any("ON arm" in p or "engagement" in p for p in problems)
    assert record["verdict"] == "invalid" and record["checks"]["engagement"]["ok"] is False
    stored = json.loads((out / "items" / f"{T4.SLOT_FILE}.dnf.json").read_text())
    assert "engagement" in stored["checks"]


def test_4_an_engaged_dnf_item_persists_an_ok_engagement_check(tmp_path):
    T4 = _t4()
    ops, hooks, out = T4.make_hooks(tmp_path, arm="ON")
    hooks.before_attempt(T4.SLOT, T4.ctx())
    ops.serve(*T4.req(prompt=100, gen=10, draft=T4.ON_DRAFT))
    problems, record = hooks.dnf_problems(T4.SLOT, T4.abort_of([(100, 10)]))
    assert problems == [] and record["checks"]["engagement"]["ok"] is True


def test_4_an_on_item_with_no_request_long_enough_to_be_judged_is_unengaged():
    T4 = _t4()
    assert any("unengaged" in p for p in T4.pr.engagement_problems([T4.rq(1), T4.rq(0)], "ON", item=True))
    assert any("unengaged" in p for p in T4.pr.engagement_problems([], "ON", item=True))
    assert T4.pr.engagement_problems([T4.rq(5, **T4.GOOD_ON)], "ON", item=True) == []
    assert T4.pr.engagement_problems([T4.rq(1)], "OFF", item=True) == []
    assert T4.pr.engagement_problems([T4.rq(1)], "ON") == []                                # the legacy call keeps its meaning


def test_4_the_done_hook_marks_an_on_item_without_a_judged_request_invalid(tmp_path):
    T4 = _t4()
    ops, hooks, out = T4.make_hooks(tmp_path, arm="ON")
    hooks.before_attempt(T4.SLOT, T4.ctx())
    ops.serve(*T4.req(prompt=100, gen=1))
    d = hooks.after_attempt(T4.SLOT, dict(id="python/a"), T4.ctx(T4.row_of([(100, 1)])))
    assert d.kind == "invalidate" and "unengaged" in d.reason


def _leg_with_records(tmp_path, arm, items, dnf_items=()):
    """A `valid_leg_problems` fixture: leg.json / receipt.json / chain.json ledger / item records on disk."""
    from bench import chain_rows as cr_
    root = tmp_path / f"tg1-p426-{arm}-pilot.a1"
    (root / "items").mkdir(parents=True)
    S.write_record(root / "leg.json", S.self_hashed(dict(leg=f"tg1-p426-{arm}-pilot", attempt=1, state="VALID", reason="")))
    S.write_record(root / "receipt.json", S.arm_receipt_doc(arm))
    ledger = []
    for i, (slot, requests, verdict) in enumerate(items):
        name = cr_.slot_file(slot)
        ledger.append(dict(slot=slot, kind="row", invocation="x", index=i))
        ready = ph.write_exclusive(root / "items" / f"{name}.ready.json", dict(slot=slot, k=i))
        S.write_record(root / "items" / f"{name}.json",
                       S.self_hashed(dict(slot=slot, ready_sha256=ready["sha256"], requests=requests, verdict=verdict)))
    for j, (slot, requests, verdict) in enumerate(dnf_items):
        name = cr_.slot_file(slot)
        ledger.append(dict(slot=slot, kind="dnf", invocation="x", index=len(items) + j))
        ready = ph.write_exclusive(root / "items" / f"{name}.ready.json", dict(slot=slot, k=len(items) + j))
        S.write_record(root / "items" / f"{name}.dnf.json",
                       S.self_hashed(dict(slot=slot, ready_sha256=ready["sha256"], requests=requests, verdict=verdict)))
    (root / "chain.json").write_text(json.dumps(dict(p426_ledger=ledger)))
    return root


def test_4_valid_leg_problems_re_validates_dnf_item_records(tmp_path):
    from bench import p426_freeze as fz
    T4 = _t4()
    good = [T4.rq(5, **T4.GOOD_ON)]
    root = _leg_with_records(tmp_path, "on", [("t|oc|M|s|python|a", good, "reconciled")],
                             dnf_items=[("t|oc|M|s|python|b", [T4.rq(5)], "reconciled")])         # a DNF record whose request lacks counters
    problems = fz.valid_leg_problems(root, "on")
    assert any("|b" in p and ("ON arm" in p or "engagement" in p) for p in problems), problems
    bad_hash = _leg_with_records(tmp_path / "x", "on", [("t|oc|M|s|python|a", good, "reconciled")],
                                 dnf_items=[("t|oc|M|s|python|b", good, "invalid")])
    assert any("|b" in p and "reconciled" in p for p in fz.valid_leg_problems(bad_hash, "on"))
    fine = _leg_with_records(tmp_path / "y", "on", [("t|oc|M|s|python|a", good, "reconciled")],
                             dnf_items=[("t|oc|M|s|python|b", good, "reconciled")])
    assert fz.valid_leg_problems(fine, "on") == []


def test_4_an_on_leg_with_no_judged_request_anywhere_is_unengaged(tmp_path):
    from bench import p426_freeze as fz
    T4 = _t4()
    root = _leg_with_records(tmp_path, "on", [], dnf_items=[("t|oc|M|s|python|b", [], "reconciled")])
    assert any("unengaged" in p for p in fz.valid_leg_problems(root, "on"))
    off = _leg_with_records(tmp_path / "off", "off", [("t|oc|M|s|python|a", [T4.rq(1)], "reconciled")])
    assert fz.valid_leg_problems(off, "off") == []


# ------------------------------------------------------------------------------------------------ 6. the amendment owns the pilot gate
from bench import p426_freeze as fz  # noqa: E402
from bench.tests import b2_s8_support as S8  # noqa: E402
from bench.tests import test_b2_s8_freeze as TF  # noqa: E402


@pytest.fixture
def freeze_world(tmp_path, monkeypatch):
    """`test_b2_s8_freeze.world` (two worktrees with pins, fake freeze ops), under a name that does not clash with the sequencer's."""
    wd = tmp_path / "wd"
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    off, on = wd / "p426" / "stack-p426-off", wd / "p426" / "stack-p426-on"
    for wt in (off, on):
        pins = wt / "src/mlx-vlm/dev/p369_phase2/pins.json"
        pins.parent.mkdir(parents=True)
        pins.write_text(TF.PINS)
    return dict(wd=wd, off=off, on=on, ops=TF.FOps(wd, off, on), rehearsal=wd / "p426" / "rehearsal", rec=wd / "p426" / "record")


def test_6_write_amendment_refuses_a_failing_pilot_gate_by_itself(freeze_world, capsys):
    w = freeze_world
    TF.make_v8(w, capsys)
    off, on = TF.pilot_roots(w, speed_valid=False)
    (rc, err), out = TF.amend(w, capsys, off, on)
    assert rc == 2 and "speed" in err and not out.exists()


@pytest.mark.parametrize("kw, needle", [(dict(engagement_ok=False), "request"), (dict(items=4), "5"),
                                        (dict(state="VALID_WITH_DNF", items=4, dnf=1), "DNF")])
def test_6_write_amendment_runs_every_gate_condition(freeze_world, capsys, kw, needle):
    w = freeze_world
    TF.make_v8(w, capsys)
    off, on = TF.pilot_roots(w, **kw)
    (rc, err), out = TF.amend(w, capsys, off, on)
    assert rc == 2 and needle in err and not out.exists()


def test_6_write_amendment_needs_the_pass_pilot_pair_dossier_and_records_its_hash(freeze_world, capsys):
    w = freeze_world
    TF.make_v8(w, capsys)
    off, on = TF.pilot_roots(w, dossier=False)
    (rc, err), out = TF.amend(w, capsys, off, on)
    assert rc == 2 and "dossier" in err and not out.exists()
    dpath = TF.write_pilot_dossier(off, on, verdict="FAIL")
    (rc, err), out = TF.amend(w, capsys, off, on)
    assert rc == 2 and "dossier" in err and not out.exists()
    dpath.unlink()
    dpath = TF.write_pilot_dossier(off, on, verdict="PASS")
    (rc, err), out = TF.amend(w, capsys, off, on)
    assert rc == 0, err
    doc = json.loads(out.read_text())
    assert doc["pilot_dossier_sha256"] == S.sha256_file(dpath)


def test_6_a_dossier_that_names_other_attempts_or_receipts_is_refused(freeze_world, capsys):
    w = freeze_world
    TF.make_v8(w, capsys)
    off, on = TF.pilot_roots(w, dossier=False)
    TF.write_pilot_dossier(off, on, verdict="PASS", receipt_sha_off="0" * 64)
    (rc, err), out = TF.amend(w, capsys, off, on)
    assert rc == 2 and "receipt_sha256" in err and not out.exists()


def test_6_the_sequencer_re_verifies_an_existing_amendment_instead_of_returning(world):
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0
    path = world.rec / "amendment.json"
    assert path.is_file()
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0                 # untouched: verified, fine
    doc = json.loads(path.read_text())
    path.write_text(json.dumps(ph.seal(dict({k: v for k, v in doc.items() if k != "sha256"}, v8_base_sha256="0" * 64))))
    assert T8.go(world, "--through", "tg1-p426-on-pilot") in (1, 2)            # the records load (2) or the re-verification (1) refuses it


def test_6_an_existing_amendment_that_does_not_name_the_selected_pass_dossier_stops_the_sequence(world):
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0
    path = world.rec / "amendment.json"
    doc = json.loads(path.read_text())
    path.write_text(json.dumps(ph.seal(dict({k: v for k, v in doc.items() if k != "sha256"}, pilot_dossier_sha256="0" * 64))))
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 1
    assert "amendment" in (world.out / "sequence.log").read_text().splitlines()[-1]


def test_6_an_existing_amendment_that_names_no_pilot_dossier_stops_the_sequence(world):
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0
    path = world.rec / "amendment.json"
    doc = json.loads(path.read_text())
    path.write_text(json.dumps(ph.seal({k: v for k, v in doc.items() if k not in ("sha256", "pilot_dossier_sha256")})))
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 1
    assert "amendment" in (world.out / "sequence.log").read_text().splitlines()[-1]


def test_6_an_existing_amendment_with_a_broken_self_hash_stops_the_sequence(world):
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0
    path = world.rec / "amendment.json"
    path.write_text(path.read_text().replace('"w_go_s"', '"w_go_s_x"', 1))
    assert T8.go(world, "--through", "tg1-p426-on-pilot") in (1, 2)


# ------------------------------------------------------------------------------------------------ 7. rehearsal binding
def _v8_with(freeze_world, capsys, tamper=None):
    manifest = TF.make_manifest(freeze_world, capsys)
    legs = TF.make_rehearsal_legs(freeze_world)
    if tamper:
        tamper(legs, manifest)
    out = freeze_world["rec"] / "v8_base.json"
    rc, err = TF.run(TF.v8_argv(freeze_world, manifest, legs, out), freeze_world["ops"], capsys=capsys)
    return rc, err, out


def _edit_chain(root, **changes):
    p = Path(root) / "chain.json"
    doc = json.loads(p.read_text())
    doc.update(changes)
    p.write_text(json.dumps(doc))


def _edit_leg(root, **changes):
    p = Path(root) / "leg.json"
    doc = json.loads(p.read_text())
    p.write_text(json.dumps(ph.seal(dict({k: v for k, v in doc.items() if k != "sha256"}, **changes))))


def test_7_a_rehearsal_bound_to_this_manifest_with_the_expected_names_and_injections_passes(freeze_world, capsys):
    rc, err, out = _v8_with(freeze_world, capsys)
    assert rc == 0, err and out.exists()


@pytest.mark.parametrize("which", ["r1_off", "r1_on", "r2", "r3"])
def test_7_a_leg_run_under_another_manifest_refuses(freeze_world, capsys, which):
    def tamper(legs, manifest):
        fr = json.loads((legs[which] / "chain.json").read_text())["frozen_record"]
        _edit_chain(legs[which], frozen_record=dict(fr, sha256="0" * 64))
    rc, err, out = _v8_with(freeze_world, capsys, tamper)
    assert rc == 2 and "frozen_record" in err and not out.exists()


def test_7_a_leg_whose_frozen_record_path_is_another_file_refuses(freeze_world, capsys):
    def tamper(legs, manifest):
        fr = json.loads((legs["r1_off"] / "chain.json").read_text())["frozen_record"]
        _edit_chain(legs["r1_off"], frozen_record=dict(fr, path="$STACK_WORKDIR/p426/rehearsal/other.json"))
    rc, err, out = _v8_with(freeze_world, capsys, tamper)
    assert rc == 2 and "frozen_record" in err and not out.exists()


def test_7_a_leg_that_records_no_frozen_record_refuses(freeze_world, capsys):
    def tamper(legs, manifest):
        doc = json.loads((legs["r3"] / "chain.json").read_text())
        doc.pop("frozen_record")
        (legs["r3"] / "chain.json").write_text(json.dumps(doc))
    rc, err, out = _v8_with(freeze_world, capsys, tamper)
    assert rc == 2 and "frozen_record" in err and not out.exists()


@pytest.mark.parametrize("which, name", [("r1_off", "tg1-p426-rehearsal-on"), ("r1_on", "tg1-p426-rehearsal-off"),
                                         ("r2", "tg1-p426-rehearsal-kill"), ("r3", "tg1-p426-rehearsal-mismatch")])
def test_7_each_rehearsal_leg_must_carry_its_expected_leg_name(freeze_world, capsys, which, name):
    rc, err, out = _v8_with(freeze_world, capsys, lambda legs, manifest: _edit_leg(legs[which], leg=name))
    assert rc == 2 and "tg1-p426-rehearsal" in err and not out.exists()


@pytest.mark.parametrize("which, inject", [("r2", "stall-kill"), ("r2", None), ("r3", "reconcile-mismatch"), ("r3", None)])
def test_7_r2_and_r3_must_carry_their_expected_injection(freeze_world, capsys, which, inject):
    rc, err, out = _v8_with(freeze_world, capsys, lambda legs, manifest: _edit_chain(legs[which], inject=inject))
    assert rc == 2 and "inject" in err and not out.exists()


def test_7_r1_must_carry_no_injection(freeze_world, capsys):
    rc, err, out = _v8_with(freeze_world, capsys, lambda legs, manifest: _edit_chain(legs["r1_on"], inject="stall-kill"))
    assert rc == 2 and "inject" in err and not out.exists()


def test_7_the_manifests_own_commits_are_not_compared_with_the_v8_arms(freeze_world, capsys):
    manifest = TF.make_manifest(freeze_world, capsys)
    for wt in (freeze_world["off"], freeze_world["on"]):                      # the arms move on after the rehearsal (spec 1)
        freeze_world["ops"].state[str(wt)]["head"] = ("a" if wt == freeze_world["off"] else "b") * 40
    legs = TF.make_rehearsal_legs(freeze_world)
    out = freeze_world["rec"] / "v8_base.json"
    rc, err = TF.run(TF.v8_argv(freeze_world, manifest, legs, out), freeze_world["ops"], capsys=capsys)
    assert rc == 0, err


def test_7_the_chain_records_its_frozen_record_and_injection_in_chain_json(tmp_path, monkeypatch):
    from bench.tests.test_b2_s8c_chain import chain_doc, world_leg
    rc, env = world_leg(tmp_path, monkeypatch, ("chain", "s1", "--rehearsal"), extra=("--inject", "stall-kill"), rehearsal=True)
    assert rc == 0, "\n".join(env["lines"][-6:])
    doc = chain_doc(env)
    record = Path(env["records"]["reh"])
    assert doc["inject"] == "stall-kill" and doc["frozen_record"]["sha256"] == json.loads(record.read_text())["sha256"]
    assert doc["frozen_record"]["path"].endswith(record.name) and str(tmp_path) not in doc["frozen_record"]["path"]


def test_11_the_item_records_ready_sha256_is_the_ready_records_self_hash(tmp_path):
    from bench.tests import test_b2_s4_reconcile as T4
    ops, hooks, out = T4.make_hooks(tmp_path)
    assert hooks.before_attempt(T4.SLOT, T4.ctx()).kind == "accept"
    ops.serve(*T4.req(prompt=100, gen=10, draft=T4.ON_DRAFT))
    assert hooks.after_attempt(T4.SLOT, dict(id="python/a"), T4.ctx(T4.row_of([(100, 10)]))).kind == "accept"
    ready = json.loads((out / "items" / f"{T4.SLOT_FILE}.ready.json").read_text())
    rec = json.loads((out / "items" / f"{T4.SLOT_FILE}.json").read_text())
    assert rec["ready_sha256"] == ready["sha256"] and ph.sealed_ok(ready)


def test_12_a_non_utf8_evidence_file_is_scrubbed_with_surrogateescape_and_recorded_lossy(tmp_path):
    w = T9.World(tmp_path)
    raw = b"\xff\xfe bytes then a path " + str(w.wd / "x" / "y").encode() + b" and \xc3\x28 more\n"
    T9.put(w.root / "RUNLOG.md", raw)
    doc = w.harvest(emails=(OPERATOR,))
    e = T9.entry(doc, "leg:RUNLOG.md")
    out = (w.stage / e["published"]).read_bytes()
    assert b"$STACK_WORKDIR/x/y" in out and str(w.wd).encode() not in out
    assert out.startswith(b"\xff\xfe") and b"\xc3\x28" in out                      # the undecodable bytes survive unchanged
    assert e["lossy_decode"] == "surrogateescape"
    assert all("lossy_decode" not in f for f in doc["files"] if f["source"] != "leg:RUNLOG.md")
