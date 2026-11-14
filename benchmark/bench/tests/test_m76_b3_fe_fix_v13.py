"""Delivery 4: erratum-v1.3 failing cases — A7 provenance (a session pair differing in a non-whitelisted manifest field is rejected),
panel inputs bound to B8's items (a caller prompt not matching the derived input sha refuses; a tampered frozen record refuses),
an incomplete panel blocks (`panel_incomplete`), exclusion accounting. Class (c) throughout. Real committed manifest as the A7 base."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from bench import p426_panel as P, p426_signals as S, p426_verify as V
from bench.tests import test_m76_b3_fe_surface as G

MAN = G.REPO / "benchmark" / "results" / G.ENTRY / "math500.p426s2-on-b1.manifest.json"


# ----------------------------------------------------------------------------------------------- A7 provenance
@pytest.fixture(scope="module")
def base_manifest():
    m = json.loads(MAN.read_text())
    m.setdefault("runtime", {})["lang"] = "python"
    return m


def a7_tree(tmp_path, ref_man, test_man, session="s1", extra_test=None):
    """results_root/wave2/<attempt>/<session>/{python.jsonl, python.manifest.json} for each arm."""
    atts = {}
    for arm, man in (("n16", ref_man), ("x", test_man)):
        d = tmp_path / "wave2" / f"tg1-m76-{arm}-{session}.a1" / session
        d.mkdir(parents=True)
        (d / "python.jsonl").write_text("{}\n")
        if man is not None:
            (d / "python.manifest.json").write_text(json.dumps(man))
        atts[arm] = {"path": d.parent, "name": f"tg1-m76-{arm}-{session}.a1"}
    return V.Reader(tmp_path), atts


def reasons(tmp_path, ref, test):
    reader, atts = a7_tree(tmp_path, ref, test)
    return V.kv_a7_provenance_reasons(reader, "s1", atts, "n16", "x")


def test_a7_identical_manifests_and_per_invocation_identity_are_accepted(tmp_path, base_manifest):
    other = copy.deepcopy(base_manifest)
    other["run_id"] = "other-run"
    other["worker"] = {"pid": 99}
    other["cleanup_status"] = "x"
    other["router_history"] = [{"pid": 1}]
    other["timestamp"] = "2001-01-01T00:00:00Z"
    other["runtime"]["invocation_nonce"] = "zzz"
    assert reasons(tmp_path, base_manifest, other) == []


def test_a7_the_whitelisted_kv_keys_may_differ(tmp_path, base_manifest):
    other = copy.deepcopy(base_manifest)
    other.setdefault("kv", {})["kv_bits"] = 4
    other["kv"]["tq4_attention"] = "m72_exact"
    other.setdefault("git", {})["stack_head"] = "e" * 40
    assert reasons(tmp_path, base_manifest, other) == []


@pytest.mark.parametrize("path,value", [
    (("sampling", "temperature"), 0.987), (("sampling", "thinking_budget"), 3), (("sampling_profile",), "other"),
    (("runtime", "apc_enabled"), True), (("runtime", "mtp_verify_scan"), "per_query"), (("runtime", "draft_kind"), "none"),
    (("runtime", "prefill_step_size"), 7), (("git", "mlx_vlm"), "0" * 40), (("fingerprint_version",), 999)])
def test_a7_a_difference_outside_the_whitelist_rejects_the_session_pair(tmp_path, base_manifest, path, value):
    other = copy.deepcopy(base_manifest)
    node = other
    for p in path[:-1]:
        node = node.setdefault(p, {})
    node[path[-1]] = value
    got = reasons(tmp_path, base_manifest, other)
    assert got and all(r.startswith("rule 2d") for r in got), got


def test_a7_a_missing_or_unreadable_manifest_rejects(tmp_path, base_manifest):
    assert reasons(tmp_path, base_manifest, None)
    reader, atts = a7_tree(tmp_path / "b", base_manifest, base_manifest)
    (atts["x"]["path"] / "s1" / "python.manifest.json").write_text("{not json")
    assert V.kv_a7_provenance_reasons(reader, "s1", atts, "n16", "x")


def test_a7_an_arm_without_a_manifest_for_a_language_the_other_ran_rejects(tmp_path, base_manifest):
    go = copy.deepcopy(base_manifest)
    go["runtime"]["lang"] = "go"
    reader, atts = a7_tree(tmp_path, base_manifest, base_manifest)
    (atts["n16"]["path"] / "s1" / "go.jsonl").write_text("{}\n")
    (atts["n16"]["path"] / "s1" / "go.manifest.json").write_text(json.dumps(go))
    got = V.kv_a7_provenance_reasons(reader, "s1", atts, "n16", "x")
    assert any("go" in r for r in got)


def test_a7_normalisation_drops_only_identity_and_the_kv_flags_of_the_arm_identity(base_manifest):
    m = copy.deepcopy(base_manifest)
    m["run_id"], m["worker"] = "r", {"pid": 1}
    m["runtime"]["arm_identity"] = {"flags": {"--kv-bits": "4", "--tq4-attention": "m72_exact", "--prefill-step-size": "512"},
                                    "entry": {"kv_bits": 4, "tq4_attention": "m72_exact", "max_kv_cache_size": 1}}
    m["runtime"]["arm_identity_sha256"] = "abc"
    n = V.kv_a7_normalise(m)
    assert "run_id" not in n and "worker" not in n and "arm_identity_sha256" not in n["runtime"]
    assert n["runtime"]["arm_identity"] == {"flags": {"--prefill-step-size": "512"}, "entry": {"max_kv_cache_size": 1}}
    assert m["run_id"] == "r"                                           # the input is not mutated


# ----------------------------------------------------------------------------------------------- panel inputs bound to B8's items
def derived(member="A1", item="q1", prompt="Solve x + 1 = 2.", attachment=None):
    return {item: (P._input_record(member, item, prompt, P.KV_INPUT_SOURCE[member], attachment), attachment)}


def test_a_caller_prompt_that_matches_the_derived_input_is_accepted():
    P.kv_validate_prompts("A1", {"q1": "Solve x + 1 = 2."}, derived())
    P.kv_validate_prompts("A1", None, derived())
    P.kv_validate_prompts("A1", {}, derived())


@pytest.mark.parametrize("given", [{"q1": "Task q1"}, {"q1": "Solve x + 1 = 2. "}, {"q1": ""}, {"q1": None}, {"q1": 5},
                                   {"other": "Solve x + 1 = 2."}])
def test_a_caller_prompt_that_does_not_match_the_derived_input_sha_refuses(given):
    with pytest.raises(V.RefusalError):
        P.kv_validate_prompts("A1", given, derived())


def test_the_input_sha_covers_member_item_prompt_and_attachment():
    a = P._input_record("A1", "q1", "p", "s")
    assert a["input_sha256"] != P._input_record("A2", "q1", "p", "s")["input_sha256"]
    assert a["input_sha256"] != P._input_record("A1", "q2", "p", "s")["input_sha256"]
    assert a["input_sha256"] != P._input_record("A1", "q1", "p2", "s")["input_sha256"]
    assert a["prompt_sha256"] == hashlib.sha256(b"p").hexdigest()
    with pytest.raises(V.RefusalError):
        P._input_record("A1", "q1", "  ", "s")                         # an empty benchmark input refuses


class Src:
    def __init__(self, **kw):
        self.kw = kw

    def math500(self):
        return self.kw.get("math500", {})

    def cjudge(self):
        return self.kw.get("cjudge", {})

    def vartrack_question(self, seed, chain_len):
        return f"Q(seed={seed},chain={chain_len})"


def test_inputs_are_derived_from_the_benchmark_not_from_the_caller():
    got = P.kv_member_inputs("A1", ["q1"], {}, Src(math500={"q1": "Problem one"}))
    assert got["q1"][0]["prompt"] == "Problem one" and got["q1"][1] is None
    with pytest.raises(V.RefusalError):
        P.kv_member_inputs("A1", ["q2"], {}, Src(math500={"q1": "Problem one"}))           # an item without its input
    a4 = P.kv_member_inputs("A4", ["128000000"], {}, Src())
    assert a4["128000000"][0]["prompt"] == "Q(seed=128000000,chain=4)"
    with pytest.raises(V.RefusalError):
        P.kv_member_inputs("A4", ["not-a-seed"], {}, Src())


def test_a5_inputs_are_the_question_of_a_chain4_item_only():
    ids = {"longctx_items": {"c1": {"task": "reasoning", "task_seed": 77}, "r1": {"task": "retrieval", "task_seed": 5}},
           "longctx_chain_len": 4}
    got = P.kv_member_inputs("A5", ["c1"], ids, Src())
    assert got["c1"][0]["prompt"] == "Q(seed=77,chain=4)"
    with pytest.raises(V.RefusalError):
        P.kv_member_inputs("A5", ["r1"], ids, Src())                    # retrieval items are never judged
    with pytest.raises(V.RefusalError):
        P.kv_member_inputs("A5", ["nope"], ids, Src())


# a frozen record is re-checked: every tamper of the per-item input refuses
def frozen_dir(tmp_path, prompt="Problem one", attachment_ok=True):
    out = tmp_path / "A1"
    out.mkdir()
    (out / "p1.md").write_text(f"# packet\n\n{prompt}\n\nanswer A / B\n")
    rec = P._input_record("A1", "q1", prompt, "src")
    doc = {"member": "A1", "items": [{"item": "q1"}], "inputs": {"q1": rec}}
    rows = [{"item_id": "q1", "path": "p1.md", "pkt": "p1"}]
    return doc, rows, out


def check(doc, rows, out):
    P._kv_check_inputs(doc, rows, out, "A1")


def test_a_consistent_frozen_input_record_passes(tmp_path):
    check(*frozen_dir(tmp_path))


@pytest.mark.parametrize("tamper", ["prompt", "prompt_sha", "input_sha", "key", "missing", "extra", "packet", "attachment"])
def test_every_tamper_of_the_frozen_input_record_refuses(tmp_path, tamper):
    doc, rows, out = frozen_dir(tmp_path)
    rec = doc["inputs"]["q1"]
    if tamper == "prompt":
        rec["prompt"] = "Another problem"
    elif tamper == "prompt_sha":
        rec["prompt_sha256"] = "0" * 64
    elif tamper == "input_sha":
        rec["input_sha256"] = "0" * 64
    elif tamper == "key":
        doc["inputs"] = {"q1": dict(rec, item="q2")}
    elif tamper == "missing":
        doc["inputs"] = {}
    elif tamper == "extra":
        doc["inputs"]["q9"] = dict(rec, item="q9")
    elif tamper == "packet":
        (out / "p1.md").write_text("# packet\n\nwhatever the caller supplied\n")
    elif tamper == "attachment":
        (out / "p1.png").write_bytes(b"\x89PNG not in the frozen record")
    with pytest.raises(V.RefusalError):
        check(doc, rows, out)


# ----------------------------------------------------------------------------------------------- incomplete panel blocks
B8 = {"pair": ["n16", "x"], "axes": {"wave1": {"pairs": [{"kind": "math500", "accepted": True}, {"kind": "cjudge", "accepted": True},
                                                          {"kind": "vision", "accepted": False}]}}}


def test_expected_members_are_those_with_an_accepted_pair():
    exp = P.kv_expected_members(B8)
    assert P.KV_MEMBER_KIND["A1"] == "math500" and "A1" in exp and "A2" in exp and "A3" not in exp
    withs = dict(B8, axes=dict(B8["axes"], A7={"sessions": ["s1", "s2", "s3"],
                                                "pairs": [{"pair": "s1", "accepted": True}, {"pair": "s2", "accepted": False}]}))
    assert "A7-s1" in P.kv_expected_members(withs) and "A7-s2" not in P.kv_expected_members(withs)


def test_a_missing_member_or_an_unadmitted_slot_is_incomplete():
    full = {"judged": 3, "planned_items": 3, "admitted_verdicts": 12, "planned_verdicts": 12, "report": {}}
    assert P.kv_panel_completeness({"A1": full, "A2": full}, ["A1", "A2"])["complete"] is True
    miss = P.kv_panel_completeness({"A1": full}, ["A1", "A2"])
    assert miss["complete"] is False and miss["missing_members"] == ["A2"]
    short = P.kv_panel_completeness({"A1": dict(full, admitted_verdicts=11), "A2": full}, ["A1", "A2"])
    assert short["complete"] is False and "A1" in short["incomplete"]
    fewer = P.kv_panel_completeness({"A1": dict(full, judged=2), "A2": full}, ["A1", "A2"])
    assert fewer["complete"] is False
    rep = P.kv_panel_completeness({"A1": dict(full, report={"unsealed": ["x"]}), "A2": full}, ["A1", "A2"])
    assert rep["complete"] is False


def test_a_panel_root_missing_an_expected_member_yields_a_blocking_panel_incomplete_flag(tmp_path):
    sec = S.kv_panel_section(tmp_path, B8, "n16", "x", "b" * 64)                      # an empty panel root
    assert sec["status"].startswith("incomplete") and "members" not in sec           # not ingested
    assert set(sec["completeness"]["missing_members"]) == {"A1", "A2"}
    flags = S.kv_flags({"header": {"label": "X − N16"}, "axes": {}, "panel": sec})
    inc = [f for f in flags if f["flag"] == "panel_incomplete"]
    assert len(inc) == 1 and inc[0]["blocking"] is True and set(inc[0]["items"]) == {"A1", "A2"}
    assert "panel_incomplete" in S.KV_BLOCKING


def test_partial_ingestion_is_labelled_and_the_flag_stays(tmp_path):
    sec = S.kv_panel_section(tmp_path, B8, "n16", "x", "b" * 64, partial=True)
    assert sec["status"] == S.KV_PANEL_PARTIAL and sec["mode"] == "partial" and "members" in sec
    flags = S.kv_flags({"header": {"label": "X − N16"}, "axes": {}, "panel": sec})
    assert [f["flag"] for f in flags if f["flag"] == "panel_incomplete"] == ["panel_incomplete"]


def test_a_complete_panel_raises_no_incomplete_flag():
    sig = {"header": {"label": "X − N16"}, "axes": {}, "panel": {"status": "complete", "members": {}, "tested": [],
                                                                  "completeness": {"complete": True, "missing_members": []}}}
    assert not [f for f in S.kv_flags(sig) if f["flag"] == "panel_incomplete"]


def test_partial_needs_a_panel_and_the_kv_lever(tmp_path):
    import io
    import contextlib

    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = S.main(["all", "--partial", "--results-root", str(tmp_path), "--rows-root", str(tmp_path), "--b8", str(tmp_path / "B8.json"),
                     "--out-md", str(tmp_path / "o.md"), "--out-json", str(tmp_path / "o.json")])
    assert rc == 2 and not (tmp_path / "o.md").exists()


# ----------------------------------------------------------------------------------------------- exclusion accounting
def test_a_rejected_pairs_exclusions_cover_its_accepted_and_rejected_keys_once():
    rec = {"keys": [{"key": ["math500", "a"]}, {"key": ["math500", "b"]}],
           "keys_rejected": [{"key": ["math500", "c"]}, {"key": ["math500", "a"]}, {"key": "not-a-list"}, "x"]}
    assert P._rejected_pair_keys(rec) == ["a", "b", "c"]
    assert P._rejected_pair_keys({}) == []
    assert P._rejected_pair_keys({"keys_rejected": [{"key": ["math500", 7]}]}) == ["7"]
