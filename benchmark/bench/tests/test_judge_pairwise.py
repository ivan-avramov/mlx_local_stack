"""Tests for the M38 blind pairwise judge panel (bench.judge_pairwise + bench.run_judge_pairwise)."""
import json
import os

import pytest

import bench.judge_pairwise as J
import bench.run_judge_pairwise as RJ

MODELS = ["ModelAlpha", "ModelBeta", "ModelGamma", "ModelDelta"]


def _rows_by_model(n_items=3, all_converged=True):
    out = {}
    for m in MODELS:
        rows = []
        for i in range(n_items):
            rows.append({"id": f"dom-{i:02d}", "content": f"{m} answer to dom-{i:02d}",
                         "converged": all_converged})
        out[m] = rows
    return out


# --------------------------------------------------------------------------------- blinding
def test_strip_model_names_redacts_names_and_trims_trailing_whitespace():
    text = "ModelAlpha said this, and  ModelBeta   disagreed.   \nNewline.   "
    out = J.strip_model_names(text, MODELS)
    assert "ModelAlpha" not in out and "ModelBeta" not in out
    assert "\n" in out                      # F1: lines are NEVER joined
    assert not any(ln.endswith(" ") for ln in out.split("\n"))   # per-line rstrip only


def test_strip_model_names_passthrough_on_empty():
    assert J.strip_model_names("", MODELS) == ""
    assert J.strip_model_names(None, MODELS) is None


def test_strip_model_names_longest_first_avoids_partial_redaction():
    # "Qwen3.8-27B" is a substring of "Qwen3.8-27B-mlx-uniform-4bit"; the longer name must  # allow-shorthand
    # be redacted whole, not leave a partial "-mlx-uniform-4bit" fragment behind.  # allow-shorthand
    names = ["Qwen3.8-27B", "Qwen3.8-27B-mlx-uniform-4bit"]  # allow-shorthand
    out = J.strip_model_names("See Qwen3.8-27B-mlx-uniform-4bit here.", names)
    assert "mlx-uniform" not in out  # allow-shorthand


# ------------------------------------------------------------------- F1: structure preserved
_MARKDOWN_ANSWER = """# Heading One

Some prose here about the approach.

- bullet one
- bullet two

```python
if v is None:
    pass
```

## Heading Two
More prose."""


def test_strip_model_names_preserves_markdown_structure():
    out = J.strip_model_names(_MARKDOWN_ANSWER, MODELS)
    assert "# Heading One" in out
    assert "## Heading Two" in out
    assert "- bullet one" in out and "- bullet two" in out
    assert "```python" in out and "if v is None:" in out


def test_strip_model_names_collapses_long_blank_runs_only():
    text = "para one\n\n\n\n\npara two"
    out = J.strip_model_names(text, MODELS)
    assert "\n\n\n\n" not in out
    assert "para one" in out and "para two" in out


# ------------------------------------------------------------------------ F2: family tokens
def test_strip_model_names_redacts_family_tokens_case_insensitive():
    for token in J.FAMILY_TOKENS:
        text = f"this looks like a {token.upper()} family checkpoint"
        out = J.strip_model_names(text, [])
        assert token.lower() not in out.lower(), f"{token} leaked"
        assert "[REDACTED]" in out


def test_strip_model_names_does_not_redact_substring_of_unrelated_word():
    # whole-word match: "Qwen" must not eat part of an unrelated word containing it.
    out = J.strip_model_names("Qwentin reported the results.", [])
    assert "Qwentin" in out


def test_strip_model_names_strips_template_tags_including_orphan_think():
    # client._THINK only strips PAIRED <think>...</think>; an orphan close tag (truncated
    # generation) must still be caught here.
    text = "answer text</think>\nmore answer <|special_token|> and a ◁think▷ marker"
    out = J.strip_model_names(text, [])
    assert "</think>" not in out and "<|special_token|>" not in out and "◁think▷" not in out


def test_leaks_helper_detects_each_class():
    assert J._leaks("plain text", []) == []
    assert "family-token" in J._leaks("this is a Qwen model", [])
    assert "template-tag" in J._leaks("tail</think>", [])
    assert "ModelAlpha" in J._leaks("ModelAlpha said it", ["ModelAlpha"])


class _NoopSub:
    """A regex stand-in whose `.sub` is a no-op (simulating a broken/regressed redaction
    pass) while `.search` still delegates to the real compiled pattern — used to prove the
    post-blind assertion actually fires when redaction and detection disagree, rather than
    being decorative (both currently share one regex, so they can never disagree in
    production; this test manufactures the regression to prove the backstop works)."""
    def __init__(self, real):
        self._real = real

    def sub(self, repl, text):
        return text

    def search(self, text):
        return self._real.search(text)


def test_strip_model_names_assertion_fires_on_crafted_leak(monkeypatch):
    monkeypatch.setattr(J, "_FAMILY_RE", _NoopSub(J._FAMILY_RE))
    with pytest.raises(J.BlindingLeak):
        J.strip_model_names("this is a Qwen checkpoint", [])


# ------------------------------------------------------------------------- candidate pairs
def test_shared_converged_items_intersection():
    rows_by_model = _rows_by_model(3)
    rows_by_model["ModelDelta"][0]["converged"] = False  # dom-00 not converged for Delta
    shared = J.shared_converged_items(rows_by_model)
    assert shared == {"dom-01", "dom-02"}


def test_build_candidate_pairs_covers_all_six_pairs_and_items():
    rows_by_model = _rows_by_model(3)
    pairs = J.build_candidate_pairs(rows_by_model, seed=38)
    assert len(pairs) == 6 * 3  # C(4,2) model pairs * 3 shared items
    for p in pairs:
        assert p["anchor_type"] is None and p["expected"] is None
        model_a = p["a_key"].split("::")[0]
        model_b = p["b_key"].split("::")[0]
        assert {model_a, model_b} <= set(MODELS)
        assert model_a != model_b


def test_build_candidate_pairs_requires_four_models():
    rows_by_model = _rows_by_model(3)
    del rows_by_model["ModelDelta"]
    with pytest.raises(ValueError):
        J.build_candidate_pairs(rows_by_model, seed=38)


def test_build_candidate_pairs_deterministic():
    rows_by_model = _rows_by_model(3)
    a = J.build_candidate_pairs(rows_by_model, seed=38)
    b = J.build_candidate_pairs(rows_by_model, seed=38)
    assert a == b


def test_build_candidate_pairs_balanced_ab_per_model_pair():
    # 10 shared items per model pair -> exactly 5 must land each model in slot A (not just an
    # independent coin flip, which would drift at small n).
    rows_by_model = _rows_by_model(10)
    pairs = J.build_candidate_pairs(rows_by_model, seed=38)
    by_model_pair = {}
    for p in pairs:
        ma, mb = p["a_key"].split("::")[0], p["b_key"].split("::")[0]
        key = tuple(sorted((ma, mb)))
        by_model_pair.setdefault(key, []).append(ma)
    for key, a_models in by_model_pair.items():
        n_first_in_a = sum(1 for m in a_models if m == key[0])
        assert n_first_in_a == 5, f"{key}: {n_first_in_a}/10 balanced expected"


# ------------------------------------------------------------------------------ judge families
def test_judge_families_maps_anthropic_and_openai():
    fams = J.judge_families(["opus", "sonnet", "gpt-5.5"])  # allow-shorthand
    assert fams["opus"] == "anthropic" and fams["sonnet"] == "anthropic"  # allow-shorthand
    assert fams["gpt-5.5"] == "openai"


def test_merge_and_shuffle_keeps_all_pairs_deterministically():
    cands = [{"pair_id": f"c{i}"} for i in range(4)]
    anchors = [{"pair_id": f"a{i}"} for i in range(3)]
    merged1 = J.merge_and_shuffle(cands, anchors, seed=38)
    merged2 = J.merge_and_shuffle(cands, anchors, seed=38)
    assert merged1 == merged2
    assert {p["pair_id"] for p in merged1} == {f"c{i}" for i in range(4)} | {f"a{i}" for i in range(3)}


# ------------------------------------------------------------------------------- verdict parse
def test_parse_verdict_extracts_choice_and_rationale():
    out = J.parse_verdict('{"choice": "A", "rationale": "A is more rigorous."}')
    assert out == {"choice": "A", "rationale": "A is more rigorous."}


def test_parse_verdict_normalizes_case_and_accepts_tie():
    assert J.parse_verdict('{"choice": "tie"}')["choice"] == "tie"
    assert J.parse_verdict('{"choice": "b"}')["choice"] == "B"


def test_parse_verdict_trailing_prose_with_brace_does_not_corrupt():
    text = '{"choice": "A"} Note: consider {x} separately.'
    assert J.parse_verdict(text)["choice"] == "A"


def test_parse_verdict_none_on_garbage():
    assert J.parse_verdict("no json here")["choice"] is None
    assert J.parse_verdict("")["choice"] is None
    assert J.parse_verdict('{"choice": "C"}')["choice"] is None


# --------------------------------------------------------------------------- order/normalize
def test_normalize_choice_flips_on_ba_order():
    assert J.normalize_choice("BA", "A") == "B"
    assert J.normalize_choice("BA", "B") == "A"
    assert J.normalize_choice("BA", "tie") == "tie"
    assert J.normalize_choice("AB", "A") == "A"


def test_order_agreement_verdict_truth_table():
    assert J.order_agreement_verdict("A", "A") == "A"
    assert J.order_agreement_verdict("A", "B") == "tie"       # order flip -> tie
    assert J.order_agreement_verdict("tie", "tie") == "tie"
    assert J.order_agreement_verdict(None, "A") == "tie"      # unparsed counts as disagreement


def test_panel_verdict_majority_and_three_way_tie():
    assert J.panel_verdict(["A", "A", "B"]) == "A"             # 2-1 majority
    assert J.panel_verdict(["A", "B", "tie"]) == "tie"         # 1-1-1 -> tie
    assert J.panel_verdict(["tie", "tie", "A"]) == "tie"       # 2-1 majority for tie
    assert J.panel_verdict([]) == "tie"


# --------------------------------------------------------------------------------- call_judge
_PAIR = {"pair_id": "p1", "anchor_type": None, "item_id": "dom-01",
         "a_key": "ModelAlpha::dom-01", "b_key": "ModelBeta::dom-01",
         "a_text": "ModelAlpha wrote this first answer, citing approach one.",
         "b_text": "ModelBeta wrote this second answer, citing approach two.",
         "expected": None}


def test_call_judge_blinds_before_sending():
    captured = {}

    def fake(system, user):
        captured["user"] = user
        return '{"choice": "A", "rationale": "ok"}', None

    J.call_judge(_PAIR, "AB", "x", {"x": fake}, "the task", MODELS)
    assert "ModelAlpha" not in captured["user"] and "ModelBeta" not in captured["user"]


def test_call_judge_both_orders_are_distinct_calls():
    seen = []

    def fake(system, user):
        seen.append(user)
        return '{"choice": "A"}', None

    J.call_judge(_PAIR, "AB", "x", {"x": fake}, "t", MODELS)
    J.call_judge(_PAIR, "BA", "x", {"x": fake}, "t", MODELS)
    assert len(seen) == 2 and seen[0] != seen[1]


def test_call_judge_records_choice_and_prompt_sha():
    fn = lambda s, u: ('{"choice": "B", "rationale": "B wins"}', None)
    row = J.call_judge(_PAIR, "AB", "x", {"x": fn}, "t", MODELS)
    assert row["choice"] == "B"
    assert row["prompt_sha"] == J.PROMPT_SHA
    assert row["pair_id"] == "p1" and row["order"] == "AB" and row["judge"] == "x"


def test_call_judge_unparseable_response_is_choice_none_not_escalated():
    fn = lambda s, u: ("garbage, not json", None)
    row = J.call_judge(_PAIR, "AB", "x", {"x": fn}, "t", MODELS)
    assert row["choice"] is None
    assert row["raw"] == "garbage, not json"


def test_call_judge_retries_then_succeeds():
    calls = {"n": 0}

    def flaky(system, user):
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("boom")
        return '{"choice": "A"}', None

    row = J.call_judge(_PAIR, "AB", "x", {"x": flaky}, "t", MODELS,
                       retries=2, backoff=0, sleep=lambda s: None)
    assert row["choice"] == "A"
    assert calls["n"] == 2


def test_call_judge_escalates_after_exhausting_retries():
    def always_fails(system, user):
        raise ConnectionError("boom")

    with pytest.raises(J.TransportEscalation):
        J.call_judge(_PAIR, "AB", "x", {"x": always_fails}, "t", MODELS,
                     retries=2, backoff=0, sleep=lambda s: None)


def test_call_judge_cost_log_accumulates_tokens():
    fn = lambda s, u: ('{"choice": "A"}', {"input_tokens": 100, "output_tokens": 20})
    cost_log = {}
    J.call_judge(_PAIR, "AB", "x", {"x": fn}, "t", MODELS, cost_log=cost_log)
    J.call_judge(_PAIR, "BA", "x", {"x": fn}, "t", MODELS, cost_log=cost_log)
    assert cost_log["x"] == {"calls": 2, "input_tokens": 200, "output_tokens": 40}


def test_call_judge_cost_log_unknown_usage_stays_null_not_zero():
    # A codex-shaped backend never reports usage — the cost log must show `null` (unknown),
    # never a fabricated 0 that reads as "confirmed zero tokens spent".
    fn = lambda s, u: ('{"choice": "A"}', None, None)
    cost_log = {}
    J.call_judge(_PAIR, "AB", "codex", {"codex": fn}, "t", MODELS, cost_log=cost_log)
    J.call_judge(_PAIR, "BA", "codex", {"codex": fn}, "t", MODELS, cost_log=cost_log)
    assert cost_log["codex"] == {"calls": 2, "input_tokens": None, "output_tokens": None}


# ---------------------------------------------------------------------- F3: truncation/refusal
def test_call_judge_truncation_is_null_with_reason():
    fn = lambda s, u: ('{"choi', None, "max_tokens")   # truncated mid-JSON
    row = J.call_judge(_PAIR, "AB", "x", {"x": fn}, "t", MODELS)
    assert row["choice"] is None
    assert row["null_reason"] == "max_tokens"
    assert row["stop_reason"] == "max_tokens"


def test_call_judge_refusal_is_null_with_reason_even_if_json_parses():
    # even a well-formed JSON body is forced to null on a refusal stop_reason (spec: the
    # stop_reason wins, not a lucky parse).
    fn = lambda s, u: ('{"choice": "A"}', None, "refusal")
    row = J.call_judge(_PAIR, "AB", "x", {"x": fn}, "t", MODELS)
    assert row["choice"] is None
    assert row["null_reason"] == "refusal"


def test_call_judge_normal_stop_reason_is_not_nulled():
    fn = lambda s, u: ('{"choice": "A"}', None, "end_turn")
    row = J.call_judge(_PAIR, "AB", "x", {"x": fn}, "t", MODELS)
    assert row["choice"] == "A"
    assert row["null_reason"] is None
    assert row["stop_reason"] == "end_turn"


class _FakeAnthropicResp:
    def __init__(self, text, input_tokens=10, output_tokens=5, stop_reason="end_turn"):
        import types
        self.content = [types.SimpleNamespace(type="text", text=text)]
        self.usage = types.SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
        self.stop_reason = stop_reason


class _FakeAnthropicClient:
    def __init__(self, text, **kw):
        import types
        self.captured = {}
        self.messages = types.SimpleNamespace(create=self._create)
        self._resp = _FakeAnthropicResp(text, **kw)

    def _create(self, **kwargs):
        self.captured = kwargs
        return self._resp


def test_anthropic_call_passes_generous_max_tokens_and_output_config():
    client = _FakeAnthropicClient('{"choice": "A"}')
    text, usage, stop_reason = J._anthropic_call("claude-opus-5", "sys", "usr", client=client)
    assert client.captured["max_tokens"] == 16000
    assert client.captured["max_tokens"] > 4096          # F3: must not be the old 4096
    assert client.captured["output_config"] == {"effort": "low"}  # allow-shorthand
    assert text == '{"choice": "A"}'
    assert usage == {"input_tokens": 10, "output_tokens": 5}
    assert stop_reason == "end_turn"


def test_anthropic_call_surfaces_max_tokens_stop_reason():
    client = _FakeAnthropicClient('{"choi', stop_reason="max_tokens")
    _, _, stop_reason = J._anthropic_call("claude-opus-5", "s", "u", client=client)
    assert stop_reason == "max_tokens"


# ------------------------------------------------------------------------------- run_pairwise
def _pairs_two():
    return [dict(_PAIR), {**_PAIR, "pair_id": "p2", "item_id": "dom-02"}]


def test_run_pairwise_issues_both_orders_every_judge(tmp_path):
    fn = lambda s, u: ('{"choice": "A"}', None)
    judge_fns = {"j1": fn, "j2": fn}
    out = tmp_path / "verdicts.jsonl"
    made = J.run_pairwise(_pairs_two(), ["j1", "j2"], judge_fns, {}, MODELS, str(out),
                          now=lambda: 0)
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert made == 2 * 2 * 2   # 2 pairs * 2 orders * 2 judges
    assert len(rows) == made
    seen = {(r["pair_id"], r["order"], r["judge"]) for r in rows}
    assert len(seen) == made


def test_run_pairwise_resumes_skipping_done_rows(tmp_path):
    fn_calls = {"n": 0}

    def fn(s, u):
        fn_calls["n"] += 1
        return '{"choice": "A"}', None

    out = tmp_path / "verdicts.jsonl"
    J.run_pairwise(_pairs_two(), ["j1"], {"j1": fn}, {}, MODELS, str(out), now=lambda: 0)
    first_n = fn_calls["n"]
    assert first_n == 4  # 2 pairs * 2 orders * 1 judge

    made_second = J.run_pairwise(_pairs_two(), ["j1"], {"j1": fn}, {}, MODELS, str(out),
                                 now=lambda: 0)
    assert made_second == 0
    assert fn_calls["n"] == first_n  # no new calls issued


def test_run_pairwise_escalation_stops_and_leaves_prior_rows(tmp_path):
    def boom(s, u):
        raise ConnectionError("boom")

    out = tmp_path / "verdicts.jsonl"
    ok = lambda s, u: ('{"choice": "A"}', None)
    judge_fns = {"good": ok, "bad": boom}
    with pytest.raises(J.TransportEscalation):
        J.run_pairwise(_pairs_two(), ["good", "bad"], judge_fns, {}, MODELS, str(out),
                       retries=0, backoff=0, sleep=lambda s: None, now=lambda: 0)
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert all(r["judge"] == "good" for r in rows)  # bad's rows never got graded/written


# ----------------------------------------------------------------------------------- CLI
def _write_model_rows(root, n_items=2):
    for m in MODELS:
        d = root / m
        d.mkdir()
        with open(d / "cjudge.m38.jsonl", "w") as f:
            for i in range(n_items):
                f.write(json.dumps({"id": f"dom-{i:02d}", "content": f"{m} says {i}",
                                    "converged": True}) + "\n")


def _write_anchor_pairs(path, n=2):
    with open(path, "w") as f:
        for i in range(n):
            f.write(json.dumps({"pair_id": f"anchor-identity-{i:02d}", "anchor_type": "identity",
                                "item_id": f"dom-{i:02d}", "a_key": "x::orig", "b_key": "x::identity",
                                "a_text": "same text", "b_text": "same text",
                                "expected": "tie"}) + "\n")


def test_cli_dry_run_calls_no_judge_and_writes_manifest(tmp_path, monkeypatch):
    _write_model_rows(tmp_path)
    anchors = tmp_path / "pairs.jsonl"
    _write_anchor_pairs(anchors)
    out = tmp_path / "out"

    def boom():
        raise AssertionError("dry-run must not build real judge backends")
    monkeypatch.setattr(J, "default_judge_fns", boom)

    rc = RJ.main(["--models", *MODELS, "--anchors", str(anchors), "--out", str(out),
                 "--results-dir", str(tmp_path),
                 "--corpus", str(tmp_path / "no_corpus.jsonl"), "--dry-run"])
    assert rc == 0
    manifest = (out / "pair_manifest.jsonl").read_text().splitlines()
    assert len(manifest) == 6 * 2 + 2   # 6 model-pairs * 2 items + 2 anchors
    assert (out / "dry_run_prompt.txt").exists()
    assert not (out / "verdicts.jsonl").exists()


def test_cli_real_run_writes_verdicts_and_costlog(tmp_path, monkeypatch):
    _write_model_rows(tmp_path)
    anchors = tmp_path / "pairs.jsonl"
    _write_anchor_pairs(anchors)
    out = tmp_path / "out"

    fake_fns = {"opus": lambda s, u: ('{"choice": "A"}', {"input_tokens": 5, "output_tokens": 1}),  # allow-shorthand
                "sonnet": lambda s, u: ('{"choice": "A"}', None),
                "gpt-5.5": lambda s, u: ('{"choice": "A"}', None)}
    monkeypatch.setattr(J, "default_judge_fns", lambda: fake_fns)

    rc = RJ.main(["--models", *MODELS, "--anchors", str(anchors), "--out", str(out),
                 "--results-dir", str(tmp_path), "--allow-single-family",
                 "--corpus", str(tmp_path / "no_corpus.jsonl"), "--judges", "opus"])  # allow-shorthand
    assert rc == 0
    rows = [json.loads(l) for l in (out / "verdicts.jsonl").read_text().splitlines()]
    n_pairs = 6 * 2 + 2
    assert len(rows) == n_pairs * 2   # both orders, one judge
    cost = json.load(open(out / "costlog.json"))
    assert cost["opus"]["calls"] == n_pairs * 2  # allow-shorthand
    assert cost["opus"]["input_tokens"] == 5 * n_pairs * 2  # allow-shorthand


def test_cli_unknown_judge_returns_1(tmp_path, monkeypatch):
    _write_model_rows(tmp_path)
    anchors = tmp_path / "pairs.jsonl"
    _write_anchor_pairs(anchors)
    monkeypatch.setattr(J, "default_judge_fns", lambda: {"opus": lambda s, u: ("{}", None)})  # allow-shorthand
    rc = RJ.main(["--models", *MODELS, "--anchors", str(anchors), "--out", str(tmp_path / "out"),
                 "--results-dir", str(tmp_path),
                 "--corpus", str(tmp_path / "no_corpus.jsonl"), "--judges", "not-a-judge"])
    assert rc == 1


def test_cli_escalation_returns_1(tmp_path, monkeypatch):
    _write_model_rows(tmp_path)
    anchors = tmp_path / "pairs.jsonl"
    _write_anchor_pairs(anchors)
    out = tmp_path / "out"

    def boom(s, u):
        raise ConnectionError("boom")
    monkeypatch.setattr(J, "default_judge_fns", lambda: {"opus": boom})  # allow-shorthand

    rc = RJ.main(["--models", *MODELS, "--anchors", str(anchors), "--out", str(out),
                 "--results-dir", str(tmp_path), "--allow-single-family",
                 "--corpus", str(tmp_path / "no_corpus.jsonl"), "--judges", "opus",  # allow-shorthand
                 "--retries", "0"])
    assert rc == 1
    assert (out / "costlog.json").exists()   # cost log still written on escalation


def test_cli_single_family_refused_without_flag(tmp_path, monkeypatch):
    _write_model_rows(tmp_path)
    anchors = tmp_path / "pairs.jsonl"
    _write_anchor_pairs(anchors)
    monkeypatch.setattr(J, "default_judge_fns",
                        lambda: {"opus": lambda s, u: ("{}", None), "sonnet": lambda s, u: ("{}", None)})  # allow-shorthand
    rc = RJ.main(["--models", *MODELS, "--anchors", str(anchors), "--out", str(tmp_path / "out"),
                 "--results-dir", str(tmp_path),
                 "--corpus", str(tmp_path / "no_corpus.jsonl"),
                 "--judges", "opus", "sonnet"])   # both anthropic -> single family  # allow-shorthand
    assert rc == 1


def test_cli_single_family_allowed_with_flag(tmp_path, monkeypatch):
    _write_model_rows(tmp_path)
    anchors = tmp_path / "pairs.jsonl"
    _write_anchor_pairs(anchors)
    monkeypatch.setattr(J, "default_judge_fns", lambda: {"opus": lambda s, u: ('{"choice":"A"}', None)})  # allow-shorthand
    rc = RJ.main(["--models", *MODELS, "--anchors", str(anchors), "--out", str(tmp_path / "out"),
                 "--results-dir", str(tmp_path), "--allow-single-family",
                 "--corpus", str(tmp_path / "no_corpus.jsonl"), "--judges", "opus"])  # allow-shorthand
    assert rc == 0


def test_strip_model_names_redacts_family_tokens_with_version_suffix():
    """`qwen3`, `Qwen3-8B`, `OptiQ4` are how checkpoints self-identify; `\\b` alone let them through."""
    from bench.judge_pairwise import FAMILY_TOKENS, strip_model_names
    for tok in FAMILY_TOKENS:
        out = strip_model_names(f"a {tok}3 checkpoint and {tok}3-next at hf.co/{tok}3/repo", [])
        low = out.lower()  # allow-shorthand
        assert tok.lower() not in low and f"{tok.lower()}3" not in low, (tok, out)  # allow-shorthand
