"""C121: seeded opencode sessions (per-item project-config overlay), the pinned v1 binary resolved
outside the repo, and the R8 CLAUDE.md switch. Box-free: the one integration test talks to a
throwaway mock OpenAI-compatible server on a random localhost port (never :8000, never a model)."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # benchmark/ on sys.path
import run_opencode_probe as P
from bench import provenance, rowschema

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
SHIPPED = Path(P.SHIPPED_OPENCODE_CONFIG)


# ------------------------------------------------------------------ pinned binary (C123, replaces AC6)
def test_pin_stays_at_1_18_30():
    assert P.PINNED_OPENCODE_VERSION == "1.18.30"


def test_opencode_bin_defaults_under_stack_workdir(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENCODE_PROBE_BIN", raising=False)
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    assert P._opencode_bin() == tmp_path / "opencode-1.18.30/node_modules/.bin/opencode"


def test_opencode_bin_env_override(monkeypatch):
    monkeypatch.setenv("OPENCODE_PROBE_BIN", "/x/opencode")
    assert P._opencode_bin() == Path("/x/opencode")


def test_opencode_version_refuses_a_missing_binary(tmp_path):
    with pytest.raises(SystemExit) as e:
        P._opencode_version(tmp_path / "nope")
    assert "nope" in str(e.value) or "missing" in str(e.value)


def test_opencode_version_runs_the_given_binary(monkeypatch, tmp_path):
    b = tmp_path / "opencode"; b.write_text("")
    seen = {}

    def fake(cmd, **kw):
        seen["cmd"] = cmd
        return "1.18.30\n"
    monkeypatch.setattr(subprocess, "check_output", fake)
    assert P._opencode_version(b) == "1.18.30"
    assert seen["cmd"] == [str(b), "--version"]


def test_opencode_env_puts_the_pinned_binary_dir_first_on_path(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(tmp_path / "bin" / "opencode"))
    env = P._opencode_env(tmp_path / "xdg")
    assert env["PATH"].split(os.pathsep)[0] == str(tmp_path / "bin")


# ------------------------------------------------------------------ AC1: overlay
def test_overlay_is_exactly_one_seed_key():
    assert P._seed_overlay(MODEL, 123) == {
        "provider": {"mlx-local": {"models": {MODEL: {"options": {"seed": 123}}}}}}


def test_write_overlay_writes_json_and_returns_sha(tmp_path):
    sha = P._write_seed_overlay(tmp_path, MODEL, 123)
    raw = (tmp_path / "opencode.json").read_bytes()
    assert json.loads(raw) == P._seed_overlay(MODEL, 123)
    assert sha == hashlib.sha256(raw).hexdigest()


def _deep_merge(a, b):
    out = copy.deepcopy(a)
    for k, v in b.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _diff_paths(a, b, pre=()):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in set(a) | set(b):
            out += _diff_paths(a.get(k), b.get(k), pre + (k,))
        return out
    return [] if a == b else [pre]


def test_overlay_overrides_nothing_but_the_seed_in_the_shipped_config():
    shipped = json.loads(SHIPPED.read_text())
    assert MODEL in shipped["provider"]["mlx-local"]["models"]
    merged = _deep_merge(shipped, P._seed_overlay(MODEL, 5))
    assert _diff_paths(shipped, merged) == [("provider", "mlx-local", "models", MODEL, "options", "seed")]


# ------------------------------------------------------------------ AC2: seeds
def test_item_seed_is_distinct_per_item_reproducible_and_base_dependent():
    s = {i: P._item_seed(i, 1) for i in ("python/a", "python/b", "go/c")}
    assert len(set(s.values())) == 3
    assert s["python/a"] == P._item_seed("python/a", 1) == rowschema.sample_seed("python/a", 0, base=1)
    assert P._item_seed("python/a", 2) != s["python/a"]


def test_seed_base_is_required(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_opencode_probe.py", "--model", "m", "--items", "x"])
    with pytest.raises(SystemExit) as e:
        P.main()
    assert e.value.code == 2


def test_row_seed_fields():
    f = P._seed_row_fields("python/a", 7, "abc")
    assert f == {"sampler_seed": rowschema.sample_seed("python/a", 0, base=7), "seed_base": 7,
                 "overlay_sha256": "abc"}


def test_manifest_runtime_records_seed_provenance(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENCODE_PROBE_BIN", raising=False)
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    rt = P._seed_runtime(7)
    assert rt["seed_base"] == 7 and rt["overlay_schema"] == "provider.mlx-local.models.<model>.options.seed"
    assert rt["opencode_bin"] == "$STACK_WORKDIR/opencode-1.18.30/node_modules/.bin/opencode"
    assert str(tmp_path) not in json.dumps(rt)
    assert rt["seed_propagation"] == "unverified"          # no marker from the integration test
    (tmp_path / "opencode-1.18.30").mkdir()
    (tmp_path / "opencode-1.18.30" / "seed_propagation_verified").write_text(P.PINNED_OPENCODE_VERSION)
    assert P._seed_runtime(7)["seed_propagation"] == "verified-by-test"


# ------------------------------------------------------------------ AC4: pre-check
def _fake_debug(models_options, base="http://localhost:8000/v1"):
    doc = {"provider": {"mlx-local": {"options": {"baseURL": base},
                                      "models": {MODEL: {"options": models_options}}}}}

    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(doc), stderr="")
    return run


def test_overlay_check_passes_when_seed_resolved_and_base_unchanged(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", _fake_debug({"temperature": 0.5, "seed": 9}))
    P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1")


def test_overlay_check_refuses_when_seed_not_resolved(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", _fake_debug({"temperature": 0.5}))
    with pytest.raises(provenance.ServedConfigError, match="M50.*seed"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1")


def test_overlay_check_refuses_when_base_url_changed(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", _fake_debug({"seed": 9}, base="http://localhost:9999/v1"))
    with pytest.raises(provenance.ServedConfigError, match="M50.*baseURL"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1")


# ------------------------------------------------------------------ AC5: R8 + policy hash
def test_env_disables_claude_code_prompt_loading(tmp_path):
    env = P._opencode_env(tmp_path / "xdg")
    assert env["OPENCODE_DISABLE_CLAUDE_CODE_PROMPT"] == "true"
    assert env["OPENCODE_DISABLE_EXTERNAL_SKILLS"] == "true"


def test_scaffold_policy_hash_changes_with_the_policy(monkeypatch):
    h0 = P._scaffold_runtime()["scaffold_policy_sha256"]
    monkeypatch.setattr(P, "SCAFFOLD_ENV_POLICY",
                        {"OPENCODE_DISABLE_EXTERNAL_SKILLS": "true"})   # the pre-C121 policy
    assert P._scaffold_runtime()["scaffold_policy_sha256"] != h0


def test_scaffold_runtime_names_both_switches_and_claude_md_state(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    rt = P._scaffold_runtime()
    assert "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT=true" in rt["skill_policy"]
    assert "OPENCODE_DISABLE_EXTERNAL_SKILLS=true" in rt["skill_policy"]
    assert rt["claude_md_present"] is False
    (tmp_path / ".claude").mkdir(); (tmp_path / ".claude" / "CLAUDE.md").write_text("x")
    assert P._scaffold_runtime()["claude_md_present"] is True


# ------------------------------------------------------------------ AC3: propagation (integration)
def _pinned_bin():
    """Read-only lookup (the conftest guard forbids the writer-flavoured resolver in tests)."""
    from bench import paths
    env = os.environ.get("OPENCODE_PROBE_BIN")
    if env:
        b = Path(env)
    else:
        wd = paths.resolve_stack_workdir(required=False)
        if wd is None:
            return None
        b = wd / P.OPENCODE_BIN_RELPATH
    return b if b.is_file() else None


class _Mock(BaseHTTPRequestHandler):
    bodies: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length", 0)))
        type(self).bodies.append(json.loads(body))
        self.send_response(200); self.send_header("content-type", "text/event-stream"); self.end_headers()
        for ch in ({"choices": [{"index": 0, "delta": {"role": "assistant", "content": "ok"}, "finish_reason": None}]},
                   {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}):
            ch.update(id="x", object="chat.completion.chunk", created=1, model="m")
            self.wfile.write(b"data: " + json.dumps(ch).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")


def test_pinned_opencode_forwards_seed_and_deployed_sampling_to_the_endpoint(tmp_path):
    """AC3. Run once with OPENCODE_PROBE_RECORD_VERIFIED=1 to stamp `seed_propagation: verified-by-test`."""
    b = _pinned_bin()
    if b is None:
        pytest.skip("pinned opencode binary absent (npm install --prefix $STACK_WORKDIR/opencode-1.18.30 "
                    "opencode-ai@1.18.30, or set OPENCODE_PROBE_BIN)")
    if P._opencode_version(b) != P.PINNED_OPENCODE_VERSION:
        pytest.skip("opencode binary is not the pinned version")
    _Mock.bodies = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cfg = json.loads(SHIPPED.read_text())
        cfg.pop("plugin", None); cfg.pop("mcp", None)
        prov = cfg["provider"]["mlx-local"]
        prov["options"]["baseURL"] = f"http://127.0.0.1:{srv.server_address[1]}/v1"
        cfg["provider"] = {"mlx-local": prov}
        xdgc = tmp_path / "xdgc"; (xdgc / "opencode").mkdir(parents=True)
        (xdgc / "opencode" / "opencode.json").write_text(json.dumps(cfg))
        proj = tmp_path / "proj"; proj.mkdir()          # NON-git scratch dir, as the probe uses
        P._write_seed_overlay(proj, MODEL, 424242)
        env = P._opencode_env(tmp_path / "xdgd")
        env.update(XDG_CONFIG_HOME=str(xdgc), OPENCODE_PROBE_BIN=str(b))
        env["PATH"] = str(b.parent) + os.pathsep + env["PATH"]
        subprocess.run([str(b), "run", "--dir", str(proj), "--model", f"mlx-local/{MODEL}", "--pure", "say hi"],
                       cwd=proj, env=env, capture_output=True, text=True, timeout=180,
                       stdin=subprocess.DEVNULL)
    finally:
        srv.shutdown()
    assert _Mock.bodies, "opencode sent no request to the mock endpoint"
    deployed = prov["models"][MODEL]["options"]
    for body in _Mock.bodies:
        assert body["seed"] == 424242
        for k, v in deployed.items():
            assert body[k] == v, (k, body.get(k), v)
    if os.environ.get("OPENCODE_PROBE_RECORD_VERIFIED") == "1":   # operator opt-in: stamps the manifest marker
        P._record_seed_propagation_verified(b)


def test_record_seed_propagation_writes_the_marker_next_to_the_default_install(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENCODE_PROBE_BIN", raising=False)
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    (tmp_path / "opencode-1.18.30").mkdir()
    P._record_seed_propagation_verified()
    assert (tmp_path / "opencode-1.18.30" / "seed_propagation_verified").read_text() == "1.18.30"
