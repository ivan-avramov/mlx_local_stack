"""Adapter that drives the official BFCL harness (`bfcl-eval`) against our mlx-serve
OpenAI-compatible endpoint and normalizes its scores. Single-turn AST categories only.
`bfcl-eval` is an optional heavy dependency: detected lazily, graceful-degrade if absent.

================================================================================
BFCL v4 (bfcl-eval 2026.3.x, VERSION_PREFIX="BFCL_v4") — what this adapter assumes
================================================================================

Drifts handled vs the original v3 adapter:

1. Category names. v4 renamed the python `simple` category to `simple_python` and
   split simple by language (`simple_python`/`simple_java`/`simple_javascript`).
   The bare `"simple"` is INVALID in v4 (raises "Invalid test category name").
   We default to the *python* single-turn AST set, matching the v4 `"python"` test
   collection (minus live/irrelevance): simple_python, multiple, parallel,
   parallel_multiple. Source: bfcl_eval/constants/category_mapping.py NON_LIVE_CATEGORY.

2. Score-file prefix + layout. Score files are `BFCL_v4_<cat>_score.json` (we read
   VERSION_PREFIX from the package when importable, else fall back to "BFCL_v4").
   IMPORTANT v4 layout change: scores are written under a *grouping* subdirectory,
   not directly under <score_dir>/<model>/. For our non-live AST categories the
   group is "non_live", so the path is
       <score_dir>/<model>/non_live/BFCL_v4_<cat>_score.json
   (bfcl_eval/eval_checker/eval_runner_helper.py save_eval_results +
    bfcl_eval/utils.py get_directory_structure_by_category -> get_general_grouping).
   The line-0 summary shape is UNCHANGED: {accuracy, correct_count, total_count, ...}.
   parse_scores() searches the grouping subdir(s) and falls back to the flat path.

3. Limit flag. `--num-tests` was REMOVED in v4. The v4 mechanism is `--run-ids`
   (a boolean flag) which makes `generate` read a `test_case_ids_to_generate.json`
   file at <PROJECT_ROOT>/test_case_ids_to_generate.json and run ONLY the listed
   ids (the --test-category arg is then ignored). PROJECT_ROOT defaults to the
   package's grandparent dir but is overridable via env BFCL_PROJECT_ROOT. We set
   BFCL_PROJECT_ROOT to a per-run root we own, write the id file there with the
   first N ids per category (id format is "<category>_<index>", e.g.
   "simple_python_0"), and pass --run-ids. We also pass `--partial-eval` to
   `evaluate` so a limited result set does not raise on missing ids.
   If limit is None we run full (no id file, no --run-ids).

================================================================================
LOCAL / SELF-HOSTED MODEL MECHANISM (critical — read before a live run)
================================================================================

v4 does NOT accept arbitrary local model names. `bfcl generate` and `bfcl evaluate`
both hard-raise ValueError("Unknown model_name ...") if the --model value is not a
key in bfcl_eval.constants.model_config.MODEL_CONFIG_MAPPING. So our served names
like "gemma-4-26B-A4B-it-OptiQ-4bit" / "Qwen3.6-27B-OptiQ-4bit" CANNOT be passed
directly — they must be mapped to a REGISTERED bfcl model key.

How a registered local (OSS) model talks to our endpoint:
  * The OSS handler (base_oss_handler.py) builds an OpenAI client at
    http://$LOCAL_SERVER_ENDPOINT:$LOCAL_SERVER_PORT/v1 (or env REMOTE_OPENAI_BASE_URL),
    and calls the legacy *text* /v1/completions endpoint with a model-specific
    pre-formatted prompt string (NOT /v1/chat/completions). Our mlx-serve must
    expose /v1/completions.
  * With --skip-server-setup, v4 does NOT launch vLLM/sglang, BUT it STILL loads a
    HF tokenizer+config (AutoTokenizer/AutoConfig) for the registered handler — used
    to format the prompt and read max_position_embeddings. So either the registered
    model_name must be a resolvable HF repo id (downloaded/cached), or you set
    env REMOTE_OPENAI_TOKENIZER_PATH to a local dir holding tokenizer files, or
    pass --local-model-path. The prompt template is the handler's _format_prompt
    (e.g. GemmaHandler emits the gemma <start_of_turn> template; the BFCL
    function-calling instructions are injected as a system prompt for prompt-mode
    models).

REGISTRATION OPTIONS (pick one before a live run — do NOT pass a raw served name):
  (a) Reuse a close stock key whose handler/template matches our served model and
      point it at our endpoint. The key MUST resolve to a *local OSS* handler (a
      subclass of base_oss_handler.OSSHandler) — those hit our endpoint. Beware: the
      lowercase "qwen3-32b" keys map to QwenAPIHandler (Alibaba DashScope API) and
      would NOT hit localhost. Use the HF-id local keys instead:
        - gemma:  "google/gemma-3-27b-it"            -> GemmaHandler  (prompt mode)
        - qwen:   "Qwen/Qwen3-32B" (prompt) or
                  "Qwen/Qwen3-32B-FC" (function-calling) -> QwenHandler/QwenFCHandler
                  (also Qwen/Qwen3-30B-A3B-Instruct-2507[-FC] for an MoE template).
      Pick the registry key whose handler template best matches the served weights.
      For our gemma, "google/gemma-3-27b-it" GemmaHandler's _format_prompt is the
      gemma <start_of_turn> template our served gemma understands. mlx-serve must answer to whatever
      model id the OpenAI client sends — mlx-serve serves a single loaded model and
      generally ignores/loose-matches the request's "model" field, so the served
      weights are whatever you loaded on :8000 regardless of the BFCL key. (Verify
      on the live run; see risks.) Tokenizer: the HF id "google/gemma-3-27b-it"
      must be cached locally, OR set REMOTE_OPENAI_TOKENIZER_PATH to a local gemma
      tokenizer dir to avoid a download.
  (b) Add a first-party ModelConfig entry to MODEL_CONFIG_MAPPING for our exact
      served name (edit bfcl_eval/constants/model_config.py +
      constants/supported_models.py), choosing model_handler=GemmaHandler /
      QwenHandler etc. and model_name=<HF id or local tokenizer path>. This is the
      "officially supported" path (README/CONTRIBUTING) and survives `--model
      <our-name>`. It mutates the installed package, so prefer (a) for a quick run.

This adapter therefore takes the bfcl *registry key* as `model` (what gets passed to
--model), and a separate served-name is irrelevant to bfcl (mlx-serve owns it). The
returned dict still keys on whatever `model` you pass, so pass the registry key.
"""
import json
import os
import shutil
import subprocess

# v4 single-turn non-live AST categories (python set). "simple" -> "simple_python".
AST_CATEGORIES = ("simple_python", "multiple", "parallel", "parallel_multiple")


def _version_prefix() -> str:
    """Read VERSION_PREFIX from the installed bfcl_eval if importable; else 'BFCL_v4'."""
    try:
        from bfcl_eval.constants.category_mapping import VERSION_PREFIX  # type: ignore
        return VERSION_PREFIX
    except Exception:  # noqa: BLE001 — package may be absent in CI; degrade to v4 literal
        return "BFCL_v4"


# v4 score files live under a grouping subdir (non_live for our AST set); some
# installs/older layouts wrote flat. Search both, most-specific first.
_SCORE_SUBDIRS = ("non_live", "")


def _read_summary(path: str) -> dict | None:
    """BFCL score files are JSONL; line 0 is the summary {accuracy, correct_count, total_count}."""
    try:
        with open(path, encoding="utf-8") as f:
            first = f.readline().strip()
        if not first:
            return None
        obj = json.loads(first)
        if "accuracy" not in obj:
            return None
        return obj
    except (OSError, json.JSONDecodeError):
        return None


def _score_path(score_dir: str, model: str, cat: str) -> str | None:
    """Locate the v4 score file for a category, trying the grouping subdir then flat.
    Model dir uses '/'->'_' like bfcl's runner does."""
    prefix = _version_prefix()
    model_dir = model.replace("/", "_")
    fname = f"{prefix}_{cat}_score.json"
    for sub in _SCORE_SUBDIRS:
        p = os.path.join(score_dir, model_dir, sub, fname) if sub else \
            os.path.join(score_dir, model_dir, fname)
        if os.path.exists(p):
            return p
    return None


def parse_scores(score_dir: str, model: str, categories=AST_CATEGORIES) -> dict:
    """Read BFCL per-category score files and normalize to one record. `acc` is the
    count-weighted overall accuracy (0-1) across the categories that produced a score;
    a missing/malformed category maps to None and is excluded from the overall."""
    per_category: dict = {}
    correct = total = 0
    for cat in categories:
        path = _score_path(score_dir, model, cat)
        summ = _read_summary(path) if path else None
        if summ is None:
            per_category[cat] = None
            continue
        c = int(summ.get("correct_count", 0))
        t = int(summ.get("total_count", 0))
        per_category[cat] = {"accuracy": summ.get("accuracy"), "correct": c, "total": t}
        correct += c
        total += t
    acc = round(correct / total, 4) if total else None
    return {"per_category": per_category, "acc": acc, "n": total}


def find_poisoned_rows(result_dir: str, model: str) -> dict:
    """{category: [ids]} of raw result rows whose `result` is an inference-error STRING
    (`"Error during inference: ..."`) — items that never produced a model answer because
    the transport failed. Such rows grade as `ast_decoder:decoder_failed`, i.e. as wrong
    ANSWERS, which is how 152 rows (dead-port window) and 2-per-runaway-episode (600 s
    client timeout, O41.0) entered scored results in 2026-08-24's incidents. Grading
    paths call this to REFUSE such trees (see run_bfcl_fc._apply_poison_guard);
    generation-side, the O41.1 fail-loud handler prevents new ones."""
    poisoned: dict = {}
    model_root = os.path.join(result_dir, model)
    for dirpath, _dirnames, filenames in os.walk(model_root):
        for fn in sorted(filenames):
            if not (fn.startswith("BFCL_v4_") and fn.endswith("_result.json")):
                continue
            cat = fn[len("BFCL_v4_"):-len("_result.json")]
            with open(os.path.join(dirpath, fn)) as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row.get("result"), str) and row["result"].startswith(
                        "Error during inference"
                    ):
                        poisoned.setdefault(cat, []).append(row.get("id"))
    return poisoned


def bfcl_available() -> bool:
    return shutil.which("bfcl") is not None


def _write_run_ids_file(project_root: str, categories, limit: int) -> str:
    """Write a v4 test_case_ids_to_generate.json with the first `limit` ids per
    category (id format '<category>_<index>'). Returns the file path. bfcl reads it
    from <BFCL_PROJECT_ROOT>/test_case_ids_to_generate.json."""
    os.makedirs(project_root, exist_ok=True)
    ids = {cat: [f"{cat}_{i}" for i in range(limit)] for cat in categories}
    path = os.path.join(project_root, "test_case_ids_to_generate.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ids, f)
    return path


def _cli(phase, model, categories, result_dir, score_dir, limit):
    """Build the v4 bfcl argv for a phase.

    Local/self-hosted endpoint flags: --backend vllm (an OSS/local handler backend;
    the actual server is ours, so it is never spun up) + --skip-server-setup so v4
    uses the existing endpoint from LOCAL_SERVER_ENDPOINT/LOCAL_SERVER_PORT.
    --num-threads 1 keeps requests serialized (we run one model at a time).

    Limit: v4 has no --num-tests. When limit is set we pass --run-ids (boolean) and
    rely on the caller having written test_case_ids_to_generate.json under
    BFCL_PROJECT_ROOT; we still pass --test-category (ignored by generate under
    --run-ids, but required/used by evaluate)."""
    cmd = ["bfcl", phase, "--model", model,
           "--test-category", ",".join(categories)]
    if phase == "generate":
        cmd += ["--num-threads", "1", "--backend", "vllm", "--skip-server-setup",
                "--result-dir", result_dir, "--allow-overwrite"]
        if limit is not None:
            cmd += ["--run-ids"]
    else:  # evaluate
        cmd += ["--result-dir", result_dir, "--score-dir", score_dir]
        if limit is not None:
            cmd += ["--partial-eval"]  # don't raise on ids absent from the limited run
    return cmd


def run_bfcl(model, categories=AST_CATEGORIES, endpoint="localhost", port=8000,
             result_dir="bfcl_runs/result", score_dir="bfcl_runs/score",
             limit=None, runner=subprocess.run) -> dict:
    """Drive bfcl-eval (v4) against the local mlx-serve endpoint for the AST single-turn
    categories, then normalize the scores. `runner` is injectable for tests. Lazy-detected;
    graceful-degrade if `bfcl` is absent or a phase exits non-zero.

    `model` MUST be a key registered in bfcl's MODEL_CONFIG_MAPPING (v4 rejects unknown
    names) — see the module docstring "LOCAL / SELF-HOSTED MODEL MECHANISM". The served
    weights on :<port> are whatever mlx-serve loaded; bfcl only uses `model` to pick the
    handler/template and tokenizer.

    `result_dir`/`score_dir` are passed to bfcl as-is; bfcl resolves them against
    BFCL_PROJECT_ROOT (absolute paths win the join, so absolute is safe). When `limit`
    is set we set BFCL_PROJECT_ROOT to the result_dir's parent so the run-ids file is
    found, and write that file with the first `limit` ids per category."""
    base = {"model": model, "axis": "tool_calling", "categories": list(categories)}
    if not bfcl_available():
        return {**base, "acc": None, "n": 0, "skipped": True,
                "note": "bfcl CLI not found; pip install bfcl-eval where BFCL runs (see README)"}
    env = {**os.environ, "LOCAL_SERVER_ENDPOINT": endpoint, "LOCAL_SERVER_PORT": str(port)}

    if limit is not None:
        # bfcl reads test_case_ids_to_generate.json from BFCL_PROJECT_ROOT; root it at
        # the dir holding result/ so absolute result/score dirs still resolve correctly.
        project_root = os.path.dirname(os.path.abspath(result_dir)) or "."
        env["BFCL_PROJECT_ROOT"] = project_root
        try:
            _write_run_ids_file(project_root, categories, limit)
        except OSError as e:
            return {**base, "acc": None, "n": 0, "skipped": False,
                    "note": f"bfcl limit setup failed: {type(e).__name__}: {str(e)[:120]}"}

    for phase in ("generate", "evaluate"):
        try:
            proc = runner(_cli(phase, model, categories, result_dir, score_dir, limit),
                          env=env, capture_output=True, text=True)
        except Exception as e:  # noqa: BLE001 — bfcl binary/PATH failure; degrade, never raise
            return {**base, "acc": None, "n": 0, "skipped": False,
                    "note": f"bfcl {phase} raised: {type(e).__name__}: {str(e)[:120]}"}
        rc = getattr(proc, "returncode", 1)  # missing returncode => treat as failure
        if rc != 0:
            return {**base, "acc": None, "n": 0, "skipped": False,
                    "note": f"bfcl {phase} failed rc={rc}: {(getattr(proc, 'stderr', '') or '')[:160]}"}
    return {**base, **parse_scores(score_dir, model, categories), "skipped": False}
