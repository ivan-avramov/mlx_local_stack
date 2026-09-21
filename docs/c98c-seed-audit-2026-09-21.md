# C98 (c) — audit of `openwebui_config.json` seed rows against the live Open WebUI (2026-09-21)

Status: DONE (CPU-only; no model calls). Instrument: `$STACK_WORKDIR/scratch/c98c/c98c_audit.py` — signs in as
the admin, reads `GET /api/v1/configs/export`, and separates the export's **flat dotted rows** (what
`PersistentConfig` reads) from its **nested top-level blob rows** (`ui`, `rag`, `task`, …). Defaults come from
`open_webui.config.DEFAULT_CONFIG` extracted from the shipped `ghcr.io/open-webui/open-webui:main` image
(`018046a13da7`, built 2026-09-04) with the compose environment. Runtime cross-checks: `/api/v1/tasks/config`,
`/api/v1/auths/admin/config`, `/api/v1/retrieval/config`, `/api/config`, `/api/v1/configs/models`.
Live state was read only through the HTTP API.

## Mechanism (confirmed, generalises C98)

`runserver.sh` copies the seed to `open-webui-data/config.json`; OWUI's `import_legacy_config_json` upserts
that nested document and renames it to `old_config.json`. The result is **185 nested blob leaves that equal the
seed byte-for-byte** (184/184 seed leaves match the blob) sitting beside **468 flat rows that the code reads**.
No seed row reaches the flat table. Every value that *is* live is live for another reason: OWUI's own default,
the compose environment (`RAG_WEB_SEARCH_RESULT_COUNT`, `RAG_WEB_SEARCH_CONCURRENT_REQUESTS`,
`ENABLE_OLLAMA_API`), or `openwebui-init/init.py`'s API calls (task model + autocomplete, web search, RAG
embedding, models, functions).

## Seed rows the stack "believes" but that are NOT live (seed ≠ live and seed ≠ default)

| seed row | seed | live (runtime endpoint) | who could apply it |
|---|---|---|---|
| `channels.enable` | true | `ENABLE_CHANNELS false` | nobody — inert |
| `ui.enable_user_webhooks` | true | `ENABLE_USER_WEBHOOKS false` | nobody — inert |
| `task.title.prompt_template` | custom 1480-char template | `''` (OWUI built-in) | nobody — inert |
| `task.follow_up.prompt_template` | custom 827-char template | `''` | nobody — inert |
| `task.tags.prompt_template` | custom 626-char template | `''` | nobody — inert |
| `models.default_metadata.*` (capabilities, `defaultFeatureIds`, `builtinTools`; 20 leaves) | all true / feature list | `DEFAULT_MODEL_METADATA {}` | nobody — inert; per-model capabilities are set by C93/C95 through the API and are live |

The three task templates are not copies of OWUI's defaults (they differ in structure: chat-history block
placement, guideline wording). They were authored, and they have never run.

## Seed rows that are live, but not because of the seed

- `rag.web.search.*` (engine `searxng`, `enable`, result count 10, concurrency 1, searxng URL, ddgs backend)
  → live via `init.py apply_web_search_config` (readback `WEB_SEARCH_ENGINE searxng`, `ENABLE_WEB_SEARCH true`).
- `task.model.*`, `task.autocomplete.*` → live via `init.py apply_task_model_config` (seed says `-1`
  input max length; live is the intended 1000).
- `openai.api_base_urls`, `openai.api_configs.*.model_ids` → maintained by OWUI's connection discovery
  and `init.py`; seed values are stale placeholders.
- `ui.prompt_suggestions` (6), `ui.banners`, `ui.enable_community_sharing`, `ui.enable_message_rating`,
  `folders/notes/memories/users.enable`, `rag.top_k 3`, `rag.web.loader.concurrent_requests 10` (after C98a)
  → equal to OWUI defaults; the seed is redundant.

## Everything else

The remaining ~150 seed leaves equal OWUI's defaults (`rag.*` extractor/OCR/reranker placeholders, engine
API keys `''`, `ldap.enable false`, …): inert and harmless.

## Options (C100)

(a) Minimal honesty pass like C98a: set `channels.enable` and `ui.enable_user_webhooks` to `false`, delete
the three custom task templates and the `models.default_metadata` block. (b) Retire the seed file entirely:
stop the `cp` in `runserver.sh`, delete `openwebui_config.json`, and let `init.py` remain the single source of
truth (it already is). (c) Keep any of the six inert intents by adding them to `init.py` (task templates via
`/api/v1/tasks/config/update`; channels/webhooks via `/api/v1/auths/admin/config`), which makes them live and
therefore something to verify. Recommendation: (b), plus (c) only for the task templates if the operator
wants them — they are the only rows that encode a design intent rather than a copied default.
