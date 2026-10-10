"""V5a re-review (P13/P14) counterexamples, ported from the cold reviewer's fixtures (signals are fake)."""
import pytest
from bench import proc_guard as pg
from bench.tests.test_proc_guard import Process, guard


def test_pid_reused_parent_cannot_authorize_unrelated_child(tmp_path, monkeypatch):
    """process_iter retains cached create_time; ppid rejects reused identity.
    The dead identity must not remain an ancestry authority in alive.
    All signals are fake Process.kill calls.
    """
    root = Process(99201, created=110)
    owned_shell = Process(99202, ppid=root.pid, created=111)
    processes = [root, owned_shell]
    g = guard(tmp_path, processes, per_process=8)
    g.started = 100
    g.register(root, 'client')
    g.tick()
    assert g.tracked[(owned_shell.pid, 111)] == 'model'

    # The shell exits and is reaped. Its PID now belongs to another terminal's
    # operator process. psutil 7.2.2 process_iter reuses the cached Process object;
    # create_time remains 111, status/uids observe the replacement.
    def stale_identity():
        raise g.psutil.NoSuchProcess(owned_shell.pid)
    owned_shell.ppid = stale_identity
    owned_shell.kill = stale_identity
    unrelated = Process(99203, ppid=owned_shell.pid, created=121, rss=9,
                        cwd='/unrelated', argv=['unrelated-operator-command'])
    processes.append(unrelated)
    monkeypatch.setattr(pg.os, 'getsid', lambda pid: 5 if pid == 0 else 6)
    g.tick()
    assert not unrelated.dead, ('unrelated process killed', g.tracked, g.mem_kills)


def test_kill_role_can_kill_then_raise(tmp_path, monkeypatch):
    child = Process(99301, created=110)
    g = guard(tmp_path, [child]); g.started = 100
    g.register(child, 'client')
    def failed_tick():
        raise g.psutil.AccessDenied(99399)
    monkeypatch.setattr(g, 'tick', failed_tick)
    with pytest.raises(g.psutil.AccessDenied):
        g.kill_role('client')
    assert child.dead


def test_kill_then_error_cannot_bypass_worker_cancellation(tmp_path, monkeypatch):
    from bench import tg1_runner as runner, token_turn_gate as tg
    calls = []
    class Guard:
        client_resource = True
        def __init__(self, *args, **kwargs): pass
        def start(self): pass
        def spawn(self, *args, **kwargs):
            class Child:
                returncode = -9
                def poll(self): return -9
                def wait(self, **kwargs): return -9
            return Child()
        def kill_role(self, role):
            calls.append('kill-' + role)
            if role == 'client':
                # Real kill_role signals tracked clients in finally even when
                # its ancestry/memory scan raises; see preceding test.
                raise tg.TransportAbort('scan failed after signalling client')
        def cleanup(self): calls.append('cleanup')
        def run_grader(self, *args, **kwargs): pytest.fail('export on error')
    monkeypatch.setattr(pg, 'ProcessGuard', Guard)
    monkeypatch.setattr(pg, 'wait_cancel', lambda *a, **k: calls.append('cancel'))
    with pytest.raises(tg.TransportAbort, match='scan failed'):
        runner.run_item(None, model='fixture', work=tmp_path, prompt='fixture',
            env={'TMPDIR': str(tmp_path/'itemtmp')}, binary='fixture',
            evidence=tmp_path/'evidence/one', entry=dict(baseline_failing=1,
            leaves=[['a']], lang='python'), limit=262144, private=tmp_path,
            router={}, base='fixture')
    assert 'cancel' in calls, calls
