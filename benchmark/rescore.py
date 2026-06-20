#!/usr/bin/env python3
"""Re-score existing capacity_retrieval.json results under the MLX-peak gate
(fits = server_peak_gb <= GATE). Use after changing the gate metric so completed
models don't need re-running -- their MLX peak (server_peak_gb) is already recorded.
Pure stdlib. Usage:  python rescore.py   (GATE_GB env overrides the 46GB default)"""
import glob
import json
import os

GATE = float(os.environ.get("GATE_GB", "46"))
RESULTS = os.path.join(os.path.dirname(__file__), "results")

for jf in sorted(glob.glob(os.path.join(RESULTS, "*", "capacity_retrieval.json"))):
    d = json.load(open(jf))
    recs = d.get("records", [])
    if not recs:
        continue
    for r in recs:
        sp = r.get("server_peak_gb")
        r["fits"] = (sp is not None) and (sp <= GATE)
    fit = [r for r in recs if r["fits"]]
    thr = d.get("retrieval_threshold", 0.85)
    d["gate_metric"] = "mlx_peak_gb (mx.get_peak_memory, the prefill spike)"
    d["gate_gb"] = GATE
    d["max_fitting_ctx"] = max((r["ctx"] for r in fit), default=None)
    d["capacity_gate_pass"] = any(r["ctx"] >= 256_000 for r in fit)
    passing = [r["ctx"] for r in fit if r.get("retrieval_acc", 0) >= thr]
    d["retrieval_effective_ctx"] = max(passing, default=None)
    json.dump(d, open(jf, "w"), indent=2)
    name = os.path.basename(os.path.dirname(jf))
    peaks = " ".join(f"{r['ctx']//1000}K:mlx={r.get('server_peak_gb')}/rss={r.get('peak_rss_gb')}/acc={r.get('retrieval_acc')}" for r in recs)
    print(f"{name}: max_fit={d['max_fitting_ctx']} gate_pass={d['capacity_gate_pass']} "
          f"retr_eff={d['retrieval_effective_ctx']}\n    {peaks}")
