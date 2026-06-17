#!/usr/bin/env python3
"""Needle-in-haystack correctness check at 256K.

Inserts a unique token (NEEDLE_TOKEN) at ~0.7 depth in a 256K-token context,
asks the model to retrieve it, and asserts it appears in the response.
Failure means the context is not being used (not just non-OOM).

Usage:
    uv run python benchmark/needle_256k.py [--model MODEL] [--ctx 256000]
"""
import argparse
import json
import textwrap
import urllib.request

BASE = "http://localhost:8000"
NEEDLE = "XKRYPTO9F2"  # unique enough to not appear naturally in filler text
FILLER_SENTENCE = (
    "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "
)


def post(path, payload, timeout=3600):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def build_context(target_tokens: int, chars_per_token: float) -> tuple[str, int]:
    """Build a ~target_token string with the needle at ~70% depth."""
    target_chars = int(target_tokens * chars_per_token)
    needle_pos = int(target_chars * 0.70)

    needle_sentence = (
        f"The secret code for this session is {NEEDLE}. Remember this code exactly. "
    )
    filler = (FILLER_SENTENCE * (target_chars // len(FILLER_SENTENCE) + 2))

    prefix = filler[:needle_pos]
    suffix_len = target_chars - needle_pos - len(needle_sentence)
    suffix = filler[needle_pos : needle_pos + max(suffix_len, 0)]
    context = prefix + needle_sentence + suffix
    return context, needle_pos


def calibrate_chars_per_token(model: str) -> float:
    r = post(
        "/v1/chat/completions",
        {
            "model": model,
            "messages": [{"role": "user", "content": FILLER_SENTENCE * 200}],
            "max_tokens": 1,
            "temperature": 0.0,
            "stream": False,
        },
        timeout=120,
    )
    chars = len(FILLER_SENTENCE * 200)
    tokens = (r.get("usage") or {}).get("prompt_tokens") or (
        r.get("timings") or {}
    ).get("prompt_n", 1)
    return chars / tokens


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen3.6-27B-UD-MLX-6bit")
    ap.add_argument("--ctx", type=int, default=256000)
    args = ap.parse_args()

    print(f"[needle] model={args.model} target_ctx={args.ctx}")
    print("[needle] calibrating chars/token ...", flush=True)
    cpt = calibrate_chars_per_token(args.model)
    print(f"[needle] {cpt:.2f} chars/token", flush=True)

    context, needle_pos = build_context(args.ctx, cpt)
    needle_depth = needle_pos / len(context)

    question = textwrap.dedent(f"""
        The document above contains a secret code that was mentioned once.
        What is the secret code? Answer with only the code, nothing else.
    """).strip()

    print(
        f"[needle] context_chars={len(context)} needle_depth={needle_depth:.2f} "
        f"needle={NEEDLE}",
        flush=True,
    )
    print("[needle] sending prefill request (may take several minutes) ...", flush=True)

    r = post(
        "/v1/chat/completions",
        {
            "model": args.model,
            "messages": [
                {"role": "user", "content": context + "\n\n" + question}
            ],
            "max_tokens": 32,
            "temperature": 0.0,
            "stream": False,
        },
    )

    tm = r.get("timings") or {}
    response_text = (
        (r.get("choices") or [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    peak = tm.get("peak_memory")
    pt = (r.get("usage") or {}).get("prompt_tokens") or tm.get("prompt_n")

    print(f"[needle] prompt_tokens={pt} peak_mem={peak}GB")
    print(f"[needle] model response: {response_text!r}")

    found = NEEDLE in response_text
    if found:
        print(f"[needle] PASS — needle '{NEEDLE}' found in response")
    else:
        print(f"[needle] FAIL — needle '{NEEDLE}' NOT found in response: {response_text!r}")

    return 0 if found else 1


if __name__ == "__main__":
    raise SystemExit(main())
