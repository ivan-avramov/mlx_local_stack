# SearXNG engine qualification — 2026-09-16

Decides the web-search engine and configuration the stack ships with. Supersedes
the DDGS-as-default decision of 2026-09-15 (`websearch-ddgs-qualification-2026-09-15.md`,
whose measurements stand; only the conclusion drawn from them changed).

Harness: `scripts/websearch/searxng_qualify.py`. Corpus: the same 25 queries and
mechanical expectations as the DDGS study (`scripts/websearch/queries.json`), so
the two are comparable. Run artifacts contain live third-party result text and
stay out of the repo (`scripts/websearch/runs/`, gitignored).

## Verdict

Ship **SearXNG** with a three-engine whitelist: **`duckduckgo web`, `startpage`,
`google`**. Keyless, so it works on a clean checkout with no signup.

| | sequential 25 | burst 8 @ 4-wide | median latency |
|---|---|---|---|
| shipped config, production request shape | 25/25 useful | 8/8 useful | 0.73 s |

## Why the engine choice was forced

Of Open WebUI's ~20 web-search providers exactly two need no API key: `searxng`
and `duckduckgo`. The keyless Exa endpoint discovered earlier is Exa's **MCP**
server; Open WebUI's `exa` provider calls `api.exa.ai/search` with an `x-api-key`
header and cannot use it. DDGS measured 1/8 under burst on 2026-09-15. That
leaves SearXNG as the only keyless provider that survives agentic traffic.
Hosted providers remain the documented upgrade path, not the default.

## Screen: each engine alone

25 queries, 1.2 s apart, through Open WebUI's exact request shape. Single-engine
numbers answer only "is this engine reachable from this network"; they say
nothing about behaviour under production load and must not be generalised to it.
`duckduckgo web` is the known-positive control and passed, so the zeros below are
findings rather than instrument failure.

| engine | non-empty | useful | median | mechanism |
|---|---|---|---|---|
| `duckduckgo web` | 25/25 | 25 | 0.74 s | control; healthy |
| `google` | 25/25 | 25 | 0.33 s | healthy |
| `google cse` | 25/25 | 25 | 0.39 s | healthy, keyless |
| `startpage` | 25/25 | 25 | 0.44 s | healthy |
| `yep` | 20/25 | 17 | 0.89 s | thin results, mean 7.6 |
| `mwmbl` | 3/25 | 3 | — | timeouts, then suspended |
| `brave` | 0/25 | 0 | — | HTTP 429 after ~6 queries, suspended 180 s |
| `duckduckgo` | 0/25 | 0 | — | CAPTCHA on every query |
| `mojeek` | 0/25 | 0 | — | HTTP 403 access denied |

`marginalia` was excluded before measurement: `require_api_key` is true upstream.

### Corrections to earlier notes

- **`brave` is not "connection-dead"** as the 2026-08-28 note in `settings.yml`
  recorded. It works and then throttles hard — a materially different mechanism,
  and the reason it cannot serve agentic traffic keylessly. Use `braveapi` with
  a key instead.
- **`mojeek` no longer fails silently.** SearXNG now surfaces its 403 as an
  engine error; the old "silent dead weight" note is out of date.
- **`google` was not the liability it looked like.** The 2026-09-15 CAPTCHA
  observation was Google via DDGS's scraper. SearXNG's own `google` engine was
  the *fastest* healthy arm here. Different code path, different outcome.

## Pool: the shape production actually generates

Open WebUI never sends an `engines=` selector, so the instance's default pool is
what serves every query. Three candidate pools, each 25 sequential plus an
8-search burst at 4-wide. All three were perfect (25/25 and 8/8), so availability
did not decide it; contribution did.

| pool | results before truncation | top-3 slots by engine |
|---|---|---|
| `duckduckgo web` | 10.0 | duckduckgo web 99 |
| `+ startpage` | 17.8 | startpage 78, duckduckgo web 21 |
| `+ startpage + google` | 21.3 | google 87, startpage 10, duckduckgo web 2 |

Two conclusions. First, the extra engines genuinely contribute rather than
duplicating: dedup-merged yield rises from 10 to 21.3 before Open WebUI truncates
to 10. Second, adding an engine **re-ranks** more than it broadens what the model
sees, because the count stays at 10.

## Why a pool rather than the single best engine

The earlier report recommended `keep_only: ["duckduckgo web"]`. The measurements
here argue against it. `brave` shows how abruptly a keyless scrape path can go
from healthy to 429-and-suspended, and `duckduckgo web`'s bot-detection bypass
was patched upstream days before this run. A one-engine config returns **zero
results** the moment its engine trips. A three-engine pool keeps answering:
SearXNG suspends the failing engine for 180 s and routes around it
automatically.

That is also the answer to "can we degrade transparently?" — we can, and it needs
no adapter of our own. The degradation is inside SearXNG, per-engine and
self-healing.

The cost is 3× outbound requests per query, which is why search concurrency is
pinned to 1 (below): the fan-out across engines already happens inside SearXNG
for every single query, so client-side concurrency multiplies it.

`google cse` is healthy and keyless but is a fourth path to Google's index; it is
excluded to hold fan-out at three.

## What else the investigation changed

- **The old engine pool was mostly not a web search.** Resolving each engine's
  effective categories (settings entry, else the module's own `categories`, else
  the `["general"]` default) showed 11 engines serving a default query, of which
  four were dictionary, translation and currency widgets (`dictzone`, `lingva`,
  `mymemory translated`, `currency`) whose output was ranked alongside real pages.
  The shipped instance now registers exactly three, all general web.
- **`wikipedia` and `wikidata` are invisible to Open WebUI.** Both are
  `display_type: infobox`, so their output lands in the JSON `infoboxes` key,
  and the adapter reads `results` only. Whitelisting them would have done
  nothing.
- **A latent startup bug was already present.** SearXNG's loader applies
  `keep_only` to the default engine list and merges the user `engines:` list
  afterwards, appending any override whose name it removed. The committed file
  carried an override for `karmasearch`, which upstream had deleted, so it was
  being appended as an engine definition with no module. `render_settings.py`
  now refuses to render such a file, covered by `searxng/test_render_settings.py`.

## Shipped configuration

`searxng/settings.yml` → `settings.generated.yml` (gitignored, mounted):

- whitelist as above, plus `braveapi` and `wolframalpha_api` held inactive for
  the bring-your-own-key path
- `secret_key` generated per render, or pinned via `SEARXNG_SECRET_KEY`
- `image_proxy: false`; `limiter: false` (loopback-only exposure, and the only
  real client is Open WebUI)

`docker-compose.yml`:

- port published as `127.0.0.1:8080:8080`, not `8080:8080`. Off-box exposure made
  this an open unauthenticated search proxy that also burned our rate-limit
  budget. Open WebUI reaches the container over the compose network and never
  used the host mapping.
- `FORWARDED_ALLOW_IPS=*` removed: it tells the ASGI server to trust
  client-supplied `X-Forwarded-For`, which lets any caller forge the address the
  bot limiter keys on. There is no reverse proxy in front of the service.

`openwebui_config.json` + `openwebui-init/init.py`:

| setting | was | now | why |
|---|---|---|---|
| `web.search.engine` | `duckduckgo` | `searxng` | this report |
| `web.search.concurrent_requests` | 0 / 5 | 1 | simultaneous queries trip rate limits |
| `web.loader.concurrent_requests` | 1 | 5 | fetching *content sites* carries no bot-detection risk |
| `rag.top_k` | 3 | 12 | see below |
| `web.search.ddgs_backend` | `auto` | `google,duckduckgo,brave` | `auto` puts reference backends first |

### The retrieval squeeze, and what was deliberately not changed

Ten fetched pages were chunked at 1000 characters and cut to `top_k: 3`, so
roughly 3 KB reached the model. `top_k` is now 12. Note this is a **global RAG
setting**, so it also widens document chat; that is believed to be an improvement
on a 256K-context stack but it was not measured here.

`bypass_web_loader` stays **off**: SearXNG returns ~200-character snippets, so
bypassing the fetch would starve the model. That flag is only useful for
providers that return extracted page content. `bypass_embedding_and_retrieval`
and `full_context` also stay off; sending ten full pages verbatim is plausible at
256K but costs latency and adds boilerplate, and is untested.

## Limits of this study

- **One network, one day.** Every verdict is a property of this box's egress as
  much as of the engine. `brave` was healthy in August and throttles now.
- **Arms share a rate-limit budget.** Arms ran back to back, so a later arm met
  upstreams that had already seen traffic. Pool arms were ordered widest-first so
  the bias works against the recommendation, and the probe container was
  restarted between stages to clear SearXNG-side suspension (which does not clear
  the upstream's memory).
- **`useful` is a mechanical keyword/domain proxy**, not human relevance, and
  freshness needs dated-source review that was not done.
- **No end-to-end chat turn was measured.** Everything here stops at the search
  API. The `<source>` block the model actually receives after loading, chunking
  and retrieval is still unverified — that is the next test, and the `top_k`
  change above is reasoned rather than measured.

## Reproducing

```sh
docker run -d --name searxng-probe -p 127.0.0.1:8089:8080 \
  -v "$PWD/scripts/websearch/probe_settings.yml:/etc/searxng/settings.yml:ro" \
  -e SEARXNG_SETTINGS_PATH=/etc/searxng/settings.yml searxng/searxng:latest

# screen: candidates alone, control included automatically
python3 scripts/websearch/searxng_qualify.py --out scripts/websearch/runs/screen-r2 \
  --label screen-r2 --pace 1.2 \
  --arms brave mojeek startpage yep mwmbl duckduckgo google "google cse"

# the shipped config on the real production path (no engines= selector)
python3 scripts/websearch/searxng_qualify.py --base http://127.0.0.1:8090 \
  --out scripts/websearch/runs/ship-r2 --label ship-r2 --pace 1.2 \
  --burst 8 --burst-width 4 --control "" --arms "@default"
```
