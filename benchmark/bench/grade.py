"""Mechanical grading. No model calls. Run anytime, unsupervised.

Reasoning (aime/math500/gpqa): extract answer, exact/equivalence match — pure, in-process.
Coding (humanevalplus/mbppplus): shell out to the official `evalplus` evaluator on the
saved completions. (livecodebench: see grade_lcb — needs lcb_runner.)
"""
import json
import subprocess
import sys

from . import benchmarks, convergence, extract, generate, rowschema, stats, traces

# The pre-registered convergence gate. conv_rate >= this is a GATE; pass@1|converged RANKS within
# it. Not a tunable: it is declared here so a run cannot be reinterpreted after the fact.
CONV_GATE = 0.90

# Above this share of errored rows the run is a harness failure, not a measurement.
_MAX_ERROR_SHARE = 0.20


def _rows(model, bench):
    """All rows, migrated to the v2 view (a v1 row becomes sample 0)."""
    p = generate.result_path(model, bench)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(rowschema.migrate(json.loads(line)))
        except json.JSONDecodeError:
            pass
    return out


def _per_item(items):
    """[{id, sample, score}] -> {id: [score, ...]} for the stats layer. Items are the unit of
    analysis; pooling the N*k draws would understate variance by ignoring item clustering."""
    out = {}
    for i in items:
        out.setdefault(i["id"], []).append(float(i["score"]))
    return out


def _finalize(score: dict, rows: list) -> dict:
    """Attach the convergence VECTOR and the sampling statistics to any grader's output.

    One shared post-processor so no grader can forget a field — but it needs per-(item, sample)
    results, which is why every grader now returns `items`. Emits:

      acc                  correctness over generated items — UNCHANGED historical meaning
      conv_rate            share of generated items that self-terminated (legacy alias:
                           convergence_rate)
      conv_gate_pass       conv_rate >= CONV_GATE (the gate half of the decision rule)
      pass_at_1_converged  correctness among CONVERGED items only (the ranking half)
      acc_strict           truncation counted as failure — DERIVED deployment number, never the
                           ranking key, and always reported with the budget that produced it
                           because it rises monotonically with thinking_budget
      nonconv_kinds        mechanism breakdown (budget_hit / meander / degenerate_repetition / ...)
      samples / ci95 / reliability / mde
      n_contaminated       rows excluded from correctness as known stale-router artifacts
      valid                HARNESS-clean, not converged (see the module tests)
    """
    items = score.get("items") or []
    generated = [r for r in rows if not r.get("error")]
    errs = len(rows) - len(generated)

    audit = convergence.audit(rows)
    score["conv_rate"] = audit["convergence_rate"]
    score["convergence_rate"] = audit["convergence_rate"]   # legacy key: existing readers/tests
    score["all_converged"] = audit["valid"]
    score["loop_ids"] = audit["loop_ids"]
    score["conv_gate_pass"] = (audit["convergence_rate"] is not None
                               and audit["convergence_rate"] >= CONV_GATE)
    tsum = traces.summarize(rows)
    score["nonconv_kinds"] = tsum["kinds"]
    # EOS'd degenerate loops: rows the ratified convergence formula counts as CONVERGED whose trace
    # is a verbatim loop. Surfaced by COST share because the row count understates it badly — the
    # IFEval case was 1 row in 28 (4%) but 32% of wall-clock. This is also the class the
    # "runaway tax has nothing to charge" finding could not see, since that was measured on
    # budget-hits and max_tokens truncations only.
    score["n_degenerate_eosed"] = tsum["n_degenerate_eosed"]
    score["degenerate_eosed_ids"] = tsum["degenerate_eosed_ids"]
    score["degenerate_wall_share"] = tsum["degenerate_wall_share"]
    score["degenerate_token_share"] = tsum["degenerate_token_share"]

    conv_by_key = {rowschema.row_key(r): convergence.is_converged(r) for r in rows}
    budgets = {r.get("thinking_budget") for r in generated if r.get("thinking_budget")}
    score["acc_strict_budget"] = budgets.pop() if len(budgets) == 1 else sorted(budgets) or None

    scored = [i for i in items if not i.get("contaminated")]
    score["n_contaminated"] = len(items) - len(scored)

    per_item = _per_item(scored)
    # Where per-item scores exist they DEFINE acc (pass@1 over items) — unchanged.
    # But do NOT clobber an acc the grader computed itself when there are no per-item structures.
    # IFEval's headline is prompt-level strict and it populates no `items` list, so the previous
    # unconditional assignment replaced a real 0.75 with None: scores.json recorded
    # `"acc": null, "prompt_strict": 0.75` and the scoreboard column read "—", which is
    # indistinguishable from a grading failure and read as "IFEval is still broken".
    if per_item:
        score["acc"] = round(stats.pass_at_1(per_item), 4)
    else:
        score.setdefault("acc", None)

    # GRADED outcome, where the evaluator exposes per-test verdicts (LiveCodeBench does; evalplus
    # reports only a per-sample base/plus status, so it stays binary). Binary pass/fail throws away
    # most of what an execution-gated suite knows: the pass FRACTION is a continuous per-item score,
    # which cuts the items needed for a given resolution by 2-4x at zero extra model time. Reported
    # ALONGSIDE acc, never instead of it -- acc must stay the official, publishable pass@1.
    graded_items = [{**i, "score": i["score_graded"]} for i in scored if "score_graded" in i]
    if graded_items:
        gp = _per_item(graded_items)
        score["acc_graded"] = round(stats.pass_at_1(gp), 4)
        gboot = stats.cluster_bootstrap(gp, iters=2000, seed=0)
        score["ci95_graded"] = [round(gboot["lo"], 4), round(gboot["hi"], 4)]
    else:
        score["acc_graded"] = score["ci95_graded"] = None

    # strict: a truncated draw scores 0 regardless of correctness
    strict_items = [{**i, "score": (0.0 if conv_by_key.get((i["id"], i["sample"])) is False
                                    else i["score"])} for i in scored]
    strict_per_item = _per_item(strict_items)
    score["acc_strict"] = round(stats.pass_at_1(strict_per_item), 4) if strict_per_item else None

    conv_items = [i for i in scored if conv_by_key.get((i["id"], i["sample"])) is not False]
    conv_per_item = _per_item(conv_items)
    score["pass_at_1_converged"] = round(stats.pass_at_1(conv_per_item), 4) if conv_per_item else None
    score["n_converged_items"] = len(conv_per_item)

    ks = {len(v) for v in per_item.values()}
    score["samples"] = max(ks) if ks else 0
    if per_item:
        boot = stats.cluster_bootstrap(per_item, iters=2000, seed=0)
        score["ci95"] = [round(boot["lo"], 4), round(boot["hi"], 4)]
        score["mde"] = round(stats.mde(len(per_item)), 4)
    else:
        score["ci95"] = score["mde"] = None
    # Reliability needs k>1 AND binary draws. At k=1 there is nothing to be reliable about, and
    # reporting it anyway would read as "perfectly stable" for every model.
    score["reliability"] = None
    if score["samples"] > 1:
        try:
            score["reliability"] = stats.reliability(per_item)
        except ValueError:
            score["reliability"] = None      # graded (non-binary) scores: histogram undefined

    share = errs / len(rows) if rows else 0.0
    score["errors"] = errs
    score["valid"] = bool(rows) and share <= _MAX_ERROR_SHARE
    if not score["valid"]:
        score["note"] = (f"{errs}/{len(rows)} rows are harness errors "
                         f"({share:.0%} > {_MAX_ERROR_SHARE:.0%}) — fix the harness and re-run"
                         if rows else "no rows")
    return score


def _norm_math(s: str | None) -> str:
    if s is None:
        return ""
    s = s.strip().replace(" ", "").replace("\\left", "").replace("\\right", "")
    s = s.replace("\\!", "").rstrip(".")
    return s


def _math_eq(pred, gold) -> bool:
    if pred is None or gold is None:
        return False
    try:
        from math_verify import parse, verify
        return bool(verify(parse(gold), parse(pred)))
    except Exception:
        return _norm_math(pred) == _norm_math(gold)


def grade_reasoning(name, model):
    spec = benchmarks.SPECS[name]
    at = spec["answer_type"]
    rows = _rows(model, name)
    n = correct = errors = saturated = 0
    items = []
    for r in rows:
        if r.get("error"):
            errors += 1
            continue
        n += 1
        ct, tb = r.get("completion_tokens"), r.get("thinking_budget")
        if ct and tb and ct >= tb:  # thinking alone ~filled the budget => didn't self-converge
            saturated += 1
        content, gold = r.get("content", ""), r.get("answer_gold")
        if at == "int":
            pred = extract.extract_int(content)
            ok = pred is not None and gold is not None and str(pred) == str(int(float(gold)))
        elif at == "mc":
            pred = extract.extract_mc_letter(content, len(r.get("options") or "ABCD"))
            ok = pred is not None and pred == gold
        else:  # math
            pred = extract.extract_boxed(content)
            ok = _math_eq(pred, gold)
        correct += int(ok)
        items.append({"id": r["id"], "sample": r.get("sample", 0), "pred": pred, "gold": gold,
                      "ok": bool(ok), "score": float(bool(ok)),
                      "contaminated": r.get("contaminated")})
    return {"benchmark": name, "model": model, "n": n, "errors": errors,
            "correct": correct, "acc": round(correct / n, 4) if n else None,
            "budget_saturation": round(saturated / n, 3) if n else None, "items": items}


EVALPLUS_IMAGE = "ganler/evalplus:latest"
_PAD_SOLUTION = "def __pad__():\n    pass\n"


def _evalplus_all_ids(ds):
    """Full problem id list (evalplus's all-problems assertion requires every problem
    present). Lazy import so reasoning grading works without evalplus installed."""
    if ds == "humaneval":
        from evalplus.data import get_human_eval_plus
        return list(get_human_eval_plus().keys())
    from evalplus.data import get_mbpp_plus
    return list(get_mbpp_plus().keys())


def grade_evalplus(name, model, *, image=EVALPLUS_IMAGE, runner=subprocess.run, all_ids=None):
    """Grade humanevalplus/mbppplus with the OFFICIAL evalplus evaluator run IN DOCKER.
    Docker (Linux) is required because evalplus's reliability_guard calls resource.setrlimit
    in a way macOS rejects ('current limit exceeds maximum'); the container also isolates the
    executed code. evalplus asserts ALL problems are present, so we pad our subset to the full
    problem set with failing dummies, run the evaluator, then read pass@1 for ONLY our
    generated subset from the per-problem *_eval_results.json. Never raises; graceful-degrade
    with a note. `runner`/`all_ids` are injectable for tests."""
    ds = "humaneval" if name == "humanevalplus" else "mbpp"
    rows = [r for r in _rows(model, name) if not r.get("error")]
    # {task_id: {sample: code}} — NOT {task_id: code}. Keying by id alone let the LAST sample
    # win, so with k samples pass@1 was computed from 1/k of the data while the CI and the
    # reliability histogram were reported over k. Sample order is preserved because evalplus
    # returns per-task results as a LIST indexed by submission order.
    our: dict = {}
    for r in rows:
        if r.get("id"):
            our.setdefault(r["id"], {})[r.get("sample", 0)] = extract.extract_code(r.get("content", ""))
    if not our:
        return {"benchmark": name, "model": model, "n": 0, "acc": None, "note": "no completions"}
    try:
        ids = all_ids if all_ids is not None else _evalplus_all_ids(ds)
    except Exception as e:  # noqa: BLE001 — evalplus not importable for the id list
        return {"benchmark": name, "model": model, "n": len(our), "acc": None,
                "note": f"evalplus dataset unavailable for padding ({type(e).__name__}: {str(e)[:80]})"}
    # Absolute path: `docker run -v` treats a relative host path as a NAMED VOLUME (RESULTS is
    # relative), which would mount an empty /work and yield no results.
    sdir = generate.result_path(model, name).parent.resolve()
    sdir.mkdir(parents=True, exist_ok=True)
    spath = sdir / f"{name}_samples.jsonl"
    order: dict = {}                                              # task_id -> [sample, ...]
    with spath.open("w", encoding="utf-8") as f:                  # pad subset -> full set
        for tid in ids:
            if tid in our:
                order[tid] = sorted(our[tid])
                for smp in order[tid]:
                    f.write(json.dumps({"task_id": tid, "solution": our[tid][smp]}) + "\n")
            else:
                # Padding exists only to satisfy evalplus's all-problems assertion — ONE failing
                # dummy per absent task, never k of them.
                f.write(json.dumps({"task_id": tid, "solution": _PAD_SOLUTION}) + "\n")
    rpath = sdir / f"{name}_samples_eval_results.json"
    if rpath.exists():
        rpath.unlink()                                            # don't read a stale result
    cmd = ["docker", "run", "--rm", "--platform", "linux/amd64", "-v", f"{sdir}:/work",
           image, "evalplus.evaluate", "--dataset", ds, "--samples", f"/work/{name}_samples.jsonl"]
    try:
        proc = runner(cmd, capture_output=True, text=True, timeout=3600)
    except Exception as e:  # noqa: BLE001 — docker missing / timeout
        return {"benchmark": name, "model": model, "n": len(our), "acc": None,
                "note": f"evalplus docker failed: {type(e).__name__}: {str(e)[:100]}"}
    if not rpath.exists():
        err = (getattr(proc, "stderr", "") or "")[-160:]
        return {"benchmark": name, "model": model, "n": len(our), "acc": None,
                "note": f"evalplus produced no results (rc={getattr(proc, 'returncode', '?')}): {err}"}
    ev = json.loads(rpath.read_text()).get("eval", {})
    items, base_hits, plus_hits, draws = [], 0, 0, 0
    for tid in our:                                               # subset only; padding ignored
        res = ev.get(tid)
        if not res:
            continue
        res = res if isinstance(res, list) else [res]
        for idx, smp in enumerate(order.get(tid, [0])):
            r_i = res[idx] if idx < len(res) else {}
            base_ok = r_i.get("base_status") == "pass"
            plus_ok = r_i.get("plus_status") == "pass"
            base_hits += int(base_ok)
            plus_hits += int(plus_ok)
            draws += 1
            items.append({"id": tid, "sample": smp, "ok": plus_ok, "score": float(plus_ok),
                          "base_ok": base_ok})
    if not items:
        return {"benchmark": name, "model": model, "n": 0, "acc": None,
                "note": "no subset task_ids found in evalplus results"}
    n_items = len({i["id"] for i in items})
    return {"benchmark": name, "model": model, "n": n_items, "items": items,
            "acc": round(plus_hits / draws, 4),
            "pass@1_base": round(base_hits / draws, 4),
            "pass@1_plus": round(plus_hits / draws, 4)}


def _lcb_eval_inputs(rows, sample_by_id):
    """Build codegen_metrics inputs from saved generation rows + a {question_id: input_output}
    map. Rows from outside the pinned release are skipped. Returns
    (samples_list, generations_list, ids, sample_orders):
      samples_list[i]     = {"input_output": <json str>}
      generations_list[i] = [<code>, ...]   ALL k completions for problem i
      sample_orders[i]    = [<sample index>, ...] aligned with generations_list[i]

    One entry PER PROBLEM with its k generations grouped, not one entry per row: codegen_metrics
    takes a list of completions per problem and reports per-problem pass@1 over them. Emitting k
    separate problem entries would instead report each draw as its own problem, which silently
    turns an item-level metric into a draw-level one (and breaks the pairing with other graders).
    """
    grouped: dict = {}
    for r in rows:
        qid = r.get("id")
        if sample_by_id.get(qid) is None:
            continue
        grouped.setdefault(qid, {})[r.get("sample", 0)] = extract.extract_code(r.get("content", ""))
    samples_list, generations_list, ids, sample_orders = [], [], [], []
    for qid, by_sample in grouped.items():
        order = sorted(by_sample)
        samples_list.append({"input_output": sample_by_id[qid]})
        generations_list.append([by_sample[s] for s in order])
        ids.append(qid)
        sample_orders.append(order)
    return samples_list, generations_list, ids, sample_orders


def _lcb_test_passed(x):
    """Read ONE lcb_runner per-test verdict the way the evaluator itself reads it.

    lcb_runner encodes 1/True = pass, 0/False = wrong answer, **-1 = timeout**, **-2 = runtime or
    compile error** (`evaluation/testing_util.py` appends -2 on each error path;
    `compute_code_generation_metrics.py` uses `curr_res = [-2]` for a whole-problem failure).
    `bool(-1)` and `bool(-2)` are TRUE in Python, so scoring a verdict by truthiness counts every
    timeout and every crash as a PASS.

    That is not hypothetical: the 2026-08-11 re-grade published LCB `acc` 0.9333 / 0.9333 / 0.8667
    for the three candidates while the official evaluator's `pass@1` was 0.80 for ALL THREE — a
    phantom 6.7pp "differentiator" the campaign was sizing future arms against. The
    `by_difficulty` breakdown, which was quarantined over it, had been correct the whole time.
    """
    return x is True or x == 1


def _lcb_by_difficulty(ids, diff_by_id, detail_pass):
    """Group per-problem pass@1 (0-1, index-keyed as in metrics['detail']['pass@1'],
    index-aligned with ids) by the problem's Easy/Medium/Hard difficulty. LCB is calibrated
    across calibers, so the per-difficulty breakdown — not the overall number — is what
    separates clustered mid-tier / quantized candidates. Returns
    {DIFFICULTY: {'n': N, 'pass@1': mean}}."""
    from collections import defaultdict
    buckets = defaultdict(list)
    for idx, frac in detail_pass.items():
        i = int(idx)
        qid = ids[i] if 0 <= i < len(ids) else None
        buckets[diff_by_id.get(qid, "UNKNOWN")].append(frac)
    return {d: {"n": len(v), "pass@1": sum(v) / len(v)} for d, v in buckets.items()}


def grade_lcb(name, model):
    """Grade LiveCodeBench via the official lcb_runner executor (lazy, graceful-degrade).
    Re-loads the PINNED release to recover per-problem test cases, runs codegen_metrics
    on the saved completions, and reports pass@1 (0–1) overall AND per difficulty."""
    rows = [r for r in _rows(model, name) if not r.get("error")]
    if not rows:
        return {"benchmark": name, "model": model, "n": 0, "acc": None, "note": "no completions"}
    try:
        from lcb_runner.benchmarks.code_generation import load_code_generation_dataset
        from lcb_runner.evaluation import codegen_metrics
    except Exception as e:  # noqa: BLE001 — optional heavy dep
        return {"benchmark": name, "model": model, "n": len(rows), "acc": None,
                "note": f"lcb_runner not available ({type(e).__name__}: {str(e)[:80]}); see benchmark/README.md"}
    try:
        problems = load_code_generation_dataset(release_version=benchmarks.LCB_RELEASE)
        sample_by_id = {}
        diff_by_id = {}
        for p in problems:
            qid = getattr(p, "question_id", None)
            if qid is not None:
                sample_by_id[qid] = p.get_evaluation_sample()["input_output"]
                diff_by_id[qid] = str(getattr(p, "difficulty", "")).split(".")[-1].upper()
    except Exception as e:  # noqa: BLE001 — dataset/accessor drift on the installed version
        return {"benchmark": name, "model": model, "n": len(rows), "acc": None,
                "note": f"lcb dataset/sample load failed ({type(e).__name__}: {str(e)[:80]})"}
    samples_list, generations_list, ids, sample_orders = _lcb_eval_inputs(rows, sample_by_id)
    if not samples_list:
        return {"benchmark": name, "model": model, "n": 0, "acc": None,
                "note": f"no saved rows matched the pinned release {benchmarks.LCB_RELEASE}"}
    metrics, results, _meta = codegen_metrics(samples_list, generations_list,
                                              k_list=[1], num_process_evaluate=8, timeout=6)
    pass1 = metrics.get("pass@1")
    acc = (pass1 / 100.0 if (pass1 is not None and pass1 > 1.0) else pass1)
    # Per-difficulty pass@1 (detail values are per-problem 0-1 fractions, index-aligned).
    detail = (metrics.get("detail") or {}).get("pass@1") or {}
    by_difficulty = _lcb_by_difficulty(ids, diff_by_id, detail)
    # Per-(item, sample) results from codegen_metrics' per-problem, per-generation verdicts.
    # `results` is index-aligned with generations_list; each entry is the list of per-generation
    # outcomes (a list of per-test booleans, or a scalar). Degrade to the problem-level pass@1
    # fraction if the shape is unfamiliar, rather than guessing per-draw.
    items = []
    for idx, qid in enumerate(ids):
        per_gen = results.get(idx) if isinstance(results, dict) else (
            results[idx] if isinstance(results, list) and idx < len(results) else None)
        frac = detail.get(idx, detail.get(str(idx)))
        for j, smp in enumerate(sample_orders[idx]):
            ok, graded = None, None
            if isinstance(per_gen, list) and j < len(per_gen):
                v = per_gen[j]
                if isinstance(v, list) and v:
                    # Per-test-case verdicts. `ok` stays ALL-must-pass so `acc` remains the
                    # official pass@1 (comparable with published numbers); the pass FRACTION is
                    # reported separately as the graded outcome, which carries far more
                    # information per item and cuts the N needed for a given resolution 2-4x.
                    # Sentinels MUST go through _lcb_test_passed — a truthiness test scores
                    # timeouts (-1) and crashes (-2) as passes and inflates both numbers.
                    ok = all(_lcb_test_passed(x) for x in v)
                    graded = sum(1 for x in v if _lcb_test_passed(x)) / len(v)
                else:
                    ok = _lcb_test_passed(v)
            if ok is None:                       # unfamiliar shape: fall back to the problem mean
                # `frac` is a per-problem pass fraction, so a partial (0.5 at k>1) must not count
                # as a pass for a single draw — bool(0.5) would.
                ok = frac is not None and frac >= 1.0
            item = {"id": qid, "sample": smp, "ok": ok, "score": float(ok)}
            if graded is not None:
                item["score_graded"] = graded
            items.append(item)
    return {"benchmark": name, "model": model, "n": len(samples_list), "acc": acc,
            "pass@1": pass1, "release": benchmarks.LCB_RELEASE,
            "by_difficulty": by_difficulty, "items": items,
            "matched": len(ids), "total_rows": len(rows)}


def _load_ifeval_lib():
    """Lazy-import the vendored IFEval verifiers. Adds bench/vendor to sys.path so the
    package's absolute imports (`from instruction_following_eval import ...`) resolve, and
    best-effort ensures the nltk 'punkt' tokenizer the verifiers need. Raises if the deps
    (absl-py/langdetect/nltk/immutabledict) are absent — the caller degrades gracefully."""
    import os
    vendor = os.path.join(os.path.dirname(__file__), "vendor")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    from instruction_following_eval import evaluation_lib  # noqa: E402 — heavy optional deps
    try:
        import nltk
        try:
            nltk.data.find("tokenizers/punkt")
        except LookupError:
            nltk.download("punkt", quiet=True)
    except Exception:  # noqa: BLE001 — tokenizer is best-effort; verifiers that need it will fail closed
        pass
    return evaluation_lib


def _ifeval_aggregate(strict_outs, loose_outs) -> dict:
    """Prompt-level = fraction of prompts following ALL their instructions; instruction-level
    = fraction of individual instructions followed. Computed for strict and loose verdicts."""
    def prompt_acc(outs):
        return (sum(1 for o in outs if o.follow_all_instructions) / len(outs)) if outs else 0.0

    def inst_acc(outs):
        flat = [b for o in outs for b in o.follow_instruction_list]
        return (sum(1 for b in flat if b) / len(flat)) if flat else 0.0

    return {
        "prompt_strict": round(prompt_acc(strict_outs), 4),
        "inst_strict": round(inst_acc(strict_outs), 4),
        "prompt_loose": round(prompt_acc(loose_outs), 4),
        "inst_loose": round(inst_acc(loose_outs), 4),
    }


def grade_ifeval(name, model):
    """Grade IFEval with the vendored official verifiers (lazy, graceful-degrade). Re-loads
    the IFEval dataset to recover per-item instruction_id_list/kwargs, runs strict+loose, and
    aggregates. Headline acc = prompt-level strict."""
    rows = [r for r in _rows(model, name) if not r.get("error")]
    if not rows:
        return {"benchmark": name, "model": model, "n": 0, "acc": None, "note": "no completions"}
    try:
        ev = _load_ifeval_lib()
    except Exception as e:  # noqa: BLE001 — optional verifier deps
        return {"benchmark": name, "model": model, "n": len(rows), "acc": None,
                "note": f"ifeval verifiers unavailable ({type(e).__name__}: {str(e)[:80]}); "
                        f"install benchmark/requirements.txt where grade runs"}
    meta_by_id = {it["id"]: it for it in benchmarks.load("ifeval", None, 0)}
    strict_outs, loose_outs, graded = [], [], 0
    unmatched, skipped = 0, 0
    for r in rows:
        it = meta_by_id.get(r.get("id"))
        if it is None:
            unmatched += 1
            continue
        inp = ev.InputExample(key=it["id"], instruction_id_list=it["meta"]["instruction_id_list"],
                              prompt=it["prompt"], kwargs=it["meta"]["kwargs"])
        p2r = {it["prompt"]: r.get("content", "")}
        try:
            s_out = ev.test_instruction_following_strict(inp, p2r)
            l_out = ev.test_instruction_following_loose(inp, p2r)
        except Exception:  # noqa: BLE001 — a single verifier blowing up shouldn't kill the batch
            # COUNT it. A bare `continue` shrinks n invisibly, and n is the headline's denominator:
            # the 5-item smoke reported n=4 with no indication that an item had been dropped.
            skipped += 1
            continue
        strict_outs.append(s_out)   # append BOTH only after both succeed, so the
        loose_outs.append(l_out)    # strict/loose lists stay index-aligned
        graded += 1
    if not graded:
        # Distinguish the two ways this happens. "no rows matched the dataset" was reported for BOTH,
        # so a run whose verifiers all raised looked like an id-mismatch and would have been
        # misdiagnosed.
        why = (f"all {skipped} completions were dropped by verifier exceptions"
               if skipped else f"{unmatched} completions matched no dataset id")
        return {"benchmark": name, "model": model, "n": 0, "acc": None,
                "n_verifier_skipped": skipped, "n_unmatched": unmatched,
                "n_completions": len(rows),
                "note": f"nothing graded: {why}"}
    agg = _ifeval_aggregate(strict_outs, loose_outs)
    out = {"benchmark": name, "model": model, "n": graded, "acc": agg["prompt_strict"], **agg,
           "n_verifier_skipped": skipped, "n_unmatched": unmatched, "n_completions": len(rows)}
    if skipped or unmatched:
        out["note"] = (f"{len(rows)} completions -> n={graded} graded; "
                       f"{skipped} dropped by a verifier exception, {unmatched} not in the dataset")
    return out


def grade(name, model):
    kind = benchmarks.SPECS[name]["kind"]
    if kind == "reasoning":
        score = grade_reasoning(name, model)
    elif name in ("humanevalplus", "mbppplus"):
        score = grade_evalplus(name, model)
    elif name == "livecodebench":
        score = grade_lcb(name, model)
    elif name == "ifeval":
        score = grade_ifeval(name, model)
    else:
        raise ValueError(name)
    # The convergence VECTOR + sampling statistics, attached in ONE place so no grader can
    # forget a field. Replaces the old run-level INVALID flag: non-convergence is now a reported
    # outcome with a mechanism, not a voided run. See _finalize.
    return _finalize(score, _rows(model, name))


def grade_all(models, benches):
    scores = []
    for model in models:
        for b in benches:
            scores.append(grade(b, model))
    root = generate.results_root()          # NOT a second hardcoded literal — one seam (see
    root.mkdir(parents=True, exist_ok=True)  # generate.results_root)
    (root / "scores.json").write_text(
        json.dumps([{k: v for k, v in s.items() if k != "items"} for s in scores], indent=2))
    return scores
