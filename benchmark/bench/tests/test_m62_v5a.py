import json, os, subprocess, threading, time
from pathlib import Path
import pytest
from bench import proc_guard as pg, token_turn_gate as tg, structured_grade as sg, tg1_runner as runner
from bench.tests.test_proc_guard import Process, guard
from bench.tests.test_token_turn_gate import request, assistant, event

@pytest.fixture(autouse=True)
def mock_ancestors(monkeypatch):
    import psutil
    monkeypatch.setattr(psutil.Process, "parents", lambda self: [])

def test_operator_other_terminal_is_not_item_owned(tmp_path, monkeypatch):
    shell=Process(99101,cwd=str(tmp_path),created=1,argv=["/bin/zsh","-l"])
    monkeypatch.setattr(pg.os,"getsid",lambda pid: 5 if pid==0 else 6)
    g=guard(tmp_path,[shell]); g.started=100
    g.cleanup()
    assert not shell.dead, "pre-existing unrelated operator shell killed solely for cwd"

def test_signal_during_spawn_registration_does_not_leak(tmp_path,monkeypatch):
    child=Process(99102,cwd=str(tmp_path))
    child.wait = lambda **kw: -9
    child.poll = lambda: -9 if child.dead else None
    monkeypatch.setattr(pg.os,"getsid",lambda pid: 5)
    g=guard(tmp_path,[child])
    monkeypatch.setattr(pg.subprocess,"Popen",lambda *a,**k: child)
    def interrupted(*a): raise SystemExit(143)
    monkeypatch.setattr(g,"register",interrupted)
    try:
        with pytest.raises(SystemExit): g.spawn(["fixture"])
    finally: g.cleanup()
    assert child.dead, "unregistered spawn survives same-session sweep exclusion"

def test_commented_testmain_is_forbidden(tmp_path):
    (tmp_path/"helper_test.go").write_text("package p\nimport \"testing\"\nfunc /* allowed Go comment */ TestMain(m *testing.M) { m.Run() }\n")
    assert sg.tampered(tmp_path,{}, {},"go"), "legal TestMain declaration evades regex"

def test_normal_final_export_requires_finished_session():
    s=tg.EventStream(tg.TokenTurnGate(1)); request(s); s.accept(event("step_start","m2"))
    m=assistant("m2"); m["finish"]="tool-calls"
    with pytest.raises(tg.TransportAbort): tg.reconcile(s,{"messages":[assistant(),m]},0)

def test_kill_does_not_erase_started_request():
    s=tg.EventStream(tg.TokenTurnGate(1)); request(s); s.accept(event("step_start","m2"))
    with pytest.raises(tg.TransportAbort): tg.reconcile(s,{"messages":[assistant()]},-9,"stalled")

@pytest.mark.parametrize("slow_phases", [False, True])
def test_resource_kill_cancels_before_export(tmp_path,monkeypatch,capsys,slow_phases):
    work=tmp_path/"work"; work.mkdir(); private=tmp_path/"private"; private.mkdir()
    (work/"solution.py").write_text("answer=42")
    prepared=sg.manifest(work)
    entry=dict(baseline_failing=1,leaves=[["test.py","test","ok"]],protected={},prepared=prepared,lang="python",test="test.py",id="python/one")
    calls=[]
    class Guard:
        client_resource=True; mem_kills=[]; orphans_unattributed=[]
        def __init__(self,*a,**k): pass
        def start(self): pass
        def spawn(self,cmd,**kw):
            kw["stdout"].write((json.dumps(event("step_start"))+"\n"+json.dumps(event("step_finish",tokens=assistant()["tokens"]))+"\n"+json.dumps(event("step_start","m2"))+"\n").encode()); kw["stdout"].flush()
            class Proc:
                returncode=-9
                def poll(self): return -9
                def wait(self,**kw): return -9
            return Proc()
        def run_grader(self,cmd,**kw):
            calls.append("export")
            return subprocess.CompletedProcess(cmd,0,json.dumps(dict(messages=[assistant(),dict(id="m2",type="assistant",error=dict(type="aborted"))])),"")
        def kill_role(self, role): calls.append("kill-" + role)
        def cleanup(self): calls.append("cleanup")
    monkeypatch.setattr(pg,"ProcessGuard",Guard)
    monkeypatch.setattr(runner, "HEARTBEAT_INTERVAL_S", 0.005)
    metrics = iter([1, 1, 0])
    def metric(endpoint):
        busy = next(metrics)
        calls.append("busy" if busy else "idle")
        return {"summary": {"in_flight": busy}}
    monkeypatch.setattr(runner, "worker_json", metric)
    real_cancel = pg.wait_cancel
    def cancel(*a, **kw):
        calls.append("cancel")
        if slow_phases:
            time.sleep(0.04)
        return real_cancel(*a, **kw, sleep=lambda _: None)
    monkeypatch.setattr(pg, "wait_cancel", cancel)
    real_drain = tg.EventStream.finish
    def drain(self, **kw):
        calls.append("drain")
        return real_drain(self, **kw)
    monkeypatch.setattr(tg.EventStream, "finish", drain)
    real_finish = runner.GradeWorker.finish
    def finish(self):
        calls.append("finish-grades")
        return real_finish(self)
    monkeypatch.setattr(runner.GradeWorker, "finish", finish)
    def grade(*a, **kw):
        if slow_phases:
            time.sleep(0.04)
        return sg.Grade(passing={("test.py", "test", "ok")})
    monkeypatch.setattr(sg, "grade", grade)
    result=runner.run_item(None,model="fixture",work=work,prompt="fixture",env={"TMPDIR":str(tmp_path/"itemtmp")},binary="fixture",evidence=tmp_path/"evidence/one",entry=entry,limit=262144,private=private,router={},base="fixture")
    order = ["kill-client", "kill-model", "cancel", "busy", "idle", "drain", "finish-grades", "export"]
    assert [calls.index(c) for c in order] == sorted(calls.index(c) for c in order), calls
    assert calls.count("cancel") == 1
    assert result["gate"]["requests_completed_at_kill"] is not None
    assert result["nonconv_kind"] == "client_resource" and result["converged"] is False
    assert result["termination"]["reason"] == "client_resource"
    if slow_phases:
        lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
        for phase in ("cancellation", "terminal_grading"):
            assert sum(line["phase"] == phase for line in lines) >= 2

def test_running_tool_event_is_malformed_not_a_completed_call():
    g=tg.TokenTurnGate(1); s=tg.EventStream(g); s.accept(event("step_start"))
    with pytest.raises(tg.TransportAbort):
        for n in range(8):
            s.accept(event("tool_use",partID=str(n),tool="shell",state={"input":{},"status":"running"}))

@pytest.mark.parametrize('tracked', [False, True])
def test_protected_service_pids_never_killed(tmp_path, monkeypatch, tracked):
    router = Process(99103, created=110, cwd=str(tmp_path), rss=999)
    worker = Process(99104, created=110, cwd=str(tmp_path), rss=999)
    g = guard(tmp_path, [router, worker], protected_pids={router.pid, worker.pid}, per_process=1)
    g.started = 100
    if tracked:
        g.tracked.update({(p.pid, p.created): 'model' for p in [router, worker]})
    g.tick()
    g.cleanup()
    assert not router.dead and not worker.dead


def test_new_path_only_process_aborts_without_kill(tmp_path, monkeypatch):
    p = Process(99105, created=110, cwd=str(tmp_path))
    monkeypatch.setattr(pg.os, 'getsid', lambda pid: 5 if pid == 0 else 6)
    g = guard(tmp_path, [p]); g.started = 100
    with pytest.raises(tg.TransportAbort, match='cleanup uncertain.*99105'):
        g.cleanup()
    assert not p.dead
    assert g.orphans_unattributed[0]['pid'] == p.pid


@pytest.mark.parametrize('sig', [__import__('signal').SIGTERM, __import__('signal').SIGINT])
def test_acquisition_signal_delivered_after_registration(tmp_path, monkeypatch, sig):
    import signal
    child = Process(99106, created=110)
    child.poll = lambda: -9 if child.dead else None
    child.wait = lambda **kw: -9
    g = guard(tmp_path, [child]); g.started = 100
    monkeypatch.setattr(g, 'start', lambda: None)
    handlers = {}
    calls = []
    def terminate(signum, frame):
        calls.append(('signal', (child.pid, child.created) in g.tracked))
        raise SystemExit(128 + signum)
    monkeypatch.setattr(pg.signal, 'getsignal', lambda s: terminate)
    monkeypatch.setattr(pg.signal, 'signal', lambda s, h: handlers.__setitem__(s, h))
    def spawn(*a, **kw):
        handlers.get(sig, terminate)(sig, None)
        calls.append(('spawn', True))
        return child
    monkeypatch.setattr(pg.subprocess, 'Popen', spawn)
    with pytest.raises(SystemExit):
        g.spawn(['fixture'])
    g.cleanup()
    assert calls == [('spawn', True), ('signal', True)] and child.dead


@pytest.mark.parametrize('source', [
    '// func TestMain(m *testing.M) {}',
    '/* func TestMain(m *testing.M) {} */',
    'var s = "func TestMain("',
    'var s = `func TestMain(`',
    "var r = '{'\nfunc helper() { f := func() {}; _ = f }",
    'func (x T) TestMain() {}',
])
def test_testmain_comments_literals_methods_allowed(tmp_path, source):
    (tmp_path / 'solution.go').write_text('package p\n' + source)
    assert not sg.tampered(tmp_path, {}, {}, 'go')


def test_testmain_commented_declaration_in_existing_solution(tmp_path):
    p = tmp_path / 'solution.go'; p.write_text('package p')
    prepared = sg.manifest(tmp_path)
    p.write_text('package p\nfunc /* c */ TestMain /* d */ (m *testing.M) {}')
    assert sg.tampered(tmp_path, {}, prepared, 'go')


@pytest.mark.parametrize('state', [None, [], {}, {'status':'completed','input':[]},
    {'status':'completed','input':{},'output':3}, {'status':'error','input':{},'error':{}},
    {'status':'completed','input':{}}, {'status':'error','input':{}}])
def test_tool_state_projection_rejected_before_k(state):
    g = tg.TokenTurnGate(1); s = tg.EventStream(g); s.accept(event('step_start'))
    with pytest.raises(tg.TransportAbort):
        s.accept(event('tool_use', tool='shell', state=state))
    assert g.max_identical_run_live == 0


def test_killed_active_message_must_be_trailing():
    s = tg.EventStream(tg.TokenTurnGate(1)); request(s); s.accept(event('step_start', 'm2'))
    with pytest.raises(tg.TransportAbort):
        tg.reconcile(s, {'messages':[assistant(), assistant('m2'),
            dict(id='m3',type='assistant',error={'type':'aborted'})]}, -9, 'stalled')


def test_snapshot_rejects_copied_manifest_when_source_a_equals_b(tmp_path, monkeypatch):
    work = tmp_path / 'work'; work.mkdir(); (work / 'a').write_text('stable')
    real = sg.manifest
    def manifest(path):
        return real(path) if Path(path) == work else {'a': 'corrupt-copy'}
    monkeypatch.setattr(sg, 'manifest', manifest)
    with sg.snapshot(work, tmp_path, boundary=1) as snap:
        assert snap is None


def test_heartbeat_continues_through_terminal_phases(capsys):
    import time
    lock = threading.RLock()
    watch = runner.PhaseHeartbeat(tg.TokenTurnGate(1), lock, time.monotonic(), interval=0.01)
    watch.start()
    try:
        for phase in ('cancellation', 'terminal_grading', 'cleanup'):
            watch.set_phase(phase)
            time.sleep(0.035)
    finally:
        watch.close()
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    for phase in ('cancellation', 'terminal_grading', 'cleanup'):
        assert sum(row['phase'] == phase for row in lines) >= 2
    assert all('m62_watch' in row for row in lines)
    assert runner.HEARTBEAT_INTERVAL_S <= 60


def test_interrupted_acquisition_runner_cleans_and_cancels(tmp_path, monkeypatch):
    import signal
    work = tmp_path / 'work'; work.mkdir()
    private = tmp_path / 'private'; private.mkdir()
    child = Process(99107, created=110)
    child.poll = lambda: -9 if child.dead else None
    child.wait = lambda **kw: -9
    g = guard(tmp_path, [child]); g.started = 100
    monkeypatch.setattr(g, 'start', lambda: None)
    monkeypatch.setattr(pg, 'ProcessGuard', lambda *a, **kw: g)
    handlers = {}
    def interrupt(sig, frame):
        assert (child.pid, child.created) in g.tracked
        raise SystemExit(143)
    monkeypatch.setattr(pg.signal, 'getsignal', lambda sig: interrupt)
    monkeypatch.setattr(pg.signal, 'signal', lambda sig, fn: handlers.__setitem__(sig, fn))
    def spawn(*a, **kw):
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        return child
    monkeypatch.setattr(pg.subprocess, 'Popen', spawn)
    cancelled = []
    def metrics(endpoint):
        assert child.dead, 'cancel check before owned process cleanup'
        cancelled.append(True)
        return {'summary': {'in_flight': 0}}
    monkeypatch.setattr(runner, 'worker_json', metrics)
    with pytest.raises(SystemExit):
        runner.run_item(None, model='fixture', work=work, prompt='fixture',
            env={'TMPDIR': str(tmp_path/'itemtmp')}, binary='fixture', evidence=tmp_path/'evidence/one',
            entry=dict(baseline_failing=1, leaves=[['a']], lang='python'),
            limit=262144, private=private, router={}, base='fixture')
    assert child.dead and cancelled


@pytest.mark.parametrize('status', ['completed', 'error'])
@pytest.mark.parametrize('field,bad', [('input', []), ('metadata', []), ('time', {}),
                                     ('time', {'start':True, 'end':2}), ('status', 'running')])
def test_tool_projection_field_types(status, field, bad):
    from bench.tests.test_token_turn_gate import tool_state
    state = tool_state(status=status); state[field] = bad
    stream = tg.EventStream(tg.TokenTurnGate(1)); stream.accept(event('step_start'))
    with pytest.raises(tg.TransportAbort):
        stream.accept(event('tool_use', tool='shell', state=state))
    assert stream.gate.max_identical_run_live == 0


def test_failed_cancellation_is_not_retried_or_exported(tmp_path, monkeypatch):
    calls = []
    class Guard:
        client_resource = True
        def __init__(self, *a, **kw): pass
        def start(self): pass
        def spawn(self, *a, **kw):
            class Proc:
                returncode = -9
                def poll(self): return -9
                def wait(self, **kw): return -9
            return Proc()
        def kill_role(self, *a): pass
        def cleanup(self): calls.append('cleanup')
        def run_grader(self, *a, **kw): pytest.fail('export after failed cancellation')
    monkeypatch.setattr(pg, 'ProcessGuard', Guard)
    def cancel(*a, **kw):
        calls.append('cancel')
        raise tg.TransportAbort('worker health: did not cancel')
    monkeypatch.setattr(pg, 'wait_cancel', cancel)
    with pytest.raises(tg.TransportAbort, match='did not cancel'):
        runner.run_item(None, model='fixture', work=tmp_path, prompt='fixture',
            env={'TMPDIR': str(tmp_path/'itemtmp')}, binary='fixture', evidence=tmp_path/'evidence/one',
            entry=dict(baseline_failing=1, leaves=[['a']], lang='python'),
            limit=262144, private=tmp_path, router={}, base='fixture')
    assert calls == ['cancel', 'cleanup']


def test_kill_samples_owned_descendants_before_parent_exit(tmp_path):
    parent = Process(99120)
    child = Process(99121, ppid=parent.pid)
    g = guard(tmp_path, [parent, child])
    g.register(parent, 'client')
    def kill_parent():
        parent.dead = True
        child.parent = 1
    parent.kill = kill_parent
    g.kill_role('client')
    g.kill_role('model')
    assert parent.dead and child.dead
