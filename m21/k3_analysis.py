"""M21b k=3 analysis (P28 rule): mean strict per arm + paired tokens-per-task ratio.

Reads the graded rows + evalplus per-sample results for both arms, rebuilds the per-(item, sample)
strict vector exactly as grade.py does (plus_status pass AND converged; error rows = 0), then:
  - mean strict per arm (cluster bootstrap over items, k draws per item)
  - paired strict delta (stats.paired_delta, TOST +/-5pp)
  - tokens per task: per-item MEAN over k samples; ratio = sum_i mixed_i / sum_i ref_i, paired
    two-stage bootstrap (items with replacement, then draws within item, both arms on the same item)
  - meander/budget-hit counts per arm; per-item table for the bimodal items.
Usage: .venv-bench/bin/python k3_analysis.py [--iters 10000] [--meander-tokens 32768]
"""
import argparse, json, random, statistics, sys
from pathlib import Path
REPO = Path("$STACK_REPO"); sys.path.insert(0, str(REPO / "benchmark"))
from bench import stats, grade  # noqa: E402

BENCH = "humanevalplus"  # overridden by --bench
ARMS = {"ref": ("Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit", "t0.6-r2"),
        "mixed": ("Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "t0.5")}


def load_arm(model, tune):
    rows = grade._rows(model, BENCH, tune=tune)
    d = REPO / "benchmark" / "results" / model
    evp = d / f"{BENCH}.{tune}_samples_eval_results.json"
    rowsp = d / f"{BENCH}.{tune}.jsonl"
    if evp.stat().st_mtime < rowsp.stat().st_mtime:
        print(f"WARNING: {evp.name} is OLDER than {rowsp.name} -> STALE grade; re-run grade first", file=sys.stderr)
    ev = json.loads(evp.read_text())["eval"]
    by_id = {}
    for r in rows:
        by_id.setdefault(r["id"], {})[r.get("sample", 0)] = r
    strict, tokens, conv, hit = {}, {}, {}, {}
    for tid, smps in by_id.items():
        order = sorted(s for s, r in smps.items() if not r.get("error"))
        res = ev.get(tid) or []
        res = res if isinstance(res, list) else [res]
        for s, r in sorted(smps.items()):
            if r.get("error"):
                ok = False
            else:
                idx = order.index(s)
                ok = idx < len(res) and res[idx].get("plus_status") == "pass"
            c = r.get("converged") is not False and not r.get("error")
            strict.setdefault(tid, []).append(float(ok and c))
            tokens.setdefault(tid, []).append(float(r.get("completion_tokens") or 0))
            conv.setdefault(tid, []).append(c)
            hit.setdefault(tid, []).append(r.get("finish_reason") != "stop" or not c)
    return strict, tokens, conv, hit, rows


def paired_ratio_boot(tok_a, tok_b, ids, iters, seed=0):
    rng = random.Random(seed)
    n = len(ids)
    def stat(sel):
        a = sum(statistics.mean(x) for x, _ in sel); b = sum(statistics.mean(y) for _, y in sel)
        return a / b if b else float("nan")
    obs = stat([(tok_a[i], tok_b[i]) for i in ids])
    reps = []
    for _ in range(iters):
        sel = []
        for _ in range(n):
            i = ids[rng.randrange(n)]
            ka, kb = len(tok_a[i]), len(tok_b[i])
            sel.append(([tok_a[i][rng.randrange(ka)] for _ in range(ka)],
                        [tok_b[i][rng.randrange(kb)] for _ in range(kb)]))
        reps.append(stat(sel))
    reps.sort()
    return obs, stats._percentile(reps, 0.025), stats._percentile(reps, 0.975)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--iters", type=int, default=10000)
    ap.add_argument("--meander-tokens", type=int, default=32768)
    ap.add_argument("--bench", default="humanevalplus"); a = ap.parse_args()
    global BENCH; BENCH = a.bench
    arms = {k: load_arm(*v) for k, v in ARMS.items()}
    ids = sorted(set(arms["ref"][0]) & set(arms["mixed"][0]))
    print(f"items paired: {len(ids)}  (ref {len(arms['ref'][0])}, mixed {len(arms['mixed'][0])})")
    for k, (strict, tokens, conv, hit, rows) in arms.items():
        ks = sorted({len(v) for v in strict.values()})
        b = stats.cluster_bootstrap({i: strict[i] for i in ids}, iters=a.iters)
        n_draw = sum(len(v) for v in strict.values())
        meand = sum(1 for v in tokens.values() for t in v if t >= a.meander_tokens)
        hits = sum(1 for v in hit.values() for h in v if h)
        tot = sum(statistics.mean(tokens[i]) for i in ids)
        per_draw = [t for i in ids for t in tokens[i]]
        print(f"[{k}] {ARMS[k][0]}@{ARMS[k][1]}: k={ks} draws={n_draw} "
              f"mean strict={b['point']:.4f} [{b['lo']:.3f},{b['hi']:.3f}] "
              f"(= {b['point']*len(ids):.2f} items of {len(ids)}) budget-hit/nonconv draws={hits} "
              f"meander(>= {a.meander_tokens}) draws={meand} "
              f"tokens: sum of item-means={tot:.0f} median draw={statistics.median(per_draw):.0f} "
              f"p90 draw={sorted(per_draw)[int(0.9*len(per_draw))-1]:.0f}")
    pd = stats.paired_delta({i: arms["mixed"][0][i] for i in ids}, {i: arms["ref"][0][i] for i in ids},
                            iters=a.iters)
    print("paired strict delta (mixed - ref):", {k: pd[k] for k in pd if k in
          ("delta", "point", "lo", "hi", "verdict", "equivalent", "discordant", "n_items", "mde")} or pd)
    obs, lo, hi = paired_ratio_boot(arms["mixed"][1], arms["ref"][1], ids, a.iters)
    print(f"paired tokens-per-task ratio mixed/ref = {obs:.3f}  95% CI [{lo:.3f}, {hi:.3f}]  "
          f"(CI excludes 1: {'YES' if hi < 1 or lo > 1 else 'NO'})")
    med_ratio = statistics.median(statistics.mean(arms['mixed'][1][i]) / max(statistics.mean(arms['ref'][1][i]), 1) for i in ids)
    print(f"median per-item ratio = {med_ratio:.3f}")
    # heavy-item table
    print("\nper-item (mean tokens, strict draws) where either arm mean >= 8192 or strict differs:")
    for i in ids:
        ma, mb = statistics.mean(arms["mixed"][1][i]), statistics.mean(arms["ref"][1][i])
        sa, sb = sum(arms["mixed"][0][i]), sum(arms["ref"][0][i])
        if max(ma, mb) >= 8192 or sa != sb:
            print(f"  {i:14s} mixed {ma:8.0f} {[int(t) for t in arms['mixed'][1][i]]} strict {sa:.0f}/{len(arms['mixed'][0][i])} | "
                  f"ref {mb:8.0f} {[int(t) for t in arms['ref'][1][i]]} strict {sb:.0f}/{len(arms['ref'][0][i])}")
    # P28 verdict
    ms = stats.pass_at_1({i: arms["mixed"][0][i] for i in ids}) * len(ids)
    rs = stats.pass_at_1({i: arms["ref"][0][i] for i in ids}) * len(ids)
    hits_m = sum(1 for v in arms["mixed"][3].values() for h in v if h); hits_r = sum(1 for v in arms["ref"][3].values() for h in v if h)
    me_m = sum(1 for v in arms["mixed"][1].values() for t in v if t >= a.meander_tokens); me_r = sum(1 for v in arms["ref"][1].values() for t in v if t >= a.meander_tokens)
    c1 = ms >= rs - 1; c2a = obs < 1 and hi < 1; c2b = (me_m + hits_m) < (me_r + hits_r) and ms >= rs
    print(f"\nP28: (1) mean strict items mixed {ms:.2f} >= ref {rs:.2f} - 1 -> {c1}; "
          f"(2a) ratio<1 with CI excluding 1 -> {c2a}; (2b) fewer meanders at equal accuracy "
          f"(mixed {me_m}+{hits_m} vs ref {me_r}+{hits_r}, strict {ms:.2f} vs {rs:.2f}) -> {c2b}; "
          f"RULE -> {'PICK MIXED' if c1 and (c2a or c2b) else 'KEEP 4-bit (rule not met)'}")


if __name__ == "__main__":
    main()
