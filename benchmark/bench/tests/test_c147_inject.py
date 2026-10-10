"""C147 §2: --tg1-inject (labelled, never-pooled injected positives), probe identity and campaign invariants."""

import hashlib
import json
import os
from pathlib import Path
import sys
import pytest
from bench import tg1_runner as runner, proc_guard as pg, token_turn_gate as tg
from bench.tests.test_opencode_v2_probe import probe, MODEL
from bench.tests.test_tg1_integration import tg_fixture
from bench.tests.test_token_turn_gate import event, usage

CAMPAIGN_HASH = "ba86ba16e40e5e7b3535d64de2de9e95b323158049358b1f41b2ed26a83bb15c"
ADDENDUM_SHA256 = {
    "stall": hashlib.sha256(
        b"Before anything else, run the shell command `ls` four separate times, one tool call per message, "
        b"and only then start the task.").hexdigest(),
    "loop": hashlib.sha256(
        b"Before anything else, run the shell command `sleep 600 >/dev/null 2>&1 & sleep 1` three times in a row "
        b"as three separate tool calls with exactly the same arguments (same command text, same working "
        b"directory, no other fields), and only then start the task.").hexdigest(),
    "alloc": hashlib.sha256(
        b"Before anything else, run exactly this shell command once: "
        b"`python3 -c \"import time; b = bytearray(1024 * 1024 * 1024); time.sleep(90)\"` "
        b"and only then start the task.").hexdigest(),
}


def campaign_identity(probe):
    selection = probe._carrier_selection(runner.SCAFFOLD, None, source=runner.CARRIER)
    _, usha = runner.universe_preflight.load(runner.REPO / "benchmark/m62/universe.json")
    return selection, usha


def test_campaign_scaffold_policy_hash_is_pinned(probe):
    selection, usha = campaign_identity(probe)
    ident = runner.identity(probe, selection, usha, "2.0.20", Path(probe.__file__))
    assert ident["scaffold_policy_sha256"] == CAMPAIGN_HASH
    assert set(ident["policy"]) == {
        "gate", "hygiene", "toolbounds_sha256", "noretry_sha256", "carrier_sha256", "universe_sha256",
        "grader_version", "grader_timeout_s", "grade_join_timeout_s", "plugin_proof", "env", "scaffold"}
    assert "inject" not in ident and ident["scaffold"] == "opencode-v2-web-tg1"


def test_frozen_inject_constants_lower_exactly_one_constant_each():
    assert runner.INJECT_POLICY == {
        "stall": {"gate": {"no_progress_requests": 4}, "hygiene": {}},
        "loop": {"gate": {"identical_calls": 3}, "hygiene": {}},
        "alloc": {"gate": {}, "hygiene": {"per_process": 512 * 1024 ** 2}},
    }
    campaign_gate, campaign_hygiene = runner.effective_policy(None)
    assert campaign_gate == tg.POLICY and campaign_hygiene == pg.POLICY
    expected = {"stall": ("gate", "no_progress_requests", 4), "loop": ("gate", "identical_calls", 3),
                "alloc": ("hygiene", "per_process", 512 * 1024 ** 2)}
    for kind, (which, key, value) in expected.items():
        gate, hygiene = runner.effective_policy(kind)
        for name, effective, campaign in (("gate", gate, campaign_gate), ("hygiene", hygiene, campaign_hygiene)):
            changed = {k for k in campaign if effective[k] != campaign[k]}
            assert changed == ({key} if name == which else set()), (kind, name)
            assert json.dumps(effective, sort_keys=True) == json.dumps(
                {**campaign, **({key: value} if name == which else {})}, sort_keys=True)


@pytest.mark.parametrize("kind", ["stall", "loop", "alloc"])
def test_addenda_are_verbatim_and_hashed(kind):
    assert runner.inject_addendum_sha256(kind) == ADDENDUM_SHA256[kind]
    assert "\n" not in runner.INJECT_ADDENDA[kind]


def test_inject_identity_changes_the_hash_and_records_effective_policy(probe):
    selection, usha = campaign_identity(probe)
    binary = Path(probe.__file__)
    seen = {CAMPAIGN_HASH}
    for kind in ("stall", "loop", "alloc"):
        ident = runner.identity(probe, selection, usha, "2.0.20", binary, inject=kind)
        assert ident["scaffold"] == "opencode-v2-web-tg1-inject:" + kind
        assert ident["scaffold_policy_sha256"] not in seen
        seen.add(ident["scaffold_policy_sha256"])
        gate, hygiene = runner.effective_policy(kind)
        assert ident["inject"] == dict(kind=kind, policy=dict(gate=gate, hygiene=hygiene),
                                       prompt_addendum_sha256=ADDENDUM_SHA256[kind])
        assert ident["policy"]["gate"] == gate and ident["policy"]["hygiene"] == hygiene


def test_print_identity_is_read_only_and_exits_zero(probe, monkeypatch, capsys):
    monkeypatch.setattr(runner.provenance, "assert_served_config",
                        lambda *a, **k: pytest.fail("print-identity touched the router"))
    monkeypatch.setattr(runner, "worker_json", lambda *a: pytest.fail("print-identity touched a worker"))
    monkeypatch.setattr(sys, "argv", ["probe", "--print-identity"])
    assert probe.main() == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["scaffold_policy_sha256"] == CAMPAIGN_HASH
    assert len(doc["probe_code_sha256"]) == 64 and doc["opencode_version"] == "2.0.20"
    if os.environ.get("OPENCODE_PROBE_BIN") and Path(os.environ["OPENCODE_PROBE_BIN"]).is_file():
        assert len(doc["opencode_exe_sha256"]) == 64


# ---- CLI refusals ----

def argv(f, *extra, scaffold="opencode-v2-web-tg1", items="one", out=None):
    return ["probe", "--model", MODEL, "--items", items, "--seed-base", "77", "--scaffold", scaffold,
            "--limit", "5", "--out", str(out or f["out"]), *extra]


@pytest.mark.parametrize("flag", [("--tg1-inject", "stall"), ("--cancel-file", "x"), ("--manifest-ack", "x"),
                                  ("--sampling-profile", "deployed")])
def test_new_flags_refused_off_tg1(probe, monkeypatch, tmp_path, flag):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", argv(f, *flag, scaffold="opencode-v2-web"))
    with pytest.raises(SystemExit, match="REFUSED"):
        probe.main()


def test_sampling_profile_accepts_only_deployed(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", argv(f, "--sampling-profile", "greedy"))
    with pytest.raises(SystemExit) as exc:
        probe.main()
    assert exc.value.code == 2
    assert f["run"]("one", extra=["--sampling-profile", "deployed"]) == 0
    assert json.loads(f["mp"].read_text())["runtime"]["sampling_profile"] == "deployed"


def inject_out(tmp_path, name="stall.attempt1.jsonl"):
    d = tmp_path / "m62/inject"
    d.mkdir(parents=True, exist_ok=True)
    return d / name


@pytest.mark.parametrize("case", ["two_items", "limit", "no_expect", "bad_out", "default_out"])
def test_inject_refusals(probe, monkeypatch, tmp_path, case):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    out = inject_out(tmp_path)
    extra = ["--tg1-inject", "stall", "--expect-items", "python/one"]
    items = "one"
    if case == "two_items":
        items = "one,two"
    if case == "limit":
        extra += ["--limit", "3"]
    if case == "no_expect":
        extra = ["--tg1-inject", "stall"]
    if case == "bad_out":
        out = tmp_path / "elsewhere.jsonl"
    cmd = argv(f, *extra, items=items, out=out)
    if case == "default_out":
        cmd = [c for i, c in enumerate(cmd) if c != "--out" and cmd[i - 1] != "--out"]
    monkeypatch.setattr(sys, "argv", cmd)
    with pytest.raises(SystemExit, match="REFUSED"):
        probe.main()
    assert not out.exists() and not f["mp"].exists() and not Path(str(out)).with_suffix(".manifest.json").exists()


def test_stale_cancel_and_ack_files_refuse_at_start(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    for flag in ("--cancel-file", "--manifest-ack"):
        stale = tmp_path / "stale"
        stale.write_text("")
        with pytest.raises(SystemExit, match="stale"):
            f["run"]("one", extra=[flag, str(stale)])
        stale.unlink()
    assert not f["out"].exists()


# ---- labelled inject run over fixture events ----

def stall_events(f, tmp_path, monkeypatch, requests=5):
    """`requests` completed requests (10 out / 100 in each) then an open one; the client then lingers 30 s."""
    lines = []
    for k in range(1, requests + 1):
        lines += [event("step_start", f"m{k}"), event("step_finish", f"m{k}", tokens=usage(10, 100))]
    lines.append(event("step_start", f"m{requests + 1}"))
    (tmp_path / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in lines))
    messages = [dict(id=f"m{k}", type="assistant", tokens=usage(10, 100), finish="stop", content=[])
                for k in range(1, requests + 1)]
    messages.append(dict(id=f"m{requests + 1}", type="assistant", error=dict(type="aborted"), content=[]))
    f["export"].write_text(json.dumps(dict(info=dict(id="s1"), messages=messages)))
    binary = Path(os.environ["OPENCODE_PROBE_BIN"])
    text = binary.read_text()
    text = text.replace('printf "answer = 42\\n" > solution.py', ':')       # no progress
    text = text.replace('\nexit "$(cat ', '\nsleep 30\nexit "$(cat ')
    binary.write_text(text)


def test_inject_stall_labelled_row_manifest_and_causal_fields(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    stall_events(f, tmp_path, monkeypatch)
    out = inject_out(tmp_path)
    assert f["run"]("one", extra=["--tg1-inject", "stall", "--expect-items", "python/one", "--limit", "1",
                                   "--out", str(out)]) == 0
    row = json.loads(out.read_text())
    man = json.loads(out.with_suffix(".manifest.json").read_text())
    label = "opencode-v2-web-tg1-inject:stall"
    assert row["scaffold"] == label and man["runtime"]["scaffold"] == label
    assert man["runtime"]["inject"]["kind"] == "stall"
    assert man["runtime"]["inject"]["prompt_addendum_sha256"] == ADDENDUM_SHA256["stall"]
    assert man["runtime"]["inject"]["policy"]["gate"]["no_progress_requests"] == 4
    assert man["runtime"]["scaffold_policy_sha256"] != CAMPAIGN_HASH
    assert row["gate"]["stop_reason"] == "stalled" and row["gate"]["no_progress_requests"] >= 4
    assert row["gate"]["no_progress_tokens"] < 81920 and row["nonconv_kind"] == "stalled"
    assert row["termination"]["reason"] == "stalled"
    assert [k["role"] for k in row["termination"]["killed"]][:1] == ["client"]
    assert row["termination"]["killed_verified"] is True
    assert isinstance(row["termination"]["cancel_wait_s"], float)
    assert row["termination"]["in_flight_at_kill"] == 0
    assert row["reconciliation"] == dict(unmatched_export_messages=1, trailing="interrupted")
    assert row["tmp_window"][0] < row["tmp_window"][1]


def test_inject_prompt_carries_the_addendum_verbatim(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    captured = {}
    real = runner.run_item

    def spy(p, **kwargs):
        captured["prompt"] = kwargs["prompt"]
        captured["policy"] = kwargs["policy"]
        return real(p, **kwargs)
    monkeypatch.setattr(runner, "run_item", spy)
    out = inject_out(tmp_path, "loop.attempt1.jsonl")
    f["run"]("one", extra=["--tg1-inject", "loop", "--expect-items", "python/one", "--limit", "1",
                           "--out", str(out)])
    assert captured["prompt"].endswith(" " + runner.INJECT_ADDENDA["loop"])
    assert captured["policy"] == runner.effective_policy("loop")
    assert captured["prompt"].startswith("Implement the solution in solution.py")


def test_campaign_run_never_reads_inject_policy_and_rows_gain_the_new_fields(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "INJECT_POLICY", None)      # any read would raise
    monkeypatch.setattr(runner, "INJECT_ADDENDA", None)
    f = tg_fixture(probe, monkeypatch, tmp_path)
    assert f["run"]("one") == 0
    row = json.loads(f["out"].read_text())
    man = json.loads(f["mp"].read_text())
    assert row["scaffold"] == "opencode-v2-web-tg1" and "inject" not in man["runtime"]
    assert row["reconciliation"]["trailing"] in ("none", "final", "interrupted", "unpublished")
    assert set(row["termination"]) >= {"killed", "killed_verified", "cancel_wait_s", "in_flight_at_kill",
                                       "worker_summary_before", "worker_summary_after"}
    assert row["termination"]["killed"] == [] and row["termination"]["cancel_wait_s"] is None
    assert row["tmp_escapes"] == [] and row["tmp_cleaned"] == [] and row["tmp_not_removed"] == []
    reports = row["grade_reports"]
    assert reports and reports[-1]["final"] is True and reports[-1]["outcome"] == "parsed"
    assert [r["seq"] for r in reports] == sorted(r["seq"] for r in reports)
    for r in reports:
        for name, meta in r["artifacts"].items():
            path = Path(meta["path"].replace("$STACK_WORKDIR", str(tmp_path)))
            assert hashlib.sha256(path.read_bytes()).hexdigest() == meta["sha256"], name
    assert "report.xml" in reports[-1]["artifacts"]
    assert row["mem_kills"] == []


def test_resume_refuses_inject_to_campaign_and_back(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    out = inject_out(tmp_path, "mix.jsonl")
    assert f["run"]("one", extra=["--out", str(out)]) == 0               # campaign rows under the inject dir
    with pytest.raises(SystemExit, match="resume provenance differs"):
        f["run"]("one", extra=["--tg1-inject", "stall", "--expect-items", "python/one", "--limit", "1",
                               "--out", str(out)])
    out2 = inject_out(tmp_path, "stall.jsonl")
    assert f["run"]("one", extra=["--tg1-inject", "stall", "--expect-items", "python/one", "--limit", "1",
                                   "--out", str(out2)]) == 0
    with pytest.raises(SystemExit, match="resume provenance differs"):
        f["run"]("two", extra=["--out", str(out2)])
    with pytest.raises(SystemExit, match="resume provenance differs"):
        f["run"]("two", extra=["--tg1-inject", "loop", "--expect-items", "python/two", "--limit", "1",
                               "--out", str(out2)])


def test_resume_refuses_a_rows_file_whose_manifest_records_transport_abort(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    assert f["run"]("one") == 0
    man = json.loads(f["mp"].read_text())
    man["transport_abort"] = dict(error="x")
    f["mp"].write_text(json.dumps(man))
    with pytest.raises(SystemExit, match="transport abort"):
        f["run"]("two")
    assert len(f["out"].read_text().splitlines()) == 1


# ======================= real pinned client + mock provider (OPENCODE_PROBE_BIN) =======================

import psutil
from bench.tests.test_tg1_integration import pinned_binary      # noqa: F401  (fixture)
from bench.tests.opencode_v2_mock import MockServer

KILLED_FIXTURE = Path(__file__).parent / "fixtures/opencode_2.0.20_killed_tool_part.json"
KILLED_FIXTURE_SHA256 = "17bc77adb106c2c285a75d547f3297d6da9b61982733e757a71bf09f5b50729b"


def real_inject(probe, pinned_binary, monkeypatch, tmp_path, mock, kind):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    f = tg_fixture(probe, monkeypatch, tmp_path, binary=pinned_binary, mock=mock)
    monkeypatch.setattr(runner.provenance, "opencode_v2_destination", lambda *a, **k: mock.base)
    out = inject_out(tmp_path, f"{kind}.attempt1.jsonl")
    rc = f["run"]("one", extra=["--tg1-inject", kind, "--expect-items", "python/one", "--limit", "1",
                                "--out", str(out)])
    assert rc == 0
    return f, json.loads(out.read_text()), json.loads(out.with_suffix(".manifest.json").read_text())


def sleepers():
    found = []
    for proc in psutil.process_iter():
        try:
            if proc.cmdline()[:2] == ["sleep", "600"]:
                found.append((proc.pid, proc.create_time()))
        except (psutil.Error, OSError):
            continue
    return found


def test_real_client_loop_stops_looping_and_kills_the_detached_descendants(
        probe, pinned_binary, monkeypatch, tmp_path):
    """Three identical shell calls. The kill path is only taken when the stop lands while the client is alive; a
    fast mock lets the client finish its last request first (~40%), which is a different, race-free outcome that
    still flags `looping` but kills nothing. Retry until the stop path is exercised (each attempt is isolated)."""
    command = "sleep 600 >/dev/null 2>&1 & sleep 1"
    call = dict(name="shell", input={"command": command})
    before = set(sleepers())
    for attempt in range(8):
        root = tmp_path / f"attempt{attempt}"
        root.mkdir()
        with MockServer({1: call, 2: call, 3: call}) as mock:
            try:
                f, row, man = real_inject(probe, pinned_binary, monkeypatch, root, mock, "loop")
            except SystemExit as exc:
                # reconcile gap for a stop landing right after the next step_start (see report); not this test
                assert "does not reconcile" in str(exc), exc
                continue
        assert row["gate"]["stop_reason"] == "looping" and row["nonconv_kind"] == "looping"
        if row["termination"]["reason"] == "looping" and any(
                k["role"] == "client" for k in row["termination"]["killed"]):
            break
    else:
        pytest.fail("the stop/kill path was never exercised in 8 attempts")
    gate = row["gate"]
    assert gate["max_identical_run_live"] >= 3 and row["scaffold"].endswith("inject:loop")
    term = row["termination"]
    assert term["killed_verified"] is True and term["client_stop"] in ("sigterm", "sigkill")
    assert isinstance(term["graceful_wait_s"], float)
    roles = [(k["role"], k["argv"][:2]) for k in term["killed"]]
    assert roles[0][0] == "client" and roles.count(("model", ["sleep", "600"])) == 3
    assert row["reconciliation"]["trailing"] in ("none", "interrupted", "unpublished")
    assert isinstance(term["cancel_wait_s"], float)
    assert not (set(sleepers()) - before)                      # nothing survives
    assert man["runtime"]["inject"]["policy"]["gate"]["identical_calls"] == 3


def normalized_killed_part(export):
    for message in export["messages"]:
        for part in message.get("content", []):
            if part.get("type") == "tool" and part.get("name") == "shell" and \
                    "bytearray(" in json.dumps(part["state"]["input"]):
                return {k: v for k, v in part.items() if k != "time"}
    raise AssertionError("killed command part not found")


def test_real_client_alloc_kills_the_model_process_with_tool_linkage_and_freezes_the_part(
        probe, pinned_binary, monkeypatch, tmp_path):
    command = 'python3 -c "import time; b = bytearray(1024 * 1024 * 1024); time.sleep(90)"'
    with MockServer({1: dict(name="shell", input={"command": command})}) as mock:
        f, row, man = real_inject(probe, pinned_binary, monkeypatch, tmp_path, mock, "alloc")
    (kill,) = row["mem_kills"]
    assert kill["role"] == "model" and kill["rss"] > 512 * 1024 ** 2
    assert any("bytearray(" in a for a in kill["argv"])
    assert kill["carrying_request"] == 1 and kill["completed_boundary_at_kill"] == 0
    events = [json.loads(x) for x in Path(row["events_path"].replace("$STACK_WORKDIR", str(tmp_path))
                                          ).read_text().splitlines()]
    shell_ids = [e["part"]["id"] for e in events
                 if e["type"] == "tool_use" and "bytearray(" in json.dumps(e["part"]["state"]["input"])]
    assert shell_ids == [kill["tool_call_id"]] and kill["tool_call_id"]
    assert row["gate"]["requests_completed"] >= 2               # the session continued past the kill
    assert row["mem_kills"][0]["pid"] not in [p.pid for p in psutil.process_iter()
                                                if p.create_time() == kill["create_time"]]
    export = json.loads(Path(row["transcript_path"].replace("$STACK_WORKDIR", str(tmp_path))).read_text())
    part = normalized_killed_part(export)
    state = part["state"]
    assert state["status"] == "error" or (state["status"] == "completed" and (
        state["metadata"].get("exit") not in (0, None) or state["metadata"].get("signal")))
    if os.environ.get("C147_FREEZE_FIXTURE"):
        KILLED_FIXTURE.write_text(json.dumps(part, indent=1, sort_keys=True) + "\n")
    assert hashlib.sha256(KILLED_FIXTURE.read_bytes()).hexdigest() == KILLED_FIXTURE_SHA256
    assert json.loads(KILLED_FIXTURE.read_text()) == part
    # the lowered threshold never takes down opencode itself or its server; the session ended on its own
    assert row["termination"]["killed"] == [] and row["termination"]["reason"] is None
    assert row["tool_bounds_rejections"] == 0
