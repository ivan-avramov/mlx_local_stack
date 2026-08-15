"""The aider->corpus bridge.

Builds a synthetic tree mirroring the REAL m1f layout — one run dir PER LANGUAGE, named
`<timestamp>--m1f-<arm>-<lang>` — rather than reusing the checked-in fixture, which is a single run
dir containing several languages. Testing against the shape production actually reads is the point.
"""
import json
import os

import bench.aider_rows as AR


def _case(passed, *, duration=10.0, ctok=1000, exhausted=0, malformed=0):
    return {
        "testcase": None,  # filled by _mk
        "model": "openai/M",
        "edit_format": "diff",
        "tests_outcomes": [False, True] if passed else [False, False],
        "duration": duration,
        "completion_tokens": ctok,
        "prompt_tokens": 500,
        "num_exhausted_context_windows": exhausted,
        "num_malformed_responses": malformed,
        "test_timeouts": 0,
    }


def _mk(root, arm, lang, exercises):
    """exercises: {name: case_dict}"""
    base = os.path.join(root, f"2026-08-12-00-00-00--m1f-{arm}-{lang}", lang,
                        "exercises", "practice")
    for name, c in exercises.items():
        d = os.path.join(base, name)
        os.makedirs(d, exist_ok=True)
        c = dict(c, testcase=name)
        with open(os.path.join(d, ".aider.results.json"), "w") as fh:
            json.dump(c, fh)


def _tree(tmp_path):
    root = str(tmp_path / "tmp.benchmarks")
    _mk(root, "ornith", "python", {"anagram": _case(True), "bowling": _case(False)})
    _mk(root, "ornith", "go", {"two-fer": _case(True, exhausted=1)})   # passed but exhausted
    # a LATER partial run for the same arm+lang; must never pool into m1f
    other = os.path.join(root, "2026-08-13-00-00-00--m1g-ornith-python", "python",
                         "exercises", "practice", "zzz")
    os.makedirs(other, exist_ok=True)
    with open(os.path.join(other, ".aider.results.json"), "w") as fh:
        json.dump(dict(_case(True), testcase="zzz"), fh)
    return root


def test_keys_are_lang_scoped_so_arms_pair_item_by_item(tmp_path):
    root = _tree(tmp_path)
    cases = AR.collect_arm_cases(root, "ornith", langs=("python", "go"))
    assert set(cases) == {"python/anagram", "python/bowling", "go/two-fer"}


def test_a_later_run_of_the_same_arm_does_NOT_pool_into_m1f(tmp_path):
    """Pooling two runs of one model is the apples-to-apples violation the run_name guard exists
    for; `m1g-ornith-python` sits in the same benchmark dir and must be excluded."""
    root = _tree(tmp_path)
    cases = AR.collect_arm_cases(root, "ornith", langs=("python",))
    assert "python/zzz" not in cases
    assert set(cases) == {"python/anagram", "python/bowling"}


def test_never_writes_the_canonical_completion_tokens_field(tmp_path):
    """aider's completion_tokens is a per-case SUM across turns. Writing it into the canonical field
    would feed a sum to a per-turn budget comparison — which already produced one wrong claim
    ("max completion 62,083 against an 81,920 budget"; the real per-turn max was 148,908)."""
    rows, _ = AR.build(_tree(tmp_path), "ornith", "M", langs=("python", "go"))
    assert rows
    for r in rows:
        assert "completion_tokens" not in r and "prompt_tokens" not in r
        assert r["completion_tokens_sum"] == 1000


def test_converged_is_null_rather_than_a_fabricated_100pct(tmp_path):
    rows, _ = AR.build(_tree(tmp_path), "ornith", "M", langs=("python", "go"))
    assert all(r["converged"] is None for r in rows)


def test_acc_is_last_attempt_pass_and_strict_zeroes_context_exhaustion(tmp_path):
    rows, score = AR.build(_tree(tmp_path), "ornith", "M", langs=("python", "go"))
    assert score["n"] == 3
    assert score["acc"] == 2 / 3           # anagram + two-fer passed, bowling failed
    assert score["acc_strict"] == 1 / 3    # two-fer exhausted context => zeroed
    assert score["n_context_exhausted"] == 1


def test_write_arm_emits_the_three_files_the_scoreboard_reads(tmp_path):
    root = _tree(tmp_path)
    out = tmp_path / "results"
    man = {"box": "worker", "max_kv_cache_size": 65536,
           "note": "M1 ran at 65536 => resolved thinking budget ~52,390, NOT the declared 81,920"}
    score = AR.write_arm(out, "ornith", "M", root, manifest=man, langs=("python", "go"))
    d = out / "M"
    assert (d / "aider.jsonl").exists()
    assert (d / "aider.score.json").exists()
    assert json.loads((d / "aider.manifest.json").read_text())["max_kv_cache_size"] == 65536
    lines = (d / "aider.jsonl").read_text().splitlines()
    assert len(lines) == 3
    first = json.loads(lines[0])
    assert first["bench"] == "aider" and first["model"] == "M"
    assert score["acc"] == 2 / 3
