Not ready.

1. blocker — `benchmark/bench/p426_verify.py:235-253` — Item records are optional and not required one-to-one with completed rows; a missing/mis-slotted arm item is accepted, then omitted from speed/acceptance, enabling arm-dependent selection. Fix: refuse unless every row has exactly one matching non-ready item record with the expected slot.

2. major — `benchmark/bench/p426_verify.py:435-440` — F1 is valid: one seed-mismatched key rejects the entire session, discarding valid keys and changing Holm’s family. Fix: reject only that key; keep the session accepted if all session-level rules pass.

3. major — `benchmark/bench/p426_signals.py:488-502` — A sequencer `makeup` record produces “substitution pending,” although §4.4 requires the substituted strict delta. Fix: load, verify, and score the named make-up legs.

4. major — `benchmark/bench/p426_signals.py:310-316` — Pilot/reload noise is computed even when B8 rejected either diagnostic pair; only a boolean label reveals this. Fix: emit no same-epoch number unless both diagnostic pairs were accepted.

5. major — `benchmark/bench/p426_signals.py:287-307,313-314,346` — Noise-floor intersections omit DNF-only slots, so a DNF→success flip disappears and the denominator shrinks. Fix: compare planned outcome maps with DNF represented as non-success.

6. major — `benchmark/bench/p426_signals.py:181-190` — Primary speed ignores `decode_rate_source`; unsupported totals can enter the headline ratio. Fix: accept totals only when their source denotes completed requests, otherwise drop and list the item.

7. major — `benchmark/bench/p426_verify.py:256-280` — Equal arbitrary row manifest hashes are marked C217-identical without resolving them to a verified HARVEST main manifest; this can wrongly suppress later panel judging. Fix: bind each identity hash to the corresponding verified published manifest.

8. minor — `benchmark/bench/p426_signals.py:348-349` — Cross-epoch headline pools OFF and ON, contrary to per-arm reporting, and unequal denominators can mask asymmetric instability. Fix: report totals separately by arm and attempt; remove the pooled headline.

9. minor — `benchmark/bench/p426_signals.py:411` — Floating representation makes an exact −5 pp delta trigger the strictly-below flag. Fix: compare with a small tolerance.

10. minor — `benchmark/bench/p426_signals.py:494` — `b8_sha256` hashes re-serialized JSON, not the supplied B8 file bytes. Fix: hash the original bytes in the CLI and pass that digest through.

11. minor — `benchmark/bench/p426_signals.py:436-451` — Coverage trusts only `sequence.json`, so a B8/`leg.json`-invalid leg can be listed as done. Fix: derive state from verified leg/B8 records and require consistency with sequence.

12. minor — `benchmark/bench/p426_signals.py:656-682` — JSON and Markdown are replaced separately; failure on the second write leaves a mixed-generation sheet. Fix: stage both outputs, then publish them together after both writes succeed.

The paired delta, permutation p, Holm, MDE, loss bound, geometric-mean CI, strict scoring, runaway tax, and C269 calculations are otherwise consistent with the contract. The committed-data strict s2 ON result is 42/43; the contract’s 43/43 golden conflicts with its own strict definition.
