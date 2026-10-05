"""M57 final review: Z1 (lsof exit-1 semantics), Z4 (backend composition), Z3 (genuine worker)."""
import subprocess
import sys
import types

import pytest

import bench.provenance as P
from bench.tests.test_worker_port_attribution import (ARGV_AUTO, HF, _facts, _ports, _registry)


class _AD(Exception):
    pass


class _NS(Exception):
    pass


def _fake_psutil(procs):
    return types.SimpleNamespace(
        CONN_LISTEN="LISTEN", AccessDenied=_AD, NoSuchProcess=_NS, ZombieProcess=_NS,
        process_iter=lambda attrs=None: procs)


class _Proc:
    def __init__(self, pid, conns):
        self.pid, self._c = pid, conns

    def net_connections(self, kind="inet"):
        if isinstance(self._c, Exception):
            raise self._c
        return self._c


def _listen(port):
    return [types.SimpleNamespace(status="LISTEN", laddr=types.SimpleNamespace(ip="127.0.0.1", port=port))]


def _lsof(monkeypatch, rc=1, out="", err="", exc=None):
    def run(*a, **k):
        if exc:
            raise exc
        return subprocess.CompletedProcess(a, rc, stdout=out, stderr=err)
    monkeypatch.setattr(P.subprocess, "run", run)


def _psutil(monkeypatch, procs):
    monkeypatch.setitem(sys.modules, "psutil", _fake_psutil(procs))


# ------------------------------------------------------------------ Z1
def test_z1_lsof_exit1_with_stderr_is_an_observation_failure(monkeypatch):
    _psutil(monkeypatch, [_Proc(5, _AD())])                          # psutil incomplete
    _lsof(monkeypatch, rc=1, err="lsof: WARNING: can't stat() fs\n")
    with pytest.raises(Exception, match="state unknown"):
        P._port_listener_pids(8091)


def test_z1_clean_lsof_exit1_is_no_listener(monkeypatch):
    _psutil(monkeypatch, [_Proc(5, _AD())])
    _lsof(monkeypatch, rc=1)
    assert P._port_listener_pids(8091) == []


def test_z1_other_exit_code_is_a_failure(monkeypatch):
    _psutil(monkeypatch, [_Proc(5, _AD())])
    _lsof(monkeypatch, rc=2)
    with pytest.raises(Exception, match="state unknown"):
        P._port_listener_pids(8091)


# ------------------------------------------------------------------ Z4
def test_z4_psutil_complete_and_lsof_missing_uses_psutil(monkeypatch):
    _psutil(monkeypatch, [_Proc(7, _listen(8091)), _Proc(8, [])])
    _lsof(monkeypatch, exc=FileNotFoundError("lsof"))
    assert P._port_listener_pids(8091) == [7]


def test_z4_psutil_complete_empty_and_lsof_missing_is_no_listener(monkeypatch):
    _psutil(monkeypatch, [_Proc(8, [])])
    _lsof(monkeypatch, exc=FileNotFoundError("lsof"))
    assert P._port_listener_pids(8091) == []


def test_z4_psutil_incomplete_and_lsof_clean_uses_lsof(monkeypatch):
    _psutil(monkeypatch, [_Proc(5, _AD())])
    _lsof(monkeypatch, rc=0, out="p42\n")
    assert P._port_listener_pids(8091) == [42]


def test_z4_both_incomplete_refuses_with_state_unknown(monkeypatch):
    _psutil(monkeypatch, [_Proc(5, _AD())])
    _lsof(monkeypatch, exc=FileNotFoundError("lsof"))
    with pytest.raises(Exception, match="router/worker state unknown"):
        P._port_listener_pids(8091)


def test_z4_both_complete_unions(monkeypatch):
    _psutil(monkeypatch, [_Proc(7, _listen(8091))])
    _lsof(monkeypatch, rc=0, out="p9\n")
    assert P._port_listener_pids(8091) == [7, 9]


def test_z4_zombie_processes_do_not_make_psutil_incomplete(monkeypatch):
    _psutil(monkeypatch, [_Proc(6, _NS()), _Proc(7, _listen(8091))])
    _lsof(monkeypatch, exc=FileNotFoundError("lsof"))
    assert P._port_listener_pids(8091) == [7]


def test_z4_unrelated_unreadable_process_does_not_refuse_when_lsof_is_clean(monkeypatch):
    _psutil(monkeypatch, [_Proc(5, _AD()), _Proc(7, _listen(8091))])
    _lsof(monkeypatch, rc=0, out="p7\n")
    assert P._port_listener_pids(8091) == [7]


# ------------------------------------------------------------------ Z3
def _tree(monkeypatch, parents):
    monkeypatch.setattr(P, "_ppid", lambda pid: parents.get(pid))


_FUSED = ["--attention-policy", "fused_v1"]


def test_z3_genuine_descendant_worker_is_accepted(monkeypatch, tmp_path):
    _ports(monkeypatch, {8091: [111], 8000: [1]})
    _facts(monkeypatch, {111: {"argv": ARGV_AUTO + _FUSED}})
    _tree(monkeypatch, {111: 50, 50: 1, 1: 0})
    assert P.registry_attention_policy("m", _registry(tmp_path))["attention_policy_source"] == "worker"


def test_z3_console_script_entry_point_is_accepted(monkeypatch, tmp_path):
    _ports(monkeypatch, {8091: [111], 8000: [1]})
    _facts(monkeypatch, {111: {"argv": ["/venv/bin/python", "/venv/bin/mlx_vlm.server",
                                        "--model", HF] + _FUSED}})
    _tree(monkeypatch, {111: 1})
    assert P.registry_attention_policy("m", _registry(tmp_path))["attention_policy_source"] == "worker"


def test_z3_non_mlx_vlm_listener_refuses(monkeypatch, tmp_path):
    _ports(monkeypatch, {8091: [111], 8000: [1]})
    _facts(monkeypatch, {111: {"argv": ["python", "-m", "http.server", "--model", HF]}})
    _tree(monkeypatch, {111: 1})
    with pytest.raises(P.ServingStateError, match="mlx_vlm"):
        P.registry_attention_policy("m", _registry(tmp_path))


def test_z3_listener_not_descended_from_the_router_refuses(monkeypatch, tmp_path):
    _ports(monkeypatch, {8091: [111], 8000: [1]})
    _facts(monkeypatch, {111: {"argv": ARGV_AUTO + _FUSED}})
    _tree(monkeypatch, {111: 77, 77: 2, 2: 0})
    with pytest.raises(P.ServingStateError, match="descend"):
        P.registry_attention_policy("m", _registry(tmp_path))


def test_z3_no_router_skips_the_descent_check(monkeypatch, tmp_path):
    _ports(monkeypatch, {8091: [111], 8000: []})
    _facts(monkeypatch, {111: {"argv": ARGV_AUTO + _FUSED}})
    _tree(monkeypatch, {111: 77})
    assert P.registry_attention_policy("m", _registry(tmp_path))["attention_policy_source"] == "worker"


def test_z3_manager_port_state_unknown_refuses(monkeypatch, tmp_path):
    _ports(monkeypatch, {8091: [111], 8000: OSError("router/worker state unknown")})
    _facts(monkeypatch, {111: {"argv": ARGV_AUTO}})
    with pytest.raises(P.ServingStateError):
        P.registry_attention_policy("m", _registry(tmp_path))
