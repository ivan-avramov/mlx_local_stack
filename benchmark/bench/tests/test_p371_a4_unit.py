"""P371 phase 2b, plan 4 A4: tool-window receipts (`toolwindows.js` -> `bench.toolwindows`), the adapter's merge of open
windows (start receipts) with completed `tool_use` events by call id, per-tick validation (a contract violation aborts the
chain's attempt, never a transport class), the M64 four-plugin run dir / env check / activation proof, the watchdog
flag and the final tick through the core."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from bench import arm_adapter as aa
from bench import arm_opencode as ao
from bench import arm_runner
from bench import arm_watchdog as wd
from bench import provenance
from bench import run_config as rc
from bench import token_turn_gate as tg
from bench import toolwindows as tw
from bench import worker_receipts as wr
from bench.tests.arm_neutral import NeutralArm
from bench.tests.p371_world import evidence, manifest, rows, run_core, template, world      # noqa: F401  (fixture)
from bench.tests.test_opencode_v2_probe import MODEL, tg1_probe as probe          # noqa: F401  (fixture)
from bench.tests.test_token_turn_gate import event, usage

REPO = Path(__file__).resolve().parents[3]
PLUGIN = REPO / "benchmark/opencode_plugins/toolwindows.js"
FROZEN = "Mon Jan 05 2026"
ATTEMPT = "python/one#a1.r0"


def rec(seq, phase="start", call="c1", tool="shell", ms=1_000_000, session="s1", attempt=ATTEMPT, **over):
    return dict(attempt_id=attempt, session_id=session, call_id=call, tool=tool, phase=phase, seq=seq, ms=ms, **over)


def write(path, *records, raw=None):
    Path(path).write_text(raw if raw is not None else "".join(json.dumps(r) + "\n" for r in records))


def reader(tmp_path, *records, raw=None):
    path = tmp_path / "tw.jsonl"
    write(path, *records, raw=raw)
    return tw.Receipts(path, ATTEMPT), path


# ---------------------------------------------------------------- the helpers module
def test_env_names_and_env_for(tmp_path):
    assert tw.ENV_RECEIPTS == "BENCH_TOOLWINDOW_RECEIPTS" and tw.ENV_ATTEMPT == "BENCH_ATTEMPT_ID"
    assert tw.env_for(ATTEMPT, tmp_path / "x.jsonl") == {tw.ENV_RECEIPTS: str(tmp_path / "x.jsonl"), tw.ENV_ATTEMPT: ATTEMPT}
    for bad in (("", tmp_path / "x"), (ATTEMPT, "relative/x.jsonl"), (None, tmp_path / "x")):
        with pytest.raises(ValueError):
            tw.env_for(*bad)


def test_a_start_receipt_opens_a_window_and_an_end_receipt_closes_it(tmp_path):
    r, _ = reader(tmp_path, rec(1), rec(2, "end", ms=1_005_000))
    r.poll("s1")
    assert r.calls == {"c1": dict(tool="shell", start_ms=1_000_000, end_ms=1_005_000, session="s1")}
    r, _ = reader(tmp_path, rec(1))
    r.poll("s1")
    assert r.calls["c1"]["end_ms"] is None


def test_polling_is_incremental_and_a_torn_tail_waits_for_its_newline(tmp_path):
    r, path = reader(tmp_path, raw=json.dumps(rec(1)) + "\n" + json.dumps(rec(2, "end"))[:30])
    r.poll("s1")
    assert r.seq == 1 and r.calls["c1"]["end_ms"] is None                 # the torn second line is not consumed yet
    path.write_text(json.dumps(rec(1)) + "\n" + json.dumps(rec(2, "end")) + "\n")
    r.poll("s1")
    assert r.seq == 2 and r.calls["c1"]["end_ms"] == 1_000_000
    r.poll("s1")
    assert r.seq == 2                                                     # nothing is read twice


def test_a_torn_tail_at_the_final_poll_is_corrupt(tmp_path):
    r, _ = reader(tmp_path, raw=json.dumps(rec(1)) + "\n" + json.dumps(rec(2, "end"))[:30])
    r.poll("s1")
    with pytest.raises(aa.ArmContractError, match="torn"):
        r.poll("s1", final=True)


@pytest.mark.parametrize("raw,why", [
    ('not json\n', "not JSON"), ('[1]\n', "not an object"),
    (json.dumps(rec(1, extra=1)) + "\n", "keys"), (json.dumps({k: v for k, v in rec(1).items() if k != "ms"}) + "\n", "keys"),
    (json.dumps(rec(1, phase="middle")) + "\n", "phase"), (json.dumps(rec(1, ms="x")) + "\n", "ms"),
    (json.dumps(rec(1, ms=True)) + "\n", "ms"), (json.dumps(rec(1, call="")) + "\n", "call_id"),
    (json.dumps(rec(1, tool=5)) + "\n", "tool"),
    (json.dumps(rec(1)) + "\n" + json.dumps(rec(3, "end")) + "\n", "sequence"),                  # a gap
    (json.dumps(rec(1)) + "\n" + json.dumps(rec(1, "end")) + "\n", "sequence"),                  # a repeat
    (json.dumps(rec(2)) + "\n", "sequence"),                                                     # starts at 2
    (json.dumps(rec(1, attempt="other#a1.r0")) + "\n", "attempt"),
    (json.dumps(rec(1)) + "\n" + json.dumps(rec(2, call="c1")) + "\n", "twice"),                 # two starts for one call
    (json.dumps(rec(1, "end")) + "\n", "without a start"),
    (json.dumps(rec(1)) + "\n" + json.dumps(rec(2, "end")) + "\n" + json.dumps(rec(3, "end")) + "\n", "twice"),
    (json.dumps(rec(1)) + "\n" + json.dumps(rec(2, "end", ms=999_000)) + "\n", "before its start"),
])
def test_a_corrupt_or_out_of_order_receipt_aborts_with_a_contract_error(tmp_path, raw, why):
    r, _ = reader(tmp_path, raw=raw)
    with pytest.raises(aa.ArmContractError, match=why):
        r.poll("s1")


def test_a_receipt_for_another_session_aborts_once_the_session_is_known(tmp_path):
    r, _ = reader(tmp_path, rec(1, session="sX"))
    r.poll(None)                                                           # session not known yet: held
    with pytest.raises(aa.ArmContractError, match="session"):
        r.poll("s1")


def test_a_missing_receipt_file_is_corrupt(tmp_path):
    with pytest.raises(aa.ArmContractError, match="missing"):
        tw.Receipts(tmp_path / "gone.jsonl", ATTEMPT).poll("s1")


def test_the_contract_error_is_not_a_transport_abort():
    assert issubclass(aa.ArmContractError, ValueError) and not issubclass(aa.ArmContractError, tg.TransportAbort)


# ---------------------------------------------------------------- the adapter: windows from receipts + events
def m64_arm(p):
    return ao.OpencodeArm(p, mode="m64", search=ao.OfflineTestSearchService())


def tool_use(call, tool="shell", start=1_000, end=3_500, status="completed", error=None):
    state = dict(status=status, input={"command": "ls"}, metadata={}, time=dict(start=start, end=end))
    if status == "error":
        state["error"] = error or "boom"
    else:
        state.update(output="x", title=tool)
    return dict(type="tool_use", sessionID="s1", part=dict(partID="p-" + call, id=call, messageID="m1", type="tool",
                                                           tool=tool, state=state))


def bound(probe, tmp_path, *events, records=()):
    arm = m64_arm(probe)
    stream = arm.new_stream(tg.TokenTurnGate(3), lambda n: None)
    path = tmp_path / "tw.jsonl"
    write(path, *records)
    arm.bind_stream(stream, paths=dict(toolwindows=path), attempt=wr.AttemptContext.make("python/one", 1))
    stream.feed("".join(json.dumps(e) + "\n" for e in [event("step_start"), *events]).encode())
    return arm, stream, path


def test_an_open_window_comes_from_a_start_receipt_alone(probe, tmp_path):
    arm, stream, _ = bound(probe, tmp_path, records=[rec(1, ms=5_000)])
    assert arm.tool_windows(stream) == [(5.0, None, "shell")]


def test_a_window_closed_by_its_end_receipt_before_the_event_arrives(probe, tmp_path):
    arm, stream, _ = bound(probe, tmp_path, records=[rec(1, ms=5_000), rec(2, "end", ms=9_000)])
    assert arm.tool_windows(stream) == [(5.0, 9.0, "shell")]


def test_a_completed_tool_use_event_wins_by_call_id_and_is_counted_once(probe, tmp_path):
    arm, stream, _ = bound(probe, tmp_path, tool_use("c1", start=5_100, end=8_900),
                           records=[rec(1, ms=5_000), rec(2, "end", ms=9_000)])
    assert arm.tool_windows(stream) == [(5.1, 8.9, "shell")]


def test_open_and_completed_windows_merge_in_a_stable_order(probe, tmp_path):
    arm, stream, _ = bound(probe, tmp_path, tool_use("c1", start=1_000, end=2_000),
                           records=[rec(1, ms=1_000), rec(2, "end", ms=2_000), rec(3, call="c2", ms=3_000)])
    assert arm.tool_windows(stream) == [(1.0, 2.0, "shell"), (3.0, None, "shell")]


def test_a_tool_use_without_a_start_receipt_is_a_contract_error(probe, tmp_path):
    arm, stream, _ = bound(probe, tmp_path, tool_use("c9"), records=[])
    with pytest.raises(aa.ArmContractError, match="c9.*start receipt"):
        arm.tool_windows(stream)


def test_a_call_rejected_by_toolbounds_never_reached_the_window_hooks(probe, tmp_path):
    arm, stream, _ = bound(probe, tmp_path, tool_use("c9", status="error",
                                                      error="M62_TOOL_BOUND: shell background must be false"))
    assert arm.tool_windows(stream) == [(1.0, 3.5, "shell")]               # no receipt required, no window opened by it
    arm, stream, _ = bound(probe, tmp_path, tool_use("c9", status="error", error="Permission denied: webfetch"))
    with pytest.raises(aa.ArmContractError, match="start receipt"):
        arm.tool_windows(stream)


def test_a_receipt_of_another_session_or_attempt_aborts_the_tick(probe, tmp_path):
    arm, stream, _ = bound(probe, tmp_path, records=[rec(1, session="sX")])
    with pytest.raises(aa.ArmContractError, match="session"):
        arm.tool_windows(stream)
    arm, stream, _ = bound(probe, tmp_path, records=[rec(1, attempt="python/two#a1.r0")])
    with pytest.raises(aa.ArmContractError, match="attempt"):
        arm.tool_windows(stream)


def test_a_missing_or_gapped_receipt_file_aborts_the_tick(probe, tmp_path):
    arm, stream, path = bound(probe, tmp_path, records=[rec(1)])
    arm.tool_windows(stream)
    path.unlink()
    with pytest.raises(aa.ArmContractError, match="missing"):
        arm.tool_windows(stream)
    arm, stream, _ = bound(probe, tmp_path, records=[rec(1), rec(3, "end")])
    with pytest.raises(aa.ArmContractError, match="sequence"):
        arm.tool_windows(stream)


def test_the_final_poll_rejects_a_torn_tail(probe, tmp_path):
    arm, stream, path = bound(probe, tmp_path, records=[rec(1)])
    path.write_text(json.dumps(rec(1)) + "\n" + json.dumps(rec(2, "end"))[:20])
    arm.tool_windows(stream)                                              # mid-run: waits
    with pytest.raises(aa.ArmContractError, match="torn"):
        arm.tool_windows(stream, final=True)


def test_a_configuration_without_receipts_keeps_the_event_windows_only(probe, tmp_path):
    arm = ao.OpencodeArm(probe, mode="tg1")
    stream = arm.new_stream(tg.TokenTurnGate(3), lambda n: None)
    arm.bind_stream(stream, paths={}, attempt=wr.AttemptContext.make("python/one", 1))
    stream.feed("".join(json.dumps(e) + "\n" for e in [event("step_start"), tool_use("c1")]).encode())
    assert arm.tool_windows(stream) == [(1.0, 3.5, "shell")]


# ---------------------------------------------------------------- the watchdog
def test_window_keys_are_stable_when_a_window_is_inserted_before_others():
    d = wd.ShellWatchdog(limit_s=5, grace_s=1, clock=lambda: 100.0, listing=lambda: [], alive=lambda *a: False,
                         send=lambda *a: None)
    d.set_windows([(0, 10, "a"), (12, 20, "b")])
    d.tick()
    d.set_windows([(0, 10, "a"), (1, 9, "x"), (12, 20, "b")])
    d.tick()
    assert sorted(o["name"] for o in d.window_overruns) == ["a", "b", "x"] and d.exec_timeout


def test_an_overrun_of_a_completed_window_alone_is_an_exec_timeout():
    d = wd.ShellWatchdog(limit_s=5, grace_s=1, clock=lambda: 100.0, listing=lambda: [], alive=lambda *a: False,
                         send=lambda *a: None)
    d.set_windows([(0, 10, "a")])
    assert d.tick() == [] and d.exec_timeout is True and d.kills == []


# ---------------------------------------------------------------- run dir, env, activation, identity
def tree_names(run):
    return sorted(p.name for p in (Path(run) / "cfg/opencode/plugins").iterdir())


def test_the_m64_run_dir_loads_four_plugins_and_tg1_keeps_three(probe, tmp_path):
    m = m64_arm(probe)
    assert tree_names(m.make_run_dir(tmp_path / "a", "r1", m.selection())) == [
        "datefreeze.js", "noretry.js", "toolbounds.js", "toolwindows.js"]
    t = ao.OpencodeArm(probe, mode="tg1")
    assert tree_names(t.make_run_dir(tmp_path / "b", "r1", t.selection())) == ["datefreeze.js", "noretry.js", "toolbounds.js"]


def test_the_m64_env_names_the_item_receipt_file_and_the_attempt(probe, tmp_path):
    arm = m64_arm(probe)
    run = arm.make_run_dir(tmp_path, "r1", arm.selection())
    scratch = tmp_path / "s"
    scratch.mkdir()
    ctx = wr.AttemptContext.make("python/one", 1)
    env = arm.build_env(run, scratch, arm.seed_overlay(MODEL, 7), receipts=tmp_path / "d.jsonl", frozen_date=FROZEN,
                        toolwindow_receipts=tmp_path / "ev/t.jsonl", attempt=ctx)
    assert env[tw.ENV_RECEIPTS] == str(tmp_path / "ev/t.jsonl") and env[tw.ENV_ATTEMPT] == "python/one#a1.r0"
    arm.verify_env(env, run, arm.selection(), arm.seed_overlay(MODEL, 7))
    tg = ao.OpencodeArm(probe, mode="tg1")
    run1 = tg.make_run_dir(tmp_path / "t", "r1", tg.selection())
    env1 = tg.build_env(run1, scratch, tg.seed_overlay(MODEL, 7), receipts=tmp_path / "d.jsonl", frozen_date=FROZEN,
                        toolwindow_receipts=tmp_path / "ev/t.jsonl", attempt=ctx)
    assert tw.ENV_RECEIPTS not in env1 and tw.ENV_ATTEMPT not in env1


@pytest.fixture
def m64_env(probe, tmp_path):
    arm = m64_arm(probe)
    sel = arm.selection()
    run = arm.make_run_dir(tmp_path, "r1", sel)
    scratch = tmp_path / "s"
    scratch.mkdir()
    overlay = arm.seed_overlay(MODEL, 7)
    env = arm.build_env(run, scratch, overlay, receipts=tmp_path / "d.jsonl", frozen_date=FROZEN,
                        toolwindow_receipts=tmp_path / "ev/t.jsonl", attempt=wr.AttemptContext.make("python/one", 1))
    return arm, run, sel, overlay, env


@pytest.mark.parametrize("mutate,why", [
    (lambda e, r: e.pop(tw.ENV_RECEIPTS), "BENCH_TOOLWINDOW_RECEIPTS"),
    (lambda e, r: e.update({tw.ENV_RECEIPTS: "relative/t.jsonl"}), "absolute"),
    (lambda e, r: e.update({tw.ENV_RECEIPTS: str(Path(r) / "cfg/opencode/t.jsonl")}), "outside the config"),
    (lambda e, r: e.pop(tw.ENV_ATTEMPT), "BENCH_ATTEMPT_ID"),
    (lambda e, r: e.update({tw.ENV_ATTEMPT: ""}), "BENCH_ATTEMPT_ID"),
    (lambda e, r: (Path(r) / "cfg/opencode/plugins/toolwindows.js").unlink(), "missing or unexpected"),
    (lambda e, r: (Path(r) / "cfg/opencode/plugins/toolwindows.js").write_text("// edited"), "toolwindows.js sha256"),
])
def test_the_env_check_refuses_a_missing_or_altered_toolwindows_plugin_or_env(m64_env, mutate, why):
    arm, run, sel, overlay, env = m64_env
    mutate(env, run)
    with pytest.raises(provenance.ServedConfigError, match=why):
        arm.verify_env(env, run, sel, overlay)


def test_tg1_refuses_the_toolwindows_env_and_file(probe, tmp_path):
    arm = ao.OpencodeArm(probe, mode="tg1")
    sel = arm.selection()
    run = arm.make_run_dir(tmp_path, "r1", sel)
    scratch = tmp_path / "s"
    scratch.mkdir()
    overlay = arm.seed_overlay(MODEL, 7)
    env = arm.build_env(run, scratch, overlay, receipts=tmp_path / "d.jsonl", frozen_date=FROZEN)
    arm.verify_env(env, run, sel, overlay)
    env[tw.ENV_RECEIPTS] = str(tmp_path / "t.jsonl")
    with pytest.raises(provenance.ServedConfigError, match="toolwindows"):
        arm.verify_env(env, run, sel, overlay)


def test_the_item_env_check_names_exactly_this_items_receipt_file(m64_env, tmp_path):
    arm, run, sel, overlay, env = m64_env
    paths = dict(datefreeze=tmp_path / "d.jsonl", toolwindows=tmp_path / "ev/t.jsonl")
    arm.verify_item_env(env, paths, FROZEN)
    with pytest.raises(tg.TransportAbort, match="tool-window"):
        arm.verify_item_env(env, dict(paths, toolwindows=tmp_path / "ev/other.jsonl"), FROZEN)


def test_evidence_suffixes_add_the_tool_window_file_for_m64_only(probe):
    assert m64_arm(probe).evidence_suffixes()["toolwindows"] == ".toolwindows.jsonl"
    assert "toolwindows" not in ao.OpencodeArm(probe, mode="tg1").evidence_suffixes()


def test_the_watchdog_policy_pins_the_plugin_sha_and_the_tg1_generation_data_is_unchanged():
    assert ao.m64_template().watchdog["toolwindows_sha256"] == hashlib.sha256(PLUGIN.read_bytes()).hexdigest()
    assert not any("toolwindows" in d for d in ao.GENERATION_DATA)


def test_the_snapshot_lists_the_m64_plugin_set(probe, tmp_path, monkeypatch):
    binary = tmp_path / "opencode"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(binary))
    plugins = m64_arm(probe).snapshot().fields["plugins"]
    assert sorted(plugins) == ["datefreeze.js", "noretry.js", "toolbounds.js", "toolwindows.js"]
    assert plugins["toolwindows.js"] == hashlib.sha256(PLUGIN.read_bytes()).hexdigest()
    assert sorted(ao.OpencodeArm(probe, mode="tg1").snapshot().fields["plugins"]) == [
        "datefreeze.js", "noretry.js", "toolbounds.js"]


def test_the_activation_proof_requires_all_four_m64_plugins_loaded(probe, tmp_path):
    arm = m64_arm(probe)
    run = arm.make_run_dir(tmp_path, "r1", arm.selection())
    plugins = Path(run) / "cfg/opencode/plugins"

    def runner(argv, **kw):
        lines = "".join(f'msg="loading plugin" role=server id={(plugins / n).resolve()}\n'
                        for n in ("noretry.js", "toolbounds.js", "datefreeze.js"))
        return subprocess.CompletedProcess(argv, 0, "", lines)

    with pytest.raises(provenance.ServedConfigError, match="load proof missing: toolwindows.js"):
        arm._prove_plugins(tmp_path, {}, run, "/bin/oc", runner)


# ---------------------------------------------------------------- through the core (neutral client, watchdog on)
class Watched(NeutralArm):
    """A neutral client with the shell watchdog on, whose tool windows the test scripts."""
    watchdog_enabled = True

    def __init__(self, p, windows, marker, tail="sleep 0.4"):
        super().__init__(p)
        self.windows, self.marker, self.log, self.tail = windows, marker, [], tail

    def command(self, binary, model, prompt):
        argv = super().command(binary, model, prompt)
        argv[-1] += f"; touch {self.marker}" + (f"; {self.tail}" if self.tail else "")
        return argv

    def tool_windows(self, stream, final=False):
        exited = Path(self.marker).exists()
        self.log.append(("windows", exited, final))
        got = self.windows(exited)
        if isinstance(got, BaseException):
            raise got
        return got

    def transcript(self, *a, **k):
        self.log.append(("transcript",))
        return super().transcript(*a, **k)


def watched_template(limit_s=1.0):
    return template(watchdog=rc.watchdog_on(limit_s=limit_s, grace_s=0.5, toolwindows_sha256="w" * 64))


def go(world, windows, tail="sleep 0.4", **kw):
    adapter = Watched(world.host, windows, world.tmp / "exited", tail)
    out = run_core(world, adapter=adapter, template_=watched_template(), **kw)
    return out[0], adapter


def test_one_final_tick_runs_after_the_client_exit_and_before_the_transcript(world):
    _, adapter = go(world, lambda exited: [(0.0, 5.0, "shell")] if exited else [])
    kinds = [e for e in adapter.log if e[0] in ("windows", "transcript")]
    before = kinds[:kinds.index(("transcript",))]
    assert before[-1][:2] == ("windows", True)                      # the last poll before the transcript saw the exit
    assert all(e[1] is False for e in before[:-1])                  # every in-loop tick ran while the client was alive


def test_a_completed_window_overrun_found_by_the_final_tick_flags_the_row(world):
    _, adapter = go(world, lambda exited: [(0.0, 5.0, "shell")] if exited else [])
    (row,) = rows(world)
    assert "exec_timeout" in row["nonconv_flags"] and row["nonconv_kind"] == "exec_timeout" and row["converged"] is False
    assert row["shell_watchdog"]["window_overruns"][0]["duration_s"] == 5.0 and row["shell_watchdog"]["kills"] == []


def test_a_short_completed_window_does_not_flag_the_row(world):
    go(world, lambda exited: [(0.0, 0.5, "shell")])
    (row,) = rows(world)
    assert row["nonconv_kind"] is None and row["shell_watchdog"]["window_overruns"] == []


def test_a_contract_error_from_the_windows_aborts_the_attempt_without_a_transport_cause(world):
    with pytest.raises(SystemExit, match="REFUSED.*start receipt"):
        go(world, lambda exited: aa.ArmContractError("tool_use c9 has no start receipt"), tail="")
    assert rows(world) == []
    stamp = manifest(world)["transport_abort"]
    assert "cause" not in stamp and "start receipt" in stamp["error"]


def test_the_core_binds_the_stream_to_the_items_evidence_paths_and_attempt(world, monkeypatch):
    seen = {}
    real = NeutralArm.bind_stream
    monkeypatch.setattr(NeutralArm, "bind_stream", lambda self, stream, *, paths, attempt: seen.update(
        paths=dict(paths), attempt=attempt) or real(self, stream, paths=paths, attempt=attempt))
    run_core(world)
    assert seen["attempt"].attempt_id == "fake/one#a1.r0" and set(seen["paths"]) >= {"events", "stderr", "export"}
