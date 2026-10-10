"""M58 G1a straddle requests: prompts sized so the 256-token decode crosses the MLX key-length thresholds
(T ∈ {1024, 8192, 32768, 65536}; prompt ≈ T − 64 tokens). Under `joint_v1+ab` the response timings must show
`verify_ab_straddle_blocks > 0`, `verify_ab_straddle_mismatch > 0` (the live known positive), `verify_ab_mismatch == 0`,
`verify_ab_invalid == 0`. Thinking off (the gate is about verification blocks, not the answer). Writes one JSON.
  python straddle_probe.py --cpt 4.611 --out <json> [--base http://127.0.0.1:8000/v1]"""
import argparse, json, time, urllib.request

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
WORDS = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon".split()


def filler(n_tokens, cpt):
    import random
    rng = random.Random(n_tokens)
    out, n = [], 0
    target = int(n_tokens * cpt)
    while n < target:
        w = rng.choice(WORDS); out.append(w); n += len(w) + 1
    return " ".join(out)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cpt", type=float, required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--base", default="http://127.0.0.1:8000/v1"); ap.add_argument("--thresholds", default="1024,8192,32768,65536")
    ap.add_argument("--max-tokens", type=int, default=300)
    a = ap.parse_args()
    rows = []
    for T in [int(x) for x in a.thresholds.split(",")]:
        target = T - 64
        body = {"model": MODEL, "max_tokens": a.max_tokens, "temperature": 0.5, "seed": 7, "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
                "messages": [{"role": "user", "content": "Filler follows; after it, write a 300-word story about a lighthouse.\n\n" + filler(target - 40, a.cpt) + "\n\nNow the story:"}]}
        t0 = time.time()
        req = urllib.request.Request(a.base + "/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3600) as resp:
            r = json.load(resp)
        t = r.get("timings") or {}; u = r.get("usage") or {}
        row = {"T": T, "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
               "crossed": (u.get("prompt_tokens") or 0) < T <= (u.get("prompt_tokens") or 0) + (u.get("completion_tokens") or 0),
               "wall_s": round(time.time() - t0, 1), "finish_reason": r["choices"][0].get("finish_reason"),
               "counters": {k: v for k, v in t.items() if k.startswith(("verify", "draft", "sdpa"))}}
        rows.append(row); print(json.dumps(row), flush=True)
    verdict = all(r["crossed"] for r in rows) and all(
        (r["counters"].get("verify_ab_straddle_blocks", 0) > 0 and r["counters"].get("verify_ab_straddle_mismatch", 0) > 0
         and r["counters"].get("verify_ab_mismatch", 1) == 0 and r["counters"].get("verify_ab_invalid", 1) == 0) for r in rows)
    json.dump({"rows": rows, "pass": verdict}, open(a.out, "w"), indent=1)
    print("STRADDLE_GATE", "PASS" if verdict else "FAIL")


if __name__ == "__main__":
    main()
