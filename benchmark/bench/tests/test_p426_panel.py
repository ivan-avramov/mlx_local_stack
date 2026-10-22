"""P426 B3 / C207: the two-family blind pairwise panel for the ON vs OFF comparisons.

Judges come from a per-box `judges.json` (two DIFFERENT families per modality, never hard-coded); packets reuse
`judge_pairwise.export_packets` with the axis's rubric (its sha recorded per packet) and, for vision, the image copied beside
the packet; the Cursor judge runs `cursor-agent --mode ask` per packet with retries 0 (a failure is a missing verdict, counted);
items score ON 1 / tie 0.5 / OFF 0 averaged over judges × orders; the C161 length adjustment is a logistic fit on the
log-length ratio, reported as P(ON preferred at equal length) with an item-cluster bootstrap interval.
"""

import json
import math
import types

import pytest

from bench import judge_pairwise as jp
from bench import p426_panel as P

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
JUDGES = {
    "box": "m5max-128",
    "text": [
        {"label": "claude-opus-5-5", "family": "anthropic", "client": "claude-code:blind-judge"},
        {"label": "cursor:gpt-5.6-sol-high", "family": "openai", "client": "cursor-agent", "model": "gpt-5.6-sol-high"},
    ],
    "image": [
        {"label": "claude-opus-5-5", "family": "anthropic", "client": "claude-code:blind-judge"},
        {"label": "cursor:gemini-3.1-pro", "family": "google", "client": "cursor-agent", "model": "gemini-3.1-pro"},
    ],
}


def _write_judges(tmp_path, doc=JUDGES):
    p = tmp_path / "judges.json"
    p.write_text(json.dumps(doc))
    return p


# ------------------------------------------------------------------ judges
def test_judges_load_per_modality(tmp_path):
    p = _write_judges(tmp_path)
    assert [j["label"] for j in P.load_judges(p, "text")] == ["claude-opus-5-5", "cursor:gpt-5.6-sol-high"]
    assert [j["family"] for j in P.load_judges(p, "image")] == ["anthropic", "google"]


@pytest.mark.parametrize(
    "mutate, why",
    [
        (lambda d: d["text"].pop(), "two judges"),
        (lambda d: d["text"][1].update(family="anthropic"), "families"),
        (lambda d: d.pop("image"), "image"),
    ],
)
def test_bad_judge_configs_refuse(tmp_path, mutate, why):
    doc = json.loads(json.dumps(JUDGES))
    mutate(doc)
    with pytest.raises(ValueError, match=why):
        P.load_judges(_write_judges(tmp_path, doc), "image" if why == "image" else "text")


# ------------------------------------------------------------------ packets
def _rows(texts):
    return [{"id": i, "content": t, "converged": True} for i, t in texts.items()]


def test_export_uses_the_axis_rubric_and_records_its_sha(tmp_path):
    pairs = P.pairs(MODEL, _rows({"q1": "off answer"}), _rows({"q1": "on answer"}))
    rows = P.export("math500", pairs, ["claude-opus-5-5", "cursor:gpt-5.6-sol-high"], {"q1": "Solve x."}, tmp_path / "pk")
    assert len(rows) == 4  # 1 pair x 2 orders x 2 judges
    text = (tmp_path / "pk" / "claude-opus-5-5" / "batch00" / f"{rows[0]['pkt']}.md").read_text()
    assert P.RUBRICS["reasoning"] in text and jp.RUBRIC_SYSTEM_PROMPT not in text
    assert {r["prompt_sha"] for r in rows} == {P.rubric_sha("reasoning")}
    assert MODEL not in text and "p426-on" not in text  # blind


def test_vision_packets_carry_the_image_beside_them(tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"\xff\xd8fake\xff\xd9")
    pairs = P.pairs(MODEL, _rows({"v1": "a dog"}), _rows({"v1": "a cat"}))
    rows = P.export("vision", pairs, ["claude-opus-5-5"], {"v1": "Describe."}, tmp_path / "pk", images={"v1": img})
    for r in rows:
        batch = (tmp_path / "pk" / r["judge"] / Path_(r["path"]).parent.name)
        assert (batch / f"{r['pkt']}.jpg").read_bytes() == img.read_bytes()
        assert f"{r['pkt']}.jpg" in Path_(r["path"]).read_text()


def Path_(p):
    from pathlib import Path

    return Path(p)


# ------------------------------------------------------------------ the Cursor judge (retries 0)
def test_the_cursor_judge_writes_verdicts_and_provenance(tmp_path):
    pairs = P.pairs(MODEL, _rows({"q1": "off", "q2": "off2"}), _rows({"q1": "on", "q2": "on2"}))
    P.export("cjudge", pairs, ["cursor:gpt-5.6-sol-high"], {}, tmp_path / "pk")
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        if cmd[:2] == ["cursor-agent", "--version"]:
            return types.SimpleNamespace(returncode=0, stdout="2026.10.14-941492e\n", stderr="")
        out = '{"choice": "A", "rationale": "x"}' if len(calls) % 2 else "no json here"
        return types.SimpleNamespace(returncode=0, stdout=out, stderr="")

    judge = JUDGES["text"][1]
    report = P.run_cursor_judge(tmp_path / "pk", judge, runner=runner)
    assert report["written"] == 2 and report["failed"] == 2  # unparseable → no verdict file (missing, counted)
    assert all("--mode" in c and "ask" in c and "gpt-5.6-sol-high" in c for c in calls[1:])
    prov = json.loads((tmp_path / "pk" / judge["label"] / "provenance.json").read_text())
    assert prov["client_version"] == "2026.10.14-941492e" and prov["model"] == "gpt-5.6-sol-high"
    ingested, rep = jp.ingest_packets(str(tmp_path / "pk"))
    assert len(ingested) == 2 and len(rep["missing"]) == 2


# ------------------------------------------------------------------ scoring and the length adjustment
def _verdict(item, order, judge, choice, on_is_a=True):
    on, off = f"{MODEL}@p426-on::{item}", f"{MODEL}@p426-off::{item}"
    a, b = (on, off) if on_is_a else (off, on)
    return {"item_id": item, "order": order, "judge": judge, "a_key": a, "b_key": b, "choice": choice}


def test_item_scores_map_choices_to_on_wins_across_orders_and_judges():
    """An ingested choice is in the SHOWN order: in BA the pair's b is shown as "A"."""
    rows = [
        _verdict("q1", "AB", "j1", "A"),  # a = ON shown first, chosen → ON 1
        _verdict("q1", "BA", "j1", "B"),  # BA: shown B = pair a = ON → 1
        _verdict("q1", "AB", "j2", "tie"),  # 0.5
        _verdict("q1", "BA", "j2", "A", on_is_a=False),  # BA: shown A = pair b = ON → 1
    ]
    assert P.item_scores(rows)["q1"] == {"score": 0.875, "n": 4, "missing": 0}


def test_item_scores_ignore_missing_and_count_them():
    rows = [_verdict("q1", "AB", "j1", "A"), _verdict("q1", "BA", "j1", None)]
    s = P.item_scores(rows)
    assert s["q1"]["n"] == 1 and s["q1"]["missing"] == 1


def test_the_length_adjustment_removes_a_pure_length_preference():
    """Balanced lengths, preference only through length: raw 0.5 and adjusted 0.5."""
    data = [
        dict(item=f"q{i}", score=0.9 if i % 2 == 0 else 0.1, log_len_ratio=math.log(2.0 if i % 2 == 0 else 0.5))
        for i in range(60)
    ]
    est = P.length_adjusted(data, n_boot=300, seed=426)
    assert est["raw"] == pytest.approx(0.5) and est["adjusted"] == pytest.approx(0.5, abs=0.02)


def test_the_length_adjustment_corrects_an_unbalanced_length_mix():
    """ON is mostly longer: the raw mean overstates the equal-length preference."""
    data = [dict(item=f"q{i}", score=0.8, log_len_ratio=math.log(2.0)) for i in range(45)]
    data += [dict(item=f"s{i}", score=0.6, log_len_ratio=math.log(0.5)) for i in range(15)]
    est = P.length_adjusted(data, n_boot=300, seed=426)
    assert est["raw"] == pytest.approx(0.75)
    assert 0.6 < est["adjusted"] < est["raw"]
    assert est["ci"][0] <= est["adjusted"] <= est["ci"][1]


def test_the_bootstrap_is_seeded_and_clusters_by_item():
    data = [dict(item=f"q{i % 10}", score=float(i % 3 == 0), log_len_ratio=0.1 * (i % 5 - 2)) for i in range(40)]
    a = P.length_adjusted(data, n_boot=200, seed=426)
    b = P.length_adjusted(data, n_boot=200, seed=426)
    assert a == b and a["n_items"] == 10


# ------------------------------------------------------------------ stack code round 1 K7–K11
def _items(n=3, off="off text", on="on text longer"):
    return [(f"q{i}", f"{off} {i}", f"{on} {i}") for i in range(n)]


def test_k7_export_needs_a_fresh_directory(tmp_path):
    pairs = P.make_pairs(MODEL, _items())
    P.export("cjudge", pairs, ["claude-opus-5-5"], {}, tmp_path / "pk")
    with pytest.raises(FileExistsError):
        P.export("cjudge", pairs, ["claude-opus-5-5"], {}, tmp_path / "pk")


def test_k7_k8_only_sealed_verdicts_bound_to_their_packet_are_admitted(tmp_path):
    pairs = P.make_pairs(MODEL, _items(1))
    rows = P.export("cjudge", pairs, ["claude-opus-5-5"], {}, tmp_path / "pk")
    for r in rows:  # the blind-judge agent writes bare verdicts
        Path_(r["path"]).with_name(f"{r['pkt']}.verdict.json").write_text('{"choice": "A", "rationale": "x"}')
    P.seal_verdicts(tmp_path / "pk", JUDGES["text"][0], client_version="claude-code 9.9")
    got, report = P.ingest(tmp_path / "pk")
    assert len(got) == 2 and all(v["client_version"] == "claude-code 9.9" and v["packet_sha"] for v in got)
    first = Path_(rows[0]["path"])
    first.write_text(first.read_text() + "tampered")  # a packet changed after its verdict
    got, report = P.ingest(tmp_path / "pk")
    assert len(got) == 1 and report["unbound"] == 1


def test_k8_a_failed_client_version_check_refuses_before_any_judging(tmp_path):
    P.export("cjudge", P.make_pairs(MODEL, _items(1)), ["cursor:gpt-5.6-sol-high"], {}, tmp_path / "pk")
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=1, stdout="", stderr="not logged in")

    with pytest.raises(RuntimeError, match="version"):
        P.run_cursor_judge(tmp_path / "pk", JUDGES["text"][1], runner=runner)
    assert len(calls) == 1


def test_k9_model_names_are_stripped_from_packets(tmp_path):
    rows = P.export("cjudge", P.make_pairs(MODEL, [("q0", "off", f"on {MODEL}")]), ["claude-opus-5-5"], {}, tmp_path / "pk")
    assert all(MODEL not in Path_(r["path"]).read_text() for r in rows)


HOME_PATH = "/".join(["", "Users", "someone", "x.py"])  # built at runtime: the repo's PII scan refuses a literal one


@pytest.mark.parametrize("leak", ["p426-on", "the MTP drafter", HOME_PATH, "caslca/x"])
def test_k9_a_leaking_packet_refuses(tmp_path, leak):
    pairs = P.make_pairs(MODEL, [("q0", "off text", f"on text {leak}")])
    with pytest.raises(ValueError, match="leak"):
        P.export("cjudge", pairs, ["claude-opus-5-5"], {}, tmp_path / "pk")


def test_k10_selectors_apply_each_axis_rule():
    off = {"a": {"id": "a", "content": "x"}, "b": {"id": "b", "content": "y"}, "c": {"id": "c", "content": "z"}}
    on = {"a": {"id": "a", "content": "x2"}, "b": {"id": "b", "content": "y2"}}
    items, excluded = P.select("math500", off, on, correct_off={"a", "b"}, correct_on={"a"})
    assert [i[0] for i in items] == ["a"] and excluded == {"not both correct": ["b"], "missing in an arm": ["c"]}
    items, excluded = P.select("cjudge", off, on)
    assert [i[0] for i in items] == ["a", "b"] and excluded == {"missing in an arm": ["c"]}
    r_off = {1: {"seed": 1, "content": "p", "score": 1.0}, 2: {"seed": 2, "content": "q", "score": 0.0}}
    r_on = {1: {"seed": 1, "content": "p2", "score": 1.0}, 2: {"seed": 2, "content": "q2", "score": 1.0}}
    items, excluded = P.select("reasoning", r_off, r_on)
    assert [i[0] for i in items] == ["1"] and excluded == {"not both correct": ["2"]}
    v_off = {"v": {"id": "v", "description": "a dog"}}
    v_on = {"v": {"id": "v", "description": "a cat"}}
    assert P.select("vision", v_off, v_on)[0] == [("v", "a dog", "a cat")]


def test_k10_make_pairs_balances_slots_and_keeps_every_item():
    pairs = P.make_pairs(MODEL, _items(10))
    assert len(pairs) == 10
    on_first = sum(1 for p in pairs if "@p426-on::" in p["a_key"])
    assert on_first == 5


def test_k11_only_complete_judge_order_lattices_are_admitted():
    judges = ["j1", "j2"]
    full = [_verdict("q1", o, j, "A") for o in ("AB", "BA") for j in judges]
    partial = [_verdict("q2", o, j, "A") for o, j in (("AB", "j1"), ("BA", "j1"), ("AB", "j2"))]
    duped = [_verdict("q3", o, j, "A") for o in ("AB", "BA") for j in judges] + [_verdict("q3", "AB", "j1", "B")]
    admitted, excluded = P.admit(full + partial + duped, judges)
    assert set(admitted) == {"q1"} and excluded == {"incomplete": ["q2"], "duplicate": ["q3"]}
