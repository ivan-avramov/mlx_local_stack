#!/usr/bin/env python3
"""Generate benchmark/results/m72/MMA.md from the m72_tq4_probe ``--mode mma`` JSONs (never hand-edit the output).

M72 step 1.2 matrix-unit verify kernel prototype (C312 / C313, ``dev/m72_mma_verify.py``): accuracy against the fp32
reference (A1-A4), per-layer times against matched in-process baselines, and decode projections for
Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed with the method of ``m72_mq_report`` (fixed cost = the pick's shipped
measurement minus this run's native16 attention).
Usage: python benchmark/spikes/m72_mma_report.py <run_dir> > benchmark/results/m72/MMA.md
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m72_probe_report import LAYERS, PICK_BASELINE, VERIFY_K, interp  # noqa: E402

PASSES = ("mma-1", "mma-2")
ARMS = ("native16", "tq4_production", "mq_best", "mma_tq4", "mma_n16")
MMA_ARMS = ("mma_tq4", "mma_n16")
CONTROLS = tuple((n, a) for n in ("N1", "N2", "N3") for a in MMA_ARMS)
CAP = 262144


def load(d):
    return {n: json.loads((d / f"{n}.json").read_text()) for n in PASSES if (d / f"{n}.json").exists()}


def accuracy_lines(name, run):
    acc = run["meta"]["mma_accuracy"]
    rows = acc["rows"]
    out = [f"- {name}: sweep {acc['n_pass']} / {acc['n']} pass A1 (T ∈ {sorted({r['T'] for r in rows})}, "
           f"k = {min(r['k'] for r in rows)}–{max(r['k'] for r in rows)})."]
    for arm in MMA_ARMS:
        for case in ("random", "planted"):
            sel = [r for r in rows if r["arm"] == arm and r["case"] == case]
            if not sel:
                continue
            worst = max(sel, key=lambda r: r["rel_err"])
            out.append(f"  - {arm} / {case}: {sum(r['pass'] for r in sel)} / {len(sel)} pass; non-finite "
                       f"{sum(not r['finite'] for r in sel)}; worst rel error {worst['rel_err']:.2e} (production "
                       f"{worst['prod_rel_err']:.2e}) at T = {worst['T']}, k = {worst['k']}.")
    bad = [r for r in rows if not r["pass"]]
    if bad:
        out.append("  - Sweep failures: " + "; ".join(
            f"T={r['T']} k={r['k']} {r['arm']} {r['case']} rel {r['rel_err']:.2e}" for r in bad))
    ck = [(c["T"], k, arm, c["mma"][k]["accuracy"][arm]) for c in run["checkpoints"] for k in sorted(c["mma"], key=int)
          for arm in MMA_ARMS]
    ck_bad = [f"T={T} k={k} {arm} rel {a['rel_err']:.2e}" for T, k, arm, a in ck if not a["pass"]]
    out.append(f"  - Checkpoints: {sum(a['pass'] for *_, a in ck)} / {len(ck)} pass A1"
               + (f"; failures: {'; '.join(ck_bad)}." if ck_bad else "."))
    ctl = acc["controls"]
    out.append("  - Negative controls (each must fail A1): " + (", ".join(
        f"{c['name']} {c['arm']} rel {c['rel_err']:.3g} pass {c['pass']}" for c in ctl) or "none recorded")
        + f" → {a3_verdict(ctl)}.")
    return out


def a3_verdict(ctl):
    """A3 holds only when exactly the six (N1, N2, N3) x (mma_tq4, mma_n16) controls are present, once each, and
    every control's ``pass`` is False (each fails A1)."""
    keys = [(c.get("name"), c.get("arm")) for c in ctl]
    want = set(CONTROLS)
    why = []
    missing = sorted(want - set(keys))
    if missing:
        why.append("missing " + ", ".join(f"{n} {a}" for n, a in missing))
    extra = sorted({k for k in keys if k not in want}, key=str)
    if extra:
        why.append("unexpected " + ", ".join(f"{n} {a}" for n, a in extra))
    dup = sorted({k for k in keys if k in want and keys.count(k) > 1})
    if dup:
        why.append("duplicated " + ", ".join(f"{n} {a}" for n, a in dup))
    passed = [c for c in ctl if c.get("pass") is not False]
    if passed:
        why.append("did not fail A1: " + ", ".join(f"{c.get('name')} {c.get('arm')}" for c in passed))
    return "A3 holds" if not why else "A3 NOT shown (" + "; ".join(why) + ")"


def provenance_mismatch(runs):
    """Messages for every provenance field whose value differs across passes (empty = combinable)."""
    def fields(run):
        m = run["meta"]
        return {"meta.fork.head": (m.get("fork") or {}).get("head"), "meta.mlx": m.get("mlx"),
                "meta.device.architecture": (m.get("device") or {}).get("architecture"),
                "checkpoint T list": sorted(c["T"] for c in run["checkpoints"])}

    vals = {n: fields(r) for n, r in runs.items()}
    first = next(iter(vals.values()))
    return [f"{key} differs: " + ", ".join(f"{n} = {v[key]!r}" for n, v in vals.items())
            for key in first if len({repr(v[key]) for v in vals.values()}) > 1]


def main():
    d = Path(sys.argv[1])
    runs = load(d)
    if not runs:
        sys.exit(f"no {' / '.join(p + '.json' for p in PASSES)} in {d}")
    names = list(runs)
    bad = provenance_mismatch(runs)
    if bad:
        sys.exit("REFUSED: passes not combinable (" + "; ".join(bad) + ")")
    cks = {n: {c["T"]: c for c in runs[n]["checkpoints"]} for n in names}
    Ts = sorted(cks[names[0]])
    Tp = [T for T in Ts if T < CAP]  # sub-cap only (served layout)
    ks = sorted(cks[names[0]][Ts[0]]["mma"], key=int)

    def t(T, k, arm):
        """Mean over passes of the median time (ms)."""
        return sum(cks[n][T]["mma"][k][arm]["median_ms"] for n in names) / len(names)

    P = print
    m = runs[names[0]]["meta"]
    kern = m.get("mma_kernel", {})
    P("# M72 step 1.2 — matrix-unit (simdgroup MMA) verify kernel prototype (GENERATED by "
      "`benchmark/spikes/m72_mma_report.py`; never hand-edit)\n")
    fork = m["fork"]
    dirty = ", ".join(fork.get("dirty_paths") or []) or "none"
    P(f"MLX {m['mlx']}, {m['device']['device_name']} `{m['device']['architecture']}`; fork "
      f"`{fork.get('head', '?')[:8]}` (dirty: {dirty}); per full-attention layer, 24 q / 4 kv heads, "
      f"head dim 256, bf16, synthetic K/V, caches preallocated to 262,144 tokens; medians; mean of passes "
      f"{', '.join(names)}. Prototype: `dev/m72_mma_verify.py` (tile {kern.get('tile_tokens', '?')} tokens, fragment "
      f"types {kern.get('fragment_types', '?')}, fragment mapping verified: {kern.get('fragment_mapping_ok', '?')}).\n")
    P("Timed-arm order per checkpoint and k: " + "; ".join(
        f"{n} {' → '.join(runs[n]['meta'].get('arm_order') or ['not recorded'])}" for n in names) + ".\n")

    P("## 1. Accuracy (A1: rel error ≤ 2 × max(production rel error, 2⁻¹²) and allclose(atol = rtol = 3e-2) "
      "vs the fp32 reference; A2 planted cases; A3 controls N1 head shift, N2 lengths + 1, N3 lengths − 1 must fail)\n")
    for n in names:
        for line in accuracy_lines(n, runs[n]):
            P(line)

    P("\n## 2. Per-layer times (ms)\n")
    P("native16 = SDPA (k = 1) / `joint_v1`'s joint call (k ≥ 2), the shipped pick's path; TQ4 production = the "
      "shipped singleton (k ≥ 2: the per-query loop); mq best = `dev/m72_mq_decode.py`, the faster of G = 2 / 1.\n")
    P("| T | k | native16 | TQ4 production | mq best | mma TQ4 | mma native16 | mma TQ4 / TQ4 production | "
      "mma TQ4 / native16 | mma native16 / native16 | blocks × tokens |")
    P("|---|---|---|---|---|---|---|---|---|---|---|")
    for T in Ts:
        plan = cks[names[0]][T]["plan"]
        for k in ks:
            v = {a: t(T, k, a) for a in ARMS}
            G = cks[names[0]][T]["mma"][k]["mq_best"]["G"]
            P(f"| {T} | {k} | {v['native16']:.3f} | {v['tq4_production']:.3f} | {v['mq_best']:.3f} (G={G}) | "
              f"{v['mma_tq4']:.3f} | {v['mma_n16']:.3f} | {v['mma_tq4'] / v['tq4_production']:.2f} | "
              f"{v['mma_tq4'] / v['native16']:.2f} | {v['mma_n16'] / v['native16']:.2f} | "
              f"{plan['blocks']} × {plan['tokens_per_block']} |")
    if len(names) == 2:
        a, b = names
        P(f"\nPass-to-pass drift ({b} / {a}, mma TQ4 / mma native16 at k = 1 and k = {VERIFY_K}): " + ", ".join(
            f"T={T} " + " / ".join(
                f"{cks[b][T]['mma'][k][arm]['median_ms'] / cks[a][T]['mma'][k][arm]['median_ms']:.3f}"
                for k in ("1", VERIFY_K) for arm in MMA_ARMS)
            for T in Ts))
    P("\nPower / peak per checkpoint (first pass): " + "; ".join(
        f"T={T} {cks[names[0]][T]['power'].get('wattage')} {cks[names[0]][T]['power'].get('battery')} peak "
        f"{cks[names[0]][T]['peak_GB']:.1f} GB" for T in Ts))

    P("\n## 3. Projection for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` "
      "(vs its shipped native16 + fused_v1 + joint_v1)\n")
    if len(Tp) < 2:
        P(f"Not computed: the projection interpolates over ≥ 2 sub-cap checkpoints; this run has {Tp}.")
        return
    P(f"Method of PROBE.md §4 with this run's matched times, interpolated over the sub-cap checkpoints {Tp}: fixed = "
      f"the pick's measured round (MTP ON) or token (MTP OFF) minus {LAYERS} × this run's native16 attention; each "
      f"column swaps in {LAYERS} × its attention. PROBE.md's validation puts MTP ON projections +7…+18 % optimistic "
      "and MTP OFF within −5…−8 %. Prefill unchanged.\n")

    def g(k, arm):
        return lambda T: interp({x: t(x, k, arm) for x in Tp}, T)

    def gmin(k, arms):
        return lambda T: interp({x: min(t(x, k, a) for a in arms) for x in Tp}, T)

    e = PICK_BASELINE["emitted_per_round"]
    P(f"### Decode, MTP ON (tok/s), verify block k = {VERIFY_K}, emitted/round {e} (M58)\n")
    P("| T | native16 shipped (measured) | TQ4 today | TQ4 + mma | native16 + mma | TQ4 + mma / native16 + mma |")
    P("|---|---|---|---|---|---|")
    for T, dd in PICK_BASELINE["decode_on_tps"].items():
        fixed = e / dd * 1e3 - LAYERS * g(VERIFY_K, "native16")(T)
        tps = {a: e / (fixed + LAYERS * g(VERIFY_K, a)(T)) * 1e3 for a in ("tq4_production", "mma_tq4", "mma_n16")}
        P(f"| {T} | {dd:.2f} | " + " | ".join(f"{tps[a]:.2f} ({tps[a] / dd:.2f}×)"
                                             for a in ("tq4_production", "mma_tq4", "mma_n16"))
          + f" | {tps['mma_tq4'] / tps['mma_n16']:.2f}× |")
    P("\n### Decode, MTP OFF (tok/s), k = 1\n")
    P("TQ4 best = per checkpoint the faster of mq best / mma TQ4; native16 best = the faster of SDPA / mma native16.\n")
    P("| T | native16 (measured) | TQ4 best | native16 best | TQ4 best / native16 best |")
    P("|---|---|---|---|---|")
    for T, dd in PICK_BASELINE["decode_off_tps"].items():
        fixed = 1e3 / dd - LAYERS * g("1", "native16")(T)
        tq = 1e3 / (fixed + LAYERS * gmin("1", ("mq_best", "mma_tq4"))(T))
        n16 = 1e3 / (fixed + LAYERS * gmin("1", ("native16", "mma_n16"))(T))
        P(f"| {T} | {dd:.2f} | {tq:.2f} ({tq / dd:.2f}×) | {n16:.2f} ({n16 / dd:.2f}×) | {tq / n16:.2f}× |")


if __name__ == "__main__":
    main()
