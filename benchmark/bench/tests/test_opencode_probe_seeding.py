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
def test_pin_and_binary_install_dir_name_the_same_version():
    assert P.PINNED_OPENCODE_VERSION == "1.18.30"
    assert f"opencode-{P.PINNED_OPENCODE_VERSION}/" in P.OPENCODE_BIN_RELPATH


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


# ------------------------------------------------------------------ B1: fail-closed binary resolution
def _exe(path, body="#!/bin/sh\nexit 0\n", mode=0o755):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body); path.chmod(mode)
    return path


def test_require_opencode_bin_returns_the_exact_absolute_executable(monkeypatch, tmp_path):
    b = _exe(tmp_path / "x" / "opencode")
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(b))
    assert P._require_opencode_bin() == str(b)


def test_require_opencode_bin_refuses_relative_missing_and_non_executable(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCODE_PROBE_BIN", "opencode")           # bare name would be a PATH lookup
    with pytest.raises(SystemExit, match="absolute"):
        P._require_opencode_bin()
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(tmp_path / "gone" / "opencode"))
    with pytest.raises(SystemExit, match="gone"):
        P._require_opencode_bin()
    nx = _exe(tmp_path / "nx" / "opencode", mode=0o644)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(nx))
    with pytest.raises(SystemExit, match="executable"):
        P._require_opencode_bin()


def test_missing_pin_refuses_naming_the_path_and_never_spawns_a_path_opencode(monkeypatch, tmp_path):
    rec = tmp_path / "invocations.txt"
    fake = _exe(tmp_path / "brewbin" / "opencode", f"#!/bin/sh\necho \"$@\" >> {rec}\nexit 0\n")
    monkeypatch.setenv("PATH", str(fake.parent) + os.pathsep + os.environ["PATH"])
    wd = tmp_path / "wd"; wd.mkdir()
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    monkeypatch.delenv("OPENCODE_PROBE_BIN", raising=False)       # default path under wd: absent
    monkeypatch.setattr(sys, "argv", ["p", "--model", "m", "--items", "x", "--seed-base", "1"])
    with pytest.raises(SystemExit) as e:
        P.main()
    assert "opencode-1.18.30" in str(e.value) and "REFUSED" in str(e.value)
    assert not rec.exists(), "the PATH opencode was spawned"


def test_router_discovery_spawns_the_given_binary(monkeypatch, tmp_path):
    seen = {}

    def fake(cmd, **kw):
        seen["cmd0"] = cmd[0]
        doc = {"provider": {"mlx-local": {"options": {"baseURL": "http://localhost:8000/v1"}}}}
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(doc), stderr="")
    monkeypatch.setattr(subprocess, "run", fake)
    assert provenance.opencode_router_base(tmp_path, {}, opencode_bin="/pinned/opencode") == "http://localhost:8000/v1"
    assert seen["cmd0"] == "/pinned/opencode"


def test_export_and_overlay_check_spawn_the_given_binary(monkeypatch, tmp_path):
    cmds = []

    def fake_co(cmd, **kw):
        cmds.append(cmd[0])
        return "Session ID\nses_a1  t\n" if cmd[1] == "session" else json.dumps({"messages": []})
    monkeypatch.setattr(subprocess, "check_output", fake_co)
    P._export_latest_session({}, cwd=tmp_path, opencode_bin="/pinned/opencode")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: (cmds.append(cmd[0]) or _fake_debug(_resolved(9))(cmd)))
    P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/pinned/opencode")
    assert cmds == ["/pinned/opencode"] * 3


def test_run_opencode_spawns_the_given_binary(monkeypatch, tmp_path):
    seen = {}

    class Boom(Exception):
        pass

    def popen(cmd, **kw):
        seen["cmd0"] = cmd[0]
        raise Boom()
    monkeypatch.setattr(P.subprocess, "Popen", popen)
    with pytest.raises(Boom):
        P._run_opencode(MODEL, tmp_path, "p", tmp_path / "s", tmp_path / "t", lambda w, t: (False, ""), "",
                        tick_s=1, hard_ceiling_s=1, poll_s=1, stall_ticks=1, loop_repeats=1, pure=True,
                        opencode_bin="/pinned/opencode")
    assert seen["cmd0"] == "/pinned/opencode"


def test_opencode_version_runs_the_given_binary(monkeypatch, tmp_path):
    b = tmp_path / "opencode"; b.write_text("")
    seen = {}

    def fake(cmd, **kw):
        seen["cmd"] = cmd
        return "1.18.30\n"
    monkeypatch.setattr(subprocess, "check_output", fake)
    assert P._opencode_version(b) == "1.18.30"
    assert seen["cmd"] == [str(b), "--version"]


# ------------------------------------------------------------------ AC1: overlay
def test_overlay_is_exactly_one_seed_key():
    assert P._seed_overlay(MODEL, 123) == {
        "provider": {"mlx-local": {"models": {MODEL: {"options": {"seed": 123}}}}}}


def test_write_overlay_writes_json_and_returns_sha(tmp_path):
    sha = P._write_seed_overlay(tmp_path, MODEL, 123)
    raw = (tmp_path / "opencode.json").read_bytes()
    assert json.loads(raw) == P._seed_overlay(MODEL, 123)
    assert sha == hashlib.sha256(raw).hexdigest()


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


def _receipt_env(monkeypatch, tmp_path):
    """A fake pinned install + config + test file, all under tmp_path."""
    b = _exe(tmp_path / "opencode-1.18.30" / "node_modules" / ".bin" / "opencode", "#!/bin/sh\necho 1.18.30\n")
    cfg = tmp_path / "shipped.json"; cfg.write_text('{"a": 1}')
    tf = tmp_path / "the_test.py"; tf.write_text("# test v1")
    monkeypatch.delenv("OPENCODE_PROBE_BIN", raising=False)
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.setattr(P, "SHIPPED_OPENCODE_CONFIG", cfg)
    monkeypatch.setattr(P, "SEED_TEST_FILE", tf)
    return b, cfg, tf


def test_manifest_runtime_records_seed_provenance(monkeypatch, tmp_path):
    b, cfg, tf = _receipt_env(monkeypatch, tmp_path)
    rt = P._seed_runtime(7, global_sha="g1")
    assert rt["seed_base"] == 7 and rt["overlay_schema"] == "provider.mlx-local.models.<model>.options.seed"
    assert rt["opencode_bin"] == "$STACK_WORKDIR/opencode-1.18.30/node_modules/.bin/opencode"
    assert str(tmp_path) not in json.dumps(rt)
    assert rt["seed_propagation"] == "unverified"          # no receipt yet
    assert rt["opencode_global_config_sha256"] == "g1"
    P._record_seed_propagation_verified(b, "g1")
    assert P._seed_runtime(7, global_sha="g1")["seed_propagation"] == "verified-by-test"


def test_receipt_is_bound_to_exe_config_test_and_global_config_hashes(monkeypatch, tmp_path):
    b, cfg, tf = _receipt_env(monkeypatch, tmp_path)
    P._record_seed_propagation_verified(b, "g1")
    r = json.loads(P._seed_marker_path(b).read_text())
    assert set(r) >= {"version", "exe_sha256", "config_sha256", "test_sha256", "global_config_sha256"}
    ok = lambda: P._seed_runtime(7, global_sha="g1")["seed_propagation"]   # noqa: E731
    assert ok() == "verified-by-test"
    assert P._seed_runtime(7, global_sha="g2")["seed_propagation"] == "unverified"   # global config changed
    assert P._seed_runtime(7, global_sha=None)["seed_propagation"] == "unverified"   # unresolvable
    cfg.write_text('{"a": 2}')                                       # shipped config changed
    assert ok() == "unverified"
    cfg.write_text('{"a": 1}')
    assert ok() == "verified-by-test"
    tf.write_text("# test v2")                                       # integration test changed
    assert ok() == "unverified"
    tf.write_text("# test v1")
    b.write_text("#!/bin/sh\necho 1.18.30 # rebuilt\n")            # executable changed
    assert ok() == "unverified"


def test_global_config_sha_follows_the_config_dir_opencode_reports(tmp_path):
    cfgdir = tmp_path / "gcfg"; cfgdir.mkdir()
    (cfgdir / "opencode.json").write_text('{"x": 1}')
    b = _exe(tmp_path / "opencode", f"#!/bin/sh\necho 'home   /h'\necho 'config   {cfgdir}'\n")
    h1 = P._global_config_sha256(str(b), {})
    assert h1 and len(h1) == 64
    (cfgdir / "opencode.json").write_text('{"x": 2}')
    assert P._global_config_sha256(str(b), {}) != h1
    assert P._global_config_sha256(str(tmp_path / "missing"), {}) is None


def test_legacy_text_marker_reads_unverified(monkeypatch, tmp_path):
    b, cfg, tf = _receipt_env(monkeypatch, tmp_path)
    P._seed_marker_path(b).write_text(P.PINNED_OPENCODE_VERSION)
    assert P._seed_runtime(7, global_sha="g1")["seed_propagation"] == "unverified"


# ------------------------------------------------------------------ AC4: pre-check
def _shipped_opts():
    return dict(json.loads(SHIPPED.read_text())["provider"]["mlx-local"]["models"][MODEL]["options"])


def _fake_debug(models_options, base="http://localhost:8000/v1", limit=True):
    entry = {"options": models_options}
    if limit:
        entry["limit"] = {"context": 262144, "output": 102400}
    doc = {"provider": {"mlx-local": {"options": {"baseURL": base}, "models": {MODEL: entry}}}}

    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(doc), stderr="")
    return run


def _resolved(seed=9, **over):
    return {**_shipped_opts(), **over, "seed": seed}


def test_overlay_check_passes_when_seed_resolved_and_base_unchanged(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", _fake_debug(_resolved(9)))
    P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")


def test_overlay_check_refuses_when_seed_not_resolved(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", _fake_debug(_shipped_opts()))
    with pytest.raises(provenance.ServedConfigError, match="M50.*seed"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")


def test_overlay_check_refuses_when_base_url_changed(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", _fake_debug(_resolved(9), base="http://localhost:9999/v1"))
    with pytest.raises(provenance.ServedConfigError, match="M50.*baseURL"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")


def test_overlay_check_refuses_a_model_missing_from_the_global_config(monkeypatch, tmp_path):
    """B2: overlay-only model entry (seed, no deployed sampling, no limit) must NOT pass."""
    monkeypatch.setattr(subprocess, "run", _fake_debug({"seed": 9}, limit=False))
    with pytest.raises(provenance.ServedConfigError, match="M50.*deployed"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")


def test_overlay_check_refuses_one_drifted_field_naming_it(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", _fake_debug(_resolved(9, temperature=0.99)))
    with pytest.raises(provenance.ServedConfigError, match="M50.*temperature"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")


def test_overlay_check_refuses_a_missing_field_and_missing_limit(monkeypatch, tmp_path):
    o = _resolved(9); o.pop("top_k")
    monkeypatch.setattr(subprocess, "run", _fake_debug(o))
    with pytest.raises(provenance.ServedConfigError, match="M50.*top_k"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")
    monkeypatch.setattr(subprocess, "run", _fake_debug(_resolved(9), limit=False))
    with pytest.raises(provenance.ServedConfigError, match="M50.*limit"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")


def test_overlay_check_refuses_a_model_absent_from_the_shipped_config(monkeypatch, tmp_path):
    cfg = tmp_path / "shipped.json"; cfg.write_text(json.dumps({"provider": {"mlx-local": {"models": {}}}}))
    monkeypatch.setattr(P, "SHIPPED_OPENCODE_CONFIG", cfg)
    monkeypatch.setattr(subprocess, "run", _fake_debug(_resolved(9)))
    with pytest.raises(provenance.ServedConfigError, match="M50.*shipped"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")


def test_overlay_check_rejects_nonzero_exit_even_with_valid_json(monkeypatch, tmp_path):
    ok = _fake_debug(_resolved(9))

    def run(cmd, **kw):
        r = ok(cmd); r.returncode = 3
        return r
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(provenance.ServedConfigError, match="M50.*exit"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")


def test_overlay_check_rejects_timeout_and_malformed_json(monkeypatch, tmp_path):
    def timeout(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 120)
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(provenance.ServedConfigError, match="M50.*(timeout|Timeout)"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="{not json", stderr=""))
    with pytest.raises(provenance.ServedConfigError, match="M50.*JSON"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")


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
        env.update(XDG_CONFIG_HOME=str(xdgc))
        # PRODUCTION wiring only: the probe's own spawn function with the exact pinned executable
        # (no test-side PATH repair; `opencode` is not on this env's PATH ahead of anything).
        P._run_opencode(MODEL, proj, "say hi", proj / "sol.py", proj / "t.py", lambda w, t: (False, ""),
                        "", tick_s=300, hard_ceiling_s=170, poll_s=1.0, stall_ticks=50, loop_repeats=50,
                        pure=True, env=env, opencode_bin=str(b))
    finally:
        srv.shutdown()
    assert _Mock.bodies, "opencode sent no request to the mock endpoint"
    deployed = prov["models"][MODEL]["options"]
    for body in _Mock.bodies:
        assert body["seed"] == 424242
        for k, v in deployed.items():
            assert body[k] == v, (k, body.get(k), v)
    if os.environ.get("OPENCODE_PROBE_RECORD_VERIFIED") == "1":   # operator opt-in: stamps the manifest marker
        P._record_seed_propagation_verified(b, P._global_config_sha256(str(b), dict(os.environ)))


# ------------------------------------------------------------------ B2: continuation / resume; B9: overlay map
from bench.tests.test_m50_entrypoints import _oc_probe_setup  # noqa: E402


@pytest.fixture
def _stub_bin(monkeypatch, tmp_path_factory):
    b = _exe(tmp_path_factory.mktemp("stub") / "opencode", "#!/bin/sh\necho 1.18.30\n")
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(b))
    return b


def _prior(OP, out, rows=(), **over):
    rt = {"client": "opencode", "opencode_version": OP.PINNED_OPENCODE_VERSION,
          **OP._scaffold_runtime(), **OP._seed_runtime(1)}
    rt.update(over)
    rt = {k: v for k, v in rt.items() if v is not None}
    cfg = provenance.router_block("http://localhost:8000")["config"]
    out.with_suffix(".manifest.json").write_text(json.dumps(
        {"router": {"pid": 5, "config": cfg, "port": 8000}, "runtime": rt}))
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _resume_main(OP, monkeypatch, out, seed_base="1"):
    monkeypatch.setattr(provenance, "opencode_router_base", lambda *a, **k: "http://localhost:8000/v1")
    monkeypatch.setattr(sys, "argv", ["p", "--model", "m", "--items", "ex", "--seed-base", seed_base, "--out", str(out)])
    return OP.main()


ROW = {"id": "python/ex", "sample": 0, "passed": True}


def test_resume_refuses_a_different_seed_base_naming_both(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"; _prior(OP, out, [ROW], seed_base=9)
    with pytest.raises(SystemExit) as e:
        _resume_main(OP, monkeypatch, out, seed_base="1")
    m = str(e.value)
    assert "seed_base" in m and "9" in m and "1" in m


@pytest.mark.parametrize("field,val", [("scaffold_policy_sha256", "deadbeef"),
                                       ("opencode_bin", "$STACK_WORKDIR/other/opencode"),
                                       ("opencode_version", "9.9.9")])
def test_resume_refuses_scaffold_identity_drift(tmp_path, monkeypatch, _stub_bin, field, val):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"; _prior(OP, out, [ROW], **{field: val})
    with pytest.raises(SystemExit) as e:
        _resume_main(OP, monkeypatch, out)
    assert field in str(e.value)


def test_resume_refuses_a_pre_c121_manifest_with_rows(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"; _prior(OP, out, [ROW], seed_base=None, scaffold_policy_sha256=None)
    with pytest.raises(SystemExit, match="pre-C121"):
        _resume_main(OP, monkeypatch, out)


def test_resume_skips_items_already_present_and_writes_no_duplicate(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"; _prior(OP, out, [ROW])
    monkeypatch.setattr(OP, "_run_opencode", lambda *a, **k: pytest.fail("an already-recorded item re-ran"))
    before = out.read_text()
    assert _resume_main(OP, monkeypatch, out) == 0
    assert out.read_text() == before


def test_resume_with_matching_identity_continues_other_items(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"; _prior(OP, out, [{"id": "python/other", "sample": 0}])
    monkeypatch.setattr(OP, "_solution_and_test", lambda w, s, l: (_ for _ in ()).throw(StopIteration("reached item")))
    with pytest.raises(StopIteration):          # `ex` is not recorded, so it proceeds to run
        _resume_main(OP, monkeypatch, out)


def test_manifest_records_the_overlay_sha_per_item_before_any_traffic(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"
    monkeypatch.setattr(OP, "_solution_and_test", lambda w, s, l: (_ for _ in ()).throw(StopIteration("stop")))
    captured = {}
    real = OP._write_seed_overlay

    def spy(cwd, model, seed):
        captured["sha"] = real(cwd, model, seed)
        return captured["sha"]
    monkeypatch.setattr(OP, "_write_seed_overlay", spy)
    with pytest.raises(StopIteration):
        _resume_main(OP, monkeypatch, out)
    man = json.loads(out.with_suffix(".manifest.json").read_text())
    assert man["overlay_sha256_by_item"] == {"python/ex": captured["sha"]}


# ------------------------------------------------------------------ B3: ancestor instruction files + git-init'd item dirs
def test_git_init_scratch_creates_a_repo_boundary(tmp_path):
    P._git_init_scratch(tmp_path)
    assert (tmp_path / ".git").is_dir()


def test_scaffold_runtime_folds_scratch_git_init_into_the_policy_hash(monkeypatch):
    rt = P._scaffold_runtime()
    assert rt["scratch_git_init"] is True
    monkeypatch.setattr(P, "SCRATCH_GIT_INIT", False)
    rt2 = P._scaffold_runtime()
    assert rt2["scratch_git_init"] is False
    assert rt2["scaffold_policy_sha256"] != rt["scaffold_policy_sha256"]


def test_ancestor_instruction_files_are_hashed_with_portable_paths(monkeypatch, tmp_path):
    home = tmp_path / "home"; scratch = home / "wd" / "scratch" / "octmp"
    scratch.mkdir(parents=True)
    (home / "AGENTS.md").write_text("operator instructions")
    (home / "wd" / "CLAUDE.md").write_text("claude")
    (home / "wd" / ".cursor").mkdir(); (home / "wd" / ".cursor" / "rules").write_text("r")
    monkeypatch.setenv("HOME", str(home))
    got = P._ancestor_instruction_files(scratch)
    import hashlib
    assert got["~/AGENTS.md"] == hashlib.sha256(b"operator instructions").hexdigest()
    assert "~/wd/CLAUDE.md" in got and "~/wd/.cursor/rules" in got
    assert str(home) not in json.dumps(got)


def test_manifest_lists_ancestor_instruction_files(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    (tmp_path / "AGENTS.md").write_text("sentinel instructions")      # ancestor of <workdir>/scratch
    monkeypatch.setattr(OP, "_solution_and_test", lambda w, s, l: (_ for _ in ()).throw(StopIteration("stop")))
    out = tmp_path / "oc.jsonl"
    with pytest.raises(StopIteration):
        _resume_main(OP, monkeypatch, out)
    rt = json.loads(out.with_suffix(".manifest.json").read_text())["runtime"]
    assert rt["scratch_git_init"] is True
    assert any(k.endswith("AGENTS.md") for k in rt["ancestor_instruction_files"])
    assert "opencode_global_config_sha256" in rt


def test_item_dir_is_git_initialised_before_the_overlay_check(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    seen = {}

    def check(cwd, *a, **k):
        seen["git"] = (cwd / ".git").is_dir()
        raise provenance.ServedConfigError("M50 tripwire: stop")
    monkeypatch.setattr(OP, "_assert_overlay_resolved", check)
    with pytest.raises(SystemExit, match="M50"):
        _resume_main(OP, monkeypatch, tmp_path / "oc.jsonl")
    assert seen["git"] is True


def _run_with_mock(tmp_path, ancestor_sentinel, git_init):
    """Pinned opencode against a mock endpoint, item dir BELOW an ancestor AGENTS.md; returns the
    captured system prompts."""
    b = _pinned_bin()
    if b is None:
        pytest.skip("pinned opencode binary absent")
    _Mock.bodies = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cfg = json.loads(SHIPPED.read_text()); cfg.pop("plugin", None); cfg.pop("mcp", None)
        prov = cfg["provider"]["mlx-local"]
        prov["options"]["baseURL"] = f"http://127.0.0.1:{srv.server_address[1]}/v1"
        cfg["provider"] = {"mlx-local": prov}
        xdgc = tmp_path / "xdgc"; (xdgc / "opencode").mkdir(parents=True)
        (xdgc / "opencode" / "opencode.json").write_text(json.dumps(cfg))
        (tmp_path / "AGENTS.md").write_text(ancestor_sentinel)
        proj = tmp_path / "scratch" / "item"; proj.mkdir(parents=True)
        if git_init:
            P._git_init_scratch(proj)
        P._write_seed_overlay(proj, MODEL, 7)
        env = P._opencode_env(tmp_path / "xdgd"); env.update(XDG_CONFIG_HOME=str(xdgc))
        P._run_opencode(MODEL, proj, "say hi", proj / "s.py", proj / "t.py", lambda w, t: (False, ""), "",
                        tick_s=300, hard_ceiling_s=170, poll_s=1.0, stall_ticks=50, loop_repeats=50,
                        pure=True, env=env, opencode_bin=str(b))
    finally:
        srv.shutdown()
    assert _Mock.bodies
    return json.dumps([m for body in _Mock.bodies for m in body.get("messages", [])
                       if m.get("role") == "system"])


def test_ancestor_agents_md_reaches_the_prompt_without_git_init_and_not_with_it(tmp_path):
    sentinel = "SENTINEL-ANCESTOR-INSTRUCTIONS-8c1f"
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    leaked = _run_with_mock(tmp_path / "a", sentinel, git_init=False)
    assert sentinel in leaked, "known positive: the upward AGENTS.md search should reach the prompt"
    assert sentinel not in _run_with_mock(tmp_path / "b", sentinel, git_init=True)


# ------------------------------------------------------------------ B6b: refusal at an item leaves the exit stamp
def test_item_refusal_stamps_served_config_drift_on_an_existing_manifest(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"; _prior(OP, out, [])           # manifest of earlier items exists
    monkeypatch.setattr(OP, "_assert_overlay_resolved",
                        lambda *a, **k: (_ for _ in ()).throw(provenance.ServedConfigError("M50 tripwire: overlay")))
    with pytest.raises(SystemExit, match="M50"):
        _resume_main(OP, monkeypatch, out)
    man = json.loads(out.with_suffix(".manifest.json").read_text())
    assert "overlay" in man["served_config_drift"]["error"]


# ------------------------------------------------------------------ B7: overlay rewritten by the model
def test_overlay_after_run_is_restored_flagged_and_exported_under_the_original(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"
    seen = {}

    class Gate:
        stop_reason = "completed"; ticks = []; elapsed_s = 1.0

    def fake_run(model, cwd, *a, **k):
        (cwd / "opencode.json").write_text('{"provider": {"rewritten": true}}')   # the "model" rewrote it
        return 0, "", 1.0, Gate()

    def fake_export(env, *, cwd, opencode_bin):
        seen["overlay_at_export"] = json.loads((cwd / "opencode.json").read_text())
        return None
    monkeypatch.setattr(OP, "_run_opencode", fake_run)
    monkeypatch.setattr(OP, "_export_latest_session", fake_export)
    monkeypatch.setattr(OP, "_solution_and_test", lambda w, s, l: (w / "s.py", w / "t.py"))
    monkeypatch.setattr(OP, "_grade_result", lambda *a, **k: (False, "", False))
    monkeypatch.setattr(OP, "_scrub_then_tail", lambda t, n: t)

    def mk(w, s, l):
        (w / "s.py").write_text("x"); (w / "t.py").write_text("y"); return w / "s.py", w / "t.py"
    monkeypatch.setattr(OP, "_solution_and_test", mk)
    assert _resume_main(OP, monkeypatch, out) == 0
    row = json.loads(out.read_text().splitlines()[-1])
    assert row["overlay_rewritten_by_model"] is True
    assert row["overlay_sha256_after"] != row["overlay_sha256"]
    assert seen["overlay_at_export"] == OP._seed_overlay("m", row["sampler_seed"])   # restored before export
