#!/usr/bin/env python3
"""Upstream-merge identity gate for the served mlx-vlm fork (C130/C131): does the merge branch change
model outputs of `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` in its shipped state?

SELF-CONTAINED (no sourced shell functions, no helper module; helpers copied from
$STACK_WORKDIR/m60/run_m60.py). Registry of record: main_models.yaml, lean router, session max 1.

  0 preflight (refuse = exit 2, nothing started)
  A OLD source (submodule untouched): lean router -> load -> verify -> identity set  -> rows `old`
    -> unload -> scripts/stack_stop.sh -> verify down
  B NEW source: fetch + detached checkout of the branch head into src/mlx-vlm -> lean router -> load ->
    verify -> identity set -> rows `new` -> unload + load (new worker pid) -> identity set -> rows
    `new_reload` -> LONG-PROMPT CHECK -> unload -> stop -> verify down
  C verdict (CPU): IDENTICAL exit 0 (submodule LEFT on the new sha) | RELOAD_NOISE exit 5 |
    DIFFERENT exit 6 | LONG_PROMPT_FAIL exit 7 | tripwire/abort exit 3 | internal error exit 4.
    Every exit other than IDENTICAL restores src/mlx-vlm (`git submodule update --force`) in a
    `finally` and verifies HEAD == old sha + clean tree.

IDENTITY SET — why this shape. `bench.parity_replay run` is the only existing tool that replays
frozen raw payloads with an EXPLICIT seed and persists digest-comparable rows (content_sha256,
reasoning_sha256, prompt/completion tokens, finish, draft_* and verify_* counters, served runtime,
serving-code hash); it is the M58 G1b instrument (20/20 cross-load identical + reload control).
`bench.stack_smoke` cannot serve as an identity instrument: it sends no seed and records no digest;
its CASE CONTENT (get_weather tool, synthetic red-circle image) is reused here as frozen payloads.
parity_replay rows do not carry `message.tool_calls`, so the replay runs through a 20-line in-process
shim (SHIM below) that wraps `parity_replay._post` and appends each response's tool_calls to a
sidecar keyed by the same payload+seed sha the rows carry; nothing in the repo is modified.
The request file is generated here deterministically (seed = sha256 of the request id; images are
PNGs encoded with zlib, no PIL), written once per run and replayed verbatim by all three passes.
23 requests at deployed sampling (`params_for(model, profile="deployed")`, thinking ON):
plain chat 4, thinking-heavy 4, code 2, tool first turn 4 (incl. parallel calls and tools-present-
but-unneeded), tool-result follow-up 3 (fixed assistant tool_calls; two of them carry reasoning —
inline <think> and reasoning_content), multi-turn with a prior assistant turn WITH reasoning 4
(inline complete block, closer-only block, reasoning_content field, list-of-parts content over
three turns) — the `_strip_assistant_thinking` path the merge moved — and vision 2.
NOT covered: streaming (SSE) responses; chat-id pinned session reuse / cached-token identity
(parity_replay sends no X-MLX-VLM-Chat-Id; cached_tokens is recorded, informational only); the
Responses / Anthropic routes; video/audio; prompts between ~2K and the long rung; the second pick;
draft-OFF; the router (mlx-serve is not changed by this merge). The long-prompt check is a
pass/fail on the new source only (no old-source control, unseeded runner).

  . "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
  cd "$STACK_WORKDIR/upstream/2026-10-06" && nohup "$STACK_REPO/.venv-bench/bin/python" run_merge_gate.py \
      > run_merge_gate.out 2>&1 < /dev/null &
  --dry-run        every CPU-side check + every command each phase would run; no request, nothing
                   started, no git state touched
  --analyze-only   recompute the verdict from a saved run dir (default: newest under runs/)
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import json
import math
import os
import re
import shutil
import signal
import statistics
import struct
import subprocess
import sys
import tarfile
import time
import urllib.request
import zlib
from pathlib import Path

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
SERVE_CONFIG = "main_models.yaml"
SESSION_MAX = "1"
BASE = "http://localhost:8000"
SUBMODULE = "src/mlx-vlm"
DEFAULT_OLD = "664c2ead"
DEFAULT_BRANCH = "sync/upstream-v0.7.6"
CONTEXT_LIMIT = 262144
CLAMP_FLOOR = 159744            # limit - max_tokens: the compaction threshold the long prompt must exceed
TOP_RUNG = 245760
LONG_RUNG = 196608              # smallest rung > CLAMP_FLOOR with same-rung timing rows (capacity ladder)
LONG_TOL = 0.01                 # observed runner deviation: -0.22..-0.27 % (128K..256K rows)
RETRIEVAL_THRESHOLD = 0.85      # the runner's own pass threshold (5 needles: 5/5)
FLOOR_DECODE_TPS = 8.0          # parity_replay's derived-timeout floor
HEADROOM_S = 900.0
PREFILL_HEADROOM = 1.5
EST_DECODE_TPS = 35.0           # fallback; dry-run derives it from the M58 G1b rows
PASS_BOUND_S = 7200             # tripwire per identity pass (prediction ~7-15 min)
WATCH_INTERVAL_S = 300
EXPECT_POWER = {"watt": 140, "mv": 28000, "batt_min": 20}
EXPECT_SAMPLING = {"temperature": 0.5, "top_p": 0.95, "top_k": 20, "min_p": 0.0,
                   "presence_penalty": 0.0, "max_tokens": 102400, "thinking_budget": 81920,
                   "enable_thinking": True, "reasoning_effort": "medium"}
BUSY_PATTERNS = ("mlx_vlm.server", "mlx_vlm/server", "mlx-serve start", "session_cache_probe",
                 "opencode run", "run.py generate", "run_opencode_probe", "run_agentbench_os",
                 "bench.run_", "vision_gate.py", "decode_probe", "parity_replay", "runserver.sh",
                 "run_m60.py", "bench.stack_smoke")
SIDECAR_ENV = "MERGE_GATE_TOOLCALL_SIDECAR"
INSTRUMENT_FILES = ("benchmark/bench/parity_replay.py", "benchmark/bench/client.py", "benchmark/bench/provenance.py",
                    "benchmark/bench/run_retrieval.py", "benchmark/bench/retrieval.py", "benchmark/bench/driver.py",
                    "benchmark/bench/model_params.py", "benchmark/bench/paths.py", "scripts/stack_stop.sh")

RC_OK, RC_REFUSED, RC_TRIPWIRE, RC_INTERNAL = 0, 2, 3, 4
RC_RELOAD_NOISE, RC_DIFFERENT, RC_LONG_FAIL = 5, 6, 7
VERDICT_RC = {"IDENTICAL": RC_OK, "RELOAD_NOISE": RC_RELOAD_NOISE, "DIFFERENT": RC_DIFFERENT,
              "LONG_PROMPT_FAIL": RC_LONG_FAIL, "INTEGRITY": RC_TRIPWIRE}

# Compared per request, in "first differing field" order. prompt_tokens is the only field that does
# not depend on generation (a prompt-render change); every other field follows the generated stream.
COMPARE_FIELDS = ("prompt_tokens", "reasoning_sha256", "content_sha256", "tool_calls",
                  "completion_tokens", "finish_reason", "draft", "verify")
FIELD_KIND = {f: ("prompt" if f == "prompt_tokens" else "generation") for f in COMPARE_FIELDS}
RUNTIME_WANT = {"draft_kind": "mtp", "attention_policy": "fused_v1", "lazy_prompt_embeddings": True,
                "mtp_verify_scan": "joint_v1"}

SHIM = r'''
import json, os, sys
from bench import parity_replay as P
_SIDE = os.environ["MERGE_GATE_TOOLCALL_SIDECAR"]
_orig = P._post
def _post(payload, timeout):
    resp = _orig(payload, timeout)
    rec = {"payload_sha256": P._payload_sha(payload, payload.get("seed"))}
    try:
        msg = resp["choices"][0]["message"]
        rec["tool_calls"] = msg.get("tool_calls")
        rec["message_keys"] = sorted(msg)
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
    with open(_SIDE, "a") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    return resp
P._post = _post
sys.argv[0] = "bench.parity_replay"
sys.exit(P.main())
'''


class Refusal(Exception):
    """Preflight refusal — nothing was started."""


class Tripwire(Exception):
    """Abort: the submodule is restored, the stack stopped, no verdict."""


# ============================================================================ pure helpers
def sha256_text(s: str) -> str:
    return hashlib.sha256((s or "").encode()).hexdigest()


def payload_sha(payload: dict, seed) -> str:
    """Byte-for-byte the key `bench.parity_replay._payload_sha` writes into every row."""
    return sha256_text(json.dumps({"payload": payload, "seed": seed}, sort_keys=True,
                                  separators=(",", ":"), ensure_ascii=False))


def seed_for(rid: str) -> int:
    return int(hashlib.sha256(f"merge-gate-v1:{rid}".encode()).hexdigest()[:8], 16) % (2 ** 31 - 1)


def png_data_url(w: int, h: int, pixel) -> str:
    """Deterministic RGB PNG (stdlib zlib, no PIL) as a data URL; pixel(x, y) -> (r, g, b)."""
    raw = b"".join(b"\x00" + bytes(c for x in range(w) for c in pixel(x, y)) for y in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    import base64
    return "data:image/png;base64," + base64.b64encode(png).decode()


def _red_disc(x, y):
    return (220, 20, 20) if (x - 128) ** 2 + (y - 128) ** 2 <= 80 ** 2 else (255, 255, 255)


def _blue_square_left(x, y):
    return (20, 40, 210) if 24 <= x < 104 and 88 <= y < 168 else (255, 255, 255)


def _fn(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required}}}


T_WEATHER = _fn("get_weather", "Get the current weather for a city.",
                {"city": {"type": "string", "description": "City name"}}, ["city"])
T_TIME = _fn("get_local_time", "Get the current local time for a city.",
             {"city": {"type": "string", "description": "City name"}}, ["city"])
T_SEARCH = _fn("search_files", "Search the repository for files whose contents match a pattern.",
               {"pattern": {"type": "string", "description": "Regular expression"},
                "file_glob": {"type": "string", "description": "Glob such as *.py"},
                "max_results": {"type": "integer", "description": "Upper bound on results"}},
               ["pattern"])


def _call(cid, name, args):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def identity_requests() -> list:
    """(kind, id, messages, tools, est_completion_tokens) — the frozen identity set (23 requests)."""
    U = lambda t: {"role": "user", "content": t}  # noqa: E731
    A = lambda t: {"role": "assistant", "content": t}  # noqa: E731
    boxed = "\n\nSolve step by step. Put your final answer in \\boxed{}."
    reqs = [
        ("plain", "plain-01-arith", [U("What is 17 * 23? Reply with the number only.")], None, 250),
        ("plain", "plain-02-system", [{"role": "system", "content": "You are a concise assistant."},
                                      U("Name the capital of Australia in one word.")], None, 200),
        ("plain", "plain-03-json", [U('Return a JSON object with keys "city" (string, "Paris") and '
                                      '"population_millions" (number, about 2.1). Output only the JSON, '
                                      'no prose, no code fence.')], None, 300),
        ("plain", "plain-04-translate", [U("Translate 'The library opens at nine.' into French and German. "
                                           "Two lines, no commentary.")], None, 300),
        ("thinking", "think-01-mean", [U("The arithmetic mean of 7, 2, $x$ and 10 is 9. What is the value "
                                         "of $x$?" + boxed)], None, 400),
        ("thinking", "think-02-divisors", [U("How many positive divisors does 360 have?" + boxed)], None, 900),
        ("thinking", "think-03-train", [U("A train leaves at 14:35 and arrives at 18:10 the same day, with a "
                                          "17-minute stop on the way. For how many minutes was it moving?"
                                          + boxed)], None, 700),
        ("thinking", "think-04-order", [U("Alice is older than Bob. Carol is younger than Bob. Dave is older "
                                          "than Alice. Eve is younger than Carol. List the five people from "
                                          "youngest to oldest.")], None, 900),
        ("code", "code-01-prime", [U("Write a Python function `is_prime(n)` that returns True for primes and "
                                     "False otherwise. Return ONLY the code in one ```python block.")], None, 900),
        ("code", "code-02-intervals", [U("Write a Python function `merge_intervals(intervals)` that merges "
                                         "overlapping closed intervals given as a list of [start, end] pairs "
                                         "and returns them sorted. Return ONLY the code in one ```python "
                                         "block.")], None, 1200),
        ("tool", "tool-01-weather", [U("What's the weather in Paris right now? Use the tool.")],
         [T_WEATHER], 250),
        ("tool", "tool-02-parallel", [U("What is the local time and the weather in Tokyo right now? Use the "
                                        "tools.")], [T_WEATHER, T_TIME], 350),
        ("tool", "tool-03-unneeded", [U("What is 12 + 30? Answer directly.")], [T_WEATHER, T_TIME], 250),
        ("tool", "tool-04-nested", [U("Find up to 5 Python files that mention 'session_cache'. Use the "
                                      "search tool.")], [T_SEARCH], 350),
        ("tool_result", "toolres-01-plain", [
            U("What's the weather in Paris right now? Use the tool."),
            {"role": "assistant", "content": None,
             "tool_calls": [_call("call_gate_w1", "get_weather", {"city": "Paris"})]},
            {"role": "tool", "tool_call_id": "call_gate_w1", "name": "get_weather",
             "content": json.dumps({"city": "Paris", "temp_c": 18, "condition": "cloudy"})}],
         [T_WEATHER], 250),
        ("tool_result", "toolres-02-inline-think", [
            U("Is it warmer in Lisbon or Oslo right now? Use the tool for both cities."),
            {"role": "assistant",
             "content": "<think>\nI need the weather in both cities, so I will call get_weather twice.\n"
                        "</think>\n\n",
             "tool_calls": [_call("call_gate_l1", "get_weather", {"city": "Lisbon"}),
                            _call("call_gate_o1", "get_weather", {"city": "Oslo"})]},
            {"role": "tool", "tool_call_id": "call_gate_l1", "name": "get_weather",
             "content": json.dumps({"city": "Lisbon", "temp_c": 22, "condition": "sunny"})},
            {"role": "tool", "tool_call_id": "call_gate_o1", "name": "get_weather",
             "content": json.dumps({"city": "Oslo", "temp_c": 9, "condition": "rain"})}],
         [T_WEATHER], 300),
        ("tool_result", "toolres-03-reasoning-content", [
            U("What time is it in Tokyo? Use the tool."),
            {"role": "assistant", "content": "",
             "reasoning_content": "The user wants the local time in Tokyo; get_local_time takes a city.",
             "tool_calls": [_call("call_gate_t1", "get_local_time", {"city": "Tokyo"})]},
            {"role": "tool", "tool_call_id": "call_gate_t1", "name": "get_local_time",
             "content": json.dumps({"city": "Tokyo", "time": "21:05", "utc_offset": "+09:00"})}],
         [T_WEATHER, T_TIME], 250),
        ("multiturn_reasoning", "mt-01-inline-think", [
            U("Pick a prime number between 10 and 20 and tell me only the number."),
            A("<think>\nPrimes between 10 and 20 are 11, 13, 17 and 19. I will pick 13.\n</think>\n\n13"),
            U("Now multiply your number by 3 and add 4. Give the result only.")], None, 400),
        ("multiturn_reasoning", "mt-02-closer-only", [
            {"role": "system", "content": "You are a careful assistant."},
            U("Give me a four-letter English word that starts with 'b'."),
            A("The user wants a four-letter word starting with b. 'Book' works.\n</think>\n\nBook"),
            U("Spell that word backwards, then give its plural.")], None, 400),
        ("multiturn_reasoning", "mt-03-reasoning-content", [
            U("Which is larger, 2^10 or 10^3?"),
            {"role": "assistant", "content": "2^10 = 1024 is larger than 10^3 = 1000.",
             "reasoning_content": "2^10 is 1024 and 10^3 is 1000, so 2^10 is larger by 24."},
            U("By how much, as a percentage of the smaller number? One decimal place.")], None, 600),
        ("multiturn_reasoning", "mt-04-parts-three-turns", [
            U("Let's build a three-item grocery list for pancakes. First item?"),
            {"role": "assistant", "content": [{"type": "text", "text":
                                               "<think>\nPancakes need flour, eggs and milk.\n</think>\n\nFlour."}]},
            U("Second item?"),
            A("<think>\nNext comes eggs.\n</think>\n\nEggs."),
            U("Third item, then repeat the whole list as one comma-separated line.")], None, 400),
        ("vision", "vis-01-red-disc", [{"role": "user", "content": [
            {"type": "text", "text": "What shape and colour is drawn in this image? Answer in one short sentence."},
            {"type": "image_url", "image_url": {"url": png_data_url(256, 256, _red_disc)}}]}], None, 400),
        ("vision", "vis-02-blue-square", [{"role": "user", "content": [
            {"type": "text", "text": "What colour is the square, and is it in the left half or the right half "
                                     "of the image? One short sentence."},
            {"type": "image_url", "image_url": {"url": png_data_url(256, 256, _blue_square_left)}}]}], None, 450),
    ]
    return reqs


def build_frozen(params: dict, model: str = MODEL) -> dict:
    """parity_replay's frozen-request format; every payload carries its explicit seed."""
    requests = []
    for kind, rid, msgs, tools, est in identity_requests():
        seed = seed_for(rid)
        p = {"model": model, "messages": msgs, "stream": False, **params, "seed": seed}
        if tools:
            p["tools"] = tools
        requests.append({"bench": kind, "id": rid, "seed": seed, "payload": p, "est_completion_tokens": est})
    ids = [r["id"] for r in requests]
    shas = [payload_sha(r["payload"], r["seed"]) for r in requests]
    if len(set(ids)) != len(ids) or len(set(shas)) != len(shas):
        raise Refusal("identity set has a duplicate id or a duplicate payload")
    return {"kind": "merge_gate_identity_set", "version": 1, "model": model,
            "arms": {"merge_gate": {"model": model, "requests": requests}}}


def frozen_keys(frozen: dict) -> dict:
    """{(model, bench, id): payload_sha256} exactly as parity_replay computes it."""
    out = {}
    for arm in frozen["arms"].values():
        for r in arm["requests"]:
            p = dict(r["payload"]); p["model"] = arm["model"]; p["stream"] = False
            out[(arm["model"], r["bench"], r["id"])] = payload_sha(p, r.get("seed"))
    return out


def predicted_pass_s(frozen: dict, tps: float) -> float:
    reqs = [r for a in frozen["arms"].values() for r in a["requests"]]
    return sum(r.get("est_completion_tokens", 500) for r in reqs) / tps + 3.0 * len(reqs)


def normalize_tool_calls(tc):
    """Comparable form of message.tool_calls: per-request random `id`s dropped, arguments parsed."""
    if tc is None:
        return None
    if not isinstance(tc, list):
        return ("unparseable", str(tc))
    out = []
    for c in tc:
        if not isinstance(c, dict):
            out.append(("unparseable", str(c)))
            continue
        fn = c.get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                pass
        out.append((c.get("type"), fn.get("name"), json.dumps(args, sort_keys=True)))
    return out


def _first_char_diff(a: str, b: str):
    a, b = a or "", b or ""
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def field_value(row: dict, tools: dict, f: str):
    if f == "tool_calls":
        return normalize_tool_calls((tools.get(row.get("payload_sha256")) or {}).get("tool_calls"))
    if f == "draft":
        d = row.get("draft") or {}
        return {k: d.get(k) for k in ("draft_kind", "draft_rounds", "draft_n", "draft_n_accepted")}
    if f == "verify":
        return row.get("verify") or {}
    return row.get(f)


def compare_sides(rows_a: dict, rows_b: dict, tools_a: dict, tools_b: dict, fields_=COMPARE_FIELDS) -> list:
    """Per-request differences between two passes keyed identically; [] = identical on every field."""
    diffs = []
    for k in sorted(set(rows_a) | set(rows_b)):
        if k not in rows_a or k not in rows_b:
            diffs.append({"key": list(k), "fields": ["missing"], "first_field": "missing",
                          "kinds": ["integrity"]})
            continue
        x, y = rows_a[k], rows_b[k]
        fields = [f for f in fields_ if field_value(x, tools_a, f) != field_value(y, tools_b, f)]
        if fields:
            diffs.append({"key": list(k), "fields": fields, "first_field": fields[0],
                          "kinds": sorted({FIELD_KIND[f] for f in fields}),
                          "a": {f: field_value(x, tools_a, f) for f in ("prompt_tokens", "completion_tokens",
                                                                       "finish_reason")},
                          "b": {f: field_value(y, tools_b, f) for f in ("prompt_tokens", "completion_tokens",
                                                                       "finish_reason")},
                          "reasoning_first_char_diff": _first_char_diff(x.get("reasoning"), y.get("reasoning")),
                          "content_first_char_diff": _first_char_diff(x.get("content"), y.get("content"))})
    return diffs


def decide(on_diffs: list, rl_diffs: list, long_check, integrity: list) -> tuple:
    """(verdict, rc, reason). on = old vs new, rl = new vs new_reload."""
    if integrity:
        return "INTEGRITY", RC_TRIPWIRE, f"{len(integrity)} integrity problem(s): {integrity[:3]}"
    if any("integrity" in d["kinds"] for d in on_diffs + rl_diffs):
        return "INTEGRITY", RC_TRIPWIRE, "a request is missing on one side"
    k_on = {k for d in on_diffs for k in d["kinds"]}
    k_rl = {k for d in rl_diffs for k in d["kinds"]}
    if not on_diffs and not rl_diffs:
        if long_check and long_check.get("pass"):
            return "IDENTICAL", RC_OK, "old == new on every request, reload control identical, long prompt passes"
        return "LONG_PROMPT_FAIL", RC_LONG_FAIL, f"identity set identical but the long-prompt check fails: " \
                                                f"{(long_check or {}).get('reasons') or 'not run'}"
    if rl_diffs and k_on <= k_rl:
        return "RELOAD_NOISE", RC_RELOAD_NOISE, (f"old!=new on {len(on_diffs)} request(s), new!=new_reload on "
                                                 f"{len(rl_diffs)}; difference kinds {sorted(k_on)} within the "
                                                 f"reload kinds {sorted(k_rl)}: the instrument cannot separate "
                                                 f"source from reload")
    why = "reload control identical" if not rl_diffs else \
        f"old/new differ in kind(s) {sorted(k_on - k_rl)} that the reload control never shows"
    return "DIFFERENT", RC_DIFFERENT, f"old!=new on {len(on_diffs)} request(s); {why}"


def side_problems(doc: dict, keys: dict, tools: dict, n_tool_recs: int, side: str,
                  want_code_vlm=None) -> list:
    """Integrity of one parity_replay journal against the frozen identity set."""
    probs = []
    if doc.get("status") != "complete":
        probs.append(f"{side}: journal status {doc.get('status')!r} (error {str(doc.get('error'))[:80]!r})")
    if doc.get("served_config_drift"):
        probs.append(f"{side}: served_config_drift stamp")
    exp = {tuple(k) for k in doc.get("expected_keys") or []}
    if exp != set(keys):
        probs.append(f"{side}: expected_keys differ from the identity set ({len(exp ^ set(keys))} keys)")
    seen = set()
    for r in doc.get("rows") or []:
        k = (r.get("model"), r.get("bench"), r.get("id"))
        if k in seen:
            probs.append(f"{side}: duplicate row {k}")
        seen.add(k)
        if keys.get(k) != r.get("payload_sha256"):
            probs.append(f"{side}: row {k[2]} payload+seed sha differs from the identity set")
        if r.get("code") != doc.get("code"):
            probs.append(f"{side}: row {k[2]} serving code differs from its journal")
        rt = r.get("runtime") or {}
        for f, v in RUNTIME_WANT.items():
            if rt.get(f) != v:
                probs.append(f"{side}: row {k[2]} runtime.{f}={rt.get(f)!r}, expected {v!r}")
        for f, dg in (("content", "content_sha256"), ("reasoning", "reasoning_sha256")):
            if not isinstance(r.get(f), str) or sha256_text(r[f]) != r.get(dg):
                probs.append(f"{side}: row {k[2]} {dg} does not match its stored {f}")
        if r.get("payload_sha256") not in tools:
            probs.append(f"{side}: row {k[2]} has no tool-call sidecar record")
    if seen != set(keys):
        probs.append(f"{side}: rows cover {len(seen)} of {len(keys)} identity keys")
    if n_tool_recs != len(keys):
        probs.append(f"{side}: tool-call sidecar has {n_tool_recs} records, expected {len(keys)}")
    if want_code_vlm is not None and (doc.get("code") or {}).get(SUBMODULE) != want_code_vlm:
        probs.append(f"{side}: serving-code hash of {SUBMODULE} {str((doc.get('code') or {}).get(SUBMODULE))[:12]} "
                     f"!= expected {str(want_code_vlm)[:12]} (the pass did not run the intended source)")
    return probs


def long_timeout(prefill_s: list, prompt_tokens: list, max_tokens: int = EXPECT_SAMPLING["max_tokens"]) -> dict:
    """Request timeout for the long prompt, DERIVED from same-rung rows: 1.5 x the slowest observed
    prefill + the clamped generation cap at the floor decode rate + 900 s headroom."""
    if not prefill_s or not prompt_tokens:
        raise Refusal(f"no same-rung ({LONG_RUNG}) timing rows to derive the long-prompt timeout from")
    gen_cap = min(max_tokens, CONTEXT_LIMIT - min(prompt_tokens))
    t = math.ceil(PREFILL_HEADROOM * max(prefill_s) + gen_cap / FLOOR_DECODE_TPS + HEADROOM_S)
    return {"timeout_s": t, "prefill_max_s": max(prefill_s), "prefill_min_s": min(prefill_s), "n_rows": len(prefill_s),
            "prompt_tokens_seen": sorted(set(prompt_tokens)), "gen_cap_tokens": gen_cap,
            "formula": f"ceil({PREFILL_HEADROOM} x {max(prefill_s)} + {gen_cap}/{FLOOR_DECODE_TPS} + {HEADROOM_S})"}


def long_prompt_check(record: dict, rung: int, threshold: float = RETRIEVAL_THRESHOLD,
                      floor: int = CLAMP_FLOOR, top: int = TOP_RUNG, tol: float = LONG_TOL) -> dict:
    """Pass iff the recorded prompt_tokens is within tol of the rung AND above the compaction floor,
    the runner's own accuracy meets its threshold, and every trial stopped normally below the
    resolved thinking budget."""
    reasons = []
    rows = record.get("rows") or []
    if not (floor < rung <= top):
        reasons.append(f"rung {rung} is not in ({floor}, {top}]")
    if not rows:
        reasons.append("no trial rows")
    for r in rows:
        pt = r.get("prompt_tokens")
        if not isinstance(pt, int) or isinstance(pt, bool):
            reasons.append(f"trial {r.get('trial')}: prompt_tokens {pt!r} missing")
            continue
        if abs(pt - rung) > tol * rung:
            reasons.append(f"trial {r.get('trial')}: prompt_tokens {pt} outside ±{tol:.0%} of {rung} "
                           f"(compaction/truncation signature)")
        if pt <= floor:
            reasons.append(f"trial {r.get('trial')}: prompt_tokens {pt} not above the {floor} compaction floor")
        if r.get("finish_reason") != "stop":
            reasons.append(f"trial {r.get('trial')}: finish_reason {r.get('finish_reason')!r}")
        resolved = min(EXPECT_SAMPLING["thinking_budget"],
                       int(0.8 * min(EXPECT_SAMPLING["max_tokens"], CONTEXT_LIMIT - pt)))
        if (r.get("completion_tokens") or 0) >= resolved:
            reasons.append(f"trial {r.get('trial')}: completion_tokens {r.get('completion_tokens')} >= "
                           f"resolved budget {resolved}")
    acc = record.get("accuracy")
    if acc is None or acc < threshold:
        reasons.append(f"retrieval accuracy {acc} below the runner threshold {threshold}")
    if record.get("ctx") != rung:
        reasons.append(f"record ctx {record.get('ctx')} != requested rung {rung}")
    return {"pass": not reasons, "reasons": reasons, "rung": rung, "accuracy": acc,
            "prompt_tokens": [r.get("prompt_tokens") for r in rows],
            "completion_tokens": [r.get("completion_tokens") for r in rows],
            "finish": [r.get("finish_reason") for r in rows], "prefill_s": [r.get("prefill_s") for r in rows],
            "wall_s": [r.get("wall_s") for r in rows]}


def http_rejection(log_text: str):
    """The first HTTP 4xx (server refusal) line in a driver log, else None (5xx/timeouts stay aborts)."""
    for ln in (log_text or "").splitlines():
        if re.search(r"HTTP Error 4\d\d", ln) or "ContextBudgetError" in ln or "context budget" in ln.lower():
            return ln.strip()[:240]
    return None


def parse_power(ac_text: str, batt_text: str) -> dict:
    w = re.search(r"Wattage\s*=\s*(\d+)W", ac_text or "")
    v = re.search(r"Voltage\s*=\s*(\d+)mV", ac_text or "")
    b = re.search(r"(\d+)%", batt_text or "")
    return {"watt": int(w.group(1)) if w else None, "mv": int(v.group(1)) if v else None,
            "batt": int(b.group(1)) if b else None}


def power_problems(p: dict, expect: dict = EXPECT_POWER) -> list:
    probs = []
    if p.get("watt") != expect["watt"]:
        probs.append(f"adapter wattage {p.get('watt')} != {expect['watt']} W")
    if p.get("mv") != expect["mv"]:
        probs.append(f"adapter voltage {p.get('mv')} != {expect['mv']} mV")
    if p.get("batt") is None or p["batt"] <= expect["batt_min"]:
        probs.append(f"battery {p.get('batt')} % not above {expect['batt_min']} %")
    return probs


def registry_entry_problems(entry: dict) -> list:
    probs = []
    want = {"kv_bits": 0, "attention_policy": "fused_v1", "lazy_prompt_embeddings": True,
            "mtp_verify_scan": "joint_v1", "draft_kind": "mtp", "max_kv_cache_size": 262144,
            "kv_prealloc_tokens": 262144}
    for k, v in want.items():
        if entry.get(k) != v:
            probs.append(f"registry {k}={entry.get(k)!r}, expected {v!r}")
    if not entry.get("draft_model"):
        probs.append("registry draft_model missing")
    gd = entry.get("generation_defaults") or {}
    for k, v in EXPECT_SAMPLING.items():
        if gd.get(k) != v:
            probs.append(f"registry generation_defaults.{k}={gd.get(k)!r}, expected {v!r}")
    return probs


def worker_cmdline_problems(cmd: str) -> list:
    probs = []
    for needle in ("--attention-policy fused_v1", "--lazy-prompt-embeddings",
                   "--mtp-verify-scan joint_v1", "--draft-kind mtp", "--max-kv-size 262144",
                   "--kv-prealloc-tokens 262144"):
        if needle not in cmd:
            probs.append(f"worker cmdline lacks `{needle}`")
    m = re.search(r"--kv-bits\s+(\S+)", cmd)
    if m and m.group(1) not in ("0", "0.0"):
        probs.append(f"worker cmdline carries --kv-bits {m.group(1)} (native16 expected)")
    if "--mtp-verify-ab" in cmd:
        probs.append("worker cmdline carries --mtp-verify-ab (gate-1 AB mode, not the shipped state)")
    return probs


def busy_processes(ps_lines_: list, self_pids: set) -> list:
    out = []
    for line in ps_lines_:
        parts = line.strip().split(None, 1)
        if len(parts) < 2 or not parts[0].isdigit() or int(parts[0]) in self_pids:
            continue
        if any(p in parts[1] for p in BUSY_PATTERNS):
            out.append(line.strip()[:160])
    return out


def unsatisfied_requirements(lines: list, installed: dict) -> list:
    """Requirement lines whose distribution is absent from the venv or whose installed version fails
    the specifier. `installed` = {normalized name: version or None}; specifier check via packaging."""
    from packaging.requirements import Requirement
    out = []
    for ln in lines:
        ln = ln.split("#", 1)[0].strip()
        if not ln:
            continue
        req = Requirement(ln)
        name = re.sub(r"[-_.]+", "-", req.name).lower()
        ver = installed.get(name)
        if ver is None:
            out.append(f"{ln} (not installed)")
        elif req.specifier and not req.specifier.contains(ver, prereleases=True):
            out.append(f"{ln} (installed {ver})")
    return out


# ============================================================================ environment
def load_config_env() -> dict:
    cfg = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "mlx_local_stack" / "config.sh"
    env = dict(os.environ)
    if cfg.is_file():
        r = subprocess.run(["bash", "-c", f'set -a; . "{cfg}"; env -0'], capture_output=True, timeout=30)
        if r.returncode == 0:
            for kv in r.stdout.split(b"\0"):
                if b"=" in kv:
                    k, v = kv.split(b"=", 1)
                    env[k.decode()] = v.decode(errors="replace")
    return env


ENV = load_config_env()
for _k in ("STACK_REPO", "STACK_WORKDIR", "MLX_BOX"):
    if not ENV.get(_k):
        sys.stderr.write(f"REFUSED: {_k} is not set (config.sh not loaded) — blocker\n")
        sys.exit(RC_REFUSED)
REPO = Path(ENV["STACK_REPO"])
WD = Path(__file__).resolve().parent
SUB = REPO / SUBMODULE
PY = str(REPO / ".venv-bench" / "bin" / "python")
STACK_PY = str(REPO / ".venv" / "bin" / "python")
RESULTS = REPO / "benchmark" / "results" / MODEL
DEFAULT_FORK = REPO.parent / "mlx-vlm"
DRY = False
_LOG = None
_STATE = {"router_owned": False, "power_ticks": [], "children": [], "submodule_touched": False,
          "keep_new": False, "verdict": None}


def scrub(s) -> str:
    s = str(s)
    for real, ph in ((ENV["STACK_WORKDIR"], "$STACK_WORKDIR"), (str(REPO), "$STACK_REPO"),
                     (str(Path.home()), "$HOME")):
        s = s.replace(real, ph)
    return s


def log(msg: str) -> None:
    line = f"[{time.strftime('%m-%d %H:%M:%S')}] {'DRY ' if DRY else ''}{scrub(msg)}"
    print(line, flush=True)
    if _LOG is not None:
        _LOG.write(line + "\n")
        _LOG.flush()


def sh(cmd, timeout=60, **kw):
    kw.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)


def gitq(*args, cwd=None, runner=None, timeout=120):
    """Read-only git (no optional index refresh, so a `status` never writes the index)."""
    run = runner or sh
    return run(["git", "--no-optional-locks", "-C", str(cwd or REPO), *args], timeout=timeout)


def git_mut(argv: list, runner=None, timeout=300):
    """A git command that CHANGES state: printed in dry-run, never executed there."""
    log(f"{'WOULD RUN' if DRY else 'RUN'} git: {' '.join(map(str, argv))}")
    if DRY:
        return None
    r = (runner or sh)(argv, timeout=timeout)
    if r.returncode:
        raise Tripwire(f"`{' '.join(map(str, argv))}` exited {r.returncode}: {(r.stderr or r.stdout).strip()[-300:]}")
    return r


def listeners() -> list:
    return [int(x) for x in sh(["lsof", "-nP", "-iTCP:8000", "-sTCP:LISTEN", "-t"]).stdout.split()]


def ps_lines() -> list:
    return sh(["ps", "-axo", "pid=,args="]).stdout.splitlines()


def proc_env(pid: int) -> str:
    return sh(["ps", "-Eww", "-o", "command=", "-p", str(pid)]).stdout


def read_power() -> dict:
    return parse_power(sh(["pmset", "-g", "ac"]).stdout, sh(["pmset", "-g", "batt"]).stdout)


def power_tick(label: str) -> dict:
    p = read_power()
    pp = power_problems(p)
    _STATE["power_ticks"].append({"t": int(time.time()), "label": label, **p, "ok": not pp})
    return {**p, "problems": pp}


def registry_sha() -> str:
    return hashlib.sha256((REPO / SERVE_CONFIG).read_bytes()).hexdigest()


def instrument_sha() -> str:
    """One hash over the stack-side instrument files the three passes must share."""
    h = hashlib.sha256()
    for f in INSTRUMENT_FILES:
        h.update(f.encode() + b"\0" + (REPO / f).read_bytes() + b"\0")
    return h.hexdigest()


def check_instrument(label: str) -> None:
    want = _STATE.get("instrument_sha256")
    now = instrument_sha()
    if want and now != want:
        raise Tripwire(f"[{label}] the instrument files changed since preflight ({want[:12]} -> {now[:12]}): "
                       f"passes would not share one instrument")
    if registry_sha() != _STATE.get("registry_sha256", registry_sha()):
        raise Tripwire(f"[{label}] {SERVE_CONFIG} changed since preflight")


def registry_entry() -> dict:
    import yaml
    data = yaml.safe_load((REPO / SERVE_CONFIG).read_text())
    for e in data.get("models") or []:
        if e.get("name") == MODEL:
            return e
    raise Refusal(f"{MODEL} not in {SERVE_CONFIG}")


def driver_env() -> dict:
    env = dict(ENV)
    env.pop("APC_ENABLED", None)
    env.pop("PYTHONPATH", None)
    env["MLX_SERVE_CONFIG"] = SERVE_CONFIG
    return env


def bench_json(code: str, timeout=120):
    """Run a snippet in the bench venv (cwd benchmark/, served registry) and parse its JSON stdout."""
    env = dict(driver_env(), PYTHONPATH=str(REPO / "benchmark"))
    r = sh([PY, "-c", code], timeout=timeout, cwd=str(REPO / "benchmark"), env=env)
    if r.returncode:
        raise Refusal(f"bench helper failed: {(r.stderr or r.stdout).strip()[-300:]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def serving_code_hash(repo_dir: Path, sha: str):
    return bench_json("import json,sys; from bench import provenance as p; "
                      f"print(json.dumps(p.serving_path_hash({str(repo_dir)!r}, {sha!r})))")


def deployed_params() -> dict:
    return bench_json(f"import json; from bench.model_params import params_for; "
                      f"print(json.dumps(params_for({MODEL!r}, profile='deployed')))")


# ============================================================================ source / import checks
def resolve_commit(repo_dir: Path, ref: str):
    r = gitq("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", cwd=repo_dir)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def submodule_state(runner=None) -> dict:
    head = gitq("rev-parse", "HEAD", cwd=SUB, runner=runner).stdout.strip()
    st = gitq("status", "--porcelain", cwd=SUB, runner=runner).stdout.strip()
    return {"head": head, "clean": not st, "status": st.splitlines()[:5]}


def worker_entry_module() -> str:
    """The module the worker entrypoint imports (mlx-serve spawns `<venv>/bin/mlx_vlm.server`)."""
    pm = (SUB.parent / "mlx-serve" / "src" / "mlx_serve" / "process_manager.py").read_text()
    m = re.search(r'_MLX_VLM_SERVER\s*=\s*_VENV_BIN\s*/\s*"([^"]+)"', pm)
    script = REPO / ".venv" / "bin" / (m.group(1) if m else "mlx_vlm.server")
    mm = re.search(r"^from\s+(\S+)\s+import\s+main", script.read_text(), re.M)
    if not mm:
        raise Refusal(f"cannot read the worker entrypoint module from {script}")
    return mm.group(1)


def export_tree(repo_dir: Path, sha: str, label: str) -> Path:
    """`git archive` of mlx_vlm/ + dependency files at `sha` into $WD/import_check/<label>-<sha12>/
    (read-only for git; cached by a completion marker)."""
    dest = WD / "import_check" / f"{label}-{sha[:12]}"
    if (dest / ".complete").is_file():
        return dest
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    r = subprocess.run(["git", "--no-optional-locks", "-C", str(repo_dir), "archive", "--format=tar", sha,
                        "mlx_vlm", "requirements.txt", "pyproject.toml"],
                       capture_output=True, timeout=300, stdin=subprocess.DEVNULL)
    if r.returncode:
        raise Refusal(f"git archive {sha[:12]} failed: {r.stderr.decode(errors='replace')[-200:]}")
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as t:
        t.extractall(dest, filter="data")
    (dest / ".complete").write_text(sha + "\n")
    return dest


def import_check(src_dir: Path, module: str) -> dict:
    """Import the worker module from `src_dir` with the STACK venv (no new dependency may be needed)."""
    code = ("import json, importlib, importlib.util as u, mlx_vlm; "
            f"m = importlib.import_module({module!r}); getattr(m, 'main'); "
            "print(json.dumps({'mlx_vlm': mlx_vlm.__file__, 'module': m.__file__, "
            "'cryptography_installed': u.find_spec('cryptography') is not None}))")
    env = dict(ENV)
    env.pop("APC_ENABLED", None)
    env["PYTHONPATH"] = str(src_dir)
    r = sh([STACK_PY, "-c", code], timeout=600, cwd=str(WD), env=env)
    out = {"src": scrub(src_dir), "rc": r.returncode, "problems": []}
    if r.returncode:
        out["problems"].append(f"import {module} from {scrub(src_dir)} failed: "
                               f"{scrub((r.stderr or r.stdout).strip().splitlines()[-1:] )}")
        return out
    info = json.loads(r.stdout.strip().splitlines()[-1])
    out.update(info)
    if not str(info["mlx_vlm"]).startswith(str(src_dir / "mlx_vlm")):
        out["problems"].append(f"mlx_vlm imported from {scrub(info['mlx_vlm'])}, not from {scrub(src_dir)}")
    return out


def installed_dists() -> dict:
    code = ("import json, re, importlib.metadata as md; "
            "print(json.dumps({re.sub(r'[-_.]+','-',d.metadata['Name']).lower(): d.version "
            "for d in md.distributions() if d.metadata['Name']}))")
    r = sh([STACK_PY, "-c", code], timeout=120, cwd=str(WD))
    return json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {}


def same_rung_rows() -> tuple:
    pre, pts, files = [], [], []
    for f in sorted(RESULTS.glob("capacity_ladder.*.jsonl")):
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("ctx") == LONG_RUNG and isinstance(r.get("prefill_s"), (int, float)):
                pre.append(r["prefill_s"]); pts.append(r.get("prompt_tokens")); files.append(f.name)
    for f in sorted(RESULTS.glob("retrieval.*.json")):
        if f.name.endswith(("manifest.json", "provenance.json")):
            continue
        for rec in json.loads(f.read_text()).get("records") or []:
            if rec.get("ctx") == LONG_RUNG:
                for r in rec.get("rows") or []:
                    if isinstance(r.get("prefill_s"), (int, float)):
                        pre.append(r["prefill_s"]); pts.append(r.get("prompt_tokens")); files.append(f.name)
    return pre, [p for p in pts if isinstance(p, int)], sorted(set(files))


# ============================================================================ preflight
def preflight(args) -> dict:
    """Every CPU-side check. Real mode: any problem refuses. Dry-run: listed as WOULD-REFUSE."""
    static, dynamic, info = [], [], {}
    try:
        static += registry_entry_problems(registry_entry())
    except Refusal as e:
        static.append(str(e))
    info["registry_sha256"] = registry_sha()
    info["registry_dirty"] = bool(gitq("status", "--porcelain", SERVE_CONFIG).stdout.strip())
    if info["registry_dirty"]:
        static.append(f"{SERVE_CONFIG} has uncommitted changes")
    try:
        params = deployed_params()
        if params != EXPECT_SAMPLING:
            static.append(f"deployed params {params} != expected {EXPECT_SAMPLING}")
    except Refusal as e:
        params = dict(EXPECT_SAMPLING)
        static.append(str(e))
    info["params"] = params
    for tool in ("uv", "lsof", "pmset", "git"):
        if shutil.which(tool, path=ENV.get("PATH")) is None:
            static.append(f"`{tool}` not on PATH")
    for p in (PY, STACK_PY, REPO / "scripts/stack_stop.sh"):
        if not Path(p).exists():
            static.append(f"{scrub(p)} missing")
    uvh = sh(["uv", "run", "--help"]).stdout
    if "--no-sync" not in uvh or "--frozen" not in uvh:
        static.append("`uv run` lacks --frozen/--no-sync (needed so the new source never re-locks/syncs .venv)")
    info["uv_lock_sha256"] = hashlib.sha256((REPO / "uv.lock").read_bytes()).hexdigest()
    info["stack_head"] = gitq("rev-parse", "HEAD").stdout.strip()
    info["instrument_sha256"] = _STATE["instrument_sha256"] = instrument_sha()
    _STATE["registry_sha256"] = info["registry_sha256"]
    dirty = gitq("status", "--porcelain", "--", *INSTRUMENT_FILES).stdout.strip().splitlines()
    info["instrument_dirty"] = dirty
    log(f"preflight: instrument sha256={info['instrument_sha256'][:16]}… (re-verified before every pass); "
        f"uncommitted instrument files: {dirty or 'none'}")
    if dirty:
        log("preflight: WARN instrument files carry uncommitted edits — the gate measures with them as they are "
            "now; any change mid-run trips")

    # ---- source state
    old_sha = resolve_commit(SUB, args.old_sha)
    if not old_sha:
        static.append(f"--old-sha {args.old_sha} does not resolve in {SUBMODULE}")
    sub = submodule_state()
    recorded = gitq("ls-tree", "HEAD", SUBMODULE).stdout.split()
    recorded_sha = recorded[2] if len(recorded) >= 3 else None
    info.update(old_sha=old_sha, submodule=sub, recorded_pointer=recorded_sha)
    if old_sha and sub["head"] != old_sha:
        static.append(f"{SUBMODULE} HEAD {sub['head'][:12]} != expected old sha {old_sha[:12]} — restore first: "
                      f"git -C $STACK_REPO submodule update --force {SUBMODULE}")
    if not sub["clean"]:
        static.append(f"{SUBMODULE} working tree not clean: {sub['status']}")
    if old_sha and recorded_sha != old_sha:
        static.append(f"the stack records {SUBMODULE} at {str(recorded_sha)[:12]}, not the old sha "
                      f"{old_sha[:12]}: `git submodule update --force` would not restore the old source")
    fork = Path(args.fork_path).expanduser().resolve()
    info["fork_path"] = scrub(fork)
    new_sha = resolve_commit(fork, f"refs/heads/{args.branch}") if fork.is_dir() else None
    info["branch"] = args.branch
    info["new_sha"] = new_sha
    if not new_sha:
        static.append(f"branch {args.branch} does not resolve in {scrub(fork)}")
    else:
        if args.new_sha:
            pin = resolve_commit(fork, args.new_sha)
            if pin != new_sha:
                static.append(f"branch head {new_sha[:12]} != pinned --new-sha {args.new_sha}")
        if old_sha and new_sha == old_sha:
            static.append(f"branch {args.branch} head == old sha {old_sha[:12]}: nothing merged yet")
        elif old_sha:
            anc = sh(["git", "-C", str(fork), "merge-base", "--is-ancestor", old_sha, new_sha]).returncode
            info["old_is_ancestor_of_new"] = anc == 0
            if anc != 0:
                log(f"preflight: WARN old sha {old_sha[:12]} is not an ancestor of {new_sha[:12]}")
        wt = sh(["git", "-C", str(fork), "worktree", "list", "--porcelain"]).stdout
        blocks = [b for b in wt.split("\n\n") if f"branch refs/heads/{args.branch}" in b]
        if blocks:
            wpath = blocks[0].splitlines()[0].replace("worktree ", "")
            whead = re.search(r"HEAD (\w+)", blocks[0])
            wdirty = sh(["git", "--no-optional-locks", "-C", wpath, "status", "--porcelain"]).stdout.strip()
            info["branch_worktree"] = {"path": scrub(wpath), "head": whead.group(1) if whead else None,
                                       "dirty": bool(wdirty)}
            log(f"preflight: branch worktree {scrub(wpath)} head={info['branch_worktree']['head']} "
                f"dirty={bool(wdirty)} (the import check uses `git archive` of the COMMITTED head, never the "
                f"worktree's uncommitted state)")
    info["mlx_serve_head"] = gitq("rev-parse", "HEAD", cwd=REPO / "src/mlx-serve").stdout.strip()

    # ---- import / dependency check (stack venv, NEW source first on PYTHONPATH; submodule untouched)
    try:
        module = worker_entry_module()
    except (Refusal, OSError) as e:
        module = "mlx_vlm.server"
        static.append(str(e))
    info["worker_module"] = module
    trees = {}
    for label, repo_dir, sha in (("old", SUB, old_sha), ("new", fork, new_sha)):
        if not sha:
            continue
        try:
            trees[label] = export_tree(repo_dir, sha, label)
        except Refusal as e:
            static.append(str(e))
            continue
        ic = import_check(trees[label], module)
        info[f"import_{label}"] = ic
        log(f"preflight: import check {label} ({sha[:12]}): rc={ic['rc']} mlx_vlm.__file__="
            f"{scrub(ic.get('mlx_vlm'))} problems={ic['problems'] or 'none'}")
        static += [f"import check {label}: {p}" for p in ic["problems"]]
    if "new" in trees:
        inst = installed_dists()
        reqs = (trees["new"] / "requirements.txt").read_text().splitlines() \
            if (trees["new"] / "requirements.txt").is_file() else []
        try:
            uns = unsatisfied_requirements(reqs, inst)
        except Exception as e:  # noqa: BLE001
            uns = [f"requirements check failed: {type(e).__name__}: {e}"]
        old_reqs = set((trees["old"] / "requirements.txt").read_text().splitlines()) if "old" in trees else set()
        info["requirements_added_or_changed"] = sorted(set(reqs) - old_reqs)
        info["requirements_unsatisfied"] = uns
        log(f"preflight: new requirements.txt changes {info['requirements_added_or_changed'] or 'none'}; "
            f"unsatisfied in .venv: {uns or 'none'}")
        static += [f"new source needs a dependency the stack venv lacks: {u}" for u in uns]
    try:
        info["code_old"] = serving_code_hash(SUB, old_sha) if old_sha else None
        info["code_new"] = serving_code_hash(fork, new_sha) if new_sha else None
        info["code_now"] = bench_json("import json; from bench import provenance as p; "
                                      "print(json.dumps(p._git_shas()['serving_path']))")
        log(f"preflight: serving-code hash old={str(info['code_old'])[:12]} new={str(info['code_new'])[:12]} "
            f"checked-out={str((info['code_now'] or {}).get(SUBMODULE))[:12]}")
        if info["code_old"] and (info["code_now"] or {}).get(SUBMODULE) != info["code_old"]:
            static.append("serving-code hash of the checked-out submodule != hash of the old sha")
    except Refusal as e:
        static.append(str(e))

    # ---- long-prompt timeout, derived from same-rung rows
    pre, pts, files = same_rung_rows()
    try:
        info["long_timeout"] = long_timeout(pre, pts)
        info["long_timeout"]["source_files"] = files
        lt = info["long_timeout"]
        log(f"preflight: long-prompt rung {LONG_RUNG}: {lt['n_rows']} same-rung rows ({', '.join(files)}), "
            f"prefill {lt['prefill_min_s']}-{lt['prefill_max_s']} s, prompt_tokens {lt['prompt_tokens_seen']} -> "
            f"request timeout {lt['timeout_s']} s = {lt['formula']}")
    except Refusal as e:
        static.append(str(e))

    # ---- dynamic: box state
    ls = listeners()
    if ls:
        dynamic.append(f":8000 is bound by pid(s) {ls} — the stack must be DOWN (scripts/stack_stop.sh)")
    busy = busy_processes(ps_lines(), {os.getpid(), os.getppid()})
    if busy:
        dynamic.append(f"{len(busy)} serving/benchmark process(es) alive: " + " | ".join(busy[:4]))
    power = power_tick("preflight")
    dynamic += power["problems"]
    dk = sh(["docker", "compose", "ps", "-q"], cwd=str(REPO)) if shutil.which("docker") else None
    if dk is not None and dk.returncode == 0 and dk.stdout.strip():
        dynamic.append("docker compose services are up (OpenWebUI) — lean router only")
    hot = [ln.strip()[:120] for ln in sh(["ps", "-axo", "pcpu=,pid=,args="]).stdout.splitlines()
           if ln.strip() and float(ln.split()[0]) > 50.0 and int(ln.split()[1]) != os.getpid()]
    info["power"] = {k: power[k] for k in ("watt", "mv", "batt")}
    info["hot_processes"] = hot
    log(f"preflight: registry sha256={info['registry_sha256'][:16]}… head={info['stack_head'][:7]} "
        f"old={str(old_sha)[:12]} new={str(new_sha)[:12]} ({args.branch}) power={info['power']}")
    if hot:
        log(f"preflight: WARN {len(hot)} process(es) above 50 % CPU: {hot[:3]}")
    for p in static:
        log(f"preflight: STATIC PROBLEM — {p}")
    for p in dynamic:
        log(f"preflight: {'WOULD REFUSE' if DRY else 'REFUSE'} — {p}")
    if not static and not dynamic:
        log("preflight: all checks pass")
    return {"static": static, "dynamic": dynamic, "info": info}


# ============================================================================ router / worker
def start_router(label: str) -> int:
    env = dict(ENV)
    dotenv = REPO / ".env"
    if dotenv.is_file():
        for line in dotenv.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.replace("export ", "").strip()] = v.strip().strip('"').strip("'")
    env.pop("APC_ENABLED", None)
    env.pop("PYTHONPATH", None)
    env["MLX_VLM_CACHE_SESSION_MAX"] = SESSION_MAX
    env["MLX_SERVE_CONFIG"] = SERVE_CONFIG
    cmd = ["uv", "run", "--frozen", "--no-sync", "mlx-serve", "start"]
    log(f"{'WOULD RUN' if DRY else 'RUN'} router [{label}]: verify :8000 free; MLX_VLM_CACHE_SESSION_MAX={SESSION_MAX} "
        f"MLX_SERVE_CONFIG={SERVE_CONFIG} nohup {' '.join(cmd)} >>logs/main_model.log 2>&1 </dev/null &   "
        f"(cwd=$STACK_REPO; APC_ENABLED and PYTHONPATH absent; --frozen --no-sync: uv never re-locks/syncs "
        f".venv against the checked-out source); then verify one :8000 listener = mlx-serve with that env")
    if DRY:
        return -1
    if listeners():
        raise Tripwire(":8000 bound before the router start")
    (REPO / "logs").mkdir(exist_ok=True)
    subprocess.Popen(cmd, cwd=str(REPO), env=env, stdout=open(REPO / "logs/main_model.log", "a"),
                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    _STATE["router_owned"] = True
    for _ in range(90):
        if listeners():
            break
        time.sleep(2)
    return verify_router()


def verify_router() -> int:
    ls = listeners()
    if len(ls) != 1:
        raise Tripwire(f"expected exactly one :8000 listener, found {ls}")
    pid = ls[0]
    e = proc_env(pid)
    probs = []
    if "mlx-serve" not in e:
        probs.append("listener is not mlx-serve")
    if f"MLX_SERVE_CONFIG={SERVE_CONFIG}" not in e:
        probs.append(f"router env lacks MLX_SERVE_CONFIG={SERVE_CONFIG}")
    if f"MLX_VLM_CACHE_SESSION_MAX={SESSION_MAX}" not in e:
        probs.append(f"router env lacks MLX_VLM_CACHE_SESSION_MAX={SESSION_MAX}")
    if "APC_ENABLED" in e:
        probs.append("router env carries APC_ENABLED")
    if " PYTHONPATH=" in e:
        probs.append("router env carries PYTHONPATH (could shadow the submodule source)")
    cwd = sh(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"]).stdout
    if str(REPO) not in cwd:
        probs.append("router cwd is not the stack repo")
    log(f"router pid={pid} owns :8000; env/cwd problems={probs or 'none'}")
    if probs:
        raise Tripwire("router ownership/environment: " + "; ".join(probs))
    return pid


def worker_procs() -> list:
    out = []
    for line in ps_lines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and "mlx_vlm.server" in parts[1] and MODEL in parts[1] and "uv run" not in parts[1]:
            out.append((int(parts[0]), parts[1]))
    return out


def _auth() -> dict:
    h = {"Content-Type": "application/json"}
    if ENV.get("MLX_API_KEY"):
        h["Authorization"] = f"Bearer {ENV['MLX_API_KEY']}"
    return h


def load_and_verify_worker(label: str, expect_sha: str, previous_pid=None) -> dict:
    log(f"{'WOULD RUN' if DRY else 'RUN'} load [{label}]: POST {BASE}/v1/models/load "
        f"{{\"model\": \"{MODEL}\", \"keep_alive\": \"240m\"}} (timeout 900 s); verify exactly one worker with "
        f"--attention-policy fused_v1 --lazy-prompt-embeddings --mtp-verify-scan joint_v1 --draft-kind mtp, env "
        f"session max {SESSION_MAX}, no APC_ENABLED/PYTHONPATH; {SUBMODULE} HEAD == {expect_sha[:12] if expect_sha else '?'}"
        + (f"; worker pid != {previous_pid}" if previous_pid else ""))
    if DRY:
        return {}
    req = urllib.request.Request(BASE + "/v1/models/load", method="POST", headers=_auth(),
                                 data=json.dumps({"model": MODEL, "keep_alive": "240m"}).encode())
    try:
        urllib.request.urlopen(req, timeout=900).read()
    except Exception as e:  # noqa: BLE001 — transport: abort
        raise Tripwire(f"model load failed: {type(e).__name__}: {e}")
    ws = worker_procs()
    if len(ws) != 1:
        raise Tripwire(f"expected exactly one worker for {MODEL}, found {len(ws)}")
    pid, cmd = ws[0]
    probs = worker_cmdline_problems(cmd)
    e = proc_env(pid)
    if "APC_ENABLED" in e:
        probs.append("worker env carries APC_ENABLED")
    if f"MLX_VLM_CACHE_SESSION_MAX={SESSION_MAX}" not in e:
        probs.append(f"worker env lacks MLX_VLM_CACHE_SESSION_MAX={SESSION_MAX}")
    if " PYTHONPATH=" in e:
        probs.append("worker env carries PYTHONPATH")
    if previous_pid is not None and pid == previous_pid:
        probs.append(f"reload did not produce a new worker (pid {pid} unchanged)")
    sub = submodule_state()
    if sub["head"] != expect_sha or not sub["clean"]:
        probs.append(f"{SUBMODULE} HEAD {sub['head'][:12]} clean={sub['clean']} != expected {expect_sha[:12]}")
    finder = next((REPO / ".venv" / "lib").glob("python*/site-packages/__editable___mlx_vlm_*_finder.py"), None)
    mapping = None
    if finder:
        m = re.search(r"MAPPING[^=]*=\s*(\{[^}]*\})", finder.read_text())
        mapping = m.group(1) if m else None
    if mapping and str(SUB / "mlx_vlm") not in mapping:
        probs.append(f"the .venv editable finder does not map mlx_vlm to {SUBMODULE}: {scrub(mapping)}")
    lstart = sh(["ps", "-o", "lstart=", "-p", str(pid)]).stdout.strip()
    log(f"worker [{label}] pid={pid} started={lstart} cmdline: {cmd}")
    log(f"worker [{label}] source: editable finder maps mlx_vlm -> {scrub(mapping)}; no PYTHONPATH in env; "
        f"{SUBMODULE} HEAD={sub['head'][:12]} clean={sub['clean']}")
    if probs:
        raise Tripwire(f"worker verification [{label}]: " + "; ".join(probs))
    return {"pid": pid, "cmdline": scrub(cmd), "started": lstart, "submodule_head": sub["head"],
            "editable_mapping": scrub(mapping)}


def unload_worker(label: str) -> None:
    log(f"{'WOULD RUN' if DRY else 'RUN'} unload [{label}]: POST {BASE}/v1/models/unload; verify no worker left")
    if DRY:
        return
    try:
        urllib.request.urlopen(urllib.request.Request(BASE + "/v1/models/unload", method="POST", headers=_auth(),
                                                      data=json.dumps({"model": MODEL}).encode()), timeout=180).read()
    except Exception as e:  # noqa: BLE001
        raise Tripwire(f"unload failed: {type(e).__name__}: {e}")
    for _ in range(60):
        if not worker_procs():
            return
        time.sleep(1)
    raise Tripwire(f"worker still alive 60 s after unload: {worker_procs()}")


def stop_stack(label: str) -> None:
    log(f"{'WOULD RUN' if DRY else 'RUN'} stop [{label}]: POST /v1/models/unload ; bash scripts/stack_stop.sh ; "
        f"verify :8000 free and no serving process")
    if DRY:
        return
    if listeners():
        try:
            urllib.request.urlopen(urllib.request.Request(BASE + "/v1/models/unload", method="POST",
                                                          headers=_auth(), data=b"{}"), timeout=180).read()
        except Exception as e:  # noqa: BLE001 — still stop by PID below
            log(f"unload POST failed ({type(e).__name__}: {e}); stopping by PID")
    r = sh(["bash", str(REPO / "scripts/stack_stop.sh")], timeout=300, cwd=str(REPO))
    log(f"stack_stop rc={r.returncode} {(r.stdout + r.stderr).strip()[-200:]}")
    left = busy_processes(ps_lines(), {os.getpid(), os.getppid()})
    if listeners() or left:
        raise Tripwire(f"stack not down after stack_stop: listeners={listeners()} processes={left[:3]}")
    _STATE["router_owned"] = False
    log("stack stopped: :8000 free, no serving process")


# ============================================================================ git: new source in / old source back
def checkout_new(state: dict, runner=None) -> None:
    sub = submodule_state(runner)
    if not DRY and (sub["head"] != state["old_sha"] or not sub["clean"]):
        raise Tripwire(f"{SUBMODULE} is not at the old sha / clean before the checkout: {sub}")
    _STATE["submodule_touched"] = True          # from here on every non-IDENTICAL exit restores
    git_mut(["git", "-C", str(SUB), "fetch", str(state["fork_abs"]), state["branch"]], runner)
    if not DRY:
        fh = gitq("rev-parse", "FETCH_HEAD", cwd=SUB, runner=runner).stdout.strip()
        if fh != state["new_sha"]:
            raise Tripwire(f"FETCH_HEAD {fh[:12]} != branch head recorded at preflight {state['new_sha'][:12]} "
                           f"(the branch moved)")
    else:
        log(f"WOULD VERIFY git -C {SUBMODULE} rev-parse FETCH_HEAD == {state['new_sha'][:12] if state['new_sha'] else '?'}")
    git_mut(["git", "-C", str(SUB), "checkout", "--detach", state["new_sha"] or "FETCH_HEAD"], runner)
    if DRY:
        log(f"WOULD VERIFY git -C {SUBMODULE} rev-parse HEAD == new sha and `status --porcelain` empty")
        return
    after = submodule_state(runner)
    log(f"{SUBMODULE} now at {after['head']} clean={after['clean']}")
    if after["head"] != state["new_sha"] or not after["clean"]:
        raise Tripwire(f"checkout of the new sha did not verify: {after}")


def restore_submodule(old_sha: str, runner=None) -> list:
    """`git submodule update --force src/mlx-vlm`, then verify HEAD == old sha and a clean tree."""
    run = runner or sh
    cmd = ["git", "-C", str(REPO), "submodule", "update", "--force", SUBMODULE]
    log(f"{'WOULD RUN' if DRY else 'RUN'} restore: {' '.join(cmd)} ; verify git -C {SUBMODULE} rev-parse HEAD == "
        f"{old_sha[:12] if old_sha else '?'} and status --porcelain empty")
    if DRY:
        return []
    probs = []
    r = run(cmd, timeout=300)
    if r.returncode:
        probs.append(f"submodule update exited {r.returncode}: {(r.stderr or r.stdout).strip()[-200:]}")
    st = submodule_state(runner)
    if st["head"] != old_sha:
        probs.append(f"{SUBMODULE} HEAD {st['head'][:12]} != old sha {old_sha[:12]} after restore")
    if not st["clean"]:
        probs.append(f"{SUBMODULE} not clean after restore: {st['status']}")
    log(f"restore {'VERIFIED' if not probs else 'FAILED'}: HEAD={st['head'][:12]} clean={st['clean']}"
        + (f" problems={probs}" if probs else ""))
    return probs


def finalize_submodule(state: dict, runner=None) -> dict:
    """The submodule leaves this script on the new sha ONLY under IDENTICAL (keep_new)."""
    if not _STATE["submodule_touched"]:
        return {"action": "untouched"}
    if _STATE["verdict"] == "IDENTICAL" and _STATE["keep_new"]:
        st = submodule_state(runner)
        ok = st["head"] == state["new_sha"] and st["clean"]
        log("=" * 78)
        log(f"IDENTICAL — {SUBMODULE} LEFT AT THE NEW SHA {state['new_sha']} ({state['branch']}); verified={ok}. "
            f"The stack still RECORDS {state['old_sha'][:12]}; the next runner certifies on the new sha.")
        log("=" * 78)
        if ok:
            return {"action": "kept_new", "problems": []}
        probs = [f"IDENTICAL but {SUBMODULE} is not at the new sha/clean: {st}"]
        return {"action": "kept_new", "problems": probs + restore_submodule(state["old_sha"], runner)}
    return {"action": "restored", "problems": restore_submodule(state["old_sha"], runner)}


# ============================================================================ passes
def _read_journal(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def run_pass(tag: str, run_dir: Path, frozen_path: Path, n: int, predicted_s: float, router_pid: int,
             worker_pid) -> None:
    out, side = run_dir / f"replay_{tag}.json", run_dir / f"toolcalls_{tag}.jsonl"
    cmd = [PY, "-c", "<SHIM: parity_replay with a tool_calls sidecar>", "run", "--frozen", str(frozen_path),
           "--tag", f"merge-gate-{tag}", "--out", str(out), "--models", MODEL]
    log(f"{'WOULD RUN' if DRY else 'RUN'} pass {tag}: (cwd=$STACK_REPO/benchmark) PYTHONPATH=$STACK_REPO/benchmark "
        f"MLX_SERVE_CONFIG={SERVE_CONFIG} {SIDECAR_ENV}={side} {' '.join(cmd)}  "
        f"[{n} requests, predicted {predicted_s / 60:.1f} min, bound {PASS_BOUND_S / 3600:.1f} h; per-request "
        f"timeout derived inside parity_replay = max_tokens/{FLOOR_DECODE_TPS} + {HEADROOM_S:.0f} s, retries 0]")
    if DRY:
        return
    check_instrument(f"pass {tag}")
    if out.exists() or side.exists():
        raise Tripwire(f"{out.name} or {side.name} already exists")
    env = dict(driver_env(), PYTHONPATH=str(REPO / "benchmark"))
    env[SIDECAR_ENV] = str(side)
    real = [PY, "-c", SHIM, *cmd[3:]]
    t0 = time.time()
    drv = subprocess.Popen(real, cwd=str(REPO / "benchmark"), env=env, stdout=open(run_dir / f"replay_{tag}.log", "a"),
                           stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    _STATE["children"].append(drv)
    time.sleep(1)
    if drv.poll() is None and f"MLX_SERVE_CONFIG={SERVE_CONFIG}" not in proc_env(drv.pid):
        drv.kill(); drv.wait()
        raise Tripwire(f"{tag}: driver pid {drv.pid} env lacks MLX_SERVE_CONFIG={SERVE_CONFIG}")
    rc, next_tick = None, time.time() + WATCH_INTERVAL_S
    try:
        while rc is None:
            rc = drv.poll()
            if time.time() >= next_tick:
                next_tick = time.time() + WATCH_INTERVAL_S
                doc = _read_journal(out) or {}
                rows = doc.get("rows") or []
                walls = [r.get("wall_s") or 0 for r in rows]
                ctok = [r.get("completion_tokens") or 0 for r in rows]
                eta = (statistics.mean(walls) * (n - len(rows))) if walls else None
                fin = {}
                for r in rows:
                    fin[r.get("finish_reason")] = fin.get(r.get("finish_reason"), 0) + 1
                p = power_tick(f"pass {tag}")
                ws = [w for w, _ in worker_procs()]
                log(f"tick {tag}: rows={len(rows)}/{n} elapsed={time.time() - t0:.0f}s predicted={predicted_s:.0f}s "
                    f"mean-ETA={eta if eta is None else round(eta)}s finish={fin} ctok mean/max="
                    f"{round(statistics.mean(ctok)) if ctok else None}/{max(ctok) if ctok else None} "
                    f"status={doc.get('status')} power={ {k: p[k] for k in ('watt', 'mv', 'batt')} }"
                    f"{' POWER DEVIATION ' + '; '.join(p['problems']) if p['problems'] else ''} "
                    f"router_alive={listeners() == [router_pid]} worker={ws}"
                    f"{' (finishing beats correcting: ~' + str(round(eta)) + 's left)' if eta is not None else ''}")
            if time.time() - t0 > PASS_BOUND_S:
                drv.kill(); drv.wait()
                raise Tripwire(f"{tag}: pass exceeded the {PASS_BOUND_S} s bound — killed by PID")
            time.sleep(3)
    finally:
        if drv.poll() is None:
            drv.kill(); drv.wait()
    log(f"END pass {tag} rc={rc} elapsed={time.time() - t0:.0f}s")
    if rc != 0:
        raise Tripwire(f"{tag}: parity_replay exited {rc} (transport/M50/C106/malformed refusals exit nonzero) — "
                       f"see replay_{tag}.log")
    doc = _read_journal(out) or {}
    if doc.get("status") != "complete" or len(doc.get("rows") or []) != n:
        raise Tripwire(f"{tag}: journal status {doc.get('status')!r} with {len(doc.get('rows') or [])}/{n} rows")
    if [w for w, _ in worker_procs()] != [worker_pid] or listeners() != [router_pid]:
        raise Tripwire(f"{tag}: router or worker changed during the pass — not one loaded instance")


def run_long_prompt(run_dir: Path, run_id: str, timeout_s: int, router_pid: int, worker_pid) -> dict:
    tag = f"mergegate-{run_id}"
    cmd = [PY, "-m", "bench.run_retrieval", "--model", MODEL, "--sampling-profile", "deployed",
           "--grid", str(LONG_RUNG), "--samples", "1", "--threshold", str(RETRIEVAL_THRESHOLD),
           "--request-timeout", str(timeout_s), "--out-tag", tag]
    bound = timeout_s + 900 + 120 + 600
    log(f"{'WOULD RUN' if DRY else 'RUN'} long prompt: (cwd=$STACK_REPO/benchmark) PYTHONPATH=$STACK_REPO/benchmark "
        f"MLX_SERVE_CONFIG={SERVE_CONFIG} {' '.join(cmd)}  [subprocess bound {bound} s = request timeout + preload 900 + "
        f"calibration 120 + 600]; then move results/{MODEL}/retrieval.{tag}.json + .manifest.json into the run dir")
    if DRY:
        return {}
    check_instrument("long prompt")
    env = dict(driver_env(), PYTHONPATH=str(REPO / "benchmark"))
    t0 = time.time()
    drv = subprocess.Popen(cmd, cwd=str(REPO / "benchmark"), env=env, stdout=open(run_dir / "long_prompt.log", "a"),
                           stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    _STATE["children"].append(drv)
    rc, next_tick = None, time.time() + WATCH_INTERVAL_S
    try:
        while rc is None:
            rc = drv.poll()
            if time.time() >= next_tick:
                next_tick = time.time() + WATCH_INTERVAL_S
                p = power_tick("long prompt")
                log(f"tick long-prompt: elapsed={time.time() - t0:.0f}s (expected prefill ~"
                    f"{_STATE.get('long_prefill_hint', '?')} s) power={ {k: p[k] for k in ('watt', 'mv', 'batt')} }"
                    f"{' POWER DEVIATION' if p['problems'] else ''} router_alive={listeners() == [router_pid]} "
                    f"worker={[w for w, _ in worker_procs()]}")
            if time.time() - t0 > bound:
                drv.kill(); drv.wait()
                raise Tripwire(f"long prompt exceeded its {bound} s bound — killed by PID")
            time.sleep(5)
    finally:
        if drv.poll() is None:
            drv.kill(); drv.wait()
    log(f"END long prompt rc={rc} elapsed={time.time() - t0:.0f}s")
    if rc != 0:
        rejected = http_rejection((run_dir / "long_prompt.log").read_text(errors="replace"))
        if rejected is None:
            raise Tripwire(f"long prompt: run_retrieval exited {rc} — see long_prompt.log")
        # A 4xx is the SERVER refusing the long prompt (upstream v0.7.6 ungated compaction cannot cut a
        # single-message prompt and raises ContextBudgetError) — a behaviour change, not a transport fault.
        chk = {"pass": False, "reasons": [f"server rejected the {LONG_RUNG} prompt: {rejected}"], "rung": LONG_RUNG,
               "accuracy": None, "prompt_tokens": [], "completion_tokens": [], "finish": [], "prefill_s": [],
               "wall_s": [], "elapsed_s": round(time.time() - t0)}
        (run_dir / "long_prompt_check.json").write_text(json.dumps(chk, indent=1))
        log(f"LONG PROMPT: FAIL — {chk['reasons'][0]}")
        return chk
    dest = run_dir / "long_prompt"
    dest.mkdir(exist_ok=True)
    moved = []
    for suffix in ("json", "manifest.json"):
        src = RESULTS / f"retrieval.{tag}.{suffix}"
        if src.is_file():
            shutil.move(str(src), str(dest / src.name))
            moved.append(src.name)
    res = dest / f"retrieval.{tag}.json"
    if not res.is_file():
        raise Tripwire(f"long prompt: {res.name} not produced")
    rec = (json.loads(res.read_text()).get("records") or [{}])[0]
    chk = long_prompt_check(rec, LONG_RUNG)
    wlog = Path(ENV.get("TMPDIR") or "/tmp") / "mlx-manager-logs" / f"{MODEL}.log"
    if wlog.is_file():
        chk["worker_log_compaction_lines"] = [ln[:200] for ln in wlog.read_text(errors="replace").splitlines()
                                              if "compact" in ln.lower()][:10]
    chk["moved_out_of_repo"] = moved
    chk["elapsed_s"] = round(time.time() - t0)
    (run_dir / "long_prompt_check.json").write_text(json.dumps(chk, indent=1))
    log(f"LONG PROMPT: {'PASS' if chk['pass'] else 'FAIL'} prompt_tokens={chk['prompt_tokens']} acc={chk['accuracy']} "
        f"finish={chk['finish']} ctok={chk['completion_tokens']} prefill_s={chk['prefill_s']} reasons={chk['reasons']}")
    if [w for w, _ in worker_procs()] != [worker_pid] or listeners() != [router_pid]:
        raise Tripwire("router or worker changed during the long prompt")
    return chk


# ============================================================================ verdict (CPU)
def load_side(run_dir: Path, tag: str) -> tuple:
    doc = _read_journal(run_dir / f"replay_{tag}.json")
    if doc is None:
        return None, {}, {}, 0
    rows = {(r.get("model"), r.get("bench"), r.get("id")): r for r in doc.get("rows") or []}
    tools, n = {}, 0
    p = run_dir / f"toolcalls_{tag}.jsonl"
    if p.is_file():
        for line in p.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                n += 1
                tools[rec.get("payload_sha256")] = rec
    return doc, rows, tools, n


def analyze_run(run_dir: Path) -> dict:
    state = json.loads((run_dir / "state.json").read_text())
    frozen = json.loads((run_dir / "identity_set.json").read_text())
    keys = frozen_keys(frozen)
    integrity, sides = [], {}
    if hashlib.sha256((run_dir / "identity_set.json").read_bytes()).hexdigest() != state.get("identity_set_sha256"):
        integrity.append("identity_set.json changed since the run")
    for tag, code in (("old", state.get("code_old")), ("new", state.get("code_new")),
                      ("new_reload", state.get("code_new"))):
        doc, rows, tools, n = load_side(run_dir, tag)
        if doc is None:
            integrity.append(f"{tag}: replay journal missing")
            sides[tag] = ({}, {}, None)
            continue
        integrity += side_problems(doc, keys, tools, n, tag, code)
        sides[tag] = (rows, tools, doc)
    for tag in ("new", "new_reload"):
        a, b = (sides["old"][2] or {}).get("code") or {}, (sides[tag][2] or {}).get("code") or {}
        if a.get("src/mlx-serve") != b.get("src/mlx-serve"):
            integrity.append(f"{tag}: src/mlx-serve serving code differs from the old pass")
    on = compare_sides(sides["old"][0], sides["new"][0], sides["old"][1], sides["new"][1])
    rl = compare_sides(sides["new"][0], sides["new_reload"][0], sides["new"][1], sides["new_reload"][1])
    lp_path = run_dir / "long_prompt_check.json"
    long_check = json.loads(lp_path.read_text()) if lp_path.is_file() else None
    if long_check is None and not integrity:
        integrity.append("long_prompt_check.json missing")
    verdict, rc, reason = decide(on, rl, long_check, integrity)
    counts = {}
    for tag, (rows, tools, doc) in sides.items():
        rr = list(rows.values())
        counts[tag] = {"rows": len(rr), "finish": {f: sum(1 for r in rr if r.get("finish_reason") == f)
                                                   for f in sorted({r.get("finish_reason") for r in rr}, key=str)},
                       "ctok_sum": sum(r.get("completion_tokens") or 0 for r in rr),
                       "wall_sum_s": round(sum(r.get("wall_s") or 0 for r in rr), 1),
                       "draft_engaged": sum(1 for r in rr if (r.get("draft") or {}).get("draft_n")),
                       "tool_call_rows": sum(1 for t in tools.values() if t.get("tool_calls")),
                       "cached_tokens": [r.get("cached_tokens") for r in rr]}
    cached_info = [list(k) for k in sorted(set(sides["old"][0]) & set(sides["new"][0]))
                   if sides["old"][0][k].get("cached_tokens") != sides["new"][0][k].get("cached_tokens")]
    out = {"verdict": verdict, "rc": rc, "reason": reason, "integrity": integrity,
           "old_vs_new": {"differing": len(on), "diffs": on},
           "new_vs_new_reload": {"differing": len(rl), "diffs": rl},
           "cached_tokens_old_vs_new_differ_info_only": cached_info,
           "long_prompt": long_check, "counts": counts}
    return out


def write_summary(run_dir: Path, state: dict, res: dict) -> None:
    doc = {"model": MODEL, "registry": SERVE_CONFIG, "state": state, **res}
    (run_dir / "merge_gate_summary.json").write_text(json.dumps(doc, indent=1, default=str))
    lp = res.get("long_prompt") or {}
    md = [f"# Upstream-merge identity gate — `{MODEL}`", "",
          f"- **Verdict: {res['verdict']}** (exit {res['rc']}) — {res['reason']}",
          f"- old sha `{state.get('old_sha')}` -> new sha `{state.get('new_sha')}` (`{state.get('branch')}`); "
          f"serving-code hash old `{str(state.get('code_old'))[:12]}` new `{str(state.get('code_new'))[:12]}`",
          f"- identity set: {res['counts'].get('old', {}).get('rows')} requests, sha `{str(state.get('identity_set_sha256'))[:16]}`",
          f"- old vs new: {res['old_vs_new']['differing']} differing; new vs new_reload (reload control): "
          f"{res['new_vs_new_reload']['differing']} differing",
          f"- long prompt (rung {LONG_RUNG}, timeout {(state.get('long_timeout') or {}).get('timeout_s')} s): "
          f"{'PASS' if lp.get('pass') else 'FAIL/not run'} prompt_tokens={lp.get('prompt_tokens')} acc={lp.get('accuracy')} "
          f"finish={lp.get('finish')} prefill_s={lp.get('prefill_s')} reasons={lp.get('reasons')}",
          f"- submodule at exit: {state.get('submodule_final')}", ""]
    for tag in ("old", "new", "new_reload"):
        w = (state.get("workers") or {}).get(tag) or {}
        md.append(f"- worker `{tag}` pid {w.get('pid')} HEAD `{str(w.get('submodule_head'))[:12]}`: `{w.get('cmdline')}`")
    md += ["", "| set | rows | finish | ctok sum | wall sum s | MTP engaged | tool-call rows |", "|---|---|---|---|---|---|---|"]
    for tag, c in res["counts"].items():
        md.append(f"| {tag} | {c['rows']} | {c['finish']} | {c['ctok_sum']} | {c['wall_sum_s']} | {c['draft_engaged']} | "
                  f"{c['tool_call_rows']} |")
    if res["integrity"]:
        md += ["", "## Integrity problems"] + [f"- {p}" for p in res["integrity"]]
    for name, blk in (("old vs new", res["old_vs_new"]), ("new vs new_reload", res["new_vs_new_reload"])):
        if blk["diffs"]:
            md += ["", f"## Per-request differences: {name}", "",
                   "| request | first differing field | all fields | ctok a/b | prompt a/b | finish a/b |",
                   "|---|---|---|---|---|---|"]
            for d in blk["diffs"]:
                a, b = d.get("a") or {}, d.get("b") or {}
                md.append(f"| {d['key'][2]} | {d['first_field']} | {', '.join(d['fields'])} | "
                          f"{a.get('completion_tokens')}/{b.get('completion_tokens')} | "
                          f"{a.get('prompt_tokens')}/{b.get('prompt_tokens')} | {a.get('finish_reason')}/{b.get('finish_reason')} |")
    md += ["", f"Wall times: {json.dumps(state.get('wall_s'))}", "",
           f"Power log ({len(state.get('power_ticks') or [])} ticks): "
           f"{json.dumps(state.get('power_ticks'))[:2000]}"]
    (run_dir / "merge_gate_summary.md").write_text("\n".join(md) + "\n")
    if run_dir.resolve() != WD.resolve():
        for f in ("merge_gate_summary.json", "merge_gate_summary.md"):
            shutil.copyfile(run_dir / f, WD / f)


# ============================================================================ dry-run self-tests (no request)
def dry_selftest() -> list:
    probs = []
    g = ENV["STACK_WORKDIR"] + "/m58/g1b"
    docs = {t: _read_journal(Path(g) / f"replay_{t}.json") for t in ("per_query", "per_query2", "joint_v1")}
    if all(docs.values()):
        rows = {t: {(r["model"], r["bench"], r["id"]): r for r in d["rows"]} for t, d in docs.items()}
        none = {}
        # per_query vs joint_v1 differ in scan policy, so their verify_* counters legitimately differ
        # (M58's own identity tuple excludes verify); the same-policy reload pair compares every field.
        no_verify = tuple(f for f in COMPARE_FIELDS if f != "verify")
        on = compare_sides(rows["per_query"], rows["joint_v1"], none, none, no_verify)
        rl = compare_sides(rows["per_query"], rows["per_query2"], none, none)
        v = decide(on, rl, {"pass": True}, [])
        log(f"selftest comparator on the M58 G1b journals (record: 20/20 identical; per_query->joint_v1 without "
            f"verify_*, per_query->per_query2 on every field): on={len(on)} rl={len(rl)} -> {v[0]}")
        if v[0] != "IDENTICAL":
            probs.append(f"comparator does not reproduce the M58 G1b identity: {on[:2]} {rl[:2]}")
        k = sorted(rows["per_query2"])[3]
        for f, bump in (("completion_tokens", lambda r: r.update(completion_tokens=r["completion_tokens"] + 1)),
                        ("prompt_tokens", lambda r: r.update(prompt_tokens=r["prompt_tokens"] + 1)),
                        ("content_sha256", lambda r: r.update(content_sha256="0" * 64))):
            mut = {kk: dict(r) for kk, r in rows["per_query2"].items()}
            bump(mut[k])
            d = compare_sides(rows["per_query"], mut, none, none)
            v2 = decide(d, [], {"pass": True}, [])
            log(f"selftest known positive ({f} changed on {k[2]}): {len(d)} differing, first={d[0]['first_field'] if d else None} -> {v2[0]}")
            if v2[0] != "DIFFERENT" or len(d) != 1 or d[0]["first_field"] != f:
                probs.append(f"comparator misses a one-field known positive on {f}")
        rate = sum(r["completion_tokens"] for r in docs["per_query"]["rows"]) / sum(
            r["wall_s"] for r in docs["per_query"]["rows"])
        _STATE["est_tps"] = rate
        log(f"selftest decode basis: M58 G1b per_query pass {sum(r['wall_s'] for r in docs['per_query']['rows']):.0f} s "
            f"for {len(docs['per_query']['rows'])} requests, effective {rate:.1f} completion tok/s (used for the prediction)")
    else:
        log("selftest: M58 G1b journals absent — comparator known-positive not exercised")
    ret = RESULTS / "retrieval.m57q-e-q1-20261005.json"
    if ret.is_file():
        rec = [r for r in json.loads(ret.read_text())["records"] if r["ctx"] == 131072][0]
        rec1 = dict(rec, rows=rec["rows"][:1])
        c = long_prompt_check(rec1, 131072)
        log(f"selftest long-prompt rule on a real 131072 row (known negative: below the floor): pass={c['pass']} "
            f"reasons={c['reasons']}")
        if c["pass"] or not all("159744" in r for r in c["reasons"]):
            probs.append(f"long-prompt rule does not fail ONLY on the floor for a real 131072 row: {c['reasons']}")
    ws = worker_procs()
    if ws:
        wp = worker_cmdline_problems(ws[0][1])
        log(f"selftest worker-cmdline check on the LIVE worker pid {ws[0][0]} (daily driver, shipped state): {wp or 'OK'}")
        if wp:
            probs.append(f"worker cmdline check rejects the live shipped-state worker: {wp}")
    else:
        log("selftest: no live worker — cmdline check not exercised")
    return probs


# ============================================================================ main
def gate_run(pf: dict, args) -> int:
    info = pf["info"]
    run_id = time.strftime("%Y%m%d-%H%M%S")
    run_dir = (WD / "dry_run") if DRY else (WD / "runs" / run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    frozen = build_frozen(info["params"])
    fpath = run_dir / "identity_set.json"
    fpath.write_text(json.dumps(frozen, indent=1, sort_keys=True))
    n = len(frozen_keys(frozen))
    theirs = bench_json("import json; from bench import parity_replay as P; "
                        f"rs = P.load_requests({str(fpath)!r}, [{MODEL!r}]); "
                        "print(json.dumps([[r['model'], r['bench'], r['id'], P._payload_sha(r['payload'], r['seed'])] "
                        "for r in rs]))")
    if {(m, b, i): s for m, b, i, s in theirs} != frozen_keys(frozen):
        raise Refusal("parity_replay.load_requests does not reproduce the identity-set keys/payload hashes")
    log(f"identity set: parity_replay.load_requests reads {len(theirs)} requests; payload+seed hashes match")
    pred =predicted_pass_s(frozen, _STATE.get("est_tps") or EST_DECODE_TPS)
    state = {"run_id": run_id, "old_sha": info["old_sha"], "new_sha": info["new_sha"], "branch": info["branch"],
             "fork_path": info["fork_path"], "fork_abs": str(Path(args.fork_path).expanduser().resolve()),
             "code_old": info.get("code_old"), "code_new": info.get("code_new"),
             "identity_set_sha256": hashlib.sha256(fpath.read_bytes()).hexdigest(),
             "long_timeout": info.get("long_timeout"), "preflight": info, "workers": {}, "wall_s": {},
             "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    kinds = {}
    for r in frozen["arms"]["merge_gate"]["requests"]:
        kinds[r["bench"]] = kinds.get(r["bench"], 0) + 1
    log(f"identity set: {n} requests {kinds} sha256={state['identity_set_sha256'][:16]} -> {scrub(fpath)}; "
        f"predicted {pred / 60:.1f} min per pass")
    lt = (info.get("long_timeout") or {}).get("timeout_s") or 10800
    _STATE["long_prefill_hint"] = (info.get("long_timeout") or {}).get("prefill_max_s")
    save = (lambda: (run_dir / "state.json").write_text(json.dumps(
        {**{k: v for k, v in state.items() if k != "fork_abs"}, "power_ticks": _STATE["power_ticks"]},
        indent=1, default=str)))
    save()
    _STATE["run_ctx"] = (run_dir, state)
    if DRY:
        log("PLAN shim (runs as `python -c`; wraps parity_replay._post, appends tool_calls per payload sha):")
        for ln in SHIM.strip().splitlines():
            log(f"    {ln}")
    t_all = time.time()

    log("---- PHASE A: OLD source (submodule untouched)")
    t = time.time()
    router = start_router("old")
    state["workers"]["old"] = load_and_verify_worker("old", info["old_sha"])
    run_pass("old", run_dir, fpath, n, pred, router, state["workers"]["old"].get("pid"))
    stop_stack("old")
    state["wall_s"]["phase_A"] = round(time.time() - t); save()

    log("---- PHASE B: NEW source")
    t = time.time()
    checkout_new(state)
    save()
    router = start_router("new")
    state["workers"]["new"] = load_and_verify_worker("new", info["new_sha"])
    run_pass("new", run_dir, fpath, n, pred, router, state["workers"]["new"].get("pid"))
    unload_worker("reload control")
    state["workers"]["new_reload"] = load_and_verify_worker("new_reload", info["new_sha"],
                                                            previous_pid=state["workers"]["new"].get("pid"))
    run_pass("new_reload", run_dir, fpath, n, pred, router, state["workers"]["new_reload"].get("pid"))
    tl = time.time()
    run_long_prompt(run_dir, run_id, lt, router, state["workers"]["new_reload"].get("pid"))
    state["wall_s"]["long_prompt"] = round(time.time() - tl)
    stop_stack("new")
    state["wall_s"]["phase_B"] = round(time.time() - t); save()

    log("---- PHASE C: verdict (CPU)")
    if DRY:
        log("PLAN verdict: compare old vs new and new vs new_reload per request on " + ", ".join(COMPARE_FIELDS)
            + " (tool_calls from the sidecar with random ids dropped; draft = draft_kind/rounds/n/n_accepted; "
              "verify = every verify_* counter); IDENTICAL only if both comparisons are empty AND the long prompt "
              "passes; kind rule: prompt_tokens = 'prompt' kind, everything else 'generation'; RELOAD_NOISE iff "
              "the reload control differs and old/new difference kinds are within the reload kinds; else DIFFERENT")
        log(f"PLAN restore on every non-IDENTICAL exit (finally): git -C $STACK_REPO submodule update --force {SUBMODULE}"
            f" ; verify HEAD == {str(info['old_sha'])[:12]} and status --porcelain empty")
        restore_submodule(info["old_sha"] or "")
        return RC_OK
    check_instrument("verdict")
    res = analyze_run(run_dir)
    _STATE["verdict"] = res["verdict"]
    _STATE["keep_new"] = res["verdict"] == "IDENTICAL"
    state["wall_s"]["total"] = round(time.time() - t_all)
    state["verdict"] = res["verdict"]
    _STATE["finalize_ctx"] = (run_dir, state, res)
    log(f"VERDICT: {res['verdict']} (exit {res['rc']}) — {res['reason']}")
    for d in res["old_vs_new"]["diffs"][:10]:
        log(f"  old/new {d['key'][2]}: first={d['first_field']} fields={d['fields']} a={d.get('a')} b={d.get('b')}")
    return res["rc"]


def main(argv=None) -> int:
    global DRY, _LOG
    ap = argparse.ArgumentParser(description="Upstream-merge identity gate (old vs new mlx-vlm source)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--analyze-only", action="store_true")
    ap.add_argument("--run-dir", default=None, help="--analyze-only: run dir (default newest under runs/)")
    ap.add_argument("--old-sha", default=DEFAULT_OLD)
    ap.add_argument("--branch", default=DEFAULT_BRANCH)
    ap.add_argument("--new-sha", default=None)
    ap.add_argument("--fork-path", default=str(DEFAULT_FORK))
    args = ap.parse_args(argv)
    DRY = args.dry_run
    _LOG = open(WD / ("dry_run.log" if DRY else "run_merge_gate.log"), "a", buffering=1)
    lock, rc, state_for_restore = None, RC_INTERNAL, None
    try:
        if not DRY:
            lock = open(WD / "run.lock", "w")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                log("REFUSED: another run_merge_gate.py holds run.lock")
                return RC_REFUSED
            if not args.analyze_only:
                (WD / "run_merge_gate.rc").unlink(missing_ok=True)
                (WD / "run_merge_gate.pid").write_text(str(os.getpid()))
        log(f"merge gate start: model={MODEL} mode={'dry-run' if DRY else 'analyze-only' if args.analyze_only else 'RUN'}")
        if args.analyze_only:
            runs = sorted((WD / "runs").glob("*/state.json")) if (WD / "runs").is_dir() else []
            run_dir = Path(args.run_dir) if args.run_dir else (runs[-1].parent if runs else None)
            if run_dir is None:
                raise Refusal("no run dir to analyze")
            st = json.loads((run_dir / "state.json").read_text())
            res = analyze_run(run_dir)
            st["submodule_final"] = submodule_state()
            write_summary(run_dir, st, res)
            log(f"VERDICT (analyze-only, {scrub(run_dir)}): {res['verdict']} (exit {res['rc']}) — {res['reason']}")
            if res["verdict"] != "IDENTICAL" and st["submodule_final"]["head"] != st.get("old_sha"):
                log(f"NOTE {SUBMODULE} is at {st['submodule_final']['head'][:12]}, not the old sha: restore with "
                    f"git -C $STACK_REPO submodule update --force {SUBMODULE} (analyze-only never touches git)")
            rc = res["rc"]
            return rc
        if DRY:
            st = dry_selftest()
            for p in st:
                log(f"selftest PROBLEM — {p}")
        pf = preflight(args)
        if not DRY and (pf["static"] or pf["dynamic"]):
            log("REFUSED: preflight")
            rc = RC_REFUSED
            return rc
        state_for_restore = {"old_sha": pf["info"]["old_sha"], "new_sha": pf["info"]["new_sha"],
                             "branch": pf["info"]["branch"], "uv_lock_sha256": pf["info"]["uv_lock_sha256"]}
        rc = gate_run(pf, args)
        if DRY:
            bad = pf["static"] or st
            log(f"DRY-RUN complete: no request sent, nothing started, no git state touched; "
                f"static problems={len(pf['static'])} would-refuse={len(pf['dynamic'])} selftest problems={len(st)}")
            rc = RC_REFUSED if bad else RC_OK
    except Refusal as e:
        log(f"REFUSED: {e}")
        _STATE["last_error"] = f"refused: {e}"
        rc = RC_REFUSED
    except Tripwire as e:
        log(f"ABORT: {e}")
        _STATE["last_error"] = f"tripwire: {e}"
        rc = RC_TRIPWIRE
    except Exception as e:  # noqa: BLE001
        log(f"INTERNAL ERROR: {type(e).__name__}: {e}")
        _STATE["last_error"] = f"internal: {type(e).__name__}: {e}"
        rc = RC_INTERNAL
    finally:
        for c in _STATE["children"]:
            if c.poll() is None:
                c.kill()
        if _STATE["router_owned"] and not DRY:
            try:
                stop_stack("finally")
            except Exception as e:  # noqa: BLE001
                log(f"STACK STILL UP after abort: {e} — stop it by PID (scripts/stack_stop.sh)")
                rc = RC_TRIPWIRE if rc in (RC_OK,) else rc
        if not DRY and not args.analyze_only and state_for_restore is not None:
            lock_ok = hashlib.sha256((REPO / "uv.lock").read_bytes()).hexdigest() == state_for_restore["uv_lock_sha256"]
            if not lock_ok:
                log("TRIPWIRE: uv.lock changed during the run (a uv re-lock/sync touched the stack) — restoring")
                rc = RC_TRIPWIRE
            if rc != VERDICT_RC.get(_STATE["verdict"] or "", -1):
                _STATE["keep_new"] = False          # any abort, even after the verdict, restores
            try:
                fin = finalize_submodule(state_for_restore)
            except Exception as e:  # noqa: BLE001
                fin = {"action": "restore_crashed", "problems": [f"{type(e).__name__}: {e}"]}
            if fin.get("problems"):
                log(f"SUBMODULE NOT RESTORED/VERIFIED: {fin['problems']} — run: git -C $STACK_REPO submodule "
                    f"update --force {SUBMODULE}")
                rc = RC_TRIPWIRE
            ctx = _STATE.get("finalize_ctx")
            if ctx is None and _STATE.get("run_ctx"):
                run_dir, state = _STATE["run_ctx"]
                ctx = (run_dir, state, {"verdict": "ABORT", "rc": rc, "reason": _STATE.get("last_error"),
                                        "integrity": [], "old_vs_new": {"differing": None, "diffs": []},
                                        "new_vs_new_reload": {"differing": None, "diffs": []},
                                        "long_prompt": None, "counts": {}})
            if ctx:
                run_dir, state, res = ctx
                res["rc"] = rc
                try:
                    state["submodule_final"] = {**submodule_state(), "action": fin.get("action")}
                    state["power_ticks"] = _STATE["power_ticks"]
                    state["uv_lock_unchanged"] = lock_ok
                    write_summary(run_dir, state, res)
                except Exception as e:  # noqa: BLE001
                    log(f"summary write failed: {type(e).__name__}: {e}")
        if not DRY and not args.analyze_only and lock is not None:
            (WD / "run_merge_gate.rc").write_text(f"{rc}\n")
        log(f"merge gate exit rc={rc}")
    return rc


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(Tripwire("SIGTERM")))
    sys.exit(main())
