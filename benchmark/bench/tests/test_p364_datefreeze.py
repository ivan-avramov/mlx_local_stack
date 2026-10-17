"""P364: freeze the date opencode shows the model (spec docs/specs/p364-datefreeze.md v2).

Layers: the plugin on recorded hook payloads (node), the Python receipt reconciliation, env/identity wiring, and the
REAL pinned binary against the mock model server (wire bytes, every request receipted, compaction and title requests,
a faked midnight update, format drift, second item)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bench import datefreeze as df
from bench import opencode_v2_core as core
from bench import provenance
from bench import tg1_runner as runner
from bench.token_turn_gate import TransportAbort
from bench.tests.opencode_v2_mock import MockServer
from bench.tests.test_opencode_v2_probe import INSTALLED_BIN, MODEL, tg1_probe as probe  # noqa: F401

REPO = Path(__file__).resolve().parents[3]
PLUGIN = REPO / "benchmark/opencode_plugins/datefreeze.js"
FROZEN = "Mon Jan 05 2026"
REAL = "Sat Oct 17 2026"
NODE = shutil.which("node", path="/opt/homebrew/bin:/usr/local/bin:/usr/bin")


# ------------------------------------------------------------------ the plugin on recorded payloads (node)
HARNESS = """
import fs from "node:fs"
import plugin from "./plugin.mjs"
const hooks = {}
let setupError = null
try { plugin.setup({ session: { hook: (name, fn) => { hooks[name] = fn } } }) } catch (e) { setupError = e.message }
const [name, file] = process.argv.slice(2)
if (setupError) { console.log(JSON.stringify({ setupError })); process.exit(0) }
const payload = JSON.parse(fs.readFileSync(file, "utf8"))
const out = { hooks: Object.keys(hooks).sort() }
try { hooks[name](payload); out.ok = true } catch (e) { out.ok = false; out.error = e.message }
out.payload = payload
console.log(JSON.stringify(out))
"""


def system_entries(date=REAL):
    return [
        {"type": "text", "text": "You are an AI agent running in OpenCode."},
        {"type": "text", "text": "Skills\n</available_skills>\n\nToday's date: " + date + "\n\nHere is some useful information"},
        {"type": "text", "text": "When you create a worktree, move the session."},
    ]


def payload(**kw):
    base = dict(sessionID="ses_a", model={"id": "m"}, system=system_entries(),
                messages=[{"id": "msg_1", "role": "user", "content": [{"type": "text", "text": "do it"}], "metadata": {}}],
                options={}, agent="build", tools={})
    base.update(kw)
    return base


@pytest.fixture
def node(tmp_path):
    if not NODE:
        pytest.skip("node not installed")
    (tmp_path / "plugin.mjs").write_bytes(PLUGIN.read_bytes())
    (tmp_path / "harness.mjs").write_text(HARNESS)
    receipts = tmp_path / "receipts.jsonl"

    def run(hook, doc, *, env=None, frozen=FROZEN):
        (tmp_path / "payload.json").write_text(json.dumps(doc))
        full = {"PATH": os.environ["PATH"], "BENCH_DATEFREEZE_RECEIPTS": str(receipts)}
        if frozen is not None:
            full["BENCH_FROZEN_PROMPT_DATE"] = frozen
        full.update(env or {})
        got = subprocess.run([NODE, "harness.mjs", hook, "payload.json"], cwd=tmp_path, env=full,
                             capture_output=True, text=True, timeout=30)
        assert got.returncode == 0, got.stderr
        result = json.loads(got.stdout)
        result["receipts"] = ([json.loads(line) for line in receipts.read_text().splitlines()]
                              if receipts.exists() else [])
        return result

    return run


def test_plugin_registers_exactly_the_structured_hooks(node):
    assert node("context", payload())["hooks"] == ["compaction", "context", "generate", "title"]


def test_exact_replacement_and_nothing_else_touched(node):
    doc = payload()
    got = node("context", doc)
    assert got["ok"] is True
    expected = payload(system=system_entries(FROZEN))
    assert got["payload"] == expected
    (r,) = got["receipts"]
    assert (r["sessionID"], r["seq"], r["kind"], r["frozen"]) == ("ses_a", 1, "primary", FROZEN)
    assert (r["n_initial_replaced"], r["n_update_removed"]) == (1, 0)
    texts = "\n".join(s["text"] for s in expected["system"])
    assert r["system_sha256"] == hashlib.sha256(texts.encode()).hexdigest()


def test_update_message_is_removed_entirely(node):
    update = {"role": "system", "content": [{"type": "text", "text": "Today's date is now: Sun Oct 18 2026"}]}
    doc = payload(messages=[payload()["messages"][0], update])
    got = node("context", doc)
    assert got["ok"] is True and got["payload"]["messages"] == payload()["messages"]
    assert got["receipts"][0]["n_update_removed"] == 1


def test_update_line_removed_other_instruction_updates_kept(node):
    text = "Previously loaded instructions no longer apply.\nToday's date is now: Sun Oct 18 2026"
    update = {"role": "system", "content": [{"type": "text", "text": text}]}
    got = node("context", payload(messages=[payload()["messages"][0], update]))
    assert got["payload"]["messages"][1]["content"][0]["text"] == "Previously loaded instructions no longer apply."
    assert got["receipts"][0]["n_update_removed"] == 1


def test_update_as_plain_string_content_is_removed(node):
    update = {"role": "system", "content": "Today's date is now: Sun Oct 18 2026"}
    got = node("context", payload(messages=[update, payload()["messages"][0]]))
    assert got["payload"]["messages"] == payload()["messages"]


def test_only_system_role_update_messages_of_the_exact_shape_are_removed(node):
    """F2: user / synthetic text that merely resembles the update stays; so does a non-date-shaped system line."""
    exact = "Today's date is now: Sun Oct 18 2026"
    messages = payload()["messages"] + [
        {"role": "user", "content": [{"type": "text", "text": exact}]},
        {"role": "user", "content": exact},
        {"role": "system", "content": [{"type": "text", "text": "Today's date is now: whenever"}]},
    ]
    got = node("context", payload(messages=messages))
    assert got["ok"] is True and got["payload"]["messages"] == messages
    assert got["receipts"][0]["n_update_removed"] == 0


def test_an_unrelated_empty_message_is_never_deleted(node):
    update = {"role": "system", "content": [{"type": "text", "text": "Today's date is now: Sun Oct 18 2026"}]}
    empty_user = {"role": "user", "content": []}
    empty_system = {"role": "system", "content": [{"type": "text", "text": ""}]}
    got = node("context", payload(messages=[empty_user, update, empty_system]))
    assert got["payload"]["messages"] == [empty_user, empty_system]
    assert got["receipts"][0]["n_update_removed"] == 1


def test_model_authored_text_is_never_edited(node):
    echoed = "Today's date is now: Sun Oct 18 2026"
    messages = payload()["messages"] + [
        {"role": "assistant", "content": [{"type": "text", "text": echoed}]},
        {"role": "tool", "content": [{"type": "tool-result", "result": {"type": "text", "value": echoed}}]}]
    got = node("context", payload(messages=messages))
    assert got["ok"] is True and got["payload"]["messages"] == messages
    assert got["receipts"][0]["n_update_removed"] == 0


@pytest.mark.parametrize("shown", ["2026-10-17", "Saturday, October 17, 2026", "Sat Oct 17 26", "", "Sat Oct 7 2026"])
def test_format_drift_refuses_and_leaves_an_error_receipt(node, shown):
    got = node("context", payload(system=system_entries(shown)))
    assert got["ok"] is False and "P364_DATEFREEZE" in got["error"]
    assert got["receipts"][0]["error"] and "n_initial_replaced" not in got["receipts"][0]


def test_no_date_instruction_refuses_for_every_non_title_kind(node):
    bare = payload(system=[{"type": "text", "text": "no date here"}])
    for hook in ("context", "compaction", "generate"):
        got = node(hook, bare)
        assert got["ok"] is False and "no date instruction" in got["error"], hook


def test_title_request_without_a_date_is_fine_and_receipted_with_zero(node):
    got = node("title", payload(system=[{"type": "text", "text": "You are a title generator."}]))
    assert got["ok"] is True and got["receipts"][0]["kind"] == "title" and got["receipts"][0]["n_initial_replaced"] == 0


@pytest.mark.parametrize("hook,kind", [("compaction", "compaction"), ("generate", "generate")])
def test_other_hooks_mask_and_receipt_their_kind(node, hook, kind):
    got = node(hook, payload())
    assert got["ok"] is True and got["receipts"][0]["kind"] == kind and FROZEN in got["payload"]["system"][1]["text"]


@pytest.mark.parametrize("frozen", [None, "", "2026-01-05", "Mon Jan 5 2026", "Mon January 05 2026"])
def test_env_unset_or_malformed_fails_at_setup(node, frozen):
    got = node("context", payload(), frozen=frozen)
    assert "setupError" in got and "BENCH_FROZEN_PROMPT_DATE" in got["setupError"]


def test_receipts_path_must_be_set_and_absolute(node):
    got = node("context", payload(), env={"BENCH_DATEFREEZE_RECEIPTS": "relative.jsonl"})
    assert "BENCH_DATEFREEZE_RECEIPTS" in got["setupError"]


def test_unwritable_receipts_abort_the_request(node, tmp_path):
    got = node("context", payload(), env={"BENCH_DATEFREEZE_RECEIPTS": str(tmp_path / "no/such/dir/r.jsonl")})
    assert got["ok"] is False


# ------------------------------------------------------------------ Python side: shape, receipts, reconciliation
def line(**kw):
    base = dict(sessionID="ses_a", seq=1, kind="primary", frozen=FROZEN, n_initial_replaced=1, n_update_removed=0,
                system_sha256="a" * 64)
    base.update(kw)
    return json.dumps(base) + "\n"


def write(path, *lines):
    path.write_text("".join(lines))
    return path


@pytest.mark.parametrize("date,ok", [(FROZEN, True), ("Sat Oct 17 2026", True), ("Sat Oct 7 2026", False),
                                     ("2026-10-17", False), ("", False), (None, False), ("Mon Jan 05 2026 ", False)])
def test_date_shape(date, ok):
    assert df.valid(date) is ok


def test_python_strftime_matches_the_shape():
    assert df.valid(core._prompt_date())


def test_reconcile_exact_match(tmp_path):
    path = write(tmp_path / "r", line(seq=1), line(seq=2, n_update_removed=1), line(seq=3))
    got = df.reconcile(path, frozen=FROZEN, session_id="ses_a", requests_observed=3)
    assert got["requests"] == 3 and got["update_removed"] is True


@pytest.mark.parametrize("name,lines,observed", [
    ("fewer receipts", [line(seq=1)], 2),
    ("more receipts", [line(seq=1), line(seq=2)], 1),
    ("seq gap", [line(seq=1), line(seq=3)], 2),
    ("duplicate seq", [line(seq=1), line(seq=1)], 2),
    ("stale frozen", [line(frozen="Tue Jan 06 2026")], 1),
    ("error receipt", [json.dumps(dict(sessionID="ses_a", seq=1, kind="primary", frozen=FROZEN, error="x")) + "\n"], 1),
    ("not json", ["{garbage\n"], 1),
    ("not an object", ["[1]\n"], 1),
    ("zero replaced", [line(n_initial_replaced=0)], 1),
    ("bad hash", [line(system_sha256="zz")], 1),
    ("negative removed", [line(n_update_removed=-1)], 1),
    ("other session", [line(sessionID="ses_b")], 1),
    ("unexpected kind", [line(), line(seq=1, kind="title", n_initial_replaced=0)], 1),
    ("missing key", [json.dumps(dict(sessionID="ses_a", seq=1, kind="primary", frozen=FROZEN)) + "\n"], 1),
])
def test_reconcile_refuses(tmp_path, name, lines, observed):
    with pytest.raises(TransportAbort):
        df.reconcile(write(tmp_path / "r", *lines), frozen=FROZEN, session_id="ses_a", requests_observed=observed)


def test_reconcile_missing_file_refuses(tmp_path):
    with pytest.raises(TransportAbort, match="missing"):
        df.reconcile(tmp_path / "gone", frozen=FROZEN, session_id="ses_a", requests_observed=0)


def test_reconcile_no_requests_empty_file_is_fine(tmp_path):
    got = df.reconcile(write(tmp_path / "r"), frozen=FROZEN, session_id=None, requests_observed=0)
    assert got == dict(requests=0, receipts=0, n_update_removed=0, update_removed=False)


def test_reconcile_receipts_without_a_session_refuse(tmp_path):
    with pytest.raises(TransportAbort):
        df.reconcile(write(tmp_path / "r", line()), frozen=FROZEN, session_id=None, requests_observed=0)


def test_killed_item_may_differ_by_the_one_request_in_flight(tmp_path):
    path = write(tmp_path / "r", line(seq=1), line(seq=2))
    got = df.reconcile(path, frozen=FROZEN, session_id="ses_a", requests_observed=1, killed=True)
    assert got["requests"] == 2
    with pytest.raises(TransportAbort):
        df.reconcile(write(tmp_path / "r2", line(seq=1), line(seq=2), line(seq=3)), frozen=FROZEN,
                     session_id="ses_a", requests_observed=1, killed=True)
    one_short = write(tmp_path / "r3", line(seq=1))
    assert df.reconcile(one_short, frozen=FROZEN, session_id="ses_a", requests_observed=2, killed=True)["requests"] == 1
    with pytest.raises(TransportAbort):
        df.reconcile(one_short, frozen=FROZEN, session_id="ses_a", requests_observed=3, killed=True)
    with pytest.raises(TransportAbort):                                     # an unkilled item is exact
        df.reconcile(one_short, frozen=FROZEN, session_id="ses_a", requests_observed=2)


def test_websocket_carrier_is_refused():
    df.refuse_websocket({"providers": {"mlx-local": {"settings": {"baseURL": "http://x"}}}})
    for doc in ({"providers": {"p": {"transport": "websocket"}}}, {"providers": {"p": {"webSocket": "session"}}},
                {"a": [{"settings": {"transport": "WebSocket"}}]}):
        with pytest.raises(TransportAbort, match="WebSocket"):
            df.refuse_websocket(doc)


def test_the_tg1_carrier_selects_no_websocket():
    df.refuse_websocket(json.loads(runner.CARRIER.read_text()))


# ------------------------------------------------------------------ env and the M50 inventory
def test_env_carries_the_frozen_date_and_receipts_only_when_asked(tmp_path, probe):
    run = tmp_path / "run"
    plain = probe._opencode_env(run, tmp_path / "s", probe._seed_overlay(MODEL, 1))
    assert "BENCH_FROZEN_PROMPT_DATE" not in plain and "BENCH_DATEFREEZE_RECEIPTS" not in plain
    receipts = tmp_path / "ev/r.jsonl"
    env = probe._opencode_env(run, tmp_path / "s", probe._seed_overlay(MODEL, 1), frozen_date=FROZEN, receipts=receipts)
    assert env["BENCH_FROZEN_PROMPT_DATE"] == FROZEN and env["BENCH_DATEFREEZE_RECEIPTS"] == str(receipts)
    assert {k: v for k, v in env.items() if not k.startswith("BENCH_")} == plain
    with pytest.raises(ValueError):
        probe._opencode_env(run, tmp_path / "s", probe._seed_overlay(MODEL, 1), frozen_date="2026-01-05", receipts=receipts)


def tg1_fixture_dir(tmp_path, *, datefreeze=True):
    from bench.tests.test_opencode_v2_provenance import fixture_env
    run, env, carrier_sha, plugin_sha, overlay = fixture_env(tmp_path)
    tb = run / "cfg/opencode/plugins/toolbounds.js"
    tb.write_text("toolbounds")
    shas = dict(toolbounds_sha=hashlib.sha256(b"toolbounds").hexdigest())
    if datefreeze:
        (run / "cfg/opencode/plugins/datefreeze.js").write_bytes(PLUGIN.read_bytes())
        shas["datefreeze_sha"] = hashlib.sha256(PLUGIN.read_bytes()).hexdigest()
    ev = tmp_path / "evidence"
    ev.mkdir()
    env = {**env, "BENCH_FROZEN_PROMPT_DATE": FROZEN, "BENCH_DATEFREEZE_RECEIPTS": str(ev / "r.jsonl")}
    return run, env, carrier_sha, plugin_sha, overlay, shas


def test_m50_allows_datefreeze_by_sha_under_tg1_only(tmp_path):
    run, env, carrier, plugin, overlay, shas = tg1_fixture_dir(tmp_path)
    provenance.opencode_v2_env_check(env, run, carrier, plugin, overlay, scaffold="opencode-v2-web-tg1", **shas)
    with pytest.raises(provenance.ServedConfigError):                    # not under any other scaffold
        provenance.opencode_v2_env_check(env, run, carrier, plugin, overlay, scaffold="opencode-v2-web")
    (run / "cfg/opencode/plugins/datefreeze.js").write_text("// changed")
    with pytest.raises(provenance.ServedConfigError, match="datefreeze"):
        provenance.opencode_v2_env_check(env, run, carrier, plugin, overlay, scaffold="opencode-v2-web-tg1", **shas)


def test_m50_tg1_requires_the_datefreeze_plugin_and_env(tmp_path):
    run, env, carrier, plugin, overlay, shas = tg1_fixture_dir(tmp_path)
    kwargs = dict(scaffold="opencode-v2-web-tg1")
    with pytest.raises(provenance.ServedConfigError):                    # no sha given
        provenance.opencode_v2_env_check(env, run, carrier, plugin, overlay, toolbounds_sha=shas["toolbounds_sha"], **kwargs)
    for key in ("BENCH_FROZEN_PROMPT_DATE", "BENCH_DATEFREEZE_RECEIPTS"):
        broken = {k: v for k, v in env.items() if k != key}
        with pytest.raises(provenance.ServedConfigError, match=key):
            provenance.opencode_v2_env_check(broken, run, carrier, plugin, overlay, **shas, **kwargs)
    with pytest.raises(provenance.ServedConfigError, match="BENCH_FROZEN_PROMPT_DATE"):
        provenance.opencode_v2_env_check({**env, "BENCH_FROZEN_PROMPT_DATE": "2026-01-05"}, run, carrier, plugin, overlay,
                                         **shas, **kwargs)


def test_m50_receipts_live_outside_the_config_dir(tmp_path):
    run, env, carrier, plugin, overlay, shas = tg1_fixture_dir(tmp_path)
    inside = {**env, "BENCH_DATEFREEZE_RECEIPTS": str(run / "cfg/opencode/receipts.jsonl")}
    with pytest.raises(provenance.ServedConfigError, match="outside"):
        provenance.opencode_v2_env_check(inside, run, carrier, plugin, overlay, scaffold="opencode-v2-web-tg1", **shas)
    (run / "cfg/opencode/r.jsonl").write_text("")                      # a stray receipt file is an unexpected entry
    with pytest.raises(provenance.ServedConfigError, match="unexpected"):
        provenance.opencode_v2_env_check(env, run, carrier, plugin, overlay, scaffold="opencode-v2-web-tg1", **shas)


# ------------------------------------------------------------------ identity
def selection(p):
    return p._carrier_selection(runner.SCAFFOLD, None, source=runner.CARRIER)


def ident(p, **kw):
    return runner.identity(p, selection(p), "u" * 64, "2.0.20", Path(p.__file__), **kw)


def test_plugin_sha_is_in_the_scaffold_policy_and_generation_data(probe):
    got = ident(probe)
    assert got["policy"]["datefreeze_sha256"] == hashlib.sha256(PLUGIN.read_bytes()).hexdigest()
    assert "benchmark/opencode_plugins/datefreeze.js" in runner.GENERATION_DATA


def test_changing_the_plugin_changes_the_policy_and_the_code_identity(probe, monkeypatch, tmp_path):
    from bench import identity_closure as ic
    base = ident(probe)
    other = tmp_path / "datefreeze.js"
    other.write_text(PLUGIN.read_text() + "\n// changed\n")
    monkeypatch.setattr(runner, "DATEFREEZE_PLUGIN", other)
    assert ident(probe)["scaffold_policy_sha256"] != base["scaffold_policy_sha256"]
    entry = "benchmark/run_tg1_probe.py"
    without = [d for d in runner.GENERATION_DATA if "datefreeze" not in d]
    assert ic.closure_sha256(entry, REPO, data=runner.GENERATION_DATA) != ic.closure_sha256(entry, REPO, data=without)
    assert base["probe_code_sha256"] == ic.closure_sha256(entry, REPO, data=runner.GENERATION_DATA)


def test_the_frozen_date_is_not_in_the_generation_composite():
    assert "frozen_prompt_date" not in runner.GENERATION_FIELDS and "prompt_date" not in runner.GENERATION_FIELDS


# ------------------------------------------------------------------ the real pinned binary against the mock server
@pytest.fixture
def real_bin(tmp_path):
    if not INSTALLED_BIN.is_file():
        pytest.skip("bench opencode 2.0.20 not installed (scripts/install_bench_opencode.sh)")
    return str(INSTALLED_BIN.resolve())


def sorted_names(path):
    return sorted(p.name for p in Path(path).iterdir())


ROOTS = []


def normalised(text, *extra):
    """Run-specific strings (run directory, session id) replaced so two runs compare byte for byte."""
    for root in sorted(set(ROOTS), key=len, reverse=True):
        text = text.replace(root, "ROOT")
    for i, token in enumerate(extra):
        text = text.replace(token, f"TOKEN{i}")
    return text


def run_direct(tmp_path, mock, binary, *, plugins, frozen=FROZEN, carrier=None, title=False, prompt=None, name="run"):
    """One `opencode run` against the mock with exactly the given plugin set; returns (rc, stderr, receipts path)."""
    root = tmp_path / name
    ROOTS.append(str(root))
    for d in ("home", "cfg/opencode/plugins", "data", "state", "cache", "tmp"):
        (root / d).mkdir(parents=True, exist_ok=True)
    for fname, source in plugins.items():
        (root / "cfg/opencode/plugins" / fname).write_text(source)
    doc = json.loads(core.BENCH_OPENCODE_CONFIG.read_text())
    doc["providers"]["mlx-local"]["settings"]["baseURL"] = mock.base
    doc["providers"]["vllm"]["settings"]["baseURL"] = mock.base.replace("/v1", "/vllm-tripwire/v1")
    if carrier:
        carrier(doc)
    (root / "cfg/opencode/opencode.json").write_text(json.dumps(doc))
    scratch = root / "scratch"
    scratch.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=scratch, check=True)
    receipts = tmp_path / (name + ".receipts.jsonl")
    env = core._opencode_env(root, scratch, core._seed_overlay(MODEL, 1))
    os.makedirs(env["TMPDIR"], exist_ok=True)
    if frozen is not None:
        env["BENCH_FROZEN_PROMPT_DATE"] = frozen
    env["BENCH_DATEFREEZE_RECEIPTS"] = str(receipts)
    cmd = [binary, "run", "--standalone", "--model", "mlx-local/" + MODEL, "--format", "json"]
    if not title:
        cmd += ["--title", "probe"]
    cmd += [prompt or "Write solution.py with answer = 42."]
    got = subprocess.run(cmd, cwd=scratch, env=env, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    return got.returncode, got.stderr, receipts


def receipts_of(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines()] if Path(path).exists() else []


def all_text(body):
    return json.dumps(body)


def lower_cased(headers):
    return {k.lower(): v for k, v in headers.items()}


def test_wire_every_request_carries_the_frozen_date_and_is_receipted(real_bin, tmp_path):
    script = {1: dict(name="shell", input={"command": "echo hi"}), 2: dict(name="shell", input={"command": "echo again"})}
    with MockServer(script) as mock:
        rc, err, receipts = run_direct(tmp_path, mock, real_bin, plugins={"datefreeze.js": PLUGIN.read_text()})
        assert rc == 0, err[-500:]
        assert len(mock.chats) == 3
        for chat in mock.chats:
            text = all_text(chat["body"])
            assert "Today's date: " + FROZEN in text and REAL not in text and "Today's date is now" not in text
        got = receipts_of(receipts)
        assert [(r["kind"], r["seq"]) for r in got] == [("primary", 1), ("primary", 2), ("primary", 3)]
        assert len({r["sessionID"] for r in got}) == 1 and all(r["n_initial_replaced"] == 1 for r in got)
        # every receipt hash is the sha of the (masked) system text the server really received
        for chat, r in zip(mock.chats, got):
            system = chat["body"]["messages"][0]["content"]
            parts = [system] if isinstance(system, str) else [p["text"] for p in system]
            assert FROZEN in "".join(parts)
            candidates = {hashlib.sha256(sep.join(parts).encode()).hexdigest() for sep in ("\n", "\n\n", "")}
            assert r["system_sha256"] in candidates, "receipt hash does not match the wire system text"


def test_wire_masking_changes_only_the_date_text_headers_and_cache_keys_unchanged(real_bin, tmp_path):
    plain = {"noop.js": 'export default { id: "bench.noop", setup() {} }'}
    with MockServer() as control, MockServer() as masked:
        rc1, err1, _ = run_direct(tmp_path, control, real_bin, plugins=plain, name="arm-a")
        rc2, err2, _ = run_direct(tmp_path, masked, real_bin, plugins={"datefreeze.js": PLUGIN.read_text()}, name="arm-b")
        assert rc1 == 0 and rc2 == 0, (err1[-300:], err2[-300:])
        assert len(control.chats) == len(masked.chats) == 2
        for a, b in zip(control.chats, masked.chats):
            assert set(lower_cased(a["headers"])) == set(lower_cased(b["headers"]))
            ha, hb = lower_cased(a["headers"]), lower_cased(b["headers"])
            for key in ha:
                if "session" not in key and key not in ("host", "b3", "traceparent"):
                    assert normalised(ha[key]) == normalised(hb[key]), key
            ta = all_text(a["body"]).replace("Today's date: " + REAL, "Today's date: " + FROZEN)
            tb = all_text(b["body"])
            # session ids differ between the two processes; everything else is identical
            sa = lower_cased(a["headers"])["x-session-id"]
            sb = lower_cased(b["headers"])["x-session-id"]
            assert normalised(ta, sa) == normalised(tb, sb)


def test_wire_compaction_and_title_requests_are_masked(real_bin, tmp_path):
    def enable(doc):
        doc["agents"].pop("title", None)
        doc["compaction"] = {"auto": True}
        doc["providers"]["mlx-local"]["models"][MODEL]["limit"] = {"context": 2000, "input": 1500, "output": 300}

    with MockServer() as mock:
        rc, err, receipts = run_direct(tmp_path, mock, real_bin, plugins={"datefreeze.js": PLUGIN.read_text()},
                                       carrier=enable, title=True)
        got = receipts_of(receipts)
        kinds = {r["kind"] for r in got}
        assert {"title", "compaction"} <= kinds, (kinds, err[-300:])
        assert all("error" not in r for r in got)
        for chat in mock.chats:
            text = all_text(chat["body"])
            assert REAL not in text and "Today's date is now" not in text
        assert any("Today's date: " + FROZEN in all_text(c["body"]) for c in mock.chats)
        assert any("title generator" in all_text(c["body"]).lower() for c in mock.chats)


MIDNIGHT = """
const seen = new Map()
export default { id: "bench.midnight", setup(ctx) {
  ctx.session.hook("context", (event) => {
    const n = (seen.get(event.sessionID) ?? 0) + 1
    seen.set(event.sessionID, n)
    if (n >= 2) event.messages.push({ role: "system", content: [{ type: "text", text: "Today's date is now: Sun Oct 18 2026" }] })
  })
} }
"""


def test_wire_faked_midnight_crossing_sends_the_same_prompt(real_bin, tmp_path):
    script = {1: dict(name="shell", input={"command": "echo hi"})}
    with MockServer(script) as clean, MockServer(script) as crossed:
        plugin = PLUGIN.read_text()
        rc1, e1, r1 = run_direct(tmp_path, clean, real_bin, plugins={"datefreeze.js": plugin}, name="clean")
        # the injector must run BEFORE datefreeze (plugins load in file-name order)
        rc2, e2, r2 = run_direct(tmp_path, crossed, real_bin, plugins={"00-midnight.js": MIDNIGHT, "datefreeze.js": plugin},
                                 name="crossed")
        assert rc1 == 0 and rc2 == 0, (e1[-300:], e2[-300:])
        assert [r["n_update_removed"] for r in receipts_of(r2)] == [0, 1]
        assert [r["n_update_removed"] for r in receipts_of(r1)] == [0, 0]
        for a, b in zip(clean.chats, crossed.chats):
            sa, sb = lower_cased(a["headers"])["x-session-id"], lower_cased(b["headers"])["x-session-id"]
            assert normalised(all_text(a["body"]), sa) == normalised(all_text(b["body"]), sb)
            assert "Today's date is now" not in all_text(b["body"])
    with MockServer(script) as unmasked:                                  # positive control: the injector does reach the wire
        rc3, e3, _ = run_direct(tmp_path, unmasked, real_bin, plugins={"00-midnight.js": MIDNIGHT}, name="unmasked")
        assert rc3 == 0, e3[-300:]
        assert "Today's date is now: Sun Oct 18 2026" in all_text(unmasked.chats[1]["body"])


def test_wire_format_drift_refuses_before_any_request(real_bin, tmp_path):
    drift = """
export default { id: "bench.drift", setup(ctx) {
  ctx.session.hook("context", (event) => { for (const s of event.system) s.text = s.text.replace(/Today's date: [^\\n]*/, "Today's date: 2026-10-17") })
} }
"""
    with MockServer() as mock:
        rc, err, receipts = run_direct(tmp_path, mock, real_bin,
                                       plugins={"00-drift.js": drift, "datefreeze.js": PLUGIN.read_text()})
        assert rc != 0 and len(mock.chats) == 0
        got = receipts_of(receipts)
        assert got and "unexpected shape" in got[0]["error"]


def test_wire_a_plugin_that_failed_setup_leaves_no_receipts(real_bin, tmp_path):
    """opencode survives a throwing plugin setup (it logs and runs on), so the guard is the reconciliation: requests
    with no receipts abort the item. (The discovery proof below also refuses a `failed to load plugin` line.)"""
    for bad, label in ((None, "unset"), ("2026-01-05", "malformed")):
        with MockServer() as mock:
            rc, err, receipts = run_direct(tmp_path, mock, real_bin, plugins={"datefreeze.js": PLUGIN.read_text()},
                                           frozen=bad, name="env-" + label)
            assert receipts_of(receipts) == [] and len(mock.chats) == 2, label
            with pytest.raises(TransportAbort):
                df.reconcile(receipts if receipts.exists() else receipts, frozen=FROZEN, session_id="ses_x",
                             requests_observed=2)


def test_wire_plugin_load_is_proven_by_activation_discovery(real_bin, tmp_path):
    """The M50 proof reads `loading plugin ... id=<path>` from `opencode api GET /api/integration`."""
    with MockServer() as mock:
        root = tmp_path / "act"
        for d in ("home", "cfg/opencode/plugins", "data", "state", "cache", "tmp"):
            (root / d).mkdir(parents=True)
        (root / "cfg/opencode/plugins/datefreeze.js").write_text(PLUGIN.read_text())
        doc = json.loads(core.BENCH_OPENCODE_CONFIG.read_text())
        doc["providers"]["mlx-local"]["settings"]["baseURL"] = mock.base
        (root / "cfg/opencode/opencode.json").write_text(json.dumps(doc))
        scratch = root / "scratch"
        scratch.mkdir()
        env = core._opencode_env(root, scratch, core._seed_overlay(MODEL, 1), frozen_date=FROZEN,
                                 receipts=tmp_path / "r.jsonl")
        os.makedirs(env["TMPDIR"], exist_ok=True)
        got = subprocess.run([real_bin, "api", "GET", "/api/integration", "--standalone"], cwd=scratch,
                             env={**env, "OPENCODE_PRINT_LOGS": "1"}, capture_output=True, text=True, timeout=120)
        assert got.returncode == 0
        assert f'id={root / "cfg/opencode/plugins/datefreeze.js"}' in got.stderr
        env.pop("BENCH_FROZEN_PROMPT_DATE")
        bad = subprocess.run([real_bin, "api", "GET", "/api/integration", "--standalone"], cwd=scratch,
                             env={**env, "OPENCODE_PRINT_LOGS": "1"}, capture_output=True, text=True, timeout=120)
        assert "failed to load plugin" in bad.stderr and "P364_DATEFREEZE" in bad.stderr


# ------------------------------------------------------------------ the tg1 probe end to end
from bench.tests.test_tg1_integration import FROZEN as TG_FROZEN, fake_receipts, pinned_binary, tg_fixture  # noqa: E402,F401


def test_real_tg1_probe_masks_receipts_and_rows_second_item_fresh_file(probe, pinned_binary, monkeypatch, tmp_path):
    script = {1: dict(name="shell", input={"command": "echo hi"}), 3: dict(name="shell", input={"command": "echo hi"})}
    with MockServer(script) as mock:
        f = tg_fixture(probe, monkeypatch, tmp_path, binary=pinned_binary, mock=mock)
        assert f["run"]("one,two") == 0                      # the REAL destination / activation proof runs here
        rows = [json.loads(s) for s in f["out"].read_text().splitlines()]
        assert [r["id"] for r in rows] == ["python/one", "python/two"]
        for row in rows:
            assert row["prompt_date"] == TG_FROZEN != row["prompt_date_real"]
            assert row["prompt_date_update_removed"] is False
            assert set(row["evidence_sha256"]) >= {"events", "stderr", "export", "datefreeze"}
        receipts = [Path(r["events_path"].replace("$STACK_WORKDIR", str(tmp_path))).with_suffix("").parent
                    / (Path(r["events_path"]).name.split(".")[0] + ".datefreeze.jsonl") for r in rows]
        files = sorted(Path(tmp_path / "opencode_transcripts").rglob("*.datefreeze.jsonl"))
        assert len(files) == 2 and len({p.name for p in files}) == 2
        counts = [len(receipts_of(p)) for p in files]
        assert counts == [r["requests_observed"] for r in rows] and all(c >= 2 for c in counts)
        for chat in mock.chats:
            text = all_text(chat["body"])
            assert "Today's date: " + TG_FROZEN in text and REAL not in text and "Today's date is now" not in text
        assert len(mock.chats) == sum(counts)
        cfg = next((tmp_path / "opencode-probe-v2").glob("run-*")) / "cfg/opencode"
        assert sorted(p.relative_to(cfg).as_posix() for p in cfg.rglob("*")) == [
            "opencode.json", "plugins", "plugins/datefreeze.js", "plugins/noretry.js", "plugins/toolbounds.js"]
        man = json.loads(f["mp"].read_text())
        assert man["runtime"]["frozen_prompt_date"] == TG_FROZEN
        assert man["runtime"]["policy"]["datefreeze_sha256"] == hashlib.sha256(PLUGIN.read_bytes()).hexdigest()


def test_probe_requires_a_frozen_date_and_never_defaults_it(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    with pytest.raises(SystemExit, match="--frozen-prompt-date is required"):
        f["run"]("one", frozen=None)
    with pytest.raises(SystemExit, match="Www Mmm DD YYYY"):
        f["run"]("one", frozen="2026-01-05")
    assert not f["out"].exists() and not f["mp"].exists()


@pytest.mark.parametrize("case", ["no_receipts", "one_missing", "extra", "corrupt", "stale_date", "wrong_session", "error"])
def test_receipt_defects_abort_the_item_before_any_row(probe, monkeypatch, tmp_path, case):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    binary = Path(os.environ["OPENCODE_PROBE_BIN"])
    good = fake_receipts([("s1", 2)])
    text = binary.read_text()
    assert good in text
    bad = {
        "no_receipts": "",
        "one_missing": fake_receipts([("s1", 1)]),
        "extra": fake_receipts([("s1", 3)]),
        "corrupt": good + "printf 'not-json\\n' >> \"$BENCH_DATEFREEZE_RECEIPTS\"\n",
        "stale_date": good.replace(TG_FROZEN, "Tue Jan 06 2026"),
        "wrong_session": fake_receipts([("s9", 2)]),
        "error": good + 'printf \'{"sessionID":"s1","seq":3,"kind":"primary","frozen":"%s","error":"boom"}\\n\' '
                        '"' + TG_FROZEN + '" >> "$BENCH_DATEFREEZE_RECEIPTS"\n',
    }[case]
    binary.write_text(text.replace(good, bad))
    with pytest.raises(SystemExit, match="P364 date-freeze receipts"):
        f["run"]("one")
    assert not f["out"].exists()


def test_a_reused_receipt_path_is_refused(probe, monkeypatch, tmp_path):
    """Receipts are immutable evidence: a leftover file from an earlier item/run can never satisfy this one."""
    from bench import proc_guard as pg
    stale = tmp_path / "r.jsonl"
    stale.write_text(line())
    with pytest.raises(TransportAbort, match="immutable evidence path exists"):
        pg.reserve_evidence(stale)
