#!/usr/bin/env python3
"""M39 vision gate (operator re-scope, 2026-09-12): NOT a benchmark -- a pass/fail check for
"can this model do some vision", over the 20-image corpus in
`benchmark/corpora/vision_gate_v1.jsonl`.

Two chat turns per image, through the harness's own request path (`bench.client.probe`) and
production sampling (`bench.model_params.params_for(model, profile="deployed")`), thinking ON,
no changes to budgets:

  Turn 1: image + "Describe this image in detail." -> a free-text description.
  Turn 2: the full turn-1 conversation + the human reference captions -> the model's own
          PASS/FAIL self-verdict on whether its description matches the ground truth.

Never grades a transport failure (AGENTS.md: "Transport/HTTP failures ESCALATE ... they are
NEVER graded"): a completed row is only appended after BOTH turns succeed, so any exception
(HTTP error, dataset-cache miss, ...) aborts the whole run with a nonzero exit before a row is
written for the in-flight item -- a rerun with --resume picks up exactly where it left off.

Usage:
  benchmark/vision_gate.py --model <full-registry-name> [--url http://localhost:8000]
      [--corpus benchmark/corpora/vision_gate_v1.jsonl] [--out <path>] [--limit N]
      [--timeout SECONDS] [--resume]
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench import budget_timeout, client, convergence, generate, model_params, paths, rowschema  # noqa: E402

DEFAULT_CORPUS = paths.repo_root() / "benchmark" / "corpora" / "vision_gate_v1.jsonl"
# Name used only as the `bench` key for `generate.rows_for_rate`'s decode-rate lookup (globs
# results/<model>/vision_gate.*.jsonl) -- vision_gate is deliberately NOT a `bench.benchmarks`
# entry; this script never touches that registry.
BENCH_NAME = "vision_gate"
TUNE = "v1"
TURN1_TEXT = "Describe this image in detail."

_FIRST_WORD = re.compile(r"^[A-Za-z]+")


# --------------------------------------------------------------------------- image materialization
def _image_cache_dir() -> str:
    """`$STACK_WORKDIR/vision_gate_images` -- same out-of-repo-workdir rule and pre-approved
    cache-exception fallback as `bench.benchmarks._visionqa_image_cache_dir`, reimplemented here
    because this script is a standalone CLI outside the `bench` package."""
    workdir = os.environ.get("STACK_WORKDIR")
    if workdir:
        return os.path.join(workdir, "vision_gate_images")
    fallback = os.path.expanduser("~/.cache/huggingface/mlx_local_stack_vision_gate_images")
    print(f"WARNING: STACK_WORKDIR is not set; vision_gate image cache falls back to "
          f"{fallback} (set STACK_WORKDIR per the workdir rule, AGENTS.md)", file=sys.stderr)
    return fallback


def _image_cache_path(row: dict) -> str:
    """`<id>-<sha8>.<ext>`; the sha8 digests `image_ref` so a corpus rebuild that reuses an id
    can never hit a stale cached image (same rule as `_visionqa_image_cache_path`)."""
    ext = row["meta"]["image_format"].lower()
    ref = hashlib.sha1(json.dumps(row["image_ref"], sort_keys=True).encode()).hexdigest()[:8]
    return os.path.join(_image_cache_dir(), f"{row['id']}-{ref}.{ext}")


def resolve_image(row: dict, ds_cache: dict) -> str:
    """Materialize `row`'s image to a local file and return its path (same pattern as
    `bench.benchmarks._resolve_visionqa_images`). `ds_cache` groups by (dataset, split,
    revision) so the one shared HF dataset behind this corpus loads at most once per process."""
    path = _image_cache_path(row)
    if os.path.exists(path):
        return path
    from datasets import load_dataset
    ref = row["image_ref"]
    key = (ref["dataset"], ref["split"], ref["revision"])
    if key not in ds_cache:
        try:
            ds_cache[key] = load_dataset(ref["dataset"], split=ref["split"], revision=ref["revision"])
        except Exception as e:  # noqa: BLE001 -- turn an opaque HF error into an actionable one
            raise RuntimeError(
                f"vision_gate: dataset {ref['dataset']!r} (split={ref['split']!r}, "
                f"revision={ref['revision']!r}) is not in the local HF cache and could not be "
                "fetched (offline / no network?). Run benchmark/corpora/build_vision_gate_v1.py "
                "once with network access to populate ~/.cache/huggingface, or unset "
                f"HF_HUB_OFFLINE. ({type(e).__name__}: {str(e)[:200]})") from e
    img = ds_cache[key][ref["index"]]["image"]
    os.makedirs(_image_cache_dir(), exist_ok=True)
    tmp = path + ".tmp"
    img.save(tmp, format=row["meta"]["image_format"])
    os.replace(tmp, path)
    return path


def _data_url(image_path: str, image_format: str) -> str:
    with open(image_path, "rb") as f:
        raw = f.read()
    mime = "image/jpeg" if image_format.upper() == "JPEG" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


# --------------------------------------------------------------------------- message construction
def turn1_messages(row: dict, image_path: str) -> list:
    """Mirrors `bench.benchmarks._visionqa_messages`'s content-list shape: a text part + a
    base64 `image_url` data URL."""
    return [{"role": "user", "content": [
        {"type": "text", "text": TURN1_TEXT},
        {"type": "image_url",
         "image_url": {"url": _data_url(image_path, row["meta"]["image_format"])}},
    ]}]


def turn2_prompt(captions: list) -> str:
    bullets = "\n".join(f"- {c}" for c in captions)
    return (
        "Here is a ground-truth description of the same image, written by people:\n\n"
        f"{bullets}\n\n"
        "Compare your description with the ground truth. Did your description correctly "
        "capture what is in the image? Reply with exactly one word: PASS or FAIL."
    )


def turn2_messages(msgs1: list, description: str, captions: list) -> list:
    """The FULL conversation so far (turn-1 user message WITH the image, then the assistant's
    description) plus the compare-and-verdict user turn."""
    return msgs1 + [
        {"role": "assistant", "content": description},
        {"role": "user", "content": turn2_prompt(captions)},
    ]


def parse_verdict(text: str):
    """Strict PASS/FAIL parse of a self-verdict reply.

    DECIDED RULE: the reply's FIRST WORD (leading whitespace skipped, trailing punctuation
    ignored) must literally BE "PASS" or "FAIL" -- PASS/FAIL appearing later in a hedge does not
    count, because the model was asked for exactly one word and a reply that didn't follow that
    is not a clean self-verdict:

        "PASS"          -> "PASS"
        "pass."         -> "PASS"   (trailing punctuation stripped)
        "FAIL!"         -> "FAIL"
        "I think PASS"  -> None     (first word is "I", not PASS/FAIL)
        "" / anything else that doesn't start with PASS/FAIL -> None

    Never raises; returns None (caller keeps the raw text regardless) rather than guessing.
    """
    m = _FIRST_WORD.match((text or "").strip())
    if not m:
        return None
    word = m.group(0).upper()
    return word if word in ("PASS", "FAIL") else None


# --------------------------------------------------------------------------- convergence
def _converged(finish_reason, completion_tokens, prompt_tokens, thinking_budget,
               context_limit, max_tokens):
    """The harness convergence rule (`bench.convergence`), judged against the RESOLVED thinking
    budget when the registry's `max_kv_cache_size` (context_limit) and the request's max_tokens
    are both known, else the declared budget (AGENTS.md: never silently invent a context_limit)."""
    row = {"finish_reason": finish_reason, "completion_tokens": completion_tokens,
           "prompt_tokens": prompt_tokens, "thinking_budget": thinking_budget}
    if context_limit and max_tokens:
        convergence.backfill_resolved_budget([row], context_limit=context_limit, max_tokens=max_tokens)
    return convergence.is_converged(row)


# --------------------------------------------------------------------------- corpus / output I/O
def load_corpus(path: Path, limit=None) -> list:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows[:limit] if limit else rows


def read_rows(out_path: Path) -> list:
    if not out_path.exists():
        return []
    rows = []
    for line in out_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def append_row(path: Path, row: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
        f.flush()


def summary_path_for(out: Path) -> Path:
    stem = out.name[:-len(".jsonl")] if out.name.endswith(".jsonl") else out.name
    return out.parent / f"{stem}.summary.json"


def summarize(rows: list) -> dict:
    n = len(rows)
    passed = sum(1 for r in rows if r.get("verdict") == "PASS")
    failed = sum(1 for r in rows if r.get("verdict") == "FAIL")
    nulls = n - passed - failed
    toks = [r["completion_tokens"] for r in rows if isinstance(r.get("completion_tokens"), (int, float))]
    walls = [r["wall_s"] for r in rows if isinstance(r.get("wall_s"), (int, float))]
    return {
        "n": n, "pass": passed, "fail": failed, "null": nulls,
        "pass_rate": round(passed / n, 3) if n else None,
        "turn1_tokens_mean": round(statistics.mean(toks), 1) if toks else None,
        "turn1_wall_s_mean": round(statistics.mean(walls), 1) if walls else None,
        "fail_or_null_ids": [r["id"] for r in rows if r.get("verdict") != "PASS"],
    }


# --------------------------------------------------------------------------- per-item run
def run_one(model: str, params: dict, context_limit, timeout: float, row: dict, ds_cache: dict) -> dict:
    image_path = resolve_image(row, ds_cache)
    msgs1 = turn1_messages(row, image_path)
    p1 = client.probe(model, msgs1, {**params, "seed": rowschema.sample_seed(row["id"], 0)},
                      timeout=timeout)
    description = client.strip_thinking(p1["content"])
    converged1 = _converged(p1["finish_reason"], p1["completion_tokens"], p1["prompt_tokens"],
                            params.get("thinking_budget"), context_limit, params.get("max_tokens"))

    msgs2 = turn2_messages(msgs1, description, row["captions"])
    p2 = client.probe(model, msgs2, {**params, "seed": rowschema.sample_seed(row["id"], 1)},
                      timeout=timeout)
    verdict_raw = client.strip_thinking(p2["content"])
    verdict = parse_verdict(verdict_raw)
    converged2 = _converged(p2["finish_reason"], p2["completion_tokens"], p2["prompt_tokens"],
                            params.get("thinking_budget"), context_limit, params.get("max_tokens"))

    return {
        "id": row["id"],
        "description": description,
        "prompt_tokens": p1["prompt_tokens"], "completion_tokens": p1["completion_tokens"],
        "wall_s": p1["wall_s"], "decode_tps": p1["decode_tps"],
        "finish_reason": p1["finish_reason"], "converged": converged1,
        "verdict": verdict, "verdict_raw": verdict_raw,
        "turn2": {"prompt_tokens": p2["prompt_tokens"], "completion_tokens": p2["completion_tokens"],
                  "wall_s": p2["wall_s"], "finish_reason": p2["finish_reason"],
                  "converged": converged2},
    }


# --------------------------------------------------------------------------- CLI
def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="full registry name (main_models.yaml)")
    ap.add_argument("--url", default="http://localhost:8000", help="mlx-serve router base URL")
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ap.add_argument("--out", default=None,
                    help="default: <results_root>/<model>/vision_gate.v1.jsonl")
    ap.add_argument("--limit", type=int, default=None, help="cap on corpus rows (smoke runs)")
    ap.add_argument("--timeout", type=float, default=None,
                    help="per-turn HTTP timeout, seconds. Default: DERIVED (C28) from the "
                         "model's measured decode rate + its thinking budget, never an SDK "
                         "default (AGENTS.md)")
    ap.add_argument("--resume", action="store_true",
                    help="skip ids already present in --out; without it, a non-empty --out is "
                         "refused rather than silently duplicated")
    return ap


def main(argv=None) -> int:
    args = build_argparser().parse_args(argv)
    if args.url:
        client.BASE = args.url

    out = (Path(args.out) if args.out
          else paths.default_results_root() / args.model / f"{BENCH_NAME}.{TUNE}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)

    existing = read_rows(out)
    done_ids = {r["id"] for r in existing}
    if done_ids and not args.resume:
        print(f"[vision_gate] {out} already has {len(done_ids)} row(s); pass --resume to "
              "continue, or use a different --out (never silently overwritten/duplicated)",
              file=sys.stderr)
        return 2

    corpus_rows = load_corpus(Path(args.corpus), args.limit)
    todo = [r for r in corpus_rows if r["id"] not in done_ids] if args.resume else corpus_rows

    params = model_params.params_for(args.model, profile="deployed")
    context_limit = model_params.registry_context_limit(args.model)

    if args.timeout:
        timeout = args.timeout
        print(f"[vision_gate] per-turn HTTP timeout = {timeout:.0f}s (EXPLICIT --timeout)")
    else:
        rate_rows = generate.rows_for_rate(args.model, BENCH_NAME)
        tps = budget_timeout.floor_decode_tps(rate_rows)
        d = budget_timeout.derive_timeout(params.get("thinking_budget"), tps)
        timeout = d["timeout_s"]
        print(f"[vision_gate] per-turn HTTP timeout = {timeout:.0f}s (DERIVED, C28) -- {d['reason']}")

    print(f"[vision_gate] {args.model}: {len(todo)} item(s) to run "
          f"({len(done_ids)} already done)" if args.resume else
          f"[vision_gate] {args.model}: {len(todo)} item(s) to run")

    ds_cache: dict = {}
    for i, row in enumerate(todo):
        print(f"[vision_gate] {args.model} {row['id']} ({i + 1}/{len(todo)})", flush=True)
        row_out = run_one(args.model, params, context_limit, timeout, row, ds_cache)
        append_row(out, row_out)
        print(f"[vision_gate]   -> verdict={row_out['verdict']} converged={row_out['converged']} "
              f"tokens={row_out['completion_tokens']}", flush=True)

    summary = summarize(read_rows(out))
    summary_path_for(out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"[vision_gate] RESULT {args.model}: {summary['pass']}/{summary['n']} pass, "
          f"fail={summary['fail']} null={summary['null']} pass_rate={summary['pass_rate']}")
    print(f"[vision_gate] wrote {out}")
    print(f"[vision_gate] wrote {summary_path_for(out)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 -- transport/dataset/registry failures ESCALATE
        # (AGENTS.md: "Transport/HTTP failures ... are NEVER graded") -- abort loudly, nonzero
        # exit, and (by construction) no row was appended for the in-flight item.
        print(f"[vision_gate] FATAL: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
