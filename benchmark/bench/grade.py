"""Mechanical grading. No model calls. Run anytime, unsupervised.

Reasoning (aime/math500/gpqa): extract answer, exact/equivalence match — pure, in-process.
Coding (humanevalplus/mbppplus): shell out to the official `evalplus` evaluator on the
saved completions. (livecodebench: see grade_lcb — needs lcb_runner.)
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from . import benchmarks, extract, generate


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


def grade_evalplus(name, model):
    ds = "humaneval" if name == "humanevalplus" else "mbpp"
    rows = [r for r in _rows(model, name) if not r.get("error")]
    samples = [{"task_id": r["id"], "solution": extract.extract_code(r.get("content", ""))} for r in rows]
    if not samples:
        return {"benchmark": name, "model": model, "n": 0, "acc": None, "note": "no completions"}
    sdir = generate.result_path(model, name).parent
    spath = sdir / f"{name}_samples.jsonl"
    spath.write_text("\n".join(json.dumps(s) for s in samples), encoding="utf-8")
    try:
        proc = subprocess.run([sys.executable, "-m", "evalplus.evaluate",
                               "--dataset", ds, "--samples", str(spath)],
                              capture_output=True, text=True, timeout=3600)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return {"benchmark": name, "model": model, "n": len(samples), "acc": None,
                "note": f"evalplus unavailable/failed: {e}. pip install -r benchmark/requirements.txt"}
    out = proc.stdout + proc.stderr
    # evalplus prints lines like 'humaneval+ (base+extra)\npass@1: 0.640'
    m = re.findall(r"pass@1:\s*([0-9.]+)", out)
    base = float(m[0]) if m else None
    plus = float(m[-1]) if len(m) > 1 else base
    return {"benchmark": name, "model": model, "n": len(samples),
            "acc": plus, "pass@1_base": base, "pass@1_plus": plus, "raw": out[-400:]}


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


def grade_lcb(name, model):
    """Grade LiveCodeBench via the official lcb_runner executor (lazy, graceful-degrade).
    Re-loads the PINNED release to recover per-problem test cases, runs codegen_metrics
    on the saved completions, and reports pass@1 normalized to a 0–1 fraction."""
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
        for p in problems:
            qid = getattr(p, "question_id", None)
            if qid is not None:
                sample_by_id[qid] = p.get_evaluation_sample()["input_output"]
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
    return {"benchmark": name, "model": model, "n": len(samples_list), "acc": acc,
            "pass@1": pass1, "release": benchmarks.LCB_RELEASE,
            "matched": len(ids), "total_rows": len(rows)}


def grade(name, model):
    kind = benchmarks.SPECS[name]["kind"]
    if kind == "reasoning":
        return grade_reasoning(name, model)
    if name in ("humanevalplus", "mbppplus"):
        return grade_evalplus(name, model)
    if name == "livecodebench":
        return grade_lcb(name, model)
    raise ValueError(name)


def grade_all(models, benches):
    scores = []
    for model in models:
        for b in benches:
            scores.append(grade(b, model))
    Path("benchmark/results").mkdir(parents=True, exist_ok=True)
    Path("benchmark/results/scores.json").write_text(
        json.dumps([{k: v for k, v in s.items() if k != "items"} for s in scores], indent=2))
    return scores
