"""One-off A/B: does the OFFICIAL LCB prompt reduce Qwen's over-thinking on an AtCoder
(stdin) problem vs our restrictive prompt? Same model/params; thinking_budget capped at
16384 to bound time. Reports comp_tok + convergence + a repetition signature (loop vs
genuine). Run on the box with the model loaded:  PYTHONPATH=<clone> python benchmark/lcb_prompt_ab.py
"""
import sys
import time
from collections import Counter

sys.path.insert(0, "benchmark")
from bench import benchmarks, client, model_params  # noqa: E402
from lcb_runner.benchmarks.code_generation import load_code_generation_dataset  # noqa: E402

# argv[1] = served model name; argv[2:] = problem ids (default abc358_e)
M = sys.argv[1] if len(sys.argv) > 1 else "Qwen3.6-27B-UD-MLX-6bit-kv16"
PROB_IDS = sys.argv[2:] if len(sys.argv) > 2 else ["abc358_e"]

probs = {p.question_id: p for p in load_code_generation_dataset(release_version="release_v5")}


def our_msgs(prob):
    sc = ("\n\nStarter code:\n```python\n" + prob.starter_code + "\n```") if prob.starter_code else ""
    return benchmarks.build_messages("livecodebench", {"id": "x", "prompt": prob.question_content + sc})


def official_msgs(prob):
    SYS = ("You are an expert Python programmer. You will be given a question (problem "
           "specification) and will generate a correct Python program that matches the "
           "specification and passes all tests.")
    q = "### Question:\n" + prob.question_content + "\n\n"
    if prob.starter_code:
        q += ("### Format: You will use the following starter code to write the solution to the "
              "problem and enclose your code within delimiters.\n```python\n" + prob.starter_code + "\n```\n\n")
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


def run(tag, msgs):
    p = model_params.params_for(M, profile="official")
    p["thinking_budget"] = 16384
    p["max_tokens"] = 24576
    t0 = time.time()
    r = client.probe(M, msgs, p, timeout=3600)
    rs = r.get("reasoning") or ""
    tot, uniq, mx = repsig(rs)
    ct = r["completion_tokens"] or 0
    status = "HIT-16384" if ct >= 16384 else "CONVERGED"
    print("[%s | %s] comp_tok=%s finish=%s %s wall=%ss | lines tot=%s uniq=%s maxrepeat=%s" % (
        tag, M, ct, r["finish_reason"], status, round(time.time() - t0), tot, uniq, mx), flush=True)


for pid in PROB_IDS:
    prob = probs[pid]
    print("=== problem %s (starter_code=%s) ===" % (pid, bool(prob.starter_code)), flush=True)
    run("OUR_prompt:%s" % pid, our_msgs(prob))
    run("OFFICIAL_prompt:%s" % pid, official_msgs(prob))
print("AB_DONE", flush=True)
