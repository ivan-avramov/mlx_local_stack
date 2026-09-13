"""Blind mixed-family pairwise judge panel for role C (M38) — `docs/judge-panel-c.md`
"Panel and protocol". Builds the candidate model-pair comparisons, merges them with the
`judge_anchors` control pairs, and runs every pair in BOTH orders through every judge.

Backends reuse `bench.judge`'s call SHAPE (model ids, adaptive-thinking Anthropic call, the
one-shot `codex exec` invocation) but NOT its functions directly: `judge.anthropic_judge` /
`judge.codex_judge` are intentionally graceful-degrade (ANY exception, including a transport
error, is swallowed to `None`) for the code-quality panel's use case. This panel's spec requires
the opposite: a transport failure retries up to twice with backoff and then ESCALATES (raises) —
never gets written as a graded null row. `_anthropic_call`/`_codex_call` below are that
call shape MINUS the swallow; `judge.DEFAULT_JUDGES`' model ids (`claude-opus-5`,
`claude-sonnet-5`) are the ones used here too.
"""
import hashlib
import json
import os
import random
import re
import subprocess
import time
from itertools import combinations

from . import judge as _judge

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")

# Family tokens beyond the four exact registry names — a candidate can leak its lineage
# through prose ("this Qwen-based model...") without ever printing the full registry
# string, so these are redacted case-insensitively as whole words. AGENTS.md full-name
# rule is about docs/commits/prose; this is the runtime blinding list and is deliberately
# broader than any 4-model run (family + vendor + repackager tokens).
FAMILY_TOKENS = ("Qwen", "Alibaba", "NVIDIA", "Nemotron", "Ornith", "Fable", "OptiQ",  # allow-shorthand
                  "TeichAI", "unsloth", "mlx-community")
# A trailing version suffix is part of the token: `\b` alone does not fire between "Qwen" and
# "3", so `qwen3` / `Qwen3-8B` / `qwen3-next` survived as an identity leak (cold review 2026-09-11).
_FAMILY_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in FAMILY_TOKENS) + r")(?:[0-9][\w.\-]*)?\b",
    re.IGNORECASE)

# Template/reasoning-tag artifacts that identify the SERVING PATH (and sometimes the model
# family) rather than content. `</?think>` matches an orphan closing tag too — `client._THINK`
# in bench/client.py only strips PAIRED `<think>...</think>` blocks, so a truncated/malformed
# generation can leave an orphan `</think>` in committed rows; the blinder must not rely on
# pairing.
_TEMPLATE_TAG_RE = re.compile(r"</?think>|◁/?think▷|<\|[^|]*\|>", re.IGNORECASE)

RUBRIC_SYSTEM_PROMPT = (
    "You are judging the research/design quality of two candidate responses to the same "
    "prompt. Judge ONLY: soundness of reasoning, depth and insight, structure and clarity, "
    "actionability, and calibrated uncertainty. Ignore length except where it hurts clarity. "
    "The responses are labeled A and B; all identifying information has been removed. "
    'Reply with ONLY a JSON object: {"choice": "A"|"B"|"tie", "rationale": "<one paragraph>"}. '
    "No prose outside the JSON."
)
PROMPT_SHA = hashlib.sha256(RUBRIC_SYSTEM_PROMPT.encode()).hexdigest()

ORDERS = ("AB", "BA")


# --------------------------------------------------------------------------------- blinding
class BlindingLeak(RuntimeError):
    """An identifying token survived blinding. Raised, never logged-and-continued: a leaked
    model name reaching a judge invalidates that call's blindness, and the panel's whole
    premise is that judges cannot infer identity."""


def _leaks(text, model_names):
    leaks = [n for n in model_names if n and n in text]
    if _FAMILY_RE.search(text):
        leaks.append("family-token")
    if _TEMPLATE_TAG_RE.search(text):
        leaks.append("template-tag")
    return leaks


def strip_model_names(text, model_names):
    """Blind a text for judging WITHOUT destroying its markdown structure. The rubric scores
    "structure and clarity", and the `degrade` anchor's whole mechanism is flattening
    headings/lists into run-on prose — a blinder that ALSO flattens every candidate's
    structure (the original bug: `" ".join(text.split())` joined every line) would erase that
    signal for every real pair, not just anchors.

    Redaction order: (1) the four exact registry names, longest first, so one name that is a
    substring of another (e.g. a bare arch name vs. the full quant tag) is not half-replaced;
    (2) case-insensitive whole-word `FAMILY_TOKENS`; (3) template/reasoning-tag artifacts
    (`_TEMPLATE_TAG_RE`, orphan `</think>` included). Formatting: per-LINE `rstrip()` only —
    lines are NEVER joined — and runs of >=3 blank lines collapse to 2 (cosmetic only).

    Raises `BlindingLeak` if any exact name / family token / template tag still matches the
    output — a leak must abort the call, never ship unblinded text to a judge. `text` may be
    None/empty (passed through, nothing to leak)."""
    if not text:
        return text
    out = text
    for name in sorted((n for n in model_names if n), key=len, reverse=True):
        out = out.replace(name, "[REDACTED]")
    out = _FAMILY_RE.sub("[REDACTED]", out)
    out = _TEMPLATE_TAG_RE.sub("", out)

    lines = [ln.rstrip() for ln in out.split("\n")]
    collapsed, blank_run = [], 0
    for ln in lines:
        if ln == "":
            blank_run += 1
            if blank_run <= 2:
                collapsed.append(ln)
        else:
            blank_run = 0
            collapsed.append(ln)
    out = "\n".join(collapsed).strip("\n")

    leaks = _leaks(out, model_names)
    if leaks:
        raise BlindingLeak(f"strip_model_names: blinding leak survived: {leaks}")
    return out


# ------------------------------------------------------------------------- candidate pairs
def load_model_rows(models, tune="m38", results_dir=RESULTS):
    """Read `<results_dir>/<model>/cjudge.<tune>.jsonl` for each model. Returns
    {model: [row, ...]}. A missing file yields an empty list for that model (graceful-degrade:
    callers that need every model present, like `build_candidate_pairs`, will simply find no
    shared items rather than crashing on one late generation job)."""
    out = {}
    for model in models:
        path = os.path.join(results_dir, model, f"cjudge.{tune}.jsonl")
        rows = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
        out[model] = rows
    return out


def load_manifest_for(model, tune, results_dir=RESULTS):
    """The generation manifest for one (model, tune)'s cjudge rows (M40 `--pair-tunes`
    guard rails), or None if missing/unparseable — graceful-degrade, same convention as
    `load_model_rows`: a CLI print/guard must not crash on an old run with no manifest."""
    path = os.path.join(results_dir, model, f"cjudge.{tune}.manifest.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def shared_converged_items(rows_by_model):
    """Item ids CONVERGED in every model's rows (the only items eligible for a fair pairwise
    comparison — AGENTS.md apples-to-apples). Empty input -> empty set."""
    sets = [{r["id"] for r in rows if r.get("converged")} for rows in rows_by_model.values()]
    if not sets:
        return set()
    shared = sets[0]
    for s in sets[1:]:
        shared &= s
    return shared


def _sub_rng(seed, *parts):
    """A Random instance derived from (seed, *parts) via blake2b (not Python's salted
    `hash()`) — reproducible across processes/runs, independent of dict/combinations
    iteration order (rowschema.sample_seed uses the same construction for the same reason)."""
    h = hashlib.blake2b(("\x00".join(str(p) for p in (seed, *parts))).encode(), digest_size=8)
    return random.Random(int.from_bytes(h.digest(), "big"))


def _balanced_flags(n, rng):
    """n//2 True + the remainder False, order shuffled by `rng` — exactly balanced placement
    within a group of n, still seed-dependent (mirrors `judge_anchors._balanced_flags`)."""
    half = n // 2
    flags = [True] * half + [False] * (n - half)
    rng.shuffle(flags)
    return flags


def build_candidate_pairs(rows_by_model, seed=38):
    """One pair per (unordered model pair, shared converged item) across ALL C(4,2)=6 model
    pairs. A/B model assignment is BALANCED per model pair (exactly half its items swapped,
    seeded, not just independently coin-flipped) so the winner is never correlated with a
    fixed slot even at small item counts. Schema matches `judge_anchors.build_anchor_pairs`
    exactly (`anchor_type`/`expected` are None for a real candidate pair — there is no ground
    truth to check it against)."""
    models = sorted(rows_by_model)
    if len(models) < 2:
        raise ValueError(f"build_candidate_pairs: need >= 2 models, got {models}")
    items = sorted(shared_converged_items(rows_by_model))
    lookup = {m: {r["id"]: r for r in rows} for m, rows in rows_by_model.items()}
    pairs = []
    for m1, m2 in combinations(models, 2):
        flags = _balanced_flags(len(items), _sub_rng(seed, m1, m2))
        for item_id, swap in zip(items, flags):
            r1, r2 = lookup[m1][item_id], lookup[m2][item_id]
            model_a, model_b = (m2, m1) if swap else (m1, m2)
            row_a, row_b = (r2, r1) if swap else (r1, r2)
            pairs.append({
                "pair_id": f"cand-{m1}__{m2}-{item_id}",
                "anchor_type": None,
                "item_id": item_id,
                "a_key": f"{model_a}::{item_id}",
                "b_key": f"{model_b}::{item_id}",
                "a_text": row_a.get("content", "") or "",
                "b_text": row_b.get("content", "") or "",
                "expected": None,
            })
    return pairs


def build_tune_pairs(model, tune_a, tune_b, rows_a, rows_b, seed=38):
    """One candidate pair per shared-converged item comparing the SAME model at two TUNES
    (`--pair-tunes TUNE_A TUNE_B`, M40: a predictor ON-vs-OFF judge pass) instead of two
    different models. Same balanced A/B slot assignment as `build_candidate_pairs` (exactly
    half the items swapped, seeded on the two identities) — but keyed on `<model>@<tune>`
    identities, and pair_id / a_key / b_key fix the CALLER's tune_a/tune_b order rather than
    sorting alphabetically: which tune is "A" and which is "B" here is ON-vs-OFF, an
    experiment design choice, not an arbitrary pair of model names to canonicalize."""
    key_a, key_b = f"{model}@{tune_a}", f"{model}@{tune_b}"
    items = sorted(shared_converged_items({key_a: rows_a, key_b: rows_b}))
    lookup_a = {r["id"]: r for r in rows_a}
    lookup_b = {r["id"]: r for r in rows_b}
    flags = _balanced_flags(len(items), _sub_rng(seed, key_a, key_b))
    pairs = []
    for item_id, swap in zip(items, flags):
        row_a, row_b = lookup_a[item_id], lookup_b[item_id]
        model_a, model_b = (key_b, key_a) if swap else (key_a, key_b)
        text_a, text_b = (row_b, row_a) if swap else (row_a, row_b)
        pairs.append({
            "pair_id": f"cand-{key_a}__{key_b}-{item_id}",
            "anchor_type": None,
            "item_id": item_id,
            "a_key": f"{model_a}::{item_id}",
            "b_key": f"{model_b}::{item_id}",
            "a_text": text_a.get("content", "") or "",
            "b_text": text_b.get("content", "") or "",
            "expected": None,
        })
    return pairs


def merge_and_shuffle(candidate_pairs, anchor_pairs, seed=38):
    """Concatenate candidate + anchor pairs and shuffle deterministically — the judges never
    see anchors and candidates in a predictable block."""
    merged = list(candidate_pairs) + list(anchor_pairs)
    random.Random(seed).shuffle(merged)
    return merged


# ------------------------------------------------------------------------------- verdict parse
_CHOICE_RE = re.compile(r'"choice"\s*:\s*"(A|B|a|b|tie|Tie|TIE)"')


def parse_verdict(text):
    """Brace-matched JSON parse of `{"choice": "A"|"B"|"tie", "rationale": ...}` (same
    brace-depth scan as `judge.parse_scores`, so trailing prose containing braces cannot
    corrupt the parse). Returns `{"choice": "A"|"B"|"tie"|None, "rationale": str|None}` —
    `choice: None` on anything unparseable, counted by the caller, never guessed at."""
    result = {"choice": None, "rationale": None}
    if not text:
        return result
    start = text.find("{")
    if start == -1:
        return result
    depth, end = 0, -1
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        # Unterminated object (truncated judge output): still recover an unambiguous choice.
        m = _CHOICE_RE.search(text[start:])
        if m:
            v = m.group(1)
            result["choice"] = "tie" if v.lower() == "tie" else v.upper()
        return result
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        # Lenient fallback (2026-09-12, wave 2): a judge's rationale with UNESCAPED inner
        # quotes breaks the JSON while the choice field itself is unambiguous. Recover only
        # the choice (rationale stays None); the raw text is kept on the row either way.
        m = _CHOICE_RE.search(text[start:end + 1])
        if m:
            v = m.group(1)
            result["choice"] = "tie" if v.lower() == "tie" else v.upper()
            result["rationale"] = None
        return result
    if not isinstance(obj, dict):
        return result
    raw = obj.get("choice")
    if isinstance(raw, str):
        v = raw.strip()
        if v.upper() in ("A", "B"):
            result["choice"] = v.upper()
        elif v.lower() == "tie":
            result["choice"] = "tie"
    rationale = obj.get("rationale")
    if isinstance(rationale, str):
        result["rationale"] = rationale
    return result


def normalize_choice(order, choice):
    """Map a judge's A/B choice back to the pair's CANONICAL a_key/b_key labeling. Order `AB`
    presented a_text as "A"; order `BA` presented b_text as "A" (swapped), so a `BA`-order
    choice of "A" means the pair's B side won. `tie`/None pass through unchanged."""
    if order == "BA" and choice in ("A", "B"):
        return {"A": "B", "B": "A"}[choice]
    return choice


def order_agreement_verdict(choice_ab_norm, choice_ba_norm):
    """Verdict per (pair, judge): the two orders' NORMALIZED choices, agreeing else `tie`
    (docs/judge-panel-c.md: "Verdict per (pair, judge) = agreement of the two orders, else
    tie"). Either side `None` (unparseable) counts as disagreement -> `tie`, never guessed."""
    if choice_ab_norm is None or choice_ba_norm is None:
        return "tie"
    return choice_ab_norm if choice_ab_norm == choice_ba_norm else "tie"


def panel_verdict(per_judge_verdicts):
    """Majority over judges' verdicts ("A"/"B"/"tie"); no strict majority -> "tie" (a 1-1-1
    three-way split, or any other tie for the top count, has no winner)."""
    counts = {}
    for v in per_judge_verdicts:
        counts[v] = counts.get(v, 0) + 1
    if not counts:
        return "tie"
    best = max(counts.values())
    winners = [k for k, c in counts.items() if c == best]
    return winners[0] if len(winners) == 1 else "tie"


# ------------------------------------------------------------------------------------ prompts
def build_user_prompt(task_prompt, first_text, second_text):
    """The blinded pairwise user message for one ORDER: `first_text` is shown as "A",
    `second_text` as "B" — the caller decides which underlying side goes first."""
    return (f"## Prompt\n{task_prompt}\n\n## Response A\n{first_text}\n\n"
            f"## Response B\n{second_text}\n\nWhich response is better? "
            "Reply with ONLY the JSON object.")


# --------------------------------------------------------------------------------- backends
# 16000 (not the code-quality panel's 4096): adaptive thinking on claude-opus-5 routinely
# spends its budget before emitting the closing JSON at 4096, which truncates the response ->
# choice:null -> counted as BOTH a tie and an order flip in the gate, so an under-sized
# max_tokens can fail the reliability gate on a client setting, not a model property.
_JUDGE_MAX_TOKENS = 16000
# Installed SDK (anthropic 0.111.0) accepts `output_config` on messages.create — verified via
# `inspect.signature`. "low" effort keeps the judge's own reasoning cheap; it is not scored,  # allow-shorthand
# only the final JSON verdict is.
_JUDGE_OUTPUT_CONFIG = {"effort": "low"}  # allow-shorthand
# stop_reason values that mean "the model didn't finish", not "the model declined to choose".
# These get a distinct null_reason instead of being silently folded into ordinary parse failure.
_TRUNCATION_STOP_REASONS = ("max_tokens", "refusal")


def _anthropic_call(model_id, system, user, client=None, max_tokens=_JUDGE_MAX_TOKENS,
                     output_config=_JUDGE_OUTPUT_CONFIG):
    """Same call shape as `judge.anthropic_judge` (adaptive thinking, no sampling params) —
    but RAISES on any error instead of degrading to None. Returns
    (text, usage_dict|None, stop_reason|None)."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    kwargs = dict(model=model_id, max_tokens=max_tokens, system=system,
                  messages=[{"role": "user", "content": user}],
                  thinking={"type": "adaptive"})
    if output_config is not None:
        kwargs["output_config"] = output_config
    resp = client.messages.create(**kwargs)
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
    usage = getattr(resp, "usage", None)
    usage_dict = None
    if usage is not None:
        usage_dict = {"input_tokens": getattr(usage, "input_tokens", None),
                      "output_tokens": getattr(usage, "output_tokens", None)}
    stop_reason = getattr(resp, "stop_reason", None)
    return text, usage_dict, stop_reason


CODEX_MODEL = os.environ.get("M38_CODEX_MODEL", "gpt-5.6-terra")  # operator choice 2026-09-12
CODEX_EFFORT = os.environ.get("M38_CODEX_EFFORT", "medium")


def _codex_call(system, user, runner=subprocess.run, model=None, effort=None):
    """Same call shape as `judge.codex_judge` (one-shot `codex exec`) — but RAISES on a
    nonzero exit / launch failure instead of degrading to None. No token usage and no
    stop_reason concept for this backend (both always None -> cost log records `null`,
    never a fabricated 0). The model and reasoning effort are PINNED explicitly (`-m`,
    `-c model_reasoning_effort=`): the 2026-09-12 first run passed neither and silently
    used the operator's codex default (gpt-6-astra, high) under a "gpt-5.5" label."""
    model = model or CODEX_MODEL
    effort = effort or CODEX_EFFORT
    prompt = f"{system}\n\n{user}"
    proc = runner(["codex", "exec", "-m", model, "-c", f"model_reasoning_effort={effort}",
                   "--skip-git-repo-check", prompt],
                  capture_output=True, text=True, timeout=300)
    if getattr(proc, "returncode", 1) != 0:
        raise RuntimeError(f"codex exec failed rc={getattr(proc, 'returncode', None)} "
                           f"stderr={getattr(proc, 'stderr', '')[:200]!r}")
    return getattr(proc, "stdout", "") or "", None, None


def default_judge_fns():
    """{"opus"/"sonnet"/"gpt-5.5": (system, user) -> (text, usage|None, stop_reason|None)} —  # allow-shorthand
    same Anthropic model ids as `judge.DEFAULT_JUDGES` (claude-opus-5 / claude-sonnet-5), plus
    GPT-5.5 via codex. Lazy: the anthropic import only happens on first real call."""
    return {
        "opus": lambda s, u: _anthropic_call("claude-opus-5", s, u),  # allow-shorthand
        "sonnet": lambda s, u: _anthropic_call("claude-sonnet-5", s, u),
        f"codex:{CODEX_MODEL}:{CODEX_EFFORT}": _codex_call,
    }


# --------------------------------------------------------------------------------- resumable
def load_done_keys(verdicts_path):
    """{(pair_id, order, judge)} already persisted in `verdicts_path` — the resume set. A
    missing file or unreadable line is treated as "nothing done" for that line (never crashes
    a resume on a previous partial write)."""
    done = set()
    if not os.path.exists(verdicts_path):
        return done
    with open(verdicts_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            done.add((row.get("pair_id"), row.get("order"), row.get("judge")))
    return done


def judge_families(judges):
    """{judge_name: family|None} via `judge._FAMILY` (the same mapping `judge.py`'s
    code-quality panel uses to detect a mixed-family split) — shared here so the CLI's
    single-family guard and the ranking's per-family preference split use one source of
    truth for "which family is this judge in"."""
    fam = {}
    for j in judges:
        fam[j] = "openai" if j.startswith("codex:") else _judge._FAMILY.get(j)
    return fam


def iter_calls(pairs, judges):
    """Every (pair, order, judge) triple — both orders, every judge, every pair."""
    for pair in pairs:
        for order in ORDERS:
            for judge_name in judges:
                yield pair, order, judge_name


# ------------------------------------------------------------------------------------ runner
class TransportEscalation(RuntimeError):
    """Raised when a judge call still fails after its retry budget. Never caught by the
    runner — it is meant to abort the process (AGENTS.md: transport failures escalate, they
    are never graded)."""


def _unpack_result(result):
    """A judge fn returns (text,), (text, usage) or (text, usage, stop_reason) — accept all
    three arities (older mocks/tests use the shorter forms) or a bare string."""
    if isinstance(result, tuple):
        if len(result) >= 3:
            return result[0], result[1], result[2]
        if len(result) == 2:
            return result[0], result[1], None
        return (result[0] if result else None), None, None
    return result, None, None


def call_judge(pair, order, judge_name, judge_fns, task_prompt, model_names,
                retries=2, backoff=1.0, sleep=None, cost_log=None):
    """Run one (pair, order, judge) call, blinded, and return the verdict row (without `ts` —
    the caller stamps that so tests stay time-independent). Retries up to `retries` times with
    exponential backoff on ANY exception from the judge fn, then raises `TransportEscalation`
    (never writes a graded null for a transport failure). A response that stopped on
    `_TRUNCATION_STOP_REASONS` (max_tokens/refusal) is a DISTINCT null: `choice: None,
    null_reason: <stop_reason>` — still not a transport failure, so still graded, but
    distinguishable in the gate/report from an ordinary unparseable response."""
    sleep = sleep or time.sleep
    a_text = strip_model_names(pair["a_text"], model_names)
    b_text = strip_model_names(pair["b_text"], model_names)
    first, second = (a_text, b_text) if order == "AB" else (b_text, a_text)
    user = build_user_prompt(task_prompt, first, second)
    fn = judge_fns[judge_name]

    last_exc = None
    raw, usage, stop_reason = None, None, None
    for attempt in range(retries + 1):
        try:
            raw, usage, stop_reason = _unpack_result(fn(RUBRIC_SYSTEM_PROMPT, user))
            last_exc = None
            break
        except Exception as exc:  # noqa: BLE001 — retried, then escalated below
            last_exc = exc
            if attempt < retries:
                sleep(backoff * (2 ** attempt))
    if last_exc is not None:
        raise TransportEscalation(
            f"{judge_name} {pair['pair_id']} order={order} failed after "
            f"{retries} retries: {last_exc}") from last_exc

    if cost_log is not None:
        # input_tokens/output_tokens start at None ("unknown"), not 0: a backend that never
        # reports usage (codex) must stay `null` in the cost log forever, never read as "0
        # tokens spent" — 0 and unknown are different claims.
        c = cost_log.setdefault(judge_name,
                                {"calls": 0, "input_tokens": None, "output_tokens": None})
        c["calls"] += 1
        if usage:
            c["input_tokens"] = (c["input_tokens"] or 0) + (usage.get("input_tokens") or 0)
            c["output_tokens"] = (c["output_tokens"] or 0) + (usage.get("output_tokens") or 0)

    parsed = parse_verdict(raw)
    choice = parsed["choice"]
    null_reason = None
    if stop_reason in _TRUNCATION_STOP_REASONS:
        choice = None
        null_reason = stop_reason
    return {
        "pair_id": pair["pair_id"], "anchor_type": pair.get("anchor_type"),
        "item_id": pair["item_id"], "a_key": pair["a_key"], "b_key": pair["b_key"],
        "order": order, "judge": judge_name, "prompt_sha": PROMPT_SHA,
        "raw": raw, "choice": choice, "null_reason": null_reason, "stop_reason": stop_reason,
        "transport": "api",
    }


def run_pairwise(pairs, judges, judge_fns, task_prompts, model_names, verdicts_path,
                  retries=2, backoff=1.0, sleep=None, cost_log=None, limit_calls=None,
                  now=None):
    """Drive every (pair, order, judge) call not already in `verdicts_path`, appending each
    verdict row immediately (resumable: a crash mid-run loses at most the in-flight call).
    `task_prompts` is {item_id: prompt_text}; a missing item_id degrades to an empty prompt
    string rather than crashing (the judge still sees the two responses). Returns the number
    of calls made. Raises `TransportEscalation` on an exhausted-retry transport failure —
    the caller must let that propagate (never catch-and-grade)."""
    now = now or time.time
    done = load_done_keys(verdicts_path)
    os.makedirs(os.path.dirname(verdicts_path) or ".", exist_ok=True)
    made = 0
    with open(verdicts_path, "a", encoding="utf-8") as f:
        for pair, order, judge_name in iter_calls(pairs, judges):
            key = (pair["pair_id"], order, judge_name)
            if key in done:
                continue
            if limit_calls is not None and made >= limit_calls:
                break
            task_prompt = task_prompts.get(pair["item_id"], "")
            row = call_judge(pair, order, judge_name, judge_fns, task_prompt, model_names,
                             retries=retries, backoff=backoff, sleep=sleep, cost_log=cost_log)
            row["ts"] = now()
            f.write(json.dumps(row) + "\n")
            f.flush()
            made += 1
    return made


# ------------------------------------------------------------------- subagent packet export/ingest
# Operator decision 2026-09-12: `opus`/`sonnet` are run as Claude Code SUBAGENTS, not API calls  # allow-shorthand
# (GPT-5.5 stays on the in-process `codex exec` path above). These functions build the identical
# blinded (pair, order) list the API path would run and hand it to a subagent as a markdown
# packet instead of a live call; ingest reads the subagent's verdict file back and reshapes it
# into the SAME row schema `call_judge`/`run_pairwise` write, plus `transport` distinguishing the
# two paths (`"api"` vs `"subagent"`).
VERDICT_JSON_INSTRUCTION = (
    'Write your verdict to `{pkt}.verdict.json` in this SAME directory, as EXACTLY one JSON '
    'object: {{"choice": "A"|"B"|"tie", "rationale": "<one paragraph>"}}. No other content in '
    "that file, and do not open, read, or modify any other file (including `manifest.jsonl` — "
    "it identifies the models and would un-blind you)."
)


def build_packet_markdown(system, user, pkt):
    """The blind judge packet for one (pair, order, judge): a `# SYSTEM` block (rubric
    verbatim), a `# USER` block (the rendered pairwise prompt — same `build_user_prompt` output
    the API path sends), then a final instruction line naming the exact verdict filename to
    write. Contains no pair_id/anchor_type/expected/model name — only `pkt` (an opaque id)."""
    return (f"# SYSTEM\n{system}\n\n"
            f"# USER\n{user}\n\n"
            f"---\n{VERDICT_JSON_INSTRUCTION.format(pkt=pkt)}\n")


def _pkt_id(counter, width):
    return f"p{counter:0{width}d}"


def _order_batches(pairs, batch_size):
    """One order's (pair, order) entries chunked into `batch_size`-sized batches, in the given
    pair order (already seeded via `merge_and_shuffle` — anchors and candidates arrive
    pre-mixed)."""
    return [pairs[i:i + batch_size] for i in range(0, len(pairs), batch_size)]


def _judge_readme_text():
    return (
        "# Judge subagent instructions\n\n"
        "You have been assigned one or more `batchNN/` directories under your judge directory, "
        "each containing packet files named `pNNNN.md`.\n\n"
        "For EACH `.md` packet file in your assigned batch directory:\n\n"
        "1. Read ONLY that packet file. Never open, read, or modify any other file in this "
        "directory tree — in particular, never read `manifest.jsonl` (it names the models and "
        "would un-blind you), and never modify the packet `.md` file itself.\n"
        "2. Use the `# SYSTEM` block as your rubric and the `# USER` block as the task; judge "
        "exactly as instructed there.\n"
        "3. Write your verdict to the `.verdict.json` file named at the bottom of the packet, "
        "in the same directory, containing EXACTLY one JSON object: "
        '{"choice": "A"|"B"|"tie", "rationale": "<one paragraph>"}. No other content.\n'
    )


def export_packets(pairs, judges, task_prompts, model_names, out_dir, batch_size=10):
    """Write one markdown packet per (pair, order, judge) at
    `out_dir/<judge>/batch<NN>/<pkt>.md`, plus `out_dir/manifest.jsonl` (private — never shown
    to a judge) and `out_dir/README_JUDGE.md`. No judge is called.

    Batching: AB entries and BA entries of the SAME judge are chunked into SEPARATE batch
    sequences (all-AB batches first, then all-BA batches) — a pair's two orders can therefore
    never land in the same batch regardless of how `len(pairs)` relates to `batch_size` (a
    concatenate-then-chunk scheme fails this for small pair counts: with N pairs <= batch_size,
    every AB AND BA entry would land in the single batch 0). Candidate and anchor pairs stay
    mixed within each order's sequence because `pairs` is already seed-shuffled by the caller
    (`merge_and_shuffle`). Returns the list of manifest rows written."""
    total = len(judges) * len(pairs) * 2
    width = max(4, len(str(max(total - 1, 0))))
    counter = 0
    manifest_rows = []
    os.makedirs(out_dir, exist_ok=True)
    for judge_name in judges:
        ab_batches = _order_batches([(p, "AB") for p in pairs], batch_size)
        ba_batches = _order_batches([(p, "BA") for p in pairs], batch_size)
        for batch_idx, batch in enumerate(ab_batches + ba_batches):
            batch_dir = os.path.join(out_dir, judge_name, f"batch{batch_idx:02d}")
            os.makedirs(batch_dir, exist_ok=True)
            for pair, order in batch:
                pkt = _pkt_id(counter, width)
                counter += 1
                a_text = strip_model_names(pair["a_text"], model_names)
                b_text = strip_model_names(pair["b_text"], model_names)
                first, second = (a_text, b_text) if order == "AB" else (b_text, a_text)
                task_prompt = task_prompts.get(pair["item_id"], "")
                user = build_user_prompt(task_prompt, first, second)
                pkt_path = os.path.join(batch_dir, f"{pkt}.md")
                with open(pkt_path, "w", encoding="utf-8") as f:
                    f.write(build_packet_markdown(RUBRIC_SYSTEM_PROMPT, user, pkt))
                manifest_rows.append({
                    "pkt": pkt, "judge": judge_name, "pair_id": pair["pair_id"],
                    "order": order, "anchor_type": pair.get("anchor_type"),
                    "expected": pair.get("expected"), "item_id": pair["item_id"],
                    "a_key": pair["a_key"], "b_key": pair["b_key"],
                    "prompt_sha": PROMPT_SHA, "path": pkt_path,
                })
    manifest_path = os.path.join(out_dir, "manifest.jsonl")
    with open(manifest_path, "w", encoding="utf-8") as f:
        for row in manifest_rows:
            f.write(json.dumps(row) + "\n")
    with open(os.path.join(out_dir, "README_JUDGE.md"), "w", encoding="utf-8") as f:
        f.write(_judge_readme_text())
    return manifest_rows


def load_manifest(out_dir):
    """Read `out_dir/manifest.jsonl` written by `export_packets`."""
    path = os.path.join(out_dir, "manifest.jsonl")
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def ingest_packets(out_dir, now=None):
    """Read every `<pkt>.verdict.json` the manifest points at (if present), validate via
    `parse_verdict` (unparseable/garbage -> `choice: None, null_reason: "unparseable"`), and
    return `(rows, report)`:

      - `rows`: verdict rows in the SAME schema `call_judge`/`run_pairwise` write (pair_id,
        anchor_type, item_id, a_key, b_key, order, judge, prompt_sha, raw, choice, null_reason,
        stop_reason, transport, ts) — `stop_reason`/`transport` are the fixed literal
        `"subagent"` for every row (there is no model-reported stop reason on this path).
      - `report`: `{"judges": {judge: {batch_name: {"expected": n, "present": n}}},
        "missing": [{"pkt", "judge", "path"}, ...]}` — a missing verdict file is counted and
        skipped, never crashes the ingest.

    Does NOT write to `verdicts.jsonl` itself (see `append_new_verdicts`) and does not consult
    it for idempotency — callers combine the two."""
    now = now or time.time
    manifest_rows = load_manifest(out_dir)
    report = {"judges": {}, "missing": []}
    rows = []
    for row in manifest_rows:
        judge_name = row["judge"]
        batch_name = os.path.basename(os.path.dirname(row["path"]))
        brep = report["judges"].setdefault(judge_name, {}).setdefault(
            batch_name, {"expected": 0, "present": 0})
        brep["expected"] += 1
        verdict_path = os.path.join(os.path.dirname(row["path"]), f"{row['pkt']}.verdict.json")
        if not os.path.exists(verdict_path):
            report["missing"].append({"pkt": row["pkt"], "judge": judge_name, "path": verdict_path})
            continue
        brep["present"] += 1
        with open(verdict_path, encoding="utf-8") as f:
            raw = f.read()
        choice = parse_verdict(raw)["choice"]
        rows.append({
            "pair_id": row["pair_id"], "anchor_type": row["anchor_type"],
            "item_id": row["item_id"], "a_key": row["a_key"], "b_key": row["b_key"],
            "order": row["order"], "judge": judge_name, "prompt_sha": row["prompt_sha"],
            "raw": raw, "choice": choice,
            "null_reason": None if choice is not None else "unparseable",
            "stop_reason": "subagent", "transport": "subagent", "ts": now(),
        })
    return rows, report


def append_new_verdicts(rows, verdicts_path):
    """Append `rows` to `verdicts_path`, skipping any whose (pair_id, order, judge) key is
    already present (idempotent: re-ingesting after more verdict files land only adds the new
    ones). Returns the count actually appended."""
    done = load_done_keys(verdicts_path)
    os.makedirs(os.path.dirname(verdicts_path) or ".", exist_ok=True)
    appended = 0
    with open(verdicts_path, "a", encoding="utf-8") as f:
        for row in rows:
            key = (row["pair_id"], row["order"], row["judge"])
            if key in done:
                continue
            f.write(json.dumps(row) + "\n")
            done.add(key)
            appended += 1
    return appended
