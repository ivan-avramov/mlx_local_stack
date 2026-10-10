"""Revision-5 behavior oracles; no model, Docker, or external serving dependencies."""
import json
import threading
from pathlib import Path
import pytest
from bench import token_turn_gate as tg, tg1_runner as runner, proc_guard as pg, structured_grade as sg
from bench.tests.test_token_turn_gate import event, usage, request, assistant
from bench.tests.test_proc_guard import Process, guard
from m62 import replay


def test_f2_charge_then_enqueue_then_check():
    g = tg.TokenTurnGate(2)
    observed = []
    def enqueue(boundary):
        observed.append((boundary, len(g.request_usage), g.output_tokens))
        g.pending.add(boundary)
    s = tg.EventStream(g, enqueue)
    request(s, output=81920)
    assert observed == [(1, 1, 81920)]
    assert g.stop_reason is None
    g.grade(1, 1)
    assert g.stop_reason is None


def test_f11_new_captures_cannot_extend_stall_wait():
    g = tg.TokenTurnGate(2)
    g.pending.add(1)
    g.complete('1', usage(81920))
    for n in range(2, 9):
        g.pending.add(n)
        g.complete(str(n), usage(1))
    g.grade(1, 2)
    assert g.stop_reason == 'stalled'


@pytest.mark.parametrize('killed', [True, False])
def test_f4_torn_tail(killed):
    s = tg.EventStream(tg.TokenTurnGate(1))
    s.feed(b'{"type":')
    if killed:
        s.finish(killed=True)
        assert s.torn_tail and not s.buffer
    else:
        with pytest.raises(tg.TransportAbort):
            s.finish()


def test_f4_ignored_types_counted_without_required_projection():
    s = tg.EventStream(tg.TokenTurnGate(1))
    for k in ('text', 'reasoning', 'future_event'):
        s.accept(dict(type=k))
        s.accept(dict(type=k))
    assert s.event_types_seen == dict(text=2, reasoning=2, future_event=2)


def test_f4_duplicate_type_part_id_across_messages():
    s = tg.EventStream(tg.TokenTurnGate(1))
    request(s)
    e = event('step_start', 'm2')
    e['part']['id'] = 'step_startm1'
    with pytest.raises(tg.TransportAbort, match='duplicate'):
        s.accept(e)


@pytest.mark.parametrize('part', [None, [], {}, {'id': 'p', 'messageID': 'm1', 'tool': None, 'state': {'input': {}}}])
def test_f4_malformed_depended_event_aborts(part):
    s = tg.EventStream(tg.TokenTurnGate(1))
    s.accept(event('step_start'))
    with pytest.raises(tg.TransportAbort):
        s.accept(dict(type='tool_use', sessionID='s1', part=part))


@pytest.mark.parametrize('reasoning', [True, -1, None, 7])
def test_f7_reasoning_usage(reasoning):
    g = tg.TokenTurnGate(1, context_limit=1000)
    u = usage(473, 100, 200, 100)
    if reasoning is not None:
        u['reasoning'] = reasoning
    else:
        u.pop('reasoning', None)
    if type(reasoning) is int and reasoning >= 0:
        g.complete('m', u)
        assert g.request_usage == [('m', 480, 400, 480)] and g.primary == 'budget_hit'
    else:
        with pytest.raises(tg.TransportAbort):
            g.complete('m', u)


def test_f8_loop_mid_request_canonical_inputs_errors_count():
    g = tg.TokenTurnGate(1)
    s = tg.EventStream(g)
    s.accept(event('step_start'))
    for n in range(8):
        inputs = {'a': 1, 'b': 2} if n % 2 else {'b': 2, 'a': 1}
        s.accept(event('tool_use', partID=str(n), tool='shell', state=dict(input=inputs, status='error')))
    assert g.stop_reason == 'looping' and not g.request_usage
    assert g.first_crossing_request == 1


@pytest.mark.parametrize('finish', ['stop', None])
def test_f3_completed_unpublished_trailing_requires_finish(finish):
    g = tg.TokenTurnGate(1)
    s = tg.EventStream(g)
    request(s)
    m = assistant('m2', 327680)
    m['finish'] = finish
    if finish:
        tg.reconcile(s, dict(messages=[assistant(), m]), -9, 'stalled')
        assert g.output_tokens == 327681 and 'hard_ceiling' in g.flags
    else:
        with pytest.raises(tg.TransportAbort):
            tg.reconcile(s, dict(messages=[assistant(), m]), -9, 'stalled')


@pytest.mark.parametrize('name', ['scratch_test.go', 'nested/go.mod', 'nested/go.work', 'nested/vendor/a.go', 'nested/main_test.go'])
def test_f5_model_tests_nested_modules_allowed(tmp_path, name):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('package nested\nfunc TestMain(m *testing.M) {}' if name.endswith('main_test.go') else '')
    assert not sg.tampered(tmp_path, {}, {}, 'go')


def test_f1_transient_idle_and_growth_reset():
    s = pg.SilenceObserver()
    def sample(t, busy=0, size=100, descendant=True):
        return s.sample(t, size, {'summary': {'in_flight': busy}}, descendant)
    assert sample(0) is None
    assert sample(20) is None
    assert sample(60) is None
    assert sample(120, busy=1) is None
    assert sample(180) is None
    assert sample(240, size=101) is None
    assert sample(300, size=101) is None
    assert sample(360, size=101) is None
    assert sample(420, size=101) == 'exec_timeout'


def test_f1_idle_none_is_exit_hang_candidate():
    s = pg.SilenceObserver()
    for t in (0, 60):
        assert s.sample(t, 0, {'summary': {'in_flight': 0}}, False) is None
    assert s.sample(120, 0, {'summary': {'in_flight': 0}}, False) == 'client_exit_hang'


def test_f9_cancellation_prefill_bound():
    for prompt, expected in [(0, 300), (60000, 300), (240000, 800)]:
        clock = [0]
        def sleep(n): clock[0] += n
        with pytest.raises(tg.TransportAbort, match='worker health: did not cancel'):
            pg.wait_cancel(lambda: {'summary': {'in_flight': 1}}, prompt_tokens=prompt, now=lambda: clock[0], sleep=sleep)
        assert clock[0] == expected


def test_f13_sweep_excludes_probe_ancestors_and_session(tmp_path, monkeypatch):
    import os
    ancestor = Process(os.getppid(), cwd=str(tmp_path))
    peer = Process(201, cwd=str(tmp_path))
    child = Process(202, cwd=str(tmp_path))
    monkeypatch.setattr(pg.os, 'getsid', lambda pid: 1 if pid in (0, os.getpid(), 201) else 2)
    g = guard(tmp_path, [ancestor, peer, child])
    g.cleanup()
    assert not ancestor.dead and not peer.dead and child.dead


def test_f10_replay_export_sha_and_terminal_charge(tmp_path):
    events = tmp_path / 'e'
    export = tmp_path / 'x'
    events.write_text(json.dumps(event('step_start')) + '\n')
    export.write_text(json.dumps(dict(messages=[assistant(output=81920)])))
    import hashlib
    e = dict(id='python/one', events_path=str(events), transcript_path=str(export),
             events_sha256=hashlib.sha256(events.read_bytes()).hexdigest(),
             export_sha256=hashlib.sha256(export.read_bytes()).hexdigest(), stop_reason='completed',
             identity_matched=True)
    r = replay.replay_entry(e, tmp_path)
    assert r['output_tokens_completed'] == 81920 and r['stop_reason'] == 'stalled'
    assert r['terminal_usage_complete']
    export.write_text('{}')
    with pytest.raises(tg.TransportAbort, match='export.*sha256'):
        replay.replay_entry(e, tmp_path)


def test_f10_exact_fixture_outcomes():
    entries = [dict(fixture=x) for x in ('looping@request15', 'looping@request22', 'no_stop')]
    reports = [dict(stop_reason=r, first_crossing_request=j, terminal_usage_complete=True)
               for r,j in [('looping',15),('looping',22),(None,None)]]
    assert all(replay.criteria(entries, reports, expected_valid=0).values())
    for reason, index in [('stalled',40), ('looping',21), ('looping',23)]:
        reports[1] = dict(stop_reason=reason, first_crossing_request=index, terminal_usage_complete=True)
        assert not all(replay.criteria(entries, reports, expected_valid=0).values())


def test_f2_unchanged_successful_manifest_not_enqueued_ungradeable_retried(tmp_path):
    work = tmp_path / 'work'
    work.mkdir()
    (work / 'a').write_text('a')
    g = tg.TokenTurnGate(1)
    w = runner.GradeWorker(g, threading.RLock(), work, tmp_path, lambda s: (1, False))
    w.last_manifest = sg.manifest(work)
    w.notify(1)
    assert w.queued is None and not g.pending
    w.last_manifest = None
    w.notify(1)
    assert w.queued == 1


def test_f2_grading_worker_death_aborts(tmp_path):
    w = runner.GradeWorker(tg.TokenTurnGate(1), threading.RLock(), tmp_path, tmp_path, lambda s: (1,False))
    w.start()
    w.finish()
    w.closed = False  # dead without a requested shutdown
    with pytest.raises(tg.TransportAbort, match='grading worker'):
        w.check()


@pytest.mark.parametrize('lang,expected', [('python',300),('go',180)])
def test_f13_language_grader_timeouts(tmp_path, lang, expected):
    import subprocess
    class Guard:
        grader_mem_kill = False
        def register_container(self, n): pass
        def container_oom(self, n): return False
        def remove_container(self, n): pass
    def run(cmd, **kw):
        assert kw['timeout'] == expected
        raise subprocess.TimeoutExpired(cmd, expected)
    assert sg.grade(lang, tmp_path, 'test', tmp_path, run=run, guard=Guard()).timed_out


def test_f2_shared_gate_interface():
    g = tg.TokenTurnGate(2)
    g.on_request(1, 81920, 100, 81920)
    g.on_capture(1)
    assert g.decision() is None
    g.on_grade(1, 1, True, False)
    assert g.decision() is None
    g.on_tool_call(('shell', '{"command":"same"}'))
    g.terminal((2, 327680, 100, 81920), (2, 0, True, False))
    assert g.decision() == 'hard_ceiling'


def test_f8_mid_request_post_threshold_known_output():
    g = tg.TokenTurnGate(1)
    s = tg.EventStream(g)
    request(s, output=4, calls=[{}]*7)
    s.accept(event('step_start','m2'))
    s.accept(event('tool_use','m2',partID='last',tool='shell',state={'input':{}}))
    tg.reconcile(s, dict(messages=[assistant(output=4),assistant('m2',17)]),0)
    assert g.report()['post_threshold_tokens_known'] == 17


def test_f3_interrupted_trailing_must_not_carry_usage():
    s = tg.EventStream(tg.TokenTurnGate(1))
    request(s)
    bad = assistant('m2')
    bad['error'] = {'type':'aborted'}
    with pytest.raises(tg.TransportAbort):
        tg.reconcile(s, dict(messages=[assistant(),bad]), -9, 'stalled')


def test_f12_regress_recover_only_new_minimum_progress():
    g = tg.TokenTurnGate(10)
    for j,fail in [(1,8),(2,10),(3,8),(4,7)]:
        g.complete(str(j), usage(1))
        g.grade(j,fail)
        assert g.last_progress_boundary == (1 if j<4 else 4)


def test_f6_go_helper_failure_outside_universe():
    text = '\n'.join(json.dumps(e) for e in [
        dict(Action='pass',Package='exercise',Test='TestOfficial'),
        dict(Action='fail',Package='exercise/helper',Test='TestScratch')])
    result = sg.parse_go(text,1)
    assert result.returncode == 1 and result.failing({('exercise','TestOfficial')}) == 0


def test_f1_exit_hang_requires_finished_session():
    s = tg.EventStream(tg.TokenTurnGate(1))
    s.accept(event('step_start'))
    unfinished = assistant()
    unfinished['finish'] = 'tool-calls'
    with pytest.raises(tg.TransportAbort):
        tg.reconcile(s, dict(messages=[unfinished]), -9, 'client_exit_hang')


def test_terminal_unknown_outcome_refused():
    s = tg.EventStream(tg.TokenTurnGate(1))
    request(s)
    with pytest.raises(tg.TransportAbort):
        tg.reconcile(s, dict(messages=[assistant()]), 17, 'unknown')


def test_f13_unsupported_grader_still_aborts(tmp_path):
    with pytest.raises(tg.TransportAbort, match='unsupported'):
        sg.grade('unsupported', tmp_path, 'test', tmp_path)
