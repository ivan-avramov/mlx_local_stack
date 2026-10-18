"""M64 step 4a: opencode wrapped as the first ArmAdapter. The tg1 configuration is byte-for-byte what today's tg1 path
builds (parity); the M64 configuration differs from it only by the enumerated C165 changes."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from bench import arm_adapter as aa
from bench import arm_opencode as ao
from bench import datefreeze, tg1_runner, toolchain
from bench import token_turn_gate as tg
from bench import worker_receipts as wr
from bench.tests.test_opencode_v2_probe import MODEL, tg1_probe as probe          # noqa: F401  (fixture)
from bench.tests.test_token_turn_gate import event, usage

REPO = Path(__file__).resolve().parents[3]
TG1_LABEL = "opencode-v2-web-tg1"
FROZEN = "Mon Jan 05 2026"
SEARCH_ENTRY = {"type": "local", "command": ["searxng-mcp", "--pinned"], "enabled": True}


class FakeSearch(aa.SearchService):
    """A stand-in for the D2 service whose entry shape is whatever the real service will register."""
    available = True

    def __init__(self, entry=SEARCH_ENTRY):
        self.entry = entry

    def require(self):
        return self

    def mcp_entry(self, client):
        assert client == "opencode"
        return copy.deepcopy(self.entry)


def tg1_arm(p):
    return ao.OpencodeArm(p, mode="tg1")


def m64_arm(p, search=None):
    return ao.OpencodeArm(p, mode="m64", search=search or FakeSearch())


# ---------------------------------------------------------------- the contract attributes
def test_both_modes_pass_validate_adapter_and_declare_the_spec_tool_removals(probe):
    for arm in (tg1_arm(probe), m64_arm(probe)):
        aa.validate_adapter(arm)
        assert arm.arm_id == "oc" and arm.tool == "opencode"
        assert arm.native_client_cuts == ("client_inactivity",)                      # C154
        assert set(arm.removed_tools) == {"subagent", "execute", "question", "websearch"}   # D1 + D2 (C165 2c, 2d)
    assert tg1_arm(probe).label == TG1_LABEL
    assert m64_arm(probe).label == "opencode-v2-web-tg1c"


def test_declared_removals_are_denied_in_the_carrier_of_both_modes(probe):
    for arm in (tg1_arm(probe), m64_arm(probe)):
        doc = json.loads(arm.selection()["bytes"])
        denied = {p["action"] for p in doc["permissions"] if p["effect"] == "deny" and p["resource"] == "*"}
        assert set(arm.removed_tools) <= denied


def test_the_m64_mode_is_registered_as_the_oc_arm(probe):
    reg = aa.ArmRegistry()
    reg.register(ao.OpencodeArm)
    assert reg.registered() == ("oc",)


# ---------------------------------------------------------------- carrier: tg1 parity and the M64 diff
def test_tg1_mode_selection_is_exactly_the_tg1_path_selection(probe):
    mine = tg1_arm(probe).selection()
    theirs = probe._carrier_selection(TG1_LABEL, None, source=tg1_runner.CARRIER)
    assert mine["bytes"] == theirs["bytes"] == tg1_runner.CARRIER.read_bytes()
    assert mine["fields"] == theirs["fields"] and mine["source"] == theirs["source"]


def test_tg1_mode_selection_with_a_system_overlay_is_the_tg1_path_selection(probe):
    system = sorted((REPO / "benchmark/opencode_prompts").glob("*"))
    system = next((f for f in system if f.is_file()), None)
    if system is None:
        pytest.skip("no recorded system prompt file")
    rel = system.relative_to(REPO).as_posix()
    mine = tg1_arm(probe).selection(rel)
    theirs = probe._carrier_selection(TG1_LABEL, rel, source=tg1_runner.CARRIER)
    assert mine["bytes"] == theirs["bytes"] and mine["fields"] == theirs["fields"]


def walk(doc, path=()):
    """Every leaf (and every empty container) of a JSON document as {path: value}."""
    if isinstance(doc, dict) and doc:
        for k, v in doc.items():
            yield from walk(v, path + (k,))
    elif isinstance(doc, list) and doc:
        for i, v in enumerate(doc):
            yield from walk(v, path + (i,))
    else:
        yield path, doc


def diff(a, b):
    ma, mb = dict(walk(a)), dict(walk(b))
    return sorted((p for p in set(ma) | set(mb) if ma.get(p, "<absent>") != mb.get(p, "<absent>")), key=str)


def test_the_m64_carrier_differs_from_tg1_only_by_the_enumerated_changes(probe):
    base = json.loads(tg1_runner.CARRIER.read_text())
    new = json.loads(m64_arm(probe).selection()["bytes"])
    changed = diff(base, new)
    assert changed == [("compaction", "auto"), ("mcp", "searxng", "command", 0), ("mcp", "searxng", "command", 1),
                       ("mcp", "searxng", "enabled"), ("mcp", "searxng", "type")]
    assert base["compaction"] == {"auto": False} and new["compaction"] == {"auto": True}
    assert new["mcp"] == {"searxng": SEARCH_ENTRY}
    assert ao.M64_CARRIER_CHANGES == (("compaction.auto", False, True), ("mcp.searxng", None, "shared search service"))


def test_the_m64_carrier_keeps_every_tg1_control_that_the_spec_keeps(probe):
    doc = json.loads(m64_arm(probe).selection()["bytes"])
    perms = doc["permissions"]
    deny = lambda a: dict(action=a, resource="*", effect="deny") in perms          # noqa: E731
    assert all(deny(a) for a in ("subagent", "execute", "question", "websearch", "external_directory"))   # D1, 2c, D2
    assert dict(action="webfetch", resource="*", effect="allow") in perms           # fetch stays enabled (C165 2)
    assert dict(action="webfetch", resource="*xercism*", effect="deny") in perms    # the deny patterns stay
    assert doc["agents"]["title"] == {"disabled": True}
    assert doc["plugins"] == json.loads(tg1_runner.CARRIER.read_text())["plugins"]
    for name in (tg1 for tg1 in ("Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "Qwen3.8-27B-mlx-uniform-4bit")):
        m = doc["providers"]["mlx-local"]["models"][name]
        assert m["limit"]["context"] == 262144                                      # exposed context (C165 2b)
        assert m["body"]["thinking_budget"] == 81920 and m["body"]["max_tokens"] == 102400


def test_the_m64_selection_records_its_derivation_and_a_distinct_config_sha(probe):
    tg1 = tg1_arm(probe).selection()
    m64 = m64_arm(probe).selection()
    f = m64["fields"]
    assert f["scaffold"] == "opencode-v2-web-tg1c"
    assert f["carrier_source"] == "benchmark/opencode_bench_v2_web_tg1.json"
    assert f["carrier_source_sha256"] == tg1["fields"]["carrier_source_sha256"]       # what it derives from
    assert f["opencode_bench_config_sha256"] == hashlib.sha256(m64["bytes"]).hexdigest() != tg1["fields"][
        "opencode_bench_config_sha256"]
    assert f["carrier_transform"] == "opencode-v2-web-tg1c"
    assert json.loads(f["carrier_changes"]) == [list(c) for c in ao.M64_CARRIER_CHANGES]


def test_the_m64_mode_refuses_before_anything_without_the_search_service(probe):
    arm = ao.OpencodeArm(probe, mode="m64")                       # default service: the D2 stub
    with pytest.raises(aa.ArmRefused, match="shared search service"):
        arm.selection()


def test_a_service_that_declares_no_entry_is_refused_by_name(probe):
    arm = m64_arm(probe, search=FakeSearch(entry=None))
    with pytest.raises(aa.ArmRefused, match="client-native MCP entry"):
        arm.selection()


def test_the_offline_test_service_makes_a_carrier_without_mcp_and_is_named_for_tests(probe):
    arm = ao.OpencodeArm(probe, mode="m64", search=ao.OfflineTestSearchService())
    doc = json.loads(arm.selection()["bytes"])
    assert "mcp" not in doc and doc["compaction"] == {"auto": True}
    assert arm.search_is_offline_test is True


def test_tg1_mode_never_touches_the_search_service(probe):
    class Boom(aa.SearchService):
        available = False

        def require(self):
            raise AssertionError("tg1 mode must not use the search service")

        def mcp_entry(self, client):
            raise AssertionError("tg1 mode must not use the search service")

    assert ao.OpencodeArm(probe, mode="tg1", search=Boom()).selection()["bytes"] == tg1_runner.CARRIER.read_bytes()


# ---------------------------------------------------------------- run dir, plugin set, env
def tree(root):
    root = Path(root)
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def tg1_run_dir(p, workdir, run_id, selection):
    """What tg1_runner._main does, step for step."""
    run_dir = p._make_run_dir(workdir, run_id, selection)
    shutil.copyfile(tg1_runner.PLUGIN, run_dir / "cfg/opencode/plugins/toolbounds.js")
    shutil.copyfile(tg1_runner.DATEFREEZE_PLUGIN, run_dir / "cfg/opencode/plugins/datefreeze.js")
    return run_dir


def test_tg1_mode_run_dir_and_plugin_set_equal_the_tg1_path(probe, tmp_path):
    arm = tg1_arm(probe)
    sel = arm.selection()
    mine = arm.make_run_dir(tmp_path / "a", "r1", sel)
    theirs = tg1_run_dir(probe, tmp_path / "b", "r1", probe._carrier_selection(TG1_LABEL, None, source=tg1_runner.CARRIER))
    assert tree(mine / "cfg/opencode") == tree(theirs / "cfg/opencode")
    assert sorted(tree(mine / "cfg/opencode")) == ["opencode.json", "plugins/datefreeze.js", "plugins/noretry.js",
                                                   "plugins/toolbounds.js"]


def test_m64_mode_loads_the_tg1_plugin_set_plus_toolwindows(probe, tmp_path):
    arm = m64_arm(probe)
    run = arm.make_run_dir(tmp_path, "r1", arm.selection())
    names = sorted(k for k in tree(run / "cfg/opencode") if k.startswith("plugins/"))
    assert names == ["plugins/datefreeze.js", "plugins/noretry.js", "plugins/toolbounds.js", "plugins/toolwindows.js"]
    assert (run / "cfg/opencode/opencode.json").read_bytes() == arm.selection()["bytes"]


def test_env_equals_the_tg1_env_for_the_same_inputs(probe, tmp_path):
    arm = tg1_arm(probe)
    run = arm.make_run_dir(tmp_path, "r1", arm.selection())
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    overlay = probe._seed_overlay(MODEL, 7)
    mine = arm.build_env(run, scratch, overlay, receipts=tmp_path / "r.jsonl", frozen_date=FROZEN)
    theirs = probe._opencode_env(run, scratch, overlay, frozen_date=FROZEN, receipts=tmp_path / "r.jsonl")
    assert mine == theirs
    assert mine["BENCH_FROZEN_PROMPT_DATE"] == FROZEN


def test_verify_env_accepts_the_built_env_and_refuses_a_tampered_one(probe, tmp_path):
    for arm in (tg1_arm(probe), m64_arm(probe)):
        sel = arm.selection()
        run = arm.make_run_dir(tmp_path / arm.arm_id / arm.label, "r1", sel)
        scratch = tmp_path / ("s-" + arm.label)
        scratch.mkdir()
        overlay = probe._seed_overlay(MODEL, 7)
        env = arm.build_env(run, scratch, overlay, receipts=tmp_path / "x" / "r.jsonl", frozen_date=FROZEN,
                            toolwindow_receipts=tmp_path / "x" / "t.jsonl" if arm.m64 else None,
                            attempt=wr.AttemptContext.make("python/one", 1))
        arm.verify_env(env, run, sel, overlay)
        (run / "cfg/opencode/plugins/extra.js").write_text("export default {}")
        with pytest.raises(Exception, match="unexpected entries"):
            arm.verify_env(env, run, sel, overlay)
        (run / "cfg/opencode/plugins/extra.js").unlink()
        with pytest.raises(Exception, match="overlay"):
            arm.verify_env(env, run, sel, probe._seed_overlay(MODEL, 8))
        (run / "cfg/opencode/plugins/toolbounds.js").write_text("// edited")
        with pytest.raises(Exception, match="sha256 differs"):
            arm.verify_env(env, run, sel, overlay)


def test_command_equals_the_tg1_spawn(probe):
    assert tg1_arm(probe).command("/bin/oc", MODEL, "do it") == [
        "/bin/oc", "run", "--standalone", "--model", "mlx-local/" + MODEL, "--format", "json", "--title", "probe", "do it"]


def test_evidence_suffixes_and_guard_roots_equal_tg1(probe, tmp_path):
    arm = tg1_arm(probe)
    assert arm.evidence_suffixes() == {"events": ".events.jsonl", "stderr": ".stderr.txt", "export": ".json",
                                       "datefreeze": ".datefreeze.jsonl"}
    assert arm.guard_roots(Path("/w"), {"TMPDIR": "/t/"}, Path("/p")) == [Path("/w"), "/t/", Path("/p")]


# ---------------------------------------------------------------- identity
def fake_binary(tmp_path):
    b = tmp_path / "opencode"
    b.write_text("#!/bin/sh\n")
    b.chmod(0o755)
    return b


def test_tg1_mode_identity_equals_tg1_runner_identity(probe, tmp_path, monkeypatch):
    monkeypatch.setattr(toolchain, "current", lambda: {"lock_sha256": "l", "interpreter": "i",
                                                                  "grader_image_id": "g"})
    arm = tg1_arm(probe)
    sel = arm.selection()
    binary = fake_binary(tmp_path)
    mine = arm.identity(selection=sel, universe_sha="u" * 64, version="2.0.20", binary=binary, inject=None)
    theirs = tg1_runner.identity(probe, sel, "u" * 64, "2.0.20", binary)
    assert mine == theirs
    assert arm.identity(selection=sel, universe_sha="u" * 64, version="2.0.20", binary=binary,
                        inject="stall", inject_addendum_sha256=tg1_runner.inject_addendum_sha256("stall")
                        ) == tg1_runner.identity(probe, sel, "u" * 64, "2.0.20", binary, inject="stall")


def test_m64_identity_has_its_own_label_policy_and_generation_data(probe, tmp_path, monkeypatch):
    monkeypatch.setattr(toolchain, "current", lambda: {"lock_sha256": "l", "interpreter": "i",
                                                                  "grader_image_id": "g"})
    binary = fake_binary(tmp_path)
    t, m = tg1_arm(probe), m64_arm(probe)
    it = t.identity(selection=t.selection(), universe_sha="u" * 64, version="2.0.20", binary=binary, inject=None)
    im = m.identity(selection=m.selection(), universe_sha="u" * 64, version="2.0.20", binary=binary, inject=None)
    assert im["scaffold"] == "opencode-v2-web-tg1c" and it["scaffold"] == TG1_LABEL
    assert im["scaffold_policy_sha256"] != it["scaffold_policy_sha256"]
    assert im["policy"]["carrier_sha256"] == m.selection()["fields"]["opencode_bench_config_sha256"]
    assert im["policy"]["gate"] == it["policy"]["gate"] and im["policy"]["hygiene"] == it["policy"]["hygiene"]
    assert m.generation_data == (tg1_runner.GENERATION_DATA)
    assert "benchmark/opencode_bench_v2_web_tg1.json" in m.generation_data     # the base the carrier derives from


def test_generation_fields_are_the_tg1_composite_plus_the_arm(probe):
    assert ao.OpencodeArm.GENERATION_FIELDS == tg1_runner.GENERATION_FIELDS
    sha = aa.arm_generation_sha256("oc", {k: k for k in tg1_runner.GENERATION_FIELDS}, ao.OpencodeArm.GENERATION_FIELDS)
    assert sha != tg1_runner.generation_identity_sha256({k: k for k in tg1_runner.GENERATION_FIELDS})


# ---------------------------------------------------------------- stream: gate state equals tg1's, events normalized
def tg1_events():
    return [
        event("step_start"),
        dict(type="tool_use", sessionID="s1", part=dict(
            partID="p-t1", id="t1", messageID="m1", type="tool", tool="shell", state=dict(
                status="completed", input={"command": "ls"}, output="x", title="shell", metadata={},
                time=dict(start=1_000, end=3_500)))),
        event("step_finish", tokens=usage(10, 100, 5, 2)),
        event("step_start", "m2"),
        event("step_finish", "m2", tokens=usage(7, 200)),
    ]


def feed(stream, evs):
    stream.feed("".join(json.dumps(e) + "\n" for e in evs).encode())


def test_the_stream_drives_the_gate_exactly_like_the_tg1_stream(probe):
    g1, g2 = tg.TokenTurnGate(3), tg.TokenTurnGate(3)
    ref = tg.EventStream(g1, lambda n: None)
    mine = tg1_arm(probe).new_stream(g2, lambda n: None)
    feed(ref, tg1_events())
    feed(mine, tg1_events())
    assert g1.request_usage == g2.request_usage and g1.report() == g2.report()
    assert ref.tool_events == mine.tool_events and ref.starts == mine.starts and ref.session_id == mine.session_id
    assert ref.event_types_seen == mine.event_types_seen


def test_the_stream_normalizes_events_in_order(probe):
    arm = tg1_arm(probe)
    stream = arm.new_stream(tg.TokenTurnGate(3), lambda n: None)
    feed(stream, tg1_events())
    ev = arm.events(stream)
    assert [(e.kind, e.request_seq) for e in ev] == [
        ("request_start", 1), ("tool", 1), ("request_finish", 1), ("request_start", 2), ("request_finish", 2)]
    assert ev[1].tool == dict(name="shell", inputs={"command": "ls"}, status="completed", start=1.0, end=3.5)
    assert ev[2].usage == aa.Usage(input=100, cache_read=5, cache_write=2, output=10, reasoning=0)
    assert arm.tool_windows(stream) == [(1.0, 3.5, "shell")]


def test_a_malformed_event_aborts_exactly_like_tg1(probe):
    arm = tg1_arm(probe)
    stream = arm.new_stream(tg.TokenTurnGate(3), lambda n: None)
    with pytest.raises(tg.TransportAbort, match="second step_start"):
        feed(stream, [event("step_start"), event("step_start", "m2")])


# ---------------------------------------------------------------- reconcile: tg1 parity, compaction, receipts
def finished_export(*messages):
    return {"info": {"id": "s1"}, "messages": list(messages)}


def assistant(mid, out=10, inp=100, finish="stop", **kw):
    return dict(id=mid, type="assistant", finish=finish, tokens=dict(input=inp, output=out, reasoning=0,
                                                                    cache=dict(read=0, write=0)), content=[], **kw)


def compaction_message(inp=300, out=40, reason="auto", **kw):
    return dict(type="compaction", id="c1", status="completed", reason=reason, summary="s", recent="",
                tokens=dict(input=inp, output=out, reasoning=0, cache=dict(read=0, write=0)), **kw)


def one_request_stream(arm):
    gate = tg.TokenTurnGate(3)
    stream = arm.new_stream(gate, lambda n: None)
    feed(stream, [event("step_start"), event("step_finish", tokens=usage(10, 100))])
    return gate, stream


def test_reconcile_in_tg1_mode_equals_tg1_reconcile(probe):
    arm = tg1_arm(probe)
    gate, stream = one_request_stream(arm)
    ref_gate = tg.TokenTurnGate(3)
    ref = tg.EventStream(ref_gate, lambda n: None)
    feed(ref, [event("step_start"), event("step_finish", tokens=usage(10, 100))])
    export = finished_export(assistant("m1"))
    want = tg.reconcile(ref, export, 0, None)
    got = arm.reconcile(stream, ao.Transcript(raw=json.dumps(export), doc=export), None, 0, None)
    assert (got.unmatched_export_messages, got.trailing, got.uncharged_trailing) == (
        want["unmatched_export_messages"], want["trailing"], want["uncharged_trailing"])
    assert got.row_reconciliation() == dict(unmatched_export_messages=0, trailing="none")
    assert gate.report() == ref_gate.report() and got.compaction == []


def test_reconcile_in_tg1_mode_ignores_compaction_exactly_as_tg1_does(probe):
    """tg1 runs compaction off: a compaction message in an export is not accounted (it cannot occur)."""
    arm = tg1_arm(probe)
    _, stream = one_request_stream(arm)
    export = finished_export(compaction_message(), assistant("m1"))
    got = arm.reconcile(stream, ao.Transcript(raw="", doc=export), None, 0, None)
    assert got.compaction == []


def test_reconcile_in_m64_mode_accounts_every_compaction_request(probe):
    arm = m64_arm(probe)
    _, stream = one_request_stream(arm)
    export = finished_export(assistant("m1", inp=100), compaction_message(inp=300, out=40))
    got = arm.reconcile(stream, ao.Transcript(raw="", doc=export), None, 0, None)
    assert got.compaction_count == 1 and got.compaction_completion_tokens == 40
    assert got.compaction[0]["reason"] == "auto"
    assert got.compaction[0]["usage"] == aa.Usage(300, 0, 0, 40, 0).as_dict()
    ev = arm.events(stream)
    comp = [e for e in ev if e.kind == "compaction"]
    assert len(comp) == 1 and comp[0].compaction["usage"]["output"] == 40
    assert ev[-1].kind == "terminal" and ev[-1].terminal == "stop"


def test_a_compaction_message_without_usage_is_not_evaluable_and_aborts(probe):
    arm = m64_arm(probe)
    _, stream = one_request_stream(arm)
    bad = compaction_message()
    bad["tokens"] = None
    export = finished_export(assistant("m1"), bad)
    with pytest.raises(tg.TransportAbort, match="compaction usage"):
        arm.reconcile(stream, ao.Transcript(raw="", doc=export), None, 0, None)


def write_receipts(path, rows):
    path.write_text("".join(json.dumps(dict(sessionID="s1", seq=seq, kind=kind, frozen=FROZEN, n_initial_replaced=1,
                                            n_update_removed=0, system_sha256="a" * 64)) + "\n" for kind, seq in rows))


def test_receipts_accept_compaction_requests_only_in_m64_mode(probe, tmp_path):
    path = tmp_path / "r.jsonl"
    write_receipts(path, [("primary", 1), ("compaction", 1)])
    m = m64_arm(probe)
    got = m.receipts_reconcile(path, frozen=FROZEN, session_id="s1", requests_observed=1, killed=False)
    assert got["requests"] == 1 and got["receipts"] == 2 and got["compaction_receipts"] == 1
    with pytest.raises(tg.TransportAbort, match="unexpected request kind"):
        tg1_arm(probe).receipts_reconcile(path, frozen=FROZEN, session_id="s1", requests_observed=1, killed=False)


def test_unaccounted_compaction_requests_are_recorded_not_hidden(probe, tmp_path):
    """Two compaction requests (a template retry) but one compaction message: the first request's usage is not in
    the export, so the accounting is flagged incomplete (never silently complete)."""
    arm = m64_arm(probe)
    _, stream = one_request_stream(arm)
    path = tmp_path / "r.jsonl"
    write_receipts(path, [("primary", 1), ("compaction", 1), ("compaction", 2)])
    export = finished_export(assistant("m1"), compaction_message())
    got = arm.reconcile(stream, ao.Transcript(raw="", doc=export), dict(path=path, frozen=FROZEN, session_id="s1",
                                                                       killed=False), 0, None)
    assert got.extra["compaction_accounting_complete"] is False
    assert got.extra["compaction_receipts"] == 2 and got.compaction_count == 1


def test_native_inactivity_cut_is_still_the_registered_shape(probe):
    arm = m64_arm(probe)
    gate = tg.TokenTurnGate(3)
    stream = arm.new_stream(gate, lambda n: None)
    feed(stream, [event("step_start"), event("step_finish", tokens=usage(10, 100)), event("step_start", "m2"),
                  dict(type="error", sessionID="s1", error=dict(type="aborted", message="Session interrupted: inactivity"))])
    export = finished_export(assistant("m1", finish="tool-calls"), dict(
        id="m2", type="assistant", finish="error", tokens=None, error=dict(type="aborted", message="Step interrupted"),
        content=[], time=dict(created=1_000, streamed=3_634_000, completed=3_634_070)))
    got = arm.reconcile(stream, ao.Transcript(raw="", doc=export), None, 1, None)
    assert got.outcome == "client_inactivity" and got.trailing == "interrupted"
    assert got.uncharged_trailing == dict(reasoning_chars=0, text_chars=0, streamed_s=3633.0)
    assert arm.events(stream)[-1].terminal == "client_cut"


# ---------------------------------------------------------------- transport classification (spec 8.3)
@pytest.mark.parametrize("error,cause", [
    (dict(type="provider.internal", status=500, message="mock internal error"), "server_error"),
    (dict(type="provider.transport", message="Unable to connect"), "connection"),
    (dict(type="provider.invalid-output", message="broken"), "dropped_stream"),
])
def test_transport_shaped_errors_are_classified_with_a_cause(probe, error, cause):
    arm = m64_arm(probe)
    gate = tg.TokenTurnGate(3)
    stream = arm.new_stream(gate, lambda n: None)
    feed(stream, [event("step_start"), dict(type="error", sessionID="s1", error=error)])
    with pytest.raises(ao.TransportFailure) as exc:
        arm.reconcile(stream, ao.Transcript(raw="", doc=finished_export(assistant("m1"))), None, 1, None)
    assert exc.value.cause == cause and isinstance(exc.value, tg.TransportAbort)


def test_an_unclassifiable_error_stays_a_plain_abort(probe):
    arm = m64_arm(probe)
    stream = arm.new_stream(tg.TokenTurnGate(3), lambda n: None)
    feed(stream, [event("step_start"), dict(type="error", sessionID="s1", error=dict(
        type="compaction.failed", message="Compaction summary did not match the required template"))])
    with pytest.raises(tg.TransportAbort) as exc:
        arm.reconcile(stream, ao.Transcript(raw="", doc=finished_export(assistant("m1"))), None, 1, None)
    assert not isinstance(exc.value, ao.TransportFailure)


# ---------------------------------------------------------------- snapshot / manifest / rows
def test_snapshot_states_what_is_known_and_what_the_snapshot_tooling_still_owes(probe, tmp_path, monkeypatch):
    binary = fake_binary(tmp_path)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(binary))
    arm = m64_arm(probe)
    snap = arm.snapshot()
    assert snap.tool == "opencode" and snap.complete is False
    assert set(snap.missing) == {"dependency_tree", "bottle_sha256", "tool_schemas"}
    f = snap.fields
    assert f["version"] == "2.0.20" and f["exe_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
    assert f["plugins"] == {n: hashlib.sha256((REPO / "benchmark/opencode_plugins" / n).read_bytes()).hexdigest()
                            for n in ("datefreeze.js", "noretry.js", "toolbounds.js", "toolwindows.js")}
    assert f["carrier_sha256"] == arm.selection()["fields"]["opencode_bench_config_sha256"]
    assert f["label"] == "opencode-v2-web-tg1c"


def test_manifest_fields_name_the_arm_and_its_snapshot(probe):
    arm = m64_arm(probe)
    mf = arm.manifest_fields()
    assert mf["arm"] == "oc" and mf["tool"] == "opencode" and mf["label"] == "opencode-v2-web-tg1c"
    assert mf["search_service"] == "shared-searxng-mcp"
    assert tg1_arm(probe).manifest_fields()["search_service"] is None
