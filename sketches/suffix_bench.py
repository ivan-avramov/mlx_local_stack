"""One-off benchmark for drafter-free suffix decoding.

Loads a dense gemma4 once and runs, greedily (temperature=0), with and without
suffix decoding on (a) a coding-echo prompt and (b) a novel-prose prompt.
Reports decode tok/s, acceptance stats, and — crucially — that the greedy text
is byte-identical with and without suffix decoding (the correctness gate, on the
real model + full generate path).

Run:
  uv run --project <root> python sketches/suffix_bench.py [model_id]
"""

import sys
import time

from mlx_vlm import load
from mlx_vlm.generate.dispatch import stream_generate
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.speculative.common import _format_speculative_stats
from mlx_vlm.speculative.suffix_decoding import SuffixDecodingProposer

MODEL = sys.argv[1] if len(sys.argv) > 1 else "mlx-community/gemma-4-31b-it-4bit"
MAX_TOKENS = 200

CODE_BLOCK = '''def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def factorial(n):
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def is_prime(n):
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True
'''

ECHO_PROMPT = (
    "Reproduce the following Python module EXACTLY as-is, character for "
    "character, inside a single ```python code block. Do not change, add, or "
    "remove anything.\n\n```python\n" + CODE_BLOCK + "```"
)

PROSE_PROMPT = (
    "Write an original 180-word short story about a lighthouse keeper who finds "
    "a message in a bottle. Do not repeat yourself; use fresh vocabulary."
)


def run(model, processor, prompt_text, *, use_suffix):
    config = model.config
    prompt = apply_chat_template(
        processor, config, prompt_text, num_images=0, num_audios=0,
        enable_thinking=False,
    )
    kwargs = dict(max_tokens=MAX_TOKENS, temperature=0.0, verbose=False)
    proposer = None
    if use_suffix:
        proposer = SuffixDecodingProposer(min_match=2, max_draft=16)
        kwargs["draft_model"] = proposer
        kwargs["draft_kind"] = "suffix"

    text = ""
    last = None
    t0 = time.perf_counter()
    for chunk in stream_generate(model, processor, prompt, **kwargs):
        if getattr(chunk, "is_draft", False):
            continue
        text += chunk.text
        last = chunk
    wall = time.perf_counter() - t0

    stats = _format_speculative_stats(proposer) if proposer is not None else None
    return {
        "text": text,
        "gen_tokens": getattr(last, "generation_tokens", 0),
        "gen_tps": getattr(last, "generation_tps", 0.0),
        "prompt_tps": getattr(last, "prompt_tps", 0.0),
        "wall": wall,
        "stats": stats,
    }


def report(name, base, spec):
    print(f"\n===== {name} =====")
    same = base["text"] == spec["text"]
    print(f"greedy text identical (base vs suffix): {same}")
    if not same:
        print("  !! DIVERGED — equivalence gate violated")
    print(
        f"baseline: {base['gen_tokens']} tok @ {base['gen_tps']:.1f} tok/s "
        f"(decode), wall {base['wall']:.1f}s"
    )
    print(
        f"suffix:   {spec['gen_tokens']} tok @ {spec['gen_tps']:.1f} tok/s "
        f"(decode), wall {spec['wall']:.1f}s"
    )
    if base["gen_tps"] and spec["gen_tps"]:
        print(f"decode speedup: {spec['gen_tps'] / base['gen_tps']:.2f}x")
    print(f"acceptance: {spec['stats']}")


def main():
    print(f"loading {MODEL} ...")
    model, processor = load(MODEL)
    # Warm up (kernels / autotune) so the first timed run isn't penalised.
    run(model, processor, "Say hi.", use_suffix=False)

    for name, prompt in [("CODING-ECHO", ECHO_PROMPT), ("NOVEL-PROSE", PROSE_PROMPT)]:
        base = run(model, processor, prompt, use_suffix=False)
        spec = run(model, processor, prompt, use_suffix=True)
        report(name, base, spec)


if __name__ == "__main__":
    main()
