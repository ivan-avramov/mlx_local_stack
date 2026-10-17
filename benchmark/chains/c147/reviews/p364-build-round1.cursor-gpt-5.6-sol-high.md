F1 HIGH — `benchmark/bench/datefreeze.py:76-117`, `benchmark/bench/opencode_v2_core.py:105-129`  
Failure: receipts are unsigned files whose path and frozen date are exposed to model shell commands. The same-UID model can alter or synthesize structurally valid receipts; `system_sha256` is only format-checked. Therefore receipt reconciliation is not an independent safeguard against silent/no-op plugin failure. Corruption causes a safe abort, but forgery can support a false pass if activation misses a failure.  
Fix: keep receipt transport outside tool subprocess visibility—prefer a harness-owned broker/inherited non-tool FD with authenticated records. Random paths or permissions alone are insufficient under the same UID.

F2 MEDIUM — `benchmark/opencode_plugins/datefreeze.js:50-80`  
Failure: `cleanMessages` edits every role except assistant/tool, so user or synthetic text beginning `Today's date is now:` is removed. Its global `removed` counter can also delete an unrelated empty message after removing an update elsewhere.  
Fix: target only the pinned binary’s `role:"system"` update shape, require the exact date-shaped update text, and calculate message emptiness from per-message removals.

F3 MEDIUM — `benchmark/bench/chain_ops.py:931-939`  
Failure: `validate_leg` verifies events, stderr, and export evidence, but omits the load-bearing `datefreeze` receipt even though its hash is recorded. Deleted or modified receipt evidence can therefore survive final chain validation.  
Fix: record a portable receipt path and verify its hash during `validate_leg`; require the expected evidence-key set.

Non-blocking: `benchmark/bench/tests/test_p364_datefreeze.py:447-451` claims to verify the receipt hash against wire text, but `or FROZEN in system` makes the assertion pass whenever masking occurred, regardless of hash correctness.

Judgments:
- The activation scan catches the pinned binary’s exact `failed to load plugin` diagnostic for any plugin, including `noretry.js` and `toolbounds.js`; it cannot cover silent/no-op registration. Datefreeze receipts address that only after F1.
- Campaign requests use `context`/primary; `generate` is registered but not observed on this carrier. Title-only zero replacement is sound and production reconciliation rejects every non-primary kind.
- Binary inspection confirms `session.instructions.updated` becomes a system message whose text is converted to provider `role:"system"` content. The injected test shape is representative, subject to F2.
- The killed-item ±1 allowance correctly covers one in-flight hook/event ordering difference.
- A4 tests session pinning, not prompt identity; omitting datefreeze there is acceptable.
- Plugin identity, generation identity, frozen-date CLI/resume behavior, old-chain refusal, fake-probe parity, AGENTS.md M50 amendment, and pinned-binary coverage are otherwise correctly wired.
- Review was read-only; tests were inspected, not executed.

VERDICT: CLEARED AFTER FIXES F1 F2 F3No follow-up needed; the completed reviews do not change the prior verdict.
