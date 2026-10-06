"""M58 AC11: `parity_replay` upgrades for G1b.

`run` refuses unless every frozen key is unique, aborts (nonzero, never graded) on a malformed
response, and records per request: the payload+seed hash, the draft counters, every `verify_*`
counter, the v8 runtime slice and the worker's `--model` / `--draft-kind` / `--mtp-verify-scan`
flags; it sends the router's bearer header when `MLX_API_KEY` is configured; M50 at entry, C106 at
exit. `compare` reports identical / differing / missing PER KEY and exits nonzero on any missing key.
"""
import argparse
import json
from pathlib import Path

import pytest

import bench.provenance as P
from bench import parity_replay as R
from bench.tests.test_m50_entrypoints import _passing, _refusing


KEYS = [("m", "math500", "a"), ("m", "math500", "b"), ("m", "mbpp", "c")]
VERIFY = {"verify_blocks_joint_v1": 9, "verify_blocks_per_query": 1,
          "verify_blocks_straddle": 0, "verify_blocks_len1": 4,
          "verify_fallback_reasons": {"domain": 1}}
TIMINGS = {"predicted_per_second": 20.0, "draft_kind": "mtp", "draft_rounds": 7, "draft_n": 21,
           "draft_n_accepted": 14, **VERIFY}
RUNTIME = {"draft_kind": "mtp", "mtp_verify_scan": "joint_v1", "mtp_verify_scan_source": "worker",
           "attention_policy": "fused_v1", "lazy_prompt_embeddings": False}
WORKER = {"model": "caslca/m", "draft_kind": "mtp", "mtp_verify_scan": "joint_v1",
          "mtp_verify_ab": False}


def _reqs(keys=KEYS, seed=11):
    return [{"model": m, "bench": b, "id": i, "seed": seed,
             "payload": {"max_tokens": 10, "messages": [{"role": "user", "content": i}],
                         "model": m, "stream": False}} for m, b, i in keys]


def _resp(content="x", finish="stop", usage=None, **extra):
    return {"choices": [{"message": {"content": content, "reasoning": "r"},
                         "finish_reason": finish}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3} if usage is None else usage,
            "timings": dict(TIMINGS), **extra}


def _args(tmp_path, **kw):
    return argparse.Namespace(frozen=str(tmp_path / "frozen.json"), models=None,
                              out=str(tmp_path / "rep.json"), resume=False, tag="t", **kw)


@pytest.fixture
def env(monkeypatch, tmp_path):
    """A passing router, a recording transport, stubbed runtime/worker observation."""
    state = {"posted": [], "responses": None}
    monkeypatch.setattr(R, "load_requests", lambda f, models: _reqs())
    monkeypatch.setattr(R.client, "preload", lambda m, **k: 0.0)

    def post(payload, timeout):
        state["posted"].append(payload)
        rs = state["responses"]
        return rs.pop(0) if rs else _resp()
    monkeypatch.setattr(R, "_post", post)
    monkeypatch.setattr(R.provenance, "_runtime_block",
                        lambda runtime=None, model=None, registry_path=None: dict(RUNTIME))
    monkeypatch.setattr(R.provenance, "worker_serving_facts",
                        lambda model, registry_path=None, worker_lookup=None: dict(WORKER))
    monkeypatch.setattr(R.provenance, "assert_serving_state", _serving_state)
    _passing(monkeypatch, tmp_path, pid=616)
    return state


def _serving_state(model, registry_path=None, expect=None):
    out = {"mtp_verify_scan": "joint_v1", "mtp_verify_scan_source": "worker"}
    if expect is not None and expect["mtp_verify_scan"] != out["mtp_verify_scan"]:
        raise P.ServingStateError("changed")
    return out


def _doc(tmp_path):
    return json.loads((tmp_path / "rep.json").read_text())


# --------------------------------------------------------------------------- run: refusals
def test_run_refuses_a_duplicate_frozen_key_before_any_request(env, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(R, "load_requests", lambda f, models: _reqs(KEYS + [KEYS[0]]))
    monkeypatch.setattr(R.client, "preload", lambda m, **k: pytest.fail("preload before refusal"))
    assert R.run(_args(tmp_path)) == 2
    assert env["posted"] == [] and not (tmp_path / "rep.json").exists()
    assert "duplicate" in capsys.readouterr().err


@pytest.mark.parametrize("bad", [
    {"error": {"message": "boom"}},                                   # error envelope
    {"choices": []},                                                  # no choices
    {"choices": [{"message": {"content": ""}, "finish_reason": None}],
     "usage": {"prompt_tokens": 1, "completion_tokens": 1}},          # empty content AND no finish
    {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}], "usage": {}},   # no usage
    {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}]},                # absent
    {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}],
     "usage": {"prompt_tokens": "5", "completion_tokens": 3}},        # non-int usage
    [],                                                               # not an object
])
def test_run_aborts_nonzero_on_a_malformed_response_and_stops(env, tmp_path, bad):
    env["responses"] = [_resp(), bad, _resp()]
    assert R.run(_args(tmp_path)) == 2
    doc = _doc(tmp_path)
    assert doc["status"] == "aborted" and len(doc["rows"]) == 1 and "malformed" in doc["error"]
    assert len(env["posted"]) == 2                                    # stopped at the bad one


def test_empty_content_with_a_finish_reason_is_well_formed(env, tmp_path):
    env["responses"] = [_resp(content="", finish="length"), _resp(), _resp()]
    assert R.run(_args(tmp_path)) == 0


def test_run_refuses_at_entry_before_anything(env, monkeypatch, tmp_path, capsys):
    _refusing(monkeypatch)
    monkeypatch.setattr(R, "load_requests", lambda *a: pytest.fail("read before M50"))
    assert R.run(_args(tmp_path)) == 2
    assert "M50" in capsys.readouterr().err and not (tmp_path / "rep.json").exists()


def test_run_serving_state_refusal_mid_run_aborts_nonzero(env, monkeypatch, tmp_path):
    n = {"calls": 0}

    def refuse(runtime=None, model=None, registry_path=None):
        n["calls"] += 1
        if n["calls"] == 1:                      # the entry resolution passes; a later row drifts
            return dict(RUNTIME)
        raise P.ServingStateError("C35 tripwire: worker/registry disagree")
    monkeypatch.setattr(R.provenance, "_runtime_block", refuse)
    assert R.run(_args(tmp_path)) == 2
    assert _doc(tmp_path)["status"] == "aborted"


def test_run_c106_exit_drift_aborts_nonzero(env, monkeypatch, tmp_path):
    def drift(entry, base):
        raise P.ServedConfigError("C106: router drifted")
    monkeypatch.setattr(R.provenance, "assert_served_config_unchanged", drift)
    assert R.run(_args(tmp_path)) == 2
    assert _doc(tmp_path)["status"] == "aborted"


def test_transport_failure_aborts_nonzero(env, monkeypatch, tmp_path):
    def boom(payload, timeout):
        raise OSError("connection reset")
    monkeypatch.setattr(R, "_post", boom)
    assert R.run(_args(tmp_path)) == 2
    assert _doc(tmp_path)["status"] == "aborted"


# --------------------------------------------------------------------------- run: records
def test_run_records_the_row_provenance_per_request(env, tmp_path):
    assert R.run(_args(tmp_path)) == 0
    doc = _doc(tmp_path)
    assert doc["status"] == "complete" and doc["router"]["pid"] == 616 and doc["router_exit"]
    assert [tuple(k) for k in doc["expected_keys"]] == KEYS
    assert [(r["model"], r["bench"], r["id"]) for r in doc["rows"]] == KEYS
    row = doc["rows"][0]
    assert row["draft"] == {"draft_kind": "mtp", "draft_rounds": 7, "draft_n": 21,
                            "draft_n_accepted": 14}
    assert row["verify"] == VERIFY
    assert row["runtime"] == RUNTIME and row["runtime"]["mtp_verify_scan"] == "joint_v1"
    assert row["worker"] == WORKER
    assert len(row["payload_sha256"]) == 64


def test_payload_hash_covers_payload_and_seed(env, monkeypatch, tmp_path):
    R.run(_args(tmp_path))
    first = _doc(tmp_path)["rows"][0]["payload_sha256"]
    monkeypatch.setattr(R, "load_requests", lambda f, models: _reqs(seed=12))
    a = _args(tmp_path); a.out = str(tmp_path / "rep2.json")
    R.run(a)
    assert json.loads(Path(a.out).read_text())["rows"][0]["payload_sha256"] != first
    monkeypatch.setattr(R, "load_requests", lambda f, models: _reqs(seed=11))
    a.out = str(tmp_path / "rep3.json")
    R.run(a)
    assert json.loads(Path(a.out).read_text())["rows"][0]["payload_sha256"] == first


def test_verify_counters_absent_under_per_query_record_an_empty_dict(env, tmp_path):
    plain = {k: v for k, v in TIMINGS.items() if not k.startswith("verify_")}
    env["responses"] = [dict(_resp(), timings=plain)] * 3
    assert R.run(_args(tmp_path)) == 0
    assert all(r["verify"] == {} for r in _doc(tmp_path)["rows"])


def test_s3_a_null_worker_command_line_is_refused_not_recorded(env, monkeypatch, tmp_path):
    monkeypatch.setattr(R.provenance, "worker_serving_facts",
                        lambda model, registry_path=None, worker_lookup=None: None)
    assert R.run(_args(tmp_path)) == 2
    doc = _doc(tmp_path)
    assert doc["status"] == "aborted" and doc["rows"] == [] and "worker" in doc["error"]


# --------------------------------------------------------------------------- auth header
def _capture_urlopen(monkeypatch):
    seen = {}

    class Resp:
        def read(self):
            return json.dumps(_resp()).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        return Resp()
    monkeypatch.setattr(R.urllib.request, "urlopen", urlopen)
    return seen


def test_post_sends_the_bearer_header_when_the_router_key_is_configured(monkeypatch):
    seen = _capture_urlopen(monkeypatch)
    monkeypatch.setenv("MLX_API_KEY", "sekret")
    R._post({"max_tokens": 1}, 5)
    assert seen["headers"]["authorization"] == "Bearer sekret"
    assert seen["headers"]["content-type"] == "application/json"


def test_post_sends_no_auth_header_without_a_configured_key(monkeypatch):
    seen = _capture_urlopen(monkeypatch)
    monkeypatch.delenv("MLX_API_KEY", raising=False)
    R._post({"max_tokens": 1}, 5)
    assert "authorization" not in seen["headers"]
    monkeypatch.setenv("MLX_API_KEY", "")
    R._post({"max_tokens": 1}, 5)
    assert "authorization" not in seen["headers"]


# --------------------------------------------------------------------------- resume
def test_resume_keeps_rows_and_refuses_duplicates_in_the_journal(env, monkeypatch, tmp_path):
    env["responses"] = [_resp(), _resp(), _resp()]
    a = _args(tmp_path)
    assert R.run(a) == 0
    doc = _doc(tmp_path)
    doc["rows"] = doc["rows"][:1] * 2                       # a corrupt journal: row 0 twice
    doc["status"] = "running"
    (tmp_path / "rep.json").write_text(json.dumps(doc))
    a.resume = True
    assert R.run(a) == 2
    assert env["posted"][3:] == []                          # nothing new was requested


# --------------------------------------------------------------------------- compare
def _row(key, content="x", **kw):
    m, b, i = key
    row = {"model": m, "bench": b, "id": i, "seed": 11, "finish_reason": "stop",
           "payload_sha256": R._payload_sha(_reqs([key])[0]["payload"], 11),
           "prompt_tokens": 5, "completion_tokens": 3, "content": content,
           "content_sha256": R._sha(content), "reasoning_sha256": R._sha("r"), "reasoning": "r",
           "runtime": dict(RUNTIME),
           "draft": {"draft_kind": "mtp", "draft_rounds": 7, "draft_n": 21, "draft_n_accepted": 14},
           "verify": dict(VERIFY)}
    row.update(kw)
    return row


def _write(tmp_path, name, rows, tag, expected=KEYS, status="complete"):
    p = tmp_path / name
    p.write_text(json.dumps({"status": status, "tag": tag, "rows": rows,
                             "expected_keys": [list(k) for k in expected]}))
    return str(p)


def _cmp(tmp_path, a_rows, b_rows, **kw):
    a = argparse.Namespace(a=_write(tmp_path, "A.json", a_rows, "A", **kw),
                           b=_write(tmp_path, "B.json", b_rows, "B", **kw),
                           out=str(tmp_path / "cmp.json"))
    return R.compare(a), json.loads((tmp_path / "cmp.json").read_text())


def test_compare_identical_exits_zero_and_reports_per_key(tmp_path, capsys):
    rows = [_row(k) for k in KEYS]
    rc, out = _cmp(tmp_path, rows, [dict(r) for r in rows])
    assert rc == 0 and out["identical"] == 3 and out["differing"] == 0 and out["missing"] == 0
    assert {tuple(s["key"]): s["status"] for s in out["statuses"]} == {k: "identical" for k in KEYS}
    assert "identical=3" in capsys.readouterr().out


def test_compare_differing_content_exits_1(tmp_path):
    a = [_row(k) for k in KEYS]
    b = [_row(KEYS[0], content="y")] + [_row(k) for k in KEYS[1:]]
    rc, out = _cmp(tmp_path, a, b)
    assert rc == 1 and out["differing"] == 1
    assert [s["status"] for s in out["statuses"]].count("differing") == 1


def test_compare_draft_counters_are_part_of_the_identity(tmp_path):
    a = [_row(k) for k in KEYS]
    other = {"draft_kind": "mtp", "draft_rounds": 8, "draft_n": 24, "draft_n_accepted": 14}
    b = [_row(KEYS[0], draft=other)] + [_row(k) for k in KEYS[1:]]
    rc, out = _cmp(tmp_path, a, b)
    assert rc == 1 and out["differing"] == 1


def test_compare_missing_key_exits_nonzero_even_when_the_rest_is_identical(tmp_path):
    a = [_row(k) for k in KEYS]
    b = [_row(k) for k in KEYS[:2]]
    rc, out = _cmp(tmp_path, a, b)
    assert rc == 2 and out["missing"] == 1
    miss = [s for s in out["statuses"] if s["status"] == "missing"]
    assert [tuple(s["key"]) for s in miss] == [KEYS[2]] and miss[0]["missing_in"] == ["B"]
    rc, out = _cmp(tmp_path, b, a)
    assert rc == 2 and [s["missing_in"] for s in out["statuses"] if s["status"] == "missing"] == [["A"]]


def test_compare_missing_in_both_is_still_missing(tmp_path):
    rows = [_row(k) for k in KEYS[:2]]
    rc, out = _cmp(tmp_path, rows, [dict(r) for r in rows])      # expected_keys lists all three
    assert rc == 2 and out["missing"] == 1
    assert [s["missing_in"] for s in out["statuses"] if s["status"] == "missing"] == [["A", "B"]]


def test_compare_duplicate_row_exits_nonzero(tmp_path):
    a = [_row(k) for k in KEYS] + [_row(KEYS[0])]
    rc, out = _cmp(tmp_path, a, [_row(k) for k in KEYS])
    assert rc == 2 and out["integrity"]


@pytest.mark.parametrize("bad", [{"finish_reason": None, "content": ""}, {"prompt_tokens": None},
                                 {"completion_tokens": "3"}])
def test_compare_malformed_row_exits_nonzero(tmp_path, bad):
    a = [_row(KEYS[0], **bad)] + [_row(k) for k in KEYS[1:]]
    rc, out = _cmp(tmp_path, a, [_row(k) for k in KEYS])
    assert rc == 2 and out["integrity"]


def test_compare_reports_the_joint_path_row_counts(tmp_path):
    a = [_row(k, verify={}) for k in KEYS]                       # per_query: no counters
    b = [_row(KEYS[0], verify={"verify_blocks_joint_v1": 0})] + [_row(k) for k in KEYS[1:]]
    rc, out = _cmp(tmp_path, a, b)
    assert out["joint_rows"] == {"A": 0, "B": 2}


def test_b1_legacy_docs_without_expected_keys_are_non_gating_exit_3(tmp_path, capsys):
    rows = [_row(k) for k in KEYS]
    pa, pb = tmp_path / "A.json", tmp_path / "B.json"
    for p, tag in ((pa, "A"), (pb, "B")):
        p.write_text(json.dumps({"status": "complete", "tag": tag, "rows": rows}))
    assert R.compare(argparse.Namespace(a=str(pa), b=str(pb), out=None)) == 3   # never 0
    assert "NON-GATING" in capsys.readouterr().out
    pb.write_text(json.dumps({"tag": "B", "rows": rows[:2]}))
    assert R.compare(argparse.Namespace(a=str(pa), b=str(pb), out=None)) == 3   # legacy: never gating


def test_b1_empty_inputs_exit_2(tmp_path):
    rc, out = _cmp(tmp_path, [], [], expected=[])
    assert rc == 2 and out["integrity"]


def test_b1_expected_sets_must_be_equal_unique_and_cover_the_rows_exactly(tmp_path):
    rows = [_row(k) for k in KEYS]
    a = argparse.Namespace(a=_write(tmp_path, "A.json", rows, "A"),
                           b=_write(tmp_path, "B.json", rows, "B", expected=KEYS[:2]), out=None)
    assert R.compare(a) == 2                                   # unequal expected sets
    dup = argparse.Namespace(a=_write(tmp_path, "A.json", rows, "A", expected=KEYS + [KEYS[0]]),
                             b=_write(tmp_path, "B.json", rows, "B", expected=KEYS + [KEYS[0]]),
                             out=None)
    assert R.compare(dup) == 2                                 # duplicate expected entry
    extra = rows + [_row(("m", "mbpp", "zzz"))]                # a row nobody expected
    rc, out = _cmp(tmp_path, extra, rows)
    assert rc == 2 and any("unexpected" in p for p in out["integrity"])


def test_b2_compare_requires_complete_journals(tmp_path):
    rows = [_row(k) for k in KEYS]
    a = argparse.Namespace(a=_write(tmp_path, "A.json", rows, "A", status="running"),
                           b=_write(tmp_path, "B.json", rows, "B"), out=None)
    assert R.compare(a) == 2
    a.a = _write(tmp_path, "A.json", rows, "A", status="aborted")
    assert R.compare(a) == 2


@pytest.mark.parametrize("field", ["finish_reason", "completion_tokens", "content_sha256",
                                   "reasoning_sha256", "draft"])
def test_b2_identity_fields_are_mandatory(tmp_path, field):
    a = [_row(KEYS[0])] + [_row(k) for k in KEYS[1:]]
    b = [_row(k) for k in KEYS]
    del a[0][field]
    del b[0][field]                                            # absent on BOTH: still a failure
    rc, out = _cmp(tmp_path, a, b)
    assert rc == 2 and any(field in p for p in out["integrity"])


def test_b2_request_hashes_must_exist_and_agree_across_sides(tmp_path):
    a = [_row(k) for k in KEYS]
    b = [_row(KEYS[0], payload_sha256="0" * 64)] + [_row(k) for k in KEYS[1:]]
    rc, out = _cmp(tmp_path, a, b)
    assert rc == 2 and any("request hash" in p for p in out["integrity"])
    c = [_row(k) for k in KEYS]
    for r in c:
        del r["payload_sha256"]
    rc, out = _cmp(tmp_path, c, [dict(r) for r in c])
    assert rc == 2 and any("payload_sha256" in p for p in out["integrity"])


def test_b2_resume_validates_journal_rows_against_the_frozen_request_hash(
    env, monkeypatch, tmp_path
):
    a = _args(tmp_path)
    assert R.run(a) == 0
    base = _doc(tmp_path)
    posted_before = len(env["posted"])
    a.resume = True
    for mutate in (lambda r: r.update(payload_sha256="f" * 64), lambda r: r.pop("payload_sha256")):
        doc = json.loads(json.dumps(base))
        doc["status"] = "running"
        mutate(doc["rows"][0])
        (tmp_path / "rep.json").write_text(json.dumps(doc))
        assert R.run(a) == 2
    assert len(env["posted"]) == posted_before                 # nothing was re-requested
    honest = json.loads(json.dumps(base)); honest["status"] = "running"
    (tmp_path / "rep.json").write_text(json.dumps(honest))
    assert R.run(a) == 0                                       # an honest journal still resumes


# --------------------------------------------------------------------------- B3 closed set
def test_b3_parity_run_refuses_an_unrecognised_scan_before_any_request(env, monkeypatch, tmp_path):
    monkeypatch.setattr(R.provenance, "_runtime_block",
                        lambda runtime=None, model=None, registry_path=None: dict(
                            RUNTIME, mtp_verify_scan="joint_v2"))
    assert R.run(_args(tmp_path)) == 2
    doc = _doc(tmp_path)
    assert doc["status"] == "aborted" and "joint_v2" in doc["error"]


# --------------------------------------------------------------------------- B4 auth
def test_b4_the_whole_request_sequence_is_authenticated(monkeypatch, tmp_path):
    seen = []

    class Resp:
        def __init__(self, body):
            self.body = body

        def read(self):
            return json.dumps(self.body).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        seen.append((req.full_url, {k.lower(): v for k, v in req.header_items()}))
        return Resp(_resp() if "chat/completions" in req.full_url else {"loaded": True})
    monkeypatch.setattr(R.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("MLX_API_KEY", "sekret")
    monkeypatch.setattr(R, "load_requests", lambda f, models: _reqs())
    monkeypatch.setattr(R.provenance, "_runtime_block", lambda *a, **k: dict(RUNTIME))
    monkeypatch.setattr(R.provenance, "worker_serving_facts", lambda *a, **k: dict(WORKER))
    monkeypatch.setattr(R.provenance, "assert_serving_state", _serving_state)
    _passing(monkeypatch, tmp_path, pid=616)
    assert R.run(_args(tmp_path)) == 0
    urls = [u for u, _ in seen]
    assert any("/v1/models/load" in u for u in urls) and sum("chat/completions" in u for u in urls) == 3
    assert all(h.get("authorization") == "Bearer sekret" for _, h in seen), seen


def test_b4_client_get_and_post_send_the_bearer_header_only_when_configured(monkeypatch):
    import bench.client as C
    seen = []

    class Resp:
        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(C.urllib.request, "urlopen",
                        lambda req, timeout=None: seen.append(
                            {k.lower(): v for k, v in req.header_items()}) or Resp())
    monkeypatch.setenv("MLX_API_KEY", "k1")
    C._post("/x", {}); C._get("/y")
    assert all(h["authorization"] == "Bearer k1" for h in seen)
    seen.clear()
    monkeypatch.delenv("MLX_API_KEY")
    C._post("/x", {}); C._get("/y")
    assert all("authorization" not in h for h in seen)


# --------------------------------------------------------------------------- B5 failure exits
def _spy_exit(monkeypatch, drift=None):
    calls = []

    def unchanged(entry, base):
        calls.append(entry)
        if drift:
            raise P.ServedConfigError(drift)
        return {"pid": 616}
    monkeypatch.setattr(R.provenance, "assert_served_config_unchanged", unchanged)
    return calls


def test_b5_c106_runs_on_a_transport_abort_and_a_drift_is_recorded_without_masking(
    env, monkeypatch, tmp_path
):
    def boom(payload, timeout):
        raise OSError("connection reset")
    monkeypatch.setattr(R, "_post", boom)
    calls = _spy_exit(monkeypatch, drift="C106: router pid changed")
    assert R.run(_args(tmp_path)) == 2
    doc = _doc(tmp_path)
    assert len(calls) == 1 and doc["status"] == "aborted"
    assert "connection reset" in doc["error"]                  # the original failure survives
    assert "served_config_drift" in doc and "C106" in json.dumps(doc["served_config_drift"])


def test_b5_c106_runs_on_a_malformed_response_abort(env, monkeypatch, tmp_path):
    env["responses"] = [{"choices": []}]
    calls = _spy_exit(monkeypatch)
    assert R.run(_args(tmp_path)) == 2
    doc = _doc(tmp_path)
    assert len(calls) == 1 and "malformed" in doc["error"] and doc["router_exit"] == {"pid": 616}
    assert "served_config_drift" not in doc


def test_b5_a_preload_exception_aborts_cleanly_with_the_exit_check(env, monkeypatch, tmp_path):
    def bad_preload(model, **kw):
        raise OSError("load failed")
    monkeypatch.setattr(R.client, "preload", bad_preload)
    calls = _spy_exit(monkeypatch, drift="C106: drifted")
    assert R.run(_args(tmp_path)) == 2
    doc = _doc(tmp_path)
    assert len(calls) == 1 and doc["status"] == "aborted" and "load failed" in doc["error"]
    assert "served_config_drift" in doc


def test_b5_a_failing_exit_check_itself_never_replaces_the_original_failure(
    env, monkeypatch, tmp_path
):
    def crash(entry, base):
        raise RuntimeError("lsof exploded")
    monkeypatch.setattr(R.provenance, "assert_served_config_unchanged", crash)
    env["responses"] = [{"choices": []}]
    assert R.run(_args(tmp_path)) == 2
    doc = _doc(tmp_path)
    assert "malformed" in doc["error"] and "lsof exploded" in json.dumps(doc["served_config_drift"])


def test_s2_empty_selection_is_refused_and_never_complete(env, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(R, "load_requests", lambda f, models: [])
    assert R.run(_args(tmp_path)) == 2
    assert not (tmp_path / "rep.json").exists() and "empty" in capsys.readouterr().err


def test_s1_scan_change_between_entry_and_load_refuses(env, monkeypatch, tmp_path):
    calls = {"n": 0}

    def drifting(model, registry_path=None, expect=None):
        calls["n"] += 1
        if expect is None:
            return {"mtp_verify_scan": "joint_v1"}                 # entry value
        raise P.ServingStateError("M58: mtp_verify_scan changed (joint_v1 -> joint_v1+ab)")
    monkeypatch.setattr(R.provenance, "assert_serving_state", drifting)
    assert R.run(_args(tmp_path)) == 2
    doc = _doc(tmp_path)
    assert doc["status"] == "aborted" and doc["rows"] == [] and "changed" in doc["error"]
    assert env["posted"] == []


# --------------------------------------------------------------------------- D1 resume identity
def _journal(env, tmp_path, **patch):
    """A finished honest journal, rewritten as a `running` one with `patch` applied."""
    assert R.run(_args(tmp_path)) == 0
    doc = _doc(tmp_path)
    doc["status"] = "running"
    for k, v in patch.items():
        doc[k] = v
    (tmp_path / "rep.json").write_text(json.dumps(doc))
    return doc


def _resume(tmp_path):
    a = _args(tmp_path)
    a.resume = True
    return R.run(a)


def test_d1_a_drift_stamped_journal_is_never_resumed_and_keeps_its_stamp(env, tmp_path):
    stamp = {"entry_sha256": "a", "exit_sha256": "b", "error": "C106 drift"}
    _journal(env, tmp_path, status="aborted", served_config_drift=stamp)
    before = (tmp_path / "rep.json").read_text()
    posted = len(env["posted"])
    assert _resume(tmp_path) == 2
    assert (tmp_path / "rep.json").read_text() == before        # untouched: stamp not lost
    assert len(env["posted"]) == posted


@pytest.mark.parametrize("status", ["complete", None, "weird"])
def test_d1_complete_or_statusless_journals_are_not_resumed(env, tmp_path, status):
    doc = _journal(env, tmp_path)
    doc["status"] = status
    (tmp_path / "rep.json").write_text(json.dumps(doc))
    assert _resume(tmp_path) == 2


def test_d2_an_aborted_journal_with_a_clean_identity_IS_resumable(env, monkeypatch, tmp_path):
    # a transport abort after two rows: the point of resume
    calls = {"n": 0}
    real_post = R._post

    def flaky(payload, timeout):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("connection reset")
        return real_post(payload, timeout)
    monkeypatch.setattr(R, "_post", flaky)
    assert R.run(_args(tmp_path)) == 2
    doc = _doc(tmp_path)
    assert doc["status"] == "aborted" and len(doc["rows"]) == 2 and "served_config_drift" not in doc
    monkeypatch.setattr(R, "_post", real_post)
    assert _resume(tmp_path) == 0
    out = _doc(tmp_path)
    assert out["status"] == "complete" and len(out["rows"]) == 3


def test_d2_an_aborted_journal_with_drift_or_a_mismatched_identity_is_refused(env, tmp_path):
    doc = _journal(env, tmp_path, status="aborted")
    doc["rows"][0]["runtime"]["mtp_verify_scan"] = "per_query"
    (tmp_path / "rep.json").write_text(json.dumps(doc))
    assert _resume(tmp_path) == 2
    doc["rows"][0]["runtime"]["mtp_verify_scan"] = "joint_v1"
    doc["served_config_drift"] = {"error": "x"}
    (tmp_path / "rep.json").write_text(json.dumps(doc))
    assert _resume(tmp_path) == 2


def test_d1_row_serving_mode_must_match_the_entry_state(env, tmp_path):
    doc = _journal(env, tmp_path)
    doc["rows"][0]["runtime"]["mtp_verify_scan"] = "joint_v1+ab"     # an AB gate row
    (tmp_path / "rep.json").write_text(json.dumps(doc))
    assert _resume(tmp_path) == 2


@pytest.mark.parametrize("field,value", [("attention_policy", "auto"), ("draft_kind", "off"),
                                         ("lazy_prompt_embeddings", True)])
def test_d1_row_runtime_slice_must_match_the_entry_state(env, tmp_path, field, value):
    doc = _journal(env, tmp_path)
    doc["rows"][1]["runtime"][field] = value
    (tmp_path / "rep.json").write_text(json.dumps(doc))
    assert _resume(tmp_path) == 2


def test_d1_a_row_without_a_runtime_slice_is_refused(env, tmp_path):
    doc = _journal(env, tmp_path)
    del doc["rows"][0]["runtime"]
    (tmp_path / "rep.json").write_text(json.dumps(doc))
    assert _resume(tmp_path) == 2


def test_d1_router_config_hash_must_match_including_history(env, tmp_path):
    doc = _journal(env, tmp_path)
    doc["router"]["config_sha256"] = "0" * 64
    (tmp_path / "rep.json").write_text(json.dumps(doc))
    assert _resume(tmp_path) == 2
    doc = json.loads((tmp_path / "rep.json").read_text())
    doc["router"]["config_sha256"] = _doc_sha(tmp_path)
    doc["router_history"] = [{"pid": 1, "config": "x", "config_sha256": "f" * 64}]
    (tmp_path / "rep.json").write_text(json.dumps(doc))
    assert _resume(tmp_path) == 2


def _doc_sha(tmp_path):
    return P.router_block(R.client.BASE)["config_sha256"]


def test_d1_an_honest_running_journal_resumes_and_keeps_router_history(env, monkeypatch, tmp_path):
    doc = _journal(env, tmp_path)
    prev = dict(doc["router"], pid=1)                          # produced by an earlier router pid
    doc["router"] = prev
    doc["rows"] = doc["rows"][:2]
    (tmp_path / "rep.json").write_text(json.dumps(doc))
    assert _resume(tmp_path) == 0
    out = _doc(tmp_path)
    assert out["status"] == "complete" and len(out["rows"]) == 3 and out["router_history"] == [prev]


# --------------------------------------------------------------------------- D2 compare rows
def _mod(tmp_path, mutate_a=None, mutate_b=None):
    a = [_row(k) for k in KEYS]
    b = [_row(k) for k in KEYS]
    if mutate_a:
        mutate_a(a[0])
    if mutate_b:
        mutate_b(b[0])
    return _cmp(tmp_path, a, b)


@pytest.mark.parametrize("field", ["content_sha256", "reasoning_sha256", "finish_reason",
                                   "completion_tokens", "draft", "content", "reasoning", "runtime"])
def test_d2_null_identity_fields_are_integrity_failures_even_when_both_sides_agree(tmp_path, field):
    def null(r):
        r[field] = None
    rc, out = _mod(tmp_path, null, null)
    assert rc == 2 and any(field in p for p in out["integrity"])


@pytest.mark.parametrize("member", ["draft_kind", "draft_rounds", "draft_n", "draft_n_accepted"])
def test_d2_null_draft_members_are_integrity_failures(tmp_path, member):
    def null(r):
        r["draft"] = dict(r["draft"], **{member: None})
    rc, out = _mod(tmp_path, null, null)
    assert rc == 2 and any(member in p for p in out["integrity"])


def test_d2_changed_content_with_a_stale_digest_is_refused(tmp_path):
    def tamper(r):
        r["content"] = "changed text"                          # digest left stale
    rc, out = _mod(tmp_path, tamper, tamper)
    assert rc == 2 and any("content_sha256" in p for p in out["integrity"])

    def tamper_reasoning(r):
        r["reasoning"] = "other"
    rc, out = _mod(tmp_path, tamper_reasoning, tamper_reasoning)
    assert rc == 2 and any("reasoning_sha256" in p for p in out["integrity"])


@pytest.mark.parametrize("bad", ["joint_v2", "unknown", None])
def test_d2_each_rows_scan_must_be_in_the_closed_set(tmp_path, bad):
    def setscan(r):
        r["runtime"] = dict(r["runtime"], mtp_verify_scan=bad)
    rc, out = _mod(tmp_path, setscan, setscan)
    assert rc == 2 and any("mtp_verify_scan" in p for p in out["integrity"])


def test_d2_pre_m58_rows_exit_3_before_any_modern_audit(tmp_path, capsys):
    legacy = [{"model": m, "bench": b, "id": i, "finish_reason": "stop", "completion_tokens": 3,
               "content_sha256": "x", "reasoning_sha256": "y"} for m, b, i in KEYS]
    for name, tag in (("A.json", "A"), ("B.json", "B")):
        (tmp_path / name).write_text(json.dumps({"tag": tag, "rows": legacy}))   # no status either
    a = argparse.Namespace(a=str(tmp_path / "A.json"), b=str(tmp_path / "B.json"),
                           out=str(tmp_path / "o.json"))
    assert R.compare(a) == 3
    out = capsys.readouterr().out
    assert "NON-GATING" in out and "INTEGRITY" not in out and "exit 3" in out
    assert json.loads((tmp_path / "o.json").read_text())["legacy"] is True


def test_d2_run_rows_pass_their_own_audit(env, tmp_path):
    assert R.run(_args(tmp_path)) == 0
    doc = _doc(tmp_path)
    by, problems = R._audit(doc)
    assert problems == [] and len(by) == 3


# --------------------------------------------------------------------------- D4 finalisation
@pytest.mark.parametrize("bad", [
    {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}], "usage": [1]},
    {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}], "usage": "n/a"},
    {"choices": ["notadict"], "usage": {"prompt_tokens": 1, "completion_tokens": 1}},
    {"choices": [{"message": [], "finish_reason": "stop"}], "usage": {"prompt_tokens": 1,
                                                                         "completion_tokens": 1}},
])
def test_d4_unusual_response_structures_abort_through_the_finaliser(env, monkeypatch, tmp_path, bad):
    calls = _spy_exit(monkeypatch)
    env["responses"] = [bad]
    assert R.run(_args(tmp_path)) == 2
    doc = _doc(tmp_path)
    assert doc["status"] == "aborted" and "malformed" in doc["error"] and len(calls) == 1


def test_d4_an_unexpected_exception_after_entry_is_finalised_with_the_original_error(
    env, monkeypatch, tmp_path
):
    calls = _spy_exit(monkeypatch, drift="C106: drifted")
    monkeypatch.setattr(R.provenance, "worker_serving_facts",
                        lambda *a, **k: (_ for _ in ()).throw(KeyError("surprise")))
    assert R.run(_args(tmp_path)) == 2
    doc = _doc(tmp_path)
    assert len(calls) == 1 and "surprise" in doc["error"] and "served_config_drift" in doc


def test_d4_the_final_c106_refusal_stamps_drift_without_a_second_exit_check(
    env, monkeypatch, tmp_path
):
    calls = _spy_exit(monkeypatch, drift="C106: final drift")
    assert R.run(_args(tmp_path)) == 2
    doc = _doc(tmp_path)
    assert doc["status"] == "aborted" and len(calls) == 1
    assert "C106" in json.dumps(doc["served_config_drift"])


# --------------------------------------------------------------------------- G1b serving-state sides
def _side_rows(scan, joint_rows=None, n=20, **runtime):
    rows = []
    for i in range(n):
        key = ("m", "math500", f"i{i}")
        verify = {"verify_blocks_joint_v1": 5} if (joint_rows is None or i < joint_rows) else {}
        r = _row(key, runtime=dict(RUNTIME, mtp_verify_scan=scan, **runtime), verify=verify)
        rows.append(r)
    return rows


def _g1b(tmp_path, a, b):
    keys = [("m", "math500", f"i{i}") for i in range(20)]
    return _cmp(tmp_path, a, b, expected=keys)


def test_g1b_per_query_vs_joint_with_the_joint_path_on_enough_rows_passes(tmp_path):
    rc, out = _g1b(tmp_path, _side_rows("per_query", joint_rows=0), _side_rows("joint_v1", 18))
    assert rc == 0, out["integrity"]


@pytest.mark.parametrize("joint_rows", [0, 17])
def test_g1b_refuses_when_the_joint_side_barely_ran_the_joint_path(tmp_path, joint_rows):
    rc, out = _g1b(tmp_path, _side_rows("per_query", joint_rows=0), _side_rows("joint_v1", joint_rows))
    assert rc == 2 and any(f"only {joint_rows} of 20" in p for p in out["integrity"])
    rc, out = _g1b(tmp_path, _side_rows("joint_v1", joint_rows), _side_rows("per_query", joint_rows=0))
    assert rc == 2                                        # either side order


def test_g1b_refuses_a_joint_v1_plus_ab_side(tmp_path):
    rc, out = _g1b(tmp_path, _side_rows("per_query", joint_rows=0), _side_rows("joint_v1+ab", 20))
    assert rc == 2 and any("joint_v1+ab" in p for p in out["integrity"])


def test_g1b_a_side_must_have_one_serving_state(tmp_path):
    b = _side_rows("joint_v1", 20)
    b[3]["runtime"]["mtp_verify_scan"] = "per_query"
    rc, out = _g1b(tmp_path, _side_rows("per_query", joint_rows=0), b)
    assert rc == 2 and any("do not share one serving state" in p for p in out["integrity"])


@pytest.mark.parametrize("field,value", [("attention_policy", "auto"), ("draft_kind", "off"),
                                         ("lazy_prompt_embeddings", True)])
def test_g1b_only_the_scan_may_differ_between_sides(tmp_path, field, value):
    rc, out = _g1b(tmp_path, _side_rows("per_query", joint_rows=0),
                   _side_rows("joint_v1", 20, **{field: value}))
    assert rc == 2 and any(field in p for p in out["integrity"])


def test_g1b_same_scan_reload_control_needs_no_joint_rows(tmp_path):
    rc, out = _g1b(tmp_path, _side_rows("per_query", joint_rows=0), _side_rows("per_query", joint_rows=0))
    assert rc == 0, out["integrity"]


def test_g1b_different_serving_code_between_sides_is_refused(tmp_path):
    keys = [("m", "math500", f"i{i}") for i in range(20)]
    pa = _write(tmp_path, "A.json", _side_rows("per_query", joint_rows=0), "A", expected=keys)
    pb = _write(tmp_path, "B.json", _side_rows("joint_v1", 20), "B", expected=keys)
    for name, code in (("A.json", {"src/mlx-vlm": "aaa"}), ("B.json", {"src/mlx-vlm": "bbb"})):
        doc = json.loads((tmp_path / name).read_text()); doc["code"] = code
        (tmp_path / name).write_text(json.dumps(doc))
    a = argparse.Namespace(a=pa, b=pb, out=str(tmp_path / "o.json"))
    assert R.compare(a) == 2
    assert any("serving code" in p for p in json.loads((tmp_path / "o.json").read_text())["integrity"])


def test_run_records_the_serving_code_state(env, monkeypatch, tmp_path):
    monkeypatch.setattr(R.provenance, "_git_shas", lambda: {"serving_path": {"src/mlx-vlm": "abc"}})
    assert R.run(_args(tmp_path)) == 0
    assert _doc(tmp_path)["code"] == {"src/mlx-vlm": "abc"}
