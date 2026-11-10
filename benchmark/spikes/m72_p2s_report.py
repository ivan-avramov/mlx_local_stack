#!/usr/bin/env python3
"""Generate benchmark/results/m72/P2S.md from the m72_tq4_probe ``--mode p2s`` JSONs (never hand-edit the output).

M72 P2' stage 1 (C314, ``dev/m72_scratch_prefill.py``): fused TQ4 dequantize into a per-layer fp16 scratch + MLX fused
SDPA. Exactness / accuracy (A1-A3), per-chunk prefill attention times against native16 fused_v1, today's TQ4 prefill and
P1, the 16-layer chain (lazy vs per-layer evaluation), pass drift, and the prefill-time projection for
Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed (spec docs/specs/m72-p2-stage1-scratch.md).
Usage: python benchmark/spikes/m72_p2s_report.py <run_dir> > benchmark/results/m72/P2S.md
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m72_probe_report import CHUNK, LAYERS, PICK_BASELINE, interp  # noqa: E402

PASSES = ("p2s-1", "p2s-2")
ARMS = ("native16_fused_v1", "tq4_production", "p1_rotated_bf16", "p2s", "p2s_dequant_only")
FORWARD = list(ARMS)
REVERSE = list(reversed(ARMS))
PROJ_ARMS = ("tq4_production", "p1_rotated_bf16", "p2s")
APPEND_KEY = {"native16_fused_v1": "native16_mean_last64", "tq4_production": "tq4_mean_last64",
              "p1_rotated_bf16": "tq4_mean_last64", "p2s": "tq4_mean_last64"}
APPEND_T = 260096
CAP = 262144
CONTROLS = ("N1",)


def load(d):
    return {n: json.loads((d / f"{n}.json").read_text()) for n in PASSES if (d / f"{n}.json").exists()}


def provenance_mismatch(runs):
    """Messages for every provenance field whose value differs across passes, plus arm-order problems (empty = ok)."""
    def fields(run):
        m = run["meta"]
        return {"meta.fork.head": (m.get("fork") or {}).get("head"), "meta.mlx": m.get("mlx"),
                "meta.device.architecture": (m.get("device") or {}).get("architecture"),
                "meta.p2s_kernel": m.get("p2s_kernel"),
                "checkpoint T list": sorted(c["T"] for c in run["checkpoints"])}

    out = [f"{n}: meta.mode = {r['meta'].get('mode')!r}, not 'p2s'" for n, r in runs.items()
           if r["meta"].get("mode") != "p2s"]
    vals = {n: fields(r) for n, r in runs.items()}
    first = next(iter(vals.values()))
    out += [f"{key} differs: " + ", ".join(f"{n} = {v[key]!r}" for n, v in vals.items())
            for key in first if len({json.dumps(v[key], sort_keys=True) for v in vals.values()}) > 1]
    if len(runs) != 2:
        missing = [f"{n}.json" for n in PASSES if n not in runs]
        return out + [f"needs both {' and '.join(p + '.json' for p in PASSES)} (one forward + one reverse pass); missing: "
                      + ", ".join(missing)]
    fwd = sorted((r["meta"].get("arm_order") or []) == FORWARD for r in runs.values())
    rev = sorted((r["meta"].get("arm_order") or []) == REVERSE for r in runs.values())
    if fwd != [False, True] or rev != [False, True]:
        out.append("arm orders are not one forward + one reverse: " + ", ".join(
            f"{n} = {r['meta'].get('arm_order')!r}" for n, r in runs.items()))
    return out


def a2_verdict(ctl):
    """A2 holds when every named control (N1) is present exactly once and fails A1 (extra named controls allowed)."""
    names = [c.get("name") for c in ctl]
    why = []
    for n in CONTROLS:
        if names.count(n) == 0:
            why.append(f"missing {n}")
        elif names.count(n) > 1:
            why.append(f"duplicated {n}")
    passed = [c.get("name") for c in ctl if c.get("name") in CONTROLS and c.get("pass_a1") is not False]
    if passed:
        why.append("did not fail A1: " + ", ".join(passed))
    return "A2 holds" if not why else "A2 NOT shown (" + "; ".join(why) + ")"


def attn_s(points_ms, N):
    """Seconds of one layer's attention over a cold N-token prefill: sum over chunks of interp at each chunk's end."""
    return sum(interp(points_ms, j * CHUNK) for j in range(1, N // CHUNK + 1)) / 1e3


def projection(points, append_ms, prefill_s, arms=PROJ_ARMS):
    """{N: {"fixed": s, arm: t_X(N) s}}. ``points`` = {arm: {T: ms}} (sub-cap checkpoints; must include
    native16_fused_v1); ``append_ms`` = {arm: ms per 512-token KV append}; ``prefill_s`` = {N: measured s}.
    fixed = prefill_s(N) - 16 attn_native16(N) - 16 (N/512) append_native16; t_X = fixed + 16 attn_X + 16 (N/512) append_X.
    """
    out = {}
    n16 = "native16_fused_v1"
    for N, t_meas in prefill_s.items():
        chunks = N // CHUNK
        fixed = t_meas - LAYERS * attn_s(points[n16], N) - LAYERS * chunks * append_ms[n16] / 1e3
        row = {"fixed": fixed}
        for a in arms:
            row[a] = fixed + LAYERS * attn_s(points[a], N) + LAYERS * chunks * append_ms[a] / 1e3
        out[N] = row
    return out


def exactness_lines(name, run):
    ex = run["meta"]["p2s_exactness"]
    rows = ex["rows"]
    fid = [r for r in rows if r["what"] in ("K", "V")]
    pre = [r for r in rows if r["what"] == "prefill"]
    out = [f"- {name}: dequant fidelity (bit-identical to the generic-op reference on [0, T)) "
           f"{sum(r['bit_identical'] for r in fid)} / {len(fid)} rows (T ∈ {sorted({r['T'] for r in fid})}, dtypes "
           f"{sorted({r['dtype'] for r in fid})}); full-path identity vs P1 in fp16 (diagnostic) "
           f"{sum(r['bit_identical'] for r in pre)} / {len(pre)}; n_ok {ex['n_ok']} / {ex['n']}."]
    bad = [f"T={r['T']} L={r['L']} {r['what']} {r['dtype']}" for r in rows if not r["bit_identical"]]
    if bad:
        out.append("  - Not bit-identical: " + "; ".join(bad))
    if ex.get("skipped_T"):
        out.append(f"  - Sweep T skipped (above --max-t): {ex['skipped_T']}.")
    acc = ex.get("accuracy_rows") or []
    gate = [r for r in acc if r.get("gates_a1")]
    if acc:
        worst = max(acc, key=lambda r: r["rel_err"])
        out.append(f"  - A1 sweep rows (L = 512, gating): {sum(r['pass'] for r in gate)} / {len(gate)} pass; all rows "
                   f"{sum(r['pass'] for r in acc)} / {len(acc)}; non-finite {sum(not r['finite'] for r in acc)}; "
                   f"worst rel error {worst['rel_err']:.2e} (production {worst['prod_rel_err']:.2e}) at T = "
                   f"{worst['T']}, L = {worst['L']}.")
        fails = [f"T={r['T']} L={r['L']} rel {r['rel_err']:.2e}" for r in acc if not r["pass"]]
        if fails:
            out.append("  - A1 failures: " + "; ".join(fails))
    ca = ex.get("causal_alignment") or {}
    if "pass" in ca:
        out.append(f"  - Causal alignment (T = {ca['T']}, L = {ca['L']}): rel vs bottom-right mask "
                   f"{ca['rel_vs_bottom_right']:.2e}, vs top-left mask {ca['rel_vs_top_left']:.2e} → "
                   f"{'aligned' if ca['pass'] else 'NOT aligned'}.")
    else:
        out.append(f"  - Causal alignment: {ca or 'not recorded'}.")
    ctl = ex.get("controls") or []
    out.append("  - Negative controls (each must fail A1): " + (", ".join(
        f"{c['name']} rel {c['rel_err']:.3g} pass_a1 {c['pass_a1']}" for c in ctl) or "none recorded")
        + f" → {a2_verdict(ctl)}.")
    ck = [(c["T"], h, a) for c in run["checkpoints"] for h, a in sorted(c["p2s_accuracy"].items(), key=lambda x: int(x[0]))]
    ck_bad = [f"T={T} head {h} rel {a['rel_err']:.2e}" for T, h, a in ck if not a["pass"]]
    out.append(f"  - Checkpoint heads: {sum(a['pass'] for *_, a in ck)} / {len(ck)} pass A1"
               + (f"; failures: {'; '.join(ck_bad)}" if ck_bad else "")
               + "; worst rel / production per T: " + ", ".join(
                   f"T={c['T']} {max(a['rel_err'] for a in c['p2s_accuracy'].values()):.2e} / "
                   f"{max(a['prod_rel_err'] for a in c['p2s_accuracy'].values()):.2e}" for c in run["checkpoints"])
               + "; p2s vs P1 fp16 bit-identical (diagnostic): " + ", ".join(
                   f"T={c['T']} {c['p2s_vs_reference_bit_identical']}" for c in run["checkpoints"]) + ".")
    return out


def main():
    d = Path(sys.argv[1])
    runs = load(d)
    if not runs:
        sys.exit(f"no {' / '.join(p + '.json' for p in PASSES)} in {d}")
    bad = provenance_mismatch(runs)
    if bad:
        sys.exit("REFUSED: passes not combinable (" + "; ".join(bad) + ")")
    names = list(runs)
    cks = {n: {c["T"]: c for c in runs[n]["checkpoints"]} for n in names}
    Ts = sorted(cks[names[0]])
    Tp = [T for T in Ts if T < CAP]  # sub-cap only (served layout)

    def t(T, arm):
        """Mean over passes of the median time (ms)."""
        return sum(cks[n][T]["p2s"][arm]["median_ms"] for n in names) / len(names)

    P = print
    m = runs[names[0]]["meta"]
    fork = m["fork"]
    kern = m.get("p2s_kernel", {})
    dirty = ", ".join(fork.get("dirty_paths") or []) or "none"
    cap_rec = (m.get("shapes") or {}).get("cap")
    prealloc = f"{cap_rec:,} tokens" if cap_rec else f"the cache cap (not recorded; largest checkpoint T = {max(Ts):,})"
    P("# M72 P2′ stage 1 — fused TQ4 dequantize into a per-layer scratch + MLX fused SDPA (GENERATED by "
      "`benchmark/spikes/m72_p2s_report.py`; never hand-edit)\n")
    P(f"MLX {m['mlx']}, {m['device']['device_name']} `{m['device']['architecture']}`; fork "
      f"`{fork.get('head', '?')[:8]}` (dirty: {dirty}); per full-attention layer, 24 q / 4 kv heads, head dim 256, bf16 "
      f"queries, synthetic K/V, caches preallocated to {prealloc}; one 512-token chunk ending at T; medians; mean of "
      f"passes {', '.join(names)}. Prototype `dev/m72_scratch_prefill.py`: scratch dtype {kern.get('dtype', '?')}; "
      f"thread mapping: {kern.get('thread_mapping', '?')}; codebook: {kern.get('codebook_placement', '?')}.\n")
    P("Timed-arm order per checkpoint: " + "; ".join(
        f"{n} {' → '.join(runs[n]['meta'].get('arm_order') or ['not recorded'])}" for n in names)
      + ".\n")

    P("## 1. Exactness and accuracy (A1: rel error ≤ 2 × max(production rel error, 2⁻¹²) and allclose(atol = rtol = "
      "3e-2) vs the fp32 reference, finite; fidelity: dequant bit-identical to the generic-op reference; A2: N1 (KV "
      "heads rolled by one, planted per-head value scales) fails A1; A3: edge T / L rows)\n")
    for n in names:
        for line in exactness_lines(n, runs[n]):
            P(line)

    P("\n## 2. Per-chunk prefill attention (ms per 512-token chunk per layer)\n")
    P("native16 fused_v1 = the shipped pick's path; TQ4 production = today's TQ4 prefill; P1 = generic-op rotated "
      "dequantize to bf16 + fused SDPA; p2s = the fused dequantize kernel into the fp16 scratch + fused SDPA (the whole "
      "public function); p2s dequant only = the kernel alone (diagnostic).\n")
    P("| T | native16 fused_v1 | TQ4 production | P1 rotated bf16 | p2s | p2s dequant only | p2s / native16 fused_v1 | "
      "p2s / TQ4 production | p2s / P1 rotated bf16 |")
    P("|---|---|---|---|---|---|---|---|---|")
    for T in Ts:
        v = {a: t(T, a) for a in ARMS}
        P(f"| {T} | " + " | ".join(f"{v[a]:.2f}" for a in ARMS)
          + f" | {v['p2s'] / v['native16_fused_v1']:.2f} | {v['p2s'] / v['tq4_production']:.2f} | "
          f"{v['p2s'] / v['p1_rotated_bf16']:.2f} |")
    chain = [(n, T, cks[n][T]["chain16"]) for n in names for T in Ts if "chain16" in cks[n][T]]
    if chain:
        lz = sum(c["lazy"]["median_ms"] for *_, c in chain) / len(chain)
        pl = sum(c["per_layer_eval"]["median_ms"] for *_, c in chain) / len(chain)
        chain_T = ", ".join(str(T) for T in sorted({T for _, T, _ in chain}))
        P(f"\nchain16 at T = {chain_T} (16 chained layers over 16 distinct caches, mean of {len(chain)} pass(es)): lazy "
          f"{lz:.1f} ms, evaluated per layer {pl:.1f} ms, per-layer / lazy {pl / lz:.3f} (the cost of the mandatory "
          "per-layer evaluation).")
    else:
        P("\nchain16: not measured (no checkpoint in this run records chain16; the probe records it at the cache cap).")
    if len(names) == 2:
        a, b = names
        P(f"\nPass-to-pass drift ({b} / {a}, per arm in table order): " + "; ".join(
            f"T={T} " + " / ".join(f"{cks[b][T]['p2s'][x]['median_ms'] / cks[a][T]['p2s'][x]['median_ms']:.3f}"
                                   for x in ARMS) for T in Ts))
    P("\nPower / peak per checkpoint (first pass): " + "; ".join(
        f"T={T} {cks[names[0]][T]['power'].get('wattage')} {cks[names[0]][T]['power'].get('battery')} peak "
        f"{cks[names[0]][T]['peak_GB']:.1f} GB" for T in Ts))

    P("\n## 3. Prefill-time projection for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` "
      "(vs its shipped native16 + fused_v1)\n")
    if len(Tp) < 2 or APPEND_T not in Ts:
        P(f"Not computed: needs ≥ 2 sub-cap checkpoints and the {APPEND_T} checkpoint (KV append); this run has {Ts}.")
        return
    points = {a: {T: t(T, a) for T in Tp} for a in ("native16_fused_v1",) + PROJ_ARMS}
    append = {a: sum(cks[n][APPEND_T]["kv_append_chunk_ms"][k] for n in names) / len(names)
              for a, k in APPEND_KEY.items()}
    P(f"attn_X(N) = Σ_j interp(X, 512·j) / 1000 s over the sub-cap checkpoints {Tp} (linear extrapolation below the "
      f"first); append = the {APPEND_T} checkpoint's KV append per 512-token chunk (TQ4 "
      f"{append['tq4_production']:.2f} ms, native16 {append['native16_fused_v1']:.2f} ms); fixed = prefill_s(N) − "
      f"{LAYERS} · attn_native16(N) − {LAYERS} · (N/512) · append_native16; t_X(N) = fixed + {LAYERS} · attn_X(N) + "
      f"{LAYERS} · (N/512) · append_X. × = prefill_s(N) / t_X(N) (speed relative to native16 shipped).\n")
    proj = projection(points, append, PICK_BASELINE["prefill_s"])
    P("| N | native16 shipped (measured, s) | fixed (s) | TQ4 today | P1 rotated bf16 | p2s |")
    P("|---|---|---|---|---|---|")
    for N, row in proj.items():
        ms = PICK_BASELINE["prefill_s"][N]
        P(f"| {N} | {ms:.1f} ({N / ms:.0f} tok/s) | {row['fixed']:.1f} | "
          + " | ".join(f"{row[a]:.1f} ({ms / row[a]:.2f}×)" for a in PROJ_ARMS) + " |")


if __name__ == "__main__":
    main()
