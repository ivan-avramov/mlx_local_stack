Findings below. I read the specification and the fork's `/metrics` and `Request completed` code (`generation.py:628-741`). I did not trace `chain_core.py`, `chain_hooks.py` or the probe, so the other findings are hypotheses.

**F1 — §6.4/§6.5: the credential comparison cannot work as written**
- Severity: major. Evidence: hypothesis, from the text.
- Problem: credential values are never recorded or hashed, only compared "in memory across the pair". The chain, a separate process per leg, performs the pair comparison at its after-load checkpoint, using the first leg's receipt path from the sequencer. Credential values are not in that receipt, so the chain has nothing to compare. §6.5 also says equality lives only in memory and a sequencer restart voids the pair, which implies the sequencer holds the values. The spec never says how the chain gets them.
- Scenario: an implementer who follows §6.4 literally records `same`/`different` only after a comparison no process can perform. Either the check is skipped silently, or credentials get passed through an environment variable or file, which breaks the never-persisted rule. The pair gate then has no credential check, or a leaky one.
- Change: say who compares. For example, the sequencer holds the first leg's credential values and passes them to the second chain over an inherited pipe fd, or it performs the credential comparison itself after load and the chain only gates on the sequencer's verdict. Add a test for the chosen route.

**F2 — §4.3 failed-line table: a strict-fail kill with a request in flight has no row for "server completed it anyway"**
- Severity: major. Evidence: hypothesis.
- Problem: DNF has a `completed_unaccounted` row for a request the server finished before the client lost it. Kill and `client_inactivity` strict fails, "with a request in flight", allow only one trailing `stream_closed_before_completion` failed line. The probe kills opencode while a request is in flight. The server can finish that request before it notices the disconnect, for example when the kill lands during the last tokens or a short decode. The window then has one extra `C` line and no `F` line.
- Scenario: a scored kill lands just before the last token. The server logs `Request completed`, so `|C| = |request_usage| + 1`. The table has no row for this, so it is "not attributable" and systemic, and the whole leg is `INVALID` and the sequencer stops over a legitimate scored item.
- Change: add the symmetric `completed_unaccounted` row for kills and `client_inactivity` (|F| = 0, one trailing `C` line not in `request_usage`, same session). Add a test for it.

**F3 — §4.4: one engagement miss invalidates the whole leg**
- Severity: major. Evidence: hypothesis.
- Problem: the rule is "every ON request with `generated_tokens ≥ 2` must show `draft_rounds ≥ 1`", and any violation is systemic. This contradicts the goal's "isolated incident is recorded and the run continues". The rule rests on a code-read of when `speculative_stats_since` returns null. Cases the spec does not rule out include a stop or EOS landing on the first drafted round, a cache-session trim or resume path that skips the drafter, and a request that ends in a stop-sequence hold-back. Nothing shows the "≥ 2 tokens means a round ran" claim holds on every path. The pilot is called "the known positive", but the pilot gate itself requires engagement on every request, so it cannot calibrate the rule.
- Scenario: one 2-token request (for example a tool-call stub) lacks the counters at hour 6 of leg 4. The ON s1 leg becomes `INVALID`, and the sequencer stops with all of s1 ON discarded.
- Change: have the rehearsal and pilot measure the distribution of requests with `generated_tokens ≥ 2` and no counters. Make a per-request miss an item-level recorded flag. Make it systemic only on a systematic pattern, for example an item or leg with zero engagement, or a miss rate above a threshold fixed in v8. Keep OFF's "no `draft_*`" strict.

**F4 — §4.2/§5.1: a transport abort before the slot's `ready` record**
- Severity: minor. Evidence: hypothesis.
- Problem: "Missing [ready record] at `done` or at a DNF → systemic." The spec does not define which slot a probe abort belongs to when it happens between a `done` answer and the next `ready`. Examples are an opencode startup connect failure or a timeout in pre-item discovery. It also does not say whether such a case is a DNF or systemic. Those causes (`connection`, `timeout`) are classed DNF in §5.1.
- Scenario: a connection failure while opencode starts for slot k, before `ready` is written. By §4.2 it is systemic. By §5.1 it matches DNF causes. Two implementers will build different behaviour.
- Change: state it explicitly. Either a pre-`ready` abort is always systemic (and drop those causes from the DNF row for that phase), or the ready record is written before the probe launches opencode for the slot.

**F5 — §6.4: pair-gate env equality includes values that legitimately differ per leg**
- Severity: minor. Evidence: hypothesis.
- Problem: only `<WT>` and `<OUT>` are canonicalized, plus a fixed volatile-key list. The probe's environment carries per-leg or per-item values such as the leg name outside the out-root path, the receipt file path, the seed overlay (`OPENCODE_CONFIG_CONTENT`) and PIDs. The arm commit appears in the environment of ON/OFF legs. §6.5 allows only the three argv items, the drafter snapshot, the arm commit and the canonical roots. Any other difference is systemic.
- Scenario: the first pair (pilots) halts on an environment key nobody listed. This is recoverable only through a spec change, not an operator call.
- Change: require R1 to produce the full env diff for the pair. Freeze the volatile and allowed-difference lists from that diff in v8, and add a rule for who may extend them.

**F6 — Dangling cross-references**
- Severity: minor. Evidence: confirmed by reading the text.
- §1's table says "§6.6's common flags", but the common flags are §6.7. §6.6 is the arms and diffs.
- §6.6 and §14 refer to "the §11 restore". §11 is the harvest, and no section defines the restore (the registry change that turns ON on). The three registry lines are never specified.
- An implementer cannot tell exactly what the ON commit adds. Define the restore in §6.6 and fix the references.

**F7 — §8: decode-rate estimator (checked, no defect)**
- `/metrics` `avg_decode_tok_s` is `generated_tokens_total / _decode_time_total_s`, where both totals accumulate only in `record_success`. So `D = generated_tokens_total / avg_decode_tok_s` exactly equals Σ `decode_elapsed_s` over completed requests, and the spec's claim holds.
- Caveat: when `_decode_time_total_s == 0` the field is 0.0, which the spec already handles.
- One implementation hazard: per-item `ΔD` takes the difference of two quotients, so floating-point error grows when an item has very few tokens. Compute `D` from the unrounded snapshot values.

**Scope request (no severity):** record the pilot's observed distribution of items with ≤ 1-token requests and of in-flight kills in the item records. The F2 and F3 rules then rest on measured, not assumed, frequencies.
