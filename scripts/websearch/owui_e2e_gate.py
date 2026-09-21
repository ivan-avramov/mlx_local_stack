#!/usr/bin/env python3
"""End-to-end web-search GATE through Open WebUI, on the path the daily driver takes.

The shipped chat models run `function_calling: native`, so Open WebUI does NOT run its
forced-RAG web search (query generation -> SearXNG -> loader -> chunk -> top_k -> <source>
context). It hands the model two builtin tools instead — `search_web` (SearXNG title/link/
snippet JSON) and `fetch_url` (extracted page text) — and the model decides when to call
them. That is the path this gate measures, and it is the only path the shipped C menu uses.

One item = one fresh saved chat (the frontend's own request shape: chat_id + message id +
session_id, web_search feature on, tool approval `full`, background title/tag/follow-up tasks
off). The tool loop runs server-side; the gate polls the persisted assistant message until
`done`, then grades it mechanically:

  searched         >=1 completed `search_web` call whose result is a non-empty result list
  sources_n        citation sources Open WebUI attached (search results + fetched pages)
  answered         the final assistant message item is `completed` and non-empty
  converged        every worker round finished under the RESOLVED thinking budget
                   (from the router log's per-round prompt/completion counts, fork 0.8 clamp)
  cited            the answer carries at least one `[n]` inline citation
  expectation_hit  queries.json mechanical expectation: expect_tokens in the ANSWER, or
                   expect_domains among the search/fetch evidence the model received
  PASS             searched AND sources_n>0 AND answered AND converged AND cited AND
                   expectation_hit

Gate verdict = every item PASS. This is a pass/fail check that the shipped configuration
delivers cited web evidence into answers; it ranks nothing. `expectation_hit` is a
mechanical proxy, not human relevance grading.

Instrument discipline: a known-positive SearXNG self-test runs before any model call and
the run is INVALID if it fails; item timeouts are DERIVED from the thinking budget and a
floor decode rate (never SDK defaults, retries=0); a stalled item (no persisted progress for
one derived round) aborts the run with a nonzero exit — transport/wedge failures are never
graded. Progress is assessed on a fixed cadence from a daemon thread and written to the log.

Gate chats are exported in full to --out (private: live third-party text) and then DELETED
from Open WebUI unless --keep-chats. Only summary.json is publishable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

CITATION_RE = re.compile(r"\[\d+\]")
METRICS_RE = re.compile(
    r"/v1/chat/completions (?P<status>\d+) \| model=(?P<model>\S+) \| (?P<wall_ms>\d+)ms \| "
    r"TTFT=(?P<ttft_ms>\d+)ms \| (?P<tps>[\d.]+) tok/s \| prompt=(?P<prompt>\d+) \| completion=(?P<completion>\d+)"
)
FETCH_FAIL_RE = re.compile(r"access denied|\"error\"|403 forbidden|captcha|enable javascript", re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Api:
    """Minimal Open WebUI HTTP client. retries=0 by design (see module docstring)."""

    def __init__(self, base: str, token: str | None = None):
        self.base = base.rstrip("/")
        self.token = token

    def _req(self, method: str, path: str, data=None, timeout: float = 60):
        body = json.dumps(data).encode() if data is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        req = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            ctype = r.headers.get("Content-Type", "")
        if "text/event-stream" in ctype:
            return {"_stream": raw.decode("utf-8", "replace")}
        return json.loads(raw) if raw else None

    def get(self, path, timeout=60):
        return self._req("GET", path, timeout=timeout)

    def post(self, path, data, timeout=60):
        return self._req("POST", path, data, timeout=timeout)

    def delete(self, path, timeout=60):
        return self._req("DELETE", path, timeout=timeout)


def login(base: str, email: str, password: str) -> Api:
    api = Api(base)
    data = api.post("/api/v1/auths/signin", {"email": email, "password": password})
    return Api(base, data["token"])


# ----------------------------------------------------------------------------- selection

def select_stratified(queries: list[dict], per_category: int, seed: int) -> list[dict]:
    """Seeded, category-stratified sample: `per_category` from each category, corpus order kept."""
    rng = random.Random(seed)
    categories = sorted({q["category"] for q in queries})
    chosen: list[dict] = []
    for cat in categories:
        pool = [q for q in queries if q["category"] == cat]
        chosen.extend(rng.sample(pool, min(per_category, len(pool))))
    order = {q["id"]: i for i, q in enumerate(queries)}
    return sorted(chosen, key=lambda q: order[q["id"]])


def prepare_output(out: Path) -> None:
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"refusing to reuse nonempty evidence directory: {out}")
    out.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------------- timeouts

def derive_round_timeout(thinking_budget: int, floor_decode_tps: float, safety: float = 1.2,
                         tool_allowance_s: float = 300.0) -> float:
    """Seconds one worker round may legitimately take: full budget at the floor decode rate,
    plus a fixed allowance for search + fetch. Never an SDK default."""
    return thinking_budget / floor_decode_tps * safety + tool_allowance_s


def resolved_thinking_budget(thinking_budget: int, max_tokens: int, cap: int, prompt: int) -> int:
    """Mirror of the fork's silent clamp (see AGENTS.md measurement discipline)."""
    return min(thinking_budget, int(min(max_tokens, cap - prompt) * 0.8))


# ----------------------------------------------------------------------------- router log

def parse_router_metrics(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        m = METRICS_RE.search(line)
        if m:
            d = m.groupdict()
            rows.append({
                "status": int(d["status"]), "model": d["model"], "wall_ms": int(d["wall_ms"]),
                "ttft_ms": int(d["ttft_ms"]), "decode_tps": float(d["tps"]),
                "prompt": int(d["prompt"]), "completion": int(d["completion"]),
            })
    return rows


def read_log_from(path: Path, offset: int) -> tuple[str, int]:
    if not path.exists():
        return "", offset
    with path.open("rb") as f:
        f.seek(offset)
        chunk = f.read()
    return chunk.decode("utf-8", "replace"), offset + len(chunk)


# ----------------------------------------------------------------------------- OWUI chat plumbing

def chat_payload(model: str, q: str, title: str) -> tuple[dict, str, str]:
    """The chat object the frontend persists before it asks for a completion."""
    uid, aid = str(uuid.uuid4()), str(uuid.uuid4())
    ts = int(time.time())
    user_msg = {"id": uid, "parentId": None, "childrenIds": [aid], "role": "user",
                "content": q, "timestamp": ts, "models": [model]}
    asst_msg = {"id": aid, "parentId": uid, "childrenIds": [], "role": "assistant", "content": "",
                "model": model, "modelName": model, "modelIdx": 0, "timestamp": ts, "done": False}
    chat = {
        "title": title, "models": [model], "params": {"tool_approval_mode": "full"},
        "history": {"messages": {uid: user_msg, aid: asst_msg}, "currentId": aid},
        "messages": [user_msg, asst_msg], "tags": [], "files": [], "timestamp": ts * 1000,
    }
    return chat, uid, aid


def completion_payload(model: str, q: str, chat_id: str, asst_id: str, session_id: str) -> dict:
    return {
        "model": model,
        "messages": [{"role": "user", "content": q}],
        "stream": True,
        "chat_id": chat_id,
        "id": asst_id,
        "session_id": session_id,
        "features": {"web_search": True, "code_interpreter": False, "image_generation": False, "memory": False},
        "params": {"tool_approval_mode": "full"},
        "background_tasks": {"title_generation": False, "tags_generation": False, "follow_up_generation": False},
    }


def assistant_message(chat_doc: dict, asst_id: str) -> dict:
    return chat_doc["chat"]["history"]["messages"][asst_id]


# ----------------------------------------------------------------------------- grading

def tool_calls(msg: dict) -> list[dict]:
    """Pair function_call items with their outputs, in order."""
    out = msg.get("output") or []
    calls = []
    outputs = {o.get("call_id"): o for o in out if o.get("type") == "function_call_output"}
    for o in out:
        if o.get("type") != "function_call":
            continue
        res = outputs.get(o.get("call_id"), {})
        text = "".join(p.get("text", "") for p in (res.get("output") or []) if isinstance(p, dict))
        try:
            args = json.loads(o.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {"_raw": o.get("arguments")}
        calls.append({"name": o.get("name"), "arguments": args, "status": o.get("status"),
                      "result_text": text, "result_chars": len(text)})
    return calls


def _search_ok(call: dict) -> bool:
    try:
        parsed = json.loads(call["result_text"])
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(parsed, list) and len(parsed) > 0


def final_message_text(msg: dict) -> tuple[str, bool]:
    """Text of the last `message` output item and whether it completed."""
    items = [o for o in (msg.get("output") or []) if o.get("type") == "message"]
    if not items:
        return msg.get("content") or "", bool(msg.get("done"))
    last = items[-1]
    content = last.get("content")
    if isinstance(content, list):
        text = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    else:
        text = content or ""
    return text, last.get("status") == "completed"


def grade_item(item: dict, msg: dict, rounds: list[dict], thinking_budget: int, max_tokens: int,
               cap: int) -> dict:
    calls = tool_calls(msg)
    searches = [c for c in calls if c["name"] == "search_web"]
    fetches = [c for c in calls if c["name"] == "fetch_url"]
    answer, completed = final_message_text(msg)
    sources = msg.get("sources") or []
    evidence = "\n".join(c["result_text"] for c in calls) + "\n" + json.dumps(sources, ensure_ascii=False)

    searched = any(_search_ok(c) for c in searches)
    answered = completed and bool(answer.strip())
    cited = bool(CITATION_RE.search(answer))
    per_round_ok = [
        r["status"] == 200 and r["completion"] < resolved_thinking_budget(thinking_budget, max_tokens, cap, r["prompt"])
        for r in rounds
    ]
    converged = bool(rounds) and all(per_round_ok)

    tokens = [t.lower() for t in item.get("expect_tokens", [])]
    domains = item.get("expect_domains", [])
    token_hit = any(t in answer.lower() for t in tokens) if tokens else None
    domain_hit = any(d in evidence for d in domains) if domains else None
    expectation_hit = bool(token_hit) or bool(domain_hit)

    fetch_failed = sum(1 for c in fetches if c["result_chars"] == 0 or FETCH_FAIL_RE.search(c["result_text"][:400]))
    flags = {
        "searched": searched, "search_calls": len(searches), "fetch_calls": len(fetches),
        "fetch_failed": fetch_failed, "sources_n": len(sources),
        "sources_chars": sum(len(d) for s in sources for d in s.get("document") or []),
        "answered": answered, "answer_chars": len(answer), "cited": cited,
        "rounds": len(rounds), "converged": converged,
        "prompt_tokens_max": max((r["prompt"] for r in rounds), default=None),
        "completion_tokens_total": sum(r["completion"] for r in rounds),
        "expect_token_hit": token_hit, "expect_domain_hit": domain_hit, "expectation_hit": expectation_hit,
    }
    flags["PASS"] = all([searched, len(sources) > 0, answered, converged, cited, expectation_hit])
    return flags


# ----------------------------------------------------------------------------- self-test

def searxng_selftest(searxng_url: str, query: str = "capital city of Australia", timeout: float = 30) -> dict:
    """Known-positive: SearXNG itself answers. Runs before any model call; failure = INVALID run."""
    params = {"q": query, "format": "json", "pageno": "1", "safesearch": "1", "language": "all",
              "time_range": "", "categories": "", "theme": "simple", "image_proxy": "0"}
    url = searxng_url.rstrip("/") + "/search?" + urllib.parse.urlencode(params)
    t0 = time.time()
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=timeout) as r:
        data = json.loads(r.read())
    results = data.get("results") or []
    return {"query": query, "n_results": len(results), "engines": sorted({e for r in results for e in r.get("engines", [])}),
            "elapsed_s": round(time.time() - t0, 2), "ok": len(results) > 0}


# ----------------------------------------------------------------------------- fingerprint

def fingerprint(api: Api, model: str) -> dict:
    cfg = api.get("/api/config")
    rag = api.get("/api/v1/retrieval/config")
    web = (rag.get("web") or {})
    minfo = api.get(f"/api/v1/models/model?id={urllib.parse.quote(model)}") or {}
    meta = (minfo.get("meta") or {})
    gen = REPO / "searxng" / "settings.generated.yml"
    fp = {
        "owui_version": cfg.get("version"),
        "web_search": {k: web.get(k) for k in ("ENABLE_WEB_SEARCH", "WEB_SEARCH_ENGINE", "WEB_SEARCH_RESULT_COUNT",
                                                 "WEB_SEARCH_CONCURRENT_REQUESTS", "BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL",
                                                 "BYPASS_WEB_SEARCH_WEB_LOADER", "SEARXNG_QUERY_URL", "WEB_LOADER_CONCURRENT_REQUESTS")},
        "rag": {k: rag.get(k) for k in ("TOP_K", "CHUNK_SIZE", "RAG_FULL_CONTEXT", "BYPASS_EMBEDDING_AND_RETRIEVAL")},
        "model": {"id": minfo.get("id"), "function_calling": (minfo.get("params") or {}).get("function_calling"),
                  "capabilities": meta.get("capabilities"), "builtinTools": meta.get("builtinTools")},
        "searxng_settings_generated_sha256": hashlib.sha256(gen.read_bytes()).hexdigest() if gen.exists() else None,
    }
    return fp


# ----------------------------------------------------------------------------- run

class Assessor(threading.Thread):
    """Fixed-cadence progress assessment (operator rule: every run is reported on a cadence
    by a daemon, never by conversational intent)."""

    def __init__(self, state: dict, total: int, every: float, log):
        super().__init__(daemon=True)
        self.state, self.total, self.every, self.log = state, total, every, log
        self.stop = threading.Event()

    def run(self):
        while not self.stop.wait(self.every):
            self.assess("periodic")

    def assess(self, kind: str):
        walls = self.state["walls"]
        done = len(walls)
        mean = statistics.mean(walls) if walls else None
        eta = (self.total - done) * mean if mean else None
        cur = self.state.get("current")
        self.log(f"[assess:{kind}] done={done}/{self.total} fails={self.state['fails']} "
                 f"mean_wall={mean and round(mean)}s max_wall={walls and round(max(walls))}s "
                 f"eta_from_mean={eta and round(eta)}s current={cur} "
                 f"current_elapsed={cur and round(time.time() - self.state['current_t0'])}s")


def run_item(api: Api, item: dict, args, session_id: str, log, state: dict, log_path: Path,
             log_offset: int) -> tuple[dict, int]:
    q = args.prompt_prefix + item["q"]
    chat, uid, aid = chat_payload(args.model, q, f"e2e-gate {args.label} {item['id']}")
    created = api.post("/api/v1/chats/new", {"chat": chat})
    chat_id = created["id"]
    state["current"], state["current_t0"] = item["id"], time.time()
    log(f"[item {item['id']}] chat={chat_id} q={q!r}")

    round_timeout = derive_round_timeout(args.thinking_budget, args.floor_decode_tps)
    t0 = time.time()
    resp = api.post("/api/chat/completions", completion_payload(args.model, q, chat_id, aid, session_id),
                    timeout=round_timeout)
    log(f"[item {item['id']}] completion accepted: {json.dumps(resp)[:200] if isinstance(resp, dict) and '_stream' not in resp else 'stream'}")

    # Poll the persisted assistant message until done; abort on stall (one derived round with
    # no persisted progress) or on the overall cap (rounds_cap x derived round).
    last_sig, last_change = None, time.time()
    deadline = t0 + args.rounds_cap * round_timeout
    while True:
        doc = api.get(f"/api/v1/chats/{chat_id}")
        msg = assistant_message(doc, aid)
        sig = hashlib.sha256(json.dumps(msg.get("output") or msg.get("content"), sort_keys=True, default=str).encode()).hexdigest()
        if sig != last_sig:
            last_sig, last_change = sig, time.time()
        if msg.get("done"):
            break
        if time.time() - last_change > round_timeout:
            raise RuntimeError(f"item {item['id']}: no persisted progress for {round(time.time() - last_change)}s "
                               f"(> derived round timeout {round(round_timeout)}s) — wedge, aborting; chat {chat_id} kept")
        if time.time() > deadline:
            raise RuntimeError(f"item {item['id']}: exceeded overall cap {round(deadline - t0)}s; chat {chat_id} kept")
        time.sleep(args.poll)
    wall = time.time() - t0
    time.sleep(2)  # let the router's metrics line for the final round land
    text, log_offset = read_log_from(log_path, log_offset)
    rounds = [r for r in parse_router_metrics(text) if r["model"] == args.model]
    doc = api.get(f"/api/v1/chats/{chat_id}")
    msg = assistant_message(doc, aid)
    flags = grade_item(item, msg, rounds, args.thinking_budget, args.max_tokens, args.cap)
    row = {"id": item["id"], "category": item["category"], "q": q, "chat_id": chat_id, "wall_s": round(wall, 1),
           "flags": flags, "rounds": rounds, "tool_calls": tool_calls(msg), "usage": msg.get("usage"),
           "sources": msg.get("sources"), "answer": final_message_text(msg)[0], "chat_doc": doc,
           "finished_at": now_iso()}
    state["walls"].append(wall)
    if not flags["PASS"]:
        state["fails"] += 1
    log(f"[item {item['id']}] {'PASS' if flags['PASS'] else 'FAIL'} wall={wall:.0f}s rounds={flags['rounds']} "
        f"search={flags['search_calls']} fetch={flags['fetch_calls']}(failed {flags['fetch_failed']}) "
        f"sources={flags['sources_n']} cited={flags['cited']} conv={flags['converged']} "
        f"expect={flags['expectation_hit']} tokens_out={flags['completion_tokens_total']}")
    return row, log_offset


def summarize(rows: list[dict], fp: dict, selftest: dict, args, started: str) -> dict:
    flags = [r["flags"] for r in rows]
    n = len(rows)
    def count(k): return sum(1 for f in flags if f.get(k))
    walls = [r["wall_s"] for r in rows]
    public_items = []
    for r in rows:
        hosts = sorted({urllib.parse.urlsplit(s.get("source", {}).get("name", "")).hostname or s.get("source", {}).get("name", "")
                        for s in (r["sources"] or [])})
        public_items.append({"id": r["id"], "category": r["category"], "wall_s": r["wall_s"], "flags": r["flags"],
                             "tool_calls": [{"name": c["name"], "arguments": c["arguments"], "result_chars": c["result_chars"]}
                                            for c in r["tool_calls"]],
                             "source_hosts": hosts, "rounds": r["rounds"]})
    return {
        "label": args.label, "started": started, "finished": now_iso(), "model": args.model,
        "selection": {"seed": args.seed, "per_category": args.per_category, "n": n, "ids": [r["id"] for r in rows],
                      "prompt_prefix": args.prompt_prefix},
        "timeouts": {"thinking_budget": args.thinking_budget, "floor_decode_tps": args.floor_decode_tps,
                     "round_timeout_s": round(derive_round_timeout(args.thinking_budget, args.floor_decode_tps)),
                     "rounds_cap": args.rounds_cap, "retries": 0},
        "selftest": selftest, "fingerprint": fp,
        "gate": {"PASS": n > 0 and count("PASS") == n, "pass_n": count("PASS"), "n": n},
        "counts": {k: count(k) for k in ("searched", "answered", "converged", "cited", "expectation_hit")},
        "fetch": {"calls": sum(f["fetch_calls"] for f in flags), "failed": sum(f["fetch_failed"] for f in flags)},
        "search_calls": sum(f["search_calls"] for f in flags),
        "sources_n": [f["sources_n"] for f in flags],
        "wall_s": {"mean": round(statistics.mean(walls), 1) if walls else None, "max": max(walls) if walls else None,
                   "sum": round(sum(walls), 1)},
        "completion_tokens_total": [f["completion_tokens_total"] for f in flags],
        "items": public_items,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="new/empty directory; PRIVATE (holds live third-party text)")
    ap.add_argument("--label", default="e2e")
    ap.add_argument("--model", default="Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed")
    ap.add_argument("--queries", default=str(HERE / "queries.json"))
    ap.add_argument("--per-category", type=int, default=2, help="stratified sample size per category")
    ap.add_argument("--ids", nargs="*", help="explicit query ids (overrides --per-category)")
    ap.add_argument("--seed", type=int, default=20260920)
    ap.add_argument("--prompt-prefix", default="Search the web and cite your sources: ",
                    help="prepended to every query. On the native path the model DECIDES whether to search; the "
                         "smoke showed it answers easy facts from weights. The gate tests the pipeline when the user "
                         "asks for search, so the instruction is explicit and recorded.")
    ap.add_argument("--owui-url", default=os.environ.get("OWUI_URL", "http://localhost:3000"))
    ap.add_argument("--searxng-url", default="http://127.0.0.1:8080", help="loopback-published SearXNG for the self-test")
    ap.add_argument("--router-log", default=str(REPO / "logs" / "main_model.log"))
    ap.add_argument("--thinking-budget", type=int, default=81920)
    ap.add_argument("--max-tokens", type=int, default=102400)
    ap.add_argument("--cap", type=int, default=262144, help="max_kv_cache_size of the served model")
    ap.add_argument("--floor-decode-tps", type=float, default=11.5, help="C84 largest-context decode floor")
    ap.add_argument("--rounds-cap", type=int, default=4)
    ap.add_argument("--poll", type=float, default=5.0)
    ap.add_argument("--assess-every", type=float, default=300.0)
    ap.add_argument("--keep-chats", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    prepare_output(out)
    logf = (out / "gate.log").open("a")

    def log(s: str):
        line = f"{now_iso()} {s}"
        print(line, flush=True)
        logf.write(line + "\n"); logf.flush()

    started = now_iso()
    spec = json.loads(Path(args.queries).read_text())
    if args.ids:
        by_id = {q["id"]: q for q in spec["queries"]}
        items = [by_id[i] for i in args.ids]
    else:
        items = select_stratified(spec["queries"], args.per_category, args.seed)
    log(f"[start] label={args.label} model={args.model} n={len(items)} ids={[q['id'] for q in items]}")

    selftest = searxng_selftest(args.searxng_url)
    log(f"[selftest] searxng {selftest}")
    if not selftest["ok"]:
        log("[INVALID] known-positive SearXNG self-test returned zero results; not calling the model")
        (out / "summary.json").write_text(json.dumps({"INVALID": True, "selftest": selftest}, indent=1))
        return 2

    api = login(args.owui_url, os.environ.get("OWUI_ADMIN_EMAIL", "admin@a.a"), os.environ.get("OWUI_ADMIN_PASSWORD", "admin"))
    fp = fingerprint(api, args.model)
    (out / "fingerprint.json").write_text(json.dumps(fp, indent=1))
    log(f"[fingerprint] {json.dumps(fp)}")
    if fp["model"]["function_calling"] != "native":
        log("[INVALID] model is not function_calling=native; this gate measures the native builtin-tool path only")
        return 2
    if fp["web_search"]["WEB_SEARCH_ENGINE"] != "searxng" or not fp["web_search"]["ENABLE_WEB_SEARCH"]:
        log("[INVALID] web search is not the shipped searxng configuration")
        return 2

    log_path = Path(args.router_log)
    log_offset = log_path.stat().st_size if log_path.exists() else 0
    session_id = f"e2e-gate-{args.label}-{uuid.uuid4().hex[:8]}"
    state = {"walls": [], "fails": 0, "current": None, "current_t0": time.time()}
    assessor = Assessor(state, len(items), args.assess_every, log)
    assessor.assess("baseline")
    assessor.start()

    rows: list[dict] = []
    rc = 0
    try:
        with (out / "items.jsonl").open("a") as jf:
            for item in items:
                row, log_offset = run_item(api, item, args, session_id, log, state, log_path, log_offset)
                jf.write(json.dumps(row, ensure_ascii=False) + "\n"); jf.flush()
                rows.append(row)
    except (RuntimeError, urllib.error.URLError, TimeoutError, OSError) as e:
        log(f"[ABORT] {e}")
        rc = 3
    finally:
        assessor.stop.set()
        assessor.assess("terminal")
        summary = summarize(rows, fp, selftest, args, started)
        summary["rc"] = rc
        (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
        log(f"[summary] gate={'PASS' if summary['gate']['PASS'] and rc == 0 else 'FAIL'} "
            f"pass={summary['gate']['pass_n']}/{summary['gate']['n']} counts={summary['counts']} "
            f"fetch={summary['fetch']} wall={summary['wall_s']}")
        if not args.keep_chats and rc == 0:
            for r in rows:
                try:
                    api.delete(f"/api/v1/chats/{r['chat_id']}")
                except urllib.error.URLError as e:
                    log(f"[cleanup] failed to delete chat {r['chat_id']}: {e}")
            log(f"[cleanup] deleted {len(rows)} gate chats (exported first to {out})")
        logf.close()
    if rc:
        return rc
    return 0 if summary["gate"]["PASS"] else 1


if __name__ == "__main__":
    sys.exit(main())
