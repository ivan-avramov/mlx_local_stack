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


def grade_lcb(name, model):
    rows = [r for r in _rows(model, name) if not r.get("error")]
    try:
        from lcb_runner.evaluation import codegen_metrics  # noqa: F401
    except Exception as e:  # noqa: BLE001
        return {"benchmark": name, "model": model, "n": len(rows), "acc": None,
                "note": f"lcb_runner not available ({e}); see benchmark/README.md"}
    # Wiring validated once lcb_runner is installed; see README "LiveCodeBench" section.
    return {"benchmark": name, "model": model, "n": len(rows), "acc": None,
            "note": "lcb grading wiring pending package install — see README"}


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
