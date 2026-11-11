"""M72 1.3 A6 served-path smoke (designer instrument; spec `docs/specs/m72-1.3-tq4-production.md` A6 + S21-P10): against a lean
router started from a committed arm (`kv_bits: 4` + `tq4_attention`), HTTP only. Request 1: a ~32K-token code prompt with an explicit
session header, MTP ON (the arm's drafter), deployed sampling, `max_tokens` 512. Request 2: an ~8K-token prompt with NO session
header (must resolve to an anonymous session → `backend=cached_session`). After each: the worker's `/health` route counters; at the
end: the arm log's `Request completed` lines. Refuses unless :8000 is owned by an mlx-serve router whose `MLX_SERVE_CONFIG` is the
given arm registry (the M50 discipline, checked from `ps` / `lsof`, never from this script's argv patterns).

  m72_13_served_smoke.py --arm-registry <arm>/main_models.yaml --arm-log <arm>/logs/main_model.log --out <json>
"""

import argparse
import json
import random
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
ROUTER, WORKER = "http://127.0.0.1:8000", "http://127.0.0.1:8091"
DEPLOYED = dict(temperature=0.5, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0)


def router_owner(registry):
    pids = subprocess.run(["lsof", "-nP", "-t", "-iTCP:8000", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()
    if len(pids) != 1:
        raise SystemExit(f"refusing: :8000 listeners {pids}")
    env = subprocess.run(["ps", "eww", "-o", "command=", "-p", pids[0]], capture_output=True, text=True).stdout
    want = f"MLX_SERVE_CONFIG={Path(registry).resolve()}"
    if want not in env or "mlx-serve" not in env:
        raise SystemExit("refusing: :8000 is not an mlx-serve router on the arm registry")
    return int(pids[0])


def post(path, body, headers, timeout):
    req = urllib.request.Request(ROUTER + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # transport errors raise: abort, never grade
        return json.loads(r.read())


def worker_counts():
    with urllib.request.urlopen(WORKER + "/health", timeout=30) as r:
        h = json.loads(r.read())
    return (h.get("tq4_attention") or {}).get("route_counts", {}), (h.get("tq4_attention") or {}).get("mode")


def code_prompt(root, n_chars, seed):
    root = Path(root)
    text = "".join(f"\n# ==== {f.name} ====\n" + f.read_text(errors="replace") for f in sorted(root.rglob("*.py")))
    off = random.Random(seed).randint(0, len(text) - n_chars - 1)
    return "Here is some code:\n\n" + text[off : off + n_chars] + "\n\nExplain what this code does and identify any bugs."


def delta(a, b):
    return {k: b.get(k, 0) - a.get(k, 0) for k in sorted(set(a) | set(b)) if b.get(k, 0) != a.get(k, 0)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm-registry", required=True)
    ap.add_argument("--arm-log", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--corpus-root", required=True)  # a source tree (e.g. <arm>/benchmark)
    ap.add_argument("--timeout", type=int, default=1800)  # 32K prefill + 512 tokens at a floor of 2 tok/s, plus headroom
    a = ap.parse_args()
    if Path(a.out).exists():
        print(f"refusing: {a.out} exists", file=sys.stderr)
        return 10
    pid = router_owner(a.arm_registry)
    log_start = Path(a.arm_log).stat().st_size if Path(a.arm_log).exists() else 0
    rows = []
    for name, chars, headers, max_tokens in (("explicit_session_32k", 110_000, {"x-session-id": "m72-13-smoke-a"}, 512),
                                            ("no_session_header_8k", 28_000, {}, 128)):
        try:
            c0, mode = worker_counts()
        except OSError:
            c0, mode = {}, None  # worker not loaded yet (on demand): counts start at zero
        body = {"model": MODEL, "messages": [{"role": "user", "content": code_prompt(a.corpus_root, chars, len(rows) + 7)}],
                "max_tokens": max_tokens, "stream": False, **DEPLOYED}
        t0 = time.perf_counter()
        resp = post("/v1/chat/completions", body, headers, a.timeout)
        dt = time.perf_counter() - t0
        c1, mode = worker_counts()
        rows.append({"name": name, "headers": sorted(headers), "seconds": round(dt, 1), "usage": resp.get("usage"),
                     "finish_reason": resp["choices"][0].get("finish_reason"), "mode": mode, "route_counts_delta": delta(c0, c1)})
        print(json.dumps(rows[-1]), flush=True)
    text = Path(a.arm_log).read_text(errors="replace")[log_start:]
    done = [l[l.index("Request completed"):] for l in text.splitlines() if "Request completed" in l]
    owner_after = router_owner(a.arm_registry)
    Path(a.out).write_text(json.dumps({"router_pid": pid, "router_pid_after": owner_after, "rows": rows,
                                       "request_completed": done[-len(rows):]}, indent=1))
    return 0 if owner_after == pid else 3


if __name__ == "__main__":
    sys.exit(main())
