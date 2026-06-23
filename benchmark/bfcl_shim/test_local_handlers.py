"""Tests for the BFCL local-handler thinking-strip (template-fidelity fix).

Our served gemma-4 / Qwen3.6 emit a thinking preamble before the function-call list
(gemma: ``<|channel>thought\\n<channel|>[...]``; qwen: ``<think>...</think>\\n[...]``).
bfcl's default_decode_ast_prompting wraps the whole string in ``[...]`` and ast-parses
it, so the preamble makes it a SyntaxError -> acc=0 despite a correct call. The strip
removes the preamble, keeping the trailing function-call list.

Run:
  PYTHONPATH=benchmark/bfcl_shim <venv>/bin/python benchmark/bfcl_shim/test_local_handlers.py
"""
from local_handlers import strip_thinking


def test_strip_gemma_channel_preamble():
    raw = "<|channel>thought\n<channel|>[calculate_triangle_area(base=10, height=5, unit='units')]"
    assert strip_thinking(raw) == "[calculate_triangle_area(base=10, height=5, unit='units')]"


def test_strip_qwen_think_tags():
    raw = "<think>\nThe user wants a factorial.\n</think>\n[math.factorial(number=5)]"
    assert strip_thinking(raw) == "[math.factorial(number=5)]"


def test_strip_passthrough_when_no_markup():
    raw = "[math.hypot(x=4, y=5)]"
    assert strip_thinking(raw) == "[math.hypot(x=4, y=5)]"


def test_strip_takes_last_channel_segment():
    # multiple channels -> keep the final (answer) segment
    raw = "<|channel>analysis\n<channel|>thinking\n<|channel>final\n<channel|>[f(a=1)]"
    assert strip_thinking(raw) == "[f(a=1)]"


def test_strip_handles_both_markers():
    raw = "<|channel>thought\n<channel|><think>more</think>[g(b=2)]"
    assert strip_thinking(raw) == "[g(b=2)]"


def test_strip_preserves_brackets_in_args():
    # a function arg containing a list must not be truncated
    raw = "<channel|>[sort(items=[3, 1, 2])]"
    assert strip_thinking(raw) == "[sort(items=[3, 1, 2])]"


def test_fc_extract_normalizes_parameters_to_arguments():
    # Qwen3.6 sometimes emits "parameters" instead of "arguments" -> normalize so decode_ast works.
    from local_handlers import QwenFCEpiHandler
    s = '<tool_call>\n{"name": "algebra.quadratic_roots", "parameters": {"a": 1, "b": -3, "c": 2}}\n</tool_call>'
    assert QwenFCEpiHandler._extract_tool_calls(s) == [
        {"name": "algebra.quadratic_roots", "arguments": {"a": 1, "b": -3, "c": 2}}
    ], QwenFCEpiHandler._extract_tool_calls(s)


def test_fc_extract_keeps_arguments_and_multi_call():
    from local_handlers import QwenFCEpiHandler
    s = ('<tool_call>\n{"name": "f", "arguments": {"b": 2}}\n</tool_call>\n'
         '<tool_call>\n{"name": "g", "parameters": {"c": 3}}\n</tool_call>')
    assert QwenFCEpiHandler._extract_tool_calls(s) == [
        {"name": "f", "arguments": {"b": 2}},
        {"name": "g", "arguments": {"c": 3}},
    ], QwenFCEpiHandler._extract_tool_calls(s)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\nALL {len(tests)} strip_thinking tests PASS")
