"""Preflight probes — confirm the stack is sane, and the model's edit format, before a run.

CANARY. Loads the target model and runs ONE trivial coding probe under the run's sampling
profile, asserting it CONVERGES (finish=='stop' AND completion_tokens < thinking_budget) and
emits code. A loop / truncation / empty answer here means the stack is in a bad state (stale
router, bad model load, wrong quant) — abort before wasting a multi-hour run. This is the gate
that would have caught the stale-router loops directly.

EDIT FORMAT (`check_edit_format`). Decides, in ~5 minutes, whether a model can drive aider's
`diff` (SEARCH/REPLACE) format or needs `whole`. See that function's docstring for the two hours
of box time this exists to save.

Exit 0 = sane, 1 = not sane. Invoked by preflight.sh after a fresh router restart.

  python benchmark/bench/preflight.py <registered-model-name> [--profile NAME] [--edit-format]
"""
import ast
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bench import convergence, driver as bench_driver, model_params  # noqa: E402

CANARY = (
    "Write a Python function is_palindrome(s) that returns True iff s reads the same "
    "forwards and backwards, ignoring case and non-alphanumeric characters. "
    "Return the solution as a single self-contained ```python code block."
)


def restart_router(base: str = "http://localhost:8000", wait_s: int = 90) -> bool:
    """Force a fresh local router: kill mlx procs, relaunch mlx-serve, wait for health.
    Used as generate.run's restart_fn for auto-restart-on-loop. Returns True if healthy.
    Runs from repo root (the recipe sources ./.env and reads main_models.yaml)."""
    import subprocess
    import time
    import urllib.request
    for pat in ("mlx-serve", "mlx_vlm.server"):
        subprocess.run(["pkill", "-9", "-f", pat], stderr=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL)
    time.sleep(3)
    recipe = ("set -a; . ./.env 2>/dev/null || true; set +a; "
              "MLX_SERVE_CONFIG=main_models.yaml nohup uv run mlx-serve start "
              ">>logs/main_model.log 2>&1 </dev/null &")
    subprocess.Popen(["bash", "-lc", recipe])
    deadline = time.time() + wait_s
    while time.time() < deadline:
        time.sleep(3)
        try:
            with urllib.request.urlopen(base + "/health", timeout=4) as r:
                if b"ok" in r.read():
                    return True
        except Exception:  # noqa: BLE001
            pass
    return False


def run_canary(model: str, profile: str = "production", driver=None,
               registry_path: str = "main_models.yaml") -> dict:
    """Load `model` and run the trivial coding canary at `profile`'s sampling. Returns a dict.

    WHY `profile` EXISTS. This function used to call `params_for(model)` with no profile. It did
    NOT hardcode a temperature — it IGNORED the profile the run itself would use, and so always
    canaried against the `production` table. That silently mismatches any run evaluated at
    another profile and FALSE-FAILS it: the Ornith canary at production temp 0.7 meandered past
    its budget on a trivial is_palindrome (ct=49221 > 49152 = non-converged) while the same
    prompt at official temp 0.6 converged in 1369 tokens (docs/lab-notebook.md (2026-08-16 salvage section)). The
    canary must be measured at the sampling the run will actually use, or its verdict is about a
    config nobody is running.

    The DEFAULT stays `production` so existing callers (preflight.sh, which passes no profile)
    keep their exact behaviour — a silent change here would invalidate the one gate we trust.
    `profile="deployed"` reads main_models.yaml `generation_defaults`, i.e. what mlx-serve
    actually forwards to the worker, and is the right choice for new axes.

    Returns {"ok", "model", "profile", "converged", "has_code", "finish_reason",
    "completion_tokens", "thinking_budget", "params", "note"}. `ok` is the old boolean return.
    An unresolvable profile or a dead router DEGRADES (ok False + a note) instead of raising:
    preflight is the thing that runs when the stack is already suspect.
    """
    out = {"ok": False, "model": model, "profile": profile, "converged": None,
           "has_code": False, "finish_reason": None, "completion_tokens": None,
           "thinking_budget": None, "params": None, "note": None}
    try:
        params = model_params.params_for(model, profile, registry_path=registry_path)
    except KeyError:
        out["note"] = (f"unknown sampling profile {profile!r} — known profiles: "
                       f"{', '.join(model_params.profile_names())}")
        print(f"[preflight] {out['note']}", flush=True)
        return out
    except LookupError as e:                    # `deployed` with no registry answer: fails loud
        out["note"] = f"cannot resolve profile {profile!r} for {model!r}: {e}"
        print(f"[preflight] {out['note']}", flush=True)
        return out

    out["params"] = dict(params)
    out["thinking_budget"] = params.get("thinking_budget")
    drv = driver or bench_driver.MlxServeDriver()
    try:
        drv.preload(model)
        r = drv.complete(model, [{"role": "user", "content": CANARY}], params)
    except AssertionError:                      # never swallow a test fake's exhaustion guard
        raise
    except Exception as e:                      # noqa: BLE001 - degrade, don't crash the gate
        out["note"] = f"canary probe failed: {type(e).__name__}: {e}"
        print(f"[preflight] {out['note']}", flush=True)
        return out

    row = {"finish_reason": r.get("finish_reason"),
           "completion_tokens": r.get("completion_tokens"),
           "thinking_budget": params.get("thinking_budget")}
    out["finish_reason"] = row["finish_reason"]
    out["completion_tokens"] = row["completion_tokens"]
    out["converged"] = convergence.is_converged(row)
    content = r.get("content") or ""
    out["has_code"] = "```python" in content or "def is_palindrome" in content
    out["ok"] = out["converged"] is True and out["has_code"]
    print(f"[preflight] model={model} profile={profile} temp={params.get('temperature')} "
          f"finish={row['finish_reason']} comp_tok={row['completion_tokens']} "
          f"budget={row['thinking_budget']} converged={out['converged']} "
          f"code={out['has_code']}", flush=True)
    return out


# --------------------------------------------------------------------------- edit-format probe
FIXTURE_NAME = "pricing.py"

# A small, realistic module: module constant + three short functions, one unique anchor line
# (`TAX_RATE = 0.08`) for the SEARCH text. Kept in code, not in a data file, so the probe works
# from any cwd on any box (the boxes run the harness from the repo root, but a preflight that
# breaks on a path is a preflight nobody runs).
FIXTURE_SRC = '''"""Line-item pricing helpers."""

TAX_RATE = 0.08


def subtotal(items):
    return sum(qty * price for _, qty, price in items)


def apply_discount(amount, rate=0.10):
    if rate < 0 or rate > 1:
        raise ValueError("rate must be in [0, 1]")
    return amount * (1 - rate)


def total(items, discount_rate=0.10):
    net = apply_discount(subtotal(items), discount_rate)
    return round(net * (1 + TAX_RATE), 2)
'''

EDIT_INSTRUCTION = "raise the sales tax rate from 0.08 to 0.09"

# A few KB: enough to read the whole offending block, small enough to print in a log and to keep
# a results row from becoming a transcript dump.
RAW_MAX_CHARS = 4096

# Marker lines, tolerant of leading/trailing whitespace (models pad them) and of marker runs
# longer than aider's canonical 7 characters. Matched LINE BY LINE rather than with one spanning
# regex: a spanning regex happily pairs the SEARCH of a mangled draft block with the `=======` of
# the NEXT (good) block, swallowing the markers in between and turning a recoverable response
# into a bogus search_not_found.
_SEARCH_RE = re.compile(r"^[ \t]*<{5,}[ \t]*SEARCH\b")
_DIVIDER_RE = re.compile(r"^[ \t]*={3,}[ \t]*$")
_REPLACE_RE = re.compile(r"^[ \t]*>{5,}[ \t]*REPLACE\b")
_FENCE_RE = re.compile(r"^[ \t]*```[ \t]*[\w+.-]*[ \t]*\n(.*?)^[ \t]*```", re.M | re.S)
_FILENAME_RE = re.compile(r"^[ \t]*([\w./\\-]+\.(?:py|txt|md|js|ts|go|rs|java|cpp|c|h))[ \t]*:?$")


def _norm(text: str) -> str:
    """CRLF -> LF. Models behind HTTP proxies do emit CRLF, and an unnormalised SEARCH ends with
    a stray \\r that occurs nowhere in the file — a FAKE search_not_found indistinguishable from
    the real gemma failure."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def _filename_before(lines: list, idx: int):
    """The nearest non-blank line above the block that looks like a path — aider puts the
    filename above the fence. Captured for diagnosis only: the probe edits one known file, so a
    wrong filename is not itself an apply failure."""
    for line in reversed(lines[:idx]):
        line = line.strip()
        if not line or line.startswith("```"):
            continue
        m = _FILENAME_RE.match(line)
        return m.group(1) if m else None
    return None


def _scan(text: str):
    """(blocks, saw_marker) — the line state machine behind parse_search_replace.

    `saw_marker` is True when a marker line appeared at all; it is what separates "the model
    ignored the format" (no_block) from "the model aimed at the format and fumbled it"
    (malformed_markers), which have different fixes.
    """
    lines = _norm(text).split("\n")
    blocks, saw_marker = [], False
    state, start, search, replace = None, None, [], []
    for i, line in enumerate(lines):
        if _SEARCH_RE.match(line):
            saw_marker = True                   # an unfinished previous block is abandoned here
            state, start, search, replace = "search", i, [], []
        elif state == "search" and _DIVIDER_RE.match(line):
            saw_marker = True
            state = "replace"
        elif state == "replace" and _REPLACE_RE.match(line):
            saw_marker = True
            blocks.append({"filename": _filename_before(lines, start),
                           "search": "\n".join(search), "replace": "\n".join(replace)})
            state = None
        elif _REPLACE_RE.match(line):           # REPLACE with no divider: malformed, abandon
            saw_marker = True
            state = None
        elif state == "search":
            search.append(line)
        elif state == "replace":
            replace.append(line)                # a stray `=======` here is just replacement text
    return blocks, saw_marker


def parse_search_replace(text: str) -> list:
    """Every well-formed SEARCH/REPLACE block in `text`, in order.

    Deliberately marker-driven rather than fence-driven: thinking is ON for every campaign run
    (AGENTS.md — never disabled to make a benchmark work), so blocks arrive wrapped in prose,
    inside <think> tags, sometimes without a fence at all. Anchoring on the markers tolerates all
    of that; anything the markers do not delimit is ignored.
    """
    return _scan(text)[0]


def _looks_marker_ish(text: str) -> bool:
    if re.search(r"<{3,}[ \t]*SEARCH|>{3,}[ \t]*REPLACE|<{5,}|>{5,}", text):
        return True
    return "SEARCH" in text and "REPLACE" in text


def apply_search_replace(source: str, text: str):
    """Apply `text`'s SEARCH/REPLACE blocks to `source`. -> (new_source | None, reason).

    reason is one of:
      applied            — every block's SEARCH text was found and replaced.
      no_block           — no block, and nothing marker-like: the model ignored the format.
      malformed_markers  — markers clearly intended but the triple is broken (a prompt/template
                           problem, unlike no_block).
      search_not_found   — THE GEMMA CASE: the block is well-formed but its SEARCH text does not
                           literally occur in the file, so aider rejects the edit and retries
                           forever (docs/campaign-results.md:434 — 2h, 0 exercises, identical
                           8126-token generations).

    Matching is LITERAL. aider's real applier has whitespace-flexible fallbacks, so this probe
    errs on the strict side; that is the safe direction for a gate (a `search_not_found` verdict
    should be eyeballed via the captured raw block before it is believed).

    Duplicate SEARCH texts collapse to their LAST occurrence: a thinking model commonly drafts a
    block, criticises it, then emits the final one — applying both would fail the second (its
    SEARCH is already gone) and report a bogus search_not_found. Distinct blocks ALL apply, as
    aider does within one response.
    """
    blocks, saw_marker = _scan(text)
    if not blocks:
        if saw_marker or _looks_marker_ish(_norm(text)):
            return None, "malformed_markers"
        return None, "no_block"
    deduped = {}
    for b in blocks:                       # dict preserves insertion order; re-inserting a key
        deduped.pop(b["search"], None)     # keeps the LAST occurrence's position and body
        deduped[b["search"]] = b
    cur = _norm(source)
    for b in deduped.values():
        if not b["search"] or b["search"] not in cur:
            return None, "search_not_found"
        cur = cur.replace(b["search"], b["replace"], 1)
    return cur, "applied"


def fenced_blocks(text: str) -> list:
    """Contents of every ```-fenced block, CRLF-normalised."""
    return [m.group(1) for m in _FENCE_RE.finditer(_norm(text))]


def _whole_verdict(content: str):
    """(ok, failure_reason) for the `whole` format: did the model return a complete fenced file
    that parses as python? Syntax is the only thing checked — `whole` fails in practice not by
    bad diffs but by TRUNCATION (the gemma-MoE burned its whole 32768 output budget on thinking
    and emitted ~0 answer, campaign-results.md:443-448), and a truncated file does not parse."""
    blocks = [b for b in fenced_blocks(content) if b.strip()]
    if not blocks:
        return False, "no_code_block"
    try:
        ast.parse(blocks[-1])              # the LAST block: earlier ones are drafts/quotes
    except SyntaxError:
        return False, "syntax_error"
    return True, None


def diff_prompt(source: str = None, filename: str = FIXTURE_NAME,
                instruction: str = EDIT_INSTRUCTION) -> str:
    src = FIXTURE_SRC if source is None else source
    return (f"Here is the complete contents of `{filename}`:\n\n"
            f"```python\n{src}```\n\n"
            f"Make this change: {instruction}.\n\n"
            "Reply with EXACTLY ONE aider-style SEARCH/REPLACE block and nothing else after it. "
            "Format it exactly like this, with the filename on the line before the fence:\n\n"
            f"{filename}\n```python\n<<<<<<< SEARCH\n"
            "the exact lines to find, copied VERBATIM from the file above\n=======\n"
            "the replacement lines\n>>>>>>> REPLACE\n```\n\n"
            "The SEARCH text must match the file character for character, including indentation.")


def whole_prompt(source: str = None, filename: str = FIXTURE_NAME,
                 instruction: str = EDIT_INSTRUCTION) -> str:
    src = FIXTURE_SRC if source is None else source
    return (f"Here is the complete contents of `{filename}`:\n\n"
            f"```python\n{src}```\n\n"
            f"Make this change: {instruction}.\n\n"
            "Reply with the ENTIRE updated file in a single ```python code block — the whole "
            "file, not just the changed lines, and no elisions or '# ...' placeholders.")


def _truncate(text: str, limit: int = RAW_MAX_CHARS) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [truncated {len(text) - limit} chars]"


def check_edit_format(driver, model: str, params: dict, fixture=None) -> dict:
    """Can `model` drive aider's `diff` (SEARCH/REPLACE) format, or does it need `whole`?

    WHY. `docs/campaign-results.md:434`: `gemma-4-31b-it-6bit` ran the agentic Aider axis at
    `edit_format: diff` and got STUCK — 0 exercises in 2 hours on exercise 1, repeated identical
    8126-token generations — because its SEARCH/REPLACE blocks did not apply (aider's "misapplies
    edits" retry loop). Switching that model to `edit_format: whole` fixed it. Two hours of a
    scarce 64GB box to discover what these two probes answer in ~5 minutes.

    And it is live again: the M1 agentic head-to-head runs the qwen-arch pair on `diff` and gemma
    on `whole`, which CONFOUNDS the cross-family comparison (docs/lab-notebook.md (2026-08-16 salvage section)). So
    this runs BEFORE the head-to-head and each model's format is set from ITS OWN evidence, not
    from a family assumption.

    Returns {"diff": bool, "whole": bool, "diff_failure": reason|None, "raw": <truncated diff
    response>, "whole_failure": reason|None, "recommended_format": "diff"|"whole"|None,
    "note": str|None}. BOTH formats are probed every time even when `diff` works: the fallback
    has to be known-good before a run commits to it.

    `raw` is captured (truncated to a few KB) precisely so a failure is diagnosable — a bare
    False is what made the gemma episode a two-hour mystery. `fixture` overrides the source
    module: a `pathlib.Path` is read, a str is used as the source text itself.
    """
    if hasattr(fixture, "read_text"):
        src = fixture.read_text()
    else:
        src = fixture or FIXTURE_SRC
    p = dict(params or {})
    res = {"diff": False, "whole": False, "diff_failure": None, "whole_failure": None,
           "raw": "", "recommended_format": None, "note": None, "model": model}
    notes = []

    def _ask(prompt):
        return driver.complete(model, [{"role": "user", "content": prompt}], p)

    try:
        r = _ask(diff_prompt(src))
        content = r.get("content") or ""
        res["raw"] = _truncate(content)
        _, reason = apply_search_replace(src, content)
        res["diff"] = reason == "applied"
        res["diff_failure"] = None if res["diff"] else reason
    except AssertionError:                      # never swallow a test fake's exhaustion guard
        raise
    except Exception as e:                      # noqa: BLE001 - degrade, don't crash the gate
        res["diff_failure"] = "probe_error"
        notes.append(f"diff probe failed: {type(e).__name__}: {e}")

    try:
        r = _ask(whole_prompt(src))
        res["whole"], res["whole_failure"] = _whole_verdict(r.get("content") or "")
    except AssertionError:
        raise
    except Exception as e:                      # noqa: BLE001
        res["whole_failure"] = "probe_error"
        notes.append(f"whole probe failed: {type(e).__name__}: {e}")

    res["recommended_format"] = "diff" if res["diff"] else ("whole" if res["whole"] else None)
    res["note"] = "; ".join(notes) or None
    print(f"[preflight] edit-format model={model} diff={res['diff']} "
          f"({res['diff_failure']}) whole={res['whole']} ({res['whole_failure']}) "
          f"-> edit_format={res['recommended_format']}", flush=True)
    if not res["diff"] and res["raw"]:
        print(f"[preflight] raw diff response (truncated):\n{res['raw']}", flush=True)
    return res


def parse_args(argv=None) -> dict:
    """CLI args. `--profile` defaults to `production` so preflight.sh's existing single-argument
    invocation is byte-for-byte unchanged."""
    import argparse
    ap = argparse.ArgumentParser(prog="preflight.py")
    ap.add_argument("model", help="registered model name (GET /v1/models)")
    ap.add_argument("--profile", default="production", choices=model_params.profile_names(),
                    help="sampling profile the RUN will use (default: production)")
    ap.add_argument("--edit-format", action="store_true",
                    help="also probe aider diff-vs-whole edit format for this model")
    ns = ap.parse_args(argv)            # argv=None -> argparse reads sys.argv[1:]
    return {"model": ns.model, "profile": ns.profile, "edit_format": ns.edit_format}


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    res = run_canary(args["model"], profile=args["profile"])
    if not res["ok"]:
        print("[preflight] FAIL — stack NOT sane (loop / truncation / no code). "
              "Do NOT run; restart the router and re-check the model/quant.", flush=True)
        sys.exit(1)
    print(f"[preflight] PASS — stack sane at profile={res['profile']}, "
          "safe to run the benchmark.", flush=True)
    if args["edit_format"]:
        ef = check_edit_format(bench_driver.MlxServeDriver(), args["model"], res["params"])
        if ef["recommended_format"] is None:
            print("[preflight] FAIL — neither `diff` nor `whole` produced a usable edit; "
                  "inspect the raw block above before running the agentic axis.", flush=True)
            sys.exit(1)
        print(f"[preflight] edit_format for {args['model']}: {ef['recommended_format']} "
              "— set this in the aider settings / registry notes before the agentic run.",
              flush=True)


if __name__ == "__main__":
    main()
