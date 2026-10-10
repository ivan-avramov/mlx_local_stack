"""M58 arms analysis: capacity cold rungs (prefill s, decode tok/s over 256 tokens, peak) paired A vs B per session, and the
sustained-decode medians via decode_probe compare. Prints a markdown table. Usage: python analyze_arms.py"""
import json, os, statistics, subprocess, sys
R = "$STACK_REPO"; W = os.path.expanduser("~/ws/mlx_local_stack_workdir/m58"); M = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
res = f"{R}/benchmark/results/{M}"
def rows(tag):
    p = f"{res}/capacity_ladder.{tag}.jsonl"
    return {r["ctx"]: r for r in (json.loads(l) for l in open(p)) if r.get("execution_status") == "completed"} if os.path.exists(p) else {}
print("## Capacity cold rungs (A=per_query, B=joint_v1): prefill s | decode tok/s (256-token screen) | MLX peak GB")
print("| ctx | A-s1 | B-s1 | B-s2 | A-s2 | Δdecode s1 (B/A−1) | Δdecode s2 | Δprefill s1 | Δprefill s2 |"); print("|---|---|---|---|---|---|---|---|---|")
cap = {s: rows(f"m58-{s}") for s in ("A-s1", "B-s1", "B-s2", "A-s2")}
for ctx in (8192, 65536, 131072, 262144):
    cell = lambda s: (f"{cap[s][ctx]['prefill_s']:.1f} | {cap[s][ctx]['decode_tps']:.2f} | {cap[s][ctx].get('server_peak_gb') or 0:.2f}" if ctx in cap[s] else "— | — | —")
    d = lambda a, b, k: (f"{cap[b][ctx][k]/cap[a][ctx][k]-1:+.1%}" if ctx in cap[a] and ctx in cap[b] else "—")
    print(f"| {ctx} | {cell('A-s1')} | {cell('B-s1')} | {cell('B-s2')} | {cell('A-s2')} | {d('A-s1','B-s1','decode_tps')} | {d('A-s2','B-s2','decode_tps')} | {d('A-s1','B-s1','prefill_s')} | {d('A-s2','B-s2','prefill_s')} |")
print("\n## Sustained decode (decode_probe compare, sessions paired A-s1↔B-s1 and A-s2↔B-s2)")
cmd = [f"{R}/.venv-bench/bin/python", f"{W}/decode_probe.py", "compare", "--a", f"{W}/arms/decode.A-s1.json", f"{W}/arms/decode.A-s2.json", "--b", f"{W}/arms/decode.B-s1.json", f"{W}/arms/decode.B-s2.json"]
env = dict(os.environ, PYTHONPATH=f"{R}/benchmark")
print(subprocess.run(cmd, capture_output=True, text=True, env=env).stdout[-3000:])
