"""The coding-at-depth axis (D9, operator-requested 2026-08-18).

Why this exists: every coding instrument in the harness runs at its native short prompt, so
NO model has ever demonstrated coding quality at depth — goal B's context requirement was
satisfied by assumption. This axis embeds the SAME execution-gated items at the end of N
tokens of deterministic repo-like context, so shallow-vs-depth is a within-model PAIRED
comparison and the docker grader needs no changes.

Design rules pinned here:
  * padding is DETERMINISTIC per (item, target) — paired across models and reproducible
    across resumes (common-random-numbers, same reason draws carry explicit seeds);
  * the original task text survives VERBATIM at the end — any quality delta is attributable
    to depth, not to a mangled prompt;
  * depth is PROVENANCE: `depth_tokens` joins the fingerprint's sampling slice and compare's
    must-match guard, because two runs at different depths answered different questions.
"""
import bench.depth as D


def test_padding_is_deterministic_per_item_and_size():
    a = D.padding(8000, "HumanEval/0")
    b = D.padding(8000, "HumanEval/0")
    assert a == b, "same (item, target) must be byte-identical: paired design + resumability"


def test_padding_differs_across_items_and_sizes():
    assert D.padding(8000, "HumanEval/0") != D.padding(8000, "HumanEval/1")
    assert len(D.padding(16000, "HumanEval/0")) > len(D.padding(8000, "HumanEval/0"))


def test_padding_hits_the_token_target_approximately():
    """Exact token counts are tokenizer-specific; the row's measured prompt_tokens is the
    authoritative depth. The builder just has to land in the right neighbourhood."""
    text = D.padding(20000, "HumanEval/0")
    est = len(text) / D.CHARS_PER_TOKEN
    assert 0.8 * 20000 <= est <= 1.2 * 20000, f"estimated {est:.0f} tokens for a 20K target"


def test_padding_looks_like_python_source_not_prose():
    text = D.padding(4000, "HumanEval/0")
    assert text.count("def ") > 5
    assert "return" in text


def test_wrap_preserves_the_original_task_verbatim_at_the_end():
    msgs = [{"role": "user", "content": "Complete the following task.\n\ndef f(): ..."}]
    wrapped = D.wrap_messages(msgs, 4000, "HumanEval/0")
    assert len(wrapped) == 1 and wrapped[0]["role"] == "user"
    body = wrapped[0]["content"]
    assert body.endswith("Complete the following task.\n\ndef f(): ...")
    assert len(body) > len(msgs[0]["content"]) + 1000
    # the framing must tell the model the repo context is background, not the task
    assert "context" in body.lower()


def test_wrap_with_zero_or_none_depth_is_identity():
    msgs = [{"role": "user", "content": "task"}]
    assert D.wrap_messages(msgs, 0, "x") == msgs
    assert D.wrap_messages(msgs, None, "x") == msgs


def test_depth_tokens_is_fingerprinted_and_guarded():
    """The parity invariant extended: a knob that changes WHAT WE ASKED must be in the
    fingerprint AND in compare's must-match tier — the suffix lesson, applied before the
    axis ever runs instead of after."""
    import bench.provenance as P
    import bench.compare as CMP
    assert "depth_tokens" in P._FINGERPRINT_SAMPLING
    assert "depth_tokens" in CMP._MUST_MATCH_SAMPLING
