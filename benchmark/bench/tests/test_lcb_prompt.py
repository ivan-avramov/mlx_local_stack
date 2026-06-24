"""build_messages must emit the OFFICIAL LiveCodeBench code-generation prompt for the
`livecodebench` benchmark (lcb_runner/prompts/code_generation.py: SYSTEM_MESSAGE_GENERIC +
get_generic_question_template_answer). This is how Qwen3.6 was officially evaluated; the
thinking-mode template drops the "return only the program" restriction. The expected
strings below are transcribed from the canonical lcb_runner source (the external contract),
NOT from our implementation.
"""
import bench.benchmarks as B

# Canonical constants — copied verbatim from lcb_runner/prompts/code_generation.py.
SYS = ("You are an expert Python programmer. You will be given a question (problem "
       "specification) and will generate a correct Python program that matches the "
       "specification and passes all tests.")
FMT_WITH_STARTER = ("You will use the following starter code to write the solution to the "
                    "problem and enclose your code within delimiters.")
FMT_STDIN = ("Read the inputs from stdin solve the problem and write the answer to stdout "
             "(do not directly test on the sample inputs). Enclose your code within "
             "delimiters as follows. Ensure that when the python program runs, it reads the "
             "inputs, runs the algorithm and writes output to STDOUT.")


def _expected_user_body(question, starter):
    body = f"### Question:\n{question}\n\n"
    if starter:
        body += f"### Format: {FMT_WITH_STARTER}\n```python\n{starter}\n```\n\n"
    else:
        body += f"### Format: {FMT_STDIN}\n```python\n# YOUR CODE HERE\n```\n\n"
    body += "### Answer: (use the provided format with backticks)\n\n"
    return body


def test_lcb_functional_starter_code_uses_official_template():
    # LeetCode-style functional problem (has starter code).
    item = {"id": "3496", "prompt": "ignored-when-meta-present",
            "meta": {"platform": "leetcode", "question_content": "Sort the array.",
                     "starter_code": "class Solution:\n    def f(self, a):"}}
    msgs = B.build_messages("livecodebench", item)
    assert msgs == [
        {"role": "system", "content": SYS},
        {"role": "user", "content": _expected_user_body("Sort the array.",
                                                         "class Solution:\n    def f(self, a):")},
    ]


def test_lcb_stdin_problem_uses_official_stdin_framing():
    # AtCoder/Codeforces-style stdin problem (no starter code).
    item = {"id": "abc358_e", "prompt": "ignored",
            "meta": {"platform": "atcoder", "question_content": "Read N then sum.",
                     "starter_code": ""}}
    msgs = B.build_messages("livecodebench", item)
    assert msgs[0] == {"role": "system", "content": SYS}
    assert msgs[1]["content"] == _expected_user_body("Read N then sum.", "")
    # Explicit stdin framing present; restrictive "no explanation" wording gone.
    assert "stdin" in msgs[1]["content"] and "STDOUT" in msgs[1]["content"]
    assert "no explanation" not in msgs[1]["content"].lower()


def test_lcb_falls_back_to_prompt_when_meta_absent():
    # Robustness: an item without meta (e.g. a hand-built smoke item) still builds, using
    # item["prompt"] as the question and treating it as a stdin problem.
    item = {"id": "x", "prompt": "Do the thing."}
    msgs = B.build_messages("livecodebench", item)
    assert msgs[0]["content"] == SYS
    assert msgs[1]["content"] == _expected_user_body("Do the thing.", "")


def test_evalplus_prompt_unchanged():
    # Only LCB adopts the official template; evalplus benchmarks keep the simple prompt.
    item = {"id": "HumanEval/0", "prompt": "def f():"}
    msgs = B.build_messages("humanevalplus", item)
    assert len(msgs) == 1 and msgs[0]["role"] == "user"
    assert "no explanation after it" in msgs[0]["content"]
