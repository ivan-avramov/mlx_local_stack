# opencode v2.0.20 as a hermetic benchmark scaffold — research report (2026-10-06, source tag v2.0.20 @ 84c9be93a563)

## opencode 2.x as a hermetic benchmark scaffold: research report (M59 / C123)

**Source used.** Repo `sst/opencode` was transferred to `anomalyco/opencode`. Tag `v2.0.20` exists at commit `84c9be93a563`, and it matches the installed binary. I made a shallow clone at `~/ws/mlx_local_stack_workdir/m59_research/src/opencode-v2.0.20`; all paths below are relative to it.

**Docs.** The in-repo `packages/web/src/content/docs/*` and the opencode.ai/docs pages are still the **v1** docs (they show `--pure`, `--dir`, `OPENCODE_DISABLE_CLAUDE_CODE*`). The v2 docs live in `services/www/src/docs/content/*.mdx` (served at opencode.ai/v2/docs). `migrate-v1.mdx` there is the key page.

**What I ran.** Only `--help`, subcommand `--help`, and `debug paths`, with HOME, every XDG_* variable and TMPDIR redirected to `m59_research/sbx{1,2,3}`. These calls started no process. They created only `xdg_{config,state,cache,data}/opencode/`, `.../log/opencode.log`, `.../repos`, `.../bin`, and `tmp/opencode` plus a bun dylib. PID 45130 (`opencode serve --service`, 16 h old) already existed before I started; I did not touch it.

Labels: **SRC** = VERIFIED-FROM-SOURCE, **DOC** = FROM-DOCS (v2), **RUN** = VERIFIED-BY-RUNNING, **ASSUMP** = inferred.

### Q1 Isolation
- **Path resolution (SRC+RUN).**
  - `home = OPENCODE_TEST_HOME ?? os.homedir()` (packages/util/src/global.ts:16-18).
  - data, cache, config and state are `$XDG_*_HOME || ~/.local/share | ~/.cache | ~/.config | ~/.local/state`, then `/opencode` (util/src/global-roots.ts:4-17). Tmp is `os.tmpdir()/opencode`.
  - `OPENCODE_CONFIG_DIR` *replaces* the global config dir (global.ts:79).
  - The DB is `<data>/opencode.db`, or `$OPENCODE_DB` (cli/src/database-path.ts:4-13).
  - `debug paths` (RUN) confirmed every path follows the redirected XDG/TMPDIR, and `home` followed `HOME`.
  - Bun's `os.homedir()` honours HOME (SRC test: packages/util/test/global-roots.test.ts:26-44).
- **Is redirecting HOME enough?** Only if the XDG_* variables are unset, since every root falls back to `os.homedir()`. Redirect all of them explicitly anyway.
- **The background service (SRC+DOC).**
  - What triggers it: every command except `--help`, `debug paths` and `--standalone`/`--server` calls `ServerConnection.resolve()`, which spawns `<self> serve --service` (cli/src/services/server-connection.ts:41-50).
  - Network and lifetime: port 49374 on 127.0.0.1, no idle timeout.
  - Its environment is the env of whichever client spawned it, plus `service set env` (client/src/service-contender.ts:18-22). It runs `chdir($HOME)` (cli/src/server-process.ts:55).
  - Files: the registration file is `$XDG_STATE_HOME/opencode/service.json`. A separate settings file, `<config>/service.json`, holds the password and is written on listen (server-process.ts:132; service-config.ts:94-134). That settings file is the one C123 saw.
  - `run` reuses any existing service, even one of a different version (mismatch "ignore", server-connection.ts:45-48,76).
  - **This is why C123 saw a redirected XDG_CONFIG_HOME ignored:** the run connected to the already-running service and used *that service's* environment.
  - Per-run `OPENCODE_*`/XDG variables are read only by the server process (server-process.ts:103-125). They take effect per run **only with `--standalone`**.
- **`--standalone` (SRC).**
  - Spawns a private child `serve --stdio --port 0` with `extendEnv: true` (the client's full env), and cwd = the client's cwd at startup (cli/src/services/standalone.ts:16-34).
  - The child dies on stdin EOF or SIGTERM (server-process.ts:167-168,197-210). Its logs are discarded unless `OPENCODE_PRINT_LOGS=1`.
- **Config precedence, lowest to highest (SRC: core/src/config.ts:194-238, config/discovery.ts).**
  1. Wellknown/org config. Only loads if you previously ran `auth login <url>`.
  2. Global `<config>/opencode.json`, then `opencode.jsonc`.
  3. The `OPENCODE_CONFIG` file. Resolved against the server's cwd; a missing file is silently ignored.
  4. Project `opencode.json[c]` from the farthest ancestor to the nearest, **up to `/`**. There is no stop at the git root.
  5. All `.opencode/opencode.json[c]`, farthest to nearest. These outrank every direct file.
  6. `OPENCODE_CONFIG_CONTENT` (highest).
- **Merging (SRC).** Most top-level keys follow "last document that sets the key wins". Providers are deep-merged per provider.
- **Bad config is silent (SRC).** Malformed documents are dropped with only a log warning (config.ts:104-134).
- **`OPENCODE_DISABLE_PROJECT_CONFIG=1`** (alias `OPENCODE_CONFIG_PROJECT_DISABLE`; only `"1"`/`"true"` count) removes items 4 and 5, project `.claude`/`.agents`/`.opencode` dirs, and project AGENTS.md.
- **The "git repo only" claim (SRC):** the config walk does not depend on git. Git sets the *project root*, which matters for the AGENTS.md walk and external_directory.
- **Deterministic per-run config is possible (SRC):** `--standalone`, plus `OPENCODE_CONFIG_DIR` pointing at an empty or controlled dir, plus `OPENCODE_DISABLE_PROJECT_CONFIG=1`, plus `OPENCODE_CONFIG_CONTENT` or `OPENCODE_CONFIG`.
- **`debug config` cannot verify this (SRC: handlers/debug/config.ts:10-17).** It has no `--standalone` and always queries the shared service. Use `opencode models --standalone` or `opencode api GET /api/config` against a standalone server instead.

### Q2 Instruction files and skills
- **What is loaded at all.**
  - AGENTS.md only (DOC instructions.mdx:41-43; SRC core/src/config/plugin/instruction.ts:28-76). **CLAUDE.md, `~/.claude/CLAUDE.md` and CONTEXT.md are never loaded** (SRC grep: no references). v2 has no switch for them because none is needed.
  - **The `instructions` config key is parsed but has no effect** (DOC instructions.mdx:101-110; SRC normalize.ts:222, no consumer).
- **Global `<config>/AGENTS.md`.**
  - Always loaded; there is no env switch.
  - Removed by pointing `OPENCODE_CONFIG_DIR`/XDG_CONFIG_HOME at an empty dir, or with config `"plugins":["-opencode.config.instruction"]`, which also kills project AGENTS.md (SRC plugin/supervisor.ts:38-44).
- **Project ancestor walk.**
  - Runs from cwd up to `home` **if cwd is under home**, otherwise up to the project (git) root (instruction.ts:36).
  - **`~/AGENTS.md` exists on this box (2549 B).** Any scratch dir under the real HOME would load it, plus any AGENTS.md in between.
  - Removed by `OPENCODE_DISABLE_PROJECT_CONFIG=1`, or by HOME/`OPENCODE_TEST_HOME` pointing elsewhere so the scratch dir is not under it (then the walk stops at the scratch git root).
- **Nested AGENTS.md below cwd.** Injected after `read` tool calls (core/src/tool/plugin/read.ts:82-106). There is no switch; scratch trees must not contain AGENTS.md.
- **Skills (SRC config/discovery.ts:71-82, config/plugin/compatibility.ts:39-56, config/plugin/skill.ts:83-101; DOC skills.mdx:39-48,166-176).**
  - Built-in skills `opencode` and `report`. Switch: `-opencode.skill`.
  - `~/.claude/skills` and `~/.agents/skills` (**both exist here, containing vnote**), resolved from `home`. Switch: `-opencode.config.compatibility`, or redirect HOME.
  - Project `.claude/skills` and `.agents/skills` up to `/`. Switch: the project env var.
  - `<config>/skills`, `.opencode/skills` and the `skills` config key. Switch: `-opencode.config.skill`.
  - Per skill: a permission `{action:"skill",resource:"*",effect:"deny"}` hides skills.
- **Env names (SRC, confirmed by binary strings).** `OPENCODE_DISABLE_CLAUDE_CODE`, `_CLAUDE_CODE_PROMPT`, `_CLAUDE_CODE_SKILLS`, `OPENCODE_DISABLE_EXTERNAL_SKILLS`, `_AUTOCOMPACT`, `_DEFAULT_PLUGINS` and `_LSP_DOWNLOAD` **do not exist in v2**. They appear only in the stale v1 docs.
- **Your direct question:** v2 never loads `~/.claude/CLAUDE.md`. An empty HOME does remove `~/AGENTS.md` (when scratch is outside it) and the `~/.claude|.agents/skills` directories.

### Q3 Sampling and seed (SRC; DOC migrate-v1.mdx:166,328-408, models.mdx:106-145)
- **Why C123 saw no sampling fields.**
  - `@ai-sdk/openai-compatible` is rewritten to the native `@opencode/ai/providers/openai-compatible`, so no Vercel AI SDK and no npm install (core/src/aisdk-native.ts:67,121-143).
  - Legacy model `options.*` become model `settings` (v1/config/migrate.ts:304-355).
  - The native package destructures `{apiKey, baseURL, body, headers, provider, ...providerOptions}` (packages/ai/src/providers/openai-compatible.ts:48-59).
  - The chat protocol reads only `store` and `reasoningEffort` from providerOptions. **temperature, top_p, top_k, min_p, seed, enable_thinking and thinking_budget in `options`/`settings` are silently dropped.**
- **What the body contains (ai/src/protocols/openai-chat.ts:798-848):**
  - `model`, `messages`, `tools` (with `strict:false`), `tool_choice`, `stream:true`, `stream_options.include_usage`.
  - `max_completion_tokens`: for a local URL unless `compatibility.maxTokensField:"max_tokens"`.
  - `store:false` by default.
  - temperature, top_p, presence/frequency_penalty, seed and stop come only from `generation`, which **no config path sets**.
  - There is no top_k or min_p field at all.
- **Sanctioned route: the `body` overlay.**
  - It is deep-merged over the validated body *after* validation, so arbitrary keys reach the wire and can override protocol fields (ai/src/route/transport/http.ts:33-41).
  - Fed by native `providers.<p>.body`, `models.<m>.body` and `variants[].body`, merged in that order (core/src/model.ts:190-200; model-resolver.ts:137-161,225-231).
  - Also fed by legacy `provider.options.body` and legacy provider/model `options.extraBody` (aisdk-native.ts:153-161).
  - **Legacy *model-level* `options.body` is lost** (model-resolver.ts:225-231).
- **Agent-level fields are inert.** Agent `temperature`/`top_p`/`options` migrate to `agents.<n>.request.body`, but nothing reads `agent.request` when building requests.
- **Other route.** A plugin `session.context` hook can set `options.temperature/topP/seed` (core/src/session/model-request.ts:271-296), but plugins are unattractive here.
- **max_completion_tokens value (model-request.ts:49-57,88-98):** `min(limit.output || 32000, 256000, max(1024, context − measured − ceil(est×1.15)))`. The 102400 in C123 is `limit.output`.
- **Headers added on every request (model-request.ts:274-287):** `x-session-affinity`, `X-Session-Id`, `x-opencode-project/session/client`, and `User-Agent: opencode/...`. These cannot be disabled from config.
- **Minimal snippet (native v2; I believe it works; not captured):**
```json
{"$schema":"https://opencode.ai/config.json","model":"mlx-local/<registry-name>",
 "plugins":["-opencode.provider.vllm","-opencode.provider.ollama","-opencode.provider.lmstudio","-opencode.config.compatibility"],
 "compaction":{"auto":false},"agents":{"title":{"disabled":true}},"update":"disable","share":"disabled",
 "permissions":[{"action":"external_directory","resource":"*","effect":"deny"},{"action":"question","resource":"*","effect":"deny"},{"action":"websearch","resource":"*","effect":"deny"},{"action":"webfetch","resource":"*","effect":"deny"},{"action":"execute","resource":"*","effect":"deny"}],
 "providers":{"mlx-local":{"name":"mlx-serve (local)","package":"@opencode/ai/providers/openai-compatible",
   "settings":{"baseURL":"http://localhost:8000/v1","apiKey":"not-needed"},
   "models":{"<registry-name>":{"capabilities":{"tools":true,"input":["text","image"],"output":["text"]},
     "limit":{"context":262144,"input":159744,"output":102400},
     "body":{"temperature":0.4,"top_p":0.95,"top_k":20,"min_p":0.0,"presence_penalty":0.0,"seed":<per-run>,
             "enable_thinking":true,"thinking_budget":81920}}}}}}
```
  The per-run seed can live in a per-run `OPENCODE_CONFIG_CONTENT` overlay of just `providers.mlx-local.models.<m>.body.seed`; nested `body` deep-merges.
- **Unverified without a capture:**
  - That `body` keys really appear on the wire.
  - Whether mlx-serve wants `enable_thinking` at the top level or under `chat_template_kwargs`.
  - `store:false` and `strict:false` acceptance by mlx-serve.
  - Whether the server honours `max_completion_tokens`.

### Q4 Non-interactive runs (SRC: cli/src/commands/commands.ts:376-417, run/run.ts, run/noninteractive.ts)
- **v2 equivalent:** `cd <cwd>; PWD=<cwd> opencode run --standalone --model provider/model --format json "<prompt>" </dev/null`.
- **Working directory.** There is no `--dir`. root = `process.env.PWD ?? process.cwd()` (run.ts:72). **A Python `subprocess(cwd=X)` inherits the parent's PWD, so set `env["PWD"]=X` explicitly.**
- **stdin.** If stdin is not a TTY, it is read to EOF and appended to the message. Use DEVNULL.
- **Continuing a session.** `--session <id>`, which also creates that ID if it is new. Other flags: `--continue`, `--fork`.
- **Variants.** There is no `--variant`; use `--model p/m#variant`.
- **`--format json` events.** JSONL on stdout: `step_start`, `text` (full text at end, not deltas), `reasoning` (only with `--thinking`), `tool_use`, `step_finish` (reason, tokens, cost), and `error {type:"provider.*", message, status?, response.body?}`.
- **Transcript export.** `opencode session export <id> [--sanitize]` prints JSON `{info, messages}`. It needs `--standalone` with the same data dir, and the ID is required when non-TTY.
- **Retries (SRC core/src/session/runner/retry.ts:42-56; ai/src/provider-error.ts:65-100,213-277).**
  - Session-level retry: up to **10 retries** with jittered backoff 2→10 s (about 84 s), honouring retry-after up to 15 min. specs/v2/session.md says 4; the code wins.
  - Retried, only if no output has started: transport errors (a: connection refused; c: stream dropped / incomplete-stream), 5xx/408/409 (b), and 429.
  - (c) after output has started: the partial answer is kept, a synthetic "continue" message is added, and the run carries on.
  - (d) context-length 400: classified as `context-overflow`. It triggers one compaction and a retry if `compaction.auto`; otherwise it is terminal.
  - There is **no config switch for retries**; only a plugin `retry` hook can veto them.
- **Terminal error and exit code.** A JSON `error` line (or `Error:` on stderr) and **exit 1**. SIGINT gives 130; success gives 0. A cancelled question form also sets exit 1.
- **Client timeouts.** No HTTP header/chunk timeout appears on the native route; the docs' 5-minute `headerTimeout`/`chunkTimeout` apply only to the AI SDK path (ASSUMP, from grep).

### Q5 What loads by default and the `--pure` equivalent (SRC)
There is no `--pure`, and there are no default npm plugins.
- **Local-provider auto-discovery.** The vllm plugin defaults to **`http://127.0.0.1:8000`**: it polls `/health` and `/v1/models` every 30 s (core/src/plugin/provider/vllm.ts:22). It also polls :11434 (ollama) and :1234 (lmstudio). This puts extra traffic on the router. Disable with `plugins:["-opencode.provider.vllm",…]`.
- **models.dev catalogue.** Fetched at start and every 5 min. Disable with `OPENCODE_DISABLE_MODELS_FETCH=1`, or `OPENCODE_MODELS_PATH` for a pinned file.
- **Autoupdate.** Runs in the TUI only. `OPENCODE_DISABLE_AUTOUPDATE=1` / `update:"disable"`.
- **Off unless configured:** MCP and formatter. LSP never runs in v2.
- **ripgrep.** Downloaded lazily if no `rg` is found. Pre-seed `<cache>/bin` or have rg on PATH.
- **File watcher.** `OPENCODE_DISABLE_FILEWATCHER=1`.
- **Telemetry.** OTLP only if `OTEL_EXPORTER_OTLP_ENDPOINT` is set.

### Q6 Permissions (SRC core/src/permission.ts:87-97,173-178; schema/src/agent.ts:46-52; DOC permissions.mdx:197-226)
- **Defaults.** `*` allow, `external_directory` ask, `.env` reads ask. Config key: ordered `permissions` array; the last match wins and deny beats everything.
- **`run` without `--auto`.** Asks are auto-rejected with feedback and the run continues (noninteractive.ts:155-183).
- **`--auto`** (aliases `--yolo`, `--dangerously-skip-permissions`) answers "once" to every ask. It would therefore approve external_directory unless you deny it.
- **Confinement.** Deny `external_directory:*`. "Internal" means cwd **or the git root** (core/src/file-access.ts:94-104). Shell confinement is a text heuristic, not a sandbox.
- **Code-mode `execute` tool.** On by default; it exposes raw `fetch` without the webfetch permission check. Deny `execute`.
- **Question tool.** Allowed for `build`, but a question in `run` sets exit 1. Deny `question`.
- **Saved "always" approvals** persist per project in the DB, so per-run data dirs are needed.

### Q7 Side requests (SRC)
- **Title.** Generated for root sessions using `agents.title.model`. Legacy `small_model` maps to it. Otherwise it picks a small family from the same provider, else the **primary model** (core/src/session/context.ts:95-120). Disable with `agents.title.disabled:true`; `--title X` probably also skips it (ASSUMP).
- **Compaction.** On by default and uses the session model. Disable with `compaction.auto:false`, which also makes overflow terminal.
- **Off by default:** warming. No tool-output summarisation call exists.

### Q8 v1 → v2 breaking changes for the harness
1. CLI: no `--dir`/`--pure`/`--variant`. Use PWD+cwd, `#variant`, and `session export`.
2. A shared service by default; `--standalone` is mandatory for per-run env.
3. Model `options` sampling is dropped. Use `body`.
4. Agent sampling is inert.
5. CLAUDE.md is gone. The AGENTS.md walk runs up to HOME (includes `~/AGENTS.md`), and the `instructions` key is a no-op.
6. Skill compatibility dirs are still loaded, and the v1 disable env vars are gone.
7. Permissions use the `permissions` array; `bash` becomes `shell`, `task` becomes `subagent`, and `write`/`patch` become `edit`.
8. Session-level retries (10×) are on by default. This conflicts with the project's retries=0 rule and can only be vetoed by a plugin.
9. Auto-polling of :8000.
10. Crash recovery: the service resumes sessions that held an execution claim when it was killed (specs/v2/session.md:68). Isolated per-run data dirs make this moot.
11. JSON error types are now `provider.*`.
12. `debug config` reflects the service, not the run.
13. Built-in `execute` tool.
14. LSP removed.

### Recommended hermetic invocation for 2.x
- **Environment.** Start from a clean env (drop all `OPENCODE_*`), then set:
  - `HOME=<run>/home`, `XDG_CONFIG_HOME=<run>/cfg`, `XDG_DATA_HOME=<run>/data`, `XDG_STATE_HOME=<run>/state`, `XDG_CACHE_HOME=<run>/cache`, `TMPDIR=<run>/tmp/` (all under `$STACK_WORKDIR`).
  - `OPENCODE_CONFIG_DIR=<run>/cfg/opencode`, containing only the repo-tracked bench config, recorded by sha.
  - `OPENCODE_CONFIG_CONTENT=<per-run seed overlay>`, or a per-run file via `OPENCODE_CONFIG`.
  - `OPENCODE_DISABLE_PROJECT_CONFIG=1`, `OPENCODE_DISABLE_MODELS_FETCH=1` (plus `OPENCODE_MODELS_PATH` to a pinned catalogue if needed), `OPENCODE_DISABLE_AUTOUPDATE=1`, `OPENCODE_DISABLE_FILEWATCHER=1`.
  - `PWD=<scratch>`.
- **Scratch dir.** A git-initialised dir outside `<run>/home`, with no AGENTS.md.
- **Command:** `opencode run --standalone --model mlx-local/<name> --format json --title probe "<prompt>"`, with `cwd=<scratch>` and stdin DEVNULL.
- **Config.** The snippet in Q3, with `compaction.auto` matching the v1 setting you want to compare against.
- **M50 policy.** The tripwire currently refuses `OPENCODE_CONFIG*`. Using `OPENCODE_CONFIG_DIR` with a sha-recorded repo file is the sanctioned route, so this needs its own ruling as M59 anticipated. The provider baseURL check must read the v2 `providers.*.settings.baseURL`.

### Must be confirmed by a mock-endpoint request capture (in order)
1. `body` keys (temperature, top_p, top_k, min_p, presence_penalty, seed, enable_thinking, thinking_budget) reach the wire, the per-run overlay seed overrides the base, and `max_completion_tokens`/`store`/`strict` are acceptable to mlx-serve (or `maxTokensField:"max_tokens"` is needed).
2. The system prompt contains no `~/AGENTS.md`, global AGENTS.md or skills (vnote absent), and the tool list is as expected (`execute` and `question` absent).
3. No title or other side request reaches the mock; count requests per run.
4. No `/health` or `/v1/models` polling of the mock or :8000 with the provider plugins removed.
5. `--standalone` leaves no surviving `serve --stdio` child, and nothing is written outside `<run>`.
6. Error paths: connection refused, 500, mid-stream drop and context-length 400 each give exit 1 plus a JSON `error` line. Measure how long the 10× retry adds, and decide whether a retry-veto plugin is required for retries=0.
7. `session export` of the run works from the same data dir.
8. PWD vs cwd behaviour from a Python subprocess.

**Could not determine:**
- Whether mlx-serve accepts `store` / `stream_options` / `strict:false`.
- Whether `--title` fully suppresses title generation.
- Whether the native route has any hidden timeout.

All of these are capture-testable.

