"""Mechanical 4-category re-score of an M18 BFCL run. ZERO model time: reads the persisted
result/ files and re-runs bfcl_eval's evaluator + our parse_scores, rewriting bfcl.json to
cover all four categories. Needed because the detached relaunch passed only the REMAINING
categories, so bfcl.json summarized 2 of 4 while all four raw files were on disk."""
import argparse, json, os, sys

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--categories", default="simple_python,multiple,parallel,parallel_multiple")
a = ap.parse_args()

out_root = os.path.abspath(a.out)
# MUST precede any bfcl_eval import — its path constants are computed once at first import.
os.environ["BFCL_PROJECT_ROOT"] = out_root
sys.path.insert(0, "$STACK_REPO/benchmark")

from bench import bfcl_handler as H                   # noqa: E402
from bench.bfcl_adapter import parse_scores           # noqa: E402
from bench.run_bfcl_fc import _apply_poison_guard, _write_result  # noqa: E402
from bfcl_eval.eval_checker.eval_runner import main as evaluation_main  # noqa: E402

cats = [c.strip() for c in a.categories.split(",") if c.strip()]
result_dir, score_dir = os.path.join(out_root, "result"), os.path.join(out_root, "score")

missing = [c for c in cats
           if not os.path.exists(os.path.join(result_dir, a.model, "non_live", f"BFCL_v4_{c}_result.json"))]
if missing:
    sys.exit(f"REFUSING: no raw result file for {missing} — this would score a partial run as whole.")

# Metadata-only: puts our registry name in bfcl_eval's MODEL_CONFIG_MAPPING so the
# evaluator recognizes it. No network call, no generation.
H.register_model(a.model)
evaluation_main([a.model], cats, result_dir, score_dir, partial_eval=False)
res = {"model": a.model, "axis": "tool_calling", "categories": cats,
       **parse_scores(score_dir, a.model, tuple(cats)), "skipped": False}
# O41 grader tripwire: a tree holding inference-error rows is REFUSED (acc null + ids),
# never summarized silently — even a pre-existing contaminated tree.
res = _apply_poison_guard(res, result_dir, a.model)
print("[rescore] " + json.dumps(res, indent=2))
_write_result(out_root, res)
