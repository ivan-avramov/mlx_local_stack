#!/usr/bin/env python3
"""Bounded DDGS web-search qualification harness (provider-only, no model inference).

Runs the same public/synthetic query set against explicit DDGS backend specs and
records, per search: engines attempted, engines that parsed >=1 result, hosts
contacted, latency, result count, exception class, and mechanical usefulness /
relevance / freshness flags. Output is JSONL + a JSON summary under --out.

Run it from an ISOLATED venv that pins the DDGS version under test; the harness
never installs anything. Example (from the stack root, on the box whose network
you want to characterise):

    uv run --no-project --with ddgs==9.16.0 --with pydantic \
        scripts/websearch/ddgs_qualify.py --out "$STACK_WORKDIR/websearch/r1-9.16.0" \
        --label r1 --backends google duckduckgo brave google,duckduckgo,brave

Add ``--backends auto`` for the live-configuration control; add ``--adapter owui``
to route every search through the vendored Open WebUI ``search_duckduckgo``
adapter instead of calling ``DDGS.text`` directly.

Bounded by construction: N queries x B backend specs sequential searches with a
fixed gap, plus one burst per backend spec (``--burst`` searches at
``--burst-workers`` concurrency). Nothing retries.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import random
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ddgs  # noqa: E402
from ddgs import DDGS  # noqa: E402

import ddgs_instrument  # noqa: E402

REFERENCE_HOSTS = ("wikipedia.org", "grokipedia.com")
FRESH_RE = re.compile(r"\b2026\b|\bago\b|\btoday\b|\byesterday\b|\bhours?\b", re.I)


# ----------------------------------------------------------------------------- scoring
def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def _tokens(q: str) -> set[str]:
    return {t for t in re.split(r"\W+", q.lower()) if len(t) >= 3}


def score(query: dict, results: list[dict]) -> dict:
    """Mechanical usefulness: distinguishes 'returned something' from a useful general-web hit."""
    top5 = results[:5]
    tokens = _tokens(query["q"])
    http_results = [r for r in results if str(r.get("href", "")).startswith("http")]
    relevant = 0
    for r in results:
        text = f"{r.get('title','')} {r.get('body','')}".lower()
        if any(t in text for t in tokens):
            relevant += 1
    exp_hit = False
    for r in top5:
        h = _host(r.get("href", ""))
        text = f"{r.get('title','')} {r.get('body','')}".lower()
        if any(h == d or h.endswith("." + d) for d in query.get("expect_domains", [])):
            exp_hit = True
        if any(t in text for t in query.get("expect_tokens", [])):
            exp_hit = True
    freshness_hint = None
    if query.get("fresh"):
        freshness_hint = any(FRESH_RE.search(f"{r.get('title','')} {r.get('body','')}") for r in top5)
    reference_only = bool(results) and all(
        any(_host(r.get("href", "")).endswith(d) for d in REFERENCE_HOSTS) for r in results
    )
    return {
        "n_results": len(results),
        "n_http": len(http_results),
        "relevant_share": (relevant / len(results)) if results else 0.0,
        "expectation_hit": exp_hit,
        "fresh": None,  # requires dated-source review, not a keyword match
        "freshness_hint": freshness_hint,
        "reference_only": reference_only,
        "useful": len(http_results) >= 3 and exp_hit,  # mechanical proxy, not human relevance
        "domains_top5": [_host(r.get("href", "")) for r in top5],
    }


# ----------------------------------------------------------------------------- search
def _owui_adapter():
    """Import the vendored Open WebUI adapter lazily (needs pydantic)."""
    from owui_vendor import search_duckduckgo  # type: ignore

    return search_duckduckgo


def run_one(query: dict, backend: str, *, max_results: int, timeout: int, adapter: str,
            concurrent_requests: int | None, label: str, mode: str, round_no: int) -> dict:
    sid = uuid.uuid4().hex[:12]
    ddgs_instrument.set_search_id(sid)
    t0 = time.perf_counter()
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results: list[dict] = []
    error = None
    error_class = None
    try:
        if adapter == "owui":
            out = _owui_adapter()(query["q"], max_results, [], concurrent_requests=concurrent_requests,
                                  backend=backend)
            results = [{"title": r.title, "href": r.link, "body": r.snippet} for r in out]
        else:
            with DDGS(timeout=timeout) as d:
                results = d.text(query["q"], safesearch="moderate", max_results=max_results, backend=backend)
    except Exception as ex:  # noqa: BLE001
        error_class = type(ex).__name__
        error = str(ex)[:300]
    elapsed = time.perf_counter() - t0
    ddgs_instrument.set_search_id(None)
    reqs, engs = ddgs_instrument.TRACE.for_sid(sid)
    attempted = sorted({e.engine for e in engs} | {r.engine for r in reqs})
    succeeded = sorted({e.engine for e in engs if (e.parsed or 0) > 0})
    hosts = sorted({r.host for r in reqs})
    row = {
        "sid": sid,
        "label": label,
        "round": round_no,
        "mode": mode,
        "ddgs_version": ddgs.__version__,
        "adapter": adapter,
        "backend": backend,
        "query_id": query["id"],
        "category": query["category"],
        "started": started,
        "elapsed_s": round(elapsed, 3),
        "error_class": error_class,
        "error": error,
        "engines_attempted": attempted,
        "engines_succeeded": succeeded,
        "hosts": hosts,
        "reference_backend_contacted": any(h.endswith(d) for h in hosts for d in REFERENCE_HOSTS),
        "requests": [
            {"engine": r.engine, "host": r.host, "status": r.status, "elapsed_s": round(r.elapsed, 3),
             "bytes": r.nbytes, "error": r.error}
            for r in reqs
        ],
        "engine_parse": [{"engine": e.engine, "parsed": e.parsed, "elapsed_s": round(e.elapsed, 3),
                          "error": e.error} for e in engs],
        "score": score(query, results),
        "results": [
            {"title": (r.get("title") or "")[:160], "href": (r.get("href") or "")[:300],
             "body": (r.get("body") or "")[:4000]}
            for r in results
        ],
    }
    return row


# ----------------------------------------------------------------------------- summary
def _pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, round(p * (len(xs) - 1))))
    return round(xs[k], 3)


def summarize(rows: list[dict]) -> dict:
    out: dict = {}
    keys = sorted({(r["ddgs_version"], r["adapter"], r["backend"], r["mode"]) for r in rows})
    for key in keys:
        sel = [r for r in rows if (r["ddgs_version"], r["adapter"], r["backend"], r["mode"]) == key]
        lat = [r["elapsed_s"] for r in sel]
        n = len(sel)
        returned = sum(1 for r in sel if r["score"]["n_results"] > 0)
        useful = sum(1 for r in sel if r["score"]["useful"])
        errors: dict[str, int] = {}
        for r in sel:
            if r["error_class"]:
                errors[r["error_class"]] = errors.get(r["error_class"], 0) + 1
        empty = sum(1 for r in sel if r["error_class"] == "DDGSException" and "No results" in (r["error"] or ""))
        timeouts = sum(1 for r in sel if r["error_class"] == "TimeoutException")
        eng_att: dict[str, int] = {}
        eng_ok: dict[str, int] = {}
        for r in sel:
            for e in r["engines_attempted"]:
                eng_att[e] = eng_att.get(e, 0) + 1
            for e in r["engines_succeeded"]:
                eng_ok[e] = eng_ok.get(e, 0) + 1
        statuses: dict[str, int] = {}
        for r in sel:
            for q in r["requests"]:
                k = f"{q['engine']}:{q['status'] if q['status'] is not None else 'ERR'}"
                statuses[k] = statuses.get(k, 0) + 1
        by_cat: dict[str, dict] = {}
        for cat in sorted({r["category"] for r in sel}):
            cs = [r for r in sel if r["category"] == cat]
            by_cat[cat] = {
                "n": len(cs),
                "returned": sum(1 for r in cs if r["score"]["n_results"] > 0),
                "useful": sum(1 for r in cs if r["score"]["useful"]),
                "fresh": None,
                "freshness_hint": sum(1 for r in cs if r["score"]["freshness_hint"]) if cat == "news" else None,
            }
        out["|".join(key)] = {
            "ddgs_version": key[0], "adapter": key[1], "backend": key[2], "mode": key[3],
            "searches": n,
            "returned_any": returned,
            "returned_three": sum(r["score"]["n_http"] >= 3 for r in sel),
            "useful": useful,
            "useful_rate": round(useful / n, 3) if n else None,
            "mean_results": round(statistics.mean(r["score"]["n_results"] for r in sel), 2) if sel else None,
            "mean_relevant_share": round(statistics.mean(r["score"]["relevant_share"] for r in sel), 3) if sel else None,
            "latency_p50": _pct(lat, 0.5), "latency_p95": _pct(lat, 0.95), "latency_max": _pct(lat, 1.0),
            "empty": empty, "timeouts": timeouts, "errors": errors,
            "reference_backend_contacted": sum(1 for r in sel if r["reference_backend_contacted"]),
            "engines_attempted": eng_att, "engines_succeeded": eng_ok,
            "request_statuses": statuses,
            "by_category": by_cat,
        }
    # overlap of the combined list vs each individual backend, per (version, adapter, round, query)
    overlaps: dict[str, list[float]] = {}
    seq = [r for r in rows if r["mode"] == "seq"]
    by = {}
    for r in seq:
        by.setdefault((r["ddgs_version"], r["adapter"], r["round"], r["query_id"]), {})[r["backend"]] = r
    for _, group in by.items():
        combined = next((v for k, v in group.items() if "," in k), None)
        if not combined:
            continue
        c = {x["href"] for x in combined["results"]}
        for k, v in group.items():
            if "," in k or k == "auto":
                continue
            s = {x["href"] for x in v["results"]}
            if c or s:
                overlaps.setdefault(f"{combined['ddgs_version']}|{combined['adapter']}|{combined['backend']} vs {k}", []).append(
                    len(c & s) / len(c | s))
    out["_combined_vs_individual_jaccard_mean"] = {k: round(statistics.mean(v), 3) for k, v in overlaps.items()}
    return out


# ----------------------------------------------------------------------------- main
def select_queries(queries: list[dict], limit: int, seed: int) -> list[dict]:
    if not limit or limit >= len(queries):
        return queries
    rng = random.Random(seed)
    categories = sorted({q["category"] for q in queries})
    if limit == len(categories):
        return [rng.choice([q for q in queries if q["category"] == cat]) for cat in categories]
    return rng.sample(queries, limit)


def prepare_output(out: Path) -> None:
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"refusing to reuse nonempty evidence directory: {out}")
    out.mkdir(parents=True, exist_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="output directory (created); private, may hold result text")
    ap.add_argument("--label", default="r1", help="round label, e.g. r1/r2/r3")
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--queries", default=str(HERE / "queries.json"))
    ap.add_argument("--backends", nargs="+", default=["google", "duckduckgo", "brave", "google,duckduckgo,brave"])
    ap.add_argument("--adapter", choices=["ddgs", "owui"], default="ddgs")
    ap.add_argument("--max-results", type=int, default=10, help="OWUI WEB_SEARCH_RESULT_COUNT is 10")
    ap.add_argument("--timeout", type=int, default=5, help="DDGS default timeout (OWUI does not override it)")
    ap.add_argument("--concurrent-requests", type=int, default=5, help="only used with --adapter owui")
    ap.add_argument("--gap", type=float, default=1.0, help="seconds between sequential searches")
    ap.add_argument("--burst", type=int, default=8, help="searches per burst (0 disables)")
    ap.add_argument("--burst-workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="smoke: seeded sample; five selects one per category")
    ap.add_argument("--seed", type=int, default=20260915, help="seeded, category-stratified five-item smoke")
    ap.add_argument("--max-requests", type=int, default=500, help="hard cap on engine HTTP client invocations; redirects internal to the client are not separately counted")
    ap.add_argument("--max-wall-seconds", type=float, default=1800, help="stop admitting searches after this elapsed time")
    ap.add_argument("--no-seq", action="store_true", help="skip the sequential pass")
    args = ap.parse_args()

    spec = json.loads(Path(args.queries).read_text())
    queries = select_queries(spec["queries"], args.limit, args.seed)
    burst_ids = set(spec.get("burst_ids", []))
    burst_queries = [q for q in queries if q["id"] in burst_ids][: args.burst] if args.burst else []

    out = Path(args.out)
    prepare_output(out)
    (out / "queries.json").write_text(json.dumps(spec, indent=2))
    ddgs_instrument.install()
    ddgs_instrument.TRACE.configure_budget(args.max_requests)
    rows_path = out / "searches.jsonl"
    rows: list[dict] = []
    lock = threading.Lock()

    def emit(row: dict) -> None:
        with lock:
            rows.append(row)
            with rows_path.open("a") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        s = row["score"]
        print(f"[{row['backend']:<26}] {row['query_id']} {row['elapsed_s']:6.2f}s "
              f"n={s['n_results']:2d} useful={int(s['useful'])} eng={','.join(row['engines_succeeded']) or '-'} "
              f"{row['error_class'] or ''}", flush=True)

    common = dict(max_results=args.max_results, timeout=args.timeout, adapter=args.adapter,
                  concurrent_requests=args.concurrent_requests, label=args.label, round_no=args.round)
    t_start = time.time()
    stop_reason = None
    for backend in args.backends:
        if not args.no_seq:
            for q in queries:
                if ddgs_instrument.TRACE.budget_exhausted or time.time() - t_start >= args.max_wall_seconds:
                    stop_reason = "request budget" if ddgs_instrument.TRACE.budget_exhausted else "wall budget"
                    break
                emit(run_one(q, backend, mode="seq", **common))
                time.sleep(args.gap)
        if stop_reason:
            break
        if burst_queries:
            if ddgs_instrument.TRACE.budget_exhausted or time.time() - t_start >= args.max_wall_seconds:
                stop_reason = "request or wall budget before burst"
                break
            with ThreadPoolExecutor(max_workers=args.burst_workers, thread_name_prefix="burst") as ex:
                futs = [ex.submit(run_one, q, backend, mode="burst", **common) for q in burst_queries]
                for f in futs:
                    emit(f.result())
            time.sleep(args.gap)

    summary = summarize(rows)
    meta = {
        "label": args.label, "round": args.round, "adapter": args.adapter, "ddgs_version": ddgs.__version__,
        "python": platform.python_version(), "platform": platform.platform(),
        "args": {k: v for k, v in vars(args).items() if k != "out"},
        "queries": len(queries), "burst_queries": len(burst_queries),
        "searches": len(rows), "http_requests": sum(len(r["requests"]) for r in rows),
        "requests_started": ddgs_instrument.TRACE.requests_started,
        "stop_reason": stop_reason,
        "complete": len(rows) == len(args.backends) * ((0 if args.no_seq else len(queries)) + len(burst_queries)),
        "selected_query_ids": [q["id"] for q in queries],
        "scoring": "keyword/domain proxy only; freshness requires manual source review",
        "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
        "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [Path(__file__), HERE / "ddgs_instrument.py", Path(args.queries)]},
        "bytes_received": sum(q["bytes"] for r in rows for q in r["requests"]),
        "wall_s": round(time.time() - t_start, 1),
        "started_utc": datetime.fromtimestamp(t_start, timezone.utc).isoformat(timespec="seconds"),
        "proxy_env_present": any(os.environ.get(k) for k in ("HTTPS_PROXY", "https_proxy", "DDGS_PROXY")),
    }
    (out / "summary.json").write_text(json.dumps({"meta": meta, "summary": summary}, indent=2))
    print(json.dumps(meta, indent=2))
    for k, v in summary.items():
        if k.startswith("_"):
            continue
        print(f"{k:<45} searches={v['searches']:3d} returned={v['returned_any']:3d} useful={v['useful']:3d} "
              f"p50={v['latency_p50']} p95={v['latency_p95']} empty={v['empty']} timeouts={v['timeouts']} "
              f"ref_contacted={v['reference_backend_contacted']}")
    return 0 if meta["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
