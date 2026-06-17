#!/usr/bin/env python3
"""One-off calibration: measure natural output length + wall time per item type on a
dense vs MoE model, so we can size the screen to a time budget. Correctness irrelevant
here — we only want token counts and timing. Pure HTTP to mlx-serve :8000."""
import json, time, urllib.request

BASE = "http://localhost:8000"

ITEMS = {
    "math_aime": "Let N be the greatest four-digit positive integer such that whenever one "
        "of its digits is changed to 1, the resulting number is divisible by 7. Let Q and R "
        "be the quotient and remainder when N is divided by 1000. Find Q+R. "
        "Reason step by step and give the final integer answer in \\boxed{}.",
    "gpqa_sci": "A quantum harmonic oscillator of mass m and angular frequency w is in a state "
        "that is an equal-weight superposition of the ground state and the third excited state. "
        "What is the expectation value of the energy? "
        "(A) 2*hbar*w  (B) 3.5*hbar*w  (C) 2*hbar*w exactly  (D) (1/2+3/2)*hbar*w. "
        "Reason carefully, then answer with the single letter in \\boxed{}.",
    "code_lcb": "Write a Python function `longest_good(nums: list[int], k: int) -> int` that "
        "returns the length of the longest contiguous subarray whose maximum minus minimum is "
        "at most k. Provide only the function in a python code block. Reason about edge cases first.",
}

MODELS = ["gemma-4-31b-it-UD-MLX-4bit", "gemma-4-26B-A4B-it-QAT-MLX-4bit"]  # dense winner, MoE winner


def post(path, payload, timeout=1800):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


for model in MODELS:
    print(f"\n=== {model} ===", flush=True)
    post("/v1/models/load", {"model": model, "keep_alive": "60m"}, timeout=600)
    for name, prompt in ITEMS.items():
        t0 = time.perf_counter()
        r = post("/v1/chat/completions", {
            "model": model, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 8192, "temperature": 0.0, "stream": False})
        wall = time.perf_counter() - t0
        tm = r.get("timings") or {}
        us = r.get("usage") or {}
        msg = (r.get("choices") or [{}])[0].get("message", {})
        reasoning_chars = len(msg.get("reasoning") or "")
        content_chars = len(msg.get("content") or "")
        print(f"  {name:<10} | completion_tok={us.get('completion_tokens')} | "
              f"decode={tm.get('predicted_per_second'):.1f} tok/s | wall={wall:.0f}s | "
              f"reasoning_chars={reasoning_chars} content_chars={content_chars}", flush=True)
print("\n[calibrate] done", flush=True)
