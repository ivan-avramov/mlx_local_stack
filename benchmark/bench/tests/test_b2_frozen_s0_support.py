"""P426 B2 frozen tests, s0: every fixture, fake and helper of `b2_frozen_support` validated against the BASELINE code (the
B2 base commit 50ec18d1), through each path the slice tests use. Every test here passes on the baseline.

Note: the chain-harness validations (legacy argv without `--models`) are baseline-shaped by construction: C221 makes
`--models` required in every tg1 mode, so they record what the base commit does."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from bench.tests import b2_frozen_support as S

COMMITTED_ON = S.BENCH / "results/p426/wave1/math500-p426-on-b1/server_log_slice.log"
COMMITTED_SMOKE = S.BENCH / "results/p426/wave1/reasoning-p426-on-smoke/server_log_slice.log"
GENERATION_PY = S.REPO / "src/mlx-vlm/mlx_vlm/server/generation.py"


def _lines(path, needle):
    return [ln for ln in Path(path).read_text().splitlines() if needle in ln]


# ------------------------------------------------------------------------------------------------ log formats
def test_completed_line_reproduces_a_committed_on_line_byte_for_byte():
    real = _lines(COMMITTED_ON, "Request completed:")[0]
    got = S.completed_line(
        at="2026-10-22 17:31:06,147", stream=False, session="p426-math500-p426-on-b1-b26f0cebbb234d0b", prompt_tokens=99,
        generated_tokens=1265, elapsed=25.745, prefill=210.8, decode=51.6, finish_reason="stop", in_flight=0,
        sdpa=(16, 48), draft=S.draft_counters(513, 1026, 751), verify=S.VERIFY_ON)
    assert got == real


def test_completed_line_without_drafter_counters_reproduces_the_committed_smoke_line():
    real = _lines(COMMITTED_SMOKE, "Request completed:")[0]
    got = S.completed_line(
        at="2026-10-22 15:48:28,237", stream=False, session="p426-reasoning-p426-on-smoke-e5b29581d41d4b82",
        prompt_tokens=3210, generated_tokens=1, elapsed=3.948, prefill=890.0, decode=1091.9, finish_reason="length",
        sdpa=(112, 48), verify=dict(S.VERIFY_ON, verify_blocks_joint_v1=0, verify_blocks_straddle=0))
    assert got == real


def test_started_line_reproduces_the_committed_line():
    real = _lines(COMMITTED_SMOKE, "Request started:")[0]
    assert S.started_line(at="2026-10-22 15:48:24,320", stream=False, in_flight=1) == real


def test_failed_line_has_the_fork_format_and_the_wave1_parser_counts_it():
    from bench import p426_leg
    line = S.failed_line()
    assert re.search(r"Request failed: endpoint=\S+ model=\S+ stream=(True|False) error=stream_closed_before_completion "
                     r"in_flight=\d+$", line)
    src = GENERATION_PY.read_text()
    assert '"Request failed: endpoint=%s model=%s stream=%s error=%s in_flight=%d"' in src.replace("\n", "").replace(
        '"            "', "")
    probs, stats = p426_leg.log_problems([S.started_line(), line], "off", 1)
    assert stats["failed"] == 1 and stats["started"] == 1 and any("failed" in p for p in probs)


def test_an_item_window_parses_clean_with_the_wave1_parsers():
    from bench import p426_leg
    usage = [["msg_a", 137, 2966, 81920], ["msg_b", 69, 14555, 81920], ["msg_c", 364, 14698, 81920]]
    lines = S.item_window("ses_x", usage, draft=lambda i, g: S.draft_counters(5, 10, 7))
    probs, stats = p426_leg.log_problems(lines, "on", 3)
    assert probs == [] and stats == dict(started=3, completed=3, failed=0, overlapping=0)
    # the session / prompt / draft fields parse with the Wave-1 matcher (one request per session there)
    one = S.item_window("ses_one", usage[:1], draft=lambda i, g: S.draft_counters(5, 10, 7))
    row = dict(id="x", session_id="ses_one", prompt_tokens=2966, draft=dict(draft_n=10, draft_n_accepted=7))
    assert p426_leg.request_match_problems([row], one, []) == []


def test_metrics_doc_has_exactly_the_fork_snapshot_summary_keys():
    src = GENERATION_PY.read_text()
    block = src[src.index('"summary": {', src.index("def snapshot(self)")):]
    block = block[:block.index("},")]
    keys = re.findall(r'"(\w+)":', block)[1:]
    assert sorted(keys) == sorted(S.metrics_doc()["summary"])
    m = S.metrics_doc(started=2, completed=2, generated_total=100, decode_s=4.0)["summary"]
    assert m["avg_decode_tok_s"] == 25.0 and S.metrics_doc()["summary"]["avg_decode_tok_s"] == 0.0


def test_the_real_row_fixture_has_the_request_usage_and_session_shapes():
    row = S.real_row()
    assert row["session_id"].startswith("ses_") and row["scaffold"] == "opencode-v2-web-tg1"
    assert row["request_usage"] and all(isinstance(m, str) and all(type(x) is int for x in rest)
                                         for m, *rest in row["request_usage"])
    assert all(len(u) == 4 for u in row["request_usage"]) and row["gate"]["requests_completed"] == len(row["request_usage"])


# ------------------------------------------------------------------------------------------------ registry / argv
def test_registry_fixture_and_the_on_argv_delta_pass_the_wave1_checker():
    from bench import p426_leg
    on = S.registry_text((S.MODEL,), on=(S.MODEL,))
    off = S.registry_text((S.MODEL,))
    base = f"python -m mlx_vlm.server --model {S.HF} --port 8091"
    on_argv = base + f" --draft-kind mtp --draft-model {S.DRAFTER} --mtp-verify-scan joint_v1"
    assert p426_leg.model_argv_problems(on_argv, on, S.MODEL) == []
    assert p426_leg.model_argv_problems(base, off, S.MODEL) == []
    assert p426_leg.model_argv_problems(base, on, S.MODEL)                      # the delta is what tells them apart
    import yaml
    doc = yaml.safe_load(S.registry_text((S.MODEL, S.MODEL2, S.MODEL3), on=(S.MODEL2,), partial=(S.MODEL3,)))
    by = {m["name"]: m for m in doc["models"]}
    assert all(k in by[S.MODEL2] for k in S.C177_KEYS) and not any(k in by[S.MODEL] for k in S.C177_KEYS)
    assert [k for k in S.C177_KEYS if k in by[S.MODEL3]] == ["draft_kind"]


# ------------------------------------------------------------------------------------------------ the legacy chain harness
def test_the_fixture_ops_run_the_legacy_pilot_and_reproduce_the_golden_order(tmp_path, monkeypatch):
    env = S.chain_env(tmp_path, monkeypatch)
    try:
        assert S.run_chain(env, ["pilot"], universe=False) == 0, "\n".join(env["lines"][-12:])
        assert S.invocation_order(S.invocations(env)) == S.GOLDEN_PILOT_ORDER
    finally:
        env["ops"].cancel()


def test_the_legacy_chain_goldens_hold_on_the_base_commit(tmp_path, monkeypatch):
    from bench import schedules
    R = S.runner_module()
    names = R.load_universe()
    for pred, sha in (("off", S.GOLDEN_P223_SCHEDULE_SHA), ("mtp", S.GOLDEN_M63_SCHEDULE_SHA)):
        sched = schedules.tg1("chain", ["s1", "s2", "reload"], names, predictor=pred)
        assert schedules.schedule_sha256(sched) == sha
    env = S.chain_env(tmp_path, monkeypatch)
    try:
        assert S.run_chain(env, ["chain", "s1", "s2", "reload", "--probe-code-sha", S.HEX9], universe=False, timeout=300) == 0
        order = S.invocation_order(S.invocations(env))
        assert len(order) == 13 and S.order_sha(order) == S.GOLDEN_CHAIN_ORDER_SHA
    finally:
        env["ops"].cancel()
    cfg = R.tg1_config(R.parse_args(["chain", "s1", "--probe-code-sha", S.HEX9])).as_dict()
    assert {k: cfg[k] for k in S.GOLDEN_TG1_CONFIG_STATIC} == S.GOLDEN_TG1_CONFIG_STATIC


def test_the_served_registry_is_the_fixture_ops_overlay(tmp_path, monkeypatch):
    env = S.chain_env(tmp_path, monkeypatch, registry=S.registry_text((S.MODEL, S.MODEL2, S.MODEL3)))
    try:
        assert S.run_chain(env, ["pilot"]) == 0
        cj = S.chain_json(env)
        assert cj["sha256"]["overlay"] == S.sha256_file(env["ops"].overlay) == cj["pinned"]["registry_sha256"]
    finally:
        env["ops"].cancel()


def test_the_smoke_shape_watch_line_of_the_full_invocation_is_observable(tmp_path, monkeypatch):
    """The P469 harness: `chain s1 --smoke`, the full invocation hangs, WATCH lines of attempt a2 are logged, then STOP."""
    env = S.chain_env(tmp_path, monkeypatch, out="c147-smoke")

    def helper():
        t1c = S._t1c()
        t1c.wait_for(lambda: any(" WATCH " in ln and ".a2:" not in ln and " a2:" in ln for ln in env["lines"]), 30)
        (env["out"] / "STOP").write_text("")
    try:
        rc = S.run_chain(env, ["chain", "s1", "--smoke", "--probe-code-sha", S.HEX9], plan=["normal", "hang_in_item"],
                         timers=dict(watch_s=0.1), helper=helper)
        assert rc == 3
        watch = [ln for ln in env["lines"] if " WATCH " in ln and " a2:" in ln]
        assert watch and all(re.search(r" a2: \d+/2 ", ln) for ln in watch)
    finally:
        env["ops"].cancel()


# ------------------------------------------------------------------------------------------------ the item-barrier fake probe
def test_the_item_barrier_fake_probe_completes_under_the_baseline_chain_with_consistent_log_and_metrics(tmp_path, monkeypatch):
    from bench import p426_leg
    env = S.chain_env(tmp_path, monkeypatch)
    log, metrics = tmp_path / "WT/logs/mlx_vlm.log", tmp_path / "metrics.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    S.ops_with_metrics_file(env["ops"], metrics)
    try:
        rc = S.run_core(env, ["pilot"], extra_env=S.barrier_env(env["ops"].state, log=log, metrics=metrics, requests=2))
        assert rc == 0
        files = S.barrier_files(env["out"] / "pilot")
        for k in range(5):
            for kind in ("ready", "go", "done", "continue"):
                assert any(f.endswith(f".item{k}.{kind}") for f in files), (k, kind)
        lines = log.read_text().splitlines()
        assert p426_leg.log_problems(lines, "off", 10)[0] == []
        rows = [json.loads(x) for f in (env["out"] / "pilot").glob("*.L0.pilot.a1.jsonl") for x in f.read_text().splitlines()]
        assert len(rows) == 5 and all(r["session_id"].startswith("ses_") and len(r["request_usage"]) == 2 for r in rows)
        m = json.loads(metrics.read_text())["summary"]
        assert m["requests_completed"] == m["requests_started"] == 10 and m["in_flight"] == 0
        assert m["generated_tokens_total"] == sum(u[1] for r in rows for u in r["request_usage"])
        assert m["prompt_tokens_total"] == sum(u[2] for r in rows for u in r["request_usage"])
        man = json.loads(next((env["out"] / "pilot").glob("*.manifest.json")).read_text())
        assert man["runtime"]["evidence_policy"] == S.evidence_policy("on")
    finally:
        env["ops"].cancel()


def test_the_item_barrier_fake_probe_stops_cleanly_at_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    state = tmp_path / "state"
    state.mkdir()
    (state / "worker.json").write_text(json.dumps({"pid": 1, "create_time": 1.0, "model_path": S.HF, "registry_sha256": "a" * 64}))
    out = tmp_path / "x.L0.pilot.a1.jsonl"
    ack = tmp_path / "x.ACK"
    ack.write_text("")
    argv = [sys.executable, str(S.PROBE), "--model", S.MODEL, "--items", "p1,p2", "--lang", "python", "--seed-base", "1001",
            "--out", str(out), "--scaffold", "opencode-v2-web-tg1", "--expect-items", "python/p1,python/p2",
            "--a4-v2-receipt", "r", "--sampling-profile", "deployed", "--cancel-file", str(tmp_path / "x.CANCEL"),
            "--manifest-ack", str(tmp_path / "x.ACK2"), "--frozen-prompt-date", S.EPOCH_DATE]
    import os
    env = dict(os.environ, **S.barrier_env(state))
    proc = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    ack2 = tmp_path / "x.ACK2"
    end = time.time() + 30
    while not (tmp_path / "x.L0.pilot.a1.item0.ready").exists() and time.time() < end:
        if (tmp_path / "x.L0.pilot.a1.manifest.json").exists() and not ack2.exists():
            ack2.write_text("")
        time.sleep(0.01)
    (tmp_path / "x.L0.pilot.a1.item0.stop").write_text(json.dumps({"disposition": "pre_spawn_incident"}))
    assert proc.wait(30) == 0
    man = S.manifest_of(out)
    assert man["hook_stop"] == {"before_slot": "python/p1"} and man["cleanup_status"] == S.CLEANUP_EXACT
    assert not out.exists()


# ------------------------------------------------------------------------------------------------ the real probe in-process
def test_the_probe_fixture_runs_the_real_tg1_probe_with_the_tg1_evidence_policy(tmp_path, monkeypatch):
    from bench import tg1_runner
    f = S.probe_fixture(monkeypatch, tmp_path)
    assert f["run"]("one", extra=["--expect-items", "python/one"]) == 0
    man = S.manifest_of(f["out"])
    assert man["runtime"]["evidence_policy"] == tg1_runner.TG1_EVIDENCE.as_dict()
    assert S.barrier_files(f["out"].parent) == []
    assert "oc-fixture-client" in str(Path(__import__("os").environ["OPENCODE_PROBE_BIN"]))


@pytest.mark.parametrize("kind,cause", [("drop", "dropped_stream"), ("refuse", "connection")])
def test_the_probe_fixture_client_abort_writes_a_transport_abort_without_a_cause_in_tg1(tmp_path, monkeypatch, kind, cause):
    """1f: the abort must be the client's ERROR EVENT, not a malformed-stream refusal (the 1d fixture's leading `not json`
    line made the gate refuse "malformed complete event line" before any transport error, which this check had missed)."""
    from bench import arm_opencode as ao
    f = S.probe_fixture(monkeypatch, tmp_path)
    S.set_client_error(f, tmp_path, kind)
    try:
        rc = f["run"]("one", extra=["--expect-items", "python/one"])
    except SystemExit as e:
        rc = e.code
    assert rc not in (0, None)
    stamp = S.manifest_of(f["out"])["transport_abort"]
    assert "cause" not in stamp and "gate" not in stamp
    assert "error event" in stamp["error"] and "malformed" not in stamp["error"] and "part id" not in stamp["error"]
    assert ao.classify_error(S.client_error_events(S.ERROR_TYPES[kind])[-1]["error"]) == cause


def test_the_opencode_arm_transport_cause_on_the_base_commit():
    from bench import arm_opencode as ao
    exc = ao.TransportFailure("connection", "x")
    assert ao.OpencodeArm(mode="tg1").transport_cause(exc) is None
    assert ao.OpencodeArm(mode="m64").transport_cause(exc) == "connection"


# ------------------------------------------------------------------------------------------------ locks / gate
def test_the_lock_helpers_see_a_held_flock_from_a_second_open(tmp_path):
    p = tmp_path / "locks" / "X.lock"
    assert not S.is_flocked(p)
    with S.held_flock(p):
        assert S.is_flocked(p)
    assert not S.is_flocked(p)


def test_the_gate_harness_reaches_the_first_work_step_when_nothing_is_held(tmp_path, monkeypatch):
    seen = S.gate_harness(monkeypatch, tmp_path)
    got = S.gate_main()
    assert isinstance(got, S.GateReached) and seen["reached"] is True


def test_the_simultaneous_helper_releases_both_callers_together():
    stamps = []
    res = S.simultaneous(lambda: stamps.append(time.monotonic()) or 1, lambda: stamps.append(time.monotonic()) or 2)
    assert res == [1, 2] and abs(stamps[0] - stamps[1]) < 1.0


# ------------------------------------------------------------------------------------------------ harvest helpers
def test_the_harvest_copy_imports_the_wave1_harvest_hermetically(tmp_path):
    repo = S.harvest_repo(tmp_path)
    env = S.harvest_env(tmp_path)
    got = subprocess.run([sys.executable, "-c", "import bench.p426_harvest as h, sys; print(h.__file__)"],
                         cwd=str(repo / "benchmark"), env=env, capture_output=True, text=True, timeout=60)
    assert got.returncode == 0 and str(repo) in got.stdout
    assert env["HOME"].startswith(str(tmp_path)) and env["XDG_CONFIG_HOME"].startswith(str(tmp_path))
    leg = S.not_started_leg_root(env["STACK_WORKDIR"])
    assert json.loads((leg / "leg.json").read_text())["class"] == "NOT_STARTED" and leg.name == "tg1-p426-off-pilot.a1"
    got = S.run_harvest(repo, leg, env, main_root=tmp_path / "main", stage=tmp_path / "stage")
    assert got.returncode == 0 and got.stdout == ""          # the base module runs (and has no wave2 entry yet)


def test_the_fixture_secrets_are_found_by_a_plain_search(tmp_path):
    t = tmp_path / "transcript.json"
    t.write_text(json.dumps({"text": f"token {S.FAKE_SECRET_40} and {S.FAKE_HF_TOKEN_FILE}"}))
    text = S.all_output_text(tmp_path)
    assert S.FAKE_SECRET_40 in text and S.FAKE_HF_TOKEN_FILE in text and len(S.FAKE_SECRET_40) == 40
    assert re.search(r"hf_[A-Za-z0-9]{30,}", S.FAKE_HF_TOKEN_FILE) and not re.search(r"^(hf_|sk-|ghp_|AKIA)", S.FAKE_SECRET_40)
    assert S.FAKE_SECRET_40 not in S.all_output_text(tmp_path, exclude=[t])


# ------------------------------------------------------------------------------------------------ baseline identities
def test_the_frozen_runner_and_serving_pin_identities_of_the_base_commit():
    for rel, sha in S.FROZEN_RUNNERS.items():
        assert S.sha256_file(S.REPO / rel) == sha, rel
    got = subprocess.run(["git", "ls-files", "-s", *S.BASE_GITLINKS], cwd=str(S.REPO), capture_output=True, text=True).stdout
    links = {ln.split()[-1]: ln.split()[1] for ln in got.splitlines()}
    assert links == S.BASE_GITLINKS


def test_the_p426_order_rule_is_a_seeded_permutation():
    pool = [f"p{i}" for i in range(22)]
    a, b = S.p426_order(pool, 1001), S.p426_order(list(reversed(pool)), 1001)
    assert a == b and sorted(a) == sorted(pool) and a != sorted(pool) and S.p426_order(pool, 2002) != a


# ------------------------------------------------------------------------------------------------ v3.2 fixtures
def test_the_record_builders_follow_the_self_hash_recipe_and_link_the_amendment(tmp_path):
    import hashlib
    v8, am = S.record_dir(tmp_path)
    d8, da = json.loads(v8.read_text()), json.loads(am.read_text())
    body = {k: v for k, v in d8.items() if k != "sha256"}
    assert d8["sha256"] == hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert d8["kind"] == "p426_v8_base" and da["kind"] == "p426_timeout_amendment"
    assert da["v8_base_sha256"] == d8["sha256"] and S.self_hashed(da)["sha256"] == da["sha256"]
    reh = S.rehearsal_manifest(tmp_path / "p426/rehearsal/r1")
    assert reh["kind"] == "p426_rehearsal" and reh["rehearsal"] is True and S.self_hashed(reh) == reh
    with pytest.raises(FileExistsError):
        S.write_record(v8, d8)                                    # exclusive create


def test_the_golden_scored_fail_rows_have_the_fields_the_failed_line_table_reads():
    kill = S.golden_row("item_stall_kill")
    assert kill["nonconv_kind"] == "stalled" and kill["gate"]["requests_completed_at_kill"] == 5
    assert len(kill["request_usage"]) == 5 and kill["termination"]["in_flight_at_kill"] == 0 and kill["session_id"]
    idle = S.golden_row("item_client_inactivity")
    assert idle["nonconv_kind"] == "client_inactivity" and idle["gate"]["requests_completed_at_kill"] is None
    assert idle["gate"]["requests_completed"] == len(idle["request_usage"]) == 1


def test_the_window_and_counter_builders_agree_with_the_wave1_parser():
    from bench import p426_leg
    usage = [["m1", 10, 100, 81920], ["m2", 20, 200, 81920]]
    data = S.window(S.item_window("ses_x", usage) + [S.started_line(), S.failed_line()])
    probs, stats = p426_leg.log_problems(data.decode().splitlines(), "off", 3)
    assert stats == dict(started=3, completed=2, failed=1, overlapping=0)
    before = S.summary(started=4, completed=4, prompt_total=10, generated_total=5)
    after = S.counters_after(before, usage, failed=1)
    assert (after["requests_started"], after["requests_completed"], after["requests_failed"]) == (7, 6, 1)
    assert (after["prompt_tokens_total"], after["generated_tokens_total"]) == (310, 35)


def test_the_fake_ops_implement_the_log_seams(tmp_path, monkeypatch):
    env = S.chain_env(tmp_path, monkeypatch)
    log = env["ops"].server_log_path()
    log.write_bytes(b"0123456789")
    assert env["ops"].read_log(log, 2, 5) == b"234" and env["ops"].read_log(log, 7) == b"789"
    assert log == Path(env["ops"].overlay).parent / "logs" / "mlx_vlm.log" and Path(env["ops"].repo) == log.parents[1]


def test_the_receipt_fixture_pair_differs_only_by_the_argv_delta_and_the_drafter():
    from bench import p426_leg
    off, on = S.arm_receipt_doc("off"), S.arm_receipt_doc("on")
    extra = list(on["argv"]["worker"])
    for x in off["argv"]["worker"]:
        extra.remove(x)
    assert sorted(extra) == sorted(["--draft-kind", "mtp", "--draft-model", S.DRAFTER, "--mtp-verify-scan", "joint_v1"])
    assert [x for x in on["argv"]["worker"] if x in off["argv"]["worker"]] == off["argv"]["worker"]
    reg_on, reg_off = S.registry_text((S.MODEL,), on=(S.MODEL,)), S.registry_text((S.MODEL,))
    assert p426_leg.model_argv_problems(" ".join(on["argv"]["worker"]), reg_on, S.MODEL) == []
    assert p426_leg.model_argv_problems(" ".join(off["argv"]["worker"]), reg_off, S.MODEL) == []
    assert off["snapshots"]["drafter"] is None and on["snapshots"]["drafter"]

    def rest(r):
        return {k: v for k, v in r.items() if k not in ("argv", "snapshots", "sha256")}
    assert rest(off) == rest(on) and S.self_hashed(off) == off


def test_the_abort_manifest_fixture_extends_the_real_probe_stamp(tmp_path, monkeypatch):
    f = S.probe_fixture(monkeypatch, tmp_path)
    S.set_client_error(f, tmp_path, "drop")
    try:
        f["run"]("one", extra=["--expect-items", "python/one"])
    except SystemExit:
        pass
    real = S.manifest_of(f["out"])["transport_abort"]
    fake = S.abort_manifest([["m1", 10, 100, 81920]], in_flight="m2")["transport_abort"]
    assert set(real) - {"grade_reports"} <= set(fake)            # the tg1 stamp's keys, plus the §16.1 P426 keys
    assert set(real["cleanup_status"]) == set(S.CLEANUP_EXACT)


def test_the_a4_receipt_fixture_has_the_gate_shape_and_passes_its_own_predicate():
    reqs = [("ses_a", 0, 9000), ("ses_a", 8800, 9100), ("ses_a", 0, 9300), ("ses_a", 9200, 9400)]
    doc = S.a4_receipt(reqs)
    src = (S.REPO / "scripts/session_pinning_gate.py").read_text()
    for key in ('"turns"', '"session_id"', '"sessions"', '"cross_process_reuse"', '"pass"'):
        assert key in src
    flat = [r for t in doc["turns"] for r in t["requests"]]
    assert len(doc["turns"]) == 2 and all(t["rc"] == 0 and t["requests"] for t in doc["turns"])
    assert all(r["session"] == doc["session_id"] for r in flat) and len(flat) == 4


def test_the_stall_injection_uses_the_real_probes_stall_kill_row_shape():
    """post-reveal 3d (§16.8): the fake probe's `--inject-stall-item` kill copies the P371 golden `item_stall_kill` row's
    outcome fields (a boundary kill: `requests_completed_at_kill` == completed, `in_flight_at_kill` 0, killed processes)."""
    ref = S.golden_row("item_stall_kill")
    assert ref["nonconv_kind"] == "stalled" and ref["passed"] is False and ref["termination"]["killed"]
    assert ref["gate"]["requests_completed_at_kill"] == ref["gate"]["requests_completed"]
    assert ref["termination"]["in_flight_at_kill"] == 0
    src = (S.BENCH / "bench/tests/b2_frozen_support.py").read_text()
    assert '"--inject-stall-item"' in src and '"--inject-stall-s"' in src


def test_the_occurrence_builder_has_the_five_fields_and_the_position():
    # post-reveal 3d (§16.8): `occurrence` is the 0-based position in the leg's frozen (session, language) order
    o = S.occurrence("s1", "python", "grep", 1001, "off", 2)
    assert o == dict(session="s1", language="python", item="grep", seed=1001, arm_of_dnf="off", occurrence=2)


# ------------------------------------------------------------------------------------------------ the P426 leg fixtures (§16.4)
def test_the_fake_identity_matches_the_fake_probes_manifests_for_both_arms_languages_and_seeds(tmp_path, monkeypatch):
    FP = S._fp()
    worker = {"pid": 7, "create_time": 2.0, "model_path": S.HF, "registry_sha256": "b" * 64}
    ident = S.fake_identity()
    assert {"probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256", "snapshot_sha256"} <= set(ident)
    for lang, seed in (("python", 1001), ("go", 2002)):
        man = FP.build_manifest(S.MODEL, lang, seed, worker, "r", {}, frozen=S.EPOCH_DATE)
        assert man["runtime"]["generation_identity_sha256"] == ident["generation_identity_sha256"]
    reg = tmp_path / "on.yaml"
    reg.write_text(S.registry_text((S.MODEL,), on=(S.MODEL,)))
    monkeypatch.setenv("FAKE_SERVED_REGISTRY", str(reg))
    man = FP.build_manifest(S.MODEL, "python", 1001, worker, "r", {}, frozen=S.EPOCH_DATE)
    assert man["runtime"]["draft_kind"] == "mtp" and man["runtime"]["generation_identity_sha256"] == ident["generation_identity_sha256"]
    got = subprocess.run([sys.executable, str(S.PROBE), "--print-identity"], capture_output=True, text=True, timeout=60)
    assert got.returncode == 0 and json.loads(got.stdout.splitlines()[-1]) == ident


def test_the_served_worker_argv_is_mlx_serves_and_on_adds_exactly_the_three_flags(tmp_path):
    from bench import p426_leg
    off_reg, on_reg = tmp_path / "off.yaml", tmp_path / "on.yaml"
    off_reg.write_text(S.registry_text((S.MODEL,)))
    on_reg.write_text(S.registry_text((S.MODEL,), on=(S.MODEL,)))
    off, on = S.served_worker_argv(off_reg, S.MODEL), S.served_worker_argv(on_reg, S.MODEL)
    extra = list(on)
    for x in off:
        extra.remove(x)
    assert sorted(extra) == sorted(["--draft-kind", "mtp", "--draft-model", S.DRAFTER, "--mtp-verify-scan", "joint_v1"])
    assert p426_leg.model_argv_problems(" ".join(on), on_reg.read_text(), S.MODEL) == []
    assert p426_leg.model_argv_problems(" ".join(off), off_reg.read_text(), S.MODEL) == []


def test_the_p426_world_records_and_seams_are_consistent(tmp_path, monkeypatch):
    env = S.p426_world(tmp_path, monkeypatch, arm="on")
    try:
        ops, recs = env["ops"], env["records"]
        v8, am = json.loads(recs["v8"].read_text()), json.loads(recs["am"].read_text())
        assert S.self_hashed(v8) == v8 and am["v8_base_sha256"] == v8["sha256"] and am["kind"] == "p426_timeout_amendment"
        assert json.loads(recs["reh"].read_text())["kind"] == "p426_rehearsal"
        assert v8["probe_code_sha256"] == env["ident"]["probe_code_sha256"]
        assert v8["pins_sha256"] == S.sha256_file(env["wt"] / "src/mlx-vlm/dev/p369_phase2/pins.json")
        st = ops.worktree_state()
        assert st["head"] == S.ON_COMMIT and st["clean"] is True and st["gitlinks"] == S.BASE_GITLINKS
        assert ops.last_leg_end() is None and ops.snapshot_hashes(S.MODEL)["drafter"]["revision"]
        ident = ops.load(S.MODEL)
        assert ops.proc_argv(ident["pid"]) == S.served_worker_argv(ops.overlay, S.MODEL) and ops.proc_argv(1)[-1] == "start"
        penv = ops.proc_environ(ident["pid"])
        assert penv["HF_TOKEN"] == S.FAKE_SECRET_40 and penv["MLX_SERVE_CONFIG"] == ops.overlay
        argv, rfd = S.p426_argv(env, ("chain", "s1"))
        assert argv[argv.index("--frozen-record") + 1] == str(recs["am"]) and rfd is None and "--hmac-fd" not in argv  # C238
        assert "--hmac-fd" not in S.p426_argv(env, ("chain", "s1", "--rehearsal"))[0]
        assert S.arm_receipt_doc("on")["credential_keys"] == {"router": ["HF_TOKEN"], "worker": ["HF_TOKEN"], "probe": ["HF_TOKEN"]}
        assert "r1_env_difference" in json.loads(recs["v8"].read_text()) and "allowed_env_differences" not in json.loads(
            recs["v8"].read_text())
    finally:
        env["ops"].cancel()


def test_the_receipt_fixture_pair_differs_only_on_the_closed_list_and_keeps_credentials_out_of_env():
    """§6.5 / §16.7: the OFF / ON receipt fixtures (the R1 and pair-gate inputs) differ only in the §6.3 worker argv items and
    the drafter snapshot; no credential key (§11.3 key patterns) appears in an `env` map."""
    import re
    off, on = S.arm_receipt_doc("off"), S.arm_receipt_doc("on")
    differing = {k for k in set(off) | set(on) if k != "sha256" and off.get(k) != on.get(k)}
    assert differing == {"argv", "snapshots"}
    assert off["argv"]["router"] == on["argv"]["router"] and off["snapshots"]["target"] == on["snapshots"]["target"]
    extra = list(on["argv"]["worker"])
    for tok in off["argv"]["worker"]:
        extra.remove(tok)
    assert sorted(extra) == sorted(["--draft-kind", "mtp", "--draft-model", S.DRAFTER, "--mtp-verify-scan", "joint_v1"])
    cred = re.compile(r"(TOKEN|SECRET|PASSWORD|API_KEY|CREDENTIAL|AUTH)", re.I)
    for doc in (off, on):
        assert not [k for e in doc["env"].values() for k in e if cred.search(k) and k != "TOKENIZERS_PARALLELISM"]
        assert S.self_hashed(doc)["sha256"] == doc["sha256"]
        assert {i["path"].rsplit("/", 1)[-1] for i in doc["loaded_images"]} == {"libmlx.dylib", "mlx.metallib"}   # §6.4
    pins = json.loads(S.PINS.read_text())[S.MODEL]                          # 1i: the snapshots are the pins.json entries
    assert on["snapshots"] == {"target": pins["target"], "drafter": pins["drafter"]} and off["snapshots"]["drafter"] is None
    assert set(pins["drafter"]) == {"hf_path", "revision", "files"} and pins["drafter"]["hf_path"] == S.DRAFTER
    assert on["argv"]["worker"][on["argv"]["worker"].index("--draft-model") + 1] == on["snapshots"]["drafter"]["hf_path"]


def test_the_two_arms_probe_launch_environments_are_equal_after_canonicalization(tmp_path, monkeypatch):
    """2d (P32 ruling): the receipt's probe environment is the chain's launch environment (`ops.env_base()`); the fixture's
    carries no arm-specific key, so OFF and ON worlds of one box agree once `$STACK_WORKDIR` is canonicalized. The ON
    leg still drafts: the fake probe follows the served registry's `draft_kind`."""
    envs = {}
    for arm in ("off", "on"):
        env = S.p426_world(tmp_path / arm, monkeypatch, arm=arm)
        try:
            env["ops"].load(S.MODEL)
            base = env["ops"].env_base()
            root = str(tmp_path / arm)
            envs[arm] = {k: str(v).replace(root, "$STACK_WORKDIR") for k, v in base.items()}
            assert "B2_DRAFT" not in base and "FAKE_REGISTRY_SHA" not in base
            assert _fp_draft_kind(base, S.MODEL) == ("mtp" if arm == "on" else "off")
        finally:
            env["ops"].cancel()
    assert envs["off"] == envs["on"]


def _fp_draft_kind(environ, model):
    """`fake_probe.served_draft_kind` under the given environment (what the fake probe decides drafting from)."""
    import yaml
    models = yaml.safe_load(Path(environ["FAKE_SERVED_REGISTRY"]).read_text()).get("models") or []
    return next((m.get("draft_kind") or "off" for m in models if m.get("name") == model), "off")


def test_the_records_write_portable_path_fields(tmp_path, monkeypatch):
    """§16.7 (1g tail): record path fields are `$STACK_WORKDIR/…`; the world's records follow it."""
    env = S.p426_world(tmp_path, monkeypatch)
    try:
        v8 = json.loads(env["records"]["v8"].read_text())
        reh = json.loads(env["records"]["reh"].read_text())
        assert v8["off_worktree"] == v8["on_worktree"] == "$STACK_WORKDIR/WT" == S.portable(env["wt"])
        assert reh["out_root"].startswith("$STACK_WORKDIR/p426/rehearsal/") and str(tmp_path) not in json.dumps(reh)
        assert {i["path"].rsplit("/", 1)[-1] for i in env["ops"].loaded_images(0)} == {"libmlx.dylib", "mlx.metallib"}
    finally:
        env["ops"].cancel()


def test_the_fake_a4_gate_writes_its_window_receipt_and_gate_json(tmp_path, monkeypatch):
    from bench import p426_leg
    env = S.p426_world(tmp_path, monkeypatch)
    try:
        path = env["ops"].a4_gate(S.MODEL, "tag")
        lines = env["log"].read_text().splitlines()
        probs, stats = p426_leg.log_problems(lines, "off", 7)
        assert probs == [] and stats["completed"] == 7
        rec = json.loads(Path(path).read_text())
        gate = json.loads((tmp_path / S.GATE_JSON).read_text())
        assert rec["pass"] is True and len([r for t in rec["turns"] for r in t["requests"]]) == 4
        assert [r["session"][:5] for r in gate["A6_bare_anonymous"]["requests"]] == ["anon:"] * 3
        m = env["ops"].worker_metrics()["summary"]
        assert m["requests_completed"] == m["requests_started"] == 7
    finally:
        env["ops"].cancel()


@pytest.mark.parametrize("mode,failed,completed", [("boundary", 0, 2), ("inflight_failed", 1, 2), ("inflight_completed", 0, 3)])
def test_the_fake_probe_dnf_knob_writes_the_section_16_abort_manifest_and_the_server_side(tmp_path, monkeypatch, mode,
                                                                                         failed, completed):
    from bench import p426_leg
    env = S.p426_world(tmp_path, monkeypatch)
    try:
        env["ops"].load(S.MODEL)
        out = tmp_path / "x.L0.pilot.a1.jsonl"
        ack = tmp_path / "x.L0.pilot.a1.ACK"
        penv = dict(os.environ, **env["ops"].env_base(), B2_ABORTS=json.dumps({"p1": mode}))
        argv = [sys.executable, str(S.PROBE), "--model", S.MODEL, "--items", "p1,p2", "--lang", "python", "--seed-base", "1001",
                "--out", str(out), "--scaffold", "opencode-v2-web-tg1", "--expect-items", "python/p1,python/p2",
                "--a4-v2-receipt", "r", "--sampling-profile", "deployed", "--cancel-file", str(tmp_path / "x.CANCEL"),
                "--manifest-ack", str(tmp_path / "x.L0.pilot.a1.ACK"), "--frozen-prompt-date", S.EPOCH_DATE,
                "--evidence", "p426"]
        proc = subprocess.Popen(argv, env=penv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        end = time.time() + 30
        while not out.with_suffix(".manifest.json").exists() and time.time() < end:
            time.sleep(0.01)
        ack.write_text("ack")
        with S.barrier_answerer(tmp_path):
            assert proc.wait(60) == 1
        stamp = S.manifest_of(out)["transport_abort"]
        assert {"cause", "error", "evidence", "termination", "gate", "session_id", "in_flight"} <= set(stamp)
        assert stamp["cause"] == "connection" and isinstance(stamp["gate"]["request_usage"], list)
        assert stamp["in_flight"]["in_flight"] is (mode != "boundary") and set(stamp["cleanup_status"]) == set(S.CLEANUP_EXACT)
        lines = env["log"].read_text().splitlines()
        stats = p426_leg.log_problems(lines, "off", 0)[1]
        assert stats["completed"] == completed and stats["failed"] == failed
        assert all(stamp["session_id"] in ln for ln in lines if "Request completed" in ln)
        m = env["ops"].worker_metrics()["summary"]
        assert m["requests_completed"] == completed and m["requests_failed"] == failed
        assert not out.exists()
    finally:
        env["ops"].cancel()


def test_the_lock_probe_knob_sees_an_inherited_fd_and_nothing_otherwise(tmp_path):
    lock = tmp_path / "LEG.lock"
    lock.write_text("")
    state = tmp_path / "state"
    state.mkdir()
    (state / "worker.json").write_text(json.dumps({"pid": 1, "create_time": 1.0, "model_path": S.HF, "registry_sha256": "a" * 64}))
    base = [sys.executable, str(S.PROBE), "--model", S.MODEL, "--items", "", "--lang", "python", "--seed-base", "1",
            "--out", str(tmp_path / "o.jsonl"), "--cancel-file", str(tmp_path / "c"), "--manifest-ack", str(tmp_path / "a"),
            "--frozen-prompt-date", S.EPOCH_DATE]
    (tmp_path / "a").write_text("")
    penv = dict(os.environ, FAKE_PROBE_STATE=str(state), B2_LOCK_PROBE=str(lock), B2_ITEM_BARRIER="on")
    fd = os.open(lock, os.O_RDWR)
    try:
        for inherit, rows in ((True, "o.jsonl"), (False, "o2.jsonl")):
            argv = list(base)
            argv[argv.index("--out") + 1] = str(tmp_path / rows)
            for p in (tmp_path / "a",):
                p.write_text("") if not p.exists() else None
            got = subprocess.run(argv, env=penv, pass_fds=(fd,) if inherit else (), capture_output=True, timeout=60)
            seen = json.loads((state / "lockcheck.json").read_text())["inherited_fds"]
            assert got.returncode in (0, 2) and (bool(seen) is inherit), (inherit, seen, got.stdout[-300:])
    finally:
        os.close(fd)


# ------------------------------------------------------------------------------------------------ delivery 1e: §16.5 / §16.6 fixtures
def test_the_p426_world_carries_the_section_16_5_seams_and_the_owned_start_time(tmp_path, monkeypatch):
    env = S.p426_world(tmp_path, monkeypatch, arm="on")
    try:
        ops = env["ops"]
        ident = ops.load(S.MODEL)
        assert ops.expected_worker_argv(ops.overlay, S.MODEL) == ops.proc_argv(ident["pid"])
        assert ops.busy_procs() == [] and ops.descendants(12345) == set()
        assert ops.create_time(ident["pid"]) == ident["create_time"] == ops.worker_ident(S.MODEL)["create_time"]
        assert ops.create_time(1) == 1.0
    finally:
        env["ops"].cancel()


def test_the_gate_json_builder_follows_the_gates_writer():
    src = (S.REPO / "scripts/session_pinning_gate.py").read_text()
    assert 'res["A4_opencode"]' in src and 'res["A6_bare_anonymous"]' in src
    assert 'out.append({"cached": r["cached_tokens"], "prompt": r["prompt_tokens"],' in src
    doc = S.a4_gate_doc(S.a4_receipt([("ses_a", 0, 1)] * 4), [("anon:1", 0, 3100), ("anon:2", 0, 3101), ("anon:3", 2600, 3102)])
    assert [set(r) for r in doc["A6_bare_anonymous"]["requests"]] == [{"cached", "prompt", "session"}] * 3
    assert doc["A4_opencode"]["session_id"] == "ses_a"
