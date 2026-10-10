import json, random, sys
sys.path.insert(0, "$STACK_REPO/benchmark")
from bench import compare as CMP, grade, generate, stats

REF = ("Qwen3.6-27B-Opus-Distill-OptiQ-4bit", "m37ref")
PAIRS = [
    ("Qwen3.8-27B-mlx-uniform-4bit", "m37med"),
    ("Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "m37med"),
    ("NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit", "c48t05"),
]
BENCH = "math500"

def rows_of(model, tune):
    return grade._rows(model, BENCH, tune=tune)

def by_id(rows):
    # k=1 per item in all these runs; keep first draw per id
    out = {}
    for r in rows:
        out.setdefault(r["id"], r)
    return out

def token_ratio_ci(a_map, b_map, ids, iters=10000, seed=0):
    """Paired bootstrap CI for mean(tokens_A)/mean(tokens_B) over shared ids (item-resample)."""
    a = [a_map[i]["completion_tokens"] for i in ids]
    b = [b_map[i]["completion_tokens"] for i in ids]
    n = len(ids)
    rng = random.Random(seed)
    reps = []
    for _ in range(iters):
        sa = sb = 0.0
        for _ in range(n):
            idx = rng.randrange(n)
            sa += a[idx]; sb += b[idx]
        reps.append(sa / sb)
    reps.sort()
    point = sum(a) / sum(b)
    lo = stats._percentile(reps, 0.025)
    hi = stats._percentile(reps, 0.975)
    return {"point": point, "lo": lo, "hi": hi, "mean_a": sum(a)/n, "mean_b": sum(b)/n}

def wall_ci(a_map, b_map, ids, iters=10000, seed=0):
    a = [a_map[i]["wall_s"] for i in ids]
    b = [b_map[i]["wall_s"] for i in ids]
    n = len(ids)
    return {"sum_a_h": sum(a)/3600.0, "sum_b_h": sum(b)/3600.0,
            "mean_a_s": sum(a)/n, "mean_b_s": sum(b)/n}

def runaway_stats(rows_map, ids, loop_ids):
    loop_set = set(loop_ids)
    n_run = sum(1 for i in ids if i in loop_set)
    wall_total = sum(rows_map[i]["wall_s"] for i in ids)
    wall_run = sum(rows_map[i]["wall_s"] for i in ids if i in loop_set)
    return {"runaway_rate": n_run / len(ids), "n_runaway": n_run,
            "wall_share": (wall_run / wall_total) if wall_total else None}

def discordant(pa, pb, ids):
    # binary win/loss per item (score 0/1, k=1)
    disc = []
    for i in ids:
        va = pa[i][0]; vb = pb[i][0]
        if va != vb:
            disc.append(i)
    return disc

def main():
    ref_model, ref_tune = REF
    ref_rows = rows_of(ref_model, ref_tune)
    ref_by_id = by_id(ref_rows)
    ref_score = grade.grade(BENCH, ref_model, tune=ref_tune)
    ref_loop_ids = ref_score["loop_ids"]

    results = {"reference": {"model": ref_model, "tune": ref_tune,
                              "acc": ref_score["acc"], "acc_strict": ref_score["acc_strict"],
                              "conv_rate": ref_score["conv_rate"],
                              "nonconv_kinds": ref_score["nonconv_kinds"],
                              "loop_ids": ref_loop_ids,
                              "n": ref_score["n"]},
               "pairs": []}

    for model, tune in PAIRS:
        label = f"{model}@{tune}"
        entry = {"model": model, "tune": tune}

        strict_cmp = CMP.compare(f"{ref_model}@{ref_tune}", label, BENCH, metric="acc_strict",
                                  margin=0.05, intersect=True)
        ord_cmp = CMP.compare(f"{ref_model}@{ref_tune}", label, BENCH, metric="acc",
                               margin=0.05, intersect=True)
        entry["acc_strict_compare"] = strict_cmp
        entry["acc_compare"] = ord_cmp
        entry["compare_refused"] = not strict_cmp.get("comparable", False)
        entry["refuse_reason"] = strict_cmp.get("reason")

        rows_b = rows_of(model, tune)
        b_by_id = by_id(rows_b)
        shared_ids = sorted(set(ref_by_id) & set(b_by_id))
        entry["n_shared"] = len(shared_ids)

        score_b = grade.grade(BENCH, model, tune=tune)
        entry["b_acc"] = score_b["acc"]
        entry["b_acc_strict"] = score_b["acc_strict"]
        entry["b_conv_rate"] = score_b["conv_rate"]
        entry["b_nonconv_kinds"] = score_b["nonconv_kinds"]
        entry["b_loop_ids"] = score_b["loop_ids"]

        # discordant counts on STRICT per-item vectors
        pa_strict = CMP._per_item(ref_score, strict=True)
        pb_strict = CMP._per_item(score_b, strict=True)
        pa_strict = {k: v for k, v in pa_strict.items() if k in shared_ids}
        pb_strict = {k: v for k, v in pb_strict.items() if k in shared_ids}
        disc = discordant(pa_strict, pb_strict, shared_ids)
        entry["discordant_strict_ids"] = disc
        entry["n_discordant_strict"] = len(disc)

        # ordinary (acc) discordant too
        pa_ord = CMP._per_item(ref_score, strict=False)
        pb_ord = CMP._per_item(score_b, strict=False)
        pa_ord = {k: v for k, v in pa_ord.items() if k in shared_ids}
        pb_ord = {k: v for k, v in pb_ord.items() if k in shared_ids}
        disc_ord = discordant(pa_ord, pb_ord, shared_ids)
        entry["discordant_acc_ids"] = disc_ord
        entry["n_discordant_acc"] = len(disc_ord)

        entry["mde_n100"] = stats.mde(len(shared_ids))

        # compare.py REFUSES when reasoning_effort differs (M24 ruling: a "medium" reasoning-
        # effort template is a different regime, not a rankable per-model tune axis). For any
        # such refused pair, fall back to stats.paired_delta directly on the SAME shared items
        # and SAME strict/ordinary vectors compare.py would have used -- but tag the result
        # DIAGNOSTIC ONLY, per M24: never a pooled ranking.
        if entry["compare_refused"]:
            entry["acc_strict_delta_fallback"] = stats.paired_delta(pa_strict, pb_strict,
                                                                     margin=0.05, seed=0)
            entry["acc_delta_fallback"] = stats.paired_delta(pa_ord, pb_ord, margin=0.05, seed=0)
            entry["fallback_diagnostic_only"] = (
                "reasoning_effort differs (None vs medium) -- M24 ruling: a different regime, "
                "like enable_thinking OFF; this delta is a (model x reasoning-effort-template) "
                "composite and is DIAGNOSTIC ONLY, never a pooled ranking")

        # token ratio (ref / other)
        entry["token_ratio_ref_over_other"] = token_ratio_ci(ref_by_id, b_by_id, shared_ids)

        # wall per 100 (already n=100 shared, so sum ~ per-100)
        entry["wall"] = wall_ci(ref_by_id, b_by_id, shared_ids)

        # runaway rate/share for ref and other, restricted to shared ids
        entry["ref_runaway"] = runaway_stats(ref_by_id, shared_ids, ref_loop_ids)
        entry["other_runaway"] = runaway_stats(b_by_id, shared_ids, score_b["loop_ids"])

        # exclusive-solve sets (ordinary correctness)
        ref_solved = {i for i in shared_ids if pa_ord[i][0] == 1.0}
        other_solved = {i for i in shared_ids if pb_ord[i][0] == 1.0}
        entry["ref_only_solved"] = sorted(ref_solved - other_solved)
        entry["other_only_solved"] = sorted(other_solved - ref_solved)

        results["pairs"].append(entry)

    # Joint 4-way exclusive-solve analysis (ordinary correctness) over the ids shared by ALL
    # four models -- distinct from the pairwise ref_only_solved/other_only_solved above.
    all_models = [REF] + PAIRS
    joint_per_item = {}
    for model, tune in all_models:
        sc = grade.grade(BENCH, model, tune=tune)
        joint_per_item[f"{model}@{tune}"] = CMP._per_item(sc, strict=False)
    joint_ids = sorted(set.intersection(*[set(v) for v in joint_per_item.values()]))
    joint_exclusive = {k: [] for k in joint_per_item}
    joint_all_wrong = []
    for i in joint_ids:
        solved_by = [k for k in joint_per_item if joint_per_item[k][i][0] == 1.0]
        if len(solved_by) == 1:
            joint_exclusive[solved_by[0]].append(i)
        if len(solved_by) == 0:
            joint_all_wrong.append(i)
    results["joint_4way"] = {"n_shared": len(joint_ids), "exclusive_solves": joint_exclusive,
                              "all_four_wrong": joint_all_wrong}

    # Item-level detail for C63's 6 non-converged items + its 1 ordinarily-wrong item, and
    # whether each of the other three solved it ordinarily.
    ref_rows_by_id = ref_by_id
    pa_ord_ref = CMP._per_item(ref_score, strict=False)
    ord_wrong_ref = [i for i in shared_ids if pa_ord_ref.get(i, [1.0])[0] == 0.0] if False else \
                    [i for i, v in pa_ord_ref.items() if v[0] == 0.0]
    item_detail = []
    for i in sorted(set(ref_loop_ids) | set(ord_wrong_ref)):
        r = ref_rows_by_id[i]
        row = {"id": i, "ref_ordinary_score": pa_ord_ref[i][0],
               "ref_completion_tokens": r["completion_tokens"], "ref_wall_s": r["wall_s"],
               "ref_finish_reason": r["finish_reason"], "ref_nonconv_kind": r.get("nonconv_kind")}
        for model, tune in PAIRS:
            sc = grade.grade(BENCH, model, tune=tune)
            pi = CMP._per_item(sc, strict=False)
            row[f"{model}_ordinary_score"] = pi.get(i, [None])[0]
        item_detail.append(row)
    results["c63_item_detail"] = item_detail

    with open("$STACK_REPO/benchmark/results/paired_c63_math500.json", "w") as f:
        json.dump(results, f, indent=2)

    # Console summary
    print("=== REFERENCE:", ref_model, ref_tune, "===")
    print("acc", ref_score["acc"], "acc_strict", ref_score["acc_strict"], "conv", ref_score["conv_rate"])
    print("loop_ids:", ref_loop_ids)
    for entry in results["pairs"]:
        print("\n---", entry["model"], entry["tune"], "---")
        sc = entry["acc_strict_compare"]
        print("strict delta:", sc.get("delta"), "warnings:", sc.get("warnings"))
        oc = entry["acc_compare"]
        print("ord delta:", oc.get("delta"))
        print("discordant strict:", entry["n_discordant_strict"], entry["discordant_strict_ids"])
        print("discordant acc:", entry["n_discordant_acc"], entry["discordant_acc_ids"])
        print("token ratio:", entry["token_ratio_ref_over_other"])
        print("wall:", entry["wall"])
        print("ref runaway:", entry["ref_runaway"], "other runaway:", entry["other_runaway"])
        print("ref only solved:", entry["ref_only_solved"])
        print("other only solved:", entry["other_only_solved"])

if __name__ == "__main__":
    main()
