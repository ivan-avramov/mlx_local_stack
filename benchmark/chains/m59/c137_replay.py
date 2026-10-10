# FROZEN copy (P229, 2026-10-10) of $STACK_WORKDIR/m59/c137_replay.py, the driver behind the opencode_v2_*.m59.* (M59) rows.
# Only change: absolute home paths -> $STACK_WORKDIR / $STACK_REPO. See benchmark/chains/README.md.
"""C137 replay probe: one ~25K-token seeded request, long generation, repeated under one attention policy.
Arms (env M59_OVERLAY): fresh prefill x3 (distinct session ids) and cached prefix x2 (one session id reused).
Compares completion text byte-for-byte and usage. Usage: c137_replay.py <tag>"""
import hashlib, json, os, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_m59 as R

TAG = sys.argv[1]
MODEL = R.PICK1
MAX_TOKENS = 3000
OUT = R.OUT / "c137" / TAG
OUT.mkdir(parents=True, exist_ok=True)
REPO = R.REPO
poly = Path(os.environ["STACK_WORKDIR"]) / "polyglot-benchmark" / "python" / "exercises" / "practice"
# ~25K tokens of real exercise material: instructions + stubs + tests of several exercises
chunks = []
for ex in sorted(poly.iterdir()):
    for f in sorted(ex.rglob("*")):
        if f.is_file() and f.suffix in (".md", ".py") and ".meta" not in f.parts:
            chunks.append(f"### {ex.name}/{f.relative_to(ex)}\n" + f.read_text(errors="replace"))
    if sum(len(c) for c in chunks) > 95_000:
        break
context = "\n\n".join(chunks)[:95_000]
prompt = ("You are reviewing a set of Python exercises. Below are their specifications, stubs and tests.\n\n" + context +
          "\n\nTask: pick the three exercises whose tests are most likely to catch subtle off-by-one or boundary errors, explain why in detail, "
          "and write a complete reference implementation for the hardest of the three. Think carefully before answering.")

def chat(session, seed):
    body = {"model": f"caslca/{MODEL}" if False else MODEL, "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0,
            "max_tokens": MAX_TOKENS, "seed": seed, "enable_thinking": True, "thinking_budget": 81920, "stream": False}
    req = urllib.request.Request(R.BASE + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-session-id": session}, method="POST")
    t0 = time.time()
    d = json.loads(urllib.request.urlopen(req, timeout=3600).read())
    msg = d["choices"][0]["message"]
    text = (msg.get("reasoning_content") or msg.get("reasoning") or "") + "\n<<<CONTENT>>>\n" + (msg.get("content") or "")
    return {"session": session, "seed": seed, "elapsed_s": round(time.time() - t0, 1), "usage": d.get("usage"),
            "finish": d["choices"][0].get("finish_reason"), "sha256": hashlib.sha256(text.encode()).hexdigest(), "chars": len(text), "text": text}

R.log(f"C137 START {TAG} overlay={R.OVERLAY} max_tokens={MAX_TOKENS} prompt_chars={len(prompt)}")
R.start_router()
runs = []
try:
    R.load(MODEL)
    plan = [("c137-fresh-1", 4242), ("c137-fresh-2", 4242), ("c137-fresh-3", 4242), ("c137-cached", 4242), ("c137-cached", 4242)]
    for sess, seed in plan:
        r = chat(sess, seed); runs.append(r)
        (OUT / f"{sess}-{len(runs)}.txt").write_text(r["text"])
        R.log(f"C137 {TAG} {sess} run{len(runs)}: {r['elapsed_s']}s finish={r['finish']} usage={r['usage']} sha={r['sha256'][:12]} chars={r['chars']}")
    fresh = [r["sha256"] for r in runs[:3]]; cached = [r["sha256"] for r in runs[3:]]
    verdict = {"fresh_identical": len(set(fresh)) == 1, "cached_identical": len(set(cached)) == 1,
               "cached_equals_fresh": cached[0] == fresh[0], "shas": [r["sha256"][:12] for r in runs]}
    if len(set(fresh)) > 1:
        a, b = [r["text"] for r in runs[:2]] if runs[0]["sha256"] != runs[1]["sha256"] else [runs[0]["text"], runs[2]["text"]]
        n = 0
        while n < min(len(a), len(b)) and a[n] == b[n]:
            n += 1
        verdict["first_divergence_char"] = n
    R.log(f"C137 {TAG} VERDICT {json.dumps(verdict)}")
    (OUT / "verdict.json").write_text(json.dumps({"verdict": verdict, "runs": [{k: v for k, v in r.items() if k != 'text'} for r in runs]}, indent=1))
    R.unload(MODEL)
finally:
    R.stop_stack()
R.log(f"C137 DONE {TAG}")
