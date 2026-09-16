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

```sh
# offline verification, both versions
uv run --no-project --with ddgs==9.14.4 --with pytest --with pydantic \
    -m pytest scripts/websearch/test_ddgs_selection.py -q -p no:cacheprovider
uv run --no-project --with ddgs==9.16.0 --with pytest --with pydantic \
    -m pytest scripts/websearch/test_ddgs_selection.py -q -p no:cacheprovider

# 5-query smoke first
uv run --no-project --with ddgs==9.16.0 --with pydantic scripts/websearch/ddgs_qualify.py \
    --out "$STACK_WORKDIR/websearch/smoke-9.16.0" --limit 5 --burst 0

# one round per version (repeat with --label r2/--round 2 etc. >= 30 min apart)
for v in 9.14.4 9.16.0; do
  uv run --no-project --with "ddgs==$v" --with pydantic scripts/websearch/ddgs_qualify.py \
      --out "$STACK_WORKDIR/websearch/r1-$v" --label r1 --round 1 \
      --backends google duckduckgo brave google,duckduckgo,brave auto
done
```

Outputs contain result titles/snippets/URLs and live under `$STACK_WORKDIR`
(private); only aggregate numbers are copied into the repo.
