"""P371 phase 1: `bench.worker_receipts` (plan 4 A3): runner side of the worker receipt protocol, the one-to-one join,
the per-class checks, the fake and unavailable sources, and the HTTP client pinned by a protocol fixture."""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from bench import token_turn_gate as tg
from bench import worker_receipts as wr

FIXTURE = Path(__file__).parent / "fixtures/p371_receipt_protocol.json"
PROTOCOL = json.loads(FIXTURE.read_text())
WORKER = dict(pid=4242, create_time=1760000000.25)
SAMPLING = dict(temperature=1.0, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=1.5)
CONTROLS = {c: dict(sampling=SAMPLING, seed=1234567, thinking_budget=81920, max_tokens=102400)
            for c in ("task", "compaction")}
CTX = wr.AttemptContext.make("python|foo", 1)
NO_TOOLS_SHA = None


def req(cls="task", **kw):
    return dict(cls=cls, **kw)


def run(fake, classes, *, ctx=CTX, supports_header=True, controls=None, **kw):
    """start, then `classes` admitted in order, then fence + join."""
    mark = fake.start(ctx)
    for cls in classes:
        fake.admit(cls, header=ctx.header if supports_header else None)
    fence = fake.fence(ctx)
    return mark, fence, wr.join(wr.owned_receipts(mark, fence), [req(c) for c in classes], supports_header=supports_header,
                                ctx=ctx, mark=mark, fence=fence, controls=controls, **kw)


# ---------------------------------------------------------------- context and schema
def test_attempt_context_id_slot_attempt_rerun_and_header():
    ctx = wr.AttemptContext.make("python|foo", 2, rerun_index=1)
    assert ctx.attempt_id == "python|foo#a2.r1" and ctx.slot == "python|foo" and ctx.attempt == 2
    assert ctx.rerun_index == 1 and ctx.header == ctx.attempt_id and wr.ATTEMPT_HEADER == "X-Bench-Attempt"
    assert wr.AttemptContext.make("s", 1) != wr.AttemptContext.make("s", 1, rerun_index=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.slot = "x"
    for bad in (dict(slot="", attempt=1), dict(slot="a\nb", attempt=1), dict(slot="s", attempt=0),
                dict(slot="s", attempt=1, rerun_index=-1)):
        with pytest.raises(ValueError):
            wr.AttemptContext.make(**bad)


def test_receipt_schema_is_exactly_the_a3_field_list():
    assert wr.RECEIPT_FIELDS == (
        "seq", "worker", "attempt_header", "received_mono", "finished_mono", "sampling", "seed", "thinking_budget",
        "max_tokens", "roles", "request_tools_present", "request_tools_sha256", "prompt_tokens", "cache_tokens",
        "completion_tokens", "reasoning_tokens", "disconnected", "terminal")
    assert wr.SAMPLING_FIELDS == ("temperature", "top_p", "top_k", "min_p", "presence_penalty")
    for receipt in PROTOCOL["fence"]["response"]["receipts"]:
        assert set(receipt) == set(wr.RECEIPT_FIELDS)
        wr.validate_receipt(receipt)


@pytest.mark.parametrize("mutate", [
    lambda r: r.pop("seq"), lambda r: r.pop("reasoning_tokens"), lambda r: r.update(extra=1),
    lambda r: r.update(seq=0), lambda r: r.update(seq=True), lambda r: r.update(worker=dict(pid=1)),
    lambda r: r.update(worker=dict(pid="1", create_time=1.0)), lambda r: r.update(attempt_header=5),
    lambda r: r.update(received_mono="x"), lambda r: r.update(finished_mono=1.0),          # finished before received
    lambda r: r["sampling"].pop("min_p"), lambda r: r["sampling"].update(top_k=None), lambda r: r.update(seed=None),
    lambda r: r.update(seed=1.5), lambda r: r.update(thinking_budget=-1), lambda r: r.update(roles="user"),
    lambda r: r.update(request_tools_present=1), lambda r: r.update(request_tools_sha256=7),
    lambda r: r.update(request_tools_present=True, request_tools_sha256=None),            # sha only with tools
    lambda r: r.update(prompt_tokens=-1), lambda r: r.update(cache_tokens=True), lambda r: r.update(disconnected="no"),
    lambda r: r.update(terminal=""), lambda r: r.update(completion_tokens=1.5)])
def test_a_malformed_receipt_is_a_schema_abort(mutate):
    receipt = copy.deepcopy(PROTOCOL["fence"]["response"]["receipts"][0])
    mutate(receipt)
    with pytest.raises(wr.ReceiptSchemaError):
        wr.validate_receipt(receipt)
    assert issubclass(wr.ReceiptSchemaError, tg.TransportAbort)


# ---------------------------------------------------------------- protocol fixture through an in-process HTTP server
class Handler(BaseHTTPRequestHandler):
    log = []
    mode = "ok"

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).log.append((self.path, body, dict(self.headers)))
        if type(self).mode == "500":
            self.send_response(500); self.end_headers(); return
        if type(self).mode == "garbage":
            self.send_response(200); self.end_headers(); self.wfile.write(b"not json"); return
        for key in ("start", "fence"):
            spec = PROTOCOL[key]
            if self.path == spec["path"] and body == spec["request"]:
                raw = json.dumps(spec["response"]).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(raw)
                return
        self.send_response(400); self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    Handler.log, Handler.mode = [], "ok"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def fixture_ctx():
    return wr.AttemptContext.make("python|foo", 1)


def test_the_fixture_attempt_id_is_the_contexts():
    assert fixture_ctx().attempt_id == PROTOCOL["start"]["request"]["attempt_id"]


def test_protocol_fixture_round_trips_through_the_http_client_and_joins(server):
    src = wr.HttpReceiptSource(server, timeout_s=5)
    ctx = fixture_ctx()
    mark = src.start(ctx)
    fence = src.fence(ctx)
    assert mark.worker == WORKER and mark.seq == 10
    assert fence.worker == WORKER and fence.last_seq == 13
    assert list(fence.receipts) == PROTOCOL["fence"]["response"]["receipts"]
    assert [(p, b) for p, b, _ in Handler.log] == [("/bench/attempt/start", {"attempt_id": ctx.attempt_id}),
                                                   ("/bench/attempt/fence", {"attempt_id": ctx.attempt_id})]
    classes = [req(c) for c in PROTOCOL["classes"]]
    result = wr.join(wr.owned_receipts(mark, fence), classes, supports_header=True, ctx=ctx, mark=mark, fence=fence,
                     controls=CONTROLS)
    assert [r["seq"] for _, r in result.pairs] == [11, 12, 13]
    # the disconnected generation's tokens count to the task (client cut with tokens after disconnect)
    assert result.task_tokens["completion_tokens"] == 900 + 700 + 5000
    assert result.task_tokens["reasoning_tokens"] == 4000 + 0 + 20000
    assert result.accounting == "receipts"


def test_the_http_client_sends_the_bearer_key_and_wraps_every_transport_failure(server):
    wr.HttpReceiptSource(server, api_key="k", timeout_s=5).start(fixture_ctx())
    assert Handler.log[0][2]["Authorization"] == "Bearer k"
    Handler.mode = "500"
    with pytest.raises(wr.ReceiptTransportError):
        wr.HttpReceiptSource(server, timeout_s=5).start(fixture_ctx())
    Handler.mode = "garbage"
    with pytest.raises(wr.ReceiptTransportError):
        wr.HttpReceiptSource(server, timeout_s=5).fence(fixture_ctx())
    Handler.mode = "ok"
    with pytest.raises(wr.ReceiptTransportError):               # an attempt the server does not know: HTTP 400
        wr.HttpReceiptSource(server, timeout_s=5).start(wr.AttemptContext.make("other", 1))
    with pytest.raises(wr.ReceiptTransportError):               # nothing listens
        wr.HttpReceiptSource("http://127.0.0.1:9", timeout_s=1).start(fixture_ctx())


def test_the_http_client_validates_what_the_server_returns(server, monkeypatch):
    resp = copy.deepcopy(PROTOCOL)
    resp["fence"]["response"]["receipts"][0]["worker"] = None
    monkeypatch.setitem(PROTOCOL, "fence", resp["fence"])
    with pytest.raises(wr.ReceiptSchemaError):
        wr.HttpReceiptSource(server, timeout_s=5).fence(fixture_ctx())


# ---------------------------------------------------------------- the one-to-one join
def test_a_clean_attempt_joins_every_request_to_one_receipt_and_reports_per_class_tokens():
    fake = wr.FakeReceiptSource(WORKER)
    mark, fence, result = run(fake, ["task", "task", "compaction", "task"], controls=CONTROLS)
    assert [r["seq"] for _, r in result.pairs] == [mark.seq + i for i in (1, 2, 3, 4)]
    assert [q["cls"] for q, _ in result.pairs] == ["task", "task", "compaction", "task"]
    assert result.by_class["task"]["requests"] == 3 and result.by_class["compaction"]["requests"] == 1
    # compaction tokens are in the task totals (A2); auxiliary stays apart
    assert result.task_tokens["requests"] == 4


def test_auxiliary_requests_are_joined_but_kept_out_of_the_task_totals():
    fake = wr.FakeReceiptSource(WORKER)
    _, _, result = run(fake, ["auxiliary", "task"], controls=CONTROLS)
    assert result.by_class["auxiliary"]["requests"] == 1 and result.task_tokens["requests"] == 1


def test_legit_tool_less_compaction_passes_and_a_tool_less_task_request_aborts():
    fake = wr.FakeReceiptSource(WORKER)
    run(fake, ["task", "compaction"], controls=CONTROLS)                       # compaction admitted without tools
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    fake.admit("task", header=CTX.header, tools=False)
    fence = fake.fence(CTX)
    with pytest.raises(wr.ReceiptToolsMismatch):
        wr.join(wr.owned_receipts(mark, fence), [req("task")], supports_header=True, ctx=CTX, mark=mark, fence=fence)


@pytest.mark.parametrize("cls", ["compaction", "auxiliary"])
def test_a_tool_bearing_compaction_or_auxiliary_request_aborts(cls):
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    fake.admit(cls, header=CTX.header, tools=True)
    fence = fake.fence(CTX)
    with pytest.raises(wr.ReceiptToolsMismatch):
        wr.join(wr.owned_receipts(mark, fence), [req(cls)], supports_header=True, ctx=CTX, mark=mark, fence=fence)


def test_the_allowed_tool_set_hash_of_a_request_must_match_its_receipt():
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    fake.admit("task", header=CTX.header, tools_sha256="aa" * 32)
    fence = fake.fence(CTX)
    ok = wr.join(wr.owned_receipts(mark, fence), [req("task", tools_sha256="aa" * 32)], supports_header=True,
                 ctx=CTX, mark=mark, fence=fence)
    assert len(ok.pairs) == 1
    with pytest.raises(wr.ReceiptToolsMismatch):
        wr.join(wr.owned_receipts(mark, fence), [req("task", tools_sha256="bb" * 32)], supports_header=True,
                ctx=CTX, mark=mark, fence=fence)


def test_controls_are_checked_per_class_a_wrong_seed_on_a_compaction_request_aborts():
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    fake.admit("task", header=CTX.header)
    fake.admit("compaction", header=CTX.header, seed=999)
    fence = fake.fence(CTX)
    with pytest.raises(wr.ReceiptControlsMismatch, match="seed"):
        wr.join(wr.owned_receipts(mark, fence), [req("task"), req("compaction")], supports_header=True, ctx=CTX,
                mark=mark, fence=fence, controls=CONTROLS)
    for field, bad in (("thinking_budget", 1), ("max_tokens", 1), ("sampling", dict(SAMPLING, top_p=0.5))):
        fake = wr.FakeReceiptSource(WORKER)
        mark = fake.start(CTX)
        fake.admit("task", header=CTX.header, **{field: bad})
        fence = fake.fence(CTX)
        with pytest.raises(wr.ReceiptControlsMismatch):
            wr.join(wr.owned_receipts(mark, fence), [req("task")], supports_header=True, ctx=CTX, mark=mark,
                    fence=fence, controls=CONTROLS)


def test_a_request_without_a_receipt_aborts():
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    fake.admit("task", header=CTX.header)
    fence = fake.fence(CTX)
    with pytest.raises(wr.ReceiptMissing):                       # the client made two requests, the worker saw one
        wr.join(wr.owned_receipts(mark, fence), [req("task")] * 2, supports_header=True, ctx=CTX, mark=mark, fence=fence)
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    fake.admit("task", header=CTX.header)
    fake.admit("task", header=CTX.header)
    fake.drop_seqs = {mark.seq + 2}                              # the fence says two were admitted; one receipt is gone
    with pytest.raises(wr.ReceiptMissing):
        wr.owned_receipts(mark, fake.fence(CTX))


def test_a_sequence_gap_inside_the_attempts_range_aborts():
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    for _ in range(3):
        fake.admit("task", header=CTX.header)
    fake.drop_seqs = {mark.seq + 2}
    fence = fake.fence(CTX)
    with pytest.raises(wr.ReceiptMissing):
        wr.join(wr.owned_receipts(mark, fence), [req("task")] * 3, supports_header=True, ctx=CTX, mark=mark, fence=fence)


def test_a_duplicate_receipt_aborts():
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    fake.admit("task", header=CTX.header)
    fake.duplicate_seqs = {mark.seq + 1}
    fence = fake.fence(CTX)
    with pytest.raises(wr.ReceiptDuplicate):
        wr.join(wr.owned_receipts(mark, fence), [req("task")], supports_header=True, ctx=CTX, mark=mark, fence=fence)


def test_a_receipt_without_a_request_aborts():
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    for _ in range(2):
        fake.admit("task", header=CTX.header)
    fence = fake.fence(CTX)
    with pytest.raises(wr.ReceiptUnmatched):
        wr.join(wr.owned_receipts(mark, fence), [req("task")], supports_header=True, ctx=CTX, mark=mark, fence=fence)


def test_a_receipt_finalized_after_its_fence_aborts():
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    fake.admit("task", header=CTX.header)
    fake.late_after_fence = 1
    fence = fake.fence(CTX)
    assert max(r["seq"] for r in fence.receipts) > fence.last_seq
    with pytest.raises(wr.ReceiptLate):
        wr.owned_receipts(mark, fence)


def test_receipts_of_earlier_attempts_are_not_owned():
    fake = wr.FakeReceiptSource(WORKER)
    first = wr.AttemptContext.make("python|a", 1)
    m1 = fake.start(first)
    fake.admit("task", header=first.header)
    fake.fence(first)
    m2 = fake.start(CTX)
    fake.admit("task", header=CTX.header)
    fence = fake.fence(CTX)
    fence = dataclasses.replace(fence, receipts=tuple(fake.all_receipts()))        # a worker-wide listing
    owned = wr.owned_receipts(m2, fence)
    assert [r["seq"] for r in owned] == [m2.seq + 1] and m1.seq < m2.seq


def test_an_ambiguous_join_aborts_when_timestamps_do_not_order_the_receipts():
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    for _ in range(2):
        fake.admit("task", header=CTX.header)
    fence = fake.fence(CTX)
    tied = [dict(r, received_mono=5.0, finished_mono=6.0) for r in fence.receipts]
    with pytest.raises(wr.ReceiptAmbiguous):
        wr.join(tied, [req("task")] * 2, supports_header=True, ctx=CTX, mark=mark, fence=fence)
    swapped = [dict(fence.receipts[0], received_mono=50.0, finished_mono=51.0), dict(fence.receipts[1])]
    with pytest.raises(wr.ReceiptAmbiguous):
        wr.join(swapped, [req("task")] * 2, supports_header=True, ctx=CTX, mark=mark, fence=fence)


def test_header_rules_a_headered_client_must_match_and_a_headerless_one_joins_by_order():
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    fake.admit("task", header="python|other#a1.r0")
    fence = fake.fence(CTX)
    with pytest.raises(wr.ReceiptHeaderMismatch):
        wr.join(wr.owned_receipts(mark, fence), [req("task")], supports_header=True, ctx=CTX, mark=mark, fence=fence)
    with pytest.raises(wr.ReceiptHeaderMismatch):                # a non-null header must match even if not supported
        wr.join(wr.owned_receipts(mark, fence), [req("task")], supports_header=False, ctx=CTX, mark=mark, fence=fence)
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    fake.admit("task", header=None)
    fence = fake.fence(CTX)
    with pytest.raises(wr.ReceiptHeaderMismatch):                # a client that sends the header must have it recorded
        wr.join(wr.owned_receipts(mark, fence), [req("task")], supports_header=True, ctx=CTX, mark=mark, fence=fence)
    ok = wr.join(wr.owned_receipts(mark, fence), [req("task")], supports_header=False, ctx=CTX, mark=mark, fence=fence)
    assert len(ok.pairs) == 1                                    # headerless fake adapter: fence + order, passes


def test_a_receipt_naming_another_worker_is_a_worker_crash_abort():
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    fake.admit("task", header=CTX.header)
    fake.admit("task", header=CTX.header)
    fake.foreign_worker = {mark.seq + 2: dict(pid=9999, create_time=1.5)}
    fence = fake.fence(CTX)
    with pytest.raises(wr.WorkerMismatch) as exc:
        wr.join(wr.owned_receipts(mark, fence), [req("task")] * 2, supports_header=True, ctx=CTX, mark=mark, fence=fence)
    assert exc.value.cause == "worker_crash" and isinstance(exc.value, tg.TransportAbort)


def test_a_worker_replaced_between_the_marks_is_a_worker_crash_abort():
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    fake.fence_worker = dict(pid=4243, create_time=1760000100.0)
    fence = fake.fence(CTX)
    with pytest.raises(wr.WorkerMismatch) as exc:
        wr.owned_receipts(mark, fence)
    assert exc.value.cause == "worker_crash"
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    fake.fence_worker = None
    fake.fence_receipt_worker = dict(pid=1, create_time=2.0)
    fake.admit("task", header=CTX.header)
    with pytest.raises(wr.WorkerMismatch):
        wr.owned_receipts(mark, fake.fence(CTX))


def test_a_fence_before_the_start_mark_is_an_abort():
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    fake.admit("task", header=CTX.header)
    fence = fake.fence(CTX)
    with pytest.raises(wr.ReceiptAbort):
        wr.owned_receipts(dataclasses.replace(mark, seq=fence.last_seq + 5), fence)


def test_every_abort_is_a_transport_abort_and_only_worker_mismatch_carries_a_cause():
    for name in ("ReceiptAbort", "ReceiptSchemaError", "ReceiptUnavailable", "ReceiptTransportError", "ReceiptMissing",
                 "ReceiptDuplicate", "ReceiptUnmatched", "ReceiptLate", "ReceiptAmbiguous", "ReceiptHeaderMismatch",
                 "ReceiptToolsMismatch", "ReceiptControlsMismatch", "WorkerMismatch"):
        cls = getattr(wr, name)
        assert issubclass(cls, tg.TransportAbort)
        assert (cls.cause == "worker_crash") == (name == "WorkerMismatch")


def test_unknown_request_classes_are_refused():
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    fake.admit("task", header=CTX.header)
    fence = fake.fence(CTX)
    with pytest.raises(wr.ReceiptAbort):
        wr.join(wr.owned_receipts(mark, fence), [req("mystery")], supports_header=True, ctx=CTX, mark=mark, fence=fence)


# ---------------------------------------------------------------- persisted receipt file, sources
def test_the_raw_fenced_receipt_set_is_persisted_and_its_sha_matches(tmp_path):
    fake = wr.FakeReceiptSource(WORKER)
    mark, fence, result = run(fake, ["task", "compaction"])
    path = tmp_path / "ev/x.receipts.json"
    sha = wr.write_receipts_file(path, CTX, mark, fence)
    assert sha == hashlib.sha256(path.read_bytes()).hexdigest()
    doc = json.loads(path.read_text())
    assert doc["attempt_id"] == CTX.attempt_id and doc["start"] == dict(worker=WORKER, seq=mark.seq)
    assert doc["fence"]["last_seq"] == fence.last_seq and doc["fence"]["receipts"] == list(fence.receipts)
    with pytest.raises(wr.ReceiptAbort):                          # immutable evidence: no overwrite
        wr.write_receipts_file(path, CTX, mark, fence)


def test_the_unavailable_source_refuses_before_any_spawn():
    src = wr.UnavailableReceiptSource("the fork endpoint (P372) is not built")
    for call in (src.check, lambda: src.start(CTX), lambda: src.fence(CTX)):
        with pytest.raises(wr.ReceiptUnavailable, match="P372"):
            call()
    assert not src.available
    with pytest.raises(wr.ReceiptUnavailable):
        wr.require_source("required", src)
    wr.require_source("absent", src)                              # tg1: receipts absent, nothing to check
    wr.require_source("required", wr.FakeReceiptSource(WORKER))
    with pytest.raises(ValueError):
        wr.require_source("maybe", src)


def test_the_receipt_source_contract_is_start_and_fence():
    assert {"start", "fence"} <= set(wr.ReceiptSource.__abstractmethods__)
    for cls in (wr.FakeReceiptSource, wr.UnavailableReceiptSource, wr.HttpReceiptSource):
        assert issubclass(cls, wr.ReceiptSource)


def test_the_fake_records_the_call_order_so_start_precedes_every_admission_and_the_fence_follows():
    fake = wr.FakeReceiptSource(WORKER)
    run(fake, ["task"])
    assert [c[0] for c in fake.calls] == ["start", "admit", "fence"]


def test_the_module_imports_no_adapter_corpus_or_client_modules():
    import subprocess, sys
    code = ("import sys; import bench.worker_receipts; print([m for m in sys.modules if m in ('bench.arm_adapter',"
            "'bench.arm_opencode','bench.corpus_tg1','bench.structured_grade','bench.proc_guard','psutil')])")
    out = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[2], capture_output=True,
                         text=True)
    assert out.stdout.strip() == "[]", out.stderr
