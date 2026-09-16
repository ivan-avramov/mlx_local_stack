#!/usr/bin/env python3
"""Qualify SearXNG engine arms for use as Open WebUI's web-search backend.

Two stages, deliberately separated because they answer different questions:

  screen  -- each candidate engine ALONE, one query at a time. Answers "is this
             engine reachable and useful from this network at all?". Single-
             engine numbers say nothing about behaviour under production load
             and must not be generalised to one.
  pool    -- the proposed whitelist as a POOL, sequential then burst, which is
             the shape Open WebUI actually generates. This is the number that
             backs a ship decision.

Requests are built to match Open WebUI's `search_searxng` adapter byte-for-byte
on the parameters it controls (safesearch=1, language=all, empty categories,
pageno=1, theme=simple, image_proxy=0) plus an `engines=` selector, so an arm
that scores here scores the same way in production. Results are sorted by score
and truncated to --count exactly as the adapter does.

Every round re-measures a known-positive control arm. A round whose control
returns nothing is reported as INVALID rather than interpreted: a probe that
cannot distinguish "the engine is blocked" from "the probe is broken" is worse
than no probe.

Output (JSONL + summary JSON) contains live result titles and URLs, so --out
must be a gitignored or out-of-repo directory.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
FRESH_RE = re.compile(r"\b2026\b|\bago\b|\btoday\b|\byesterday\b|\bhours?\b", re.I)
REFERENCE_HOSTS = ("wikipedia.org", "wikidata.org", "wiktionary.org")

# Exactly the parameters open_webui/retrieval/web/searxng.py sends. Kept as a
# literal so drift in the adapter shows up as a diff here.
OWUI_PARAMS = {
    "format": "json",
    "pageno": "1",
    "safesearch": "1",
    "language": "all",
    "time_range": "",
    "categories": "",
    "theme": "simple",
    "image_proxy": "0",
}


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def _tokens(q: str) -> set[str]:
    return {t for t in re.split(r"\W+", q.lower()) if len(t) >= 3}


def score(query: dict, results: list[dict]) -> dict:
    """Mechanical usefulness, same semantics as ddgs_qualify.score.

    SearXNG names the fields `url`/`content` where DDGS uses `href`/`body`;
    everything else is identical so the two corpora stay comparable.
    """
    top5 = results[:5]
    tokens = _tokens(query["q"])
    http_results = [r for r in results if str(r.get("url", "")).startswith("http")]
    relevant = 0
    for r in results:
        text = f"{r.get('title','')} {r.get('content','')}".lower()
        if any(t in text for t in tokens):
            relevant += 1
    exp_hit = False
    for r in top5:
        h = _host(r.get("url", ""))
        text = f"{r.get('title','')} {r.get('content','')}".lower()
        if any(h == d or h.endswith("." + d) for d in query.get("expect_domains", [])):
            exp_hit = True
        if any(t in text for t in query.get("expect_tokens", [])):
            exp_hit = True
    freshness_hint = None
    if query.get("fresh"):
        freshness_hint = any(
            FRESH_RE.search(f"{r.get('title','')} {r.get('content','')}") for r in top5
        )
    reference_only = bool(results) and all(
        any(_host(r.get("url", "")).endswith(d) for d in REFERENCE_HOSTS) for r in results
    )
    return {
        "n_results": len(results),
        "n_http": len(http_results),
        "relevant_share": (relevant / len(results)) if results else 0.0,
        "expectation_hit": exp_hit,
        "fresh": None,  # requires dated-source review, not a keyword match
        "freshness_hint": freshness_hint,
        "reference_only": reference_only,
        "useful": len(http_results) >= 3 and exp_hit,
        "domains_top5": [_host(r.get("url", "")) for r in top5],
    }


#: arm value meaning "send no `engines=` selector", i.e. let the instance use
#: its configured default pool. This is the ONLY arm that reproduces Open WebUI
#: exactly: its adapter never sends `engines=`. Every named arm is a screening
#: device, not a production measurement.
DEFAULT_POOL_ARM = "@default"


def search(base: str, arm: str, q: str, count: int, timeout: float) -> dict:
    """One Open WebUI-shaped query against `base`, restricted to `arm`."""
    params = dict(OWUI_PARAMS, q=q)
    if arm != DEFAULT_POOL_ARM:
        params["engines"] = arm
    url = f"{base.rstrip('/')}/search?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            # The adapter identifies itself to instance operators; SearXNG's
            # bot filter reacts to the UA, so the probe must send the same one.
            "User-Agent": "Open WebUI (https://github.com/open-webui/open-webui) RAG Bot",
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.5",
        },
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
            status = resp.status
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "error": f"HTTP {exc.code}",
                "latency_s": round(time.monotonic() - t0, 3), "results": [], "unresponsive": []}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": None, "error": f"{type(exc).__name__}: {exc}",
                "latency_s": round(time.monotonic() - t0, 3), "results": [], "unresponsive": []}

    # The adapter sorts by score and truncates; grade what the model would see.
    results = sorted(payload.get("results", []), key=lambda x: x.get("score", 0), reverse=True)
    return {
        "ok": True,
        "status": status,
        "error": None,
        "latency_s": round(time.monotonic() - t0, 3),
        "results": results[:count],
        "n_before_truncation": len(results),
        "unresponsive": payload.get("unresponsive_engines") or [],
        "n_infoboxes": len(payload.get("infoboxes") or []),
        "n_answers": len(payload.get("answers") or []),
    }


def _row(arm: str, query: dict, res: dict, count: int, mode: str) -> dict:
    sc = score(query, res["results"]) if res["ok"] else None
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "arm": arm,
        "query_id": query["id"],
        "category": query["category"],
        "q": query["q"],
        "ok": res["ok"],
        "status": res["status"],
        "error": res["error"],
        "latency_s": res["latency_s"],
        "n_before_truncation": res.get("n_before_truncation"),
        "n_infoboxes": res.get("n_infoboxes"),
        "n_answers": res.get("n_answers"),
        "unresponsive": res["unresponsive"],
        "score": sc,
        "results": [
            {"title": r.get("title"), "url": r.get("url"),
             "content": (r.get("content") or "")[:300],
             "engine": r.get("engine"), "engine_score": r.get("score")}
            for r in res["results"]
        ],
    }


def summarise(rows: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for arm in sorted({r["arm"] for r in rows}):
        for mode in sorted({r["mode"] for r in rows if r["arm"] == arm}):
            rs = [r for r in rows if r["arm"] == arm and r["mode"] == mode]
            okr = [r for r in rs if r["ok"]]
            nonempty = [r for r in okr if r["score"]["n_results"] > 0]
            useful = [r for r in okr if r["score"]["useful"]]
            lat = [r["latency_s"] for r in okr]
            unresp: dict[str, int] = {}
            for r in rs:
                for u in r["unresponsive"]:
                    key = " | ".join(str(x) for x in u) if isinstance(u, list) else str(u)
                    unresp[key] = unresp.get(key, 0) + 1
            out[f"{arm} [{mode}]"] = {
                "arm": arm,
                "mode": mode,
                "n": len(rs),
                "http_ok": len(okr),
                "nonempty": len(nonempty),
                "useful": len(useful),
                "useful_rate": round(len(useful) / len(rs), 3) if rs else 0.0,
                "median_latency_s": round(statistics.median(lat), 2) if lat else None,
                "max_latency_s": max(lat) if lat else None,
                "mean_results": round(
                    statistics.mean([r["score"]["n_results"] for r in okr]), 1) if okr else 0.0,
                "unresponsive_engines": unresp,
                "errors": sorted({r["error"] for r in rs if r["error"]}),
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8089")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--arms", nargs="+", required=True,
                    help="engine selectors; comma-joined names make a pool arm")
    ap.add_argument("--control", default="duckduckgo web",
                    help="known-positive arm re-measured every round; '' disables")
    ap.add_argument("--queries", type=Path, default=HERE / "queries.json")
    ap.add_argument("--limit", type=int, default=0, help="first N queries (0 = all)")
    ap.add_argument("--count", type=int, default=10, help="results kept, matches OWUI result_count")
    ap.add_argument("--pace", type=float, default=1.0, help="seconds between sequential searches")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--burst", type=int, default=0, help="burst searches per arm (0 = skip)")
    ap.add_argument("--burst-width", type=int, default=4)
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    if args.out.exists() and any(args.out.iterdir()):
        print(f"ERROR: --out {args.out} exists and is not empty", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)

    spec = json.loads(args.queries.read_text())
    queries = spec["queries"]
    if args.limit:
        queries = queries[: args.limit]
    burst_ids = set(spec.get("burst_ids") or [])
    burst_queries = [q for q in spec["queries"] if q["id"] in burst_ids]

    arms = list(args.arms)
    if args.control and args.control not in arms:
        arms.append(args.control)

    rows: list[dict] = []
    jsonl = (args.out / "searches.jsonl").open("w")
    total = len(arms) * len(queries)
    done = 0
    t_start = time.monotonic()

    for arm in arms:
        for q in queries:
            res = search(args.base, arm, q["q"], args.count, args.timeout)
            row = _row(arm, q, res, args.count, "sequential")
            rows.append(row)
            jsonl.write(json.dumps(row) + "\n")
            jsonl.flush()
            done += 1
            flag = "ok " if res["ok"] and row["score"]["n_results"] else "EMPTY"
            print(f"[{done:3d}/{total}] {flag} {arm:22s} {q['id']:8s} "
                  f"n={row['score']['n_results'] if row['score'] else '-':>3} "
                  f"{res['latency_s']:5.2f}s {res['error'] or ''}", flush=True)
            time.sleep(args.pace)

    if args.burst and burst_queries:
        for arm in arms:
            print(f"--- burst x{args.burst} @ {args.burst_width}-wide: {arm}", flush=True)
            picks = (burst_queries * ((args.burst // len(burst_queries)) + 1))[: args.burst]
            with ThreadPoolExecutor(max_workers=args.burst_width) as pool:
                futs = [pool.submit(search, args.base, arm, q["q"], args.count, args.timeout)
                        for q in picks]
                for q, f in zip(picks, futs):
                    row = _row(arm, q, f.result(), args.count, "burst")
                    rows.append(row)
                    jsonl.write(json.dumps(row) + "\n")
            jsonl.flush()

    jsonl.close()

    summary = summarise(rows)
    control_ok = None
    if args.control:
        c = summary.get(f"{args.control} [sequential]")
        control_ok = bool(c and c["nonempty"] >= max(1, int(0.8 * c["n"])))

    meta = {
        "label": args.label,
        "started": datetime.fromtimestamp(time.time() - (time.monotonic() - t_start),
                                          timezone.utc).isoformat(),
        "finished": datetime.now(timezone.utc).isoformat(),
        "base": args.base,
        "arms": arms,
        "control": args.control or None,
        "control_valid": control_ok,
        "n_queries": len(queries),
        "count": args.count,
        "pace_s": args.pace,
        "burst": args.burst,
        "burst_width": args.burst_width,
        "owui_params": OWUI_PARAMS,
        "scoring": "keyword/domain proxy only; freshness requires manual source review",
        "by_arm": summary,
    }
    (args.out / "summary.json").write_text(json.dumps(meta, indent=2))

    print()
    if control_ok is False:
        print("!! CONTROL ARM FAILED -- round is INVALID, do not interpret the numbers")
    print(f"{'arm':24s} {'mode':11s} {'ok':>5s} {'nonempty':>9s} {'useful':>7s} "
          f"{'rate':>6s} {'med_s':>6s} {'mean_n':>7s}")
    for k, v in summary.items():
        print(f"{v['arm']:24s} {v['mode']:11s} {v['http_ok']:>3d}/{v['n']:<2d} "
              f"{v['nonempty']:>9d} {v['useful']:>7d} {v['useful_rate']:>6.2f} "
              f"{str(v['median_latency_s']):>6s} {v['mean_results']:>7.1f}")
    print(f"\nwrote {args.out}/summary.json")
    return 0 if control_ok is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
