# Web-search provider qualification (DDGS)

Bounded, provider-only qualification of the `ddgs` library as Open WebUI's
web-search engine (`web.search.engine = duckduckgo`, `web.search.ddgs_backend =
<explicit list>`). No model inference is involved; nothing here touches the
running container. Full write-up: `docs/websearch-ddgs-qualification-2026-09-15.md`.

## Files

- `ddgs_qualify.py` — the harness. One invocation = one round for one DDGS
  version: every query x every backend spec sequentially (1 s gap), then one
  8-search burst at 4-wide per backend spec. Writes `searches.jsonl` (one row
  per search: engines attempted / succeeded, hosts, per-request status and
  latency, results, mechanical usefulness flags) and `summary.json`.
- `ddgs_instrument.py` — observation-only monkeypatches on `ddgs` that record
  every engine HTTP request and parse outcome against the owning search.
- `queries.json` — 25 public/synthetic queries, 5 per category (factual, docs,
  news, regional, long natural-language), each with a mechanical expectation.
- `owui_vendor/` — byte-identical copy of Open WebUI's
  `retrieval/web/duckduckgo.py` (provenance in `__init__.py`) plus the minimal
  shim it needs, so `--adapter owui` exercises the real adapter code.
- `test_ddgs_selection.py` — offline (fake transport) verification of backend
  selection, invalid-backend handling, concurrency, dedup, timeout and adapter
  pass-through. Run under every DDGS version being compared.

## Run (on the box whose network is being characterised)

Use an explicit venv under `$STACK_WORKDIR`, not just `uv run --no-project`:
the latter can still expose an existing stack environment beneath its overlay.
Pin and record shared transport/parser dependencies for a version comparison.
The host study uses `primp==2.0.0`, `lxml==6.1.1`, and `pydantic==2.13.4`,
matching the cached OWUI image for those packages.

Outputs must be new/empty directories. `--max-requests` atomically caps engine
HTTP client calls (library-internal redirects are not counted separately);
`--max-wall-seconds` stops admitting new searches but does not cancel in-flight
threads. Incomplete runs return nonzero. A five-query smoke is seeded and
stratified across categories. `useful` remains a mechanical proxy; `fresh` stays
null pending manual dated-source review. Wikipedia result URLs are permitted.

```sh
# Prepare one environment per version; repeat for 9.14.4.
uv venv --python 3.12 "$STACK_WORKDIR/websearch/venvs/ddgs-9.16.0"
uv pip install --python "$STACK_WORKDIR/websearch/venvs/ddgs-9.16.0/bin/python" \
    ddgs==9.16.0 primp==2.0.0 lxml==6.1.1 pydantic==2.13.4 pytest
"$STACK_WORKDIR/websearch/venvs/ddgs-9.16.0/bin/python" -m pytest \
    scripts/websearch/test_ddgs_selection.py scripts/websearch/test_ddgs_guardrails.py \
    -q -p no:cacheprovider --basetemp "$STACK_WORKDIR/websearch/pytest-916"

# 5-query smoke first
"$STACK_WORKDIR/websearch/venvs/ddgs-9.16.0/bin/python" scripts/websearch/ddgs_qualify.py \
    --out "$STACK_WORKDIR/websearch/smoke-9.16.0" --limit 5 --burst 0 --max-requests 100

# one round per version (repeat with --label r2/--round 2 etc. >= 30 min apart)
for v in 9.14.4 9.16.0; do
  "$STACK_WORKDIR/websearch/venvs/ddgs-$v/bin/python" scripts/websearch/ddgs_qualify.py \
      --out "$STACK_WORKDIR/websearch/r1-$v" --label r1 --round 1 \
      --backends google duckduckgo brave google,duckduckgo,brave auto
done
```

Outputs contain result titles/snippets/URLs and live under `$STACK_WORKDIR`
(private); only aggregate numbers are copied into the repo.
