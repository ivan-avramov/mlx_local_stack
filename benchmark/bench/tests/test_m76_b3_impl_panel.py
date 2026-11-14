"""M76 B3: the panel under `lever=kv` (spec v1.2 "Panel, end to end"): the KV tunes and blind pairs, the both-correct selection
(A5: chain-4 both strict; retrieval excluded, stated), and the workflow the `mtp` lever's panel has — export → freeze (bound to
B8.json's sha and every packet) → judge (Cursor, retries 0) → seal (Claude blind-judge) → ingest — with two judge families
required (a single-family set only under the operator's label), and the signals reading only frozen, B8-bound members."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bench import p426_panel as P
from bench import p426_verify as V

JUDGES = dict(text=[dict(label="claude", family="anthropic", client="claude-code:blind-judge", model="claude-opus"),
                    dict(label="gpt", family="openai", client="cursor-agent", model="gpt-5.6-sol")],
              image=[dict(label="claude", family="anthropic", client="claude-code:blind-judge", model="claude-opus"),
                     dict(label="gem", family="google", client="cursor-agent", model="gemini-3.1-pro")])


def test_kv_tunes_and_build():
    assert P.kv_tunes("n16", "x") == ("m76-n16", "m76-x")
    assert P.kv_tunes("x", "v") == ("m76-x", "m76-v")
    with pytest.raises(ValueError):
        P.kv_tunes("x", "n16")
    assert P.KV_PANEL_BUILD == "s3" and P.A7_BUILD == "s2"


def test_kv_members_are_the_plans_sessions():
    assert P.kv_members() == ("A1", "A2", "A3", "A4", "A5", "A7-s1", "A7-s2", "A7-s3")
    assert P.kv_rubric("A5") == "reasoning" and P.kv_rubric("A7-s3") == "code" and P.kv_rubric("A3") == "vision"


def test_kv_pairs_are_blind_and_balanced():
    items = [(f"i{k}", f"ref {k}", f"test {k}") for k in range(10)]
    pairs = P.kv_make_pairs(items, "n16", "x")
    assert sum(1 for p in pairs if "@m76-x::" in p["a_key"]) == 5
    assert all(p["pair_id"] == f"m76-{p['item_id']}" for p in pairs)
    assert pairs == P.kv_make_pairs(items, "n16", "x")                   # seeded
    for p in pairs:
        assert {p["a_text"], p["b_text"]} == {f"ref {p['item_id'][1:]}", f"test {p['item_id'][1:]}"}


def test_kv_scores_count_the_treatment():
    rows = [dict(item_id="i", order="AB", a_key="e@m76-x::i", b_key="e@m76-n16::i", choice="A"),
            dict(item_id="i", order="BA", a_key="e@m76-x::i", b_key="e@m76-n16::i", choice="A"),
            dict(item_id="j", order="AB", a_key="e@m76-n16::j", b_key="e@m76-x::j", choice="tie"),
            dict(item_id="k", order="AB", a_key="e@m76-n16::k", b_key="e@m76-x::k", choice=None)]
    s = P.kv_item_scores(rows, "n16", "x")
    assert s["i"]["score"] == 0.5 and s["j"]["score"] == 0.5 and s["k"] == {"score": None, "n": 0, "missing": 1}
    rows[1]["order"] = "AB"
    assert P.kv_item_scores(rows, "n16", "x")["i"]["score"] == 1.0


def _strict_row(**kw):
    row = dict(prompt_tokens=131372, resolved_max_tokens=102400, resolved_thinking_budget=81920, thinking_budget=81920,
               finish_reason="stop", completion_tokens=5, content="x")
    row.update(kw)
    return row


def test_kv_select_both_correct_rules():
    ref = {"a": {"content": "ra"}, "b": {"content": "rb"}, "c": {"content": "rc"}}
    test = {"a": {"content": "ta"}, "b": {"content": "tb"}}
    items, excl = P.kv_select("math500", ref, test, correct_ref={"a", "b"}, correct_test={"a"})
    assert items == [("a", "ra", "ta")] and excl == {"missing in an arm": ["c"], "not both correct": ["b"]}
    items, _ = P.kv_select("cjudge", ref, test)
    assert [i[0] for i in items] == ["a", "b"]
    chain = _strict_row(task="reasoning", score=1.0, budget_hit=False)
    ret = _strict_row(task="retrieval", hits=[True] * 5)
    lc_ref = {"c1": chain, "c2": chain, "r1": ret}
    lc_test = {"c1": chain, "c2": dict(chain, score=0.0), "r1": ret}
    items, excl = P.kv_select("longctx", lc_ref, lc_test)
    assert [i[0] for i in items] == ["c1"]                                # chain-4 both strict only
    assert excl == {"not both correct": ["c2"], "retrieval (identical codes when both correct)": ["r1"]}
    draw = dict(score=1.0, budget_hit=False, finish_reason="stop", content="d")
    items, excl = P.kv_select("reasoning", {1: draw, 2: draw}, {1: draw, 2: dict(draw, budget_hit=True)})
    assert [i[0] for i in items] == ["1"] and excl == {"not both correct": ["2"]}


def test_two_judge_families_are_required(tmp_path):
    path = tmp_path / "judges.json"
    path.write_text(json.dumps(JUDGES))
    judges, single = P.kv_judges(path, "text")
    assert [j["label"] for j in judges] == ["claude", "gpt"] and single is None
    one = dict(text=[JUDGES["text"][0], dict(JUDGES["text"][1], family="anthropic")])
    path.write_text(json.dumps(one))
    with pytest.raises(V.RefusalError, match="two different families"):
        P.kv_judges(path, "text")
    judges, single = P.kv_judges(path, "text", single_family_label="operator: no second family handles this, C206")
    assert single == dict(label="operator: no second family handles this, C206", families=["anthropic"])


# ------------------------------------------------------------------------------------------------------------ end to end
def _differ(row):
    text = row["content"] + " (shown differently)"
    out = dict(row, content=text)
    if "content_sha256" in row:
        out["content_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    return out


class Sources(P.KVInputSources):
    """The benchmark inputs with the cjudge corpus replaced by a fixture (`Task <id>`); the vartrack question is the real one."""

    def __init__(self, cjudge=None):
        super().__init__()
        self._cj = cjudge

    def cjudge(self):
        return dict(self._cj)


class Panel:
    """A verified KV world (cjudge + A5, X's answers differ from N16's), its B8.json, a judges file and the input sources."""

    def __init__(self, tmp_path, monkeypatch):
        from bench.tests.test_m76_b3_impl_verify import World

        w = World(tmp_path, monkeypatch, kinds=())
        for label in ("b1", "b2"):
            for arm in ("n16", "x"):
                hook = _differ if arm == "x" else None
                w.leg("cjudge", arm, label, row_hook=hook)
                w.leg("longctx", arm, label, row_hook=hook)
        self.w = w
        self.b8 = V.verify_all_kv(w.rows, w.repo, ("n16", "x"), kinds=("cjudge", "longctx"))
        self.b8_path = tmp_path / "B8.json"
        self.b8_path.write_text(V.dumps(self.b8))
        self.b8_sha = hashlib.sha256(self.b8_path.read_bytes()).hexdigest()
        self.judges = tmp_path / "judges.json"
        self.judges.write_text(json.dumps(JUDGES))
        lc = w.ids["axes"]["longctx"]
        self.cjudge = {str(i): f"Task {i}" for i in w.ids["axes"]["cjudge"]["block1"] + w.ids["axes"]["cjudge"]["block2"]}
        self.sources = Sources(self.cjudge)
        self.lc = {i["id"]: i for i in lc["items"]}
        self.out = tmp_path / "panel"
        self.out.mkdir()

    def export(self, **kw):
        kw.setdefault("sources", self.sources)
        kw.setdefault("members", ("A2", "A5"))
        return P.kv_export(self.w.rows, self.b8_path, self.judges, self.out, kw.pop("prompts", None), **kw)

    def judge_all(self, member, pick="A"):
        d = self.out / member

        def runner(cmd, **kw):
            class R:
                returncode, stderr = 0, ""
                stdout = "cursor-agent 1.2.3" if "--version" in cmd else json.dumps({"choice": pick, "rationale": "r"})
            return R()
        assert P.kv_cursor(d, "gpt", runner=runner)["written"] > 0
        for m in P._read_manifest(d):
            if m["judge"] == "claude":
                (d / m["path"]).with_name(f"{m['pkt']}.verdict.json").write_text(json.dumps({"choice": pick, "rationale": "r"}))
        return P.kv_seal(d, "claude", "claude-code 2.1")


@pytest.fixture
def panel(tmp_path, monkeypatch):
    return Panel(tmp_path, monkeypatch)


def test_export_freezes_each_member_bound_to_b8_and_its_packets(panel):
    done = panel.export()
    a2, a5 = done["A2"], done["A5"]
    n2 = len(panel.w.ids["axes"]["cjudge"]["block1"]) * 2
    assert a2["counts"]["items"] == n2 and a2["counts"]["planned_verdicts"] == n2 * 2 * 2
    lc = panel.w.ids["axes"]["longctx"]
    n_chain = sum(1 for i in lc["items"] if i["task"] == "reasoning")
    assert a5["counts"]["items"] == n_chain and a5["rubric"] == "reasoning"
    assert a5["counts"]["excluded"]["retrieval (identical codes when both correct)"] == len(lc["items"]) - n_chain
    assert "retrieval items are excluded" in a5["excluded"]["rule"][0]
    for f in (a2, a5):
        assert f["b8_sha256"] == panel.b8_sha and f["pair"] == ["n16", "x"] and f["lever"] == "kv" and f["single_family"] is None
        assert [j["family"] for j in f["judges"]] == ["anthropic", "openai"]
    packets = list((panel.out / "A2").glob("*/batch*/p*.md"))
    assert packets and not any(t in p.read_text().lower() for p in packets for t in ("m76", "n16", "tq4", "qwen3.8"))  # allow-shorthand: the blinding check names the identifiers it bans
    with pytest.raises(V.RefusalError, match="exported once"):
        panel.export()


def test_a_changed_packet_after_the_freeze_refuses(panel):
    panel.export()
    pkt = next((panel.out / "A2").glob("gpt/batch*/p*.md"))
    pkt.write_text(pkt.read_text() + "\nedited")
    with pytest.raises(V.RefusalError, match="changed"):
        P.kv_check_frozen(panel.out / "A2")


def test_judge_seal_ingest_and_the_signals_read_the_frozen_members(panel):
    panel.export()
    sealed = panel.judge_all("A2", pick="A")
    assert sealed["sealed"] > 0 and sealed["failed"] == 0
    panel.judge_all("A5", pick="tie")
    members = P.kv_panel_members(panel.out, "n16", "x", panel.b8_sha)
    assert set(members) == {"A2", "A5"}
    n2 = len(panel.w.ids["axes"]["cjudge"]["block1"]) * 2
    assert members["A2"]["judged"] == n2 and members["A2"]["mean"] == pytest.approx(0.5)     # A in both orders: 0.5
    assert members["A5"]["mean"] == pytest.approx(0.5) and members["A5"]["report"]["missing"] == 0
    with pytest.raises(V.RefusalError, match="another B8"):
        P.kv_panel_members(panel.out, "n16", "x", "0" * 64)
    from bench import p426_signals as S

    sig = S.compute_kv(panel.w.rows, panel.b8, b8_sha256=panel.b8_sha, panel=panel.out)
    assert sig["panel"]["family"] == ["A2", "A5"] and sig["panel"]["members"]["A2"]["tested"] is True
    with pytest.raises(V.RefusalError, match="another B8"):
        S.compute_kv(panel.w.rows, panel.b8, b8_sha256="1" * 64, panel=panel.out)


def test_an_unsealed_or_unbound_verdict_is_never_admitted(panel):
    panel.export()
    d = panel.out / "A2"
    for m in P._read_manifest(d):
        (d / m["path"]).with_name(f"{m['pkt']}.verdict.json").write_text(json.dumps({"choice": "A"}))   # bare, never sealed
    frozen, rows, report = P.kv_ingest(d)
    assert rows == [] and report["unsealed"] == len(P._read_manifest(d))
    assert P.kv_panel_members(panel.out, "n16", "x", panel.b8_sha)["A2"]["judged"] == 0


def test_a_single_family_panel_needs_the_operators_label(panel):
    one = dict(text=[JUDGES["text"][0], dict(JUDGES["text"][1], family="anthropic")])
    panel.judges.write_text(json.dumps(one))
    with pytest.raises(V.RefusalError, match="families"):
        panel.export()
    done = panel.export(single_family_label="operator ruling: single family (C206)")
    assert done["A2"]["single_family"]["label"].startswith("operator ruling")


def test_the_panel_cli_takes_the_lever(panel, capsys):
    """The CLI derives A2's inputs from the committed cjudge corpus (no network); a `--prompts` file is only validated."""
    from bench import benchmarks

    real = {it["id"]: it["prompt"] for it in benchmarks.load("cjudge")}
    ids = list(panel.cjudge)
    prompts = panel.out.parent / "prompts.json"
    prompts.write_text(json.dumps({"A2": {ids[0]: real[ids[1]]}}))           # a mis-keyed prompt: refused, nothing exported
    rc = P.main(["--lever", "kv", "kv-export", "--rows-root", str(panel.w.rows), "--b8", str(panel.b8_path), "--judges",
                 str(panel.judges), "--out", str(panel.out), "--members", "A2", "--prompts", str(prompts)])
    assert rc == 2 and "!= the benchmark input" in capsys.readouterr().err and not (panel.out / "A2").exists()
    prompts.write_text(json.dumps({"A2": {ids[0]: real[ids[0]]}}))
    rc = P.main(["--lever", "kv", "kv-export", "--rows-root", str(panel.w.rows), "--b8", str(panel.b8_path), "--judges",
                 str(panel.judges), "--out", str(panel.out), "--members", "A2", "--prompts", str(prompts)])
    assert rc == 0 and (panel.out / "A2" / "FROZEN.json").is_file()
    frozen = json.loads((panel.out / "A2" / "FROZEN.json").read_text())
    assert all(rec["prompt"] == real[i] for i, rec in frozen["inputs"].items())
    assert P.main(["kv-seal", "--out", str(panel.out / "A2"), "--judge", "claude", "--client-version", "1"]) == 2   # lever mtp
    assert P.main(["--lever", "kv", "a7-seal", "--out", str(panel.out / "A2"), "--judge", "claude",
                   "--client-version", "1"]) == 2                                                                # an mtp command
    assert P.main(["--lever", "kv", "kv-eligibility", "--rows-root", str(panel.w.rows), "--b8", str(panel.b8_path)]) == 0
    with pytest.raises(SystemExit):
        P.main(["--lever", "bogus", "kv-seal"])
    err = capsys.readouterr().err
    assert "argument --lever: invalid choice" in err and "mtp" in err and "kv" in err


# ------------------------------------------------------------------------------------- packet inputs (erratum v1.3)
def test_packet_inputs_are_derived_from_b8s_items_and_frozen(panel):
    """v1.3: the tool derives each packet's input from the benchmark input of the B8 item (A2 the cjudge prompt, A5 the
    vartrack question of the item's task seed, never the context) and freezes a per-item input record."""
    from bench.reasoning import build_vartrack

    done = panel.export()
    a2, a5 = done["A2"], done["A5"]
    assert set(a2["inputs"]) == {it["item"] for it in a2["items"]}
    for item, rec in a2["inputs"].items():
        assert rec["item"] == item and rec["prompt"] == panel.cjudge[item] and rec["attachment_sha256"] is None
        assert rec["prompt_sha256"] == hashlib.sha256(rec["prompt"].encode()).hexdigest() and len(rec["input_sha256"]) == 64
    for item, rec in a5["inputs"].items():
        want = build_vartrack(1, 1.0, chain_len=4, seed=panel.lc[item]["task_seed"])[2]
        assert rec["prompt"] == want and len(rec["prompt"]) < 300                     # the question only, not 128K+ of context
    for m in P._read_manifest(panel.out / "A2"):
        assert a2["inputs"][m["item_id"]]["prompt"] in (panel.out / "A2" / m["path"]).read_text()


def test_a_prompts_file_is_validated_never_used(panel):
    ids = sorted(panel.cjudge)
    with pytest.raises(V.RefusalError, match="!= the benchmark input"):
        panel.export(prompts={"A2": {ids[0]: panel.cjudge[ids[1]]}})               # mis-keyed: refused before any packet
    assert not (panel.out / "A2").exists() and not list(panel.out.glob(".*partial"))
    with pytest.raises(V.RefusalError, match="not an item this member judges"):
        panel.export(prompts={"A2": {"no-such-item": "x"}})
    done = panel.export(prompts={"A2": {ids[0]: panel.cjudge[ids[0]]}})
    assert done["A2"]["inputs"][ids[0]]["prompt"] == panel.cjudge[ids[0]]


def test_an_item_without_its_benchmark_input_refuses(panel):
    missing = sorted(panel.cjudge)[0]
    panel.sources = Sources({k: v for k, v in panel.cjudge.items() if k != missing})
    with pytest.raises(V.RefusalError, match="no benchmark input"):
        panel.export(members=("A2",))


def _rewrite_frozen(d, edit):
    doc = json.loads((d / "FROZEN.json").read_text())
    edit(doc)
    (d / "FROZEN.json").write_text(json.dumps(doc, sort_keys=True, indent=1) + "\n")


def test_the_frozen_inputs_bind_every_packet_to_its_item(panel):
    panel.export(members=("A2",))
    d = panel.out / "A2"
    ids = sorted(json.loads((d / "FROZEN.json").read_text())["inputs"])
    keep = (d / "FROZEN.json").read_text()

    def swap(doc):                                      # two items' records exchanged (each re-keyed, so self-consistent ids)
        a, b = doc["inputs"][ids[0]], doc["inputs"][ids[1]]
        doc["inputs"][ids[0]], doc["inputs"][ids[1]] = dict(b, item=ids[0]), dict(a, item=ids[1])

    for edit, match in ((swap, "input sha|does not carry"), (lambda doc: doc.pop("inputs"), "no per-item input record"),
                        (lambda doc: doc["inputs"][ids[0]].update(prompt="another task"), "input sha"),
                        (lambda doc: doc["inputs"][ids[0]].update(item=ids[1]), "keyed to another item")):
        (d / "FROZEN.json").write_text(keep)
        _rewrite_frozen(d, edit)
        with pytest.raises(V.RefusalError, match=match):
            P.kv_check_frozen(d)


# ------------------------------------------------------------------------------------- incomplete panel (erratum v1.3)
def _signals(panel, **kw):
    from bench import p426_signals as S

    return S.compute_kv(panel.w.rows, panel.b8, b8_sha256=panel.b8_sha, panel=panel.out, **kw)


def _flag(sig, name):
    return [f for f in sig["flags"] if f["flag"] == name]


def test_a_complete_panel_has_no_incomplete_flag(panel):
    panel.export()
    panel.judge_all("A2")
    panel.judge_all("A5")
    sig = _signals(panel)
    assert sig["panel"]["status"] == "complete" and sig["panel"]["completeness"]["expected"] == ["A2", "A5"]
    assert not _flag(sig, "panel_incomplete")


def test_a_missing_member_blocks_and_is_not_ingested(panel):
    """v1.3: a panel directory holding only A2 is not a panel: B8 expects A2 and A5."""
    panel.export(members=("A2",))
    panel.judge_all("A2")
    sig = _signals(panel)
    assert "members" not in sig["panel"] and sig["panel"]["status"].startswith("incomplete")
    (f,) = _flag(sig, "panel_incomplete")
    assert f["blocking"] and f["items"] == ["A5"]
    from bench import p426_signals as S
    assert "panel_incomplete" in S.KV_BLOCKING and "status: incomplete" in S.render_kv(sig)


def test_unsealed_or_missing_verdict_slots_block(panel):
    panel.export()
    panel.judge_all("A5")
    d = panel.out / "A2"
    rows = P._read_manifest(d)
    for m in rows[:-1]:                                                      # one judge x order slot never written
        (d / m["path"]).with_name(f"{m['pkt']}.verdict.json").write_text(json.dumps({"choice": "A"}))   # and unsealed
    sig = _signals(panel)
    inc = sig["panel"]["completeness"]["incomplete"]
    assert set(inc) == {"A2"} and inc["A2"]["unsealed"] == len(rows) - 1 and inc["A2"]["missing"] == 1
    assert _flag(sig, "panel_incomplete") and "members" not in sig["panel"]


def test_partial_ingestion_is_explicit_and_labelled(panel):
    panel.export(members=("A2",))
    panel.judge_all("A2")
    sig = _signals(panel, partial=True)
    assert sig["panel"]["mode"] == "partial" and sig["panel"]["status"].startswith("PARTIAL")
    assert sig["panel"]["family"] == ["A2"]
    (f,) = _flag(sig, "panel_incomplete")
    assert f["blocking"] and "--partial" in f["text"]


def test_the_signals_cli_partial_flag(panel, tmp_path, capsys):
    from bench import p426_signals as S

    base = ["all", "--results-root", str(panel.w.rows / "m76"), "--rows-root", str(panel.w.rows), "--b8", str(panel.b8_path),
            "--out-md", str(tmp_path / "o" / "S.md"), "--out-json", str(tmp_path / "o" / "S.json")]
    (tmp_path / "o").mkdir()
    assert S.main(base + ["--lever", "kv", "--partial"]) == 2 and "--partial requires --panel" in capsys.readouterr().err
    assert S.main(base + ["--partial"]) == 2 and "lever-kv" in capsys.readouterr().err


# ------------------------------------------------------------------------------------- exclusion accounting (erratum v1.3)
def test_a_rejected_pairs_exclusions_include_its_rejected_keys(panel):
    b8 = json.loads(json.dumps(panel.b8))
    rec = next(p for p in b8["axes"]["wave1"]["pairs"] if p["kind"] == "cjudge" and p["block"] == "b1")
    keys = [k["key"] for k in rec["keys"]]
    rec["accepted"] = False
    rec["keys"] = [dict(k) for k in rec["keys"][1:]]                          # one key rejected (seed mismatch) …
    rec["keys_rejected"] = [dict(key=keys[0], reason="seed mismatch"), dict(key=keys[1], reason="dup")]   # … one listed twice
    _items, excluded, _identical = P.kv_wave1_select(panel.w.rows, b8, "A2")
    got = excluded["rejected pair b1"]
    assert sorted(got) == sorted(str(k[1]) for k in keys) and len(got) == len(set(got)) == len(keys)


def test_a3_input_is_the_corpus_image_both_arms_saw(tmp_path):
    img = tmp_path / "v1.png"
    img.write_bytes(b"png-bytes")
    good = hashlib.sha256(b"png-bytes").hexdigest()

    class S(P.KVInputSources):
        def vision_rows(self):
            return {"v1": dict(id="v1")}

        def vision_question(self):
            return "Describe this image in detail."

        def resolve_image(self, row):
            return img

    rows = {"v1": {"n16": dict(image_sha256=good), "x": dict(image_sha256=good)}}
    rec, att = P.kv_member_inputs("A3", ["v1"], {}, S(), rows)["v1"]
    assert att == img and rec["attachment_sha256"] == good and rec["prompt"] == "Describe this image in detail."
    with pytest.raises(V.RefusalError, match="both arms"):
        P.kv_member_inputs("A3", ["v1"], {}, S(), {"v1": {"n16": dict(image_sha256=good), "x": dict(image_sha256="0" * 64)}})
    with pytest.raises(V.RefusalError, match="not a vision_gate corpus item"):
        P.kv_member_inputs("A3", ["v2"], {}, S(), rows)
