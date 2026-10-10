"""C147 chain_ops: tripwires on fake ps/lsof/pmset/HTTP, validate_leg failure reasons, arithmetic, idle predicate."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from bench import chain_ops as co
from bench import rowschema

REPO = Path(__file__).resolve().parents[3]
OVERLAY = "/wd/c147/overlay.yaml"
PICK1, PICK2 = co.PICK1, co.PICK2


def _fake_probe():
    spec = importlib.util.spec_from_file_location("fake_probe", REPO / "benchmark/chains/c147/fake_probe.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


AC_OK = " Wattage = 140W\n Current = 4990mA\n Voltage = 28000mV\n"
BATT = "Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t85%; charging; 1:00 remaining\n"


class Sh:
    """Scriptable ps/lsof/pmset/vm_stat. `rules` is a list of (predicate(cmd), result)."""

    def __init__(self, tmp_path):
        self.calls = []
        self.ac, self.batt = AC_OK, BATT
        self.orphans = "no orphaned shells\n"
        self.listen = ""
        self.ps = ""
        self.env = f"/usr/bin/mlx-serve start MLX_SERVE_CONFIG={OVERLAY} MLX_VLM_CACHE_SESSION_MAX=1 HOME=/x"
        self.cwd = "p1\nn/repo\n"
        self.gate_rc, self.gate_receipt, self.gate_timeout = 0, {"pass": True, "run_id": "r"}, False
        self.receipt = tmp_path / "session_gate/a4_v2_latest.json"

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        s = " ".join(cmd) if isinstance(cmd, list) else cmd
        if "pmset -g ac" in s:
            return co.Result(self.ac)
        if "pmset -g batt" in s:
            return co.Result(self.batt)
        if "sweep_orphan" in s:
            return co.Result(self.orphans)
        if s.startswith("lsof") and "cwd" in s:
            return co.Result(self.cwd)
        if s.startswith("lsof"):
            return co.Result(self.listen)
        if s.startswith("ps -axo pid=,command=") or s.startswith("ps -axo pid=,uid="):
            return co.Result(self.ps)
        if s.startswith("ps -o command= -E"):
            return co.Result(self.env)
        if s.startswith("vm_stat"):
            return co.Result("Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 1000.\n"
                             "Pages speculative: 24.\n")
        if "session_pinning_gate" in s:
            if self.gate_timeout:
                raise subprocess.TimeoutExpired(cmd, 1)
            self.receipt.parent.mkdir(parents=True, exist_ok=True)
            if self.gate_receipt is not None:
                self.receipt.write_text(json.dumps(self.gate_receipt))
            return co.Result("gate out", "", self.gate_rc)
        if "stack_stop" in s:
            return co.Result("stack_stop: :8000 free", "", 0)
        return co.Result("", "", 0)


@pytest.fixture
def ops(tmp_path):
    sh = Sh(tmp_path)
    lines = []
    log = co.RunLog(tmp_path / "RUNLOG.md", out=lines.append)
    http_calls = []

    def http(path, body=None, timeout=900):
        http_calls.append((path, body))
        return b"{}"

    o = co.ChainOps("/repo", tmp_path, OVERLAY, log, sh=sh, http=http, popen=lambda *a, **k: None,
                    sleep=lambda s: None, create_time=lambda pid: 1234.5, env_source={"HOME": "/h", "APC_ENABLED": "1"})
    o._sh, o._lines, o._http_calls = sh, lines, http_calls
    return o


# --------------------------------------------------------------------------- env / power
def test_env_base_tripwires(ops, tmp_path):
    env = ops.env_base()
    assert "APC_ENABLED" not in env
    assert env["MLX_VLM_CACHE_SESSION_MAX"] == "1" and env["MLX_SERVE_CONFIG"] == OVERLAY
    assert env["STACK_WORKDIR"] == str(tmp_path) and env["TMPDIR"].startswith(str(tmp_path))


@pytest.mark.parametrize("mut,ok", [
    ({}, True),
    ({"ac": " Wattage = 100W\n Voltage = 28000mV\n"}, False),
    ({"ac": " Wattage = 140W\n Voltage = 20000mV\n"}, False),
    ({"ac": " Wattage = 140W\n"}, False),
    ({"batt": " -InternalBattery-0\t20%; charging\n"}, False),
    ({"batt": " -InternalBattery-0\t21%; charging\n"}, True),
    ({"batt": ""}, False),
    ({"orphans": "3 orphaned shells\n"}, False),
])
def test_power_ok(ops, mut, ok):
    for k, v in mut.items():
        setattr(ops._sh, k, v)
    assert ops.power_ok() is ok


def test_start_state_reports_everything(ops):
    ops._sh.ps = "10 mlx_vlm.server --model x\n"
    st = ops.start_state()
    assert (st["watts"], st["volts"], st["batt"], st["free_mem_mb"]) == (140, 28, 85, 16)
    assert st["busy"] == ["10 mlx_vlm.server --model x"] and st["orphans_clean"] is True


def test_listeners_and_busy_procs_exclude_self(ops):
    ops._sh.listen = "p42\nf9\np42\np7\n"
    assert ops.listeners() == [7, 42]
    ops._sh.ps = "5 python run_tg1_chain.py pilot\n6 opencode run x\n7 sleep 1\n"
    assert ops.busy_procs() == ["6 opencode run x"]


# --------------------------------------------------------------------------- start_router
def test_start_router_ok_and_refusals(ops):
    ops._sh.listen = "p9\n"
    with pytest.raises(co.ChainAbort, match="already bound"):
        ops.start_router()
    ops._sh.listen = ""
    ops._sh.ps = "6 opencode run x\n"
    with pytest.raises(co.ChainAbort, match="busy"):
        ops.start_router()


def _router_ops(ops, env=None, cwd=None):
    ops._sh.ps = ""
    state = {"n": 0}
    orig = ops.listeners

    def listeners(port=8000):
        state["n"] += 1
        return [] if state["n"] == 1 else [99]
    ops.listeners = listeners
    ops.repo = Path("/repo")
    ops.popen = lambda *a, **k: None
    if env is not None:
        ops._sh.env = env
    if cwd is not None:
        ops._sh.cwd = cwd
    return orig


def test_start_router_passes_with_good_env(ops, tmp_path):
    _router_ops(ops)
    ops.repo = tmp_path
    (tmp_path / "logs").mkdir()
    ops._sh.cwd = f"p99\nn{tmp_path}\n"
    assert ops.start_router() == 99


@pytest.mark.parametrize("env,cwd,frag", [
    ("/usr/bin/other MLX_SERVE_CONFIG=%s MLX_VLM_CACHE_SESSION_MAX=1" % OVERLAY, None, "not mlx-serve"),
    ("mlx-serve MLX_SERVE_CONFIG=/other MLX_VLM_CACHE_SESSION_MAX=1", None, "MLX_SERVE_CONFIG"),
    ("mlx-serve MLX_SERVE_CONFIG=%s MLX_VLM_CACHE_SESSION_MAX=2" % OVERLAY, None, "SESSION_MAX"),
    ("mlx-serve MLX_SERVE_CONFIG=%s MLX_VLM_CACHE_SESSION_MAX=1 APC_ENABLED=1" % OVERLAY, None, "APC_ENABLED"),
    (None, "p99\nn/elsewhere\n", "cwd"),
])
def test_start_router_tripwires(ops, tmp_path, env, cwd, frag):
    _router_ops(ops, env, cwd)
    ops.repo = tmp_path
    (tmp_path / "logs").mkdir()
    if cwd is None:
        ops._sh.cwd = f"p99\nn{tmp_path}\n"
    with pytest.raises(co.ChainAbort, match=frag):
        ops.start_router()


def test_start_router_two_listeners(ops, tmp_path):
    ops.repo = tmp_path
    (tmp_path / "logs").mkdir()
    state = {"n": 0}

    def listeners(port=8000):
        state["n"] += 1
        return [] if state["n"] == 1 else [1, 2]
    ops.listeners = listeners
    with pytest.raises(co.ChainAbort, match="one :8000 listener"):
        ops.start_router()


# --------------------------------------------------------------------------- load / unload
def _worker_ps(model, extra=""):
    return f"501 /py -m mlx_vlm.server --model caslca/{model} --port 8091 {extra}\n77 uv run mlx_vlm.server {model}\n"


def test_load_verifies_single_worker_env_and_records_cmdline(ops):
    ops._sh.ps = _worker_ps(PICK1)
    ident = ops.load(PICK1)
    assert ident["pid"] == 501 and ident["create_time"] == 1234.5 and "mlx_vlm.server" in ident["cmdline"]
    assert ops._http_calls[0][0] == "/v1/models/load"


@pytest.mark.parametrize("ps,env,frag", [
    ("", None, "found 0"),
    (_worker_ps(PICK1) + _worker_ps(PICK1).split("\n")[0].replace("501", "502") + "\n", None, "found 2"),
    (_worker_ps(PICK1, "--draft-kind mtp"), None, "predictor"),
    (_worker_ps(PICK1), "MLX_SERVE_CONFIG=/other MLX_VLM_CACHE_SESSION_MAX=1", "MLX_SERVE_CONFIG"),
    (_worker_ps(PICK1), "MLX_SERVE_CONFIG=%s MLX_VLM_CACHE_SESSION_MAX=1 APC_ENABLED=1" % OVERLAY, "APC_ENABLED"),
    (_worker_ps(PICK1), "MLX_SERVE_CONFIG=%s" % OVERLAY, "SESSION_MAX"),
])
def test_load_tripwires(ops, ps, env, frag):
    ops._sh.ps = ps
    if env:
        ops._sh.env = env
    with pytest.raises(co.ChainAbort, match=frag):
        ops.load(PICK1)


def test_load_accepts_draft_off(ops):
    ops._sh.ps = _worker_ps(PICK1, "--draft-kind off")
    assert ops.load(PICK1)["pid"] == 501


def test_unload_verified_termination(ops):
    ops._sh.ps = ""
    assert ops.unload(PICK1) is True
    ops._sh.ps = _worker_ps(PICK1)
    assert ops.unload(PICK1) is False
    assert any("FATAL" in line for line in ops._lines)


def test_worker_ident_and_metrics_unreadable(ops):
    ops._sh.ps = _worker_ps(PICK1)
    assert ops.worker_ident(PICK1) == {"pid": 501, "create_time": 1234.5}
    ops._sh.ps = ""
    assert ops.worker_ident(PICK1) is None


# --------------------------------------------------------------------------- A4 gate
def test_a4_gate_command_and_receipt(ops, tmp_path):
    ops.a4_gate(PICK1, "t")
    cmd = [c for c in ops._sh.calls if "session_pinning_gate" in " ".join(c)][0]
    for tok in ("--model", PICK1, "--opencode", "v2", "--scaffold", "opencode-v2-web-tg1", "--skip-owui", "--log"):
        assert tok in cmd
    assert cmd[cmd.index("--log") + 1].endswith("logs/mlx_vlm.log")


@pytest.mark.parametrize("receipt", [{"pass": False}, {"pass": "yes"}, {}, None])
def test_a4_gate_requires_pass_true(ops, receipt):
    ops._sh.gate_receipt = receipt
    with pytest.raises(co.ChainAbort, match="A4"):
        ops.a4_gate(PICK1, "t")


def test_a4_gate_timeout_is_chain_abort(ops):
    ops._sh.gate_timeout = True
    with pytest.raises(co.ChainAbort, match="timeout") as ei:
        ops.a4_gate(PICK1, "t")
    assert ei.value.code == 2


def test_a4_gate_rejects_stale_receipt(ops):
    ops._sh.gate_receipt = None
    ops._sh.receipt.parent.mkdir(parents=True)
    ops._sh.receipt.write_text(json.dumps({"pass": True}))
    import os
    os.utime(ops._sh.receipt, (1, 1))
    with pytest.raises(co.ChainAbort, match="fresh=False"):
        ops.a4_gate(PICK1, "t")


def test_leftovers_listed_not_killed(ops):
    ops._sh.ps = f"12 {__import__('os').getuid()} /bin/sleep /scratch/root/x\n13 0 /bin/sleep /scratch/root/y\n"
    out = ops.leftovers(["/scratch/root"], ["run1"])
    assert len(out) == 1 and "12" in out[0]
    assert not any(c[0] == "kill" for c in ops._sh.calls if isinstance(c, list))


def test_make_overlay_strips_draft_fields(tmp_path):
    src = tmp_path / "r.yaml"
    src.write_text("mlx_port: 8091\nmodels:\n- name: a\n  draft_kind: mtp\n  draft_block_size: 4\n"
                   "  moe_expand: 1\n  mtp_verify_scan: true\n  keep: 1\n")
    dst = co.make_overlay(src, tmp_path / "o" / "ov.yaml")
    import yaml
    d = yaml.safe_load(Path(dst).read_text())
    assert d["models"][0] == {"name": "a", "keep": 1} and d["mlx_port"] == 8091


def test_runlog_utc_and_append(tmp_path):
    lines = []
    log = co.RunLog(tmp_path / "d" / "RUNLOG.md", out=lines.append, clock=lambda: 0)
    log("hello")
    log("again")
    assert lines[0] == "1970-01-01T00:00:00Z hello"
    assert (tmp_path / "d/RUNLOG.md").read_text() == "- 1970-01-01T00:00:00Z hello\n- 1970-01-01T00:00:00Z again\n"


# --------------------------------------------------------------------------- arithmetic
def test_alarm_arithmetic():
    assert co.alarm_s(10, 100, 200) == 7200            # floor
    assert co.alarm_s(22, 400, 900) == 2 * 22 * 400 + 2700
    assert co.alarm_s(0, 400, 100) == 7200


def test_t_coop_formula():
    base = 5 + 660 + 120 + 60 + 20
    assert co.t_coop(0, "python") == base + 300 + 300
    assert co.t_coop(0, "go") == base + 300 + 180
    assert co.t_coop(150000, "python") == base + 500 + 300      # prompt/300 exceeds the 300 s floor
    assert co.t_coop(60000, "go") == base + 300 + 180


# --------------------------------------------------------------------------- idle predicate
def _s(p, t, **kw):
    d = dict(hb_age=1000, events_bytes=10, rows_sig=(1, 1), metrics={"summary": {"in_flight": 0}}, ident=(5, 1.0))
    d.update(kw)
    return p.sample(t, **d)


def test_idle_three_samples_then_recheck():
    p = co.IdlePredicate(spacing_s=60)
    assert not _s(p, 0) and not _s(p, 60)
    assert _s(p, 120)
    assert p.recheck(hb_age=1000, events_bytes=10, rows_sig=(1, 1), metrics={"summary": {"in_flight": 0}}, ident=(5, 1.0))


def test_idle_spacing_enforced():
    p = co.IdlePredicate(spacing_s=60)
    for t in (0, 10, 20, 30, 59):
        assert not _s(p, t)
    assert p.count == 1


@pytest.mark.parametrize("kw", [
    dict(hb_age=100),                                   # fresh heartbeat
    dict(hb_age=900),                                   # not strictly greater
    dict(metrics={"summary": {"in_flight": 1}}),        # busy never cancels
    dict(metrics=None),                                 # unreadable never counts
    dict(metrics={"summary": {}}),                      # malformed
    dict(ident=None),
])
def test_idle_never_when_condition_fails(kw):
    p = co.IdlePredicate(spacing_s=1)
    assert not any(_s(p, t, **kw) for t in range(0, 20))


def test_stale_heartbeat_with_growing_events_never_cancels():
    p = co.IdlePredicate(spacing_s=1)
    assert not any(_s(p, t, events_bytes=10 + t) for t in range(0, 30))


@pytest.mark.parametrize("field,vals", [("rows_sig", [(1, 1), (2, 2)]), ("ident", [(5, 1.0), (6, 2.0)]),
                                        ("events_bytes", [10, 11])])
def test_idle_change_resets(field, vals):
    p = co.IdlePredicate(spacing_s=1)
    _s(p, 0), _s(p, 1)
    assert p.count == 2
    _s(p, 2, **{field: vals[1]})
    assert p.count == 0
    _s(p, 3, **{field: vals[1]})
    assert p.count == 1


def test_recheck_resets_when_activity_resumed():
    p = co.IdlePredicate(spacing_s=1)
    _s(p, 0), _s(p, 1)
    assert _s(p, 2)
    assert not p.recheck(hb_age=1000, events_bytes=99, rows_sig=(1, 1), metrics={"summary": {"in_flight": 0}}, ident=(5, 1.0))
    assert p.count == 0
    assert not p.recheck(hb_age=1000, events_bytes=99, rows_sig=(1, 1), metrics={"summary": {"in_flight": 0}}, ident=(5, 1.0))


# --------------------------------------------------------------------------- validate_leg
@pytest.fixture
def leg_env(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    fp = _fake_probe()
    ids = ["python/alpha", "python/beta"]
    out = tmp_path / "c147/s1" / f"{PICK1}.s1.opencode_python.jsonl"
    worker = {"pid": 4242, "create_time": 1700000000.5, "model_path": "caslca/" + PICK1,
              "registry_sha256": "a" * 64}
    pinned = {"scaffold_policy_sha256": co.CAMPAIGN_POLICY_SHA, "probe_code_sha256": "p" * 64,
              "serving_path": "sp1", "registry_sha256": "a" * 64}
    fp.write_leg(out, PICK1, "python", 1001, ids, worker, tmp_path)
    leg = dict(session="s1", model=PICK1, lang="python", seed_base=1001, expected_ids=ids, out=str(out), rc=0)
    return leg, pinned, out, fp, tmp_path


def _mut_rows(out, fn):
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    for r in rows:
        fn(r)
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _mut_man(out, fn):
    mp = out.with_suffix(".manifest.json")
    m = json.loads(mp.read_text())
    fn(m)
    mp.write_text(json.dumps(m))


def test_validate_passes_on_complete_fixture(leg_env):
    leg, pinned, out, fp, wd = leg_env
    assert co.validate_leg(leg, pinned, wd) == []


def _codes(why):
    return {w.split(":")[0] for w in why}


def test_validate_rc(leg_env):
    leg, pinned, out, fp, wd = leg_env
    assert "rc_nonzero" in _codes(co.validate_leg({**leg, "rc": 1}, pinned, wd))
    assert "rc_nonzero" in _codes(co.validate_leg({**leg, "rc": None}, pinned, wd))


def test_validate_torn_rows(leg_env):
    leg, pinned, out, fp, wd = leg_env
    out.write_bytes(out.read_bytes()[:-5])
    assert "rows_torn" in _codes(co.validate_leg(leg, pinned, wd))


def test_validate_ids(leg_env):
    leg, pinned, out, fp, wd = leg_env
    assert "ids_mismatch" in _codes(co.validate_leg({**leg, "expected_ids": leg["expected_ids"] + ["python/gamma"]}, pinned, wd))
    assert "ids_mismatch" in _codes(co.validate_leg({**leg, "expected_ids": leg["expected_ids"][:1]}, pinned, wd))


def test_validate_manifest_missing_and_abort_and_drift(leg_env):
    leg, pinned, out, fp, wd = leg_env
    _mut_man(out, lambda m: m.update(transport_abort={"error": "x"}))
    assert "manifest_abort" in _codes(co.validate_leg(leg, pinned, wd))
    _mut_man(out, lambda m: (m.pop("transport_abort"), m.update(served_config_drift={"error": "x"})))
    assert "served_config_drift" in _codes(co.validate_leg(leg, pinned, wd))
    out.with_suffix(".manifest.json").unlink()
    assert "manifest_missing" in _codes(co.validate_leg(leg, pinned, wd))


@pytest.mark.parametrize("path,value,code", [
    (("runtime", "seed_base"), 7, "runtime_seed_base"),
    (("runtime", "lang"), "go", "runtime_lang"),
    (("model",), "other", "manifest_model"),
    (("runtime", "scaffold"), "opencode-v2-web", "runtime_scaffold"),
    (("runtime", "scaffold_policy_sha256"), "0" * 64, "runtime_scaffold_policy_sha256"),
    (("runtime", "probe_code_sha256"), "q" * 64, "runtime_probe_code_sha256"),   # differing build, equal policy hash
    (("runtime", "draft_kind"), "mtp", "runtime_draft_kind"),
    (("runtime", "sampling_profile"), "production", "runtime_sampling_profile"),
    (("runtime", "opencode_version"), "2.0.21", "runtime_opencode_version"),
    (("runtime", "opencode_exe_sha256"), "z", "runtime_opencode_exe_sha256"),
    (("runtime", "polyglot_sha"), "z", "runtime_polyglot_sha"),
    (("runtime", "universe_sha256"), "z", "runtime_universe_sha256"),
    (("runtime", "carrier_source_sha256"), "z", "runtime_carrier_source_sha256"),
    (("runtime", "agent_system_sha256"), "z", "runtime_agent_system_sha256"),
    (("runtime", "opencode_bench_config_sha256"), "z", "runtime_opencode_bench_config_sha256"),
    (("git", "serving_path"), "sp2", "serving_path"),
    (("registry", "sha256"), "b" * 64, "registry_sha256"),
])
def test_validate_manifest_fields(leg_env, path, value, code):
    leg, pinned, out, fp, wd = leg_env
    full_pinned = {**pinned, **{k: co.validate_leg and json.loads(out.with_suffix(".manifest.json").read_text())["runtime"][k]
                                for k in co.RUNTIME_PINNED if k not in pinned}}

    def mut(m):
        d = m
        for k in path[:-1]:
            d = d[k]
        d[path[-1]] = value
    assert co.validate_leg(leg, full_pinned, wd) == []
    _mut_man(out, mut)
    assert code in _codes(co.validate_leg(leg, full_pinned, wd))


def test_validate_pinned_incomplete(leg_env):
    leg, pinned, out, fp, wd = leg_env
    assert "pinned_incomplete" in _codes(co.validate_leg(leg, {**pinned, "probe_code_sha256": None}, wd))


def test_validate_row_sample_and_seed_and_overlay(leg_env):
    leg, pinned, out, fp, wd = leg_env
    _mut_rows(out, lambda r: r.update(sample=1))
    assert "row_sample" in _codes(co.validate_leg(leg, pinned, wd))
    fp.write_leg(out, PICK1, "python", 1001, leg["expected_ids"], json.loads(out.with_suffix(".manifest.json").read_text())["worker"], wd)
    _mut_rows(out, lambda r: r.update(sample_seed=rowschema.sample_seed(r["id"], 0, 2002)))
    assert "row_sample_seed" in _codes(co.validate_leg(leg, pinned, wd))
    fp.write_leg(out, PICK1, "python", 1001, leg["expected_ids"], json.loads(out.with_suffix(".manifest.json").read_text())["worker"], wd)
    _mut_rows(out, lambda r: r.update(overlay_sha256="0" * 64))
    assert "row_overlay_sha" in _codes(co.validate_leg(leg, pinned, wd))


def test_validate_overlay_sha_missing_fails(leg_env):
    leg, pinned, out, fp, wd = leg_env
    _mut_rows(out, lambda r: r.pop("overlay_sha256", None))
    assert "row_overlay_sha" in _codes(co.validate_leg(leg, pinned, wd))


def test_validate_row_scaffold_and_model(leg_env):
    leg, pinned, out, fp, wd = leg_env
    _mut_rows(out, lambda r: r.update(scaffold="opencode-v2-web-tg1-inject:stall"))
    assert "row_scaffold" in _codes(co.validate_leg(leg, pinned, wd))
    worker = json.loads(out.with_suffix(".manifest.json").read_text())["worker"]
    fp.write_leg(out, PICK1, "python", 1001, leg["expected_ids"], worker, wd)
    _mut_rows(out, lambda r: r.update(model=PICK2))
    assert "row_model" in _codes(co.validate_leg(leg, pinned, wd))
    fp.write_leg(out, PICK1, "python", 1001, leg["expected_ids"], worker, wd)
    _mut_rows(out, lambda r: r.pop("scaffold"))
    assert "row_scaffold" in _codes(co.validate_leg(leg, pinned, wd))


def test_validate_final_receipt_without_artifacts_fails(leg_env):
    leg, pinned, out, fp, wd = leg_env
    _mut_rows(out, lambda r: r["grade_reports"][-1].update(artifacts={}))
    assert "report_artifacts_empty" in _codes(co.validate_leg(leg, pinned, wd))


def test_validate_tampered_receipt_only_when_test_modified(leg_env):
    leg, pinned, out, fp, wd = leg_env
    tamper = {"boundary": 9, "seq": 9, "final": True, "outcome": "tampered", "artifacts": {}}
    _mut_rows(out, lambda r: (r.update(test_modified=True), r["grade_reports"].append(tamper)))
    assert co.validate_leg(leg, pinned, wd) == []
    _mut_rows(out, lambda r: r.update(test_modified=False))
    assert "report_artifacts_empty" in _codes(co.validate_leg(leg, pinned, wd))
    _mut_rows(out, lambda r: r.pop("test_modified"))
    assert "report_artifacts_empty" in _codes(co.validate_leg(leg, pinned, wd))
    _mut_rows(out, lambda r: (r.update(test_modified=True), r["grade_reports"][-1].update(outcome="parsed")))
    assert "report_artifacts_empty" in _codes(co.validate_leg(leg, pinned, wd))


@pytest.mark.parametrize("bad", [
    {"pid": "12", "create_time": 1.0, "model_path": "m", "registry_sha256": "a" * 64},
    {"pid": 12, "create_time": "x", "model_path": "m", "registry_sha256": "a" * 64},
    {"pid": 12, "create_time": 1.0, "model_path": "", "registry_sha256": "a" * 64},
    {"pid": 12, "create_time": 1.0, "model_path": "m", "registry_sha256": "short"},
    {"pid": True, "create_time": 1.0, "model_path": "m", "registry_sha256": "a" * 64},
    None,
])
def test_validate_untyped_worker(leg_env, bad):
    leg, pinned, out, fp, wd = leg_env
    _mut_rows(out, lambda r: r.update(worker_before=bad))
    assert "worker_untyped" in _codes(co.validate_leg(leg, pinned, wd))


def test_validate_untyped_manifest_worker(leg_env):
    leg, pinned, out, fp, wd = leg_env
    _mut_man(out, lambda m: m.update(worker={"pid": "1"}))
    assert "worker_untyped" in _codes(co.validate_leg(leg, pinned, wd))


def test_validate_worker_mismatch_rows_vs_manifest(leg_env):
    leg, pinned, out, fp, wd = leg_env
    _mut_rows(out, lambda r: r["worker_after"].update(pid=9999))
    assert "worker_mismatch" in _codes(co.validate_leg(leg, pinned, wd))


def test_validate_empty_evidence_sha_and_mismatch(leg_env):
    leg, pinned, out, fp, wd = leg_env
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    _mut_rows(out, lambda r: r["evidence_sha256"].update(events=""))
    assert "evidence_sha_missing" in _codes(co.validate_leg(leg, pinned, wd))
    _mut_rows(out, lambda r: r["evidence_sha256"].pop("export"))
    assert "evidence_sha_missing" in _codes(co.validate_leg(leg, pinned, wd))
    fp.write_leg(out, PICK1, "python", 1001, leg["expected_ids"], json.loads(out.with_suffix(".manifest.json").read_text())["worker"], wd)
    ev = resolve = co.resolve_portable(rows[0]["events_path"], wd)
    ev.write_bytes(ev.read_bytes() + b"tamper")
    assert "evidence_sha_mismatch" in _codes(co.validate_leg(leg, pinned, wd))


def test_validate_grade_report_missing_and_sha(leg_env):
    leg, pinned, out, fp, wd = leg_env
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    art = next(iter(rows[0]["grade_reports"][0]["artifacts"].values()))
    p = co.resolve_portable(art["path"], wd)
    p.write_bytes(p.read_bytes() + b"x")
    assert "report_sha_mismatch" in _codes(co.validate_leg(leg, pinned, wd))
    _mut_rows(out, lambda r: r["grade_reports"][0]["artifacts"][next(iter(r["grade_reports"][0]["artifacts"]))].update(sha256=""))
    assert "report_sha_missing" in _codes(co.validate_leg(leg, pinned, wd))
    _mut_rows(out, lambda r: r.update(grade_reports=[]))
    assert "grade_reports_missing" in _codes(co.validate_leg(leg, pinned, wd))


def test_seed_overlay_sha_matches_probe_recipe():
    ov = {"providers": {"mlx-local": {"models": {PICK1: {"body": {"seed": 5}}}}}}
    assert co.seed_overlay_sha(PICK1, 5) == hashlib.sha256(json.dumps(ov, sort_keys=True).encode()).hexdigest()


def test_campaign_hash_pinned():
    assert co.CAMPAIGN_POLICY_SHA == "ba86ba16e40e5e7b3535d64de2de9e95b323158049358b1f41b2ed26a83bb15c"


# --------------------------------------------------------------------------- teardown ownership (Q1)
class _Proc:
    pid = 55


def _own_router_ops(ops, tmp_path):
    ops.repo = tmp_path
    (tmp_path / "logs").mkdir(exist_ok=True)
    ops._sh.cwd = f"p99\nn{tmp_path}\n"
    ops.popen = lambda *a, **k: _Proc()
    killed, sent = set(), []
    state = {"n": 0}

    def listeners(port=8000):
        state["n"] += 1
        if state["n"] == 1:
            return []
        return [] if 99 in killed else [99]
    ops.listeners = listeners

    def create_time(pid):
        if pid in killed:
            raise ProcessLookupError(pid)
        return 1234.5
    ops.create_time = create_time

    def kill(pid, sig):
        sent.append((pid, sig))
        killed.add(pid)
    ops.kill = kill
    return sent, killed


def test_stop_stack_tears_down_only_own_router_and_never_runs_stack_stop(ops, tmp_path):
    import signal
    sent, _ = _own_router_ops(ops, tmp_path)
    assert ops.start_router() == 99
    assert ops.stop_stack() == 0
    assert (99, signal.SIGTERM) in sent and all(s == signal.SIGTERM for _, s in sent)
    assert {p for p, _ in sent} <= {99, 55}
    assert not any("stack_stop" in " ".join(c) for c in ops._sh.calls if isinstance(c, list))


def test_stop_stack_unloads_the_worker_we_loaded(ops, tmp_path):
    _own_router_ops(ops, tmp_path)
    ops.start_router()
    ops._sh.ps = _worker_ps(PICK1)
    ops.load(PICK1)
    ops._sh.ps = ""
    ops.stop_stack()
    assert ("/v1/models/unload", {"model": PICK1}) in ops._http_calls


def test_stop_stack_sigkills_only_recorded_pid_if_term_ignored(ops, tmp_path):
    import signal
    sent, killed = _own_router_ops(ops, tmp_path)
    ops.start_router()
    ops.kill = lambda pid, sig: (sent.append((pid, sig)), killed.add(pid) if sig == signal.SIGKILL else None)
    ops.stop_stack()
    assert (99, signal.SIGTERM) in sent and (99, signal.SIGKILL) in sent and {p for p, _ in sent} <= {99, 55}


def test_stop_stack_skips_pid_whose_create_time_changed(ops, tmp_path):
    sent, _ = _own_router_ops(ops, tmp_path)
    ops.start_router()
    ops.create_time = lambda pid: 999.0                    # pid reused by someone else
    ops.stop_stack()
    assert sent == []


def test_foreign_listener_refusal_then_stop_stack_does_nothing(ops):
    ops._sh.listen = "p9\n"
    sent = []
    ops.kill = lambda pid, sig: sent.append((pid, sig))
    with pytest.raises(co.ChainAbort, match="already bound"):
        ops.start_router()
    assert ops.stop_stack() is None
    assert sent == [] and not any("stack_stop" in " ".join(c) for c in ops._sh.calls if isinstance(c, list))
    assert not ops._http_calls
    assert any("NOTHING" in line for line in ops._lines)
