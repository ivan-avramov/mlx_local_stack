"""Mechanical grading. No model calls. Run anytime, unsupervised.

Reasoning (aime/math500/gpqa): extract answer, exact/equivalence match — pure, in-process.
Coding (humanevalplus/mbppplus): shell out to the official `evalplus` evaluator on the
saved completions. (livecodebench: see grade_lcb — needs lcb_runner.)
"""
import json
import random
import subprocess
import sys
import zlib

from . import benchmarks, convergence, extract, generate, rowschema, stats, traces

# ⚠️ WITHDRAWN as a GATE (AGENTS.md, 2026-08-11): unratified and unsound — conv% is quantized in n, a
# point estimate against a hard threshold fails 35-45% of the time by chance at a TRUE rate of 0.90,
# and on cost grounds it is ~10x too lenient. `conv_gate_pass` is still COMPUTED for backward
# compatibility with existing readers, but it is NOT presented as a verdict and must not rank.
# The ranking key is `acc_strict` at a MATCHED budget (operator ruling 2026-08-13).
CONV_GATE = 0.90

# Above this share of errored rows the run is a harness failure, not a measurement.
_MAX_ERROR_SHARE = 0.20


def _run_budget_config(model, bench):
    """(context_limit, max_tokens) for a run, from its manifest — the two numbers needed to work out
    the thinking budget that was ACTUALLY IN FORCE. Returns (None, None) when unknown.

    The server silently clamps `thinking_budget` to 0.8 * (max_kv_cache_size - prompt) whenever
    `max_tokens` doesn't fit the context (see `convergence.resolved_thinking_budget`), so grading
    against the DECLARED budget scores every forced `</think>` as a clean stop. Measured on the
    IFEval runs: 33 rows read as converged when they were externally truncated.
    """
    mp = generate.result_path(model, bench).with_suffix(".manifest.json")
    if not mp.exists():
        return None, None
    try:
        m = json.loads(mp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, None                 # graceful degrade: never crash the batch
    kv = m.get("kv") or {}
    sampling = m.get("sampling") or {}
    return kv.get("max_kv_cache_size"), sampling.get("max_tokens")


def _rows(model, bench):
    """All rows, migrated to the v2 view (a v1 row becomes sample 0), and annotated with the
    RESOLVED thinking budget so convergence is judged against the budget that was in force.

    This is the one seam every grader loads through, so annotating here makes conv%, nonconv_kinds
    and acc_strict correct for all of them at once.
    """
    p = generate.result_path(model, bench)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(rowschema.migrate(json.loads(line)))
        except json.JSONDecodeError:
            pass
    context_limit, max_tokens = _run_budget_config(model, bench)
    if context_limit and max_tokens:
        convergence.backfill_resolved_budget(
            out, context_limit=context_limit, max_tokens=max_tokens)
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
      pass_at_1_converged  correctness among CONVERGED items only — a DIAGNOSTIC that must NEVER
                           rank. It CONDITIONS on convergence, shrinking the denominator, so a model
                           that DNFs 99 of 100 tasks scores 100% on its one converged item
      acc_strict           ⭐ THE RANKING KEY at a MATCHED budget (operator ruling 2026-08-13): a
                           truncated draw scores 0 with the DENOMINATOR INTACT, so the 99-DNF model
                           scores 1%. Comparable only at an equal thinking_budget — `compare` refuses
                           otherwise (`_MUST_MATCH_SAMPLING`) — hence the budget travels with it in
                           `acc_strict_budget`
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


# evalplus hangs in two distinct ways, BOTH leaving a complete results file on disk:
#  (a) it prints results and never exits — so a long timeout burns wall-clock on finished work and
#      the old code then DISCARDED the computed result as TimeoutExpired;
#  (b) one sample's worker dies (observed: a rosetta `mmap_anonymous_rw` fault on Mbpp/255) and
#      evalplus waits forever for that one, having already evaluated the other 377.
# Measured 2026-08-14: a 19-dir batch wedged this way, container pinned at 0.00% CPU for 13 minutes
# while the grade process accumulated 5 seconds of CPU. 900s is well above a healthy run.
EVALPLUS_TIMEOUT_S = 900


def _container_name(model: str, bench: str) -> str:
    """Deterministic, docker-legal name so a wedged container can be killed by name."""
    import re as _re
    raw = f"evalplus-{model}-{bench}"
    return _re.sub(r"[^A-Za-z0-9_.-]", "-", raw)[:60]


def _kill_container(cname: str, runner) -> None:
    """Best-effort kill. subprocess.run's timeout kills the docker CLIENT, not the container, so a
    hung run otherwise leaks a ~4.5GB container (one was found up 7 hours)."""
    try:
        runner(["docker", "kill", cname], capture_output=True, text=True, timeout=60)
    except Exception:  # noqa: BLE001 — the container may already be gone; never mask the real error
        pass


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
    # NAMED so a wedged container can be killed. Measured: a run that hangs leaks a ~4.5GB
    # container (one was found up 7 hours), because `subprocess.run`'s timeout kills the local
    # docker CLIENT, not the container it started.
    cname = _container_name(model, name)
    cmd = ["docker", "run", "--rm", "--name", cname,
           "--platform", "linux/amd64", "-v", f"{sdir}:/work",
           image, "evalplus.evaluate", "--dataset", ds, "--samples", f"/work/{name}_samples.jsonl"]
    timed_out = None
    try:
        proc = runner(cmd, capture_output=True, text=True, timeout=EVALPLUS_TIMEOUT_S)
    except Exception as e:  # noqa: BLE001 — docker missing / timeout
        timed_out = f"{type(e).__name__}: {str(e)[:100]}"
        proc = None
        _kill_container(cname, runner)
        # DO NOT return yet. evalplus has two hang modes that both leave a COMPLETE results file:
        #  (a) it prints results and never exits, so subprocess.run raises TimeoutExpired on a run
        #      that already finished the work — the old code discarded a computed result;
        #  (b) one sample's worker dies (a rosetta mmap fault was observed on Mbpp/255) and evalplus
        #      waits forever for it, having already evaluated the other 377.
        # So fall through and read rpath; only report the timeout if there is genuinely no result.
    if not rpath.exists():
        if timed_out:
            return {"benchmark": name, "model": model, "n": len(our), "acc": None,
                    "note": f"evalplus docker timed out with no results ({timed_out}); "
                            f"container {cname} killed"}
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
    out = {"benchmark": name, "model": model, "n": n_items, "items": items,
           "acc": round(plus_hits / draws, 4),
           "pass@1_base": round(base_hits / draws, 4),
           "pass@1_plus": round(plus_hits / draws, 4)}
    if timed_out:
        # The number is real — evalplus wrote it — but the run did not exit cleanly, so say so
        # rather than presenting it as a clean grade.
        out["note"] = (f"results RECOVERED from a timed-out run ({timed_out}); container killed. "
                       f"evalplus had written {n_items} graded items before hanging.")
        out["timed_out"] = True
    return out


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
    on the saved completions, and reports pass@1 (0–1) overall AND per difficulty.

    The release is loaded through `_load_lcb_problems`, which tolerates the dataset CONFIG-NAME
    drift described there. `lcb_dataset_config` in the result records which alias resolved."""
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
        problems, lcb_cfg = _load_lcb_problems(benchmarks.LCB_RELEASE)
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
            # WHICH config alias resolved. Recorded because the dataset can only be read from cache
            # now (datasets>=5 dropped trust_remote_code), so a reader must be able to tell which
            # cached configuration produced a number without re-deriving it.
            "lcb_dataset_config": lcb_cfg,
            "by_difficulty": by_difficulty, "items": items,
            "matched": len(ids), "total_rows": len(rows)}


# LiveCodeBench dataset CONFIG-NAME aliases, tried in order.
#
# WHY THIS EXISTS. `livecodebench/code_generation_lite` is a SCRIPT-BASED dataset, and
# `datasets` >= 5 removed `trust_remote_code` entirely — so it can no longer be downloaded fresh at
# any version. What remains is the local cache, and the cache key includes the CONFIG NAME the
# caller used. The lcb_runner in use today calls `load_dataset(...)` with no name (=> "default"),
# while the cache on this box was written by an older lcb_runner that passed "release_latest", so a
# literal call fails with `Couldn't find cache ... Available configs: ['release_latest-...']` even
# though the correct release IS present. Measured 2026-08-15: the cached
# `release_latest-version_tag=release_v5` holds 880 problems and matches benchmarks.LCB_RELEASE.
#
# This was filed as a bug on 2026-07-06 ("blocks LCB pass@1 ... the jsonls persist, so pass@1 is
# re-gradable once the loader is fixed") and sat unfixed because it was mis-attributed to a missing
# lcb_runner. Both were true; the module was only the first of two blockers.
#
# ⚠️ CONSEQUENCE TO KNOW: every LCB number now depends on a cache blob that CANNOT be regenerated.
# Losing it makes LCB permanently ungradable — the same irreversibility class as the retired M2
# corpus. Archive the dataset cache alongside the results snapshots.
_LCB_CONFIG_ALIASES = ("release_latest", "default")


def _load_lcb_problems(release: str):
    """Load the pinned LCB release, tolerating config-name drift. Returns (problems, config_used).

    Raises RuntimeError naming every alias tried, so a failure is actionable rather than a bare
    KeyError from deep inside `datasets`.
    """
    # FIRST try the official loader. It is the documented path, it is what the pinned lcb_runner
    # supports, and it is the seam the existing grade_lcb tests patch — so the alias probing below
    # is strictly a FALLBACK for the cache-key drift, never a replacement.
    # Each import is scoped to the path that uses it: a combined top-of-function import would make a
    # module missing EITHER name raise ImportError and skip the fallback entirely.
    try:
        from lcb_runner.benchmarks.code_generation import load_code_generation_dataset
        return load_code_generation_dataset(release_version=release), "lcb_runner"
    except Exception:  # noqa: BLE001 — fall through to alias probing; failures reported below
        pass

    from datasets import load_dataset
    from lcb_runner.benchmarks.code_generation import CodeGenerationProblem
    tried = []
    for cfg in _LCB_CONFIG_ALIASES:
        try:
            ds = load_dataset("livecodebench/code_generation_lite", cfg,
                              split="test", version_tag=release)
            return [CodeGenerationProblem(**p) for p in ds], cfg
        except Exception as e:  # noqa: BLE001 — alias probing; the last failure is reported below
            tried.append(f"{cfg}: {type(e).__name__}: {str(e)[:60]}")
    raise RuntimeError(
        f"no LCB dataset config resolved for release {release!r}. Tried — " + " | ".join(tried))


def _load_ifeval_lib():
    """Lazy-import the vendored IFEval verifiers. Adds bench/vendor to sys.path so the
    package's absolute imports (`from instruction_following_eval import ...`) resolve, and
    ensures the nltk tokenizer corpora the verifiers need. Raises if the deps
    (absl-py/langdetect/nltk/immutabledict) OR the corpora are absent — the caller degrades
    gracefully to acc:null + a note.

    THE CORPORA CHECK IS NOT BEST-EFFORT ANY MORE. It used to check only `tokenizers/punkt` and
    swallow every failure with `except Exception: pass`, annotated "verifiers that need it will fail
    closed". They do NOT fail closed: they raise per item, inside grade_ifeval's loop, where a bare
    `continue` dropped them. Measured 2026-08-13 on the live run: modern nltk needs `punkt_tab`,
    which was missing, so 8 of 38 completions (21%) were silently dropped — and the excluded items
    were HARDER than average, moving acc from 93.3% (n=30) to 90.2% (n=41) once fixed. A biased 79%
    subset reported as a clean number is worse than no number, so this now raises.
    """
    import os
    vendor = os.path.join(os.path.dirname(__file__), "vendor")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    from instruction_following_eval import evaluation_lib  # noqa: E402 — heavy optional deps
    _ensure_nltk_corpora()
    _ensure_langdetect_determinism()
    return evaluation_lib


def _ensure_langdetect_determinism() -> None:
    """Seed langdetect, or the SAME rows grade to DIFFERENT scores.

    MEASURED 2026-08-14 — three re-grades of the identical 148
    `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` ifeval rows returned `acc` 0.8986 / 0.8986 / 0.8919 and
    `acc_strict` 0.8514 / 0.8514 / 0.8446: exactly one item flipping, while
    `Ornith-1.0-35B-mlx-uniform-4bit`'s 541 rows were stable (so it is item-specific, not global).

    MECHANISM: three verifiers call `langdetect.detect()` — `instructions.py` `response_language`,
    `english_capital`, `english_lowercase` — and langdetect's `Detector` seeds its RNG from
    `DetectorFactory.seed`, which defaults to None, i.e. it SAMPLES RANDOMLY. Nothing in this repo set
    it. Short or ambiguous responses are where it wobbles.

    WHY IT MATTERS MORE THAN 0.7pp: a grader that returns a different number for identical rows makes
    every published figure depend on which grading run someone happened to read, which is exactly how
    "89.9% vs 89.9%, exactly +0.0pp" got recorded as an exact tie. The `equivalent` verdict itself
    survives (the wobble is far inside the ±5pp TOST margin) — reproducibility is the casualty.

    Set at the seam every ifeval grade loads through, so no caller can forget it. Re-grading is free.
    """
    import langdetect
    langdetect.DetectorFactory.seed = 0


def _stable_item_seed(item_id) -> int:
    """A per-item RNG seed that is stable ACROSS PROCESSES.

    NOT builtin `hash()`: it is salted by PYTHONHASHSEED for str, so it differs run to run — which is
    the very failure mode being fixed here.
    """
    return zlib.crc32(str(item_id).encode())


# `punkt_tab` is the one that actually bit: nltk >= 3.8.2 looks for it, and having `punkt` alone
# satisfied the old check while every sentence-tokenizing verifier still failed at use time.
_NLTK_REQUIRED = ("tokenizers/punkt", "tokenizers/punkt_tab")


def _ensure_nltk_corpora(required=_NLTK_REQUIRED) -> None:
    """Verify (downloading once if needed) every nltk resource the IFEval verifiers require.

    Raises LookupError naming the resource AND the command to fix it, so the failure is actionable
    and whole-bench rather than a per-item silent drop.
    """
    import nltk
    missing = []
    for res in required:
        try:
            nltk.data.find(res)
            continue
        except LookupError:
            pass
        pkg = res.split("/")[-1]
        try:
            nltk.download(pkg, quiet=True)
            nltk.data.find(res)
        except Exception:  # noqa: BLE001 — offline, or the package name moved
            missing.append(pkg)
    if missing:
        raise LookupError(
            f"nltk corpora missing and not downloadable: {', '.join(missing)}. "
            f"IFEval's sentence-tokenizing verifiers need them, and without them ~20% of items "
            f"fail individually and would be dropped from the denominator, BIASING acc upward. "
            f"Fix: python -c \"import nltk; [nltk.download(p) for p in "
            f"['punkt','punkt_tab','averaged_perceptron_tagger','averaged_perceptron_tagger_eng']]\"")


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
    # Per-item scores so the shared post-processor can compute acc_strict — THE RANKING KEY — plus a
    # CI and an MDE. The score is prompt-level strict (follow_all_instructions), so acc derived from
    # these is IDENTICAL to prompt_strict; this adds capability without moving an existing number.
    items = []
    for r in rows:
        it = meta_by_id.get(r.get("id"))
        if it is None:
            unmatched += 1
            continue
        inp = ev.InputExample(key=it["id"], instruction_id_list=it["meta"]["instruction_id_list"],
                              prompt=it["prompt"], kwargs=it["meta"]["kwargs"])
        p2r = {it["prompt"]: r.get("content", "")}
        # RESEED PER ITEM, not once per batch. 24 sites in the vendored instructions.py fabricate an
        # ABSENT kwarg with random.choice/random.randint (e.g. :1350 letter_frequency), so for those
        # items the criterion being checked is invented at grade time from the global RNG. Measured
        # 2026-08-14 on Ornith-1.0-35B-mlx-uniform-4bit/ifeval: 1 of 541 verdicts (0.2%) flipped with
        # the RNG state, moving acc over 90.02–90.20% (0.18pp) across 8 seeds — immaterial to any
        # verdict, but it meant the grader could not reproduce its own number.
        # PER ITEM rather than once per run, because a single batch seed leaves each verdict dependent
        # on how many draws preceded it: a resume, a different --limit or a reordered queue would then
        # silently change verdicts. Keyed on the item id, so it is also identical across models.
        random.seed(_stable_item_seed(r.get("id")))
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
        items.append({"id": r.get("id"), "sample": r.get("sample", 0),
                      "score": float(bool(s_out.follow_all_instructions))})
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
           "items": items,
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
            s = grade(b, model)
            scores.append(s)
            _write_pair_score(model, b, s)
    root = generate.results_root()          # NOT a second hardcoded literal — one seam (see
    root.mkdir(parents=True, exist_ok=True)  # generate.results_root)
    (root / "scores.json").write_text(
        json.dumps([{k: v for k, v in s.items() if k != "items"} for s in scores], indent=2))
    return scores


def _write_pair_score(model, bench, score):
    """Persist a graded result BESIDE ITS ROWS, one file per (model, bench).

    `scores.json` holds only the pairs of the LAST `grade_all` call, so grading one model erases the
    record for every other. Measured 2026-08-14: a 68-cell re-grade across 17 model dirs was reduced
    to a single entry by the next single-arm grade. Those cells were not wrong, they were erased —
    and evalplus cells cost docker time to produce.

    One file per pair cannot be clobbered by an unrelated grade, and it is what lets
    `m1/scoreboard.py` show `acc_strict` — THE RANKING KEY — without having to run the graders
    itself (docker for evalplus, `lcb_runner` for LCB), which is why the scoreboard reads rows.

    `items` is dropped: it is per-draw, can be thousands of entries, and is already recoverable from
    the jsonl.

    ⚠️ A FAILED grade must never replace a good one. The clause above says an unrelated grade cannot
    clobber a pair — but nothing stopped a FAILED grade of the SAME pair from doing it. Measured
    2026-08-15: running `grade --benches humanevalplus,mbppplus` on a box WITHOUT docker returned
    acc=None for every pair and overwrote the real scores, destroying the whole n=100 three-model H2H
    (28 graded coding cells -> 7). It was recoverable only because the corpus is tracked in git.
    So: if the incoming score has no `acc` and the file on disk does, KEEP the file and say so.
    """
    try:
        p = generate.result_path(model, bench).with_suffix(".score.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        if score.get("acc") is None and p.exists():
            try:
                prev = json.loads(p.read_text())
            except (json.JSONDecodeError, OSError):
                prev = {}
            if prev.get("acc") is not None:
                print(f"  [score] REFUSING to overwrite {model}/{bench}: incoming grade FAILED "
                      f"({str(score.get('note'))[:60]}) — keeping acc={prev['acc']}", flush=True)
                return
        p.write_text(json.dumps({k: v for k, v in score.items() if k != "items"}, indent=2))
    except Exception as e:  # noqa: BLE001 — never fail a grade over its own bookkeeping
        print(f"  [score] could not persist {model}/{bench}: {type(e).__name__}: {str(e)[:60]}",
              flush=True)
