"""Offline checks for the Open WebUI end-to-end web-search gate. No network, no model."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import owui_e2e_gate as g

QUERIES = json.loads((Path(__file__).resolve().parent / "queries.json").read_text())["queries"]

METRICS_LINE = ("2026-09-17 22:35:51 [INFO] mlx-serve.metrics — /v1/chat/completions 200 | "
                "model=Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 19885ms | TTFT=5279ms | 42.7 tok/s | "
                "prompt=11104 | completion=624")


def _fc(name, args, call_id, result_text):
    return [
        {"type": "function_call", "name": name, "arguments": json.dumps(args), "call_id": call_id, "status": "completed"},
        {"type": "function_call_output", "call_id": call_id, "output": [{"type": "input_text", "text": result_text}]},
    ]


def _msg(answer, *, searched=True, sources=1, done=True):
    search_json = json.dumps([{"title": "Canberra - Wikipedia", "link": "https://en.wikipedia.org/wiki/Canberra",
                               "snippet": "Canberra is the capital city of Australia"}]) if searched else json.dumps([])
    out = [{"type": "reasoning", "status": "completed", "content": "..."}]
    out += _fc("search_web", {"query": "capital of Australia", "count": 5}, "c1", search_json)
    out += [{"type": "message", "status": "completed" if done else "in_progress", "role": "assistant",
             "content": [{"type": "output_text", "text": answer}]}]
    srcs = [{"source": {"name": "search_web", "id": "search_web"}, "document": ["Canberra is the capital"],
             "metadata": [{"source": "https://en.wikipedia.org/wiki/Canberra"}]}] * sources
    return {"done": done, "output": out, "sources": srcs, "content": answer}


ITEM = next(q for q in QUERIES if q["id"] == "fact-05")
ROUNDS = [{"status": 200, "model": "m", "wall_ms": 1, "ttft_ms": 1, "decode_tps": 40.0, "prompt": 3000, "completion": 800}]


def test_stratified_selection_is_seeded_and_covers_every_category():
    a = g.select_stratified(QUERIES, 2, 20260920)
    b = g.select_stratified(QUERIES, 2, 20260920)
    assert a == b
    assert len(a) == 10
    assert sorted({q["category"] for q in a}) == sorted({q["category"] for q in QUERIES})
    assert g.select_stratified(QUERIES, 2, 1) != a  # the seed matters


def test_output_dir_refuses_reuse(tmp_path):
    d = tmp_path / "run"
    g.prepare_output(d)
    (d / "x").write_text("1")
    with pytest.raises(FileExistsError):
        g.prepare_output(d)


def test_router_metrics_parse():
    rows = g.parse_router_metrics("noise\n" + METRICS_LINE + "\n")
    assert rows == [{"status": 200, "model": "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "wall_ms": 19885,
                     "ttft_ms": 5279, "decode_tps": 42.7, "prompt": 11104, "completion": 624}]


def test_derived_timeout_is_budget_over_floor_rate_not_a_default():
    t = g.derive_round_timeout(81920, 11.5)
    assert t > 81920 / 11.5
    assert g.resolved_thinking_budget(81920, 102400, 262144, 3000) == 81920
    assert g.resolved_thinking_budget(81920, 102400, 262144, 200000) == int((262144 - 200000) * 0.8)


def test_completion_payload_is_the_native_web_search_shape():
    p = g.completion_payload("m", "q", "chat", "asst", "sess")
    assert p["features"]["web_search"] is True and p["stream"] is True
    assert p["params"]["tool_approval_mode"] == "full"
    assert not any(p["background_tasks"].values())
    chat, uid, aid = g.chat_payload("m", "q", "t")
    assert chat["history"]["currentId"] == aid and chat["history"]["messages"][aid]["parentId"] == uid
    assert chat["params"]["tool_approval_mode"] == "full"


def test_grade_pass_requires_every_flag():
    msg = _msg("The capital is Canberra [1].")
    f = g.grade_item(ITEM, msg, ROUNDS, 81920, 102400, 262144)
    assert f["PASS"] and f["searched"] and f["cited"] and f["converged"] and f["expectation_hit"]
    assert f["search_calls"] == 1 and f["fetch_calls"] == 0 and f["sources_n"] == 1

    assert not g.grade_item(ITEM, _msg("The capital is Canberra."), ROUNDS, 81920, 102400, 262144)["PASS"]  # uncited
    assert not g.grade_item(ITEM, _msg("It is Sydney [1]."), ROUNDS, 81920, 102400, 262144)["PASS"]  # expectation miss
    assert not g.grade_item(ITEM, _msg("Canberra [1].", searched=False), ROUNDS, 81920, 102400, 262144)["PASS"]
    assert not g.grade_item(ITEM, _msg("Canberra [1].", sources=0), ROUNDS, 81920, 102400, 262144)["PASS"]
    assert not g.grade_item(ITEM, _msg("Canberra [1].", done=False), ROUNDS, 81920, 102400, 262144)["PASS"]


def test_grade_budget_hit_and_missing_rounds_are_not_converged():
    msg = _msg("Canberra [1].")
    hit = [dict(ROUNDS[0], completion=81920)]
    assert not g.grade_item(ITEM, msg, hit, 81920, 102400, 262144)["converged"]
    assert not g.grade_item(ITEM, msg, [], 81920, 102400, 262144)["converged"]  # no router evidence = not proven


def test_domain_expectation_reads_the_evidence_not_the_answer():
    docs = next(q for q in QUERIES if q["id"] == "docs-03")
    msg = _msg("Use PRAGMA journal_mode=WAL [1].")
    msg["output"][1]["arguments"] = json.dumps({"query": "sqlite wal"})
    msg["output"][2]["output"][0]["text"] = json.dumps([{"title": "WAL", "link": "https://sqlite.org/wal.html", "snippet": "x"}])
    f = g.grade_item(docs, msg, ROUNDS, 81920, 102400, 262144)
    assert f["expect_domain_hit"] is True and f["expect_token_hit"] is None and f["PASS"]


def test_fetch_failures_are_counted():
    msg = _msg("Canberra [1].")
    msg["output"] += _fc("fetch_url", {"url": "https://x"}, "c2", "Access Denied\nYou don't have permission")
    f = g.grade_item(ITEM, msg, ROUNDS, 81920, 102400, 262144)
    assert f["fetch_calls"] == 1 and f["fetch_failed"] == 1 and f["PASS"]
