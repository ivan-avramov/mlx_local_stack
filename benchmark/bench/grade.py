"""Mechanical grading. No model calls. Run anytime, unsupervised.

Reasoning (aime/math500/gpqa): extract answer, exact/equivalence match — pure, in-process.
Coding (humanevalplus/mbppplus): shell out to the official `evalplus` evaluator on the
saved completions. (livecodebench: see grade_lcb — needs lcb_runner.)
"""
import json
import subprocess
import sys

from . import benchmarks, convergence, extract, generate


def _rows(model, bench):
    p = generate.result_path(model, bench)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


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
        items.append({"id": r["id"], "pred": pred, "gold": gold, "ok": ok})
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
    our = {r["id"]: extract.extract_code(r.get("content", "")) for r in rows if r.get("id")}
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
    with spath.open("w", encoding="utf-8") as f:                 # pad subset -> full set
        for tid in ids:
            f.write(json.dumps({"task_id": tid, "solution": our.get(tid, _PAD_SOLUTION)}) + "\n")
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
    base = plus = n = 0
    for tid in our:                                               # subset only; padding ignored
        res = ev.get(tid)
        if not res:
            continue
        r0 = res[0] if isinstance(res, list) else res
        n += 1
        base += 1 if r0.get("base_status") == "pass" else 0
        plus += 1 if r0.get("plus_status") == "pass" else 0
    if n == 0:
        return {"benchmark": name, "model": model, "n": 0, "acc": None,
                "note": "no subset task_ids found in evalplus results"}
    return {"benchmark": name, "model": model, "n": n, "acc": round(plus / n, 4),
            "pass@1_base": round(base / n, 4), "pass@1_plus": round(plus / n, 4)}


def _lcb_eval_inputs(rows, sample_by_id):
    """Build codegen_metrics inputs from saved generation rows + a {question_id: input_output}
    map. One sample per row whose id is in the map (rows from outside the pinned release are
    skipped). Returns (samples_list, generations_list, ids):
      samples_list[i]    = {"input_output": <json str>}
      generations_list[i]= [<extracted code string>]   (one completion per problem)
    """
    samples_list, generations_list, ids = [], [], []
    for r in rows:
        qid = r.get("id")
        io = sample_by_id.get(qid)
        if io is None:
            continue
        code = extract.extract_code(r.get("content", ""))
        samples_list.append({"input_output": io})
        generations_list.append([code])
        ids.append(qid)
    return samples_list, generations_list, ids


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
    samples_list, generations_list, ids = _lcb_eval_inputs(rows, sample_by_id)
    if not samples_list:
        return {"benchmark": name, "model": model, "n": 0, "acc": None,
                "note": f"no saved rows matched the pinned release {benchmarks.LCB_RELEASE}"}
    metrics, _results, _meta = codegen_metrics(samples_list, generations_list,
                                               k_list=[1], num_process_evaluate=8, timeout=6)
    pass1 = metrics.get("pass@1")
    acc = (pass1 / 100.0 if (pass1 is not None and pass1 > 1.0) else pass1)
    # Per-difficulty pass@1 (detail values are per-problem 0-1 fractions, index-aligned).
    detail = (metrics.get("detail") or {}).get("pass@1") or {}
    by_difficulty = _lcb_by_difficulty(ids, diff_by_id, detail)
    return {"benchmark": name, "model": model, "n": len(samples_list), "acc": acc,
            "pass@1": pass1, "release": benchmarks.LCB_RELEASE,
            "by_difficulty": by_difficulty,
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
    for r in rows:
        it = meta_by_id.get(r.get("id"))
        if it is None:
            continue
        inp = ev.InputExample(key=it["id"], instruction_id_list=it["meta"]["instruction_id_list"],
                              prompt=it["prompt"], kwargs=it["meta"]["kwargs"])
        p2r = {it["prompt"]: r.get("content", "")}
        try:
            s_out = ev.test_instruction_following_strict(inp, p2r)
            l_out = ev.test_instruction_following_loose(inp, p2r)
        except Exception:  # noqa: BLE001 — a single verifier blowing up shouldn't kill the batch
            continue
        strict_outs.append(s_out)   # append BOTH only after both succeed, so the
        loose_outs.append(l_out)    # strict/loose lists stay index-aligned
        graded += 1
    if not graded:
        return {"benchmark": name, "model": model, "n": 0, "acc": None,
                "note": "no rows matched the IFEval dataset"}
    agg = _ifeval_aggregate(strict_outs, loose_outs)
    return {"benchmark": name, "model": model, "n": graded, "acc": agg["prompt_strict"], **agg}


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
    # Convergence guard: attach per-run convergence audit. A run with any looped/truncated
    # item is INVALID — those items must not be silently scored (stale router? quant loop?).
    audit = convergence.audit(_rows(model, name))
    score["convergence_rate"] = audit["convergence_rate"]
    score["loop_ids"] = audit["loop_ids"]
    score["valid"] = audit["valid"]
    return score


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
