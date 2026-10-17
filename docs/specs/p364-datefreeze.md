# P364 — freeze the date opencode shows the model (DRAFT proposal, 2026-10-17)

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

## Change

1. **`benchmark/opencode_plugins/datefreeze.js`** — `ctx.session.hook("http.request", …)`: parse the JSON body, replace
   every `Today's date: <toDateString>` and `Today's date is now: <toDateString>` (regex on the exact
   `toDateString` shape `Www Mmm DD YYYY`) in system / message text with the frozen date from env
   `BENCH_FROZEN_PROMPT_DATE` (must match the same shape); rebuild the `Request` with the new body (content-length
   recomputed). Env unset / malformed → throw (the request fails → transport abort; never the real date). Per request it
   appends a receipt line `{n_initial, n_changed, body_sha256_after}` to `$OPENCODE_CONFIG_DIR/datefreeze.receipts.jsonl`.
2. **Probe** (`run_tg1_probe.py` path): sets `BENCH_FROZEN_PROMPT_DATE` from a new `--frozen-prompt-date` (required for
   tg1; the chain runner passes the epoch value, frozen in `chain.json` like the policy sha); requires ≥ 1 receipt with
   `n_initial ≥ 1` for the first request of every item (else abort: the mask did not fire); row fields:
   `prompt_date` = the frozen date, `prompt_date_real` = the spawn-time real date (covariate), `prompt_date_changed` =
   any receipt with `n_changed ≥ 1` (midnight crossed; flagged in reports).
3. **Identity:** plugin sha in `scaffold_policy_sha256` (like `noretry` / `toolbounds`); the frozen date is part of the
   composite `generation_identity_sha256` (it is prompt content). One new tg1 epoch at merge.
4. **AGENTS.md** (M50 line): the bench-owned `OPENCODE_CONFIG_DIR` may also hold `datefreeze.js` by sha (tg1) and its
   receipts file.
5. **Reports:** pair on the frozen date (the composite) instead of the real date; list `prompt_date_changed` rows.

## Tests (red first)

- Mock model server capture (the existing real-mock harness that pins `permission.rejected`): the bytes received
  contain the frozen date and never the real date, for the initial instruction and for a forced date change
  (clock injected or a long-running mock session across a faked midnight if the client allows; else a body fixture
  through the plugin function directly).
- Plugin unit tests on recorded request bodies: exact-shape replacement, no other text touched, body JSON otherwise
  byte-identical after re-serialization (or the plugin edits strings in place without re-ordering keys), content-length.
- Env unset / malformed → request fails; probe aborts with no row.
- Probe: missing receipt → abort; receipt fields recorded; composite includes the frozen date.
- Chain: frozen date frozen in `chain.json`, reverified on resume.

## Residuals (disclosed)

- A midnight-crossing item still receives one extra (masked) "Today's date is now: <frozen>" message — rare, flagged.
- The model never sees the real date (all arms equal; harmless for coding tasks; a model running `date` in the shell
  still sees the real clock — not masked, P201-visible).
- M64's Pi / dsh arms need their own equivalent (built in each adapter); until then their rows pair same-day only.
