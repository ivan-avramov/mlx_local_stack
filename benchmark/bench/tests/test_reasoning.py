"""TDD tests for bench.reasoning — variable-tracking multi-hop probe."""
import re
import bench.reasoning as R


# ---------------------------------------------------------------------------
# build_vartrack tests
# ---------------------------------------------------------------------------

def test_build_vartrack_chain_statements_present():
    """All chain assignment statements appear in the context."""
    context, answer, question = R.build_vartrack(8000, chars_per_token=4.0)
    # answer is a 5-digit integer string
    assert answer.isdigit() and 10000 <= int(answer) <= 99999
    # The raw value must appear in context (the first stmt)
    assert answer in context


def test_build_vartrack_all_var_names_present():
    """Every variable name in the chain is mentioned in the context."""
    context, answer, question = R.build_vartrack(8000, chars_per_token=4.0,
                                                  chain_len=4, seed=42)
    # Extract all VAR...x<i> style names from context
    found = re.findall(r'VAR\d{4}x\d+', context)
    # Should have at least chain_len unique names (could repeat in assignments)
    unique = set(found)
    assert len(unique) >= 4


def test_build_vartrack_statements_ascending_depth():
    """Chain statements are placed at ascending depths (their positions increase)."""
    context, answer, question = R.build_vartrack(16000, chars_per_token=4.0,
                                                  chain_len=4, seed=7)
    # Find all VAR-name occurrences with their positions
    matches = list(re.finditer(r'VAR\d{4}x(\d+)', context))
    assert len(matches) >= 4
    # Collect (index_in_chain, position_in_string)
    indexed = {}
    for m in matches:
        idx = int(m.group(1))
        pos = m.start()
        if idx not in indexed:
            indexed[idx] = pos
    # Positions should be ascending by chain index
    sorted_positions = [indexed[i] for i in sorted(indexed.keys())]
    assert sorted_positions == sorted(sorted_positions)


def test_build_vartrack_answer_is_numeric_string():
    """answer is the stringified integer value of the first assignment."""
    context, answer, question = R.build_vartrack(8000, chars_per_token=4.0, seed=0)
    assert answer.isdigit()
    assert 10000 <= int(answer) <= 99999


def test_build_vartrack_question_mentions_last_var_and_answer_keyword():
    """question names the last variable and contains 'ANSWER:'."""
    context, answer, question = R.build_vartrack(8000, chars_per_token=4.0,
                                                  chain_len=4, seed=1)
    # The last var name is VAR<digits>x3 (chain_len-1 = 3)
    last_var_pat = re.compile(r'VAR\d{4}x3')
    assert last_var_pat.search(question), f"last var not in question: {question}"
    assert "ANSWER:" in question


def test_build_vartrack_deterministic():
    """Same seed always returns same context."""
    r1 = R.build_vartrack(8000, chars_per_token=4.0, seed=99)
    r2 = R.build_vartrack(8000, chars_per_token=4.0, seed=99)
    assert r1 == r2


def test_build_vartrack_different_seeds_differ():
    """Different seeds produce different contexts (high probability)."""
    c1, a1, _ = R.build_vartrack(8000, chars_per_token=4.0, seed=0)
    c2, a2, _ = R.build_vartrack(8000, chars_per_token=4.0, seed=1)
    # Either the val or the var names differ
    assert (a1 != a2) or (c1 != c2)


# ---------------------------------------------------------------------------
# score_vartrack tests
# ---------------------------------------------------------------------------

def test_score_answer_after_answer_keyword():
    assert R.score_vartrack("blah blah ANSWER: 12345", "12345") == 1.0


def test_score_answer_in_body_no_keyword():
    """Answer present in response body even without keyword."""
    assert R.score_vartrack("The value is 12345 I think", "12345") == 1.0


def test_score_wrong_answer():
    assert R.score_vartrack("ANSWER: 99999", "12345") == 0.0


def test_score_absent_answer():
    assert R.score_vartrack("I have no idea", "12345") == 0.0


def test_score_partial_match_not_counted():
    """A number that contains the answer as a substring should NOT score
    (e.g. '123456' != '12345')."""
    # 123456 is NOT 12345 — substring in a longer number should not match
    # Our regex finds 4+ digit numbers, so 123456 and 12345 are distinct numbers
    assert R.score_vartrack("ANSWER: 123456", "12345") == 0.0


def test_score_answer_keyword_takes_priority():
    """When ANSWER: is present, it controls — body number doesn't override wrong ANSWER."""
    assert R.score_vartrack("12345 ANSWER: 99999", "12345") == 0.0


# ---------------------------------------------------------------------------
# run_reasoning_ladder tests
# ---------------------------------------------------------------------------

class FakeSampler:
    def __init__(self, pid=None, interval=0.2):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    system_peak_gb = 30.0
    peak_rss_gb = 20.0


class ScriptedDriver:
    """Returns a scripted sequence of contents (rotating)."""

    def __init__(self, contents_by_ctx):
        # contents_by_ctx: dict[int, list[str]] or list of strings (all ctx)
        self._map = contents_by_ctx
        self._calls = {}

    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        # Determine ctx from the message length (we can't easily, so just use a call counter)
        # We'll use the model name as ctx key
        ctx_key = model  # caller passes ctx as model for test
        idx = self._calls.get(ctx_key, 0)
        self._calls[ctx_key] = idx + 1
        contents = self._map[ctx_key]
        content = contents[idx % len(contents)]
        return {
            "content": content,
            "prompt_tokens": 100,
            "prefill_s": 0.5,
            "prefill_tps": 200,
            "decode_tps": 50.0,
            "peak_mem_gb": 20.0,
            "wall_s": 1.0,
        }


class AllCorrectDriver:
    """Always returns ANSWER: <val> — but we don't know val per trial."""

    def __init__(self):
        self._last_val = None

    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        # Extract the val from the message context (last user message)
        user_content = messages[-1]["content"] if messages else ""
        # The context contains VAR...=<val> — find the first large number
        m = re.search(r'= (\d{5})\.', user_content)
        val = m.group(1) if m else "99999"
        return {
            "content": f"ANSWER: {val}",
            "prompt_tokens": 100,
            "prefill_s": 0.5,
            "prefill_tps": 200,
            "decode_tps": 50.0,
            "peak_mem_gb": 20.0,
            "wall_s": 1.0,
        }


class NeverCorrectDriver:
    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        return {
            "content": "I don't know.",
            "prompt_tokens": 100,
            "prefill_s": 0.5,
            "prefill_tps": 200,
            "decode_tps": 50.0,
            "peak_mem_gb": 20.0,
            "wall_s": 1.0,
        }


class ExplodingDriver:
    """Raises an exception on every complete() call."""

    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        raise RuntimeError("server exploded")


_PROD_PARAMS = {"max_tokens": 256, "temperature": 0.0, "thinking_budget": 128,
                "top_p": 0.95, "top_k": 20, "enable_thinking": True}


def test_ladder_stops_at_cliff():
    """Ladder stops after the first rung below threshold."""
    # Use AllCorrectDriver for all but last rung
    # Build a grid with 3 rungs; use NeverCorrectDriver for the 2nd rung onwards
    # We want: rung0=pass, rung1=fail → stop, rung2 never run
    grid = (8000, 16000, 24000)
    threshold = 0.85
    samples = 3

    call_count = [0]

    class CliffDriver:
        def preload(self, model, timeout=900):
            return 1.0

        def complete(self, model, messages, params, timeout=3600):
            call_count[0] += 1
            user_content = messages[-1]["content"] if messages else ""
            m = re.search(r'= (\d{5})\.', user_content)
            val = m.group(1) if m else "99999"
            # First `samples` calls (rung 8000) succeed; rest fail
            if call_count[0] <= samples:
                content = f"ANSWER: {val}"
            else:
                content = "I don't know"
            return {
                "content": content,
                "prompt_tokens": 100,
                "prefill_s": 0.5,
                "prefill_tps": 200,
                "decode_tps": 50.0,
                "peak_mem_gb": 20.0,
                "wall_s": 1.0,
            }

    driver = CliffDriver()
    records = R.run_reasoning_ladder(
        driver, "model", chars_per_token=4.0, model_pid=99999,
        params=_PROD_PARAMS,
        grid=grid, threshold=threshold, samples=samples, chain_len=4,
        sampler_factory=FakeSampler,
    )
    # Should have rung0 (pass) and rung1 (fail), stop before rung2
    assert len(records) == 2, f"Expected 2 rungs, got {len(records)}: {records}"
    assert records[0]["accuracy"] >= threshold
    assert records[1]["accuracy"] < threshold


def test_ladder_all_pass_runs_full_grid():
    """When every rung passes, all rungs are returned."""
    grid = (8000, 16000)
    driver = AllCorrectDriver()
    records = R.run_reasoning_ladder(
        driver, "model", chars_per_token=4.0, model_pid=99999,
        params=_PROD_PARAMS,
        grid=grid, threshold=0.85, samples=2, chain_len=4,
        sampler_factory=FakeSampler,
    )
    assert len(records) == 2
    for r in records:
        assert r["accuracy"] == 1.0


def test_ladder_exception_scores_zero():
    """An exception in complete() scores 0.0 for that trial."""
    grid = (8000,)
    driver = ExplodingDriver()
    records = R.run_reasoning_ladder(
        driver, "model", chars_per_token=4.0, model_pid=99999,
        params=_PROD_PARAMS,
        grid=grid, threshold=0.85, samples=3, chain_len=4,
        sampler_factory=FakeSampler,
    )
    assert len(records) == 1
    assert records[0]["accuracy"] == 0.0
    assert records[0]["errors"] == 3


def test_ladder_record_fields():
    """Each record has the required fields."""
    grid = (8000,)
    driver = AllCorrectDriver()
    records = R.run_reasoning_ladder(
        driver, "model", chars_per_token=4.0, model_pid=99999,
        params=_PROD_PARAMS,
        grid=grid, threshold=0.85, samples=2, chain_len=4,
        sampler_factory=FakeSampler,
    )
    r = records[0]
    assert "ctx" in r
    assert "accuracy" in r
    assert "samples" in r
    assert "chain_len" in r
    assert "errors" in r
    assert r["samples"] == 2
    assert r["chain_len"] == 4


def test_ladder_params_forwarded_to_driver():
    """params dict is forwarded verbatim to driver.complete (not hardcoded)."""
    received = []

    class RecordParamsDriver:
        def complete(self, model, messages, params, timeout=3600):
            received.append(dict(params))
            user_content = messages[-1]["content"] if messages else ""
            m = re.search(r'= (\d{5})\.', user_content)
            val = m.group(1) if m else "99999"
            return {"content": f"ANSWER: {val}", "prompt_tokens": 100,
                    "prefill_s": 0.5, "prefill_tps": 200, "decode_tps": 50.0,
                    "peak_mem_gb": 20.0, "wall_s": 1.0}

    custom_params = {"max_tokens": 512, "temperature": 0.7, "thinking_budget": 999,
                     "top_p": 0.95, "enable_thinking": True}
    R.run_reasoning_ladder(
        RecordParamsDriver(), "model", chars_per_token=4.0, model_pid=99999,
        params=custom_params, grid=(8000,), threshold=0.85, samples=1, chain_len=4,
        sampler_factory=FakeSampler,
    )
    assert len(received) == 1
    # temperature must pass through (not overridden to 0.0)
    assert received[0]["temperature"] == 0.7
    assert received[0]["max_tokens"] == 512
    assert received[0]["thinking_budget"] == 999
