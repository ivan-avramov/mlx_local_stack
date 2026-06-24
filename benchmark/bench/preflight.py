"""Preflight canary — confirm the stack is sane before a benchmark run.

Loads the target model and runs ONE trivial coding probe under the model's production
params, asserting it CONVERGES (finish=='stop' AND completion_tokens < thinking_budget)
and emits code. A loop / truncation / empty answer here means the stack is in a bad state
(stale router, bad model load, wrong quant) — abort before wasting a multi-hour run.

This is the gate that would have caught the stale-router loops directly. Exit 0 = sane,
1 = not sane. Invoked by preflight.sh after a fresh router restart.

  python benchmark/bench/preflight.py <registered-model-name>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bench import client, convergence, model_params  # noqa: E402

CANARY = (
    "Write a Python function is_palindrome(s) that returns True iff s reads the same "
    "forwards and backwards, ignoring case and non-alphanumeric characters. "
    "Return the solution as a single self-contained ```python code block."
)


def restart_router(base: str = "http://localhost:8000", wait_s: int = 90) -> bool:
    """Force a fresh local router: kill mlx procs, relaunch mlx-serve, wait for health.
    Used as generate.run's restart_fn for auto-restart-on-loop. Returns True if healthy.
    Runs from repo root (the recipe sources ./.env and reads main_models.yaml)."""
    import subprocess
    import time
    import urllib.request
    for pat in ("mlx-serve", "mlx_vlm.server"):
        subprocess.run(["pkill", "-9", "-f", pat], stderr=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL)
    time.sleep(3)
    recipe = ("set -a; . ./.env 2>/dev/null || true; set +a; "
              "MLX_SERVE_CONFIG=main_models.yaml nohup uv run mlx-serve start "
              ">>logs/main_model.log 2>&1 </dev/null &")
    subprocess.Popen(["bash", "-lc", recipe])
    deadline = time.time() + wait_s
    while time.time() < deadline:
        time.sleep(3)
        try:
            with urllib.request.urlopen(base + "/health", timeout=4) as r:
                if b"ok" in r.read():
                    return True
        except Exception:  # noqa: BLE001
            pass
    return False


def run_canary(model: str) -> bool:
    client.preload(model)
    params = model_params.params_for(model)
    r = client.probe(model, [{"role": "user", "content": CANARY}], params)
    row = {"finish_reason": r.get("finish_reason"),
           "completion_tokens": r.get("completion_tokens"),
           "thinking_budget": params.get("thinking_budget")}
    conv = convergence.is_converged(row)
    content = r.get("content") or ""
    has_code = "```python" in content or "def is_palindrome" in content
    print(f"[preflight] model={model} finish={row['finish_reason']} "
          f"comp_tok={row['completion_tokens']} budget={row['thinking_budget']} "
          f"converged={conv} code={has_code}", flush=True)
    return conv is True and has_code


def main():
    if len(sys.argv) < 2:
        print("usage: preflight.py <registered-model-name>")
        sys.exit(2)
    ok = run_canary(sys.argv[1])
    if not ok:
        print("[preflight] FAIL — stack NOT sane (loop / truncation / no code). "
              "Do NOT run; restart the router and re-check the model/quant.", flush=True)
        sys.exit(1)
    print("[preflight] PASS — stack sane, safe to run the benchmark.", flush=True)


if __name__ == "__main__":
    main()
