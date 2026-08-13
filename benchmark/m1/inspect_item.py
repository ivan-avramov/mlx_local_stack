"""Inspect one generated row end-to-end: trace pathology AND whether it was actually SCORED correct.

Built to answer a specific question (2026-08-13): item 2849 emitted 52,503 tokens of a verbatim loop
but self-terminated under budget. Is its ANSWER usable? That decides whether a self-terminating loop is
a correctness problem (like a thinking-budget truncation, where the answer comes from incomplete work)
or purely a COST problem (the model did finish; it just wasted the tokens getting there).

  PYTHONPATH=benchmark .venv-bench/bin/python benchmark/m1/inspect_item.py <model> <bench> <id>
"""
import json
import sys

from bench import benchmarks, convergence, grade, paths, traces


def main(argv) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 2
    model, bench, item_id = argv[1], argv[2], argv[3]
    p = paths.default_results_root() / model / f"{bench}.jsonl"
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    match = [r for r in rows if str(r.get("id")) == str(item_id)]
    if not match:
        print(f"id {item_id} not found in {p}")
        return 1
    r = match[0]

    print(f"=== {model} / {bench} / id={item_id} ===")
    print(f"  finish_reason      : {r.get('finish_reason')}")
    print(f"  completion_tokens  : {r.get('completion_tokens')} / budget {r.get('thinking_budget')}"
          f"  ({100 * (r.get('completion_tokens') or 0) / (r.get('thinking_budget') or 1):.0f}% of budget)")
    print(f"  is_converged       : {convergence.is_converged(r)}   (ratified formula)")
    print(f"  nonconv_kind       : {r.get('nonconv_kind')}")
    print(f"  is_degenerate      : {traces.is_degenerate(r)}   (trace-based, additive)")
    print(f"  wall_s / decode_tps: {r.get('wall_s')} / {r.get('decode_tps')}")
    s = r.get("reasoning_stats") or {}
    print(f"  reasoning_stats    : lines={s.get('lines')} unique_line_ratio={s.get('unique_line_ratio')} "
          f"max_line_repeat={s.get('max_line_repeat')} ngram8_unique={s.get('ngram8_unique')}")
    print(f"  content_chars      : {len(r.get('content') or '')}")

    # THE question: is the ANSWER correct? Run the official verifiers on this one row.
    if bench.startswith("ifeval"):
        ev = grade._load_ifeval_lib()
        meta = {it["id"]: it for it in benchmarks.load("ifeval", None, 0)}
        it = meta.get(r.get("id"))
        if it is None:
            print("  SCORE: item not in the dataset")
            return 0
        inp = ev.InputExample(key=it["id"], instruction_id_list=it["meta"]["instruction_id_list"],
                              prompt=it["prompt"], kwargs=it["meta"]["kwargs"])
        p2r = {it["prompt"]: r.get("content", "")}
        st = ev.test_instruction_following_strict(inp, p2r)
        lo = ev.test_instruction_following_loose(inp, p2r)
        print(f"  instructions       : {it['meta']['instruction_id_list']}")
        print(f"  SCORE strict       : follow_all={st.follow_all_instructions} per={st.follow_instruction_list}")
        print(f"  SCORE loose        : follow_all={lo.follow_all_instructions} per={lo.follow_instruction_list}")
        print()
        print("  READ: a PASS here means the answer is usable despite the loop — so a self-terminating")
        print("        loop is a COST defect, not a correctness one. That is the opposite of a")
        print("        thinking-budget truncation, where the answer is produced from work we cut short.")
    print()
    print("--- content (first 400 chars) ---")
    print((r.get("content") or "")[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
