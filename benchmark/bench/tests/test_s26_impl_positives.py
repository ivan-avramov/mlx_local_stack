"""S26 §2 / §4 (implementer tests): the tg2 positives under C360 / C361 (1) — a host change or an exception gives a sealed FAIL
record; per kind PASS / DECLINED / FAIL from real-shaped inject rows and events (`OpencodeArm.row_fields`), stall never DECLINED,
`FAIL:rss` stays FAIL, tampered evidence or a planted command run by the model is a FAIL; v8 (`positives_problems`) accepts
DECLINED for loop / alloc only and only with valid evidence; the box's inject_verify parsing."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from bench import p426_freeze as fz
from bench import p426_hooks as ph
from bench import p426_wave2 as W2
from bench.tests.test_m76_b4b1_impl_wave2 import COMMIT, DATE, IDENT, LANGS, PosOps, _positives, wd  # noqa: F401  (fixture)

FP = dict(path="/opt/homebrew/bin:/usr/bin:/bin", tools={"cargo": "absent"}, cellar=["rust/1.80.0"], bin_dirs={},
          npm_global=None, home_toolchains={".gradle": "absent"}, files={"tg2 gradle.properties": "absent"})


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tool(command, tool_name="shell", n=1):
    return dict(type="tool_use", sessionID="s1", part=dict(id=f"p{n}", messageID=f"m{n}", tool=tool_name, callID=f"c{n}",
                                                            state=dict(status="completed", input=dict(command=command),
                                                                       time=dict(start=1000, end=2000))))


def step(n):
    return [dict(type="step_start", sessionID="s1", part=dict(id=f"s{n}", messageID=f"m{n}")),
            dict(type="step_finish", sessionID="s1", part=dict(id=f"f{n}", messageID=f"m{n}"))]


def write_run(run, lang, kind, attempt, events, tamper=None, extra=None):
    """A tg2 inject run's row as the probe writes it (the real `OpencodeArm.row_fields` over the real evidence suffixes);
    `extra` adds row fields (e.g. a recorded kill)."""
    from bench import arm_opencode as ao
    run.mkdir(parents=True, exist_ok=True)
    arm = ao.OpencodeArm(None, mode="tg1", scaffold="tg2")
    stem = run / "evidence" / f"{lang}__{kind}{attempt}"
    stem.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for key, suffix in dict(arm.evidence_suffixes()).items():
        path = stem.with_name(stem.name + suffix)
        path.write_text("".join(json.dumps(e) + "\n" for e in events) if key == "events" else "{}" if key == "export"
                        else f"{key}\n")
        artifacts[key] = path
    fields = ao.OpencodeArm.row_fields(arm, version="2.0.20", rc=0, artifacts=artifacts, sha_of=sha, portable=str)
    row = dict(fields, id=f"{lang}/item", scaffold=f"opencode-v2-web-tg2-inject:{kind}", mem_kills=[],
               termination=dict(reason=None, killed=[]))
    row.update(extra or {})
    path = run / (f"{kind}.attempt{attempt}" + ".jsonl")
    path.write_text(json.dumps(row) + "\n")
    if tamper == "events":
        with open(artifacts["events"], "a") as f:
            f.write(json.dumps(step(9)[0]) + "\n")
    return path, artifacts


class HostPosOps(PosOps):
    def __init__(self, base, *, verdicts=None, events=None, change_at=None, raise_at=None, grade_raise=False, tamper=None,
                 wrong_row_sha=(), probe_rc=None, row_extra=None, **kw):
        super().__init__(**kw)
        self.base, self.fp = Path(base), copy.deepcopy(FP)
        self.verdicts, self.events = dict(verdicts or {}), dict(events or {})
        self.change_at, self.raise_at, self.grade_raise = change_at, raise_at, grade_raise
        self.tamper, self.wrong_row_sha, self.rows = dict(tamper or {}), set(wrong_row_sha), {}
        self.probe_rc, self.row_extra = dict(probe_rc or {}), dict(row_extra or {})

    def host_env(self):
        return copy.deepcopy(self.fp)

    def positive_grade(self, lang, item, variant):
        if self.grade_raise:
            raise RuntimeError("grade boom")
        return super().positive_grade(lang, item, variant)

    def positive_inject(self, lang, item, kind, *, seed, attempt):
        self.runs.append((lang, kind, attempt))
        if (lang, kind) == self.change_at:
            self.fp["cellar"] = self.fp["cellar"] + ["openjdk@17/17.0.12"]
        if (lang, kind) == self.raise_at:
            raise RuntimeError("inject boom")
        run = self.base / lang
        if self.aborts.get((lang, kind), 0) >= attempt:
            return dict(transport_abort=True, run=str(run))
        path, arts = write_run(run, lang, kind, attempt, self.events.get((lang, kind), [*step(1), tool("ls -la")]),
                               tamper=self.tamper.get((lang, kind)), extra=self.row_extra.get((lang, kind)))
        self.rows[(lang, kind)] = (path, arts)
        row_sha = "0" * 64 if (lang, kind) in self.wrong_row_sha else sha(path)
        out = dict(transport_abort=False, run=str(run), rc=self.probe_rc.get((lang, kind), 0), row_sha256=row_sha,
                   evidence_sha256="e" * 64)
        if out["rc"] == "absent":
            out.pop("rc")
        return out

    def inject_verify(self, run, kind):
        return self.verdicts.get((Path(run).name, kind), "PASS")


def entries(doc):
    return {(p["language"], p["kind"]): p for p in doc["injects"]}


def run_pos(wd, **kw):
    ops = HostPosOps(wd / "inject", **kw)
    rc, out = _positives(wd, ops)
    doc = json.loads(out.read_text())
    assert ph.sealed_ok(doc)
    return rc, doc, ops


def v8_problems(doc):
    from bench import tg2_grade
    return fz.positives_problems(doc, arm="n16", commit=COMMIT["n16"], identity=IDENT, frozen_prompt_date=DATE,
                                 image_id=tg2_grade.pinned_image_id())


def reseal(doc, mutate):
    body = copy.deepcopy({k: v for k, v in doc.items() if k != "sha256"})
    mutate(body)
    return ph.seal(body)


# ----------------------------------------------------------------------------------------------- host environment, exceptions
def test_a_clean_record_carries_both_fingerprints_and_passes_v8(wd):
    rc, doc, _ = run_pos(wd)
    assert rc == 0 and doc["verdict"] == "PASS" and doc["host_env"] == FP and doc["host_env_after"] == FP
    assert all(p["verdict"] == "PASS" and p["verify_verdict"] == "PASS" and "verify_result" in p for p in doc["injects"])
    assert v8_problems(doc) == []


def test_a_host_change_during_the_positives_is_a_fail(wd):
    rc, doc, _ = run_pos(wd, change_at=("java", "loop"))
    assert rc == 1 and doc["verdict"] == "FAIL"
    assert "host environment changed during the leg: Homebrew Cellar: added openjdk@17/17.0.12" in doc["problems"]
    assert doc["host_env"] == FP and "openjdk@17/17.0.12" in doc["host_env_after"]["cellar"]
    assert v8_problems(doc)


def test_an_inject_exception_gives_a_sealed_fail_record_and_closes_the_session(wd):
    rc, doc, ops = run_pos(wd, raise_at=("cpp", "alloc"))
    assert rc == 1 and doc["verdict"] == "FAIL"
    assert "exception: RuntimeError: inject boom" in doc["problems"]
    assert ops.served[-1] == ("stop",) and doc["host_env_after"] == FP
    assert ("cpp", "alloc") not in entries(doc)


def test_a_grade_exception_before_the_session_still_writes_the_record(wd):
    rc, doc, ops = run_pos(wd, grade_raise=True)
    assert rc == 1 and doc["problems"] == ["exception: RuntimeError: grade boom"]
    assert ops.served == [] and doc["host_env_after"] == FP and doc["injects"] == []


def test_without_the_seam_the_record_has_null_fingerprints(wd):
    rc, out = _positives(wd, PosOps())
    doc = json.loads(out.read_text())
    assert rc == 0 and doc["host_env"] is None and doc["host_env_after"] is None and doc["verdict"] == "PASS"


# ----------------------------------------------------------------------------------------------- PASS / DECLINED / FAIL per kind
def test_loop_and_alloc_declined_by_the_model_are_recorded_and_accepted_by_v8(wd):
    events = {("java", "loop"): [*step(1), tool("ls -la"), *step(2)],
              ("cpp", "alloc"): [*step(1), tool("python3 -c 'print(1)'")]}
    rc, doc, ops = run_pos(wd, verdicts={("java", "loop"): "not_observed", ("cpp", "alloc"): "not_observed:kill"},
                           events=events)
    assert rc == 0 and doc["verdict"] == "PASS", doc["problems"]
    e = entries(doc)
    for (lang, kind), marker, verdict in ((("java", "loop"), "sleep 600", "not_observed"),
                                          (("cpp", "alloc"), "bytearray(", "not_observed:kill")):
        path, arts = ops.rows[(lang, kind)]
        assert e[(lang, kind)]["verdict"] == "DECLINED"
        assert e[(lang, kind)]["declined_evidence"] == dict(events_sha256=sha(arts["events"]), marker=marker,
                                                            verify_verdict=verdict, kills=0, probe_rc=0,
                                                            row_sha256=sha(path))
    assert v8_problems(doc) == []


def test_alloc_no_shell_part_is_never_declined(wd):
    """Erratum 1: `FAIL:no_shell_part` stays a failure, even with no marker call in the events."""
    rc, doc, _ = run_pos(wd, verdicts={("cpp", "alloc"): "FAIL:no_shell_part"})
    assert rc == 1 and entries(doc)[("cpp", "alloc")]["verdict"] == "FAIL:no_shell_part"
    assert "cpp alloc: FAIL:no_shell_part" in doc["problems"] and "declined_evidence" not in entries(doc)[("cpp", "alloc")]


@pytest.mark.parametrize("kind,command", [("loop", "sleep 600 & wait"), ("alloc", "python3 -c 'x = bytearray(10**11)'")])
def test_a_planted_command_the_model_ran_is_a_fail(wd, kind, command):
    verdict = "not_observed:kill"
    rc, doc, _ = run_pos(wd, verdicts={("rust", kind): verdict}, events={("rust", kind): [*step(1), tool(command, "bash")]})
    e = entries(doc)[("rust", kind)]
    assert rc == 1 and e["verdict"] == verdict and f"rust {kind}: {verdict}" in doc["problems"]
    assert "the model ran it" in e["not_declined"]


@pytest.mark.parametrize("extra", [dict(mem_kills=[dict(role="model", rss=1, argv=["python3"])]),
                                   dict(termination=dict(reason="client_exit_hang", killed=[dict(pid=1, role="client")])),
                                   dict(mem_kills=None), dict(termination=None)])
def test_a_row_that_records_a_kill_is_not_declined(wd, extra):
    """Erratum 1: DECLINED needs a row that records no kill (`mem_kills` and `termination.killed` present and empty)."""
    rc, doc, _ = run_pos(wd, verdicts={("java", "alloc"): "not_observed:kill"}, row_extra={("java", "alloc"): extra})
    e = entries(doc)[("java", "alloc")]
    assert rc == 1 and e["verdict"] == "not_observed:kill" and "kill" in e["not_declined"]


@pytest.mark.parametrize("rc_value", [1, "absent"])
def test_a_decline_needs_probe_rc_0(wd, rc_value):
    """Sol P17: a nonzero (or unrecorded) probe exit is never DECLINED."""
    rc, doc, _ = run_pos(wd, verdicts={("java", "loop"): "not_observed"}, probe_rc={("java", "loop"): rc_value})
    e = entries(doc)[("java", "loop")]
    assert rc == 1 and e["verdict"] != "DECLINED" and "declined_evidence" not in e
    if rc_value == 1:
        assert e["verdict"] == "FAIL:probe_rc:1" and e["verify_verdict"] == "not_observed"


def test_a_pass_needs_probe_rc_0_and_the_recorded_row(wd):
    """Sol P17: PASS with a nonzero probe exit, or with a row that is not the recorded one, is a probe failure."""
    rc, doc, _ = run_pos(wd, probe_rc={("rust", "stall"): 2}, wrong_row_sha={("cpp", "loop")})
    e = entries(doc)
    assert rc == 1 and e[("rust", "stall")]["verdict"] == "FAIL:probe_rc:2"
    assert e[("cpp", "loop")]["verdict"] == "FAIL:row_sha256"
    assert {"rust stall: FAIL:probe_rc:2", "cpp loop: FAIL:row_sha256"} <= set(doc["problems"])


def test_alloc_fail_rss_without_the_marker_stays_a_fail(wd):
    rc, doc, _ = run_pos(wd, verdicts={("java", "alloc"): "FAIL:rss"})
    assert rc == 1 and entries(doc)[("java", "alloc")]["verdict"] == "FAIL:rss"
    assert "declined_evidence" not in entries(doc)[("java", "alloc")]


def test_stall_is_never_declined(wd):
    rc, doc, _ = run_pos(wd, verdicts={("rust", "stall"): "not_observed"})
    assert rc == 1 and entries(doc)[("rust", "stall")]["verdict"] == "not_observed"


@pytest.mark.parametrize("how", ["events", "row"])
def test_evidence_that_does_not_verify_is_a_fail(wd, how):
    kw = dict(tamper={("javascript", "loop"): "events"}) if how == "events" else dict(wrong_row_sha={("javascript", "loop")})
    rc, doc, _ = run_pos(wd, verdicts={("javascript", "loop"): "not_observed"}, **kw)
    e = entries(doc)[("javascript", "loop")]
    assert rc == 1 and e["verdict"] == "not_observed" and "javascript loop: not_observed" in doc["problems"]
    why = "does not verify against evidence_sha256" if how == "events" else "not the one the inject run recorded"
    assert why in e["not_declined"]


def test_a_transport_abort_stays_a_fail(wd):
    rc, doc, _ = run_pos(wd, aborts={("cpp", "loop"): 2})
    assert rc == 1 and entries(doc)[("cpp", "loop")]["verdict"] == "TRANSPORT_ABORT"
    assert entries(doc)[("cpp", "loop")]["attempts"] == 2


# ----------------------------------------------------------------------------------------------- v8
def test_v8_accepts_declined_only_for_loop_and_alloc_with_valid_evidence(wd):
    rc, doc, _ = run_pos(wd, verdicts={("java", "loop"): "not_observed"})
    assert rc == 0 and v8_problems(doc) == []
    good = entries(doc)[("java", "loop")]["declined_evidence"]

    def set_entry(lang, kind, **fields):
        def mutate(body):
            for p in body["injects"]:
                if (p["language"], p["kind"]) == (lang, kind):
                    p.update(fields)
                    for k in [k for k, v in fields.items() if v is None]:
                        p.pop(k)
        return mutate
    stall = reseal(doc, set_entry("rust", "stall", verdict="DECLINED", declined_evidence=dict(good, marker="sleep 600")))
    assert any("rust stall" in p for p in v8_problems(stall))
    rss = reseal(doc, set_entry("java", "loop", declined_evidence=dict(good, verify_verdict="FAIL:rss")))
    assert any("java loop" in p for p in v8_problems(rss))
    bare = reseal(doc, set_entry("java", "loop", declined_evidence=None))
    assert any("java loop" in p for p in v8_problems(bare))
    wrong_marker = reseal(doc, set_entry("java", "loop", declined_evidence=dict(good, marker="bytearray(")))
    assert any("java loop" in p for p in v8_problems(wrong_marker))
    cpp_row = entries(doc)[("cpp", "alloc")]["row_sha256"]
    alloc = reseal(doc, set_entry("cpp", "alloc", verdict="DECLINED",
                                  declined_evidence=dict(good, marker="bytearray(", verify_verdict="not_observed:kill",
                                                         row_sha256=cpp_row)))
    assert v8_problems(alloc) == []
    for bad in (dict(verify_verdict="FAIL:no_shell_part"), dict(kills=1), dict(kills=None), dict(probe_rc=1),
                dict(probe_rc=None), dict(probe_rc=False)):
        refused = reseal(doc, set_entry("java", "loop", declined_evidence=dict(good, **bad)))
        assert any("java loop" in p for p in v8_problems(refused)), bad


def test_v8_declined_needs_the_entrys_row_sha256_in_its_evidence(wd):
    """Erratum 11 (Sol P2, round 2): v8 accepts DECLINED only when `declined_evidence.row_sha256` is 64-hex and equals the
    entry's `row_sha256`; an altered / removed / malformed one, or an entry without its row hash, is refused."""
    rc, doc, _ = run_pos(wd, verdicts={("java", "loop"): "not_observed"})
    e = entries(doc)[("java", "loop")]
    assert rc == 0 and e["verdict"] == "DECLINED" and e["declined_evidence"]["row_sha256"] == e["row_sha256"]
    assert v8_problems(doc) == []

    def edit(evidence=None, entry=None):
        def mutate(body):
            for p in body["injects"]:
                if (p["language"], p["kind"]) == ("java", "loop"):
                    for target, changes in ((p["declined_evidence"], evidence or {}), (p, entry or {})):
                        for k, v in changes.items():
                            target.pop(k) if v is None else target.__setitem__(k, v)
        return mutate
    other = "f" * 64 if e["row_sha256"] != "f" * 64 else "e" * 64
    for kw in (dict(evidence=dict(row_sha256=other)), dict(evidence=dict(row_sha256=None)),
               dict(evidence=dict(row_sha256=e["row_sha256"].upper())), dict(evidence=dict(row_sha256=e["row_sha256"][:63])),
               dict(entry=dict(row_sha256=None)), dict(entry=dict(row_sha256=other)),
               dict(evidence=dict(row_sha256="x"), entry=dict(row_sha256="x"))):
        assert any("java loop" in p for p in v8_problems(reseal(doc, edit(**kw)))), kw


def test_declinable_verdicts():
    for v in ("not_observed", "not_observed:kill", "not_observed:descendant"):
        assert fz.declinable_verify_verdict(v)
    for v in ("PASS", "FAIL:rss", "FAIL:no_shell_part", "FAIL:transport_abort", "TRANSPORT_ABORT", None,
              "FAIL (inject_verify rc 4)", "competing_trigger:T", "not_observedX"):
        assert not fz.declinable_verify_verdict(v)
    assert fz.DECLINE_MARKERS == {"loop": "sleep 600", "alloc": "bytearray("}


# ----------------------------------------------------------------------------------------------- the box's inject_verify
def test_parse_inject_verify_takes_the_retained_attempt_and_the_result_line():
    out = ("loop.attempt1: FAIL:transport_abort  [retry: not clearance evidence]\nloop.attempt2: not_observed\n"
           "loop.attempt2:   note cancellation_not_shown\nRESULT retryable (exit 4)\n")
    assert W2.parse_inject_verify(out, "loop") == ("not_observed", "RESULT retryable (exit 4)")
    assert W2.parse_inject_verify("alloc: FAIL:missing (no file in /x)\nRESULT FAIL\n", "alloc") == ("FAIL:missing", "RESULT FAIL")
    assert W2.parse_inject_verify("stall.attempt1: PASS\nRESULT stall PASS\n", "stall") == ("PASS", "RESULT stall PASS")


@pytest.mark.parametrize("stdout, code, verdict", [
    ("loop.attempt1: not_observed\\nRESULT retryable (exit 4)\\n", 4, "not_observed"),
    ("loop.attempt1: FAIL:loop_threshold\\nRESULT FAIL\\n", 1, "FAIL:loop_threshold"),
    ("loop.attempt1: PASS\\nRESULT loop PASS\\n", 0, "PASS"),
    ("loop.attempt1: PASS\\nRESULT FAIL\\n", 1, "FAIL:inconsistent:PASS:rc1"),
    ("Traceback\\n", 2, "FAIL:no_verdict:rc2")])
def test_the_box_inject_verify_returns_the_retained_attempts_verdict(tmp_path, stdout, code, verdict):
    """Erratum 3: `BoxSeqOps.inject_verify` returns the retained attempt's verdict string, never a bare exit code."""
    wt = tmp_path / "wt"
    py = wt / ".venv-bench/bin/python"
    py.parent.mkdir(parents=True)
    py.write_text(f"#!/bin/sh\nprintf '{stdout}'\nexit {code}\n")
    py.chmod(0o755)
    ops = W2.BoxSeqOps(tmp_path, main_root=tmp_path / "main", evidence_stage=tmp_path / "ev", lever="kv", corpus="tg2")
    ops._pos = dict(wt=wt)
    assert ops.inject_verify(str(tmp_path / "run"), "loop") == verdict
    full = ops.inject_verify_result(str(tmp_path / "run"), "loop")
    assert full["verdict"] == verdict and full["rc"] == code


def test_the_box_host_env_calls_fingerprint_for_run_with_no_argument(tmp_path, monkeypatch):
    """Erratum 4."""
    from bench import host_env
    calls = []
    monkeypatch.setattr(host_env, "fingerprint_for_run", lambda *a, **kw: calls.append((a, kw)) or {"x": 1})
    ops = W2.BoxSeqOps(tmp_path, main_root=tmp_path / "main", evidence_stage=tmp_path / "ev", lever="kv", corpus="tg2")
    assert ops.host_env() == {"x": 1} and calls == [((), {})]
