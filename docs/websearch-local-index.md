# Local-index web search — deferred design

Status: **DEFERRED, not rejected.** Nothing here is built. The stack ships the
qualified SearXNG pool (`websearch-searxng-qualification-2026-09-16.md`); this
records the design and the evidence gathered so far so the question can be
reopened without redoing the research.

Motivation: a local index removes the failure mode that dominates every keyless
web-search option — bot detection. `brave` went from healthy to HTTP 429 in six
queries; `duckduckgo` CAPTCHAs on every query; `mojeek` returns 403. An index we
hold cannot rate-limit us. The question is what can realistically be held.

## Verdict by tier

| tier | feasible locally | size | notes |
|---|---|---|---|
| API/language documentation | **yes** | ~0.57 GB | DevDocs ZIM via Kiwix; 231 sets |
| package/library discovery | **yes, keyless remote** | 0 | `deps.dev`, GitHub search API |
| curated fresh sources | **yes** | small | RSS/Atom pull on a schedule |
| general encyclopedic | yes, large | ~100 GB | Wikipedia ZIM; rarely the bottleneck |
| **general web** | **no** | — | crawl, storage and freshness all infeasible |

The honest summary: a local index solves the *coding reference* problem very
well and the *general web* problem not at all. It is a complement to a search
engine, never a replacement.

## Tier 1 — DevDocs offline (the one clearly worth building)

Kiwix publishes DevDocs as ZIM files; the full set is roughly 0.57 GB, which is
trivially shippable and updatable. A coverage probe against the Kiwix catalogue:

- **hits**: python, go, rust, react, react-native, django, nginx, docker,
  kubernetes, terraform, postgresql, sqlite, redis
- **misses**: aws, google cloud, azure, mysql, mongodb, elasticsearch, kafka,
  ffmpeg, openai, stripe, snowflake, databricks

So it covers language and core-infrastructure reference well and cloud-vendor
documentation badly. Cloud docs are exactly the fast-moving, sprawling corpus a
local mirror handles worst, so the split is structural rather than incidental.

Integration options, cheapest first:

1. **Kiwix sidecar + `kiwix-serve`**, queried directly by the harness. No Open
   WebUI integration at all; useful to OpenCode via a tool.
2. **Open WebUI `external` provider.** Open WebUI's generic provider POSTs
   `{"query": ..., "count": ...}` and expects `[{link, title, snippet}]`. A thin
   adapter over `kiwix-serve` satisfies that contract, which is the cheapest way
   to put a local index behind the normal Open WebUI search UI.
3. **A SearXNG engine.** SearXNG already has local-index engine modules; adding
   one keeps everything behind the single existing surface and inherits the
   pooling and suspension behaviour for free. Probably the right end state.

Option 3 is attractive precisely because the shipped architecture already treats
SearXNG as the aggregation point. A local DevDocs engine would join the pool and
outrank scraped results for documentation queries without any new surface.

## Tier 2 — package discovery without a crawl

`deps.dev` and the GitHub search API are keyless and answer "what library does X
in language Y" better than a general web search does, because they query
structured registry data rather than blog posts. Nothing to index; this is an API
call, and the only work is a tool definition.

## Tier 3 — freshness from curated feeds

News and release announcements are the category a local index is worst at and
where staleness is most damaging. RSS/Atom from a curated source list, pulled on
a schedule into a small local store, covers the narrow "what changed recently in
the projects we care about" need. It does not cover open-ended current events —
accept that and route those to the search engine.

## Why not a general local web index

Discarded on three independent grounds, any one of which is fatal:

- **Crawl.** Building a general index means politely crawling the open web. The
  bot-detection problem is not avoided, it is multiplied.
- **Storage.** Useful general coverage is measured in terabytes.
- **Freshness.** Daily updates over a general corpus are a bandwidth and
  scheduling problem far larger than the stack.

Common Crawl and similar corpora sidestep the crawl but not the storage, and
their freshness is measured in months.

## If this is picked up

Sequence, cheapest evidence first:

1. Measure how much of the harness's real query traffic is documentation-shaped.
   If it is small, the whole tier-1 argument weakens and nothing else matters.
2. Stand up `kiwix-serve` with the DevDocs ZIM and measure answer quality on
   documentation queries against the shipped SearXNG pool, using the existing
   corpus and `useful` proxy so the numbers are comparable.
3. Only if tier 1 wins on that comparison, decide between the `external` provider
   and a SearXNG engine module.

Pre-register the acceptance criterion before step 2: a local index that does not
beat the shipped pool on documentation queries is not worth its update pipeline.
