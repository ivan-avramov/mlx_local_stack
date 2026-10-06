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
_REAL_VERSION = P._opencode_version
_REAL_CHECK = P._assert_overlay_resolved
SHIPPED = Path(P.BENCH_OPENCODE_CONFIG)       # the bench carrier (benchmark/opencode_bench.json)


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


def test_router_discovery_refuses_a_nonzero_exit_even_with_valid_json(monkeypatch, tmp_path):
    doc = {"provider": {"mlx-local": {"options": {"baseURL": "http://localhost:8000/v1"}}}}
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 2, stdout=json.dumps(doc), stderr="boom"))
    with pytest.raises(provenance.ServedConfigError, match="M50.*exit"):
        provenance.opencode_router_base(tmp_path, {}, opencode_bin="/x")


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


def test_opencode_version_spawns_under_the_given_env(monkeypatch, tmp_path):
    b = _exe(tmp_path / "opencode", "#!/bin/sh\necho 1.18.30\n")
    seen = {}

    def fake(cmd, **kw):
        seen["env"] = kw.get("env")
        return "1.18.30\n"
    monkeypatch.setattr(subprocess, "check_output", fake)
    P._opencode_version(b, {"XDG_STATE_HOME": "/redirected"})
    assert seen["env"] == {"XDG_STATE_HOME": "/redirected"}


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
def test_overlay_is_the_seed_plus_title_and_snapshot_switches_and_nothing_else():
    assert P._seed_overlay(MODEL, 123) == {
        "provider": {"mlx-local": {"models": {MODEL: {"options": {"seed": 123}}}}},
        "agent": {"title": {"disable": True}}, "snapshot": False}


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
    monkeypatch.setattr(P, "BENCH_OPENCODE_CONFIG", cfg)
    monkeypatch.setattr(P, "SEED_TEST_FILE", tf)
    return b, cfg, tf


def test_manifest_runtime_records_seed_provenance(monkeypatch, tmp_path):
    b, cfg, tf = _receipt_env(monkeypatch, tmp_path)
    rt = P._seed_runtime(7)
    assert rt["seed_base"] == 7 and rt["overlay_schema"].startswith("provider.mlx-local.models.<model>.options.seed")
    assert rt["opencode_bin"] == "$STACK_WORKDIR/opencode-1.18.30/node_modules/.bin/opencode"
    assert str(tmp_path) not in json.dumps(rt)
    assert rt["seed_propagation"] == "unverified"          # no receipt yet
    P._record_seed_propagation_verified(b)
    assert P._seed_runtime(7)["seed_propagation"] == "verified-by-test"


def test_receipt_is_bound_to_exe_config_and_test_hashes(monkeypatch, tmp_path):
    b, cfg, tf = _receipt_env(monkeypatch, tmp_path)
    P._record_seed_propagation_verified(b)
    r = json.loads(P._seed_marker_path(b).read_text())
    assert set(r) == {"version", "exe_sha256", "bench_config_sha256", "test_sha256"}
    ok = lambda: P._seed_runtime(7)["seed_propagation"]   # noqa: E731
    assert ok() == "verified-by-test"
    cfg.write_text('{"a": 2}')
    assert ok() == "unverified"
    cfg.write_text('{"a": 1}')
    assert ok() == "verified-by-test"
    tf.write_text("# test v2")
    assert ok() == "unverified"
    tf.write_text("# test v1")
    b.write_text("#!/bin/sh\necho 1.18.30 # rebuilt\n")
    assert ok() == "unverified"


def test_legacy_text_marker_reads_unverified(monkeypatch, tmp_path):
    b, cfg, tf = _receipt_env(monkeypatch, tmp_path)
    P._seed_marker_path(b).write_text(P.PINNED_OPENCODE_VERSION)
    assert P._seed_runtime(7)["seed_propagation"] == "unverified"


# ------------------------------------------------------------------ AC4: pre-check
def _shipped_opts():
    return dict(json.loads(SHIPPED.read_text())["provider"]["mlx-local"]["models"][MODEL]["options"])


def _bench_limit():
    return json.loads(SHIPPED.read_text())["provider"]["mlx-local"]["models"][MODEL]["limit"]


def _fake_debug(models_options, base="http://localhost:8000/v1", limit=True, instructions=None, limit_override=None,
                title_disabled=True, snapshot=False):
    entry = {"options": models_options}
    if limit:
        entry["limit"] = limit_override or _bench_limit()
    doc = {"provider": {"mlx-local": {"options": {"baseURL": base}, "models": {MODEL: entry}}},
           "agent": {"title": {"disable": title_disabled}}, "snapshot": snapshot}
    if instructions is not None:
        doc["instructions"] = instructions

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


def test_overlay_check_refuses_when_title_generation_is_not_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", _fake_debug(_resolved(9), title_disabled=False))
    with pytest.raises(provenance.ServedConfigError, match="M50.*title"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")


def test_overlay_check_refuses_when_snapshot_tracking_is_on(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", _fake_debug(_resolved(9), snapshot=True))
    with pytest.raises(provenance.ServedConfigError, match="M50.*snapshot"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")


def test_overlay_check_refuses_a_drifted_limit(monkeypatch, tmp_path):
    lim = dict(_bench_limit()); lim["output"] = lim["output"] + 1
    monkeypatch.setattr(subprocess, "run", _fake_debug(_resolved(9), limit_override=lim))
    with pytest.raises(provenance.ServedConfigError, match="M50.*limit"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")


def test_overlay_check_refuses_a_resolved_instructions_key(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", _fake_debug(_resolved(9), instructions=["~/private-rules.md"]))
    with pytest.raises(provenance.ServedConfigError, match="M50.*instructions"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")
    monkeypatch.setattr(subprocess, "run", _fake_debug(_resolved(9), instructions=[]))
    P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")


def test_overlay_check_refuses_a_model_absent_from_the_bench_config(monkeypatch, tmp_path):
    cfg = tmp_path / "bench.json"; cfg.write_text(json.dumps({"provider": {"mlx-local": {"models": {}}}}))
    monkeypatch.setattr(P, "BENCH_OPENCODE_CONFIG", cfg)
    monkeypatch.setattr(subprocess, "run", _fake_debug(_resolved(9)))
    with pytest.raises(provenance.ServedConfigError, match="M50.*bench"):
        P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")


def test_overlay_check_rejects_nonzero_exit_even_with_valid_json(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))        # the stderr scrub resolves the workdir
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


def _maybe_stamp_receipt(binary):
    """The operator opt-in branch of the AC3 test (OPENCODE_PROBE_RECORD_VERIFIED=1)."""
    if os.environ.get("OPENCODE_PROBE_RECORD_VERIFIED") == "1":
        P._record_seed_propagation_verified(binary)


def _hermetic_env(base, config_home=None, home=None):
    """E6: one controlled env for every integration spawn (incl. `--version`): temp HOME, XDG
    config/data/state/cache and TMPDIR all under `base`."""
    base = Path(base)
    for d in ("home", "state", "cache", "tmp", "data", "cfg"):
        (base / d).mkdir(parents=True, exist_ok=True)
    env = P._opencode_env(base / "data", config_home or (base / "cfg"), base / "state", base / "tmp")
    env["HOME"] = str(home or (base / "home"))
    env["XDG_CACHE_HOME"] = str(base / "cache")
    return env


def _validated_bin(base, config_home=None, home=None):
    """(binary, env) after a hermetic `--version`; skips when absent or not the pinned version."""
    b = _pinned_bin()
    if b is None:
        pytest.skip("pinned opencode binary absent (npm install --prefix $STACK_WORKDIR/opencode-1.18.30 "
                    "opencode-ai@1.18.30, or set OPENCODE_PROBE_BIN)")
    env = _hermetic_env(base, config_home, home)
    if P._opencode_version(b, env) != P.PINNED_OPENCODE_VERSION:
        pytest.skip("opencode binary is not the pinned version")
    return b, env


def _real_dirs_listing():
    """Top-level names of the operator's REAL opencode dirs: the integration tests must not change them."""
    out = {}
    for rel in (".config/opencode", ".local/state/opencode", ".local/share/opencode", ".cache/opencode"):
        d = Path.home() / rel
        out[rel] = sorted(os.listdir(d)) if d.is_dir() else None
    return out


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
    """AC3, in the configuration the probe really runs: a git-initialised item dir, the bench-owned
    config home, the probe's own spawn function, a hermetic env for every spawn. Nothing under the real
    ~/.config|.local/state|.local/share|.cache opencode dirs may change. Run once with
    OPENCODE_PROBE_RECORD_VERIFIED=1 to stamp `seed_propagation: verified-by-test`."""
    before = _real_dirs_listing()
    bodies, deployed = _isolation_run(tmp_path, isolate=True)
    assert bodies, "opencode sent no request to the mock endpoint"
    for body in bodies:
        assert body["seed"] == 31337
        for k, v in deployed.items():
            assert body[k] == v, (k, body.get(k), v)
    assert not any("title generator" in json.dumps(b.get("messages", [])) for b in bodies), \
        "title generation request was sent despite the overlay switch"
    assert _real_dirs_listing() == before, "an integration spawn wrote under the operator's real opencode dirs"
    cfg_home = tmp_path / "wd" / "opencode-probe" / "config-t1" / "opencode"
    assert not (cfg_home / "node_modules").exists(), "plugin install ran (network/npm activity)"
    _maybe_stamp_receipt(_pinned_bin())


# ------------------------------------------------------------------ B2: continuation / resume; B9: overlay map
from bench.tests.test_m50_entrypoints import _oc_probe_setup  # noqa: E402


@pytest.fixture
def _stub_bin(monkeypatch, tmp_path_factory):
    b = _exe(tmp_path_factory.mktemp("stub") / "opencode", "#!/bin/sh\necho 1.18.30\n")
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(b))
    return b


def _identity_now(OP):
    """The output-determining identity main() computes, built from the same helpers."""
    instr = OP._instruction_sources(Path(OP._scratch_root()))
    pg = OP.progress_gate
    ident = OP._run_identity(lang="python", pure=True, poly_sha="deadbeef", tick_s=pg.DEFAULT_TICK_S,
                             hard_ceiling_s=pg.DEFAULT_HARD_CEILING_S, stall_ticks=pg.DEFAULT_STALL_TICKS,
                             loop_repeats=pg.DEFAULT_LOOP_REPEATS, seed_base=1, poll_s=5.0,
                             cache_sha=OP._cache_bin_inventory_sha256(OP._real_cache_home()),
                             oc_bin=os.environ["OPENCODE_PROBE_BIN"], oc_version=OP.PINNED_OPENCODE_VERSION)
    return {"client": "opencode", **ident, "effective_instruction_sources": instr,
            "instruction_sources_sha256": OP._instruction_sources_sha256(instr)}


def _prior(OP, out, rows=(), doc_extra=None, **over):
    doc_extra = doc_extra or {}
    rt = _identity_now(OP)
    for k, v in over.items():
        if v is None:
            rt.pop(k, None)
        else:
            rt[k] = v
    blk = {**provenance.router_block("http://localhost:8000"), "pid": 5}
    doc = {"model": "m", "git": provenance._git_shas(), "router": blk, "runtime": rt}
    doc.update(doc_extra)
    out.with_suffix(".manifest.json").write_text(json.dumps(doc))
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _resume_main(OP, monkeypatch, out, seed_base="1", items="ex"):
    monkeypatch.setattr(provenance, "opencode_router_base", lambda *a, **k: "http://localhost:8000/v1")
    monkeypatch.setattr(sys, "argv", ["p", "--model", "m", "--items", items, "--seed-base", seed_base, "--out", str(out)])
    return OP.main()


def _stub_full_item(OP, monkeypatch, rewrite_overlay=False):
    """Stubs for one complete item through main(): run, export, grade."""
    class Gate:
        stop_reason = "completed"; ticks = []; elapsed_s = 1.0
    seen = {"runs": 0}

    def fake_run(model, cwd, *a, **k):
        seen["runs"] += 1
        if rewrite_overlay:
            (cwd / "opencode.json").write_text('{"provider": {"rewritten": true}}')
        return 0, "", 1.0, Gate()

    def fake_export(env, *, cwd, opencode_bin):
        seen["overlay_at_export"] = json.loads((cwd / "opencode.json").read_text())
        return None

    def mk(w, s_, l):
        (w / "s.py").write_text("x"); (w / "t.py").write_text("y"); return w / "s.py", w / "t.py"
    monkeypatch.setattr(OP, "_run_opencode", fake_run)
    monkeypatch.setattr(OP, "_export_latest_session", fake_export)
    monkeypatch.setattr(OP, "_solution_and_test", mk)
    monkeypatch.setattr(OP, "_grade_result", lambda *a, **k: (False, "", False))
    monkeypatch.setattr(OP, "_scrub_then_tail", lambda t, n: t)
    return seen


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
                                       ("opencode_version", "9.9.9"),
                                       ("opencode_bench_config_sha256", "changed-bench"),
                                       ("skill_policy", "OPENCODE_X=true"),
                                       ("scratch_git_init", False),
                                       ("env_switches", {"OPENCODE_X": "true"}),
                                       ("bench_home_isolation", False),
                                       ("overlay_schema", "other"),
                                       ("lang", "go"), ("pure", False), ("polyglot_sha", "other"),
                                       ("tick_s", 1), ("hard_ceiling_s", 1), ("stall_ticks", 99),
                                       ("loop_repeats", 99), ("opencode_exe_sha256", "other"),
                                       ("env_policy", {"XDG_STATE_HOME": "default"}),
                                       ("poll_s", 99.0), ("cache_bin_inventory_sha256", "changed-cache"),
                                       ("probe_code_sha256", "changed-probe")])
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
    (home / "wd" / "CONTEXT.md").write_text("ctx")
    (home / "wd" / ".cursor").mkdir(); (home / "wd" / ".cursor" / "rules").write_text("r")   # never read by 1.18.30
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "isolated-workdir"))   # not the caller's
    got = P._ancestor_instruction_files(scratch)
    import hashlib
    assert got["~/AGENTS.md"] == hashlib.sha256(b"operator instructions").hexdigest()
    assert "~/wd/CLAUDE.md" in got and "~/wd/CONTEXT.md" in got
    assert "~/wd/.cursor/rules" not in got
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
    assert rt["opencode_config_copy_sha256"] == rt["opencode_bench_config_sha256"]
    assert "opencode-probe/config-" in rt["opencode_config_home"]


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
    xdgc = tmp_path / "cfg"
    b, env = _validated_bin(tmp_path, xdgc)
    _Mock.bodies = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cfg = json.loads(SHIPPED.read_text())     # the carrier verbatim, INCLUDING its `plugin` key
        prov = cfg["provider"]["mlx-local"]
        prov["options"]["baseURL"] = f"http://127.0.0.1:{srv.server_address[1]}/v1"
        cfg["provider"] = {"mlx-local": prov}
        (xdgc / "opencode").mkdir(parents=True, exist_ok=True)
        (xdgc / "opencode" / "opencode.json").write_text(json.dumps(cfg))
        (tmp_path / "AGENTS.md").write_text(ancestor_sentinel)
        proj = tmp_path / "scratch" / "item"; proj.mkdir(parents=True)
        if git_init:
            P._git_init_scratch(proj)
        P._write_seed_overlay(proj, MODEL, 7)
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
def _add_exercise(tmp_path, name):
    (tmp_path / "poly" / "python" / "exercises" / "practice" / name).mkdir(parents=True, exist_ok=True)


def _second_item_refusal(OP, monkeypatch, tmp_path, message):
    """Item 1 runs (stubs); the overlay check refuses at item 2."""
    _add_exercise(tmp_path, "ex2")
    _stub_full_item(OP, monkeypatch)
    n = {"calls": 0}

    def check(*a, **k):
        n["calls"] += 1
        if n["calls"] >= 2:
            raise provenance.ServedConfigError(message)
    monkeypatch.setattr(OP, "_assert_overlay_resolved", check)


def test_a_refusal_before_this_session_wrote_anything_leaves_the_previous_manifest_untouched(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"; _prior(OP, out, [])           # a clean earlier session's manifest
    before = out.with_suffix(".manifest.json").read_bytes()
    monkeypatch.setattr(OP, "_assert_overlay_resolved",
                        lambda *a, **k: (_ for _ in ()).throw(provenance.ServedConfigError("M50 tripwire: transient")))
    with pytest.raises(SystemExit, match="M50"):
        _resume_main(OP, monkeypatch, out)
    assert out.with_suffix(".manifest.json").read_bytes() == before


def test_item_refusal_after_this_session_wrote_the_manifest_stamps_drift(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"
    _second_item_refusal(OP, monkeypatch, tmp_path, "M50 tripwire: overlay")
    with pytest.raises(SystemExit, match="M50"):
        _resume_main(OP, monkeypatch, out, items="ex,ex2")
    man = json.loads(out.with_suffix(".manifest.json").read_text())
    assert "overlay" in man["served_config_drift"]["error"] and man["served_config_drift"]["item"] == "python/ex2"


# ------------------------------------------------------------------ B7: overlay rewritten by the model
def test_overlay_after_run_is_restored_flagged_and_exported_under_the_original(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"
    seen = _stub_full_item(OP, monkeypatch, rewrite_overlay=True)
    assert _resume_main(OP, monkeypatch, out) == 0
    row = json.loads(out.read_text().splitlines()[-1])
    assert row["overlay_rewritten_by_model"] is True
    assert row["passed"] is None and row["acc"] is None and "overlay" in row["grade_excluded_reason"]
    assert row["overlay_sha256_after"] != row["overlay_sha256"]
    assert seen["overlay_at_export"] == OP._seed_overlay("m", row["sampler_seed"])   # restored before export


# ------------------------------------------------------------------ C1: version validated BEFORE discovery
def test_override_pointing_at_v2_is_refused_before_any_debug_config_spawn(tmp_path, monkeypatch):
    log = tmp_path / "calls.txt"
    fake = _exe(tmp_path / "fakebin" / "opencode",
                f"#!/bin/sh\necho \"$@\" >> {log}\nif [ \"$1\" = \"--version\" ]; then echo 2.0.20; fi\nexit 0\n")
    wd = tmp_path / "wd"; wd.mkdir()
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(fake))
    monkeypatch.setattr(sys, "argv", ["p", "--model", "m", "--items", "x", "--seed-base", "1"])
    with pytest.raises(SystemExit) as e:
        P.main()
    assert "2.0.20" in str(e.value)
    calls = log.read_text().split("\n")
    assert [c for c in calls if c] == ["--version"], calls      # no `debug config` / `debug paths` ever ran


# ------------------------------------------------------------------ C2: continuation keeps original attribution
def test_continuation_preserves_the_prior_identity_in_history(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"; _prior(OP, out, [{"id": "python/other", "sample": 0}])
    monkeypatch.setattr(OP, "_solution_and_test", lambda w, s, l: (_ for _ in ()).throw(StopIteration("stop")))
    with pytest.raises(StopIteration):
        _resume_main(OP, monkeypatch, out)
    man = json.loads(out.with_suffix(".manifest.json").read_text())
    hist = man["continuation_history"]
    assert len(hist) == 1 and hist[0]["runtime"]["seed_base"] == 1
    assert hist[0]["runtime"]["scaffold_policy_sha256"] == _identity_now(OP)["scaffold_policy_sha256"]


# ------------------------------------------------------------------ C3: effective instruction sources
def test_instruction_inventory_is_observation_only_never_in_the_policy_hash(monkeypatch, tmp_path):
    """E4: editing a (git-init-blocked) ancestor instruction file changes the recorded inventory hash but
    neither the scaffold-policy hash nor the receipt."""
    home = tmp_path / "home"; scratch = home / "scratch"; scratch.mkdir(parents=True)
    (home / "AGENTS.md").write_text("v1")
    monkeypatch.setenv("HOME", str(home)); monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))
    h1 = P._instruction_sources_sha256(P._instruction_sources(scratch)); p1 = P._scaffold_runtime()["scaffold_policy_sha256"]
    (home / "AGENTS.md").write_text("v2")
    h2 = P._instruction_sources_sha256(P._instruction_sources(scratch)); p2 = P._scaffold_runtime()["scaffold_policy_sha256"]
    assert h1 != h2 and p1 == p2


def test_policy_hash_changes_with_each_effective_input(monkeypatch):
    base = P._scaffold_runtime(opencode_version="1.18.30", exe_sha="e1")["scaffold_policy_sha256"]
    assert P._scaffold_runtime(opencode_version="1.18.31", exe_sha="e1")["scaffold_policy_sha256"] != base
    assert P._scaffold_runtime(opencode_version="1.18.30", exe_sha="e2")["scaffold_policy_sha256"] != base
    monkeypatch.setattr(P, "BENCH_HOME_ISOLATION", False)
    assert P._scaffold_runtime(opencode_version="1.18.30", exe_sha="e1")["scaffold_policy_sha256"] != base


def test_bench_config_home_holds_only_a_verbatim_copy_of_the_shipped_config(tmp_path):
    home = P._make_bench_config_home(tmp_path, "run1")
    assert sorted(p.name for p in home.rglob("*") if p.is_file()) == ["opencode.json"]
    assert (home / "opencode" / "opencode.json").read_bytes() == SHIPPED.read_bytes()
    assert P._sha_of(home / "opencode" / "opencode.json") == P._scaffold_runtime()["opencode_bench_config_sha256"]


def test_env_redirects_the_config_home_when_given(tmp_path):
    assert P._opencode_env(tmp_path / "d", tmp_path / "cfg")["XDG_CONFIG_HOME"] == str(tmp_path / "cfg")


def test_discovery_and_item_env_use_the_bench_config_home_never_the_personal_one(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    seen = {}

    def discovery(cwd=None, env=None, provider="mlx-local", **k):
        seen["disc"] = env["XDG_CONFIG_HOME"]
        return "http://localhost:8000/v1"
    monkeypatch.setattr(provenance, "opencode_router_base", discovery)

    def check(cwd, env, *a, **k):
        seen["item"] = env["XDG_CONFIG_HOME"]
        seen["copy"] = (Path(env["XDG_CONFIG_HOME"]) / "opencode" / "opencode.json").read_bytes()
        raise provenance.ServedConfigError("M50 tripwire: stop")
    monkeypatch.setattr(OP, "_assert_overlay_resolved", check)
    monkeypatch.setattr(sys, "argv", ["p", "--model", "m", "--items", "ex", "--seed-base", "1",
                                      "--out", str(tmp_path / "oc.jsonl")])
    with pytest.raises(SystemExit):
        OP.main()
    assert seen["disc"] == seen["item"]
    assert seen["disc"].startswith(str(tmp_path / "opencode-probe" / "config-"))
    assert seen["copy"] == SHIPPED.read_bytes()


# ------------------------------------------------------------------ isolation: personal config never reaches the request
def _isolation_run(tmp_path, isolate):
    home = tmp_path / "home"; pdir = home / ".config" / "opencode"; pdir.mkdir(parents=True)
    _Mock.bodies = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cfg = json.loads(SHIPPED.read_text())     # the carrier verbatim, INCLUDING its `plugin` key
        prov = cfg["provider"]["mlx-local"]
        prov["options"]["baseURL"] = f"http://127.0.0.1:{srv.server_address[1]}/v1"
        cfg["provider"] = {"mlx-local": prov}
        _mock_bench_source(tmp_path).write_text(json.dumps(cfg))
        cfg_home = P._make_bench_config_home(tmp_path / "wd", "t1", source=_mock_bench_source(tmp_path)) if isolate else None
        # the validated binary and env: the SAME hermetic env for `--version` and the run
        b, env = _validated_bin(tmp_path, cfg_home, home)
        if not isolate:
            env.pop("XDG_CONFIG_HOME", None)
        deployed = prov["models"][MODEL]["options"]
        pers = json.loads(json.dumps(cfg))
        pers["provider"]["mlx-local"]["models"][MODEL]["options"].update(temperature=0.987, top_k=3, thinking_budget=7)
        (pdir / "opencode.json").write_text(json.dumps(pers))
        (pdir / "AGENTS.md").write_text("SENTINEL-PERSONAL-GLOBAL-AGENTS-5e2a")
        proj = tmp_path / "wd" / "scratch" / "item"; proj.mkdir(parents=True)
        P._git_init_scratch(proj)
        P._write_seed_overlay(proj, MODEL, 31337)
        P._run_opencode(MODEL, proj, "say hi", proj / "s.py", proj / "t.py", lambda w, t: (False, ""), "",
                        tick_s=300, hard_ceiling_s=170, poll_s=1.0, stall_ticks=50, loop_repeats=50,
                        pure=True, env=env, opencode_bin=str(b))
    finally:
        srv.shutdown()
    return list(_Mock.bodies), deployed


def _mock_bench_source(tmp_path):
    return tmp_path / "bench-source.json"


def test_personal_opencode_config_and_agents_md_never_reach_the_request(tmp_path):
    """Operator ruling 2026-10-06. Known positive first: WITHOUT the bench config home the fake personal
    config's sampling and global AGENTS.md DO reach the request; with it, the body carries the bench
    values + seed and the sentinel never enters the system prompt."""
    (tmp_path / "open").mkdir(); (tmp_path / "iso").mkdir()
    before = _real_dirs_listing()
    bodies, _ = _isolation_run(tmp_path / "open", isolate=False)
    leaked = json.dumps([m for b in bodies for m in b.get("messages", [])])
    assert any(b.get("temperature") == 0.987 for b in bodies) or "SENTINEL-PERSONAL-GLOBAL-AGENTS-5e2a" in leaked, \
        "known positive failed: the personal config is not picked up even without isolation"
    bodies, deployed = _isolation_run(tmp_path / "iso", isolate=True)
    assert bodies, "no request reached the mock (opencode did not use the bench config home)"
    for body in bodies:
        assert body["seed"] == 31337
        for k, v in deployed.items():
            assert body[k] == v, (k, body.get(k), v)
        assert "SENTINEL-PERSONAL-GLOBAL-AGENTS-5e2a" not in json.dumps(body.get("messages", []))
    assert _real_dirs_listing() == before


# ------------------------------------------------------------------ C1/C2 (round 2 review): drift, router sha, history
def test_resume_refuses_when_the_previous_session_drifted(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"
    _prior(OP, out, [ROW], doc_extra={"served_config_drift": {"error": "router changed"}})
    with pytest.raises(SystemExit, match="served_config_drift"):
        _resume_main(OP, monkeypatch, out)


def test_resume_refuses_a_different_router_config_sha(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"; _prior(OP, out, [ROW])
    doc = json.loads(out.with_suffix(".manifest.json").read_text())
    doc["router"]["config_sha256"] = "0" * 64
    out.with_suffix(".manifest.json").write_text(json.dumps(doc))
    with pytest.raises(SystemExit, match="config_sha256"):
        _resume_main(OP, monkeypatch, out)


def test_continuation_keeps_the_previous_sessions_router_exit(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"
    _prior(OP, out, [{"id": "python/other", "sample": 0}], doc_extra={"router_exit": {"pid": 5, "config_sha256": "x"}})
    monkeypatch.setattr(OP, "_solution_and_test", lambda w, s, l: (_ for _ in ()).throw(StopIteration("stop")))
    with pytest.raises(StopIteration):
        _resume_main(OP, monkeypatch, out)
    man = json.loads(out.with_suffix(".manifest.json").read_text())
    assert man["continuation_history"][0]["router_exit"] == {"pid": 5, "config_sha256": "x"}


# ------------------------------------------------------------------ registry coverage (source-of-truth carrier)
def test_every_bench_role_registry_model_has_a_block_in_the_bench_config():
    import yaml
    reg = yaml.safe_load((Path(P.REPO) / "main_models.yaml").read_text())
    blocks = json.loads(SHIPPED.read_text())["provider"]["mlx-local"]["models"]
    need = [m["name"] for m in reg["models"] if (m.get("presentation") or {}).get("role") in ("main", "candidate")]
    assert need and [n for n in need if n not in blocks] == []


def test_bench_config_is_the_default_source_of_the_config_home(tmp_path):
    home = P._make_bench_config_home(tmp_path, "r")
    assert (home / "opencode" / "opencode.json").read_bytes() == Path(P.BENCH_OPENCODE_CONFIG).read_bytes()


# ------------------------------------------------------------------ round 4
def _recording_bin(tmp_path_factory, monkeypatch, seed):
    """Fake pinned `opencode` that logs argv[1:2] + its redirected env on every spawn."""
    d = tmp_path_factory.mktemp("recbin")
    blk = json.loads(SHIPPED.read_text())["provider"]["mlx-local"]["models"][MODEL]
    doc = {"provider": {"mlx-local": {"options": {"baseURL": "http://localhost:8000/v1"},
                                      "models": {MODEL: {"options": {**blk["options"], "seed": seed},
                                                         "limit": blk["limit"]}}}},
           "agent": {"title": {"disable": True}}, "snapshot": False}
    (d / "resolved.json").write_text(json.dumps(doc))
    log = d / "spawns.txt"
    b = _exe(d / "opencode", f"#!/bin/sh\necho \"$*|$XDG_CONFIG_HOME|$XDG_DATA_HOME|$XDG_STATE_HOME|$TMPDIR|$HOME|$OPENCODE_DISABLE_CLAUDE_CODE_SKILLS\" >> {log}\n"
                             f"if [ \"$1\" = \"--version\" ]; then echo 1.18.30; exit 0; fi\ncat {d / 'resolved.json'}\n")
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(b))
    return log


def test_every_spawn_runs_under_the_bench_owned_env(tmp_path, tmp_path_factory, monkeypatch):
    """E1: --version, discovery, destination check and overlay check all carry the redirected config,
    data, state and TMPDIR (all inside the workdir); the cache home stays default."""
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    monkeypatch.setattr(OP, "_opencode_version", _REAL_VERSION)
    monkeypatch.setattr(OP, "_assert_overlay_resolved", _REAL_CHECK)
    monkeypatch.setenv("OPENCODE_DISABLE_CLAUDE_CODE_SKILLS", "true")      # the operator's own stray switch
    log = _recording_bin(tmp_path_factory, monkeypatch, OP._item_seed("python/ex", 1))
    monkeypatch.setattr(OP, "_solution_and_test", lambda w, s_, l: (_ for _ in ()).throw(StopIteration("stop")))
    monkeypatch.setattr(sys, "argv", ["p", "--model", MODEL, "--items", "ex", "--seed-base", "1",
                                      "--out", str(tmp_path / "oc.jsonl")])
    with pytest.raises(StopIteration):
        OP.main()
    lines = [l.split("|") for l in log.read_text().splitlines()]
    assert lines[0][0].startswith("--version") and len(lines) >= 4
    wd = str(tmp_path)
    for cmd, cfg, data, state, tmp, home, stray in lines:
        assert cfg.startswith(f"{wd}/opencode-probe/config-"), (cmd, cfg)
        assert data.startswith(wd + "/"), (cmd, data)
        assert state == f"{wd}/opencode-probe/home/.local/state", (cmd, state)
        assert tmp.startswith(f"{wd}/opencode-probe/tmp-"), (cmd, tmp)
        assert home == f"{wd}/opencode-probe/home", (cmd, home)
        assert stray == "", "a stray parent OPENCODE_* switch leaked into the child env"
    debug = [l[0] for l in lines if l[0].startswith("debug config")]
    assert len(debug) == 3 and all("--pure" in d for d in debug), debug     # discovery, destination, overlay
    man = json.loads((tmp_path / "oc.manifest.json").read_text())
    assert man["runtime"]["env_policy"]["XDG_CACHE_HOME"].startswith("the real default cache")
    assert man["runtime"]["opencode_bench_home"] == "$STACK_WORKDIR/opencode-probe/home"
    assert man["runtime"]["env_switches"] == P.SCAFFOLD_ENV_POLICY
    assert man["runtime"]["title_generation"].startswith("disabled")
    assert man["runtime"]["title_request_provider"] is None


def test_resume_identity_per_field_via_main_model_and_serving_code(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"; _prior(OP, out, [ROW], doc_extra={"model": "other-model"})
    with pytest.raises(SystemExit, match="model"):
        _resume_main(OP, monkeypatch, out)
    g = provenance._git_shas(); g = json.loads(json.dumps(g))
    g["serving_path"] = {**(g.get("serving_path") or {}), "src/mlx-vlm": "deadbeef"}
    _prior(OP, out, [ROW], doc_extra={"git": g})
    with pytest.raises(SystemExit, match="serving"):
        _resume_main(OP, monkeypatch, out)


def test_continuation_history_preserves_the_full_prior_attribution(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"; _prior(OP, out, [{"id": "python/other", "sample": 0}])
    prev = json.loads(out.with_suffix(".manifest.json").read_text())
    monkeypatch.setattr(OP, "_solution_and_test", lambda w, s_, l: (_ for _ in ()).throw(StopIteration("stop")))
    with pytest.raises(StopIteration):
        _resume_main(OP, monkeypatch, out)
    h = json.loads(out.with_suffix(".manifest.json").read_text())["continuation_history"][0]
    assert h["runtime"] == prev["runtime"] and h["router"] == prev["router"]
    assert h["model"] == "m" and h["git"] == prev["git"]


def test_duplicate_requested_items_run_once(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"
    seen = _stub_full_item(OP, monkeypatch)
    assert _resume_main(OP, monkeypatch, out, items="ex,ex") == 0
    assert seen["runs"] == 1 and len(out.read_text().splitlines()) == 1


def test_an_all_skipped_resume_leaves_the_manifest_byte_identical(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"
    _prior(OP, out, [ROW], doc_extra={"router_exit": {"pid": 5, "config_sha256": "x"}})
    before = out.with_suffix(".manifest.json").read_bytes()
    monkeypatch.setattr(OP, "_run_opencode", lambda *a, **k: pytest.fail("ran"))
    assert _resume_main(OP, monkeypatch, out) == 0
    assert out.with_suffix(".manifest.json").read_bytes() == before


def test_persisted_error_strings_are_scrubbed_of_home_paths(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"
    leak = f"M50 tripwire: overlay failed at {Path.home()}/ws/scratch/oc-x/ex via {Path.home()}/bin/opencode"
    _second_item_refusal(OP, monkeypatch, tmp_path, leak)
    with pytest.raises(SystemExit):
        _resume_main(OP, monkeypatch, out, items="ex,ex2")
    text = out.with_suffix(".manifest.json").read_text()
    assert str(Path.home()) not in text and "$HOME" in text


def test_pre_item_refusal_removes_the_per_run_dirs_and_success_keeps_them(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    monkeypatch.setattr(OP, "_assert_overlay_resolved",
                        lambda *a, **k: (_ for _ in ()).throw(provenance.ServedConfigError("M50 tripwire: overlay")))
    with pytest.raises(SystemExit):
        _resume_main(OP, monkeypatch, tmp_path / "oc.jsonl")
    # the per-run dirs are gone; only the persistent bench HOME remains
    assert sorted(p.name for p in (tmp_path / "opencode-probe").iterdir()) == ["home"]
    assert not list((tmp_path / "scratch").glob("m50-discovery-xdg-data*")) if (tmp_path / "scratch").exists() else True
    # success path keeps the config home (it is part of the run's provenance)
    OP2 = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    _stub_full_item(OP2, monkeypatch)
    assert _resume_main(OP2, monkeypatch, tmp_path / "oc2.jsonl") == 0
    assert any(p.name.startswith("config-") for p in (tmp_path / "opencode-probe").iterdir())


# ------------------------------------------------------------------ round 4b
def test_child_env_drops_every_parent_opencode_variable_then_applies_the_switches(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCODE_DISABLE_CLAUDE_CODE_SKILLS", "true")
    monkeypatch.setenv("OPENCODE_SOMETHING_ELSE", "1")
    monkeypatch.setenv("OPENCODE_DISABLE_CLAUDE_CODE_PROMPT", "false")     # even a conflicting policy var
    env = P._opencode_env(tmp_path / "d")
    assert "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS" not in env and "OPENCODE_SOMETHING_ELSE" not in env
    assert env["OPENCODE_DISABLE_CLAUDE_CODE_PROMPT"] == "true"
    assert {k: v for k, v in env.items() if k.startswith("OPENCODE_")} == P.SCAFFOLD_ENV_POLICY


def test_bench_home_redirects_home_and_pins_the_real_cache_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    env = P._opencode_env(tmp_path / "d", tmp_path / "c", tmp_path / "s", tmp_path / "t", tmp_path / "home")
    assert env["HOME"] == str(tmp_path / "home")
    assert env["XDG_CACHE_HOME"] == str(Path(os.path.expanduser("~")) / ".cache")     # the REAL cache dir


SENTINELS = ("SENTINEL-OPENCODE-AGENT-77a1", "SENTINEL-CLAUDE-MD-77a2", "SENTINEL-HOME-AGENTS-77a3")


def _sentinel_run(tmp_path, monkeypatch, production, b):
    with monkeypatch.context() as mp:      # every env/attr change is undone when this arm ends
        return _sentinel_run_inner(tmp_path, mp, production, b)


def _sentinel_run_inner(tmp_path, monkeypatch, production, b):
    """Real-HOME stand-in with instruction sentinels; production=True is the probe's configuration (bench
    HOME + the two switches + git init); False turns all three OFF (the positive control)."""
    fake_real = tmp_path / "realhome"
    (fake_real / ".opencode" / "agent").mkdir(parents=True)
    (fake_real / ".opencode" / "agent" / "build.md").write_text(SENTINELS[0])
    (fake_real / ".claude").mkdir(); (fake_real / ".claude" / "CLAUDE.md").write_text(SENTINELS[1])
    (fake_real / "AGENTS.md").write_text(SENTINELS[2])
    _Mock.bodies = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cfg = json.loads(SHIPPED.read_text())
        cfg["provider"]["mlx-local"]["options"]["baseURL"] = f"http://127.0.0.1:{srv.server_address[1]}/v1"
        src = tmp_path / "bench.json"; src.write_text(json.dumps(cfg))
        wd = fake_real / "wd"
        cfg_home = P._make_bench_config_home(wd, "r1", source=src)
        bench_home = wd / "opencode-probe" / "home"; state = bench_home / ".local" / "state"
        tmpd = wd / "opencode-probe" / "tmp-r1"
        for d in (state, tmpd):
            d.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("HOME", str(fake_real))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        if not production:
            monkeypatch.setattr(P, "SCAFFOLD_ENV_POLICY", {})
        env = P._opencode_env(tmp_path / "data", cfg_home, state, tmpd, bench_home if production else None)
        if not production:
            env["HOME"] = str(fake_real); env["XDG_CACHE_HOME"] = str(tmp_path / "cache")
        proj = wd / "scratch" / "item"; proj.mkdir(parents=True)
        if production:
            P._git_init_scratch(proj)
        P._write_seed_overlay(proj, MODEL, 5)
        P._run_opencode(MODEL, proj, "say hi", proj / "s.py", proj / "t.py", lambda w, t: (False, ""), "",
                        tick_s=300, hard_ceiling_s=170, poll_s=1.0, stall_ticks=50, loop_repeats=50,
                        pure=True, env=env, opencode_bin=str(b))
    finally:
        srv.shutdown()
    assert _Mock.bodies
    return json.dumps([m for body in _Mock.bodies for m in body.get("messages", [])])


def test_real_home_instruction_sentinels_never_reach_the_prompt_under_the_probe_configuration(tmp_path, monkeypatch):
    """With a POSITIVE control: the same scenario with the two switches, git init and the bench HOME all OFF
    must let a sentinel through, otherwise the negative result proves nothing."""
    b = _pinned_bin()                    # resolved BEFORE the test points HOME at the stand-in
    if b is None:
        pytest.skip("pinned opencode binary absent")
    (tmp_path / "pos").mkdir(); (tmp_path / "neg").mkdir()
    leaked = _sentinel_run(tmp_path / "pos", monkeypatch, production=False, b=b)
    assert [t for t in SENTINELS if t in leaked], "positive control failed: no sentinel reached the prompt"
    assert P.SCAFFOLD_ENV_POLICY["OPENCODE_DISABLE_CLAUDE_CODE_PROMPT"] == "true"   # positive arm's patch was undone
    clean = _sentinel_run(tmp_path / "neg", monkeypatch, production=True, b=b)
    assert not [t for t in SENTINELS if t in clean]


def test_m55_report_counts_grade_excluded_rows_separately(tmp_path):
    """E10: the M55 report script (outside the repo) must not crash on `passed: null` rows."""
    from bench import paths
    wd = paths.resolve_stack_workdir(required=False)
    script = (wd / "m55" / "m55_report.py") if wd else None
    if script is None or not script.is_file():
        pytest.skip("m55_report.py not present under $STACK_WORKDIR/m55")
    src = script.read_text()
    import re
    src = re.sub(r'^M = ".*"$', f'M = {str(tmp_path)!r}', src, flags=re.M)
    models = re.search(r"^MODELS = (\[.*\])$", src, re.M).group(1)
    for sess in ("s1", "s2"):
        (tmp_path / sess).mkdir()
        for m in eval(models):
            for lang in ("rust", "java", "javascript"):
                rows = [{"id": f"{lang}/x{i}", "passed": (None if i == 0 else i % 2 == 0), "stop_reason": "completed",
                         "wall_s": 1.0, "log_tail": "", "test_modified": False} for i in range(22)]
                (tmp_path / sess / f"{m}.opencode_{lang}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = tmp_path / "report.md"
    r = subprocess.run([sys.executable, "-c", f"import sys; sys.argv=['x', {str(out)!r}]; exec(compile({src!r}, 'm55_report', 'exec'))"],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-600:]
    assert "excl" in out.read_text()


# ------------------------------------------------------------------ round 5
def test_the_opt_in_receipt_branch_writes_a_readable_receipt(monkeypatch, tmp_path):
    b, cfg, tf = _receipt_env(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENCODE_PROBE_RECORD_VERIFIED", "1")
    monkeypatch.setenv("OPENCODE_PROBE_RECEIPT", str(tmp_path / "receipt.json"))
    assert P._seed_runtime(7)["seed_propagation"] == "unverified"
    _maybe_stamp_receipt(b)
    assert (tmp_path / "receipt.json").is_file()
    assert P._seed_runtime(7)["seed_propagation"] == "verified-by-test"
    monkeypatch.delenv("OPENCODE_PROBE_RECORD_VERIFIED")
    (tmp_path / "receipt.json").unlink()
    _maybe_stamp_receipt(b)                       # not opted in: nothing written
    assert not (tmp_path / "receipt.json").exists()


def test_cache_bin_inventory_hash_tracks_files_under_the_shared_cache(tmp_path):
    cache = tmp_path / "cache"; (cache / "opencode" / "bin").mkdir(parents=True)
    (cache / "opencode" / "bin" / "rg").write_text("ripgrep-1")
    h1 = P._cache_bin_inventory_sha256(cache)
    assert h1 == P._cache_bin_inventory_sha256(cache)
    (cache / "opencode" / "bin" / "lsp-server").write_text("x")          # a new tool appears
    h2 = P._cache_bin_inventory_sha256(cache)
    assert h2 != h1
    (cache / "opencode" / "bin" / "rg").write_text("ripgrep-2")           # same size, different content
    assert P._cache_bin_inventory_sha256(cache) != h2
    (cache / "opencode" / "models.json").write_text("{}")                 # the catalogue is NOT inventoried
    h3 = P._cache_bin_inventory_sha256(cache)
    (cache / "opencode" / "models.json").write_text('{"a": 1}')
    assert P._cache_bin_inventory_sha256(cache) == h3
    assert P._cache_bin_inventory_sha256(tmp_path / "absent") == P._cache_bin_inventory_sha256(tmp_path / "absent2")


def test_no_pure_flag_is_gone(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["p", "--model", "m", "--items", "x", "--seed-base", "1", "--no-pure"])
    with pytest.raises(SystemExit) as e:
        P.main()
    assert e.value.code == 2


def test_error_strings_are_pii_scrubbed_before_truncation(monkeypatch, tmp_path):
    home = str(Path.home())
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))
    monkeypatch.setattr(P, "_login_name", lambda: "someoperator")
    msg = "x" * 5 + f" failed in {home}/ws/scratch/oc-1/ex as someoperator ({home}/.cache/opencode)"
    out = P._scrub_error(msg, limit=40)
    assert home not in out and "someoperator" not in out
    # a cut through the home prefix cannot leave a partial prefix: scrub the whole text first, then cut
    cut = P._scrub_error("a" * 20 + home + "/deep/path", limit=len("a" * 20) + 6)
    assert home not in cut and "$HOME" in cut[:30]


def test_resume_check_runs_for_a_manifest_without_rows_and_refuses_a_drift_stamp(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"
    _prior(OP, out, [], doc_extra={"served_config_drift": {"error": "router changed"}})
    with pytest.raises(SystemExit, match="served_config_drift"):
        _resume_main(OP, monkeypatch, out)


@pytest.mark.parametrize("tail,needle", [('{"id": "python/x", "sam', "line 2"),
                                         ('{"id": "python/x", "sample": 0}', "unterminated"),
                                         ('not json\n', "line 2")])
def test_resume_refuses_a_corrupt_row_file_naming_the_line(tmp_path, monkeypatch, _stub_bin, tail, needle):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    out = tmp_path / "oc.jsonl"; _prior(OP, out, [ROW])
    out.write_text(out.read_text() + tail)
    with pytest.raises(SystemExit, match=needle):
        _resume_main(OP, monkeypatch, out)


def test_failed_run_dir_creation_leaves_nothing_behind(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    monkeypatch.setattr(OP, "BENCH_OPENCODE_CONFIG", tmp_path / "missing-carrier.json")
    with pytest.raises(Exception):
        _resume_main(OP, monkeypatch, tmp_path / "oc.jsonl")
    left = [p.name for p in (tmp_path / "opencode-probe").iterdir()] if (tmp_path / "opencode-probe").exists() else []
    assert not [n for n in left if n.startswith(("config-", "tmp-"))], left
    with pytest.raises(Exception):                       # and directly, without main()'s cleanup
        OP._make_run_dirs(tmp_path, "direct")
    assert not (tmp_path / "opencode-probe" / "config-direct").exists()
    assert not (tmp_path / "opencode-probe" / "tmp-direct").exists()


# ------------------------------------------------------------------ round 6
def test_provenance_scrubs_complete_stderr_before_taking_the_tail(monkeypatch, tmp_path):
    """E1: sweep every cut position of a home path + login through the 300-char tail."""
    monkeypatch.setattr(provenance, "_login_name", lambda: "zqxloginname")
    home = str(Path.home())
    secret = f"{home}/ws/zqxloginname/scratch"
    for j in range(len(secret) + 2):
        stderr = "y" * 400 + secret + "z" * (300 - j)
        monkeypatch.setattr(subprocess, "run",
                            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 3, stdout="", stderr=stderr))
        with pytest.raises(provenance.ServedConfigError) as e:
            provenance.opencode_router_base(tmp_path, {}, opencode_bin="/x")
        m = str(e.value)
        assert "/Users/" not in m and home not in m and "zqxlogin" not in m and "loginname" not in m, (j, m[-120:])


def test_probe_overlay_check_scrubs_complete_stderr_before_the_tail(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))
    monkeypatch.setattr(P, "_login_name", lambda: "zqxloginname")
    home = str(Path.home())
    secret = f"{home}/ws/zqxloginname/scratch"
    for j in range(len(secret) + 2):
        stderr = "y" * 400 + secret + "z" * (200 - j if j < 200 else 0)
        monkeypatch.setattr(subprocess, "run",
                            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 3, stdout="", stderr=stderr))
        with pytest.raises(provenance.ServedConfigError) as e:
            P._assert_overlay_resolved(tmp_path, {}, MODEL, 9, "http://localhost:8000/v1", opencode_bin="/x")
        m = str(e.value)
        assert home not in m and "/Users/" not in m and "loginname" not in m, (j, m[-120:])


def test_manifest_drift_error_has_no_home_or_login_fragment_through_the_real_path(tmp_path, tmp_path_factory, monkeypatch):
    """E1 through main(): item 1 passes, then the destination `debug config` fails (nonzero) at item 2."""
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    monkeypatch.setattr(OP, "_opencode_version", _REAL_VERSION)
    monkeypatch.setattr(OP, "_login_name", lambda: "zqxloginname")
    monkeypatch.setattr(provenance, "_login_name", lambda: "zqxloginname")
    _add_exercise(tmp_path, "ex2"); _stub_full_item(OP, monkeypatch)
    home = str(Path.home())
    secret = f"{home}/ws/zqxloginname/scratch"
    d = tmp_path_factory.mktemp("failbin")
    (d / "stderr.txt").write_text("y" * 400 + secret + "z" * 290)       # the 300-char tail cuts through `secret`
    good = {"provider": {"mlx-local": {"options": {"baseURL": "http://localhost:8000/v1"}}}}
    (d / "good.json").write_text(json.dumps(good))
    b = _exe(d / "opencode", f"#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo 1.18.30; exit 0; fi\n"
                             f"echo x >> {d}/n\nif [ $(wc -l < {d}/n) -ge 3 ]; then cat {d}/stderr.txt >&2; exit 3; fi\n"
                             f"cat {d}/good.json\n")
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(b))
    out = tmp_path / "oc.jsonl"
    monkeypatch.setattr(sys, "argv", ["p", "--model", "m", "--items", "ex,ex2", "--seed-base", "1", "--out", str(out)])
    with pytest.raises(provenance.ServedConfigError):
        OP.main()
    text = out.with_suffix(".manifest.json").read_text()
    assert "served_config_drift" in text
    assert home not in text and "/Users/" not in text and "loginname" not in text


def test_tick_snapshots_are_confined_to_the_run_temp_dir(tmp_path):
    work = tmp_path / "work"; work.mkdir()
    sol = work / "sol.py"; test = work / "t.py"
    sol.write_text("before"); test.write_text("x"); log = work / "log.txt"; log.write_text("")
    runtmp = tmp_path / "runtmp"; runtmp.mkdir()
    seen = []

    def grade(w, t):
        seen.append(Path(w)); return True, ""
    snap = P._tick_snapshot_fn(work, sol, test, "before", grade, log, tmp_dir=runtmp)
    sol.write_text("after")
    snap(1.0)
    assert seen and str(seen[0]).startswith(str(runtmp)), seen


def test_run_opencode_passes_its_env_tmpdir_to_the_tick_snapshots(monkeypatch, tmp_path):
    got = {}
    real = P._tick_snapshot_fn

    class Boom(Exception):
        pass

    def spy(*a, **k):
        got["tmp_dir"] = k.get("tmp_dir")
        raise Boom()
    monkeypatch.setattr(P, "_tick_snapshot_fn", spy)
    monkeypatch.setattr(P.subprocess, "Popen", lambda *a, **k: type("X", (), {"returncode": 0, "poll": lambda self: 0})())
    work = tmp_path / "w"; work.mkdir(); (work / "s.py").write_text("a"); (work / "t.py").write_text("b")
    with pytest.raises(Boom):
        P._run_opencode(MODEL, work, "p", work / "s.py", work / "t.py", lambda w, t: (False, ""), "a",
                        tick_s=1, hard_ceiling_s=1, poll_s=1, stall_ticks=1, loop_repeats=1, pure=True,
                        env={"TMPDIR": str(tmp_path / "rt")}, opencode_bin="/x")
    assert got["tmp_dir"] == str(tmp_path / "rt")


@pytest.mark.parametrize("mutate", [False, True])
def test_cache_mutation_during_an_item_flags_the_row_and_the_manifest(tmp_path, monkeypatch, _stub_bin, mutate):
    cache = tmp_path / "xdgcache"; (cache / "opencode" / "bin").mkdir(parents=True)
    (cache / "opencode" / "bin" / "rg").write_text("rg-1")
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    seen = _stub_full_item(OP, monkeypatch)
    inner = OP._run_opencode

    def run(*a, **k):
        if mutate:
            (cache / "opencode" / "bin" / "lsp").write_text("installed lazily during the item")
        return inner(*a, **k)
    monkeypatch.setattr(OP, "_run_opencode", run)
    out = tmp_path / "oc.jsonl"
    assert _resume_main(OP, monkeypatch, out) == 0
    row = json.loads(out.read_text().splitlines()[-1])
    man = json.loads(out.with_suffix(".manifest.json").read_text())
    assert row["cache_drift"] is mutate
    if mutate:
        d = man["cache_bin_inventory_drift"]
        assert d["observed"] != d["entry"] and d["item"] == "python/ex" and d["entry"] == man["runtime"]["cache_bin_inventory_sha256"]
    else:
        assert "cache_bin_inventory_drift" not in man


# ------------------------------------------------------------------ round 6b: bench HOME is load-bearing
@pytest.mark.parametrize("planted", [".opencode", "AGENTS.md", "CLAUDE.md", ".claude"])
def test_bench_home_must_stay_clean(tmp_path, planted):
    home = tmp_path / "home"; home.mkdir()
    P._assert_bench_home_clean(home)                       # clean passes
    (home / planted).mkdir() if planted.startswith(".") else (home / planted).write_text("x")
    with pytest.raises(SystemExit, match=planted.replace(".", r"\.")):
        P._assert_bench_home_clean(home)


def test_sentinel_planted_between_items_refuses_the_second_item(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    _add_exercise(tmp_path, "ex2")
    seen = _stub_full_item(OP, monkeypatch)
    inner = OP._run_opencode

    def run(*a, **k):
        (tmp_path / "opencode-probe" / "home" / ".opencode" / "agent").mkdir(parents=True, exist_ok=True)   # the "model" plants it
        (tmp_path / "opencode-probe" / "home" / ".opencode" / "agent" / "build.md").write_text("SENTINEL")
        return inner(*a, **k)
    monkeypatch.setattr(OP, "_run_opencode", run)
    out = tmp_path / "oc.jsonl"
    with pytest.raises(SystemExit, match=r"\.opencode"):
        _resume_main(OP, monkeypatch, out, items="ex,ex2")
    assert seen["runs"] == 1                                 # item 2 never ran
    man = json.loads(out.with_suffix(".manifest.json").read_text())
    assert man["runtime"]["bench_home_clean"] is True       # as of the run start


def test_a_modified_per_run_config_copy_refuses_the_next_item(tmp_path, monkeypatch, _stub_bin):
    OP = _oc_probe_setup(tmp_path, monkeypatch, pid=5)
    _add_exercise(tmp_path, "ex2")
    _stub_full_item(OP, monkeypatch)
    inner = OP._run_opencode

    def run(*a, **k):
        for p in (tmp_path / "opencode-probe").glob("config-*/opencode/opencode.json"):
            p.write_text("{}")
        return inner(*a, **k)
    monkeypatch.setattr(OP, "_run_opencode", run)
    with pytest.raises(SystemExit, match="config copy"):
        _resume_main(OP, monkeypatch, tmp_path / "oc.jsonl", items="ex,ex2")
