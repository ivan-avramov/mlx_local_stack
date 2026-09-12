"""CLI: run the blind mixed-family pairwise judge panel for role C (M38) —
`docs/judge-panel-c.md` "Panel and protocol".

  cd benchmark && ../.venv-bench/bin/python -m bench.run_judge_pairwise \\
      --models NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed \\
               Qwen3.8-27B-mlx-uniform-4bit Qwen3.6-27B-Opus-Distill-OptiQ-4bit \\
      --anchors benchmark/results/judge_c_v1/pairs.jsonl --out benchmark/results/judge_c_v1

`--dry-run` writes the pair manifest and the first pair's exact prompts (both orders) and
calls no judge. A real run is resumable (re-running the same command skips (pair, order,
judge) triples already in `verdicts.jsonl`) and ESCALATES (nonzero exit, no graded row) on a
transport failure that survives its retries — see `judge_pairwise.TransportEscalation`.

Subagent judge path (operator decision 2026-09-12): `opus`/`sonnet` run as Claude Code  # allow-shorthand
SUBAGENTS instead of API calls; GPT-5.5 stays on the in-process `codex exec` path above.

  --export-packets DIR --judges opus sonnet  (plus the usual --models/--anchors/--corpus/--seed)  # allow-shorthand
      writes one markdown packet per (pair, order, judge) under DIR/<judge>/batch<NN>/<pkt>.md,
      DIR/manifest.jsonl (private, never shown to a judge) and DIR/README_JUDGE.md. No judge is
      called. `--batch-size` (default 10) controls packets per batch.

  --ingest-packets DIR [--out VERDICTS_DIR]
      reads every `<pkt>.verdict.json` the manifest points at, validates it the same way a live
      call's response is validated, and appends new rows (schema-identical to the API path, plus
      `transport`) to VERDICTS_DIR/verdicts.jsonl (default: DIR/../verdicts.jsonl). Idempotent on
      (pair_id, order, judge); reports expected-vs-present per judge/batch and any missing files.
"""
import argparse
import json
import os
import sys

from . import judge_pairwise as J

DEFAULT_CORPUS = os.path.join(os.path.dirname(__file__), "..", "corpora", "cjudge_v1.jsonl")
DEFAULT_OUT = os.path.join(J.RESULTS, "judge_c_v1")


def read_pairs_jsonl(path):
    pairs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    return pairs


def load_item_prompts(corpus_path):
    """{item_id: prompt_text} from the cjudge corpus. Missing file -> {} with a warning
    (graceful-degrade: the judge still runs, just without the task text — visible in the
    written prompts, never a crash)."""
    prompts = {}
    if not os.path.exists(corpus_path):
        print(f"[run_judge_pairwise] WARN corpus not found at {corpus_path!r}; "
              "prompts will be blank", flush=True)
        return prompts
    with open(corpus_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("id") is not None:
                prompts[row["id"]] = row.get("prompt", "")
    return prompts


def _write_dry_run_prompts(out_dir, pairs, task_prompts, model_names):
    path = os.path.join(out_dir, "dry_run_prompt.txt")
    if not pairs:
        with open(path, "w", encoding="utf-8") as f:
            f.write("(no pairs)\n")
        return path
    first = pairs[0]
    task_prompt = task_prompts.get(first["item_id"], "")
    a = J.strip_model_names(first["a_text"], model_names)
    b = J.strip_model_names(first["b_text"], model_names)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"=== pair_id: {first['pair_id']} ===\n")
        f.write("=== SYSTEM ===\n" + J.RUBRIC_SYSTEM_PROMPT + "\n\n")
        for order in J.ORDERS:
            first_text, second_text = (a, b) if order == "AB" else (b, a)
            f.write(f"=== ORDER {order} USER ===\n" +
                    J.build_user_prompt(task_prompt, first_text, second_text) + "\n\n")
    return path


def _run_ingest_packets(args):
    """`--ingest-packets DIR` branch: no pair-building, no `--models`/`--anchors` needed."""
    rows, report = J.ingest_packets(args.ingest_packets)
    verdicts_path = (os.path.join(args.out, "verdicts.jsonl") if args.out
                     else os.path.normpath(os.path.join(args.ingest_packets, "..", "verdicts.jsonl")))
    appended = J.append_new_verdicts(rows, verdicts_path)
    print(f"[run_judge_pairwise] ingest: {len(rows)} verdict file(s) parsed, {appended} new "
          f"row(s) appended -> {verdicts_path}", flush=True)
    for judge_name, batches in sorted(report["judges"].items()):
        for batch_name, counts in sorted(batches.items()):
            print(f"  {judge_name}/{batch_name}: {counts['present']}/{counts['expected']} "
                  "present", flush=True)
    if report["missing"]:
        print(f"[run_judge_pairwise] {len(report['missing'])} verdict file(s) still missing:",
              flush=True)
        for m in report["missing"]:
            print(f"  {m['judge']} {m['pkt']} -> {m['path']}", flush=True)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run the M38 blind pairwise judge panel.")
    ap.add_argument("--models", nargs="+", metavar="MODEL", default=None)  # >= 2 (C67: five contenders)
    ap.add_argument("--tune", default="m38")
    ap.add_argument("--anchors", default=None, help="pairs.jsonl from judge_anchors")
    ap.add_argument("--results-dir", default=J.RESULTS)
    ap.add_argument("--corpus", default=DEFAULT_CORPUS)
    ap.add_argument("--judges", nargs="+", default=["opus", "sonnet", "gpt-5.5"])  # allow-shorthand
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=38)
    ap.add_argument("--limit-pairs", type=int, default=None)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--backoff", type=float, default=1.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-single-family", action="store_true",
                    help="override the mixed-family guard (docs/judge-panel-c.md: mixed "
                         "family is mandatory)")
    ap.add_argument("--export-packets", default=None, metavar="DIR",
                    help="write blind markdown judge packets for a subagent judge path "
                         "(operator decision 2026-09-12); makes no judge calls")
    ap.add_argument("--ingest-packets", default=None, metavar="DIR",
                    help="read *.verdict.json under DIR (written by a judge subagent against "
                         "--export-packets' output) and append rows to verdicts.jsonl")
    ap.add_argument("--batch-size", type=int, default=10,
                    help="packets per batch directory for --export-packets")
    args = ap.parse_args(argv)

    if args.ingest_packets:
        return _run_ingest_packets(args)

    if not args.models or not args.anchors:
        ap.error("--models and --anchors are required unless --ingest-packets is given")
    out_dir = args.out or DEFAULT_OUT

    rows_by_model = J.load_model_rows(args.models, tune=args.tune, results_dir=args.results_dir)
    candidate_pairs = J.build_candidate_pairs(rows_by_model, seed=args.seed)
    anchor_pairs = read_pairs_jsonl(args.anchors)
    pairs = J.merge_and_shuffle(candidate_pairs, anchor_pairs, seed=args.seed)
    if args.limit_pairs is not None:
        pairs = pairs[:args.limit_pairs]

    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "pair_manifest.jsonl")
    with open(manifest_path, "w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p) + "\n")
    print(f"[run_judge_pairwise] {len(pairs)} pairs ({len(candidate_pairs)} candidate + "
          f"{len(anchor_pairs)} anchor) -> {manifest_path}", flush=True)

    task_prompts = load_item_prompts(args.corpus)

    if args.export_packets:
        manifest_rows = J.export_packets(pairs, args.judges, task_prompts, args.models,
                                         args.export_packets, batch_size=args.batch_size)
        print(f"[run_judge_pairwise] exported {len(manifest_rows)} packet(s) for "
              f"{len(args.judges)} judge(s) -> {args.export_packets} (no judge calls made)",
              flush=True)
        return 0

    if args.dry_run:
        prompt_path = _write_dry_run_prompts(out_dir, pairs, task_prompts, args.models)
        print(f"[run_judge_pairwise] dry-run: no judge calls made; first-pair prompts -> "
              f"{prompt_path}", flush=True)
        return 0

    judge_fns_all = J.default_judge_fns()
    unknown = [j for j in args.judges if j not in judge_fns_all]
    if unknown:
        print(f"[run_judge_pairwise] ERROR unknown judges {unknown}; choices are "
              f"{sorted(judge_fns_all)}", file=sys.stderr, flush=True)
        return 1
    families = set(J.judge_families(args.judges).values())
    if len(families) <= 1 and not args.allow_single_family:
        print(f"[run_judge_pairwise] ERROR --judges {args.judges} are all one family "
              f"({families}) — docs/judge-panel-c.md requires a mixed-family panel. Pass "
              "--allow-single-family to override.", file=sys.stderr, flush=True)
        return 1
    judge_fns = {name: judge_fns_all[name] for name in args.judges}
    verdicts_path = os.path.join(out_dir, "verdicts.jsonl")
    costlog_path = os.path.join(out_dir, "costlog.json")
    cost_log = {}
    try:
        made = J.run_pairwise(pairs, args.judges, judge_fns, task_prompts, args.models,
                              verdicts_path, retries=args.retries, backoff=args.backoff,
                              cost_log=cost_log)
        print(f"[run_judge_pairwise] made {made} calls -> {verdicts_path}", flush=True)
        return 0
    except J.TransportEscalation as exc:
        print(f"[run_judge_pairwise] ESCALATE (transport failure survived retries): {exc}",
              file=sys.stderr, flush=True)
        return 1
    finally:
        with open(costlog_path, "w") as f:
            json.dump(cost_log, f, indent=2)
        print(f"[run_judge_pairwise] cost log -> {costlog_path}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
