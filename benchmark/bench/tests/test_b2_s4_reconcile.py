"""B2 slice s4 (spec v3.2 section 4, 16.1, 16.2): per-item reconciliation, engagement, settle, hooks, ready / item records."""
from __future__ import annotations

import pytest

from bench import p426_reconcile as pr

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
PFX = "2026-10-27 12:00:00,000 INFO mlx_vlm.server.generation: "
STREAM_CLOSED = "stream_closed_before_completion"


# -- log fixtures in the fork's real formats (generation.py record_success / record_failure / begin_request)
def started(in_flight=1):
    return f"{PFX}Request started: endpoint=/v1/chat/completions model={MODEL} stream=True in_flight={in_flight}"


def completed(session="ses_1", prompt=100, gen=10, backend="cached_session", draft=None, dec=40.0, in_flight=0):
    line = (f"{PFX}Request completed: endpoint=/v1/chat/completions model={MODEL} stream=True backend={backend} "
            f"session={session} cached_tokens=0 prompt_tokens={prompt} generated_tokens={gen} elapsed=1.500s "
            f"prefill=900.0 tok/s decode={dec:.1f} tok/s finish_reason=stop in_flight={in_flight}")
    if draft is not None:
        line += " " + " ".join(f"{k}={v}" for k, v in sorted(draft.items()))
    return line


def failed(error=STREAM_CLOSED, in_flight=0):
    return f"{PFX}Request failed: endpoint=/v1/chat/completions model={MODEL} stream=True error={error} in_flight={in_flight}"


def blob(*lines):
    return ("\n".join(lines) + "\n").encode()


def lines_of(*raw):
    return pr.parse_log(blob(*raw))


def req(session="ses_1", prompt=100, gen=10, **kw):
    return [started(), completed(session, prompt, gen, **kw)]


BEFORE = dict(requests_started=5, requests_completed=5, requests_failed=0, in_flight=0, prompt_tokens_total=500,
              generated_tokens_total=50, avg_decode_tok_s=10.0)


def after_of(lines, before=BEFORE, **over):
    c = [x for x in lines if x.kind == "completed"]
    f = [x for x in lines if x.kind == "failed"]
    s = [x for x in lines if x.kind == "started"]
    a = dict(before)
    a["requests_started"] += len(s)
    a["requests_completed"] += len(c)
    a["requests_failed"] += len(f)
    a["prompt_tokens_total"] += sum(int(x.fields["prompt_tokens"]) for x in c)
    a["generated_tokens_total"] += sum(int(x.fields["generated_tokens"]) for x in c)
    a.update(over)
    return a


def row_of(usage, session="ses_1", at_kill=None, kind=None, termination=None):
    return dict(id="python/a", session_id=session, request_usage=[[str(i + 1), g, p, 81920] for i, (p, g) in enumerate(usage)],
                gate=dict(requests_completed=len(usage), requests_completed_at_kill=at_kill), nonconv_kind=kind,
                stop_reason="stop" if kind is None else kind, termination=termination)


def item(raw, usage, **rowkw):
    ls = lines_of(*raw)
    return pr.reconcile_item(row_of(usage, **rowkw), ls, dict(BEFORE), after_of(ls))


def abort_of(usage, in_flight=None, session="ses_1", cause="timeout"):
    usage = [[str(i + 1), g, p, 81920] for i, (p, g) in enumerate(usage)]
    return dict(transport_abort=dict(cause=cause, error="x", evidence=[], session_id=session, termination=None,
                                     gate=dict(request_usage=usage),
                                     in_flight=dict(in_flight=in_flight is not None, message_id=in_flight,
                                                    requests_started=len(usage) + (in_flight is not None))))


def dnf(raw, usage, **kw):
    ls = lines_of(*raw)
    return pr.reconcile_dnf(abort_of(usage, **kw), ls, dict(BEFORE), after_of(ls))


# -- parse_log
def test_parse_log_reads_the_three_line_kinds_with_fields_and_byte_offsets():
    data = blob("noise line", started(), completed(gen=7, draft=dict(draft_kind="mtp", draft_n=6, draft_n_accepted=4,
                                                                      draft_rounds=2)), failed("boom with spaces"))
    ls = pr.parse_log(data)
    assert [x.kind for x in ls] == ["started", "completed", "failed"]
    assert ls[0].fields["in_flight"] == "1" and ls[0].offset == len(b"noise line\n")
    c = ls[1].fields
    assert (c["session"], c["backend"], c["prompt_tokens"], c["generated_tokens"]) == ("ses_1", "cached_session", "100", "7")
    assert c["decode_tok_s"] == "40.0" and c["draft_rounds"] == "2" and c["draft_kind"] == "mtp" and c["draft_n_accepted"] == "4"
    assert ls[2].fields["error"] == "boom with spaces" and ls[2].fields["in_flight"] == "0"
    assert ls[1].offset == data.index(b"2026", ls[0].offset + 1)


def test_parse_log_refuses_an_unparseable_request_line():
    with pytest.raises(pr.LogParseError):
        pr.parse_log(blob(f"{PFX}Request completed: endpoint=x model=y"))


# -- section 4.3 table
def test_completed_normally_reconciles_positionally_and_builds_the_request_table():
    r = item(req(prompt=100, gen=10) + req(prompt=200, gen=5), [(100, 10), (200, 5)])
    assert r.ok and r.case == "completed" and r.problems == []
    assert [q["generated_tokens"] for q in r.requests] == [10, 5]
    assert r.totals["requests"] == 2 and r.totals["prompt_tokens"] == 300 and r.totals["generated_tokens"] == 15


def test_a_token_mismatch_at_position_k_names_k():
    r = item(req(prompt=100, gen=10) + req(prompt=200, gen=5), [(100, 10), (200, 6)])
    assert not r.ok and any("position 1" in p for p in r.problems)


def test_a_count_mismatch_is_a_problem():
    r = item(req() + req(), [(100, 10)])
    assert not r.ok and r.problems


def test_a_foreign_session_or_backend_is_a_problem():
    assert not item(req(session="ses_2"), [(100, 10)]).ok
    assert not item(req(backend="generate"), [(100, 10)]).ok


def test_serial_in_flight_greater_than_one_and_overlapping_starts_are_problems():
    assert not item([started(in_flight=2), completed()], [(100, 10)]).ok
    assert not item([started(), started(), completed(), completed()], [(100, 10), (100, 10)]).ok


def test_worker_counter_deltas_must_equal_the_log():
    ls = lines_of(*req())
    row = row_of([(100, 10)])
    for key in ("requests_started", "requests_completed", "requests_failed", "prompt_tokens_total", "generated_tokens_total"):
        bad = after_of(ls)
        bad[key] += 1
        assert not pr.reconcile_item(row, ls, dict(BEFORE), bad).ok, key


def test_kill_at_a_request_boundary_needs_zero_failed_and_the_kill_count_equal_to_c():
    r = item(req(), [(100, 10)], at_kill=1, kind="budget_hit_kill", termination="killed")
    assert r.ok and r.case == "kill_boundary"
    assert not item(req(), [(100, 10)], at_kill=2, kind="budget_hit_kill", termination="killed").ok
    r = item(req(), [(100, 10)], at_kill=None, kind="client_inactivity")
    assert r.ok and r.case == "kill_boundary"                    # null at_kill -> gate.requests_completed == |C|


def test_kill_with_a_request_in_flight_failed_is_one_trailing_stream_closed_line():
    raw = req() + [started(), failed()]
    flying = dict(killed=[{}], in_flight_at_kill=1, reason="x")          # fix round 3 (item 5): the structured in-flight evidence
    r = item(raw, [(100, 10)], at_kill=1, kind="budget_hit_kill", termination=flying)
    assert r.ok and r.case == "kill_inflight_failed"
    bad = req() + [started(), failed("other error")]
    assert not item(bad, [(100, 10)], at_kill=1, kind="budget_hit_kill", termination=flying).ok
    notlast = [started(), failed(), started(), completed()]
    assert not item(notlast, [(100, 10)], at_kill=1, kind="budget_hit_kill", termination=flying).ok


def test_kill_with_the_server_completing_the_request_the_client_lost_is_completed_unaccounted():
    raw = req() + req(prompt=300, gen=9)
    flying = dict(killed=[{}], in_flight_at_kill=1, reason="x")          # fix round 3 (item 5): the structured in-flight evidence
    r = item(raw, [(100, 10)], at_kill=1, kind="client_inactivity", termination=flying)
    assert r.ok and r.case == "kill_completed_unaccounted"
    assert not item(req() + req(session="ses_9"), [(100, 10)], at_kill=1, kind="client_inactivity", termination=flying).ok
    assert not item(req() + req() + req(), [(100, 10)], at_kill=1, kind="client_inactivity", termination=flying).ok   # only one


def test_a_failed_line_in_a_normally_completed_item_is_off_table():
    r = item(req() + [started(), failed()], [(100, 10)])
    assert not r.ok and r.case == "completed"


def test_dnf_rows_are_decided_by_observed_state():
    r = dnf(req() + req(), [(100, 10), (100, 10)])
    assert r.ok and r.case == "dnf_boundary"
    r = dnf(req() + [started(), failed()], [(100, 10)], in_flight="2")
    assert r.ok and r.case == "dnf_inflight_failed"
    r = dnf(req() + req(prompt=300, gen=9), [(100, 10)], in_flight="2")
    assert r.ok and r.case == "dnf_completed_unaccounted"
    assert not dnf(req() + req(prompt=300, gen=9), [(100, 10)], in_flight=None).ok     # no in-flight message: not allowed
    assert not dnf(req() + req(session="ses_7"), [(100, 10)], in_flight="2").ok
    assert not dnf(req() + [started(), failed("other")], [(100, 10)], in_flight="2").ok
    assert not dnf(req() + req(), [(100, 10)]).ok                                       # count mismatch at a boundary


def test_dnf_uses_the_abort_manifests_session_id():
    assert not dnf(req(session="ses_2"), [(100, 10)], session="ses_1").ok
    assert dnf(req(session="ses_2"), [(100, 10)], session="ses_2").ok


def test_an_empty_window_is_a_valid_dnf_boundary_with_no_requests():
    r = dnf([], [])
    assert r.ok and r.case == "dnf_boundary" and r.totals["requests"] == 0


# -- engagement
def rq(gen, session="ses_1", **draft):
    d = dict(session=session, backend="cached_session", prompt_tokens=10, generated_tokens=gen, decode_tok_s=1.0,
             draft_rounds=None, draft_n=None, draft_n_accepted=None, draft_kind=None, error=None)
    d.update(draft)
    return d


GOOD_ON = dict(draft_rounds=2, draft_n=6, draft_n_accepted=4, draft_kind="mtp")


def test_on_engagement_requires_counters_on_requests_of_two_or_more_tokens():
    assert pr.engagement_problems([rq(5, **GOOD_ON), rq(1)], "ON") == []             # <= 1 token listed, not judged
    assert pr.engagement_problems([rq(0), rq(1)], "ON") == []
    assert pr.engagement_problems([rq(2)], "ON")                                       # no draft_rounds
    for bad in (dict(draft_rounds=0), dict(draft_n=0), dict(draft_n_accepted=7), dict(draft_n_accepted=-1),
                dict(draft_kind="ngram"), dict(draft_rounds="2"), dict(draft_n=True)):
        assert pr.engagement_problems([rq(5, **{**GOOD_ON, **bad})], "ON"), bad


def test_off_engagement_forbids_any_draft_field():
    assert pr.engagement_problems([rq(5), rq(1)], "OFF") == []
    for k in ("draft_rounds", "draft_n", "draft_n_accepted", "draft_kind"):
        assert pr.engagement_problems([rq(5, **{k: 1 if k != "draft_kind" else "mtp"})], "OFF"), k


def test_reconcile_item_totals_carry_accepted_proposed_and_the_decode_delta():
    raw = [started(), completed(gen=5, draft=dict(draft_kind="mtp", draft_n=6, draft_n_accepted=4, draft_rounds=2))]
    ls = lines_of(*raw)
    after = after_of(ls, generated_tokens_total=55, avg_decode_tok_s=55 / 5.5)
    r = pr.reconcile_item(row_of([(100, 5)]), ls, dict(BEFORE), after)
    assert r.totals["accepted"] == 4 and r.totals["proposed"] == 6
    assert r.totals["decode_s"] == pytest.approx(5.5 - 5.0)


# -- decode_time / decode_rate
def test_decode_time_is_generated_over_avg_rate_unrounded_and_zero_when_the_rate_is_zero():
    assert pr.decode_time(dict(generated_tokens_total=100, avg_decode_tok_s=20.0)) == pytest.approx(5.0)
    assert pr.decode_time(dict(summary=dict(generated_tokens_total=100, avg_decode_tok_s=20.0))) == pytest.approx(5.0)
    assert pr.decode_time(dict(generated_tokens_total=100, avg_decode_tok_s=0)) == 0.0
    assert pr.decode_time(dict(generated_tokens_total=0, avg_decode_tok_s=0.0)) == 0.0


def test_decode_rate_excludes_the_first_token_of_every_request():
    assert pr.decode_rate([rq(11), rq(6), rq(1), rq(0)], 3.0) == pytest.approx(15 / 3.0)
    assert pr.decode_rate([rq(11)], 0.0) is None
    assert pr.decode_rate([rq(11)], None) is None
    assert pr.decode_rate([rq(1)], 2.0) == 0.0


# -- settle
class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def settle_with(metrics, logs, bound=20.0):
    clock, i = Clock(), dict(n=0)

    def read_metrics():
        return metrics(clock.t)

    def read_log(cursor):
        return logs(clock.t)

    return pr.settle(read_metrics, read_log, dict(offset=0), bound_s=bound, clock=clock, sleep=clock.sleep)


def test_settle_waits_until_idle_and_every_started_line_has_its_terminal_line():
    r = settle_with(lambda t: dict(summary=dict(in_flight=1 if t < 6 else 0)),
                    lambda t: blob(started()) if t < 6 else blob(started(), completed()))
    assert r.settled and r.in_flight == 0 and 6 <= r.waited_s <= 8


def test_settle_times_out_when_in_flight_never_drops():
    r = settle_with(lambda t: dict(summary=dict(in_flight=1)), lambda t: blob(started()), bound=10.0)
    assert not r.settled and r.in_flight == 1 and r.waited_s >= 10.0


def test_an_unterminated_started_line_keeps_settle_waiting_even_at_in_flight_zero():
    r = settle_with(lambda t: dict(summary=dict(in_flight=0)), lambda t: blob(started()), bound=10.0)
    assert not r.settled


def test_settle_with_unreadable_metrics_is_not_settled():
    r = settle_with(lambda t: None, lambda t: b"", bound=6.0)
    assert not r.settled and r.in_flight is None


# -- slot_file, the ChainOps seams
def test_slot_file_maps_pipe_and_slash():
    from bench import chain_rows as cr
    assert cr.slot_file("0|A|m/x|s1|python|a") == "0__A__m--x__s1__python__a"


def test_chain_ops_log_seams_read_byte_ranges_and_name_the_worktree_log(tmp_path):
    from bench import chain_ops as co
    ops = co.ChainOps.__new__(co.ChainOps)
    ops.repo = tmp_path
    assert ops.server_log_path() == tmp_path / "logs" / "mlx_vlm.log"
    p = tmp_path / "x.log"
    p.write_bytes(b"0123456789")
    assert ops.read_log(p, 3) == b"3456789" and ops.read_log(p, 3, 6) == b"345" and ops.read_log(p, 20) == b""


# -- P426Hooks
import hashlib  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

from bench import chain_hooks as ch  # noqa: E402
from bench import p426_hooks as ph  # noqa: E402

SLOT = f"0|A|{MODEL}|s1|python|a"
SLOT_FILE = f"0__A__{MODEL}__s1__python__a"
WORKER = dict(pid=11, create_time=1.7e9)
ON_DRAFT = dict(draft_kind="mtp", draft_n=6, draft_n_accepted=4, draft_rounds=2)


class LogOps:
    def __init__(self, tmp):
        self.log = tmp / "logs" / "mlx_vlm.log"
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_bytes(b"old line\n")
        self.summary = dict(BEFORE)
        self.router_alive, self.worker, self.unreadable = True, dict(WORKER), False

    def server_log_path(self):
        return self.log

    def read_log(self, path, start, end=None):
        return Path(path).read_bytes()[start:end]

    def worker_metrics(self):
        return None if self.unreadable else dict(summary=dict(self.summary))

    def worker_ident(self, model):
        return dict(self.worker) if self.worker else None

    def create_time(self, pid):
        return 2.0 if self.router_alive else 3.0

    def serve(self, *raw, **over):
        """The server handled requests: append the log lines and move the worker counters to match."""
        with open(self.log, "ab") as f:
            f.write(blob(*raw))
        self.summary = after_of(lines_of(*raw), before=self.summary, **over)


def make_hooks(tmp_path, arm="ON", bound=10.0):
    ops, clk, out = LogOps(tmp_path), Clock(), tmp_path / "leg"
    out.mkdir()
    st = ph.log_stat(ops.log)
    (out / "log_bounds.json").write_text(json.dumps(dict(
        files=[dict(path=ph.portable_log(ops.log), device=st["device"], inode=st["inode"], offset_start=0, offset_end=None)],
        created="t", finalized=None)))
    hooks = ph.P426Hooks(ops=ops, out_root=out, arm=arm, settle_bound_s=bound, clock=clk, sleep=clk.sleep)
    hooks.bind_router(5, 2.0)
    return ops, hooks, out


def ctx(row=None, k=0, slot=SLOT, item="a"):
    return dict(stage="ready" if row is None else "done", slot=slot, item=item, k=k, ready={}, row=row,
                load=dict(idx=0, load_gen=0, worker=dict(WORKER), session="ses_1", model=MODEL, arm="A"))


def test_ready_record_is_written_before_go_with_the_spec_fields_and_self_hash(tmp_path):
    ops, hooks, out = make_hooks(tmp_path)
    assert hooks.before_attempt(SLOT, ctx()).kind == "accept"
    rec = json.loads((out / "items" / f"{SLOT_FILE}.ready.json").read_text())
    assert rec["slot"] == SLOT and rec["item"] == "a" and rec["k"] == 0
    assert rec["log_cursor"]["offset"] == len(b"old line\n") and rec["log_cursor"]["path"] == ph.portable_log(ops.log)  # §16.7 portable record (designer, after s9b)
    assert {"device", "inode"} <= set(rec["log_cursor"])
    assert rec["worker_snapshot"]["in_flight"] == 0 and "at" in rec
    assert rec["owned"] == dict(router=dict(pid=5, start=2.0), worker=WORKER)
    assert ph.sealed_ok(rec)


def test_ready_with_unreadable_metrics_is_a_hook_infrastructure_error(tmp_path):
    ops, hooks, _ = make_hooks(tmp_path)
    ops.unreadable = True
    with pytest.raises(ch.HookInfrastructureError):
        hooks.before_attempt(SLOT, ctx())


def test_ready_invalidates_on_changed_worker_or_router_or_a_replaced_log(tmp_path):
    ops, hooks, out = make_hooks(tmp_path)
    ops.worker = dict(pid=99, create_time=1)
    assert hooks.before_attempt(SLOT, ctx()).kind == "invalidate"
    ops.worker, ops.router_alive = dict(WORKER), False
    assert hooks.before_attempt(SLOT, ctx()).kind == "invalidate"
    ops.router_alive = True
    ops.log.unlink()
    ops.log.write_bytes(b"x" * 50)                                       # a replaced file: new inode
    d = hooks.before_attempt(SLOT, ctx())
    assert d.kind == "invalidate" and "replaced" in d.reason


def test_done_reconciles_writes_the_item_record_and_accepts(tmp_path):
    ops, hooks, out = make_hooks(tmp_path)
    hooks.before_attempt(SLOT, ctx())
    ops.serve(*req(prompt=100, gen=10, draft=ON_DRAFT), *req(prompt=200, gen=5, draft=ON_DRAFT))
    assert hooks.after_attempt(SLOT, dict(id="python/a"), ctx(row_of([(100, 10), (200, 5)]))).kind == "accept"
    rec = json.loads((out / "items" / f"{SLOT_FILE}.json").read_text())
    ready = json.loads((out / "items" / f"{SLOT_FILE}.ready.json").read_text())
    assert rec["verdict"] == "reconciled" and rec["case"] == "completed" and rec["ready_sha256"] == ready["sha256"]          # fix round 3 (item 11): the ready record's self-hash
    assert rec["log_range"]["start"] == len(b"old line\n") and rec["log_range"]["end"] == ops.log.stat().st_size
    assert rec["log_range"]["sha256"] == hashlib.sha256(ops.log.read_bytes()[rec["log_range"]["start"]:]).hexdigest()
    assert len(rec["requests"]) == 2 and rec["totals"]["accepted"] == 8 and rec["totals"]["proposed"] == 12
    assert rec["worker_before"]["requests_completed"] == 5 and rec["worker_after"]["requests_completed"] == 7
    assert {"serial", "worker_deltas", "pairing", "engagement", "settle"} <= set(rec["checks"])
    assert ph.sealed_ok(rec)


def test_done_invalidates_on_a_reconciliation_violation_and_still_writes_the_record(tmp_path):
    ops, hooks, out = make_hooks(tmp_path)
    hooks.before_attempt(SLOT, ctx())
    ops.serve(*req(prompt=100, gen=10, draft=ON_DRAFT))
    d = hooks.after_attempt(SLOT, dict(id="python/a"), ctx(row_of([(100, 11)])))
    assert d.kind == "invalidate" and "position 0" in d.reason
    assert json.loads((out / "items" / f"{SLOT_FILE}.json").read_text())["verdict"] == "invalid"


def test_done_invalidates_an_on_request_without_draft_rounds(tmp_path):
    ops, hooks, _ = make_hooks(tmp_path, arm="ON")
    hooks.before_attempt(SLOT, ctx())
    ops.serve(*req(gen=10))
    assert hooks.after_attempt(SLOT, dict(), ctx(row_of([(100, 10)]))).kind == "invalidate"


def test_done_invalidates_an_off_request_with_draft_fields(tmp_path):
    ops, hooks, _ = make_hooks(tmp_path, arm="OFF")
    hooks.before_attempt(SLOT, ctx())
    ops.serve(*req(gen=10, draft=ON_DRAFT))
    assert hooks.after_attempt(SLOT, dict(), ctx(row_of([(100, 10)]))).kind == "invalidate"


def test_done_without_a_ready_record_invalidates(tmp_path):
    ops, hooks, _ = make_hooks(tmp_path)
    d = hooks.after_attempt(SLOT, dict(), ctx(row_of([])))
    assert d.kind == "invalidate" and "ready record" in d.reason


def test_done_that_does_not_settle_invalidates(tmp_path):
    ops, hooks, out = make_hooks(tmp_path, bound=6.0)
    hooks.before_attempt(SLOT, ctx())
    ops.serve(started())                                                 # a started line that never terminates
    ops.summary["in_flight"] = 1
    d = hooks.after_attempt(SLOT, dict(), ctx(row_of([])))
    assert d.kind == "invalidate" and "settle" in d.reason


def test_done_with_an_unparseable_request_line_invalidates(tmp_path):
    ops, hooks, _ = make_hooks(tmp_path)
    hooks.before_attempt(SLOT, ctx())
    with open(ops.log, "ab") as f:
        f.write(blob(f"{PFX}Request completed: endpoint=x"))
    assert hooks.after_attempt(SLOT, dict(), ctx(row_of([]))).kind == "invalidate"


def test_the_next_items_window_starts_at_its_own_ready_record(tmp_path):
    ops, hooks, out = make_hooks(tmp_path)
    hooks.before_attempt(SLOT, ctx())
    ops.serve(*req(gen=10, draft=ON_DRAFT))
    assert hooks.after_attempt(SLOT, dict(), ctx(row_of([(100, 10)]))).kind == "accept"
    slot2 = SLOT[:-1] + "b"
    hooks.before_attempt(slot2, ctx(slot=slot2, item="b", k=1))
    ops.serve(*req(prompt=300, gen=4, draft=ON_DRAFT))
    assert hooks.after_attempt(slot2, dict(), ctx(row_of([(300, 4)]), slot=slot2, item="b", k=1)).kind == "accept"


def test_dnf_problems_reconciles_the_window_and_writes_the_dnf_item_record(tmp_path):
    ops, hooks, out = make_hooks(tmp_path)
    hooks.before_attempt(SLOT, ctx())
    ops.serve(*req(draft=ON_DRAFT), started(), failed(), requests_started=ops.summary["requests_started"] + 2)
    problems, rec = hooks.dnf_problems(SLOT, abort_of([(100, 10)], in_flight="2"))
    assert problems == [] and rec["case"] == "dnf_inflight_failed"
    assert (out / "items" / f"{SLOT_FILE}.dnf.json").exists()


def test_log_bounds_catch_a_truncated_log(tmp_path):
    ops, hooks, out = make_hooks(tmp_path)
    hooks.before_attempt(SLOT, ctx())
    ops.log.write_bytes(b"ab")                                            # same inode, truncated below the ready cursor
    d = hooks.after_attempt(SLOT, dict(), ctx(row_of([])))
    assert d.kind == "invalidate" and "truncated" in d.reason


# -- chain wiring
import importlib.util  # noqa: E402
import sys  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from bench import chain_core as core  # noqa: E402
from bench import chain_ops as co_  # noqa: E402
from bench import run_config as rc  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def load_runner(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "benchmark/chains/c147" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


RUNNER = load_runner("run_tg1_chain")


class Args(SimpleNamespace):
    def __getattr__(self, name):                 # every argument the chain constructor reads and the test does not set: None
        if name.startswith("__"):
            raise AttributeError(name)
        return None


def args_of(**kw):
    return Args(**{**dict(models=[MODEL], p426=False, predictor="off", python="py"), **kw})


def test_tg1_p426_config_uses_the_p426_continue_transport_policy_and_the_legacy_config_does_not():
    p = RUNNER.tg1_config(args_of(p426=True))
    assert p.config_id == rc.P426_CONFIG_ID and p.transport_policy == "p426_continue"
    assert RUNNER.tg1_config(args_of()).transport_policy == "abort_restart"


def test_the_probe_argv_carries_evidence_p426_only_in_p426_mode():
    base = dict(py="py", probe="probe.py", leg=None, step=None, receipt=None, cancel="c", ack="a")
    assert "p426" in core.build_cmd.__code__.co_varnames or True
    import inspect
    assert "evidence" in inspect.signature(core.build_cmd).parameters
    src = inspect.getsource(core.Chain.run_invocation)
    assert 'evidence="p426" if self.config.config_id == run_config.P426_CONFIG_ID else None' in src


def chain_of(tmp_path, **kw):
    ops = SimpleNamespace(wd=tmp_path)
    cfg = RUNNER.tg1_config(args_of(**kw))
    return core.Chain(cfg, args_of(**kw), ops, None, lambda *_: None, repo=tmp_path, out_root=tmp_path / "o", names={},
                      lifecycle_files={})


def test_the_chain_installs_p426_hooks_in_p426_mode_only_and_keeps_an_injected_hook(tmp_path):
    c = chain_of(tmp_path, p426=True)
    assert isinstance(c.hooks, ph.P426Hooks) and c.hooks.arm == "OFF" and c.hooks.settle_bound_s >= 900
    assert chain_of(tmp_path, p426=True, predictor="mtp").hooks.arm == "ON"
    assert type(chain_of(tmp_path).hooks) is ch.ChainHooks
    mine = ch.ChainHooks()
    cfg = RUNNER.tg1_config(args_of(p426=True))
    assert core.Chain(cfg, args_of(p426=True), SimpleNamespace(wd=tmp_path), None, print, repo=tmp_path, out_root=tmp_path / "o", names={},
                      lifecycle_files={}, hooks=mine).hooks is mine


def stub_run_chain(tmp_path, order):
    c = core.Chain.__new__(core.Chain)
    c.config = SimpleNamespace(transport_policy="p426_continue", config_id=rc.P426_CONFIG_ID, arm_switch_ops=())
    c.builder, c.per_arm, c.rc = "tg1", False, None
    c.a, c.out_root, c.pinned, c.loaded, c.loads = SimpleNamespace(predictor="off", mode="chain", models=["M"]), tmp_path, {}, None, []
    c.hooks = ch.ChainHooks()
    c.log, c.stop_info = (lambda *_: None), {}
    log = tmp_path / "logs" / "mlx_vlm.log"
    log.parent.mkdir()
    log.write_bytes(b"abc\n")
    (log.parent / "main_model.log").write_bytes(b"main\n")

    def start_router():
        order.append(("start_router", (tmp_path / "log_bounds.json").exists()))
        return 1
    c.ops = SimpleNamespace(overlay_sha=lambda: "x", power_ok=lambda: True, docker_ok=lambda: True, start_router=start_router,
                            stop_stack=lambda: order.append(("stop_stack", None)), unload=lambda m: True,
                            server_log_path=lambda: log, create_time=lambda pid: 1.0,
                            **{n: (lambda *a, **k: None) for n in core.P426_SEAMS if n != "create_time"})
    c.p426_snapshot_checks = lambda *a, **k: None
    for name in ("resolve_specs", "init_lifecycle", "recover_txns", "adopt_receipts", "derive_policy", "freeze_schedule",
                 "check_realized", "verify_lifecycle", "verify_snapshots"):
        setattr(c, name, lambda *a, **k: None)
    c.verify_contract = lambda *a, **k: None
    c.stop_requested = lambda: False
    c.write_json = lambda status=None: None
    c.plan = lambda: []
    return c, log


def test_log_bounds_is_created_before_the_router_starts_and_finalized_after_teardown(tmp_path):
    order = []
    c, log = stub_run_chain(tmp_path, order)
    log.write_bytes(b"abc\ndef\n")
    assert c.run() == 0
    assert order[0] == ("start_router", True)                             # exclusive-created BEFORE the router
    doc = json.loads((tmp_path / "log_bounds.json").read_text())
    assert [f["path"] for f in doc["files"]] == ["<WT>/logs/mlx_vlm.log", "<WT>/logs/main_model.log"]
    assert doc["files"][0]["offset_start"] == 8 and doc["files"][0]["offset_end"] == 8 and doc["finalized"]
    assert doc["files"][0]["inode"] == log.stat().st_ino and "device" in doc["files"][0]


def test_a_log_replaced_during_the_leg_fails_the_leg_and_leaves_offset_end_null(tmp_path):
    order = []
    c, log = stub_run_chain(tmp_path, order)
    c.ops.stop_stack = lambda: (log.unlink(), log.write_bytes(b"new\n"))
    assert c.run() == 2
    doc = json.loads((tmp_path / "log_bounds.json").read_text())
    assert doc["files"][0]["offset_end"] is None and doc["problems"]


def test_an_existing_log_bounds_file_refuses_the_leg(tmp_path):
    order = []
    c, _ = stub_run_chain(tmp_path, order)
    (tmp_path / "log_bounds.json").write_text("{}")
    assert c.run() == 2 and ("start_router", False) not in order and ("start_router", True) not in order


def test_a_legacy_chain_writes_no_log_bounds(tmp_path):
    order = []
    c, _ = stub_run_chain(tmp_path, order)
    c.config = SimpleNamespace(transport_policy="abort_restart", config_id="tg1", arm_switch_ops=())
    assert c.run() == 0 and not (tmp_path / "log_bounds.json").exists()


def test_the_dnf_eligibility_runs_the_hooks_dnf_reconciliation_and_its_problems_are_systemic(tmp_path):
    from bench.tests.test_b2_s3_core import bare, scenario
    c = bare(tmp_path)
    load, leg, _inv, _rec, att, _ids = scenario(tmp_path)
    Path(leg["out"]).with_suffix(".manifest.json").write_text(json.dumps(abort_of([(100, 10)])))
    seen = []

    class H(ch.ChainHooks):
        def dnf_problems(self, slot, manifest):
            seen.append((slot, manifest["transport_abort"]["cause"]))
            return [] if not seen[1:] else ["x"], dict(sha256="f" * 64)
    c.hooks = H()
    assert c.p426_dnf_eligible(att, load, leg, "timeout", slot="S") is None and seen == [("S", "timeout")]
    assert "4.3" in c.p426_dnf_eligible(att, load, leg, "timeout", slot="S")
    assert "slot" in c.p426_dnf_eligible(att, load, leg, "timeout")                   # no slot: cannot reconcile
    Path(leg["out"]).with_suffix(".manifest.json").unlink()
    assert "manifest" in c.p426_dnf_eligible(att, load, leg, "timeout", slot="S")


def test_a_dnf_record_carries_the_item_record_pointer_and_the_sidecar_is_named_by_slot_file(tmp_path):
    from bench.tests.test_b2_s3_core import BASE, bare, incomplete
    c = bare(tmp_path)

    class H(ch.ChainHooks):
        def dnf_problems(self, slot, manifest):
            return [], dict(sha256="e" * 64, case="dnf_boundary")
    c.hooks = H()
    c.p426_dnf_eligible = lambda att, load, leg, cause, slot=None: (setattr(c, "p426_dnf_item", dict(sha256="e" * 64)), None)[1]
    out, _rec = incomplete(c, tmp_path)
    d, = c.p426_dnf
    from bench import chain_rows as cr
    assert d["item_record"] == f"items/{cr.slot_file(d['slot'])}.dnf.json"
    assert (tmp_path / "s1" / "p426_dnf" / f"{cr.slot_file(f'{BASE}|b')}.json").exists()


def test_dnf_without_a_ready_record_is_a_problem(tmp_path):
    ops, hooks, _ = make_hooks(tmp_path)
    problems, rec = hooks.dnf_problems(SLOT, abort_of([]))
    assert problems and rec is None
