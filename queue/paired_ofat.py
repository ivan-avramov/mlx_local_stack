"""Generic paired OFAT read for two arms that `compare` REFUSES by design (draft state, reasoning_effort, moe_expand):
per-item plus-status from the EvalPlus results file (hep/mbpp) or the reasoning grader (math500), strict = pass AND converged,
paired two-stage bootstrap on acc and acc_strict (m1.suffix_ofat.accuracy, TOST ±5pp), tokens-per-task ratio with the M21b
paired item/draw bootstrap (k3_analysis.paired_ratio_boot arithmetic), runaway counts, Σ wall. Run from the benchmark dir with PYTHONPATH=.
  python paired_ofat.py --bench humanevalplus --a MODEL_A TUNE_A --b MODEL_B TUNE_B [--json OUT]"""
import argparse, json, random, statistics, sys
from pathlib import Path
from bench import grade, stats, extract
from bench.grade import _math_eq
from m1 import suffix_ofat
REPO = Path(__file__).resolve().parents[0]
def load_arm(model, bench, tune):
    rows = grade._rows(model, bench, tune=tune)
    d = Path("results") / model
    by_id = {}
    for r in rows: by_id.setdefault(r["id"], {})[r.get("sample", 0)] = r
    acc, strict, tokens, wall, nonconv = {}, {}, {}, {}, 0
    if bench in ("humanevalplus", "mbppplus"):
        evp = d / f"{bench}.{tune}_samples_eval_results.json"; rowsp = d / f"{bench}.{tune}.jsonl"
        if evp.stat().st_mtime < rowsp.stat().st_mtime: print(f"WARNING: {evp.name} OLDER than rows -> stale grade", file=sys.stderr)
        ev = json.loads(evp.read_text())["eval"]
        for tid, smps in by_id.items():
            order = sorted(s for s, r in smps.items() if not r.get("error")); res = ev.get(tid) or []; res = res if isinstance(res, list) else [res]
            for s, r in sorted(smps.items()):
                ok = (not r.get("error")) and order.index(s) < len(res) and res[order.index(s)].get("plus_status") == "pass"
                c = r.get("converged") is not False and not r.get("error"); nonconv += (not c)
                acc.setdefault(tid, []).append(float(ok)); strict.setdefault(tid, []).append(float(ok and c))
                tokens.setdefault(tid, []).append(float(r.get("completion_tokens") or 0)); wall.setdefault(tid, []).append(float(r.get("wall_s") or 0))
    else:
        for tid, smps in by_id.items():
            for s, r in sorted(smps.items()):
                ok = (not r.get("error")) and _math_eq(extract.extract_boxed(r.get("content", "")), r.get("answer_gold"))
                c = bool(r.get("converged")) and not r.get("error"); nonconv += (not c)
                acc.setdefault(tid, []).append(float(ok)); strict.setdefault(tid, []).append(float(ok and c))
                tokens.setdefault(tid, []).append(float(r.get("completion_tokens") or 0)); wall.setdefault(tid, []).append(float(r.get("wall_s") or 0))
    return dict(acc=acc, strict=strict, tokens=tokens, wall=wall, nonconv=nonconv, n_rows=len(rows))
def paired_ratio_boot(tok_a, tok_b, ids, iters=10000, seed=0):
    rng = random.Random(seed); n = len(ids)
    def stat(sel):
        a = sum(statistics.mean(x) for x, _ in sel); b = sum(statistics.mean(y) for _, y in sel); return a / b if b else float("nan")
    obs = stat([(tok_a[i], tok_b[i]) for i in ids]); reps = []
    for _ in range(iters):
        sel = []
        for _ in range(n):
            i = ids[rng.randrange(n)]; ka, kb = len(tok_a[i]), len(tok_b[i])
            sel.append(([tok_a[i][rng.randrange(ka)] for _ in range(ka)], [tok_b[i][rng.randrange(kb)] for _ in range(kb)]))
        reps.append(stat(sel))
    reps.sort(); return obs, stats._percentile(reps, 0.025), stats._percentile(reps, 0.975)
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--bench", required=True); ap.add_argument("--a", nargs=2, required=True); ap.add_argument("--b", nargs=2, required=True)
    ap.add_argument("--json", default=None); ap.add_argument("--iters", type=int, default=10000); a = ap.parse_args()
    A = load_arm(a.a[0], a.bench, a.a[1]); B = load_arm(a.b[0], a.bench, a.b[1])
    ids = sorted(set(A["acc"]) & set(B["acc"])); out = {"bench": a.bench, "a": a.a, "b": a.b, "n_items": len(ids), "rows": [A["n_rows"], B["n_rows"]],
                                                    "nonconv": [A["nonconv"], B["nonconv"]], "wall_h": [round(sum(map(sum, A["wall"].values()))/3600, 2), round(sum(map(sum, B["wall"].values()))/3600, 2)]}
    if len(ids) != len(A["acc"]) or len(ids) != len(B["acc"]): out["WARN"] = f"item sets differ: {len(A['acc'])} vs {len(B['acc'])}, shared {len(ids)}"
    for key in ("acc", "strict"):
        pa = {i: A[key][i] for i in ids}; pb = {i: B[key][i] for i in ids}
        r = suffix_ofat.accuracy(pa, pb, iters=a.iters, seed=0, margin=0.05)
        r["a"] = sum(statistics.mean(v) for v in pa.values()) / len(ids); r["b"] = sum(statistics.mean(v) for v in pb.values()) / len(ids)
        disc = [(i, statistics.mean(pa[i]), statistics.mean(pb[i])) for i in ids if statistics.mean(pa[i]) != statistics.mean(pb[i])]
        r["a_wins"] = sum(1 for _, x, y in disc if x > y); r["b_wins"] = sum(1 for _, x, y in disc if x < y); r["a_only"] = [i for i, x, y in disc if x > y and y == 0][:12]; r["b_only"] = [i for i, x, y in disc if y > x and x == 0][:12]
        out[key] = r
    obs, lo, hi = paired_ratio_boot(A["tokens"], B["tokens"], ids, iters=a.iters)
    out["tokens_ratio_a_over_b"] = {"point": round(obs, 3), "lo": round(lo, 3), "hi": round(hi, 3), "mean_a": round(statistics.mean(statistics.mean(v) for v in A["tokens"].values())), "mean_b": round(statistics.mean(statistics.mean(v) for v in B["tokens"].values()))}
    if a.json: json.dump(out, open(a.json, "w"), indent=2, default=str)
    for key in ("acc", "strict"):
        r = out[key]; print(f"{a.bench} {key}: A {r['a']*100:.1f} vs B {r['b']*100:.1f}  delta {(r.get('delta') or 0)*100:+.1f}pp CI [{(r.get('lo') or 0)*100:+.1f}, {(r.get('hi') or 0)*100:+.1f}] verdict={r.get('verdict')} discordant {r['a_wins']}:{r['b_wins']} n={len(ids)}")
    t = out["tokens_ratio_a_over_b"]; print(f"{a.bench} tokens/task A/B {t['point']} CI [{t['lo']}, {t['hi']}] (means {t['mean_a']} vs {t['mean_b']}); nonconv {out['nonconv']}; wall_h {out['wall_h']}")
if __name__ == "__main__": main()
