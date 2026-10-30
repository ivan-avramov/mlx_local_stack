"""P426 B2 frozen tests, s4 reconcile (spec v3.2 §4, §16.2 `bench.p426_reconcile` / `bench.p426_hooks`, §16.4 inputs).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour.
Unit level through the named API: `parse_log`, `reconcile_item`, `reconcile_dnf`, `engagement_problems`, `settle`,
`decode_time`, `decode_rate`, `a4_window_problems`, and `P426Hooks(ops=…, …)` with the §16.4 hook context over the FakeOps
seams. Inputs are in the real formats (`b2_frozen_support`: fork log lines, `/metrics` summary dicts as the ready record
stores them, real tg1 / P371-golden rows, the §16.1 abort manifest). `arm` is `off` / `on` (§16.4)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bench.tests import b2_frozen_support as S

USAGE = [["msg_a", 137, 2966, 81920], ["msg_b", 69, 14555, 81920], ["msg_c", 364, 14698, 81920]]
SESSION = "ses_ed2e0f549ffeUD36lJn9litWF4"
BEFORE = S.summary(started=10, completed=10, prompt_total=50000, generated_total=4000, decode_s=80.0)


def R4():
    from bench import p426_reconcile
    return p426_reconcile


def row(usage=USAGE, session=SESSION, **over):
    r = S.real_row()
    r.update(session_id=session, request_usage=[list(u) for u in usage], nonconv_kind=None, stop_reason="completed")
    r["gate"] = dict(r["gate"], requests_completed=len(usage), requests_completed_at_kill=None)
    r.update(over)
    return r


def lines_of(text_lines):
    return R4().parse_log(S.window(text_lines))


def after(usage=USAGE, **kw):
    return S.counters_after(BEFORE, usage, decode_s=kw.pop("decode_s", 80.0 + sum(u[1] for u in usage) / 50.0), **kw)


def outcome(fn, *a):
    """The report, or the exception a refusing implementation raised (both are acceptable 'not ok')."""
    try:
        return fn(*a)
    except Exception as e:  # noqa: BLE001
        return e


def not_ok(rep):
    return isinstance(rep, Exception) or (rep.ok is False and rep.problems)


# ------------------------------------------------------------------------------------------------ parse_log
def test_new_parse_log_returns_the_request_lines_with_their_fields_and_byte_offsets():
    noise = "2026-10-22 15:48:06,000 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/x \"HTTP/1.1 200 OK\""
    text = [noise] + S.item_window(SESSION, USAGE[:1]) + [S.failed_line()]
    data = S.window(text)
    got = R4().parse_log(data)
    assert [ln.kind for ln in got] == ["started", "completed", "failed"]
    assert got[1].fields["session"] == SESSION and int(got[1].fields["prompt_tokens"]) == 2966
    assert int(got[1].fields["generated_tokens"]) == 137 and got[1].fields["backend"] == "cached_session"
    assert got[2].fields["error"] == "stream_closed_before_completion"
    starts = [len(S.window(text[:i])) for i in range(1, 4)]
    assert [ln.offset for ln in got] == starts


def test_new_parse_log_reads_the_drafter_counters_of_a_completed_line():
    line = S.completed_line(session=SESSION, prompt_tokens=99, generated_tokens=1265, draft=S.draft_counters(513, 1026, 751),
                            verify=S.VERIFY_ON)
    (ln,) = R4().parse_log(S.window([line]))
    assert ln.fields["draft_kind"] == "mtp" and int(ln.fields["draft_n"]) == 1026
    assert int(ln.fields["draft_n_accepted"]) == 751 and int(ln.fields["draft_rounds"]) == 513


# ------------------------------------------------------------------------------------------------ reconcile_item: green
def test_new_a_normally_completed_item_reconciles_positionally():
    rep = R4().reconcile_item(row(), lines_of(S.item_window(SESSION, USAGE)), BEFORE, after())
    assert rep.ok is True and rep.case == "completed" and not rep.problems
    assert rep.totals["requests"] == 3 and rep.totals["prompt_tokens"] == sum(u[2] for u in USAGE)
    assert rep.totals["generated_tokens"] == sum(u[1] for u in USAGE)
    assert [r["session"] for r in rep.requests] == [SESSION] * 3


def _kill_row(**term):
    r = S.golden_row("item_stall_kill")                       # 5 requests completed at the kill, at a boundary
    r["termination"] = dict(r["termination"], **term)
    return r


def _kill_usage(r):
    return r["request_usage"]


def test_new_a_probe_kill_at_a_request_boundary_reconciles():
    r = _kill_row()
    u = _kill_usage(r)
    rep = R4().reconcile_item(r, lines_of(S.item_window(r["session_id"], u)), BEFORE, after(u))
    assert rep.ok is True and rep.case == "kill_boundary"


def test_new_a_probe_kill_with_a_request_in_flight_the_server_failed_reconciles():
    r = _kill_row(in_flight_at_kill=1)
    u = _kill_usage(r)
    lines = S.item_window(r["session_id"], u) + [S.started_line(), S.failed_line()]
    rep = R4().reconcile_item(r, lines_of(lines), BEFORE, after(u, failed=1))
    assert rep.ok is True and rep.case == "kill_inflight_failed"


def test_new_a_probe_kill_with_a_request_the_server_completed_reconciles_as_completed_unaccounted():
    r = _kill_row(in_flight_at_kill=1)
    u = _kill_usage(r)
    extra = ["msg_x", 12, 200, 81920]
    lines = S.item_window(r["session_id"], u + [extra])
    rep = R4().reconcile_item(r, lines_of(lines), BEFORE, after(u + [extra]))
    assert rep.ok is True and rep.case == "kill_completed_unaccounted"


def test_new_client_inactivity_reconciles_on_requests_completed():
    r = S.golden_row("item_client_inactivity")               # requests_completed_at_kill null -> requests_completed
    u = r["request_usage"]
    rep = R4().reconcile_item(r, lines_of(S.item_window(r["session_id"], u)), BEFORE, after(u))
    assert rep.ok is True


# ------------------------------------------------------------------------------------------------ reconcile_item: red
def _red(lines, aft=None, r=None):
    return outcome(R4().reconcile_item, r or row(), lines_of(lines), BEFORE, aft or after())


def test_fix_a_missing_completed_request_is_a_count_mismatch():
    rep = _red(S.item_window(SESSION, USAGE[:2]), after(USAGE[:2]))
    assert not_ok(rep)


def test_fix_a_token_count_that_differs_from_the_client_is_a_mismatch():
    served = [list(u) for u in USAGE]
    served[1][1] += 1
    assert not_ok(_red(S.item_window(SESSION, served), after(served)))


def test_fix_a_prompt_count_that_differs_from_the_client_is_a_mismatch():
    served = [list(u) for u in USAGE]
    served[2][2] -= 3
    assert not_ok(_red(S.item_window(SESSION, served), after(served)))


def test_fix_requests_in_another_order_do_not_pair():
    served = [USAGE[1], USAGE[0], USAGE[2]]
    assert not_ok(_red(S.item_window(SESSION, served), after(served)))


def test_fix_a_completed_line_of_another_session_is_not_attributable():
    lines = S.item_window(SESSION, USAGE[:2]) + S.item_window("ses_other0000000000000000000", USAGE[2:], start=4)
    assert not_ok(_red(lines))


def test_fix_a_request_off_the_cached_session_path_is_a_mismatch():
    lines = S.item_window(SESSION, USAGE)
    lines[3] = lines[3].replace("backend=cached_session", "backend=continuous_batching")
    assert not_ok(_red(lines))


def test_fix_overlapping_requests_break_the_serial_rule():
    lines = S.item_window(SESSION, USAGE)
    lines[2] = lines[2].replace("in_flight=1", "in_flight=2")
    assert not_ok(_red(lines))


def test_fix_a_start_before_the_previous_terminal_line_breaks_the_serial_rule():
    lines = S.item_window(SESSION, USAGE)
    lines[1], lines[2] = lines[2], lines[1]                    # started, started, completed, completed, ...
    assert not_ok(_red(lines))


@pytest.mark.parametrize("field,delta", [("requests_started", 1), ("requests_completed", 1), ("requests_failed", 1),
                                         ("prompt_tokens_total", 7), ("generated_tokens_total", -2)])
def test_fix_a_worker_delta_that_differs_from_the_window_is_a_mismatch(field, delta):
    aft = after()
    aft[field] += delta
    assert not_ok(_red(S.item_window(SESSION, USAGE), aft))


def test_fix_a_failed_line_on_a_normally_completed_item_is_off_table():
    lines = S.item_window(SESSION, USAGE) + [S.started_line(), S.failed_line()]
    assert not_ok(_red(lines, after(failed=1)))


def test_fix_a_kill_failed_line_that_is_not_the_last_line_is_off_table():
    r = _kill_row(in_flight_at_kill=1)
    u = _kill_usage(r)
    lines = S.item_window(r["session_id"], u[:4]) + [S.started_line(), S.failed_line()] + S.item_window(r["session_id"], u[4:])
    assert not_ok(_red(lines, after(u, failed=1), r))


def test_fix_a_kill_failed_line_with_another_error_is_off_table():
    r = _kill_row(in_flight_at_kill=1)
    u = _kill_usage(r)
    lines = S.item_window(r["session_id"], u) + [S.started_line(), S.failed_line(error="RuntimeError: boom")]
    assert not_ok(_red(lines, after(u, failed=1), r))


def test_fix_two_failed_lines_are_off_table():
    r = _kill_row(in_flight_at_kill=1)
    u = _kill_usage(r)
    lines = S.item_window(r["session_id"], u) + [S.started_line(), S.failed_line(), S.started_line(), S.failed_line()]
    assert not_ok(_red(lines, after(u, failed=2), r))


def test_fix_a_kill_whose_completed_count_differs_from_the_gate_is_off_table():
    r = _kill_row()
    r["gate"]["requests_completed_at_kill"] = 4
    u = _kill_usage(r)
    assert not_ok(_red(S.item_window(r["session_id"], u), after(u), r))


def test_fix_an_unparseable_complete_request_line_raises():
    lines = S.item_window(SESSION, USAGE)
    lines.insert(2, S._prefix(S.ts(50)) + "Request completed: endpoint=/chat/completions model=")
    with pytest.raises(ValueError):
        R4().parse_log(S.window(lines))


def test_new_a_trailing_partial_line_yields_no_entry():
    data = S.window(S.item_window(SESSION, USAGE[:1])) + (S._prefix(S.ts(9)) + "Request started: endpoint=/chat").encode()
    got = R4().parse_log(data)
    assert [ln.kind for ln in got] == ["started", "completed"]


def test_new_log_field_values_are_strings_as_logged():
    (ln,) = R4().parse_log(S.window([S.completed_line(session=SESSION, prompt_tokens=99, generated_tokens=7)]))
    assert ln.fields["prompt_tokens"] == "99" and ln.fields["generated_tokens"] == "7"


# ------------------------------------------------------------------------------------------------ reconcile_dnf
D_SESSION = "ses_dnf00000000000000000000000"


def test_new_a_dnf_at_a_request_boundary_reconciles():
    m = S.abort_manifest(USAGE[:2])
    rep = R4().reconcile_dnf(m, lines_of(S.item_window(D_SESSION, USAGE[:2])), BEFORE, after(USAGE[:2]))
    assert rep.ok is True and rep.case == "dnf_boundary"


def test_new_a_dnf_with_a_request_in_flight_the_server_failed_reconciles():
    m = S.abort_manifest(USAGE[:2], in_flight="msg_c")
    lines = S.item_window(D_SESSION, USAGE[:2]) + [S.started_line(), S.failed_line()]
    rep = R4().reconcile_dnf(m, lines_of(lines), BEFORE, after(USAGE[:2], failed=1))
    assert rep.ok is True and rep.case == "dnf_inflight_failed"


def test_new_a_dnf_whose_in_flight_request_the_server_completed_is_completed_unaccounted():
    m = S.abort_manifest(USAGE[:2], in_flight="msg_c")
    rep = R4().reconcile_dnf(m, lines_of(S.item_window(D_SESSION, USAGE)), BEFORE, after(USAGE))
    assert rep.ok is True and rep.case == "dnf_completed_unaccounted"


def test_fix_a_dnf_boundary_with_a_missing_completed_line_is_systemic():
    m = S.abort_manifest(USAGE[:2])
    assert not_ok(outcome(R4().reconcile_dnf, m, lines_of(S.item_window(D_SESSION, USAGE[:1])), BEFORE, after(USAGE[:1])))


def test_fix_a_dnf_window_of_another_session_is_systemic():
    m = S.abort_manifest(USAGE[:2])
    lines = S.item_window("ses_other0000000000000000000", USAGE[:2])
    assert not_ok(outcome(R4().reconcile_dnf, m, lines_of(lines), BEFORE, after(USAGE[:2])))


def test_fix_a_kill_with_a_trailing_failed_line_but_no_in_flight_marker_is_off_table():
    """post-reveal 3h (§16.8 after the strict verify round 1): the in-flight cases need the structured in-flight marker; a kill
    derives it from the kill evidence (`termination.in_flight_at_kill`). Without it a trailing failed line is off-table."""
    r = _kill_row()                                              # the boundary kill: no request in flight at the kill
    u = _kill_usage(r)
    lines = S.item_window(r["session_id"], u) + [S.started_line(), S.failed_line()]
    assert not_ok(_red(lines, after(u, failed=1), r))


def test_fix_a_dnf_with_a_trailing_failed_line_but_no_in_flight_marker_is_systemic():
    """post-reveal 3h (§16.8): the abort manifest's structured in-flight marker is required for `dnf_inflight_failed`."""
    m = S.abort_manifest(USAGE[:2])                               # no in-flight message
    lines = S.item_window(D_SESSION, USAGE[:2]) + [S.started_line(), S.failed_line()]
    assert not_ok(outcome(R4().reconcile_dnf, m, lines_of(lines), BEFORE, after(USAGE[:2], failed=1)))


def test_fix_a_dnf_with_two_trailing_unaccounted_completions_is_systemic():
    m = S.abort_manifest(USAGE[:1], in_flight="msg_b")
    assert not_ok(outcome(R4().reconcile_dnf, m, lines_of(S.item_window(D_SESSION, USAGE)), BEFORE, after(USAGE)))


# ------------------------------------------------------------------------------------------------ engagement (§4.4)
def _requests(drafts, generated=(137, 69, 364)):
    usage = [[f"m{i}", g, 3000 + i, 81920] for i, g in enumerate(generated)]
    lines = []
    for i, (u, d) in enumerate(zip(usage, drafts)):
        lines += [S.started_line(at=S.ts(2 * i)),
                  S.completed_line(at=S.ts(2 * i + 1), session=SESSION, prompt_tokens=u[2], generated_tokens=u[1],
                                   draft=d, verify=S.VERIFY_ON if d else None)]
    rep = R4().reconcile_item(row(usage), R4().parse_log(S.window(lines)), BEFORE, after(usage))
    return rep.requests


GOOD = S.draft_counters(20, 40, 30)


def test_new_on_requests_with_sane_drafter_counters_are_engaged():
    assert R4().engagement_problems(_requests([GOOD, GOOD, GOOD]), "on") == []


@pytest.mark.parametrize("bad", [None, S.draft_counters(20, 0, 0), S.draft_counters(0, 40, 30),
                                 S.draft_counters(20, 40, 41), S.draft_counters(20, 40, 30, kind="suffix"),
                                 dict(GOOD, draft_rounds="1.5"), dict(GOOD, draft_n="4e1")])
def test_fix_an_on_request_without_sane_drafter_counters_is_a_violation(bad):
    assert R4().engagement_problems(_requests([GOOD, bad, GOOD]), "on")


def test_new_a_one_token_on_request_is_exempt_from_judgement():
    assert R4().engagement_problems(_requests([GOOD, None, GOOD], generated=(137, 1, 364)), "on") == []


def test_fix_an_off_request_with_a_draft_field_is_a_violation():
    assert R4().engagement_problems(_requests([None, GOOD, None]), "off")


def test_new_off_requests_without_draft_fields_pass():
    assert R4().engagement_problems(_requests([None, None, None]), "off") == []


# ------------------------------------------------------------------------------------------------ decode time and rate (§4.1, §8)
def test_new_decode_time_is_generated_over_the_average_rate_and_zero_without_one():
    assert R4().decode_time(S.summary(completed=4, generated_total=1000, decode_s=40.0)) == pytest.approx(40.0)
    assert R4().decode_time(S.summary()) == 0.0


def test_new_decode_rate_excludes_each_requests_first_token_and_lists_zero_and_one_token_requests():
    reqs = [dict(generated_tokens=137), dict(generated_tokens=0), dict(generated_tokens=1), dict(generated_tokens=69)]
    assert R4().decode_rate(reqs, 10.0) == pytest.approx((136 + 0 + 0 + 68) / 10.0)
    assert R4().decode_rate(reqs, 0.0) is None


# ------------------------------------------------------------------------------------------------ settle (§4.2)
class Clock:
    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


CURSOR = {"path": "<WT>/logs/mlx_vlm.log", "device": 1, "inode": 2, "offset": 0}


def test_new_settle_waits_until_nothing_is_in_flight_and_every_start_has_its_terminal_line():
    c = Clock()
    flights = iter([1, 1, 0, 0, 0, 0])
    data = S.window(S.item_window(SESSION, USAGE[:1]))
    res = R4().settle(lambda: S.summary(in_flight=next(flights)), lambda *a, **k: data, CURSOR, bound_s=900.0,
                      clock=c.clock, sleep=c.sleep)
    assert res.settled is True and res.in_flight == 0
    assert c.sleeps and all(s == pytest.approx(2.0) for s in c.sleeps)


def test_new_a_start_without_its_terminal_line_never_settles_within_the_bound():
    c = Clock()
    data = S.window(S.item_window(SESSION, USAGE[:1]) + [S.started_line()])
    res = R4().settle(lambda: S.summary(), lambda *a, **k: data, CURSOR, bound_s=10.0, clock=c.clock, sleep=c.sleep)
    assert res.settled is False and res.waited_s >= 10.0


def test_new_in_flight_that_never_drains_never_settles_within_the_bound():
    c = Clock()
    res = R4().settle(lambda: S.summary(in_flight=1), lambda *a, **k: b"", CURSOR, bound_s=900.0, clock=c.clock, sleep=c.sleep)
    assert res.settled is False and res.in_flight == 1 and res.waited_s >= 900.0


# ------------------------------------------------------------------------------------------------ the A4 window (§4.3)
A4_SES = "ses_a4000000000000000000000000"
A4_REQS = [(A4_SES, 0, 9000), (A4_SES, 8800, 9100), (A4_SES, 0, 9300), (A4_SES, 9200, 9400)]


A4_ANON = [(f"anon:{i:08x}", 2600 if i == 2 else 0, 3100 + i) for i in range(3)]   # (session, cached, prompt)


def a4_lines(reqs=A4_REQS, anon=A4_ANON):
    """The A4 window in the gate's order (session_pinning_gate.py:288-293): A4 opencode's `ses_*` requests, then A6's
    three `anon:*` requests."""
    lines = []
    for j, (s, c, p) in enumerate(reqs):
        lines += [S.started_line(at=S.ts(2 * j)),
                  S.completed_line(at=S.ts(2 * j + 1), session=s, prompt_tokens=p, generated_tokens=30, cached_tokens=c)]
    for i, (s, c, p) in enumerate(anon):
        lines += [S.started_line(at=S.ts(20 + 2 * i)),
                  S.completed_line(at=S.ts(21 + 2 * i), session=s, prompt_tokens=p, generated_tokens=2, cached_tokens=c)]
    return R4().parse_log(S.window(lines))


def a4_gate(anon=A4_ANON):
    """The A4 run's `gate.json` (§16.5: the `anon:*` requests are checked against it)."""
    return S.a4_gate_doc(S.a4_receipt(A4_REQS), anon)


def test_new_the_a4_window_matches_its_receipt():
    assert R4().a4_window_problems(a4_lines(), S.a4_receipt(A4_REQS), a4_gate()) == []


@pytest.mark.parametrize("mutate", ["prompt", "session", "missing"])
def test_fix_an_a4_window_whose_session_differs_from_its_receipt_is_a_problem(mutate):
    reqs = list(A4_REQS)
    if mutate == "prompt":
        reqs[1] = (A4_SES, 8800, 9101)
    elif mutate == "session":
        reqs[3] = ("ses_other0000000000000000000", 9200, 9400)
    else:
        reqs = reqs[:3]
    assert R4().a4_window_problems(a4_lines(reqs), S.a4_receipt(A4_REQS), a4_gate())


@pytest.mark.parametrize("mutate", ["missing", "prompt", "session"])
def test_fix_an_a4_window_whose_bare_requests_differ_from_gate_json_is_a_problem(mutate):
    anon = list(A4_ANON)
    if mutate == "missing":
        anon = anon[:2]
    elif mutate == "prompt":
        anon[1] = (anon[1][0], anon[1][1], anon[1][2] + 5)
    else:
        anon[2] = ("anon:ffffffff", anon[2][1], anon[2][2])
    assert R4().a4_window_problems(a4_lines(anon=anon), S.a4_receipt(A4_REQS), a4_gate())


# ------------------------------------------------------------------------------------------------ the item record shape
def test_new_the_item_report_carries_the_item_record_tables():
    rep = R4().reconcile_item(row(), lines_of(S.item_window(SESSION, USAGE, draft=lambda i, g: GOOD)), BEFORE, after())
    want = {"session", "backend", "prompt_tokens", "generated_tokens", "decode_tok_s", "draft_rounds", "draft_n",
            "draft_n_accepted", "draft_kind", "error"}
    assert all(want <= set(r) for r in rep.requests) and len(rep.requests) == 3
    assert {"requests", "prompt_tokens", "generated_tokens", "decode_s", "accepted", "proposed"} <= set(rep.totals)
    assert rep.totals["accepted"] == 3 * GOOD["draft_n_accepted"] and rep.totals["proposed"] == 3 * GOOD["draft_n"]
    json.dumps(rep.requests)
    json.dumps(rep.totals)


# ------------------------------------------------------------------------------------------------ P426Hooks (§16.2, §16.4)
def open_log_bounds(env):
    """`<out-root>/log_bounds.json` as the chain exclusive-creates it before the router starts (§4.2, §16.1 two-phase record:
    `offset_end` / `finalized` null until teardown), paths portable (`<WT>/…`, [d2] §11.2)."""
    wt = Path(env["ops"].overlay).parent
    files = []
    for p in (Path(env["ops"].server_log_path()), wt / "logs" / "main_model.log"):
        st = p.stat()
        files.append(dict(path="<WT>/" + p.relative_to(wt).as_posix(), device=st.st_dev, inode=st.st_ino,
                          offset_start=st.st_size, offset_end=None))
    out = Path(env["out"])
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "log_bounds.json", "x") as f:
        json.dump(dict(files=files, created="2026-10-27T00:00:00Z", finalized=None), f)


def hooks(tmp_path, monkeypatch, arm="off"):
    """`P426Hooks(ops=<FakeOps with the §16.2 / §16.4 seams>, out_root, arm, settle_bound_s, clock, sleep)` with a loaded
    fake worker; returns (hooks, env, context-builder, item-runner)."""
    from bench import chain_rows as cr
    from bench import p426_hooks
    env = S.p426_world(tmp_path, monkeypatch, arm=arm)
    ops = env["ops"]
    open_log_bounds(env)                            # 1h: the chain writes it before the router (§4.2), so a leg's hooks see it
    ident = ops.load(S.MODEL)
    c = Clock()
    h = p426_hooks.P426Hooks(ops=ops, out_root=env["out"], arm=arm, settle_bound_s=900.0, clock=c.clock, sleep=c.sleep)
    slot = cr.slot_for(f"tg1-p426|oc|{S.MODEL}|pilot|python", "python/p1")
    load = dict(idx=0, load_gen=0, worker=dict(pid=ident["pid"], create_time=ident["create_time"]), session="pilot",
                model=S.MODEL, arm=arm)

    def ctx(stage, ready=None, row_=None):
        return dict(stage=stage, slot=slot, item="python/p1", k=0, ready=ready, row=row_, load=load)

    def run_item(usage=USAGE, served=None, draft=None):
        """The item's requests as the server sees them: log lines (fork format) + the worker counters."""
        served = served or usage
        with env["log"].open("a") as f:
            f.write(S.window(S.item_window(SESSION, served, draft=draft)).decode())
        m = json.loads(env["metrics"].read_text())["summary"] if env["metrics"].exists() else S.summary()
        env["metrics"].write_text(json.dumps({"summary": S.counters_after(m, served, decode_s=10.0)}))
        return row(usage)
    return h, env, slot, ctx, run_item


def test_new_the_ready_hook_writes_the_ready_record_and_accepts(tmp_path, monkeypatch):
    from bench import chain_rows as cr
    h, env, slot, ctx, run_item = hooks(tmp_path, monkeypatch)
    try:
        env["log"].write_text("x" * 37 + "\n")
        d = h.before_attempt(slot, ctx("ready"))
        assert d.kind == "accept"
        p = Path(env["out"]) / "items" / (cr.slot_file(slot) + ".ready.json")
        doc = json.loads(p.read_text())
        assert doc["slot"] == slot and doc["k"] == 0 and doc["log_cursor"]["offset"] == 38
        assert doc["log_cursor"]["path"] == "<WT>/logs/mlx_vlm.log"            # post-reveal 3f: portable (§16.7)
        assert doc["worker_snapshot"] == env["ops"].worker_metrics()["summary"]
        assert doc["owned"]["worker"]["pid"] == ctx("ready")["load"]["worker"]["pid"]
    finally:
        env["ops"].cancel()


@pytest.mark.parametrize("hook", ["before", "after"])
def test_new_p426_hooks_called_without_a_context_raise_hook_infrastructure_error(tmp_path, monkeypatch, hook):
    """[d2] §16.4 / §16.7: `before_attempt(slot, context=None)` / `after_attempt(slot, done, context=None)`; in P426 mode the
    chain always passes the context, so a call without one raises `HookInfrastructureError` and writes no record."""
    from bench import chain_hooks as ch
    h, env, slot, ctx, run_item = hooks(tmp_path, monkeypatch)
    try:
        with pytest.raises(ch.HookInfrastructureError):
            if hook == "before":
                h.before_attempt(slot)
            else:
                h.after_attempt(slot, dict(id="python/p1", passed=True))
        assert not list(Path(env["out"]).rglob("items/*.json"))
    finally:
        env["ops"].cancel()


def _ready_then_done(tmp_path, monkeypatch, arm="off", **item):
    from bench import chain_rows as cr
    h, env, slot, ctx, run_item = hooks(tmp_path, monkeypatch, arm=arm)
    assert h.before_attempt(slot, ctx("ready")).kind == "accept"
    rp = Path(env["out"]) / "items" / (cr.slot_file(slot) + ".ready.json")
    ready = json.loads(rp.read_text())
    r = run_item(**item)
    done = dict(id="python/p1", attempt_id="python/p1#1.0", passed=True, nonconv_kind=None, evidence={}, receipts=None,
                final_tree=None)
    return h, env, slot, rp, h.after_attempt(slot, done, ctx("done", ready=ready, row_=r))


def test_new_the_done_hook_reconciles_writes_the_item_record_and_accepts(tmp_path, monkeypatch):
    from bench import chain_rows as cr
    h, env, slot, rp, d = _ready_then_done(tmp_path, monkeypatch)
    try:
        assert d.kind == "accept"
        doc = json.loads((Path(env["out"]) / "items" / (cr.slot_file(slot) + ".json")).read_text())
        assert doc["verdict"] == "reconciled" and doc["case"] == "completed" and doc["slot"] == slot
        ready_doc = json.loads(rp.read_text())          # post-reveal 3h (§16.8 / §4.5): the ready record's self-hash
        assert doc["ready_sha256"] == ready_doc["sha256"] == S.self_hashed(ready_doc)["sha256"]
        assert doc["log_range"]["start"] == json.loads(rp.read_text())["log_cursor"]["offset"]
        assert doc["totals"]["requests"] == 3 and all(c["ok"] for c in doc["checks"].values())
    finally:
        env["ops"].cancel()


def test_fix_the_done_hook_invalidates_a_server_count_that_differs_from_the_client(tmp_path, monkeypatch):
    from bench import chain_rows as cr
    served = [list(u) for u in USAGE]
    served[0][1] += 2
    h, env, slot, rp, d = _ready_then_done(tmp_path, monkeypatch, served=served)
    try:
        assert d.kind == "invalidate" and d.reason
        doc = json.loads((Path(env["out"]) / "items" / (cr.slot_file(slot) + ".json")).read_text())
        assert doc["verdict"] == "invalid" and not all(c["ok"] for c in doc["checks"].values())
    finally:
        env["ops"].cancel()


def test_fix_the_done_hook_invalidates_an_on_item_without_drafter_counters(tmp_path, monkeypatch):
    h, env, slot, rp, d = _ready_then_done(tmp_path, monkeypatch, arm="on")
    try:
        assert d.kind == "invalidate"
    finally:
        env["ops"].cancel()


def test_new_the_done_hook_accepts_an_engaged_on_item(tmp_path, monkeypatch):
    h, env, slot, rp, d = _ready_then_done(tmp_path, monkeypatch, arm="on", draft=lambda i, g: GOOD)
    try:
        assert d.kind == "accept"
    finally:
        env["ops"].cancel()


def test_new_an_on_item_with_no_judgeable_request_is_unengaged_never_accepted(tmp_path, monkeypatch):
    """post-reveal 3h (§16.8 after the strict verify round 1): an ON item whose every request is exempt (<= 1 generated
    token) has no judgeable request — `unengaged`, never accepted."""
    from bench import chain_rows as cr
    usage = [[f"m{i}", 1, 3000 + i, 81920] for i in range(3)]
    h, env, slot, rp, d = _ready_then_done(tmp_path, monkeypatch, arm="on", usage=usage)
    try:
        assert d.kind != "accept"
        doc = json.loads((Path(env["out"]) / "items" / (cr.slot_file(slot) + ".json")).read_text())
        assert "unengaged" in json.dumps(doc["checks"]) or "unengaged" in (d.reason or "")
    finally:
        env["ops"].cancel()


def test_new_unreadable_metrics_are_a_hook_infrastructure_error(tmp_path, monkeypatch):
    from bench import chain_hooks as ch
    h, env, slot, ctx, run_item = hooks(tmp_path, monkeypatch)
    try:
        env["ops"].metrics = lambda: None
        with pytest.raises(ch.HookInfrastructureError):
            h.before_attempt(slot, ctx("ready"))
    finally:
        env["ops"].cancel()


def test_new_a_missing_ready_record_at_done_is_systemic(tmp_path, monkeypatch):
    from bench import chain_hooks as ch
    h, env, slot, ctx, run_item = hooks(tmp_path, monkeypatch)
    try:
        r = run_item()
        done = dict(id="python/p1", attempt_id="python/p1#1.0", passed=True, nonconv_kind=None, evidence={})
        try:
            d = h.after_attempt(slot, done, ctx("done", ready=None, row_=r))
        except ch.HookInfrastructureError:
            d = None
        assert d is None or d.kind == "invalidate"
    finally:
        env["ops"].cancel()
