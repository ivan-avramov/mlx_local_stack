I reviewed the fix diff, red diff, the proposal, `opencode_v2_destination` (provenance.py:1978–2115), the new and existing tests, and all callers (`run_opencode_probe_v2.py:599,710`, `arm_opencode.py:457,460`).

**F1 — minor (hypothesis). D2 / the M50–C114 "one pre-check discovery call" exception scope.**
- Location: `provenance.py:2050` (the new non-tg1 activation call).
- Evidence: hypothesis (not reproduced). C114 as written in `AGENTS.md` says "the probe's **one** pre-check discovery call." The non-tg1 path now makes a second subprocess (`/api/integration`) in addition to the config call. The tg1 path (`provenance.py:2014`) already makes this same second call and has shipped under review, so the precedent exists; but whether C114 covers two calls (vs. the integration call simply not writing to the data-home) was not verified against the opencode source or the M50 rule text.
- Problem: if C114 is read literally as "one call," the change extends a pre-existing ambiguity to the non-tg1 scaffold; the driver marked this as D2.
- Failure scenario: an operator audit of data-home writes during pre-check flags a second write from the non-tg1 integration call as outside C114.
- Proposed change: confirm against the opencode 2.0.20 source whether `GET /api/integration --standalone` writes to the data-home; if it does, record an explicit C114 clarification that the pre-check discovery exception covers the config+integration pair (as tg1 already relies on). No codechange needed; this is documentation/precedent only.

**F2 — minor (confirmed). The `test_destination_documents` happy path now makes an unverified second call.**
- Location: `test_opencode_v2_provenance.py:218–247`.
- Evidence: confirmed by reading. The fake dispatches on any endpoint and returns the same `stderr`/`stdout` for both calls; the happy-path assertion only checks `calls[0]`. After the fix, a second `/api/integration` call occurs but is not asserted in this test.
- Problem: none material — the new tests (`test_plugin_proof_comes_from_the_activation_call`, `test_plugin_proof_in_the_config_call_alone_refuses`, `test_failed_activation_call_refuses`) explicitly cover the activation call's endpoint, env passthrough, and refusal semantics. Coverage is maintained; noting only that the older test no longer exercises the full call sequence by itself.
- Failure scenario: none — no clause is left untested.
- Proposed change: none required; optionally assert `calls[1][0] == "/api/integration"` in the happy path for symmetry.

**Confirmation of the substantive questions.**

- *Race removed without weakening the tripwire:* yes. The proof now reads `activation.stderr` from `/api/integration` (which awaits `Plugin.awaitActivation`) instead of `r.stderr` from `/api/config` (which does not). `test_plugin_proof_in_the_config_call_alone_refuses` pins that a config-call-only line no longer accepts — strictly stronger, not weaker.
- *Fail-closed preserved:* the `if activation.returncode: refuse(...)` at `provenance.py:2055` guards the new call; `TimeoutExpired` from the new call is caught by the `except Exception` → `refuse` at `provenance.py:2114`. `test_real_missing_print_logs_refuses` (`test_opencode_v2_probe.py:1075`) strips `OPENCODE_PRINT_LOGS`, the activation call passes `env=env` unchanged (no forced logging, per `fix.diff` line "the caller's env as passed, never forced" and the `calls[1][1] == env.get("OPENCODE_PRINT_LOGS")` assertion), so the real binary emits no line and refuses. Constraint holds.
- *No unintended caller behaviour change:* tg1 takes the `scaffold == "opencode-v2-web-tg1"` branch and is untouched (`activation` stays the line-2014 call). The m64 arm (`arm_opencode.py:460`) passes `scaffold=None` with plain `env` and no `require_plugin`, so the proof block is skipped — no new call. The per-item call (`run_opencode_probe_v2.py:710`) likewise skips the proof block. Only the discovery call (`run_opencode_probe_v2.py:599`) hits the new path, and it already sets `OPENCODE_PRINT_LOGS=1` plus `require_plugin=True`.
- *D1 holds:* `/api/integration`'s await-on-`Plugin.awaitActivation` is a server-handler property, not carrier-dependent; tg1 has relied on it for the same endpoint. The non-tg1 carrier differs only in compaction/title/policy/plugin-set, none of which change the integration handler's activation barrier.
- *No vacuous test:* `test_plugin_proof_comes_from_the_activation_call` verifies both the call sequence (`[/api/config, /api/integration]`) and env passthrough; the `require_plugin` param exercises the proof block without `OPENCODE_PRINT_LOGS` in env, and the `print_logs` param exercises it with — both meaningful and non-vacuous.

**NOTHING OF SUBSTANCE.** F1 is a precedent-level documentation hypothesis (not introduced by this change; tg1 already relies on it) and F2 is a non-material test-coverage observation. The change removes the race, keeps the tripwire fail-closed, preserves the constraint, and changes no other caller or scaffold.
