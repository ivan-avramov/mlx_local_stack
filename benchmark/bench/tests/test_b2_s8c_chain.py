"""B2 slice s8c (spec docs/specs/p426-b2-tg1-wave2.md v3.2, sections 1, 5.5, 16.3, 16.7, 16.8, 13): the chain-side completion of the P426
legs - the `makeup` mode, the `--rehearsal` smoke shape, the two rehearsal injections (and the probe flags behind `stall-kill`), the item
record's request `elapsed_s`, and the in-process topology test (the real `Sequencer` whose `launch` runs the real
`run_tg1_chain.main(argv, ops=FakeOps)` on a thread with the fake probe). Hermetic: no router, worker, model, network or GPU; every
workdir is under `tmp_path`; the only registries read are the synthetic ones the fixtures write."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench import p426_reconcile as prc
from bench import p426_record

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"


# ----------------------------------------------------------------------------------------------- the item record's request elapsed_s
def completed(elapsed="12.500s"):
    return ("2026-10-27 10:00:00,000 INFO Request completed: endpoint=/chat/completions model=caslca/m stream=True backend=cached_session "
            f"session=ses_x cached_tokens=0 prompt_tokens=100 generated_tokens=40 elapsed={elapsed} prefill=200.0 tok/s decode=50.0 tok/s "
            "finish_reason=stop in_flight=0\n").encode()


def test_a_request_row_carries_the_logged_elapsed_as_elapsed_s():
    """§16.8 settle bound: `elapsed_s` of the item record's requests is the worker's own `elapsed` of that request."""
    (line,) = prc.parse_log(completed())
    assert prc._request_row(line)["elapsed_s"] == 12.5


def test_a_failed_request_row_has_no_elapsed_s_value():
    failed = ("2026-10-27 10:00:00,000 ERROR Request failed: endpoint=/chat/completions model=caslca/m stream=True error=stream_closed "
              "in_flight=0\n").encode()
    (line,) = prc.parse_log(failed)
    assert prc._request_row(line)["elapsed_s"] is None


# ----------------------------------------------------------------------------------------------- schedules: the smoke shape, the make-up plan
NAMES = {"python": [f"p{i}" for i in range(1, 9)], "go": [f"g{i}" for i in range(1, 9)]}


def p426_order(lang, seed):
    import random
    pool = sorted(NAMES[lang])
    return random.Random(seed).sample(pool, len(pool))


def occ(session, lang, item, n, arm="off"):
    return dict(session=session, language=lang, item=item, seed={"s1": 1001, "s2": 2002}.get(session, 0), arm_of_dnf=arm, occurrence=n)


def test_the_rehearsal_schedule_is_one_pilot_item_then_two_full_items_of_s1s_python_order():
    """§16.3: `--rehearsal` = the smoke shape of s1's P426 Python order; nothing of Go."""
    from bench import schedules
    sched = schedules.tg1("chain", ["s1"], NAMES, picks=(MODEL,), p426=True, rehearsal=True)
    (block,) = sched["blocks"]
    (leg,) = block["legs"]
    order = p426_order("python", 1001)
    assert (block["session"], leg["lang"], leg["seed_base"]) == ("s1", "python", 1001)
    assert leg["full_names"] == order[:3] and leg["pilot_names"] == order[:1]
    assert [(i["phase"], i["names"]) for i in leg["invocations"]] == [("pilot", order[:1]), ("full", order[1:3])]
    assert sched["rehearsal"] is True
    plain = schedules.tg1("chain", ["s1"], NAMES, picks=(MODEL,), p426=True)
    assert "rehearsal" not in plain and schedules.schedule_sha256(plain) != schedules.schedule_sha256(sched)


@pytest.mark.parametrize("kw", [dict(sessions=["s1", "s2"]), dict(sessions=["s2"]), dict(sessions=["s1"], p426=False),
                                dict(sessions=["s1"], smoke=True)])
def test_the_rehearsal_shape_is_only_for_one_p426_s1_leg(kw):
    from bench import schedules
    args = dict(sessions=["s1"], p426=True, smoke=False)
    args.update(kw)
    with pytest.raises(ValueError):
        schedules.tg1("chain", args.pop("sessions"), NAMES, picks=(MODEL,), rehearsal=True, **args)


def test_the_makeup_schedule_is_one_load_one_leg_per_group_in_the_canonical_order():
    from bench import schedules
    occs = [occ("s2", "go", "g2", 1), occ("s1", "python", "p4", 3), occ("s1", "python", "p2", 1), occ("s2", "python", "p2", 0, "on"),
            occ("s1", "go", "g5", 0), occ("s1", "python", "p2", 1, "on")]
    sched = schedules.tg1_makeup(occs, NAMES, picks=(MODEL,), predictor="off")
    assert sched["mode"] == "makeup" and sched["p426"] is True and sched["makeup"] is True
    (block,) = sched["blocks"]                                    # ONE load: a fresh-load leg
    assert block["session"] == "makeup" and block["model"] == MODEL
    got = [(l["session"], l["seed_base"], l["lang"], l["full_names"]) for l in block["legs"]]
    assert got == [("s1", 1001, "python", ["p2", "p4"]), ("s1", 1001, "go", ["g5"]), ("s2", 2002, "go", ["g2"]),
                   ("s2", 2002, "python", ["p2"])]
    for l in block["legs"]:                                       # one invocation per group, the items in occurrence order
        assert [(i["phase"], i["names"], i["expect"]) for i in l["invocations"]] == [
            ("full", l["full_names"], [f"{l['lang']}/{n}" for n in l["full_names"]])]
    stems = [l["stem"] for l in block["legs"]]
    assert len(set(stems)) == 4 and all(s.startswith(f"{MODEL}.makeup.") for s in stems)
    assert schedules.tg1_makeup(list(reversed(occs)), NAMES, picks=(MODEL,), predictor="off") == sched          # an unordered set


@pytest.mark.parametrize("bad", [occ("s3", "python", "p1", 0), dict(occ("s1", "rust", "p1", 0)), occ("s1", "python", "nope", 0)])
def test_the_makeup_schedule_refuses_an_unknown_session_language_or_item(bad):
    from bench import schedules
    with pytest.raises(ValueError):
        schedules.tg1_makeup([bad], NAMES, picks=(MODEL,), predictor="off")


@pytest.mark.parametrize("build,expect", [
    (lambda s: s.tg1("pilot", [], NAMES, picks=(MODEL,), p426=True), 5),                          # pilot-only: the leg's order is longer than its run
    (lambda s: s.tg1("chain", ["reload"], NAMES, picks=(MODEL,), p426=True), 5),
    (lambda s: s.tg1("chain", ["s1"], NAMES, picks=(MODEL,), p426=True), 16),                       # python then go: 8 + 8
    (lambda s: s.tg1("chain", ["s1"], NAMES, picks=(MODEL,), p426=True, rehearsal=True), 3),
    (lambda s: s.tg1_makeup([occ("s1", "python", "p2", 0), occ("s2", "go", "g3", 1)], NAMES, picks=(MODEL,)), 2)])
def test_the_planned_slots_are_what_the_legs_invocations_run_not_the_length_of_their_order(tmp_path, build, expect):
    """Found by the topology test: a pilot leg's `full_names` is its whole seeded order, but it runs only its 5-item invocation."""
    from bench import p426_wave2 as w2
    from bench import schedules
    sched = build(schedules)
    root = tmp_path / "leg"
    root.mkdir()
    (root / "schedule.json").write_text(json.dumps(sched))
    (root / "chain.json").write_text(json.dumps(dict(schedule_sha256=schedules.schedule_sha256(sched))))
    assert w2.planned_slots(root) == expect


def test_the_sequencers_canonical_occurrences_are_the_schedules():
    """One implementation: the sequencer's canonical union / groups equal the chain's."""
    from bench import p426_wave2 as w2
    from bench import schedules
    occs = [occ("s2", "go", "g2", 1), occ("s1", "python", "p4", 3), occ("s1", "python", "p2", 1), occ("s1", "python", "p2", 1, "on")]
    assert w2.canonical_occurrences(occs) == schedules.makeup_canonical(occs)


# ----------------------------------------------------------------------------------------------- the make-up record mode
def test_the_makeup_mode_runs_under_the_timeout_amendment(tmp_path):
    from bench.tests import b2_s8_support as S
    from bench import p426_hooks as ph
    v8 = ph.write_exclusive(tmp_path / "v8_base.json", dict(kind="p426_v8_base", off_commit="a" * 40, on_commit="b" * 40))
    ph.write_exclusive(tmp_path / "amendment.json", dict(kind="p426_timeout_amendment", v8_base_sha256=v8["sha256"], w_python_s=1.0,
                                                         w_go_s=1.0, leg_deadline_s={}, settle_bound_s=900.0))
    rec = p426_record.load(tmp_path / "amendment.json", mode="makeup")
    assert rec["doc"]["kind"] == "p426_timeout_amendment" and rec["base"]["sha256"] == v8["sha256"]
    with pytest.raises(p426_record.RecordError):
        p426_record.load(tmp_path / "v8_base.json", mode="makeup")
    assert S.MODEL == MODEL


# ----------------------------------------------------------------------------------------------- the probe side of `stall-kill` (spec 16.8)
from types import SimpleNamespace                                                  # noqa: E402

from bench import arm_runner                                                       # noqa: E402
from bench import proc_guard as pg                                                 # noqa: E402  (arm_runner's `pg`)
from bench.tests.test_opencode_v2_probe import tg1_probe as probe                  # noqa: E402,F401  (fixture)


def stall_args(**kw):
    base = dict(evidence="p426", lang="python", inject_stall_item="python/p1", inject_stall_s=30)
    base.update(kw)
    return SimpleNamespace(**base)


def test_the_probe_parser_takes_the_two_stall_flags_and_defaults_to_nothing(probe):
    base = ["--model", "m", "--items", "a", "--seed-base", "1"]
    a = probe._parser().parse_args(base)
    assert a.inject_stall_item is None and a.inject_stall_s is None
    a = probe._parser().parse_args(base + ["--evidence", "p426", "--inject-stall-item", "python/a", "--inject-stall-s", "30"])
    assert (a.inject_stall_item, a.inject_stall_s) == ("python/a", 30)


@pytest.mark.parametrize("kw,needle", [
    (dict(inject_stall_s=None), "together"), (dict(inject_stall_item=None), "together"), (dict(evidence=None), "--evidence p426"),
    (dict(inject_stall_s=0), "positive"), (dict(inject_stall_item="python/zzz"), "not among"), (dict(inject_stall_item="go/p1"), "not among"),
])
def test_the_stall_flags_are_refused_unless_complete_p426_and_naming_a_selected_item(kw, needle):
    got = arm_runner.inject_stall_problem(stall_args(**kw), ["p1", "p2"])
    assert got and needle in got


def test_the_stall_flags_are_accepted_together_and_absent_means_no_problem():
    assert arm_runner.inject_stall_problem(stall_args(), ["p1", "p2"]) is None
    assert arm_runner.inject_stall_problem(stall_args(inject_stall_item=None, inject_stall_s=None, evidence=None), ["p1"]) is None


def test_the_lowered_stall_limit_applies_to_the_named_item_only():
    a = stall_args()
    assert arm_runner.silence_limit_s(a, "python/p1") == 30
    assert arm_runner.silence_limit_s(a, "python/p2") == pg.POLICY["silence_s"]
    assert arm_runner.silence_limit_s(stall_args(inject_stall_item=None, inject_stall_s=None), "python/p1") == pg.POLICY["silence_s"]


def test_the_item_loop_takes_a_per_item_silence_limit_that_defaults_to_the_policys():
    import inspect
    sig = inspect.signature(arm_runner._run_item)
    assert "silence_s" in sig.parameters and sig.parameters["silence_s"].default is None
    src = inspect.getsource(arm_runner._run_item)
    assert 'pg.POLICY["silence_s"]' in src and "silence_s if silence_s is not None" in src


def run_fake_probe(tmp_path, monkeypatch, extra, items="a,b,c"):
    """`chains/c147/fake_probe.main` in-process (the chain under test normally spawns it): returns (rc, rows)."""
    import sys
    import threading
    import time
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "chains" / "c147"))
    import fake_probe as fp
    state = tmp_path / "fstate"
    state.mkdir()
    monkeypatch.setenv("FAKE_PROBE_STATE", str(state))
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.setenv("FAKE_ITEM_S", "0.01")
    monkeypatch.setenv("FAKE_HB_S", "0.01")
    monkeypatch.setenv("FAKE_TICK_S", "0.005")
    ack, cancel, out = tmp_path / "ack", tmp_path / "cancel", tmp_path / "rows" / "x.jsonl"
    out.parent.mkdir()
    threading.Timer(0.2, lambda: ack.write_text("")).start()
    argv = ["--model", MODEL, "--items", items, "--lang", "python", "--seed-base", "1001", "--out", str(out),
            "--scaffold", "opencode-v2-web-tg1", "--expect-items", ",".join(f"python/{i}" for i in items.split(",")),
            "--a4-v2-receipt", "r", "--sampling-profile", "deployed", "--cancel-file", str(cancel), "--manifest-ack", str(ack),
            "--frozen-prompt-date", "Mon Jan 05 2026", *extra]
    rc = fp.main(argv)
    time.sleep(0)
    rows = [json.loads(x) for x in out.read_text().splitlines()] if out.exists() else []
    return rc, rows


def test_the_fake_probe_scores_the_injected_item_as_a_stall_kill_and_no_other(tmp_path, monkeypatch):
    rc, rows = run_fake_probe(tmp_path, monkeypatch, ["--inject-stall-item", "python/b", "--inject-stall-s", "30"])
    assert rc == 0
    by = {r["id"]: r for r in rows}
    assert by["python/b"]["nonconv_kind"] == "stalled" and by["python/b"]["converged"] is False and by["python/b"]["passed"] is False
    assert all(by[i]["nonconv_kind"] is None and by[i]["converged"] is True for i in ("python/a", "python/c"))


def test_the_fake_probe_without_the_flags_scores_every_item_normally(tmp_path, monkeypatch):
    rc, rows = run_fake_probe(tmp_path, monkeypatch, [])
    assert rc == 0 and all(r["nonconv_kind"] is None for r in rows) and len(rows) == 3


# ----------------------------------------------------------------------------------------------- the chain CLI: make-up mode, rehearsal, injections
CLI = ["--p426", "--models", MODEL, "--predictor", "off", "--probe-code-sha", "9" * 64, "--policy-sha", "c" * 64,
       "--frozen-prompt-date", "Mon Jan 05 2026", "--campaign-core", "campaign-1", "--frozen-record", "/x/am.json", "--out-root", "/x/leg"]


def parse(argv):
    from bench.tests.test_c147_chain_runner import R
    return R.parse_args(argv)


def refuses(argv):
    with pytest.raises(SystemExit) as e:
        parse(argv)
    assert e.value.code == 2


def test_makeup_is_a_p426_mode_with_an_occurrences_file():
    a = parse(["makeup", *CLI, "--occurrences", "/x/occ.jsonl"])
    assert (a.mode, a.occurrences, a.sessions, a.p426) == ("makeup", "/x/occ.jsonl", [], True)


@pytest.mark.parametrize("argv", [
    ["makeup", *CLI],                                                                      # --occurrences is required
    ["makeup", "s1", *CLI, "--occurrences", "/x/o"],                                       # no session: the file is the plan
    ["makeup", *CLI, "--occurrences", "/x/o", "--rehearsal"],                              # a make-up leg is never a rehearsal
    ["makeup", *[x for x in CLI if x != "--p426"], "--occurrences", "/x/o"],               # P426 only
    ["makeup", *CLI[:CLI.index("--probe-code-sha")], *CLI[CLI.index("--probe-code-sha") + 2:], "--occurrences", "/x/o"],
    ["chain", "s1", *CLI, "--occurrences", "/x/o"], ["pilot", *CLI, "--occurrences", "/x/o"],      # --occurrences is for makeup only
])
def test_makeup_refusals(argv):
    refuses(argv)


def test_the_inject_flags_still_refuse_without_rehearsal():
    refuses(["chain", "s1", *CLI, "--inject", "reconcile-mismatch"])
    refuses(["chain", "s1", *CLI, "--inject", "stall-kill"])
    assert parse(["chain", "s1", *CLI, "--rehearsal", "--inject", "stall-kill"]).inject == "stall-kill"


# ----------------------------------------------------------------------------------------------- end to end on the hermetic P426 world
def world_leg(tmp_path, monkeypatch, mode, *, arm="off", extra=(), out_name=None, rehearsal=False, before=None, helper=None, timeout=240):
    from bench.tests import b2_frozen_add_support as A
    from bench.tests import b2_frozen_support as S
    env = A.world(tmp_path, monkeypatch, arm=arm, out_name=out_name, rehearsal=rehearsal)
    if before:
        before(env)
    argv, _ = S.p426_argv(env, mode, extra=extra)
    try:
        rc = S.run_p426(env, argv, helper=(lambda: helper(env)) if helper else None, timeout=timeout)
    finally:
        env["ops"].cancel()
    return rc, env


def chain_doc(env):
    return json.loads((Path(env["out"]) / "chain.json").read_text())


def probe_argvs(env):
    from bench.tests import b2_frozen_support as S
    return [i["argv"] for i in S.invocations(env)]


def flag(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def log_text(env):
    return "\n".join(env["lines"][-12:])


def first_python_order():
    import random
    pool = sorted(f"p{i}" for i in range(1, 7))
    return random.Random(1001).sample(pool, len(pool))


def test_rehearsal_runs_the_smoke_shape_one_pilot_item_then_two_full_items(tmp_path, monkeypatch):
    rc, env = world_leg(tmp_path, monkeypatch, ("chain", "s1", "--rehearsal"), rehearsal=True)
    assert rc == 0, log_text(env)
    order = first_python_order()
    calls = probe_argvs(env)
    assert [(flag(c, "--lang"), flag(c, "--items").split(",")) for c in calls] == [("python", order[:1]), ("python", order[1:3])]
    doc = chain_doc(env)
    assert [e["slot"].split("|")[-1] for e in doc["p426_ledger"]] == order[:3]
    assert json.loads((Path(env["out"]) / "schedule.json").read_text())["rehearsal"] is True
    assert str(env["out"]).startswith(str(tmp_path / "p426" / "rehearsal"))


def test_rehearsal_refuses_an_out_root_outside_the_rehearsal_directory_before_writing_anything(tmp_path, monkeypatch):
    from bench.tests import b2_frozen_support as S
    rc, env = world_leg(tmp_path, monkeypatch, ("chain", "s1", "--rehearsal"), out_name="tg1-p426-off-s1.a1")
    assert rc == 2 and any("p426/rehearsal" in ln for ln in env["lines"]), log_text(env)
    assert not Path(env["out"]).exists() and not S.invocations(env)


def test_inject_reconcile_mismatch_invalidates_the_first_item_with_the_exact_reason(tmp_path, monkeypatch):
    rc, env = world_leg(tmp_path, monkeypatch, ("chain", "s1", "--rehearsal"), extra=("--inject", "reconcile-mismatch"), rehearsal=True)
    assert rc == 2, log_text(env)
    doc = chain_doc(env)
    assert [i["reason"] for i in doc["p426_invalid"]] == ["reconciliation mismatch (injected)"]
    assert doc["p426_ledger"] == [] and not doc["p426_dnf"]            # the leg stops after that item: an invalidated item is no row
    items = sorted(p for p in (Path(env["out"]) / "items").glob("*.json") if not p.name.endswith((".ready.json", ".dnf.json")))
    rec = json.loads(items[0].read_text())
    assert len(items) == 1 and rec["verdict"] == "invalid" and not rec["checks"]["injected"]["ok"]


def test_inject_stall_kill_flags_reach_only_the_invocation_holding_the_first_python_item(tmp_path, monkeypatch):
    rc, env = world_leg(tmp_path, monkeypatch, ("chain", "s1", "--rehearsal"), extra=("--inject", "stall-kill"), rehearsal=True)
    assert rc == 0, log_text(env)
    first = first_python_order()[0]
    calls = probe_argvs(env)
    assert flag(calls[0], "--inject-stall-item") == f"python/{first}" and flag(calls[0], "--inject-stall-s") == "30"
    assert all("--inject-stall-item" not in c and "--inject-stall-s" not in c for c in calls[1:])


def test_no_stall_flags_without_the_injection(tmp_path, monkeypatch):
    rc, env = world_leg(tmp_path, monkeypatch, ("chain", "s1", "--rehearsal"), rehearsal=True)
    assert rc == 0 and all("--inject-stall-item" not in c for c in probe_argvs(env))


MK_OCCS = [occ("s2", "python", "p2", 1), occ("s1", "python", "p4", 3), occ("s1", "python", "p2", 1, "on"), occ("s1", "go", "g5", 0),
           occ("s2", "go", "g2", 0), occ("s1", "python", "p2", 1)]
MK_SLOTS = [("s1", "python", "p2"), ("s1", "python", "p4"), ("s1", "go", "g5"), ("s2", "go", "g2"), ("s2", "python", "p2")]


def write_occs(tmp_path, occs=MK_OCCS):
    f = Path(tmp_path) / "occurrences.jsonl"
    f.write_text("".join(json.dumps(o) + "\n" for o in occs))
    return f


def test_a_makeup_leg_runs_one_invocation_per_group_in_the_canonical_order(tmp_path, monkeypatch):
    f = write_occs(tmp_path)
    rc, env = world_leg(tmp_path, monkeypatch, ("makeup",), extra=("--occurrences", str(f)), out_name="tg1-p426-off-makeup.a1")
    assert rc == 0, log_text(env)
    calls = probe_argvs(env)
    assert [(flag(c, "--lang"), flag(c, "--items"), flag(c, "--seed-base")) for c in calls] == [
        ("python", "p2,p4", "1001"), ("go", "g5", "1001"), ("go", "g2", "2002"), ("python", "p2", "2002")]
    doc = chain_doc(env)
    assert doc["mode"] == "makeup" and doc["status"] == "finished" and doc["p426_not_run"] == []
    assert [tuple(e["slot"].split("|")[3:6]) for e in doc["p426_ledger"]] == MK_SLOTS
    assert json.loads((Path(env["out"]) / "schedule.json").read_text())["makeup"] is True


def test_a_makeup_leg_stopped_early_records_its_unrun_occurrences(tmp_path, monkeypatch):
    f = write_occs(tmp_path)

    def stop_after_first_item(env):
        import time
        end = time.time() + 60
        while time.time() < end:
            done = [p for p in (Path(env["out"]) / "items").glob("*.json") if not p.name.endswith(".ready.json")]
            if done:
                (Path(env["out"]) / "STOP").write_text("")
                return
            time.sleep(0.01)
    rc, env = world_leg(tmp_path, monkeypatch, ("makeup",), extra=("--occurrences", str(f)), out_name="tg1-p426-off-makeup.a1",
                        helper=stop_after_first_item)
    doc = chain_doc(env)
    assert rc == 3                                                                   # the STOP latch honoured
    run =[tuple(e["slot"].split("|")[3:6]) for e in doc["p426_ledger"]]
    left = [(n["session"], n["language"], n["item"]) for n in doc["p426_not_run"]]
    assert run and left and not (set(run) & set(left))
    assert run + left == MK_SLOTS                                                    # the unrun ones, in the canonical order


# ----------------------------------------------------------------------------------------------- the topology test (spec 13, 16.8)
# The real `Sequencer` (`bench.p426_wave2.main`) whose `ops.launch` runs the real `run_tg1_chain.main(argv, ops=<FakeOps>)` on a
# thread with the item-barrier fake probe: the real argv, locks, records, `chain.json`, `LAST_LEG_END` and watcher contract; no
# router, worker or model. One `$STACK_WORKDIR` for the sequencer and both arms' chains (one worktree per arm).
import hashlib                                                                     # noqa: E402
import sys                                                                         # noqa: E402
import threading                                                                   # noqa: E402
import time                                                                        # noqa: E402

from bench import chain_ops as co                                                  # noqa: E402
from bench import p426_hooks as ph                                                 # noqa: E402
from bench import p426_locks as pl                                                 # noqa: E402
from bench import p426_receipt as pr                                               # noqa: E402
from bench import p426_wave2 as w2                                                 # noqa: E402
from bench.tests import b2_frozen_add_support as A                                 # noqa: E402
from bench.tests import b2_frozen_support as S                                     # noqa: E402
from bench.tests import test_b2_s8_wave2 as W                                      # noqa: E402


class TopoClock(W.Clock):
    """The sequencer's fake clock (so a 600 s gap costs no real time); it yields the CPU so the chain thread makes progress."""

    def __init__(self):
        super().__init__(t=time.time())

    def sleep(self, s):
        super().sleep(s)
        time.sleep(0.003)


def arm_ops(wd, arm, wt, clock):
    """The chain's `FakeOps` for one arm in the shared workdir: `S.p426_world`'s seams, with this arm's worktree and the REAL
    `LAST_LEG_END` (re-based onto the chain's `time.time()` so the 600 s gap is measured on the sequencer's fake clock)."""
    on = arm == "on"
    wd, wt = Path(wd), Path(wt)
    reg = wt / "main_models.yaml"
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(S.registry_text((S.MODEL,), on=(S.MODEL,) if on else ()))
    ops = S._t1c().FakeOps(wd)
    ops.overlay, ops.overlay_sha = str(reg), (lambda: S.sha256_file(reg))
    pins = wt / "src/mlx-vlm/dev/p369_phase2/pins.json"
    pins.parent.mkdir(parents=True, exist_ok=True)
    pins.write_bytes(S.PINS.read_bytes())
    log, metrics = wt / "logs" / "mlx_vlm.log", wt / "metrics.json"
    log.parent.mkdir(exist_ok=True)
    log.touch()
    (wt / "logs" / "main_model.log").touch()
    ops.repo, ops.server_log_path = wt, (lambda: log)
    ops.read_log = lambda path, start, end=None: Path(path).read_bytes()[start:end]
    S.ops_with_metrics_file(ops, metrics)
    commit = S.ON_COMMIT if on else S.OFF_COMMIT

    def account(served, failed=0):
        m = json.loads(metrics.read_text()) if metrics.exists() else S.metrics_doc()
        s = m["summary"]
        prev_d = s["generated_tokens_total"] / s["avg_decode_tok_s"] if s["avg_decode_tok_s"] else 0.0
        metrics.write_text(json.dumps(S.metrics_doc(
            started=s["requests_started"] + len(served) + failed, completed=s["requests_completed"] + len(served),
            failed=s["requests_failed"] + failed, prompt_total=s["prompt_tokens_total"] + sum(u[2] for u in served),
            generated_total=s["generated_tokens_total"] + sum(u[1] for u in served),
            decode_s=prev_d + sum(u[1] for u in served) / 50.0)))
    ops.worktree_state = lambda *a: dict(head=commit, clean=True, gitlinks=dict(S.BASE_GITLINKS))

    def last_leg_end():
        t = pl.read_last_leg_end(wd)
        return None if t is None else t - (clock() - time.time())
    ops.last_leg_end = last_leg_end
    ops.a4_gate = S.a4_gate_writer(ops, wd, log, account)
    router_argv = [str(wt / ".venv/bin/mlx-serve"), "start"]
    ops.proc_argv = lambda pid: (list(router_argv) if pid == 1 else S.served_worker_argv(ops.overlay, S.MODEL)
                                 if ops.ident and pid == ops.ident["pid"] else [sys.executable, str(S.PROBE)])
    ops.proc_environ = lambda pid: dict(A.SHARED_ENV, MLX_SERVE_CONFIG=str(reg))
    ops.interpreter_inventory = lambda pid: {"path": str(wt / ".venv/bin/python"), "inventory_sha256": "8" * 64,
                                             "editables": {"mlx-vlm": {"tree": str(wt / "src/mlx-vlm"),
                                                                       "gitlink": S.BASE_GITLINKS["src/mlx-vlm"], "clean": True}}}
    ops.loaded_images = lambda pid: S.LOADED_IMAGES(wt)
    ops.snapshot_hashes = lambda model: S.pinned_snapshots(arm)
    ops.expected_worker_argv = lambda registry_path, model: S.served_worker_argv(registry_path, model)
    ops.busy_procs, ops.descendants = (lambda: []), (lambda pid: set())
    ops.create_time = lambda pid: ops.ident["create_time"] if ops.ident and pid == ops.ident["pid"] else 1.0
    ops.extra_env.update(S.barrier_env(ops.state, log=log, metrics=metrics), FAKE_SERVED_REGISTRY=str(reg))
    loader = ops.load

    def load(model):
        ident = loader(model)
        w = ops.state / "worker.json"
        w.write_text(json.dumps(dict(json.loads(w.read_text()), registry_sha256=S.sha256_file(reg))))
        return ident
    ops.load = load
    ops.commit = commit
    return ops


class TopologyOps(W.SeqOps):
    """`SeqOps` whose `launch` of a chain runs the real chain on a thread; the watcher is still the journal fake."""

    def __init__(self, topo):
        super().__init__(topo.wd, topo.clock, topo.off, topo.on)
        self.topo, self.threads, self.lag, self.watching, self.lock_samples = topo, {}, {}, {}, []
        self.walls = dict(w_python_s=1.0e6, w_go_s=1.0e6, max_request_elapsed_s=60.0)   # the fake clock outruns the chain: no overrun
        self.state[str(topo.off)]["head"], self.state[str(topo.on)]["head"] = S.OFF_COMMIT, S.ON_COMMIT
        self.ident = {k: topo.ident[k] for k in ("probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256")}

    def launch_chain(self, h, argv):
        root = Path(argv[argv.index("--out-root") + 1])
        name = root.name.rsplit(".a", 1)[0]
        self.events.append(("launch", root.name))
        self.launches.append(dict(name=name, root=root, argv=h.argv))
        self.launch_times[root.name] = self.clock()
        arm = "on" if argv[argv.index("--predictor") + 1] == "mtp" else "off"
        ops = self.topo.arm_ops[arm]
        chain_argv = argv[2:] + ["--probe", str(S.PROBE), "--python", sys.executable, "--universe", str(self.topo.uni), "--arm-idle-s", "0"]
        res = {}
        t1c = S._t1c()

        def target():
            try:
                res["rc"] = t1c.R.main(chain_argv, ops=ops, timers=t1c.R.Timers(**t1c.TIMERS), log_out=self.topo.lines.append,
                                       campaign=S.fake_campaign(ops.commit))
            except SystemExit as e:
                res["rc"] = e.code if isinstance(e.code, int) else 2
            except BaseException as e:  # noqa: BLE001
                res["exc"] = e
        th = threading.Thread(target=target, daemon=True)
        th.start()
        h.thread, h.res = th, res
        self.threads[h.pid] = h
        end = time.time() + 20                                  # the chain takes its own lock first thing: sample both locks
        while time.time() < end and not W.flocked(self.topo.wd / pl.LEG) and th.is_alive():
            time.sleep(0.005)
        self.lock_samples.append((name, W.flocked(self.topo.wd / pl.SEQUENCER), W.flocked(self.topo.wd / pl.LEG)))

    def launch_watcher(self, h, argv):
        super().launch_watcher(h, argv)
        self.watching[h.pid] = int(argv[argv.index("--driver-pid") + 1])
        self.lag[h.pid] = 2

    def alive(self, pid, start):
        if pid in self.threads:
            return self.threads[pid].thread.is_alive()
        if pid in self.watching:
            if self.threads[self.watching[pid]].thread.is_alive():
                return True
            self.lag[pid] -= 1
            return self.lag[pid] >= 0
        return super().alive(pid, start)

    def wait(self, h):
        h.thread.join(120)
        if "exc" in h.res:
            raise h.res["exc"]
        return h.res.get("rc", 1)


@pytest.fixture
def topo(tmp_path, monkeypatch):
    """One `$STACK_WORKDIR`, two worktrees, the v8 base, a universe, the sequencer's fake clock and the topology ops."""
    wd = tmp_path / "wd"
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    t = SimpleNamespace(wd=wd, off=wd / "p426" / "stack-p426-off", on=wd / "p426" / "stack-p426-on", clock=TopoClock(), lines=[],
                        rec=wd / "p426" / "record", out=wd / "p426" / "wave2", ident=S.fake_identity())
    t.uni = wd / "universe.json"
    t.uni.parent.mkdir(parents=True, exist_ok=True)
    t.uni.write_text(json.dumps({"items": {**{f"python/p{i}": {} for i in range(1, 7)}, **{f"go/g{i}": {} for i in range(1, 7)}}}))
    t.arm_ops = {"off": arm_ops(wd, "off", t.off, t.clock), "on": arm_ops(wd, "on", t.on, t.clock)}
    pins = S.sha256_file(t.off / "src/mlx-vlm/dev/p369_phase2/pins.json")
    S.write_record(t.rec / "v8_base.json", S.v8_base(
        off_worktree=S.portable(t.off), on_worktree=S.portable(t.on), probe_code_sha256=t.ident["probe_code_sha256"],
        scaffold_policy_sha256=t.ident["scaffold_policy_sha256"], generation_identity_sha256=t.ident["generation_identity_sha256"],
        pins_sha256=pins, frozen_prompt_date=S.EPOCH_DATE, pilot_deadline_s=1.0e8))
    t.ops = TopologyOps(t)
    yield t
    for ops in t.arm_ops.values():
        ops.cancel()


def go_topology(t, cmd, *extra):
    argv = [cmd, "--record-dir", str(t.rec), "--worktree-off", str(t.off), "--worktree-on", str(t.on), "--out-base", str(t.out), *extra]
    return w2.main(argv, ops=t.ops, clock=t.clock, sleep=t.clock.sleep)


def leg(t, attempt):
    return json.loads((t.out / attempt / "leg.json").read_text())


def test_the_pilot_pair_runs_end_to_end_through_the_real_sequencer_and_the_real_chain(topo):
    rc = go_topology(topo, "run", "--through", "tg1-p426-on-pilot")
    assert rc == 0, "\n".join(topo.lines[-10:]) + "\n" + (topo.out / "sequence.log").read_text()[-2500:]
    off, on = leg(topo, "tg1-p426-off-pilot.a1"), leg(topo, "tg1-p426-on-pilot.a1")
    assert (off["state"], on["state"]) == ("VALID", "VALID") and off["speed_valid"] and on["speed_valid"]
    # records: the chain wrote its own `chain.json` / `receipt.json` / item records; the sequencer sealed the leg record
    for name in ("tg1-p426-off-pilot.a1", "tg1-p426-on-pilot.a1"):
        root = topo.out / name
        doc = json.loads((root / "chain.json").read_text())
        assert doc["status"] == "finished" and len(doc["p426_ledger"]) == 5 and doc["p426_dnf"] == [] and (root / "receipt.json").is_file()
        assert ph.sealed_ok(json.loads((root / "leg.json").read_text()))
        assert len([p for p in (root / "items").glob("*.json") if not p.name.endswith((".ready.json", ".dnf.json"))]) == 5
        assert doc["progress"] and w2.planned_slots(root) == 5                      # the plan is the leg's own frozen schedule
    # the second chain compared its receipt with the first leg's at its after-load checkpoint (the real pair gate)
    argv = topo.ops.launches[1]["argv"]
    assert argv[argv.index("--pair-receipt") + 1] == str(topo.out / "tg1-p426-off-pilot.a1" / "receipt.json")
    # locks: the sequencer's lock was held while each chain held its own; both are free at the end
    assert [s[1:] for s in topo.ops.lock_samples] == [(True, True), (True, True)]
    assert not W.flocked(topo.wd / pl.SEQUENCER) and not W.flocked(topo.wd / pl.LEG)
    # LAST_LEG_END: written after each leg; the second leg started a full gap after the first ended
    ended = pl.read_last_leg_end(topo.wd)
    assert ended is not None and topo.ops.launch_times["tg1-p426-on-pilot.a1"] - topo.ops.launch_times["tg1-p426-off-pilot.a1"] >= pl.IDLE_GAP_S
    # the pair dossier and the amendment the gate wrote
    dossier = json.loads((topo.out / "pairs" / "pilot__off-a1__on-a1.json").read_text())
    assert dossier["verdict"] == "PASS" and {e["field"] for e in dossier["differences"]} == {"argv.worker", "snapshots.drafter"}
    assert dossier["arms"]["on"]["receipt_sha256"] == hashlib.sha256((topo.out / "tg1-p426-on-pilot.a1" / "receipt.json").read_bytes()).hexdigest()
    amendment = json.loads((topo.rec / "amendment.json").read_text())
    assert amendment["kind"] == "p426_timeout_amendment" and amendment["settle_bound_s"] >= 900


def test_a_makeup_pair_runs_end_to_end_after_the_pilot_gate(topo):
    assert go_topology(topo, "run", "--through", "tg1-p426-on-pilot") == 0
    f = write_occs(topo.wd)
    topo.clock.t += 3600
    rc = go_topology(topo, "makeup", "--occurrences", str(f))
    assert rc == 0, "\n".join(topo.lines[-10:]) + "\n" + (topo.out / "sequence.log").read_text()[-2500:]
    for name, arm in (("tg1-p426-off-makeup.a1", "off"), ("tg1-p426-on-makeup.a1", "on")):
        assert leg(topo, name)["state"] == "VALID"
        doc = json.loads((topo.out / name / "chain.json").read_text())
        assert doc["mode"] == "makeup" and doc["status"] == "finished" and doc["p426_not_run"] == []
        assert [tuple(e["slot"].split("|")[3:6]) for e in doc["p426_ledger"]] == MK_SLOTS
        assert w2.planned_slots(topo.out / name) == 5                                # the union is the leg's frozen plan
    argv = topo.ops.launches[-1]["argv"]
    assert argv[argv.index("--occurrences") + 1] == str(topo.out / "makeup" / "occurrences.on.jsonl")
    assert json.loads((topo.out / "pairs" / "makeup__off-a1__on-a1.json").read_text())["verdict"] == "PASS"


def test_a_makeup_leg_refuses_an_item_that_is_not_in_the_corpus(tmp_path, monkeypatch):
    f = write_occs(tmp_path, [occ("s1", "python", "nope", 0)])
    rc, env = world_leg(tmp_path, monkeypatch, ("makeup",), extra=("--occurrences", str(f)), out_name="tg1-p426-off-makeup.a1")
    assert rc != 0 and not probe_argvs(env)
