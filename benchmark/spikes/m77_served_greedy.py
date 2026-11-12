"""M77 acceptance criterion 6 (designer instrument): greedy served output of one lean router, for comparing the M76 XO arm
(`kv_bits: 4` + `tq4_attention: m72_exact`, MTP OFF) with the X arm (the same with MTP ON). HTTP only, against :8000, which must
be owned by an mlx-serve router whose `MLX_SERVE_CONFIG` is the given arm registry (checked from `ps` / `lsof`).

For each seeded prompt (code text from a source tree, at the given character lengths): two requests in the same loaded instance,
each with its own session id (no cached prefix), temperature 0, `max_tokens` N, thinking as deployed — the second is the repeat
control. Records per request: the full returned text (reasoning + content), token counts, finish reason, `cached_tokens`, drafter
counters; and the worker's TQ4 route counters before and after. `--compare A B` diffs two output files request by request.

  m77_served_greedy.py --arm-registry <arm>/main_models.yaml --corpus-root <tree> --out <json>
  m77_served_greedy.py --compare <a.json> <b.json>
"""

import argparse
import json
import random
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m72_13_served_smoke import MODEL, code_prompt, post, router_owner, worker_counts  # noqa: E402

LENGTHS = (30_000, 120_000)  # characters ≈ 8K / 32K tokens of code


def one(prompt, max_tokens, timeout):
    sid = f"m77-greedy-{uuid.uuid4().hex[:12]}"
    body = dict(model=MODEL, messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens, temperature=0.0,
                seed=0, stream=False)
    r = post("/v1/chat/completions", body, {"x-session-id": sid}, timeout)
    msg = r["choices"][0]["message"]
    usage = r.get("usage") or {}
    return dict(session=sid, text=(msg.get("reasoning_content") or "") + "␞" + (msg.get("content") or ""),
                finish=r["choices"][0].get("finish_reason"), usage=usage,
                cached=((usage.get("prompt_tokens_details") or {}).get("cached_tokens")),
                timings=r.get("timings") or {})


def run(args):
    pid = router_owner(args.arm_registry)
    one("Say OK.", 8, args.timeout)  # warm-up: the router loads the worker on demand (no /health before it)
    before, mode = worker_counts()
    rows = []
    for i, n in enumerate(LENGTHS):
        for seed in range(args.prompts):
            prompt = code_prompt(args.corpus_root, n, 7700 + 10 * i + seed)
            a = one(prompt, args.max_tokens, args.timeout)
            b = one(prompt, args.max_tokens, args.timeout)
            rows.append(dict(chars=n, seed=seed, first=a, repeat=b, repeat_identical=a["text"] == b["text"]))
            print(f"chars {n} seed {seed}: finish {a['finish']} tokens {a['usage'].get('completion_tokens')} "
                  f"repeat identical {a['text'] == b['text']}", flush=True)
    after, mode2 = worker_counts()
    out = dict(arm_registry=str(Path(args.arm_registry).resolve()), router_pid=pid, mode=[mode, mode2],
               route_counts_before=before, route_counts_after=after, max_tokens=args.max_tokens, rows=rows)
    Path(args.out).write_text(json.dumps(out, indent=1))


def compare(a, b):
    A, B = json.loads(Path(a).read_text()), json.loads(Path(b).read_text())
    same = 0
    for ra, rb in zip(A["rows"], B["rows"]):
        eq = ra["first"]["text"] == rb["first"]["text"]
        same += eq
        if not eq:
            ta, tb = ra["first"]["text"], rb["first"]["text"]
            k = next((i for i, (x, y) in enumerate(zip(ta, tb)) if x != y), min(len(ta), len(tb)))
            print(f"chars {ra['chars']} seed {ra['seed']}: DIFFER at char {k}: {ta[k:k+40]!r} vs {tb[k:k+40]!r}")
    ctl = all(r["repeat_identical"] for r in A["rows"] + B["rows"])
    print(json.dumps(dict(identical=same, of=len(A["rows"]), repeat_controls_identical=ctl)))
    return 0 if same == len(A["rows"]) and ctl else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm-registry")
    ap.add_argument("--corpus-root")
    ap.add_argument("--out")
    ap.add_argument("--prompts", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--compare", nargs=2)
    args = ap.parse_args()
    if args.compare:
        return compare(*args.compare)
    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
