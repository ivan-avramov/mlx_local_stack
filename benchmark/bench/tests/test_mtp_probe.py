"""M6a MTP speed probe -- tests run against MOCKED subprocess/HTTP (this venv has no mlx server
deps and a benchmark rung may be live on this box). Coverage: the registry temp-copy edit never
touches the real file; the worker-cmdline flag check accepts/rejects correctly; the gate math;
the refuse-if-:8000-busy path; and the no_mtp_head graceful-degradation path.
"""
import json

import pytest
import yaml

from m1 import mtp_probe as M


REGISTRY_YAML = """
models:
  - name: TargetModel-4bit
    type: vision
    hf_path: caslca/TargetModel-4bit
    max_kv_cache_size: 262144
    kv_bits: 0
    generation_defaults:
      temperature: 0.4
    # draft_kind: suffix
    # draft_block_size: 16
    # suffix_min_match: 2
  - name: OtherModel-4bit
    type: vision
    hf_path: caslca/OtherModel-4bit
    max_kv_cache_size: 65536
    draft_kind: suffix
    draft_block_size: 16
"""


# --------------------------------------------------------------------------- registry copy
def test_edit_registry_copy_off_strips_draft_kind(tmp_path):
    src = tmp_path / "main_models.yaml"
    src.write_text(REGISTRY_YAML)
    dest = tmp_path / "registry_off.yaml"
    M.edit_registry_copy(src, dest, "TargetModel-4bit", "off")
    data = yaml.safe_load(dest.read_text())
    entry = next(m for m in data["models"] if m["name"] == "TargetModel-4bit")
    assert "draft_kind" not in entry
    assert "draft_block_size" not in entry


def test_edit_registry_copy_on_sets_mtp_only(tmp_path):
    src = tmp_path / "main_models.yaml"
    src.write_text(REGISTRY_YAML)
    dest = tmp_path / "registry_on.yaml"
    M.edit_registry_copy(src, dest, "TargetModel-4bit", "on")
    data = yaml.safe_load(dest.read_text())
    entry = next(m for m in data["models"] if m["name"] == "TargetModel-4bit")
    assert entry["draft_kind"] == "mtp"
    assert "draft_block_size" not in entry
    assert "suffix_min_match" not in entry


def test_edit_registry_copy_never_touches_the_source(tmp_path):
    src = tmp_path / "main_models.yaml"
    src.write_text(REGISTRY_YAML)
    before = src.read_text()
    dest = tmp_path / "registry_on.yaml"
    M.edit_registry_copy(src, dest, "TargetModel-4bit", "on")
    assert src.read_text() == before


def test_edit_registry_copy_leaves_OTHER_models_untouched(tmp_path):
    src = tmp_path / "main_models.yaml"
    src.write_text(REGISTRY_YAML)
    dest = tmp_path / "registry_on.yaml"
    M.edit_registry_copy(src, dest, "TargetModel-4bit", "on")
    data = yaml.safe_load(dest.read_text())
    other = next(m for m in data["models"] if m["name"] == "OtherModel-4bit")
    assert other["draft_kind"] == "suffix"
    assert other["draft_block_size"] == 16


def test_edit_registry_copy_unknown_model_raises(tmp_path):
    src = tmp_path / "main_models.yaml"
    src.write_text(REGISTRY_YAML)
    dest = tmp_path / "registry_on.yaml"
    with pytest.raises(ValueError, match="NoSuchModel-4bit"):
        M.edit_registry_copy(src, dest, "NoSuchModel-4bit", "on")


def test_original_cap_reads_from_the_untouched_registry(tmp_path):
    src = tmp_path / "main_models.yaml"
    src.write_text(REGISTRY_YAML)
    assert M._original_cap(src, "TargetModel-4bit") == 262144
    assert M._original_cap(src, "OtherModel-4bit") == 65536
    assert M._original_cap(src, "NoSuchModel-4bit") is None


# --------------------------------------------------------------------------- flag verification
@pytest.mark.parametrize("cmdline,arm,expected", [
    ("/venv/bin/mlx_vlm.server --model x --draft-kind mtp --draft-block-size 16", "on", True),
    ("/venv/bin/mlx_vlm.server --model x", "on", False),
    ("/venv/bin/mlx_vlm.server --model x --draft-kind suffix", "on", False),  # wrong kind
    ("/venv/bin/mlx_vlm.server --model x", "off", True),
    ("/venv/bin/mlx_vlm.server --model x --draft-kind mtp", "off", False),
    ("/venv/bin/mlx_vlm.server --model x --draft-kind suffix", "off", True),  # not mtp -> OFF ok
])
def test_verify_draft_flag(cmdline, arm, expected):
    assert M.verify_draft_flag(cmdline, arm) is expected


# --------------------------------------------------------------------------- process probes
class FakeRunner:
    """subprocess.run stand-in: returns canned (stdout, returncode) per argv[0], recording calls."""

    def __init__(self, responses):
        self.responses = responses   # {argv0: (stdout, returncode)}
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        stdout, rc = self.responses.get(cmd[0], ("", 1))

        class R:
            pass
        r = R()
        r.stdout, r.returncode = stdout, rc
        return r


LSOF_ONE = ("COMMAND   PID USER ...\nmlx-serve 4242 me  ...  TCP *:8000 (LISTEN)\n", 0)
LSOF_TWO = ("COMMAND   PID USER ...\n"
           "mlx-serve 4242 me  ...  TCP *:8000 (LISTEN)\n"
           "mlx-serve 9999 me  ...  TCP *:8000 (LISTEN)\n", 0)
LSOF_NONE = ("", 1)


def test_listener_pids_parses_one_listener():
    r = FakeRunner({"lsof": LSOF_ONE})
    assert M.listener_pids(8000, runner=r) == [4242]


def test_listener_pids_parses_multiple_and_dedupes():
    r = FakeRunner({"lsof": LSOF_TWO})
    assert M.listener_pids(8000, runner=r) == [4242, 9999]


def test_listener_pids_empty_when_nothing_listening():
    r = FakeRunner({"lsof": LSOF_NONE})
    assert M.listener_pids(8000, runner=r) == []


def test_worker_pids_parses_pgrep_output():
    r = FakeRunner({"pgrep": ("777\n", 0)})
    assert M.worker_pids(runner=r) == [777]


def test_worker_pids_empty_on_no_match():
    r = FakeRunner({"pgrep": ("", 1)})
    assert M.worker_pids(runner=r) == []


def test_worker_cmdline_strips_whitespace():
    r = FakeRunner({"ps": ("  /venv/bin/mlx_vlm.server --model x  \n", 0)})
    assert M.worker_cmdline(777, runner=r) == "/venv/bin/mlx_vlm.server --model x"


# --------------------------------------------------------------------------- router wait
class FakeProc:
    def __init__(self, poll_sequence):
        self._seq = list(poll_sequence)

    def poll(self):
        if len(self._seq) > 1:
            return self._seq.pop(0)
        return self._seq[0]


class Clock:
    """Advances by a fixed step every time it's read OR slept -- deterministic deadline math."""

    def __init__(self, step=2.0):
        self.t = 0.0
        self.step = step

    def now(self):
        return self.t

    def sleep(self, _s):
        self.t += self.step


def test_wait_for_router_healthy_when_health_check_succeeds():
    proc = FakeProc([None])
    clk = Clock()
    calls = {"n": 0}

    def health(_port):
        calls["n"] += 1
        return calls["n"] >= 2

    out = M.wait_for_router(proc, 8000, wait_s=60, health_check=health,
                            sleeper=clk.sleep, clock=clk.now)
    assert out["status"] == "healthy"


def test_wait_for_router_died_when_process_exits():
    proc = FakeProc([None, None, 1])
    clk = Clock()
    calls = {"n": 0}

    def health(_port):
        calls["n"] += 1
        return False

    out = M.wait_for_router(proc, 8000, wait_s=60, health_check=health,
                            sleeper=clk.sleep, clock=clk.now)
    assert out["status"] == "died"
    assert out["returncode"] == 1


def test_wait_for_router_times_out_when_never_healthy_and_never_dies():
    proc = FakeProc([None])
    clk = Clock(step=10.0)
    out = M.wait_for_router(proc, 8000, wait_s=5, health_check=lambda p: False,
                            sleeper=clk.sleep, clock=clk.now)
    assert out["status"] == "timeout"


# --------------------------------------------------------------------------- kill / teardown
def test_kill_pid_sigterm_only_when_process_dies_promptly():
    calls = []
    alive = {"n": 0}

    def runner(cmd, **kw):
        alive["n"] += 1

        class R:
            returncode = 1 if alive["n"] >= 1 else 0   # "dead" as soon as checked
        return R()

    def killer(pid, sig):
        calls.append((pid, sig))

    ok = M.kill_pid(123, runner=runner, sleeper=lambda s: None, killer=killer)
    assert ok is True
    assert calls == [(123, M.signal.SIGTERM)]   # no SIGKILL needed


def test_kill_pid_escalates_to_sigkill_when_still_alive():
    calls = []
    check_n = {"n": 0}

    def runner(cmd, **kw):
        check_n["n"] += 1

        class R:
            # alive on the first check (after SIGTERM), dead on the second (after SIGKILL)
            returncode = 0 if check_n["n"] == 1 else 1
        return R()

    def killer(pid, sig):
        calls.append((pid, sig))

    ok = M.kill_pid(123, runner=runner, sleeper=lambda s: None, killer=killer)
    assert ok is True
    assert calls == [(123, M.signal.SIGTERM), (123, M.signal.SIGKILL)]


def test_teardown_reports_clean_when_no_listeners_remain():
    def runner(cmd, **kw):
        class R:
            stdout = ""
            returncode = 1
        return R()
    out = M.teardown(4242, runner=runner, sleeper=lambda s: None,
                     killer=lambda pid, sig: None)
    assert out["clean"] is True
    assert out["remaining_listeners"] == []


def test_teardown_reports_not_clean_when_a_listener_survives():
    def runner(cmd, **kw):
        class R:
            stdout = "" if cmd[0] != "lsof" else LSOF_ONE[0]
            returncode = 0
        return R()
    out = M.teardown(4242, runner=runner, sleeper=lambda s: None,
                     killer=lambda pid, sig: None)
    assert out["clean"] is False
    assert out["remaining_listeners"] == [4242]


# --------------------------------------------------------------------------- gate math
def _row(id_, tps, error=None):
    return {"id": id_, "decode_tps": tps, "error": error}


def test_compute_gate_go_when_ratio_meets_threshold():
    off = [_row("a", 50), _row("b", 60), _row("c", 55)]
    on = [_row("a", 70), _row("b", 80), _row("c", 75)]   # ~1.36x median
    g = M.compute_gate(off, on, threshold=1.3)
    assert g["n_matched"] == 3
    assert g["ratio"] == pytest.approx(75 / 55, rel=1e-6)
    assert g["verdict"].startswith("GO")


def test_compute_gate_stop_when_ratio_below_threshold():
    off = [_row("a", 100)]
    on = [_row("a", 110)]   # 1.1x < 1.3
    g = M.compute_gate(off, on, threshold=1.3)
    assert g["verdict"].startswith("STOP")


def test_compute_gate_inconclusive_when_no_items_match():
    off = [_row("a", 100, error="boom")]
    on = [_row("a", 110)]
    g = M.compute_gate(off, on, threshold=1.3)
    assert g["n_matched"] == 0
    assert "INCONCLUSIVE" in g["verdict"]


def test_compute_gate_only_pairs_items_present_and_error_free_in_BOTH_arms():
    off = [_row("a", 100), _row("b", 100, error="timeout")]
    on = [_row("a", 130), _row("c", 999)]   # b failed off, c missing off -> only 'a' pairs
    g = M.compute_gate(off, on, threshold=1.3)
    assert g["n_matched"] == 1


# --------------------------------------------------------------------------- run_items
class FakeDriver:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.preloaded = []

    def preload(self, model, timeout=900):
        self.preloaded.append(model)
        return 1.0

    def complete(self, model, messages, params, timeout=3600, tools=None):
        self.calls.append({"model": model, "messages": messages, "params": dict(params),
                           "timeout": timeout})
        nxt = self.script.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def test_run_items_sends_no_sampling_overrides():
    items = [{"id": "x", "messages": [{"role": "user", "content": "hi"}]}]
    d = FakeDriver([{"content": "c", "completion_tokens": 5, "wall_s": 1.0,
                     "prefill_s": 0.1, "decode_tps": 50.0, "prompt_tokens": 10,
                     "finish_reason": "stop"}])
    M.run_items(d, "M", items, timeout=30)
    assert d.calls[0]["params"] == {}


def test_run_items_records_a_timeout_as_an_error_row_not_a_crash():
    items = [{"id": "x", "messages": []}, {"id": "y", "messages": []}]
    d = FakeDriver([TimeoutError("timed out"),
                    {"content": "c", "completion_tokens": 5, "wall_s": 1.0,
                     "prefill_s": 0.1, "decode_tps": 50.0, "prompt_tokens": 10,
                     "finish_reason": "stop"}])
    rows = M.run_items(d, "M", items, timeout=30)
    assert rows[0]["error"] is not None and "TimeoutError" in rows[0]["error"]
    assert rows[1]["error"] is None
    assert len(rows) == 2   # the failure did not abort the loop


# --------------------------------------------------------------------------- default items
def test_default_items_are_well_formed_and_unique():
    ids = [it["id"] for it in M.DEFAULT_ITEMS]
    assert len(ids) == len(set(ids)) == 3
    for it in M.DEFAULT_ITEMS:
        assert it["messages"] and it["messages"][0]["content"]


def test_load_items_from_jsonl(tmp_path):
    p = tmp_path / "items.jsonl"
    p.write_text(json.dumps({"id": "a", "messages": [{"role": "user", "content": "hi"}]}) + "\n")
    items = M.load_items(p)
    assert items == [{"id": "a", "messages": [{"role": "user", "content": "hi"}]}]


def test_load_items_raises_on_missing_fields(tmp_path):
    p = tmp_path / "items.jsonl"
    p.write_text(json.dumps({"id": "a"}) + "\n")
    with pytest.raises(ValueError):
        M.load_items(p)


# --------------------------------------------------------------------------- main() orchestration
def test_main_refuses_when_port_8000_is_busy(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "listener_pids", lambda port=8000, runner=None: [111])

    def _boom(*a, **kw):
        raise AssertionError("run_arm must never be called when :8000 is busy")
    monkeypatch.setattr(M, "run_arm", _boom)

    rc = M.main(["--model", "M", "--workdir", str(tmp_path)])
    assert rc == 2


def test_main_requires_workdir_or_STACK_WORKDIR(monkeypatch):
    monkeypatch.delenv("STACK_WORKDIR", raising=False)
    rc = M.main(["--model", "M"])
    assert rc == 2


def test_main_no_mtp_head_path_writes_json_and_exits_0(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "listener_pids", lambda port=8000, runner=None: [])

    def fake_run_arm(model, arm, *a, **kw):
        if arm == "off":
            return {"arm": "off", "status": "ok",
                    "rows": [{"id": "lru_cache", "error": None, "decode_tps": 50.0}]}
        return {"arm": "on", "status": "no_mtp_head",
                "message": "model load failed: RuntimeError: no mtp sidecar"}
    monkeypatch.setattr(M, "run_arm", fake_run_arm)

    rc = M.main(["--model", "M", "--workdir", str(tmp_path)])
    assert rc == 0
    out = json.loads((tmp_path / "mtp_probe" / "M" / "mtp_probe_result.json").read_text())
    assert out["status"] == "no_mtp_head"
    assert out["gate"] is None
    assert out["model"] == "M"


def test_main_both_arms_ok_computes_gate_and_writes_it(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "listener_pids", lambda port=8000, runner=None: [])

    def fake_run_arm(model, arm, *a, **kw):
        tps = 50.0 if arm == "off" else 70.0
        return {"arm": arm, "status": "ok",
                "rows": [{"id": "lru_cache", "error": None, "decode_tps": tps}]}
    monkeypatch.setattr(M, "run_arm", fake_run_arm)

    rc = M.main(["--model", "M", "--workdir", str(tmp_path), "--gate-threshold", "1.3"])
    assert rc == 0
    out = json.loads((tmp_path / "mtp_probe" / "M" / "mtp_probe_result.json").read_text())
    assert out["status"] == "ok"
    assert out["gate"]["verdict"].startswith("GO")


def test_main_json_out_override(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "listener_pids", lambda port=8000, runner=None: [])
    monkeypatch.setattr(M, "run_arm", lambda model, arm, *a, **kw:
                        {"arm": arm, "status": "ok", "rows": []})
    custom = tmp_path / "custom_result.json"
    rc = M.main(["--model", "M", "--workdir", str(tmp_path), "--json-out", str(custom)])
    assert rc == 0
    assert custom.exists()
