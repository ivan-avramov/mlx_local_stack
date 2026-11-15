"""S24-P17 / C349: a `/home/<name>/` path inside MODEL OUTPUT harvested by the benchmark (result rows) is model-written fiction on these macOS boxes (a real home path is `/Users/<name>/`), so only the `/home/` pattern is
suppressed there, on anchored path forms; every other pattern still fires in those files, and `/home/` still fires everywhere else.
Class (a): reproduces the Wave 1 stop (`cjudge-m76-x-smoke`); the boundary cases come from the cold read (Sol, GLM)."""
from __future__ import annotations

import pytest

from bench import piicheck

NAME = "dev"                                            # not a placeholder user
HOME = "/home/" + NAME + "/project/main.py"            # split so this file's own text is not a literal match
W2_STEM = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed.s1.opencode_go.L1.full.a1.jsonl"

MODEL_OUTPUT = [
    "benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/cjudge.m76-x-smoke.jsonl",  # Wave 1 row (published)
    "benchmark/results/judge_c_v1/verdicts.jsonl",                                               # judge rows (depth 2)
    f"benchmark/results/m76/wave2/tg1-m76-x-s1.a1/s1/{W2_STEM}",                                 # Wave 2 row (published)
    f"benchmark/results/p426/wave2.v8-4104c7fc/tg1-p426-off-s1.a1/s1/{W2_STEM}",
    f"leg:s1/{W2_STEM}",                                                                          # Wave 2 row (harvest source)
    "leg:pilot/" + W2_STEM.replace(".s1.", ".pilot."),
]
NOT_MODEL_OUTPUT = [
    "docs/open-questions.md",
    "benchmark/bench/p426_harvest.py",
    "README.md",
    "benchmark/results/m76/ids.json",
    "benchmark/results/some-model/not_agentbench.md",
    "benchmark/results/m76/wave2/tg1-m76-x-s1.a1/watch.jsonl",                 # attempt-level journal, not a row
    "benchmark/results/m76/wave1/math500-m76-x-b1/receipts.jsonl",             # deeper non-row jsonl
    "leg:watch.jsonl",
    "leg:s1/notes.jsonl",                                                      # session dir, not a row stem
    "docs/not_opencode_transcripts/receipt.txt",                               # near-name directories
    "Xopencode_transcripts/foo.txt",
    "scripts/final_tree/notes.md",
    "docs/opencode_transcripts/README.md",                                     # exact-name dirs: not exempt (verify r2)
    "docs/example.final_tree/notes.md",
    "evidence:run-1/opencode_transcripts/model/run.abc/events.jsonl",           # evidence: other gates, never exempt here
    "evidence/run-1/go__counter.final_tree/objects/0123abcd",
]
OTHER_PATTERNS = {
    "/Users/" + NAME + "/x": "absolute home path with a username",
    "x-home-" + NAME + "-y": "dash-flattened absolute home path with a username",
    "x-Users-" + NAME + "-y": "dash-flattened absolute home path with a username",
    "hf_" + "A" * 24: "Hugging Face token",
    "sk-" + "B" * 24: "API key",
    "ghp_" + "C" * 24: "GitHub token",
    "AKIA" + "D" * 16: "AWS access key id",
    "buildbox" + ".local": "mDNS hostname",
}


def _why(text, path):
    return [v.why for v in piicheck.violations(text, path=path, line=1)]


@pytest.mark.parametrize("path", MODEL_OUTPUT)
def test_home_path_in_model_output_is_not_a_violation(path):
    assert _why(f'{{"content": "cd {HOME}"}}', path) == []


@pytest.mark.parametrize("path", MODEL_OUTPUT)
@pytest.mark.parametrize("text,why", sorted(OTHER_PATTERNS.items()))
def test_every_other_pattern_still_fires_in_model_output(path, text, why):
    assert why in _why(f'{{"content": "{text}"}}', path)


@pytest.mark.parametrize("path", NOT_MODEL_OUTPUT)
def test_home_path_elsewhere_still_fires(path):
    assert "absolute home path with a username (/home/)" in _why(f"see {HOME}", path)


@pytest.mark.parametrize("path", [MODEL_OUTPUT[0], NOT_MODEL_OUTPUT[0]])
def test_placeholder_user_is_silent_both_ways(path):
    assert _why("see /home/" + "remoteuser" + "/x", path) == []


def test_agentbench_guest_os_exemption_unchanged():
    assert _why(f"{HOME}", "benchmark/results/x/agentbench_os_v1.jsonl") == []


def test_commit_diff_path_uses_the_same_rule():
    added = f'+{{"content": "cd {HOME}"}}'
    row = MODEL_OUTPUT[0]
    diff = f"diff --git a/{row} b/{row}\n--- a/{row}\n+++ b/{row}\n@@ -0,0 +1 @@\n{added}\n"
    assert piicheck.diff_violations(diff) == []
    doc = "docs/open-questions.md"
    diff_doc = diff.replace(row, doc)
    assert piicheck.diff_violations(diff_doc)
