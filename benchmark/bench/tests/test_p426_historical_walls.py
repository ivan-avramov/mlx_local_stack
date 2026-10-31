"""P566: the Wave-2 `--historical-walls` JSON is derived from committed sources (`benchmark/results/p426/wave2/make_historical_walls.py`)."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "results" / "p426" / "wave2" / "make_historical_walls.py"
M = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"


def load():
    spec = importlib.util.spec_from_file_location("make_historical_walls", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def rows(*items):
    return "\n".join(json.dumps(dict(model=m, id=i, wall_s=w, session_id=s)) for m, i, w, s in items) + "\n"


def log_line(session, elapsed, model=M):
    return (f"2026-10-10 21:26:20,838 - mlx_vlm.server - INFO - Request completed: endpoint=/chat/completions model=caslca/{model} "
            f"stream=True backend=cached_session session={session} cached_tokens=0 prompt_tokens=2927 generated_tokens=47 "
            f"elapsed={elapsed:.3f}s prefill=631.2 tok/s decode=26.1 tok/s finish_reason=tool_calls in_flight=0\n")


def export(*messages):
    return json.dumps(dict(info=dict(outcome="completed"), messages=list(messages)))


def msg(created, streamed=None, role="assistant", error=None):
    t = dict(created=created) if streamed is None else dict(created=created, streamed=streamed)
    m = dict(type=role, time=t)
    if error:
        m["error"] = error
    return m


@pytest.fixture
def tree():
    d = {
        f"m63/s1/{M}.s1.opencode_python.jsonl": rows((M, "python/a", 100.0, "ses_a"), ("other-model", "python/x", 9999.0, "ses_x")),
        f"m63/reload/{M}.reload.opencode_python.jsonl": rows((M, "python/b", 1289.1, "ses_b")),
        f"m63/s2/{M}.s2.opencode_go.jsonl": rows((M, "go/c", 511.2, "ses_c")),
        f"m63/archive.attempt1-busy-self/{M}.s1.opencode_go.jsonl": rows((M, "go/z", 5000.0, "ses_z")),
        f"p426/tg1-rehearsal-20261023/s1/{M}.s1.opencode_go.L1.full.a1.jsonl": rows((M, "go/d", 618.5, "ses_d")),
        f"p426/tg1-rehearsal-20261024/s1/{M}.s1.opencode_go.L1.full.a1.jsonl": rows((M, "go/e", 3663.0, "ses_e")),
        "p426/historical/mlx_vlm.request-completed.log": (log_line("ses_a", 378.8) + log_line("ses_b", 50.0)
                                                          + log_line("ses_c", 60.0) + log_line("ses_d", 720.64)
                                                          + log_line("ses_e", 3000.0) + log_line("ses_a", 2000.0, model="other")),
        f"opencode_transcripts/{M}/{M}.s1.opencode_python.L0.full.a2.20261027T101207-x/python__connect.json":
            export(msg(0, 1_061_900), msg(5, 7, role="user")),
        f"opencode_transcripts/{M}/{M}.s1.opencode_go.L1.full.a1.20261027T101207-y/go__book-store.json":
            export(msg(0, 3_653_000, error={"name": "MessageAbortedError"}), msg(0, 2000)),
        f"opencode_transcripts/{M}/{M}.s1.opencode_go.L1.full.a1.20261027T101207-y/go__book-store.final_tree/x.json": "{}",
        f"opencode_transcripts/{M}/{M}.s1.opencode_go.L1.full.a1.20261020T101207-q/go__old.json": export(msg(0, 9_999_000)),
    }
    return {k: v.encode() for k, v in d.items()}


def derive(tree):
    mod = load()
    return mod.derive(sorted(tree), tree.__getitem__)


def test_walls_are_the_largest_item_wall_per_language_over_m63_and_p456_only(tree):
    out = derive(tree)
    assert out["w_python_s"] == 1289.1          # M63 reload; other models and the P486 rehearsal (20261024) ignored
    assert out["w_go_s"] == 618.5               # P456 beats M63's 511.2; archive.* attempts and P486's 3663 excluded


def test_request_elapsed_takes_the_server_log_for_m63_p456_sessions_and_the_p499_export_proxy(tree):
    out = derive(tree)
    by = out["max_request_elapsed_by_source"]
    assert by["m63"] == 378.8 and by["p456"] == 720.64   # only this model's lines, only sessions of the counted rows (not P486's)
    assert by["p499_client_proxy"] == 1061.9              # streamed − created; the errored message excluded; other dates ignored
    assert out["max_request_elapsed_s"] == 1061.9


def test_every_source_is_listed_with_its_sha256(tree):
    out = derive(tree)
    listed = {s["path"]: s["sha256"] for s in out["sources"]}
    assert listed[f"m63/reload/{M}.reload.opencode_python.jsonl"] == hashlib.sha256(tree[f"m63/reload/{M}.reload.opencode_python.jsonl"]).hexdigest()
    assert "p426/historical/mlx_vlm.request-completed.log" in listed
    assert not any("20261024" in p or "archive." in p or "final_tree" in p for p in listed)


def test_missing_log_slice_refuses(tree):
    del tree["p426/historical/mlx_vlm.request-completed.log"]
    with pytest.raises(SystemExit, match="log slice"):
        derive(tree)


def test_a_counted_session_without_log_lines_refuses(tree):
    tree["p426/historical/mlx_vlm.request-completed.log"] = log_line("ses_a", 378.8).encode()
    with pytest.raises(SystemExit, match="no Request completed"):
        derive(tree)


def test_slice_keeps_only_this_models_request_completed_lines_of_the_counted_sessions(tree):
    mod = load()
    log = (log_line("ses_a", 1.0) + "2026-10-10 noise line session=ses_a\n" + log_line("ses_q", 2.0)
           + log_line("ses_d", 3.0, model="other") + log_line("ses_d", 4.0))
    got = mod.slice_lines(log.splitlines(keepends=True), mod.counted_sessions(sorted(tree), tree.__getitem__))
    assert [mod.parse_line(x)["elapsed"] for x in got] == [1.0, 4.0]
