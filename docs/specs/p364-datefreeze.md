# P364 — freeze the date opencode shows the model (DRAFT v2, 2026-10-17)

Status: DRAFT → Cursor `gpt-5.6-sol-high` review → operator. Motivation: C170 puts `prompt_date` in the tg1 row pairing
key, so a stored reference arm pairs only with same-day runs; C168's ≈ 4 GPU h screen assumed one reference per epoch.
Operator 2026-10-17: "yes, let's fix that. potentially mask the OC timestamps?"

## Evidence (opencode 2.0.20 binary, `$STACK_WORKDIR/opencode-2.0.20/bin/opencode`, extracted by string search)

- Built-in instruction entry `core/date`: `read: <clock>.pipe(map(d => d.toDateString()))`, `render: { initial: d =>
  "Today's date: ${d}", changed: (old, d) => "Today's date is now: ${d}" }` (beside `core/environment`). Instruction
  changes "announce as updates at the next step boundary" — a session crossing midnight receives an extra
  "Today's date is now: …" message mid-run.
- Plugin API v2 (our `noretry.js` uses `ctx.session.hook("retry", …)`, `toolbounds.js` `ctx.tool.hook("execute.before",
  …)`). Session hooks seen in the request path: `context` / `compaction` / `generate` (payload `{...u, agent, tools}`),
  `model.request` (`{...d, baseURL, headers}`), and `http.request` → `e.trigger("session","http.request",{...d,
  request})`; the returned `K.request` (a `Request`) is re-read, body included (`K.request.clone().arrayBuffer()`), and
  sent; `http.response` likewise. The request body carries `system: m.system` and `messages`.

## Change (v2 — applies Cursor round 1 D1–D6, `benchmark/chains/c147/reviews/p364-round1.cursor-gpt-5.6-sol-high.md`)

1. **`benchmark/opencode_plugins/datefreeze.js`** — structured hooks, not the wire (D3): `ctx.session.hook` on `context`,
   `compaction`, `generate` and `title` (every request kind; transport-neutral, so the WebSocket branch is covered and
   serialization, Content-Length, headers and prompt-cache keys stay opencode's own). In each payload's system /
   message text: replace `Today's date: <toDateString>` with the frozen date, and REMOVE the whole midnight update
   message `Today's date is now: …` (D1) so a midnight-crossing item sends the same prompt as one that did not. The
   frozen date comes from env `BENCH_FROZEN_PROMPT_DATE` (exact `Www Mmm DD YYYY` shape), validated at plugin setup and
   per hook; unset / malformed / no date string found where the instruction is expected → throw before the request is
   built (transport abort, never the real date). Activation proven like the existing plugins (GET /api/integration).
2. **Receipts (D2, D4):** one receipt file per item under that item's evidence dir (outside `OPENCODE_CONFIG_DIR`), path
   passed by env; one line per hook call: `sessionID`, request sequence and kind, `n_initial_replaced`,
   `n_update_removed`, sha256 of the system text after masking. The probe reconciles receipts exactly against the
   item's `requests_observed` (every request has one receipt with `n_initial_replaced ≥ 1` where the date instruction
   is present); any mismatch → abort, no row.
3. **Wire verification (D3):** the real-mock capture harness asserts the bytes sent contain the frozen date, never the
   real one, never an update message — for primary, compaction and title requests and a faked midnight crossing; and a
   WebSocket-route test (if the carrier can select it) — else the probe refuses a WebSocket transport.
4. **Identity (D5):** the plugin sha enters `scaffold_policy_sha256` and P311-lite's `GENERATION_DATA` (one new tg1
   epoch). The frozen date is NOT added to the generation composite: it stays the row `prompt_date` (P311 pairing key)
   and is immutable chain metadata — `--frozen-prompt-date` is taken from the reference epoch's `chain.json` (or set
   explicitly when an epoch starts), frozen and reverified on resume, never defaulted to "today" (that would defeat
   reuse). Rows add `prompt_date_real` (spawn-time real date, covariate) and `prompt_date_update_removed` (bool).
5. **AGENTS.md** (M50 line): the bench-owned `OPENCODE_CONFIG_DIR` may also hold `datefreeze.js` by sha (tg1); receipts
   live in the item evidence dir.
6. **Standing check (D6):** on every opencode release (with C154), re-verify the `core/date` render strings and the hook
   payload shape; the plugin's "no date string found" refusal makes drift fail closed.

## Tests (red first; D6)

- Plugin unit tests on recorded hook payloads: exact replacement, update-message removal, nothing else touched.
- Real pinned-binary tests: env propagation through `_opencode_env`, plugin activation, multi-turn item (every request
  receipted), compaction and title requests, headers / prompt-cache key unchanged vs an unmasked control except the
  date text, faked midnight crossing, format drift (fixture with a different date shape → refusal), receipt corruption /
  missing / stale → abort, second item in the same leg (fresh receipt file), M50 inventory unchanged.
- Chain: frozen date taken from the reference `chain.json`, reverified on resume; mismatch refuses.

## Residuals (disclosed)

- Midnight crossing: the update message is removed, so prompts stay identical; the row flags it.
- The model never sees the real date (all arms equal; harmless for coding tasks; a model running `date` in the shell
  still sees the real clock — not masked, P201-visible).
- M64's Pi / dsh arms need their own equivalent (built in each adapter); until then their rows pair same-day only.
