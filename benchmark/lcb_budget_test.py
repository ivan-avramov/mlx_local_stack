"""Does an adequate thinking budget let the model CONVERGE on hard LCB problems (vs hit
the budget)? Uses the official LCB prompt template + official sampling. Reports comp_tok,
convergence (finish<budget), repetition signature, wall time.

Loads problems from the lightweight prompt CACHE (no full dataset / test cases in RAM).

  PYTHONPATH=<clone> python benchmark/lcb_budget_test.py <model> <thinking_budget> <prob_id>...
"""
import json
import sys
import time
from collections import Counter

sys.path.insert(0, "benchmark")
from bench import benchmarks, client, model_params  # noqa: E402

M = sys.argv[1]
BUDGET = int(sys.argv[2])
PROB_IDS = sys.argv[3:] or ["abc358_e"]

# prompt-only cache: {id: {id, prompt, meta:{question_content, starter_code, platform}}}
with open(benchmarks._lcb_prompt_cache_path()) as f:
    items = {i["id"]: i for i in json.load(f)}


def official_msgs(qc, sc):
    SYS = ("You are an expert Python programmer. You will be given a question (problem "
           "specification) and will generate a correct Python program that matches the "
           "specification and passes all tests.")
    q = "### Question:\n" + qc + "\n\n"
    if sc:
        q += ("### Format: You will use the following starter code to write the solution to the "
              "problem and enclose your code within delimiters.\n```python\n" + sc + "\n```\n\n")
    else:
        q += ("### Format: Read the inputs from stdin solve the problem and write the answer to "
              "stdout (do not directly test on the sample inputs). Enclose your code within "
              "delimiters as follows. Ensure that when the python program runs, it reads the "
              "inputs, runs the algorithm and writes output to STDOUT.\n```python\n# YOUR CODE HERE\n```\n\n")
    q += "### Answer: (use the provided format with backticks)\n\n"
    return [{"role": "system", "content": SYS}, {"role": "user", "content": q}]


client.preload(M)


def repsig(t):
    L = [ln.strip() for ln in (t or "").splitlines() if len(ln.strip()) > 20]
    return (len(L), len(set(L)), max(Counter(L).values()) if L else 0)


for pid in PROB_IDS:
    it = items[pid]
    p = model_params.params_for(M, profile="official")
    p["thinking_budget"] = BUDGET
    p["max_tokens"] = BUDGET + 8192
    t0 = time.time()
    r = client.probe(M, official_msgs(it["meta"]["question_content"], it["meta"]["starter_code"]),
                     p, timeout=7200)
    rs = r.get("reasoning") or ""
    tot, uniq, mx = repsig(rs)
    ct = r["completion_tokens"] or 0
    status = "HIT-BUDGET" if ct >= BUDGET else "CONVERGED"
    print("[%s budget=%s] comp_tok=%s finish=%s %s wall=%ss | lines tot=%s uniq=%s maxrepeat=%s" % (
        pid, BUDGET, ct, r["finish_reason"], status, round(time.time() - t0), tot, uniq, mx), flush=True)
print("BUDGET_TEST_DONE", flush=True)
