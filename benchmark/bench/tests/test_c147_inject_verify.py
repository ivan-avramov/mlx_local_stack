"""C147 §2: inject_verify.py over fixture rows - every verdict, suite rule and exit code."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from m62 import inject_verify as iv                           # noqa: E402

PER_PROCESS = 512 * 1024 ** 2
RUN_IDS = {"stall": "20261010T120000-aaaaaaaaaaaa", "loop": "20261010T120000-bbbbbbbbbbbb",
           "alloc": "20261010T120000-cccccccccccc"}


def put(path, text):
    path.write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


def ev(kind, mid, **part):
    return json.dumps(dict(type=kind, sessionID="s1", part=dict(messageID=mid, **part)))


def tool_event(mid, call_id, command, state_extra=None):
    state = dict(status="completed", input={"command": command}, metadata={}, output="", title="shell",
                 time=dict(start=1, end=2))
    state.update(state_extra or {})
    return ev("tool_use", mid, id=call_id, tool="shell", state=state)


def build_events(kind):
    lines = []
    if kind == "stall":
        for k in range(1, 6):
            lines += [ev("step_start", f"m{k}", id=f"s{k}"), ev("step_finish", f"m{k}", id=f"f{k}")]
        lines.append(ev("step_start", "m6", id="s6"))
    elif kind == "loop":
        for k in range(1, 4):
            lines += [ev("step_start", f"m{k}", id=f"s{k}"),
                      tool_event(f"m{k}", f"c{k}", "sleep 600 >/dev/null 2>&1 & sleep 1")]
            if k < 3:
                lines.append(ev("step_finish", f"m{k}", id=f"f{k}"))
    else:
        lines += [ev("step_start", "m1", id="s1"),
                  tool_event("m1", "call_alloc", 'python3 -c "bytearray(400)"',
                             dict(metadata=dict(metadata=dict(status="completed", signal="SIGKILL")))),
                  ev("step_finish", "m1", id="f1"), ev("step_start", "m2", id="s2"), ev("step_finish", "m2", id="f2")]
    return "\n".join(lines) + "\n"


def make_row(kind, tmp, name):
    ev_path, ex_path, err_path = (tmp / f"{name}.events.jsonl", tmp / f"{name}.json", tmp / f"{name}.stderr.txt")
    sha = dict(events=put(ev_path, build_events(kind)), export=put(ex_path, "{}"), stderr=put(err_path, ""))
    arts = {}
    for artifact in ("report.xml", "stdout.txt", "stderr.txt"):
        path = tmp / f"{name}.grade.{artifact}"
        arts[artifact] = dict(path=str(path), sha256=put(path, "x" + artifact))
    art = tmp / f"{name}.report.xml"
    worker = dict(pid=1, create_time=2.0, model_path="m", registry_sha256="a" * 64)
    summary_before = dict(in_flight=1, requests_started=4, requests_completed=3, requests_failed=0)
    summary_after = dict(in_flight=0, requests_started=4, requests_completed=3, requests_failed=1)
    term = dict(reason=None, killed=[], killed_verified=None, cancel_wait_s=None, in_flight_at_kill=None,
                worker_summary_before=None, worker_summary_after=None)
    gate = dict(stop_reason=None, no_progress_tokens=50, no_progress_requests=0, max_identical_run_live=1,
                baseline_failing=1, failing_trajectory=[[1, 1, False]], requests_completed=2)
    rec = dict(unmatched_export_messages=1, trailing="interrupted")
    mem = []
    if kind in ("stall", "loop"):
        stop = "stalled" if kind == "stall" else "looping"
        gate.update(stop_reason=stop, requests_completed=5 if kind == "stall" else 2)
        if kind == "stall":
            gate.update(no_progress_requests=5)
        else:
            gate.update(max_identical_run_live=3)
        killed = [dict(pid=10, create_time=1.0, role="client", argv=["opencode", "run"])]
        if kind == "loop":
            killed.append(dict(pid=11, create_time=1.5, role="model", argv=["sleep", "600"]))
        term.update(reason=stop, killed=killed, killed_verified=True, cancel_wait_s=2.5, in_flight_at_kill=1,
                    worker_summary_before=summary_before, worker_summary_after=summary_after)
    else:
        mem = [dict(pid=20, create_time=3.0, role="model", rss=PER_PROCESS + 1,
                    argv=["python3", "-c", 'import time; bytearray(400)'], tool_call_id="call_alloc",
                    carrying_request=1, completed_boundary_at_kill=0)]
        gate.update(requests_completed=2)
    row = dict(scaffold="opencode-v2-web-tg1-inject:" + kind, gate=gate, termination=term, reconciliation=rec,
               mem_kills=mem, worker_before=worker, worker_after=worker,
               events_path=str(ev_path), transcript_path=str(ex_path), stderr_path=str(err_path),
               evidence_sha256=sha, request_usage=[["1", 10, 100, 81920]],
               id="python/one", test_modified=False,
               grade_reports=[dict(boundary=1, seq=1, final=True, outcome="parsed", artifacts=arts)],
               orphans_unattributed=[])
    manifest = dict(run_id=RUN_IDS[kind], runtime=dict(
        scaffold=row["scaffold"],
        inject=dict(kind=kind, policy=dict(gate={}, hygiene=dict(per_process=PER_PROCESS)))))
    return row, manifest


def write_attempt(run, kind, n=1, mutate=None):
    row, manifest = make_row(kind, run, f"{kind}.attempt{n}")
    if mutate:
        mutate(row, manifest)
    stem = run / f"{kind}.attempt{n}"
    (run / f"{kind}.attempt{n}.jsonl").write_text(json.dumps(row) + "\n")
    (run / f"{kind}.attempt{n}.manifest.json").write_text(json.dumps(manifest))
    return row


def verdict(tmp_path, kind, mutate=None):
    write_attempt(tmp_path, kind, 1, mutate)
    lines = []
    code = iv.main(["--run", str(tmp_path), "--kind", kind, "--workdir", str(tmp_path)], out=lines.append)
    first = lines[0]
    assert first.startswith(f"{kind}.attempt1: ")
    return first.split(": ", 1)[1].split("  [")[0], code, lines


@pytest.mark.parametrize("kind", ["stall", "loop", "alloc"])
def test_pass_for_each_kind(tmp_path, kind):
    v, code, lines = verdict(tmp_path, kind)
    assert v == "PASS" and code == 0 and lines[-1] == f"RESULT {kind} PASS"


def test_label_mismatch_and_runtime_inject_kind(tmp_path):
    assert verdict(tmp_path, "stall", lambda r, m: r.update(scaffold="opencode-v2-web-tg1"))[0] == "FAIL:label"


def test_sha_mismatch_and_grade_report_sha_mismatch_fail(tmp_path):
    v, code, _ = verdict(tmp_path, "stall", lambda r, m: r["evidence_sha256"].update(events="0" * 64))
    assert v == "FAIL:evidence_sha:events" and code == 1
    v, _, _ = verdict(tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path, "stall",
                      lambda r, m: r["grade_reports"][0]["artifacts"]["report.xml"].update(sha256="1" * 64))
    assert v.startswith("FAIL:grade_report_sha")


def test_empty_evidence_sha_fails(tmp_path):
    assert verdict(tmp_path, "loop", lambda r, m: r["evidence_sha256"].update(stderr=""))[0] == \
        "FAIL:evidence_sha:stderr"


def test_worker_drift_fails(tmp_path):
    def drift(r, m):
        r["worker_after"] = dict(r["worker_after"], create_time=9.0)
    assert verdict(tmp_path, "alloc", drift)[0] == "FAIL:worker_drift"


def test_non_firing_kind_is_not_observed_exit_4(tmp_path):
    v, code, _ = verdict(tmp_path, "stall", lambda r, m: r["gate"].update(stop_reason=None))
    assert v == "not_observed" and code == 4
    v, code, _ = verdict(tmp_path / "a" if (tmp_path / "a").mkdir() is None else tmp_path, "loop",
                         lambda r, m: r["gate"].update(stop_reason=None))
    assert v == "not_observed" and code == 4


def test_competing_triggers(tmp_path):
    assert verdict(tmp_path, "stall", lambda r, m: r["gate"].update(no_progress_tokens=81920))[0] == \
        "competing_trigger:T"
    d = tmp_path / "b"
    d.mkdir()
    assert verdict(d, "stall", lambda r, m: r["gate"].update(stop_reason="looping"))[0] == "competing_trigger:looping"
    d = tmp_path / "c"
    d.mkdir()
    v, code, _ = verdict(d, "loop", lambda r, m: r["gate"].update(stop_reason="stalled"))
    assert v == "competing_trigger:stalled" and code == 4


def test_alloc_unrelated_kill_fails_and_absent_kill_is_not_observed(tmp_path):
    def unrelated(r, m):
        r["mem_kills"][0]["argv"] = ["chrome", "--type=renderer"]
    v, code, _ = verdict(tmp_path, "alloc", unrelated)
    assert v == "FAIL:unrelated_kill" and code == 1
    d = tmp_path / "n"
    d.mkdir()
    assert verdict(d, "alloc", lambda r, m: r.update(mem_kills=[]))[0] == "not_observed:kill"


@pytest.mark.parametrize("field,value,expected", [
    ("tool_call_id", "other", "FAIL:tool_call_id"),
    ("carrying_request", 2, "FAIL:request_linkage"),
    ("completed_boundary_at_kill", 1, "FAIL:request_linkage"),
    ("rss", PER_PROCESS, "FAIL:rss"),
    ("role", "grader", "FAIL:unrelated_kill"),
])
def test_alloc_linkage_checks(tmp_path, field, value, expected):
    assert verdict(tmp_path, "alloc", lambda r, m: r["mem_kills"][0].update({field: value}))[0] == expected


def test_alloc_without_continuation_and_with_a_clean_part_state(tmp_path):
    v, code, _ = verdict(tmp_path, "alloc", lambda r, m: r["gate"].update(requests_completed=1))
    assert v == "not_observed:continuation" and code == 4
    d = tmp_path / "s"
    d.mkdir()

    def clean_exit(r, m):
        text = build_events("alloc").replace('"signal": "SIGKILL"', '"exit": 0')
        Path(r["events_path"]).write_text(text)
        r["evidence_sha256"]["events"] = hashlib.sha256(text.encode()).hexdigest()
    assert verdict(d, "alloc", clean_exit)[0] == "FAIL:killed_part_shape"


def test_stall_events_rederivation_must_agree(tmp_path):
    def fewer(r, m):
        text = "\n".join(build_events("stall").splitlines()[:6]) + "\n"          # only 3 finishes
        Path(r["events_path"]).write_text(text)
        r["evidence_sha256"]["events"] = hashlib.sha256(text.encode()).hexdigest()
    assert verdict(tmp_path, "stall", fewer)[0] == "FAIL:events_rederivation"


def test_loop_events_rederivation_must_show_three_identical_consecutive_calls(tmp_path):
    def varied(r, m):
        text = build_events("loop").replace('"c2"', '"c2"').replace(
            'sleep 600 >/dev/null 2>&1 & sleep 1', 'echo x', 1)
        Path(r["events_path"]).write_text(text)
        r["evidence_sha256"]["events"] = hashlib.sha256(text.encode()).hexdigest()
    assert verdict(tmp_path, "loop", varied)[0] == "FAIL:events_rederivation"


@pytest.mark.parametrize("mutation,expected", [
    (lambda r, m: r["termination"].update(killed_verified=False), "FAIL:causal:killed_verified"),
    (lambda r, m: r["termination"].update(cancel_wait_s=None), "FAIL:causal:cancel_wait_s"),
    (lambda r, m: r["termination"].update(cancel_wait_s=301), "FAIL:causal:cancel_wait_s"),
    (lambda r, m: r["termination"].update(killed=[], reason=None), "not_observed:kill"),
    (lambda r, m: r["reconciliation"].update(trailing="none"), "not_observed:trailing"),
    (lambda r, m: r["termination"].update(in_flight_at_kill=0), "not_observed:cancellation"),
    # registered negative case: the request COMPLETED between the samples (success counter rose) -> not a cancel
    (lambda r, m: r["termination"].update(worker_summary_after=dict(in_flight=0, requests_started=4,
                                                                    requests_completed=4, requests_failed=0)),
     "not_observed:cancellation"),
    (lambda r, m: r["termination"].update(worker_summary_after=dict(in_flight=1, requests_started=4,
                                                                    requests_completed=3, requests_failed=1)),
     "not_observed:cancellation"),
    (lambda r, m: r["termination"].update(worker_summary_before=dict(in_flight=1, requests_started=4)),
     "not_observed:cancellation"),
])
def test_loop_causal_chain(tmp_path, mutation, expected):
    assert verdict(tmp_path, "loop", mutation)[0] == expected


def test_loop_requires_the_killed_detached_descendant(tmp_path):
    v, code, _ = verdict(tmp_path, "loop", lambda r, m: r["termination"].update(killed=[
        r["termination"]["killed"][0]]))
    assert v == "not_observed:descendant" and code == 4


def test_stall_may_lack_cancellation_proof(tmp_path):
    v, code, lines = verdict(tmp_path, "stall", lambda r, m: r["termination"].update(in_flight_at_kill=0))
    assert v == "PASS" and code == 0 and any("cancellation_not_shown" in x for x in lines)


def test_orphans_unattributed_are_printed_never_failing(tmp_path):
    v, code, lines = verdict(tmp_path, "stall", lambda r, m: r.update(
        orphans_unattributed=[dict(pid=5, argv=["x"])]))
    assert v == "PASS" and code == 0 and any("orphan_unattributed" in x for x in lines)


def test_aborted_attempt_without_row_fails(tmp_path):
    (tmp_path / "loop.attempt1.jsonl").write_text("")
    (tmp_path / "loop.attempt1.manifest.json").write_text(json.dumps(dict(transport_abort=dict(error="x"))))
    lines = []
    assert iv.main(["--run", str(tmp_path), "--kind", "loop", "--workdir", str(tmp_path)], out=lines.append) == 1
    assert lines[0] == "loop.attempt1: FAIL:transport_abort"


# ---- suite level ----

def no_docker():
    return []


def no_processes():
    return []


def full_run(tmp_path, **mutations):
    for kind in iv.KINDS:
        write_attempt(tmp_path, kind, 1, mutations.get(kind))


def run_suite(tmp_path, docker_ps=no_docker, process_lister=no_processes):
    lines = []
    code = iv.main(["--run", str(tmp_path), "--workdir", str(tmp_path)], docker_ps=docker_ps,
                   process_lister=process_lister, out=lines.append)
    return code, lines


def test_suite_pass_and_every_line_leads_with_the_attempt_stem(tmp_path):
    full_run(tmp_path)
    code, lines = run_suite(tmp_path)
    assert code == 0 and lines[-1] == "RESULT PASS"
    row_lines = [x for x in lines if x.split(":", 1)[0] in {f"{k}.attempt1" for k in iv.KINDS} and "note" not in x]
    assert len(row_lines) == 3 and all(x.endswith("PASS") for x in row_lines)


def test_partial_run_directory_is_retryable_exit_4_unless_a_fail_exists(tmp_path):
    write_attempt(tmp_path, "stall", 1)
    code, lines = run_suite(tmp_path)
    assert code == 4 and any("absent" in x for x in lines)
    write_attempt(tmp_path, "loop", 1, lambda r, m: r["gate"].update(stop_reason=None))
    assert run_suite(tmp_path)[0] == 4
    write_attempt(tmp_path, "alloc", 1, lambda r, m: r["mem_kills"][0].update(argv=["x"]))
    assert run_suite(tmp_path)[0] == 1
    empty = tmp_path / "empty"
    empty.mkdir()
    assert run_suite(empty)[0] == 4


def test_only_the_last_attempt_counts_and_earlier_ones_are_listed_as_retries(tmp_path):
    write_attempt(tmp_path, "stall", 1)
    write_attempt(tmp_path, "loop", 1, lambda r, m: r["gate"].update(stop_reason=None))
    write_attempt(tmp_path, "loop", 2)
    write_attempt(tmp_path, "alloc", 1)
    code, lines = run_suite(tmp_path)
    assert code == 0
    assert any(x.startswith("loop.attempt1: not_observed") and "retry" in x for x in lines)
    assert any(x.startswith("loop.attempt2: PASS") and "retry" not in x for x in lines)
    write_attempt(tmp_path, "loop", 3, lambda r, m: r["gate"].update(stop_reason=None))
    assert run_suite(tmp_path)[0] == 4          # the last attempt is what counts


def test_retained_loop_row_must_show_cancellation(tmp_path):
    full_run(tmp_path)
    write_attempt(tmp_path, "loop", 2, lambda r, m: r["termination"].update(in_flight_at_kill=0))
    code, lines = run_suite(tmp_path)
    assert code == 4 and any("loop.attempt2: not_observed:cancellation" in x for x in lines)


def test_live_checks_exact_prefix_unrelated_containers_ignored_and_processes_listed(tmp_path):
    full_run(tmp_path)
    unrelated = lambda: ["mlxbench-other-item-1", "mlxbench-run-20261010T120000-ffffffffffff-item-1", "postgres"]    # noqa: E731
    assert run_suite(tmp_path, docker_ps=unrelated)[0] == 0
    mine = lambda: ["mlxbench-run-20261010T120000-bbbbbbbbbbbb-python-one-1", "postgres"]                                # noqa: E731
    code, lines = run_suite(tmp_path, docker_ps=mine)
    assert code == 1 and any("FAIL:containers:mlxbench-run-20261010T120000-bbbbbbbbbbbb-python-one-1" in x for x in lines)
    run_dir = str(tmp_path / "opencode-probe-v2/run-20261010T120000-cccccccccccc")
    procs = lambda: [(77, run_dir + "/state", ["sleep", "600"]), (78, "/elsewhere", ["sleep"])]   # noqa: E731
    code, lines = run_suite(tmp_path, process_lister=procs)
    assert code == 1 and any("FAIL:processes" in x and "77" in x and "78" not in x for x in lines)


def test_interrupted_charged_trailing_is_accepted(tmp_path):
    assert verdict(tmp_path, "loop", lambda r, m: r["reconciliation"].update(trailing="interrupted_charged"))[0] \
        == "PASS"


def test_a_cancelled_counter_when_the_worker_has_one_must_rise_by_exactly_one():
    base = dict(in_flight_at_kill=1)
    before = dict(in_flight=1, requests_completed=3, requests_cancelled=2)
    assert iv.cancellation_consistent(dict(base, worker_summary_before=before, worker_summary_after=dict(
        in_flight=0, requests_completed=4, requests_cancelled=3)))
    for bad in (2, 4):
        assert not iv.cancellation_consistent(dict(base, worker_summary_before=before, worker_summary_after=dict(
            in_flight=0, requests_completed=3, requests_cancelled=bad)))


def test_numerically_latest_unreadable_attempt_is_the_retained_one_and_fails(tmp_path):
    full_run(tmp_path)
    (tmp_path / "loop.attempt2.jsonl").write_text("{not json\n")
    (tmp_path / "loop.attempt2.manifest.json").write_text("{}")
    code, lines = run_suite(tmp_path)
    assert code == 1 and any(x.startswith("loop.attempt2: FAIL:unreadable") for x in lines)
    assert "RESULT PASS" not in lines
    lines = []
    assert iv.main(["--run", str(tmp_path), "--kind", "loop", "--workdir", str(tmp_path)], out=lines.append) == 1


def test_kind_without_any_attempt_file_exits_1_missing(tmp_path):
    write_attempt(tmp_path, "stall", 1)
    lines = []
    assert iv.main(["--run", str(tmp_path), "--kind", "alloc", "--workdir", str(tmp_path)], out=lines.append) == 1
    assert lines[0].startswith("alloc: FAIL:missing")
    empty = tmp_path / "e"
    empty.mkdir()
    assert iv.main(["--run", str(empty), "--kind", "stall", "--workdir", str(tmp_path)], out=lambda x: None) == 1


def _other(r):
    return copy.deepcopy(r["grade_reports"][0])


@pytest.mark.parametrize("name,mutation,reason", [
    ("absent", lambda r, m: r.pop("grade_reports"), "absent or empty"),
    ("empty", lambda r, m: r.update(grade_reports=[]), "absent or empty"),
    ("malformed", lambda r, m: r["grade_reports"][0].update(boundary="1"), "boundary"),
    ("negative_boundary", lambda r, m: r["grade_reports"][0].update(boundary=-1), "boundary"),
    ("negative_seq", lambda r, m: r["grade_reports"][0].update(seq=-1), "seq must be an int >= 0"),
    ("bool_seq", lambda r, m: r["grade_reports"][0].update(seq=True), "seq must be an int"),
    ("infrastructure_final", lambda r, m: r["grade_reports"][0].update(outcome="infrastructure"), "not permitted"),
    ("missing_report_final", lambda r, m: r["grade_reports"][0].update(outcome="missing_report"),
     "final receipt outcome"),
    ("no_final", lambda r, m: r["grade_reports"][0].update(final=False), "exactly one final"),
    ("seq_collision", lambda r, m: r["grade_reports"].insert(0, dict(_other(r), final=False)), "duplicate seq"),
    ("parsed_without_stdout", lambda r, m: r["grade_reports"][0]["artifacts"].pop("stdout.txt"), "lacks"),
    ("bad_sha", lambda r, m: r["grade_reports"][0]["artifacts"]["report.xml"].update(sha256="zz"), "64-hex"),
    ("tampered_with_artifacts", lambda r, m: (r["grade_reports"][0].update(outcome="tampered"),
                                              r.update(test_modified=True)), "no artifacts"),
])
def test_grade_report_schema_mutations_fail(tmp_path, name, mutation, reason):
    v, code, _ = verdict(tmp_path, "stall", mutation)
    assert v.startswith("FAIL:grade_reports:") and reason in v and code == 1


def test_tampered_final_receipt_is_valid_only_with_test_modified(tmp_path):
    def tampered(r, m):
        r["grade_reports"][0].update(outcome="tampered", artifacts={})
        r["test_modified"] = True
    assert verdict(tmp_path, "stall", tampered)[0] == "PASS"
    d = tmp_path / "t"
    d.mkdir()
    assert "requires test_modified" in verdict(d, "stall", lambda r, m: r["grade_reports"][0].update(
        outcome="tampered", artifacts={}))[0]


def test_suite_prints_the_consistency_limitation_and_still_clears(tmp_path):
    full_run(tmp_path)
    code, lines = run_suite(tmp_path)
    assert code == 0 and "suite: loop cancellation consistent, not correlated \u2014 see C149" in lines


def test_docstring_states_the_limitation():
    assert "not proof" in iv.cancellation_consistent.__doc__ and "C149" in iv.cancellation_consistent.__doc__


@pytest.mark.parametrize("run_id", [None, "", "RUNstall", "20261010T120000-xyz", "20261010T120000-AAAAAAAAAAAA", 7])
def test_missing_or_malformed_run_id_fails(tmp_path, run_id):
    def mutate(r, m):
        if run_id is None:
            m.pop("run_id")
        else:
            m["run_id"] = run_id
    assert verdict(tmp_path, "stall", mutate)[0] == "FAIL:run_id"


def test_run_id_removed_from_every_manifest_cannot_reach_suite_pass(tmp_path):
    full_run(tmp_path, **{k: (lambda r, m: m.pop("run_id")) for k in iv.KINDS})
    code, lines = run_suite(tmp_path)
    assert code == 1 and "RESULT PASS" not in lines


def test_live_checks_run_for_every_retained_attempt_and_leftovers_fail(tmp_path):
    full_run(tmp_path)
    seen = []

    def docker():
        seen.append("docker")
        return []
    assert run_suite(tmp_path, docker_ps=docker)[0] == 0
    assert seen == ["docker"] * 3                                  # one live check per retained attempt
    leftover = lambda: ["mlxbench-20261010T120000-aaaaaaaaaaaa-item-1"]                          # noqa: E731
    code, lines = run_suite(tmp_path, docker_ps=leftover)
    assert code == 1 and any(x.startswith("suite: stall:FAIL:containers") for x in lines)
