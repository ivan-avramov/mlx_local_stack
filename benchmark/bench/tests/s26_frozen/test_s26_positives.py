"""S26 frozen tests, the tg2 positives (spec §2 `cmd_positives`, §4 the pass rule, `positives_problems` v8; acceptance 1: host change
-> FAIL, an inject exception -> sealed FAIL record, DECLINED vs FAIL vs PASS per kind from real-shaped events (incl. `FAIL:rss` with
no marker stays FAIL), stall never DECLINED, v8 accepts DECLINED only for loop / alloc with valid evidence).

Classes: [FIX] reproduces a failure the spec fixes (a model that declines to run a planted command failed the positives; a crash
or a host change lost / hid the record); [INV] preserves an invariant; [NEW] new behaviour. Fixtures: real-shaped inject rows (the
real `OpencodeArm.row_fields` over a recorded real grade tree; `tool_use` events as opencode 2.0.20 writes them), the existing
`PosOps` seam shape, and (hybrid tests) the REAL `BoxSeqOps.positive_inject` / `inject_verify` over a fake worktree whose probe
interpreter copies prepared rows. Bare verdict strings (`PASS`, `not_observed:kill`, `FAIL:rss`, ...) are what the fake
`inject_verify` returns (ASSUMPTION: the existing seam returns the verdict; the spec compares the verdict string, §4)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import p426_freeze as fz
from bench import p426_hooks as ph
from bench import p426_wave2 as W2
from bench.tests.s26_frozen import s26_support as X

ADDED = "Homebrew Cellar: added openjdk@17/17.0.9"
CHANGED = "host environment changed during the leg: "


def mutate(world):
    world.formula("openjdk@17", "17.0.9")


@pytest.fixture
def world(tmp_path):
    return X.HostWorld(tmp_path / "host")


def run_pos(tmp_path, monkeypatch, world, **kw):
    ops = X.PosOps(tmp_path, world, **kw)
    rc, out = X.positives(tmp_path, monkeypatch, ops)
    return rc, X.record(out), ops


def loop_call(cmd="sleep 600"):
    return X.ev_tool("c2", "shell", {"command": cmd})


def alloc_call():
    return X.ev_tool("c2", "shell", {"command": "python3 -c \"x = bytearray(10**10); print(len(x))\""})


# ---------------------------------------------------------------------------------------------------- a clean run
def test_inv_a_clean_run_passes_and_records_the_host_before_and_after(tmp_path, monkeypatch, world):
    """[INV] + [NEW] §2: the sealed record carries `host_env` (= env0) and `host_env_after` (= env1); an unchanged host adds no problem."""
    rc, doc, ops = run_pos(tmp_path, monkeypatch, world)
    assert rc == 0 and doc["verdict"] == "PASS" and doc["problems"] == [] and ph.sealed_ok(doc)
    assert doc["host_env"] == doc["host_env_after"] == world.fingerprint()
    assert ops.host_calls >= 2
    assert {(e["language"], e["kind"]): e["verdict"] for e in doc["injects"]} == {
        **{(lang, k): "PASS" for lang in X.LANGS for k in X.KINDS}, (X.LANGS[0], "interrupt"): "PASS"}    # S27 §4.5


# ---------------------------------------------------------------------------------------------------- the host guard
@pytest.mark.parametrize("where", ["grade", "inject", "session_exit"])
def test_fix_a_host_change_anywhere_in_the_leg_fails_the_record(tmp_path, monkeypatch, world, where):
    """[FIX] C360: the fingerprint is taken before the first grade and after the serving session; a change a positive made fails."""
    hooks = {"grade": lambda lang, variant: mutate(world), "inject": lambda lang, kind: mutate(world),
             "session_exit": lambda: mutate(world)}
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, hooks={where: hooks[where]})
    assert rc == 1 and doc["verdict"] == "FAIL" and ph.sealed_ok(doc)
    assert CHANGED + ADDED in doc["problems"]
    assert doc["host_env"] != doc["host_env_after"]
    assert [line for line in doc["problems"] if line.startswith(CHANGED)] == [CHANGED + ADDED]


def test_fix_each_host_change_is_its_own_problem(tmp_path, monkeypatch, world):
    def both():
        mutate(world)
        world.npm_pkg("jest", "29.7.0")
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, hooks={"session_exit": both})
    got = sorted(line for line in doc["problems"] if line.startswith(CHANGED))
    assert rc == 1 and got == sorted([CHANGED + ADDED, CHANGED + "npm -g jest: absent -> 29.7.0"])


# ---------------------------------------------------------------------------------------------------- exceptions
@pytest.mark.parametrize("where, hook_args", [("inject", ("javascript", "loop")), ("grade", ("java", "stub")),
                                              ("session_enter", ())])
def test_fix_an_exception_anywhere_still_seals_a_fail_record(tmp_path, monkeypatch, world, where, hook_args):
    """[FIX] S26 Sol P5 / GLM F3: the grades, the serving session and the injects run in one `try`; any exception is a problem
    `exception: <Name>: <message>`, the record is written, `host_env_after` is taken (also when no session opened), rc 1."""
    def boom(*args):
        if tuple(args) == hook_args:
            raise RuntimeError("kaboom")
    rc, doc, ops = run_pos(tmp_path, monkeypatch, world, hooks={where: boom})
    assert rc == 1 and doc["verdict"] == "FAIL" and ph.sealed_ok(doc)
    assert "exception: RuntimeError: kaboom" in doc["problems"]
    assert doc["host_env_after"] == world.fingerprint() == doc["host_env"]
    if where == "inject":
        assert ops.served == ["start", "stop"]                        # the session was closed on the way out
        assert len(doc["injects"]) < 12 and len(doc["grades"]) == 8
    if where == "grade":
        assert ops.served == []                                       # no session ever opened; the record exists regardless


def test_fix_an_exception_message_is_cut_at_300_characters(tmp_path, monkeypatch, world):
    def boom(*args):
        raise ValueError("x" * 1000)
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, hooks={"grade": boom})
    assert rc == 1 and "exception: ValueError: " + "x" * 300 in doc["problems"]
    assert not any("x" * 301 in line for line in doc["problems"])


def test_fix_an_exception_and_a_host_change_are_both_recorded(tmp_path, monkeypatch, world):
    def boom(lang, kind):
        mutate(world)
        raise RuntimeError("kaboom")
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, hooks={"inject": boom})
    assert rc == 1 and "exception: RuntimeError: kaboom" in doc["problems"] and CHANGED + ADDED in doc["problems"]


# ---------------------------------------------------------------------------------------------------- DECLINED vs FAIL vs PASS
DEFAULT = None
SLEEP_TEXT = [X.ev_text("I will not run `sleep 600`; it would hang the shell.")]
WRITE_SLEEP = [X.ev_tool("c2", "write", {"filePath": "x.sh", "content": "sleep 600\n"})]
WRITE_BYTES = [X.ev_tool("c2", "write", {"filePath": "x.py", "content": "x = bytearray(1 << 40)\n"})]


def ev(*extra):
    return X.default_events() + list(extra)


# (kind, inject_verify verdict, events, expected recorded verdict)
MATRIX = [
    ("loop", "not_observed:kill", DEFAULT, "DECLINED"),                         # the model never ran the planted command
    ("loop", "not_observed", DEFAULT, "DECLINED"),
    ("loop", "not_observed:kill", ev(*SLEEP_TEXT), "DECLINED"),                 # the marker in TEXT is not a tool call
    ("loop", "not_observed:descendant", ev(loop_call()), "not_observed:descendant"),     # it ran `sleep 600`: the harness failed
    ("loop", "not_observed:kill", ev(loop_call("cd /tmp && sleep 600 &")), "not_observed:kill"),   # marker anywhere in the input
    ("loop", "not_observed:kill", ev(*WRITE_SLEEP), "not_observed:kill"),       # any tool call's input counts, not only `shell`
    ("loop", "FAIL:loop_threshold", DEFAULT, "FAIL:loop_threshold"),            # a FAIL is never declined for loop
    ("loop", "FAIL:events_rederivation", DEFAULT, "FAIL:events_rederivation"),
    ("loop", "PASS", ev(loop_call()), "PASS"),                                  # a PASS stays PASS whatever the events hold
    ("alloc", "not_observed:kill", DEFAULT, "DECLINED"),
    ("alloc", "FAIL:no_shell_part", DEFAULT, "FAIL:no_shell_part"),             # erratum v1.1a 1: NEVER declinable, marker or not
    ("alloc", "FAIL:no_shell_part", ev(*WRITE_BYTES), "FAIL:no_shell_part"),
    ("loop", "competing_trigger:turn_cap", DEFAULT, "competing_trigger:turn_cap"),   # every competing_trigger:* stays a failure
    ("alloc", "competing_trigger:turn_cap", DEFAULT, "competing_trigger:turn_cap"),
    ("alloc", "FAIL:rss", DEFAULT, "FAIL:rss"),                                 # spec: `FAIL:rss` with no marker stays FAIL
    ("alloc", "FAIL:rss", ev(alloc_call()), "FAIL:rss"),
    ("alloc", "FAIL:unrelated_kill", DEFAULT, "FAIL:unrelated_kill"),
    ("alloc", "not_observed:continuation", ev(alloc_call()), "not_observed:continuation"),
    ("stall", "not_observed", DEFAULT, "not_observed"),                         # stall must pass: never DECLINED
    ("stall", "competing_trigger:T", DEFAULT, "competing_trigger:T"),
    ("stall", "FAIL:stall_threshold", DEFAULT, "FAIL:stall_threshold"),
]


@pytest.mark.parametrize("kind, verdict, events, expected", MATRIX,
                         ids=[f"{k}-{v}-{'marker' if e else 'bare'}" for k, v, e, _ in MATRIX])
def test_fix_declined_only_when_the_model_never_ran_the_planted_command(tmp_path, monkeypatch, world, kind, verdict, events, expected):
    """[FIX] C361 (1) / spec §4 + erratum v1.1a/b: stall -> PASS required; loop / alloc -> PASS, else DECLINED iff the verdict is
    `not_observed*` (and ONLY then: `FAIL:*` incl. `FAIL:no_shell_part`, `competing_trigger:*` never), the artifacts verify, the
    events hold no tool call whose input contains the kind's marker, and the row is a normally completed run with no kill."""
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, verdicts={("rust", kind): verdict},
                         events={("rust", kind): events} if events is not None else None)
    entry = X.inject_of(doc, "rust", kind)
    assert entry["verdict"] == expected
    if expected in ("PASS", "DECLINED"):
        assert rc == 0 and doc["verdict"] == "PASS" and doc["problems"] == []
    else:
        assert rc == 1 and doc["verdict"] == "FAIL" and f"rust {kind}: {expected}" in doc["problems"]
    if expected == "DECLINED":
        ev_doc = entry["declined_evidence"]
        run = Path(tmp_path) / "wd" / "m65" / "inject" / f"rust-{kind}"
        row = json.loads((run / f"{kind}.attempt1.jsonl").read_text())
        values = list(ev_doc.values()) if isinstance(ev_doc, dict) else []
        assert row["evidence_sha256"]["events"] in values and X.MARKERS[kind] in values and verdict in values
    else:
        assert entry.get("declined_evidence") is None


def test_fix_declined_runs_pass_the_record_in_every_language(tmp_path, monkeypatch, world):
    """[FIX] several DECLINED across languages and kinds, everything else PASS: the record PASSES (rc 0)."""
    verdicts = {("rust", "loop"): "not_observed:kill", ("cpp", "alloc"): "not_observed:kill", ("java", "loop"): "not_observed"}
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, verdicts=verdicts)
    assert rc == 0 and doc["verdict"] == "PASS"
    assert sorted((e["language"], e["kind"]) for e in doc["injects"] if e["verdict"] == "DECLINED") == sorted(verdicts)


@pytest.mark.parametrize("tamper", ["events", "datefreeze", "row"])
def test_fix_a_decline_needs_the_recorded_artifacts_to_verify(tmp_path, monkeypatch, world, tamper):
    """[FIX] §4: DECLINED only if the run's recorded artifacts verify against the row's `evidence_sha256` (inject_verify's V3 check):
    an events / datefreeze file changed after its sha was recorded, or a row that is gone, is the verdict as it was (a FAIL)."""
    def after_write(lang, kind, events_path, run):
        if (lang, kind) != ("rust", "loop"):
            return
        if tamper == "events":
            Path(events_path).write_text(Path(events_path).read_text() + "\n")
        elif tamper == "datefreeze":
            row = json.loads((Path(run) / "loop.attempt1.jsonl").read_text())
            Path(str(row["datefreeze_path"]).replace("$STACK_WORKDIR", str(Path(tmp_path) / "wd"))).write_text("changed\n")
        else:
            (Path(run) / "loop.attempt1.jsonl").unlink()
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, verdicts={("rust", "loop"): "not_observed:kill"},
                         hooks={"after_write": after_write})
    assert X.inject_of(doc, "rust", "loop")["verdict"] == "not_observed:kill"
    assert rc == 1 and "rust loop: not_observed:kill" in doc["problems"]


def test_fix_an_unreadable_events_file_is_not_a_decline_and_not_a_crash(tmp_path, monkeypatch, world):
    def after_write(lang, kind, events_path, run):
        if (lang, kind) == ("cpp", "alloc"):
            Path(events_path).unlink()
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, verdicts={("cpp", "alloc"): "not_observed:kill"},
                         hooks={"after_write": after_write})
    assert ph.sealed_ok(doc) and rc == 1 and X.inject_of(doc, "cpp", "alloc")["verdict"] == "not_observed:kill"


def test_fix_a_transport_abort_stays_a_fail_and_is_never_declined(tmp_path, monkeypatch, world):
    """[FIX] §4: `TRANSPORT_ABORT` stays a FAIL (no row, no events, nothing to decline on)."""
    rc, doc, ops = run_pos(tmp_path, monkeypatch, world, aborts={("java", "loop"): 2}, verdicts={("java", "loop"): "not_observed"})
    entry = X.inject_of(doc, "java", "loop")
    assert rc == 1 and entry["verdict"] == "TRANSPORT_ABORT" and entry["attempts"] == 2
    assert "java loop: TRANSPORT_ABORT" in doc["problems"] and ("java", "loop") not in ops.verified


def test_inv_one_abort_then_a_decline_on_the_retry_is_a_decline(tmp_path, monkeypatch, world):
    """[INV] the one retry per run on a transport abort is unchanged; the retry's row is the one judged."""
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, aborts={("java", "alloc"): 1}, verdicts={("java", "alloc"): "not_observed:kill"})
    entry = X.inject_of(doc, "java", "alloc")
    assert rc == 0 and entry["verdict"] == "DECLINED" and entry["attempts"] == 2


@pytest.mark.parametrize("shape", ["client_kill", "mem_kill"])
@pytest.mark.parametrize("kind", ["loop", "alloc"])
def test_fix_a_not_observed_row_with_any_kill_is_not_a_decline(tmp_path, monkeypatch, world, kind, shape):
    """[FIX] erratum v1.1b 9: "no kill" = `mem_kills` AND `termination.killed` both present and empty; a `not_observed*` verdict on a
    row with a client kill, or with a memory kill, is not a clean decline (fail closed): the verdict stays, the record FAILS."""
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, verdicts={("rust", kind): "not_observed:kill"},
                         shapes={("rust", kind): shape})
    assert X.inject_of(doc, "rust", kind)["verdict"] == "not_observed:kill"
    assert rc == 1 and doc["verdict"] == "FAIL" and f"rust {kind}: not_observed:kill" in doc["problems"]


@pytest.mark.parametrize("field", ["mem_kills", "termination.killed"])
def test_fix_a_row_that_records_no_kill_field_at_all_is_not_a_decline(tmp_path, monkeypatch, world, field):
    """[FIX] erratum v1.1b 9: "present and empty" - an ABSENT `mem_kills` / `termination.killed` is not evidence of no kill."""
    def drop(row, manifest):
        if field == "mem_kills":
            row.pop("mem_kills")
        else:
            row["termination"].pop("killed")
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, verdicts={("rust", "loop"): "not_observed:kill"},
                         mutates={("rust", "loop"): drop})
    assert X.inject_of(doc, "rust", "loop")["verdict"] == "not_observed:kill" and rc == 1


@pytest.mark.parametrize("kind", ["loop", "alloc"])
def test_fix_a_nonzero_probe_exit_that_left_a_row_is_not_a_decline(tmp_path, monkeypatch, world, kind):
    """[FIX] erratum v1.1a 1: DECLINED needs the probe's rc 0 (and a verified `row_sha256`): a probe that exited nonzero but left a
    complete-looking `not_observed` row is a failure, not the model declining."""
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, verdicts={("rust", kind): "not_observed:kill"}, probe_rc={("rust", kind): 3})
    assert X.inject_of(doc, "rust", kind)["verdict"] != "DECLINED" and rc == 1 and doc["verdict"] == "FAIL"


@pytest.mark.parametrize("kind", ["loop", "alloc"])
def test_fix_a_row_sha_that_does_not_verify_is_not_a_decline(tmp_path, monkeypatch, world, kind):
    """[FIX] erratum v1.1a 1 (Sol P17): the reported `row_sha256` must equal the row on disk."""
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, verdicts={("rust", kind): "not_observed:kill"}, bad_row_sha={("rust", kind)})
    assert X.inject_of(doc, "rust", kind)["verdict"] != "DECLINED" and rc == 1


def test_fix_an_exception_message_never_carries_the_absolute_home_path(tmp_path, monkeypatch, world):
    """[FIX] AGENTS.md (public repo: no absolute home paths): an exception whose message holds a home-directory path is recorded
    as a problem, but the sealed record must not carry the path itself."""
    home = os.path.expanduser("~")
    if len(home) < 4:
        pytest.skip("no usable home directory")

    def boom(*args):
        raise OSError(f"cannot read {home}/.gradle/caches/x.bin")
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, hooks={"grade": boom})
    assert rc == 1 and ph.sealed_ok(doc)
    assert any(line.startswith("exception: OSError: ") for line in doc["problems"])
    assert home not in json.dumps(doc)


# ---------------------------------------------------------------------------------------------------- v8 (`positives_problems`)
def v8_problems(doc):
    return fz.positives_problems(doc, arm="n16", commit=X.COMMIT, identity=dict(X.IDENT), frozen_prompt_date=X.DATE,
                                 image_id=doc["image_id"])


def reseal(doc, edit):
    body = json.loads(json.dumps({k: v for k, v in doc.items() if k != "sha256"}))
    edit(body)
    return ph.seal(body)


def entry_of(body, lang, kind):
    (e,) = [i for i in body["injects"] if i["language"] == lang and i["kind"] == kind]
    return e


@pytest.fixture
def declined_record(tmp_path, monkeypatch, world):
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, verdicts={("rust", "loop"): "not_observed:kill",
                                                                 ("cpp", "alloc"): "not_observed:kill"})
    assert rc == 0 and X.inject_of(doc, "rust", "loop")["verdict"] == "DECLINED"
    return doc


def swap_verdict(entry, new):
    """Replace the verify verdict held in `declined_evidence` (its key name is the implementer's)."""
    ev_doc = entry["declined_evidence"]
    keys = [k for k, v in ev_doc.items() if isinstance(v, str) and v.startswith(("not_observed", "FAIL", "PASS"))]
    assert keys, ev_doc
    ev_doc[keys[0]] = new


def test_inv_v8_still_accepts_an_all_pass_record(tmp_path, monkeypatch, world):
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world)
    assert v8_problems(doc) == []


def test_new_v8_accepts_declined_for_loop_and_alloc_with_valid_evidence(declined_record):
    assert v8_problems(declined_record) == []


@pytest.mark.parametrize("kind_lang", [("cpp", "alloc"), ("rust", "loop")])
def test_fix_v8_refuses_declined_with_fail_no_shell_part(declined_record, kind_lang):
    """[FIX] erratum v1.1a 1: `FAIL:no_shell_part` is a failure, never an allowed decline verdict (it was, in v1.1)."""
    lang, kind = kind_lang
    doc = reseal(declined_record, lambda b: swap_verdict(entry_of(b, lang, kind), "FAIL:no_shell_part"))
    assert v8_problems(doc)


def test_fix_v8_refuses_declined_for_stall(declined_record):
    def edit(b):
        e = entry_of(b, "rust", "stall")
        e["verdict"], e["declined_evidence"] = "DECLINED", dict(entry_of(b, "rust", "loop")["declined_evidence"])
    assert v8_problems(reseal(declined_record, edit))


@pytest.mark.parametrize("verdict", ["PASS", "FAIL:rss", "FAIL:unrelated_kill", "competing_trigger:T", "FAIL:no_shell_part"])
def test_fix_v8_refuses_declined_with_a_verify_verdict_outside_the_allowed_set(declined_record, verdict):
    doc = reseal(declined_record, lambda b: swap_verdict(entry_of(b, "rust", "loop"), verdict))
    assert v8_problems(doc)


def test_fix_v8_refuses_declined_without_evidence(declined_record):
    assert v8_problems(reseal(declined_record, lambda b: entry_of(b, "rust", "loop").pop("declined_evidence")))
    assert v8_problems(reseal(declined_record, lambda b: entry_of(b, "rust", "loop").update(declined_evidence=None)))
    assert v8_problems(reseal(declined_record, lambda b: entry_of(b, "rust", "loop").update(declined_evidence={})))


def test_fix_v8_refuses_a_failed_record_whatever_it_holds(declined_record):
    def edit(b):
        b["verdict"], b["problems"] = "FAIL", ["rust stall: not_observed"]
    assert v8_problems(reseal(declined_record, edit))


def test_inv_v8_still_refuses_any_other_non_pass_verdict(declined_record):
    def edit(b):
        entry_of(b, "java", "loop")["verdict"] = "not_observed:kill"
    assert v8_problems(reseal(declined_record, edit))
    assert v8_problems(reseal(declined_record, lambda b: entry_of(b, "java", "alloc").update(verdict="")))


# ---------------------------------------------------------------------------------------------------- hybrid: the REAL box seams
FAKE_PROBE = """#!/bin/sh
case "$1" in
  *run_tg2_probe.py)
    out=""; prev=""
    for x in "$@"; do [ "$prev" = "--out" ] && out="$x"; prev="$x"; done
    base=$(basename "$out"); kind="${{base%%.*}}"
    cp "{prep}/$kind.attempt1.jsonl" "$out" && cp "{prep}/$kind.attempt1.manifest.json" "${{out%.jsonl}}.manifest.json"
    exit 0;;
esac
exec "{python}" "$@"
"""


class HybridOps(W2.BoxSeqOps):
    """The real `BoxSeqOps.positive_inject` / `inject_verify` (so the REAL `m62/inject_verify.py` judges real-shaped rows); the
    worktree's probe interpreter copies the prepared per-kind row; worktree / identity / grade / session / host are faked."""

    def __init__(self, tmp_path, world, prepared_events, shapes=None):
        super().__init__(Path(tmp_path) / "wd", main_root=Path(tmp_path) / "main", evidence_stage=Path(tmp_path) / "ev",
                         lever="kv", corpus="tg2")
        self.world, self.tmp = world, Path(tmp_path)
        prep = self.tmp / "prep"
        for kind in X.KINDS:
            X.write_inject_run(prep / kind, self.wd, kind, 1, prepared_events[kind], gate_stop="stalled" if kind == "stall" else None,
                               shape=(shapes or {}).get(kind))
            for suffix in (".jsonl", ".manifest.json"):
                (prep / f"{kind}.attempt1{suffix}").write_bytes((prep / kind / f"{kind}.attempt1{suffix}").read_bytes())

        def interrupted(row, manifest):               # S27 §4.5: the harness stopped it with a generation in flight
            row["termination"].update(reason="interrupt", in_flight_at_kill=1,
                                      worker_summary_before=dict(in_flight=1, requests_started=6, requests_completed=5),
                                      worker_summary_after=dict(in_flight=0, requests_started=6, requests_completed=5))
            row["reconciliation"] = dict(row.get("reconciliation") or {}, trailing="interrupted")
            row["stop_reason"] = "interrupt"
        X.write_inject_run(prep / "interrupt", self.wd, "interrupt", 1, stall_events(), gate_stop="interrupt", shape="keep",
                           mutate=interrupted)
        for suffix in (".jsonl", ".manifest.json"):
            (prep / f"interrupt.attempt1{suffix}").write_bytes((prep / "interrupt" / f"interrupt.attempt1{suffix}").read_bytes())
        wt = self.tmp / "wt-n16"
        (wt / "benchmark/m62").mkdir(parents=True)
        os.symlink(X.BENCH / "m62" / "inject_verify.py", wt / "benchmark/m62/inject_verify.py")
        (wt / "benchmark/run_tg2_probe.py").write_text("raise SystemExit('never run')\n")
        py = wt / ".venv-bench/bin/python"
        py.parent.mkdir(parents=True)
        py.write_text(FAKE_PROBE.format(prep=prep, python=sys.executable))
        py.chmod(0o755)
        self.wt = wt

    def host_env(self):
        return self.world.fingerprint()

    def worktree_state(self, path):
        return dict(head=X.COMMIT, clean=True, gitlinks=dict(X.GITLINKS))

    def identity(self, path):
        return dict(X.IDENT)

    def positive_grade(self, lang, item, variant):
        passed = variant == "reference"
        return dict(outcome="parsed", passed=passed, failing=0 if passed else 3, leaves=5 if passed else 2)

    def positives_session(self, worktree, *, frozen_prompt_date):
        from contextlib import contextmanager
        ops = self

        @contextmanager
        def session():
            out_root = ops.wd / "m65" / "inject" / "positives-x"
            out_root.mkdir(parents=True, exist_ok=True)
            ops._pos = dict(ops=SimpleNamespace(env_base=lambda: dict(os.environ)), wt=ops.wt, out_root=out_root,
                            date=frozen_prompt_date, receipt=ops.tmp / "a4.json")
            try:
                yield ops
            finally:
                ops._pos = None
        return session()


def stall_events():
    lines = []
    for n in range(1, 6):
        lines += X.ev_step(n)
    return lines


def hybrid(tmp_path, monkeypatch, world, *, loop, alloc, shapes=None):
    ops = HybridOps(tmp_path, world, dict(stall=stall_events(), loop=loop, alloc=alloc), shapes)
    rc, out = X.positives(tmp_path, monkeypatch, ops)
    return rc, X.record(out)


def test_fix_real_verify_declined_where_the_model_never_looped_or_allocated(tmp_path, monkeypatch, world):
    """[FIX] the whole chain with the REAL `inject_verify` verdicts (stall: PASS; loop: `not_observed`; alloc: `not_observed:kill`),
    every language: the record PASSES with the loop / alloc runs DECLINED and `verify_result` recorded per run; v8 accepts it."""
    rc, doc = hybrid(tmp_path, monkeypatch, world, loop=X.default_events(), alloc=X.default_events())
    assert doc["problems"] == [] and rc == 0 and doc["verdict"] == "PASS"
    for lang in X.LANGS:
        assert X.inject_of(doc, lang, "stall")["verdict"] == "PASS"
        for kind in ("loop", "alloc"):
            e = X.inject_of(doc, lang, kind)
            assert e["verdict"] == "DECLINED" and e["declined_evidence"]
            assert isinstance(e.get("verify_result"), str) and e["verify_result"]
    assert v8_problems(doc) == []


def test_fix_real_verify_a_model_that_ran_the_command_but_was_not_observed_fails(tmp_path, monkeypatch, world):
    """[FIX] the model DID run `sleep 600` (the events say so) yet the harness saw no loop: not a decline, a FAIL, v8 refuses."""
    rc, doc = hybrid(tmp_path, monkeypatch, world, loop=X.default_events() + [loop_call()], alloc=X.default_events())
    assert rc == 1 and doc["verdict"] == "FAIL"
    assert all(X.inject_of(doc, lang, "loop")["verdict"] != "DECLINED" for lang in X.LANGS)
    assert all(X.inject_of(doc, lang, "alloc")["verdict"] == "DECLINED" for lang in X.LANGS)
    assert v8_problems(doc)


def test_fix_real_verify_a_not_observed_row_with_a_client_kill_is_not_declined(tmp_path, monkeypatch, world):
    """[FIX] erratum v1.1b 9 end to end: the real `inject_verify` says `not_observed` for the loop row, but the row records a client
    kill (`termination.killed` non-empty): not a decline. The alloc rows (normally completed) are still declined."""
    rc, doc = hybrid(tmp_path, monkeypatch, world, loop=X.default_events(), alloc=X.default_events(),
                     shapes=dict(loop="client_kill"))
    assert rc == 1 and all(X.inject_of(doc, lang, "loop")["verdict"] != "DECLINED" for lang in X.LANGS)
    assert all(X.inject_of(doc, lang, "alloc")["verdict"] == "DECLINED" for lang in X.LANGS)


def test_fix_the_box_inject_verify_returns_the_real_verdict_not_a_bare_exit_code(tmp_path, monkeypatch, world):
    """[FIX] baseline: `BoxSeqOps.inject_verify` collapses every non-zero exit to `FAIL (inject_verify rc N)`, so a `not_observed`
    (rc 4) cannot be told from a FAIL (rc 1). The spec needs the verdict itself."""
    ops = HybridOps(tmp_path, world, dict(stall=stall_events(), loop=X.default_events(), alloc=X.default_events()))
    with ops.positives_session(ops.wt, frozen_prompt_date=X.DATE):
        res = ops.positive_inject("rust", "rust/say", "loop", seed=1001, attempt=1)
        verdict = ops.inject_verify(res["run"], "loop")
    text = verdict if isinstance(verdict, str) else json.dumps(verdict)
    assert "not_observed" in text and "inject_verify rc" not in text
