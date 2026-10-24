Findings, round 3 of 3. I read the spec and checked its claims against `chain_core.py`, `chain_hooks.py`, `arm_opencode.py`, `run_config.py` and the mlx-vlm metrics code. I did not review the spec's harvest and freeze sections against code beyond what is listed.

**F1 — blocker. §4.4 / §4.5: the source of the `draft_*` fields is never named.**
- §4.1 lists three sources: `request_usage` (`[message_id, output_tokens, prompt_tokens, budget]`), the server-log lines, and `/metrics` summary counters. None of them carries `draft_rounds`, `draft_n`, `draft_n_accepted` or `draft_kind`.
- The `Request completed` line in `mlx-vlm/mlx_vlm/server/generation.py:654-674` has no draft fields. It adds only verify counters, and only "under a non-default scan policy".
- So the only candidates are the `/metrics` `recent` ring, which is capped at `METRICS_RECENT_LIMIT`, or the per-request `latest` envelope. The spec doesn't say which.
- Failure scenario: a helper reads `recent` after an item of 150+ requests and sees only the last N. Or it reads `latest` once at the barrier. Engagement is then "proven" on a subset, the §4.4 test passes against a fixture, and the goal's "engagement proven on every item" fails on hardware. The Σaccepted ÷ Σproposed acceptance rate for B6/B8 would also be computed from partial data.
- Change: name the per-request source exactly and pin it with the real-adapter fixture. If it is `recent`, poll it at a rate and size bound that cannot overflow, and assert that the count of draft-carrying completed requests equals `|C|`. Otherwise record the counters at the server (a change C225 rules out) or from a source that is not lossy.

**F2 — major. §3 Hooks / §5.2: the hook and policy extension points are narrower than the spec assumes.**
- The `Disposition` vocabulary has no `invalidate`. `from_dict` rejects unknown kinds (`chain_hooks.py:73`), and `BEFORE_KINDS` / `AFTER_KINDS` / `slot_disposition` close the set.
- `after_attempt(slot, done)` (`chain_hooks.py:92`) cannot receive the "full row, ready record, load context" that §3 promises.
- `HookInfrastructureError` is mapped to `pre_spawn_incident` (line 107). A `/metrics` fetch failure or a ready-record write failure in a P426 hook would then become a retryable incident instead of systemic.
- `chain_core.py` branches on `transport_policy == "incident_retry"` at lines 526, 1318, 1353, 1774, 1906 and 2000. A third policy value falls into the `abort_restart` side of each. At line 2000 that means "archive the whole load and rerun, then abort". At 1774 it means `return "incomplete"`.
- Failure scenario: a literal implementation adds `p426_continue` to `TRANSPORT_POLICIES` (`run_config.py:31`) and writes the new loop. The old `!= incident_retry` sites still run: `handle_incomplete` archives the load as `abort_restart` would. A DNF then destroys the leg's earlier rows, or the post-abort path skips the settle.
- Change: enumerate every site that branches on the policy and state the P426 behaviour at each. List the `Disposition` / hook-signature changes explicitly. Say that P426 hook infrastructure errors map to systemic. Add a test per site.

**F3 — major. §11.3: the secret-value scan will refuse everything or nothing.**
- "Exact secret values" of every env key matching `*KEY*`, `*AUTH*` and similar are refused anywhere in staged bytes.
- Behaviour-affecting keys in the arm-equality set (`TQ_*`, `KV_*`, `MLX_*`) can match `*KEY*` and hold values like `4`, `1` or `true`. Examples are a `TQ_KEY_BITS`-style name or `*_AUTH_*` flags.
- Failure scenario: a value of `1` sits in the sequencer environment. Every row and `chain.json` contains `1`. Every file is quarantined and every leg's harvest fails. Or the implementer special-cases short values, and a real short secret then passes.
- Change: add a minimum length or entropy floor for the exact-value match. Add a named non-secret allowlist for keys the receipt records verbatim. Test with a `1`-valued `*KEY*` variable.

**F4 — major. §6.5: the pair gate runs after the second leg of a pair, which is too late.**
- The receipt exists after load of the second leg. Any non-allowed difference (an upgraded package, a changed env var, a different `libmlx`) is found only after the second leg has run for hours.
- That leg's data is already unusable, and per §1 a rerun is an operator decision.
- Change: have the chain compare against the first leg's receipt at its own "After load" checkpoint. The sequencer passes the first leg's receipt path. A difference is then `NOT_STARTED` or systemic before item one. Keep the sequencer gate as a second check.

**F5 — major. §6.4: the arm-equality receipt omits model weight identity.**
- The goal requires legs to "differ only in MTP state".
- The receipt covers argv, env, packages, dylibs and import paths. It does not record the target model snapshot revision or file hashes, or the drafter's snapshot.
- Failure scenario: the HF cache is refreshed or re-synced between OFF and ON legs. If the weights change underneath, that difference is invisible to every check. A drafter-revision change is also unrecorded.
- Change: add the resolved snapshot hash for the target model and the drafter, taken from the worker's open files or the cache `refs`, to the receipt. Allow only the drafter's presence/absence to differ.

**F6 — minor. §5.1 DNF classes: `timeout` / `client_timeout` are classed as transport.**
- A slow or hung generation in the ON arm only (an MTP stall) would be a DNF, "never a model failure", rather than a scored strict fail.
- The "settled, healthy" conditions reduce this, but nothing flags an arm-asymmetric DNF pattern.
- Change: §12 should hand B6/B8 the per-arm DNF counts and causes, flagged whenever the ON/OFF counts or causes differ. That is a scope request for B6; the spec need only carry the data.

**F7 — minor. §4.2: the settle bound of 900 s is chosen without evidence, and a settle timeout is systemic.**
- A legitimate probe kill during a long 256K prefill could exceed 900 s.
- The 900 s figure is not derived from the pilot walls, although C228 says timeouts come from pilot walls.
- Change: derive the settle bound from the pilot's max prefill, or state the observed max prefill that supports 900 s.

**F8 — minor (sensitive area: data boundary). §11.3: the harvest tool reads the operator's credential files.**
- `~/.hftoken`, `~/.cache/huggingface/token`, `config.sh` and `.env` are read. "Listed but unreadable → harvest refuses" means a permissions problem on a token file blocks harvest of every leg.
- Change: confirm at Go that the harvest tool may read these files. Keep the in-memory-only handling. Consider making an unreadable file a recorded warning when no staged file could contain a token.

**F9 — minor. §4.3 / §5.1: wording and economy.**
- The "legs 7–8 reload" description says `chain reload` uses "the pilot's 5 items", but the pilot is an in-load phase that §7 says is ordinary rows. State the reload's in-load phase explicitly.
- Dropping the second `Δprompt_tokens_total` / `Δgenerated_tokens_total` comparison against both log and `request_usage` would not weaken the goal. The log sums already equal the client sums via the count/order equality, so one comparison suffices.

I left the harvest, freeze-tool and lock-order sections as written. They are consistent with the C226–C228 rulings as far as I read them.