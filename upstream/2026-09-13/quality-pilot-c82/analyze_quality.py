"""Analyze completed C82 quality artifacts only; no grading or model execution.

Run once to create quality-analysis.json; --check recomputes without writing.
"""
import argparse
import ast
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WORKDIR = ROOT.parents[1]
BENCHMARK = ROOT / "stack-validation/benchmark"
sys.path.insert(0, str(BENCHMARK))
from bench import convergence, stats
from bench.compare_predictor import _paired_ratio

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
MODES = ("native16", "uniform8")
AXES = ("math500", "humanevalplus", "mbppplus")
METRICS = ("wall_s", "completion_tokens", "decode_tps")
SELECTION_SHA = "02b30efc7bd6d3fd94628a53a5e1f69d7255ee5fa3e4d86060790fc00f4a39e7"
FROZEN_SHA = "240ebeb38bea29867cb0a7a43427f387df434b0ce349959d7a2d405d7e84eaa8"
IMAGE = "sha256:ff0ea20905962ccef0bcfc07f4ae0d389acdbafd4736c0b33eb51d350f048b43"
SEED, ITERATIONS = 82, 10000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def object_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def analyze():
    sources = {}
    watched = {}

    def record(path, expected=None):
        path = Path(path)
        require(path.is_file() and not path.is_symlink(), "missing/symlinked input: " + path.name)
        digest = sha(path)
        require(expected is None or digest == expected, "input hash differs: " + path.name)
        watched[path] = digest
        label = str(path).replace(str(WORKDIR), "$STACK_WORKDIR").replace(str(Path.home()), "$HOME")
        sources[label] = {"sha256": digest, "bytes": path.stat().st_size}
        return path

    def read(path, expected=None):
        return json.loads(record(path, expected).read_text())

    selection = read(HERE / "selection.json", SELECTION_SHA)
    frozen = read(HERE / "frozen.json", FROZEN_SHA)
    require(selection["decision"] == "C82" and selection["model"] == MODEL, "wrong selection")
    require(selection["states"] == list(MODES) and selection["approved_requests"] == 30, "wrong scope")
    groups = {group["axis"]: group for group in selection["groups"]}
    expected = {bench: {item["id"]: item["sampler_seed"] for item in groups[bench]["items"]}
                for bench in AXES}
    require(all(len(items) == 5 for items in expected.values()), "not five tasks per axis")
    require(len(frozen["requests"]) == 15, "wrong frozen request count")
    rows, scores, official, finals = {}, {}, {}, {}
    for mode in MODES:
        tag = f"m42c82-{mode}-20260913"
        grade_dir = HERE / "grades" / mode
        provenance = read(grade_dir / "grading-provenance.json")
        require(provenance["status"] == "complete" and provenance["image"] == IMAGE,
                "grading not complete under pinned evaluator")
        require(provenance["platform"] == "linux/arm64" and provenance["network"] == "none", "wrong evaluator environment")
        require(provenance["selection_sha256"] == SELECTION_SHA, "grading selection changed")
        final = read(HERE / f"finalized-{mode}.json", provenance["run_evidence_sha256"])
        finals[mode] = final
        require(final["status"] == "complete" and final["decision"] == "C82"
                and final["model"] == MODEL and final["mode"] == mode and final["tune"] == tag,
                "wrong completion evidence")
        summary = read(HERE / "runs" / mode / "summary.json", final["summary_sha256"])
        require(summary["status"] == "complete" and summary["completed"] == 15
                and summary["frozen_sha256"] == FROZEN_SHA, "incomplete generation")
        scored = read(grade_dir / "complete-scores.json")
        require(len(scored) == 3 and {s["benchmark"] for s in scored} == set(AXES), "incomplete grades")
        scores[mode] = {s["benchmark"]: s for s in scored}
        rows[mode], official[mode] = {}, {}
        for bench in AXES:
            path = grade_dir / MODEL / f"{bench}.{tag}.jsonl"
            digest = final["files"][path.name]
            require(provenance["source_inputs"][path.name] == digest, "grading/finalization hash disagreement")
            record(ROOT / "stack-validation/benchmark/results" / MODEL / path.name, digest)
            records = [json.loads(line) for line in record(path, digest).read_text().splitlines() if line]
            require(len(records) == 5 and len({r["id"] for r in records}) == 5
                    and {r["id"] for r in records} == set(expected[bench]), "row identities differ")
            manifest_path = path.with_suffix(".manifest.json")
            manifest = read(manifest_path, final["files"][manifest_path.name])
            require(manifest["sampling"] == final["sampling"] and manifest["model"] == MODEL
                    and manifest["tune"] == tag and manifest["runtime"]["draft_kind"] == "mtp", "manifest mismatch")
            for row in records:
                require(row["model"] == MODEL and row["bench"] == bench and row["sample"] == 0
                        and row["sampler_seed"] == expected[bench][row["id"]], "row draw identity differs")
                require(not row.get("error") and not row.get("recovery") and not row.get("contaminated"), "infrastructure row")
                require(row["resolved_thinking_budget"] == 81920
                        and row["converged"] is convergence.is_converged(row), "convergence mismatch")
                for metric in METRICS:
                    require(type(row[metric]) in (float, int) and math.isfinite(row[metric]) and row[metric] > 0,
                            "missing/invalid timing or token metric")
            rows[mode][bench] = {r["id"]: r for r in records}
            score = scores[mode][bench]
            require(score["n"] == 5 and not score.get("errors") and not score.get("timed_out"), "invalid score")
            require(len(score["items"]) == 5 and {(i["id"], i["sample"]) for i in score["items"]}
                    == {(item, 0) for item in expected[bench]}, "grade identity mismatch")
            if bench != "math500":
                ep = path.parent / f"{bench}.{tag}_samples_eval_results.json"
                require(sha(ep) in {job["result_sha256"] for job in provenance["containers"]}, "unverified evaluator output")
                ev = read(ep)["eval"]
                official[mode][bench] = {item: ev[item][0] for item in expected[bench]}
                for item in score["items"]:
                    record_ = official[mode][bench][item["id"]]
                    require(len(ev[item["id"]]) == 1 and all(record_[key] in ("pass", "fail", "timeout")
                            for key in ("base_status", "plus_status")), "incomplete official result")
                    passed = record_["base_status"] == record_["plus_status"] == "pass"
                    require(item["ok"] is passed, "canonical/official score disagreement")
            passed = sum(bool(i["ok"]) for i in score["items"])
            strict = sum(bool(i["ok"]) and rows[mode][bench][i["id"]]["converged"] for i in score["items"])
            require(score["acc"] == passed / 5 and score["acc_strict"] == strict / 5, "aggregate score differs")
        for index, entry in enumerate(frozen["requests"], 1):
            name = f"request-{index:02d}"
            path = record(HERE / "runs" / mode / name / "request.json", final["raw_requests"][name])
            require(path.read_text() == entry["wire"], "raw request not frozen paired payload")
            response = read(path.with_name("response.json"), final["raw_responses"][name])
            row = rows[mode][entry["bench"]][entry["id"]]
            message = response["choices"][0]["message"]
            require(hashlib.sha256((message.get("content") or "").encode()).hexdigest() == row["content_sha256"],
                    "answer hash differs from raw response")
    require(finals["native16"]["sampling"] == finals["uniform8"]["sampling"], "unpaired sampling")

    axes = {}
    for bench in AXES:
        grade_items = {mode: {item["id"]: item for item in scores[mode][bench]["items"]} for mode in MODES}
        paired = []
        for item in sorted(expected[bench]):
            pair = {"id": item, "sample": 0, "sampler_seed": expected[bench][item]}
            for mode in MODES:
                row = rows[mode][bench][item]
                pair[mode] = {"ordinary_pass": bool(grade_items[mode][item]["ok"]),
                              "strict_pass": bool(grade_items[mode][item]["ok"] and row["converged"]),
                              "converged": row["converged"], "nonconv_kind": row.get("nonconv_kind"),
                              "content_sha256": row["content_sha256"], "reasoning_sha256": row["reasoning_sha256"],
                              **{metric: row[metric] for metric in METRICS}}
            paired.append(pair)
        per_item = {mode: {p["id"]: [float(p[mode]["strict_pass"])] for p in paired} for mode in MODES}
        delta = stats.paired_delta(per_item["uniform8"], per_item["native16"], iters=ITERATIONS, seed=SEED)
        delta["raw_helper_verdict"] = delta.pop("verdict")
        axes[bench] = {
            "n_pairs": 5,
            **{mode: {key: scores[mode][bench][key] for key in ("n", "acc", "acc_strict", "conv_rate", "nonconv_kinds")}
               for mode in MODES},
            "uniform8_only_pass": [p["id"] for p in paired if p["uniform8"]["ordinary_pass"] and not p["native16"]["ordinary_pass"]],
            "native16_only_pass": [p["id"] for p in paired if p["native16"]["ordinary_pass"] and not p["uniform8"]["ordinary_pass"]],
            "shared_failures": [p["id"] for p in paired if not p["native16"]["ordinary_pass"] and not p["uniform8"]["ordinary_pass"]],
            "empirical_paired_bootstrap_strict": delta,
            "ratios": {metric: _paired_ratio(*[{item: [row[metric]] for item, row in rows[mode][bench].items()}
                                               for mode in MODES], iters=ITERATIONS, seed=SEED) for metric in METRICS},
            "pairs": paired,
        }

    he = "HumanEval/141"
    corpus_info = selection["corpora"]["humanevalplus"]
    corpus = Path(os.path.expandvars(corpus_info["path"]))
    raw_problem = next(json.loads(line) for line in record(corpus, corpus_info["sha256"]).read_text().splitlines()
                       if json.loads(line)["task_id"] == he)
    failures = {mode: official[mode]["humanevalplus"][he] for mode in MODES}
    def method_calls(source):
        return sorted({node.func.attr for node in ast.walk(ast.parse(source))
                       if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)})
    generated_methods = {mode: method_calls(failures[mode]["solution"]) for mode in MODES}
    reference_methods = method_calls(raw_problem["prompt"] + raw_problem["canonical_solution"])
    require(all(f["base_status"] == "pass" and f["plus_status"] == "fail"
                and f["plus_fail_tests"] == [["éxample.exe"]] for f in failures.values()), "HumanEval/141 failure changed; review needed")
    require(all({"isalpha", "isascii", "isdigit"} <= set(names) for names in generated_methods.values())
            and "isalpha" in reference_methods and "isascii" not in reference_methods,
            "HumanEval/141 predicates changed; review needed")
    require("'a'-'z' and 'A'-'Z'" in raw_problem["prompt"], "HumanEval/141 prompt alphabet changed")
    overview = {metric: _paired_ratio(*[{(bench, item): [row[metric]] for bench, records in rows[mode].items()
                                        for item, row in records.items()} for mode in MODES],
                                      iters=ITERATIONS, seed=SEED) for metric in METRICS}
    for path in (Path(__file__), BENCHMARK / "bench/stats.py", BENCHMARK / "bench/compare_predictor.py",
                 BENCHMARK / "bench/convergence.py"):
        record(path)
    result = {
        "decision": "C82", "status": "quality_analysis_complete", "model": MODEL,
        "states": list(MODES), "n_pairs": 15, "generation_requests": 30,
        "comparison": "uniform8 minus native16; ratios uniform8/native16",
        "sampling": finals["native16"]["sampling"], "kv_treatments": {m: finals[m]["kv"] for m in MODES},
        "frozen_sha256": FROZEN_SHA, "paired_payloads_sha256": object_sha([e["wire"] for e in frozen["requests"]]),
        "axes": axes, "descriptive_all15_ratios": overview,
        **{mode: {"http_wall_s_total": sum(r["wall_s"] for rs in rows[mode].values() for r in rs.values()),
                   "completion_tokens_total": sum(r["completion_tokens"] for rs in rows[mode].values() for r in rs.values()),
                   "mean_per_request_decode_tps": sum(r["decode_tps"] for rs in rows[mode].values() for r in rs.values()) / 15,
                   "all_converged": all(r["converged"] for rs in rows[mode].values() for r in rs.values()),
                   "nonconv_kinds": dict(Counter(r.get("nonconv_kind") for rs in rows[mode].values() for r in rs.values() if not r["converged"]))}
           for mode in MODES},
        "final_answers_byte_identical_pairs": sum(p["native16"]["content_sha256"] == p["uniform8"]["content_sha256"]
                                                   for axis in axes.values() for p in axis["pairs"]),
        "statistics": {"bootstrap_seed": SEED, "iterations": ITERATIONS, "confidence_level": 0.95,
                       "quality_estimator": "bench.stats.paired_delta on strict@81920 per-item outcomes; uniform8 minus native16",
                       "ratio_estimator": "bench.compare_predictor._paired_ratio; ratio of arithmetic means, uniform8/native16",
                       "decode_estimator": "ratio of mean per-request decode rates, not aggregate throughput or mean itemwise ratio",
                       "all15_scope": "Unstratified mixed-benchmark descriptive overview; per-axis results are primary; no composite quality ranking",
                       "multiplicity_adjustment": "none; descriptive intervals",
                       "mde_assumption": "discordant-pair rate 0.20, normal approximation; highly uncertain at five pairs"},
        "shared_failure_note": {"id": he, "official_base": "pass both", "official_plus": "fail both",
                                "failing_input": ["éxample.exe"], "prompt_constraint": "first character from 'a'-'z' or 'A'-'Z'",
                                "reference_behavior": "Unicode-aware isalpha accepts the accented first character",
                                "observed_solutions": "Both use isalpha AND isascii for the first character, rejecting the recorded accented filename",
                                "generated_method_calls": generated_methods, "reference_method_calls": reference_methods,
                                "scope": "Static review of the actual C82 solutions and recorded failure. Both also use Unicode-aware isdigit; this is not proof of whole-function prompt compliance or an exhaustive failure set.",
                                "official_scores_preserved": True},
        "quality_equivalence_established": False, "default_changed": False, "capacity_evidence_included": False,
        "quality_verdict": "no_observed_difference_in_diagnostic_pilot" if all(not a["uniform8_only_pass"] and not a["native16_only_pass"] for a in axes.values()) else "observed_differences_in_diagnostic_pilot",
        "limitations": ["Five pairs per axis cannot establish plus/minus 5pp equivalence.",
                        "Zero-discordance empirical bootstrap collapses to [0,0]; it cannot bound unseen disagreements. Raw helper labels are non-operative.",
                        "Fresh sessions ran native16 then uniform8; order and startup effects were not counterbalanced within this quality pilot.",
                        "Short-task timings include varying output lengths and request overhead; do not substitute for separate capacity/long-context measurements.",
                        "No automatic recommendation/default change or larger study follows from this quality-only analysis."],
        "sources": sources,
    }
    for path, digest in watched.items():
        require(sha(path) == digest, "input changed during analysis: " + path.name)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = analyze()
    destination = HERE / "quality-analysis.json"
    if args.check:
        require(json.loads(destination.read_text()) == result, "saved analysis differs")
    else:
        with destination.open("x") as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
    print(json.dumps({"artifact": destination.name, "checked": args.check,
                      "ratios_uniform8_over_native16": result["descriptive_all15_ratios"],
                      "scores": {b: {m: result["axes"][b][m]["acc"] for m in MODES} for b in AXES}}, indent=2))


if __name__ == "__main__":
    main()
