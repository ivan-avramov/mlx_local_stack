I have completed my read-through. Here are my findings.

---

**F1 — §4.3 / `m62/inject_verify.causal` (lines 175–199)**
Severity: major (hypothesis, traced)
Problem: The spec says for the no-in-flight case "the stop, the verified client kill and a reconciled row suffice, recorded `order: "no_request_in_flight"`". The existing `causal` for `loop` has a *descendant* check that is downstream of the `trailing` check it is relaxing:

```175:188:benchmark/m62/inject_verify.py
    if (row.get("reconciliation") or {}).get("trailing") not in ("interrupted", "unpublished", "interrupted_charged"):
        return "not_observed:trailing"      # the kill landed after the in-flight message was settled
    if kind == "loop" and not any(k.get("role") == "model" and k.get("argv", [])[-2:] == ["sleep", "600"]
                                  for k in killed):
        return "not_observed:descendant"
```

If the implementer inserts the `no_request_in_flight` short-circuit before the `trailing` check (the natural reading of "suffice"), the `loop` descendant check is skipped. That descendant kill is part of what proves the stop path actually killed something model-role, which is the proof assumption (4) asks the rule to preserve. The spec text does not say the descendant check is retained for `loop`.
Scenario: a `loop` positive where the model-role `sleep 600` child has already exited on its own before the stop fires (nothing in flight, no descendant killed). Under the literal spec text this PASSes with `order: "no_request_in_flight"`, but the kill path never exercised a model-role process — the very defect S27-P6 was about (the kill landed too late to interrupt anything) is what produces the pass.
Proposed change: state explicitly that the `no_request_in_flight` branch relaxes only the `trailing`/`cancellation_consistent` checks; the `kill`/`killed_verified` checks and, for `loop`, the model-role descendant kill remain required, else the row is `not_observed:descendant`.

---

**F2 — §5.1 / `p426_reconcile` reconciliation failure as a harness fault**
Severity: major (hypothesis, traced)
Problem: §5.1 lists "a reconciliation failure on an owned-cleanup-certain item that is not an integrity fault" as a HARNESS FAULT, and the outcome exclusion list is "(a failed test, a budget hit, a loop, a tamper)". A reconciliation failure that survives §4.1's `kill_boundary_late_record` acceptance is, by construction, the *non-benign* kind — the three accounting systems (worker `Request` log, client `request_usage`, gate counts) disagree with no benign order. The spec reruns it once. But a disagreement can be produced by a model behaviour that confuses the client's accounting (e.g. a tool-call shape that makes opencode emit a `step_finish` the worker never served, or vice-versa). That is outcome-correlated, not in the exclusion list, and the rerun gives the offending model a free second attempt the other arm may not get.
Scenario: arm A's model emits a part-less error / retry shape that makes the client record a phantom `step_finish`; reconciliation fails with `boundary_count`; §5.1 reruns the item; the same model behaviour may or may not recur. Arm B's model never trips this. Arm A gets a second scored attempt on items where it produced unreconcilable accounting; arm B does not. The comparison is biased on exactly the items where arm A misbehaved.
Proposed change: narrow §5.1 so a reconciliation failure is a harness fault only when the mismatch is *not* attributable to model/client behaviour the row itself records — e.g. exclude when `reconciliation.trailing` is `interrupted_charged`/`unpublished` or the abort manifest carries a client-side error the model provoked. Equivalently: a reconciliation failure that the row's own client evidence explains is an outcome, not a harness fault.

---

**F3 — §5.2 "the sequencer pauses the leg for the designer" / `p426_wave2.classify_leg` (line 684) and `p426_harvest.harvest_wave2`**
Severity: major (hypothesis, traced)
Problem: §5.2 says the 4th harness-fault DNF "pauses the leg for the designer (P17), never invalidates it". `classify_leg` returns only `INVALID / VALID_WITH_DNF / VALID / NOT_STARTED / OVERRUN` and `harvest_wave2` enforces `state in LEG_STATES` (`p426_harvest.py:220, 935`). There is no `PAUSED` state, no rule for a paused leg's barrier files, and §8.3's tier table does not list it. A paused leg has no defined harvest path; the operator is handed a leg root the harvest will refuse (`state None is not one of …`), and `chain_rows` has no disposition rule for a `harness_fault`-only slot table either (see F4). The spec introduces the outcome but leaves the leg-state and consumer contracts unspecified.
Scenario: a leg hits a 4th harness-fault DNF; the chain writes "paused" somewhere; the operator runs the harvest; `harvest_wave2` raises `leg.json: state 'PAUSED' is not one of VALID, VALID_WITH_DNF, INVALID, NOT_STARTED, OVERRUN` and refuses; the leg is stranded.
Proposed change: add `PAUSED` to `LEG_STATES`, `classify_leg`, the harvest rule table, and §8.3's tiers (PAUSED is not a quality verdict; the operator resumes or archives), and pre-register what `chain_rows` accepts for a paused leg's slots.

---

**F4 — §5.2 / `chain_rows.SLOT_DISPOSITIONS` (line 58) and `slot_table` (lines 395–409)**
Severity: major (confirmed, traced)
Problem: §5.2 adds `harness_fault` to `chain_hooks.KINDS`/`AFTER_KINDS` and says "the slot attempt is persisted … records keyed by rerun index". But `chain_rows.SLOT_DISPOSITIONS = ("accepted", "cheat", "unclear", "exhausted")` does not include `harness_fault`, so `_validate_progress` (line 208) fails any slot attempt with that disposition, and `slot_table` (line 395) has no branch for it — a `harness_fault` last disposition falls into `else: table.blocked.append(slot)`, i.e. the slot is *blocked for the operator*, not rerun. The spec's "reruns once, immediately" is not implementable on the existing machinery without also touching `chain_rows`, which the spec does not name in its code map.
Scenario: a harness fault fires; the hook returns `Disposition("harness_fault", …)`; `run_after` persists a `slot_attempts` entry with `disposition: "harness_fault"`; on the next `_validate_progress` the chain aborts with `disposition harness_fault not in SLOT_DISPOSITIONS`; even if that gate were widened, `slot_table` blocks the slot instead of queueing `pending_reruns`.
Proposed change: the spec must list `chain_rows.SLOT_DISPOSITIONS` and `slot_table` as changed sites: add `harness_fault`, give it a branch that appends `(slot, rerun_index + 1)` to `pending_reruns` (capped by the per-item "rerun once" rule), and define the consumer rule (§5.4) in `chain_rows` terms — "one accepted attempt per slot, earlier attempts each `harness_fault`".

---

**F5 — §4.2 step-offset proof / `token_turn_gate.EventStream` and `arm_runner.terminate_client`**
Severity: minor (hypothesis, traced)
Problem: §4.2 requires "the (n)th `step_finish` offset ≥ `signal_offset`". `EventStream` tracks `self.current_offset` per event but does not persist per-step offsets anywhere the row carries them, and `stream.signal_offset` (set at `arm_runner.py:528`) is never persisted into `termination`/the row. The spec assumes both are added. The soundness concern: the events file is the client's stdio; `signal_offset = paths["events"].stat().st_size` is the kernel-visible size at SIGTERM. If the client uses buffered stdio and has a `step_finish` logically recorded before the signal but not yet flushed, its byte offset (once flushed and ingested) will be ≥ `signal_offset` even though it pre-dated the signal — a false `no_request_in_flight`/late-record pass on a genuine mismatch. The other conditions (positional pairing, worker count at kill) defend against this, but the spec presents the step-offset as the proof, not defense-in-depth.
Scenario: client buffers a `step_finish` for request N+1; SIGTERM lands; the buffer flushes during teardown; the ingester sees the `step_finish` at an offset ≥ `signal_offset`; the late-record rule accepts a row where the gate's `at_kill` was actually N+1 (the step was pre-signal) but mis-recorded as N.
Proposed change: require the client's events stream to be line-flushed (or read the gate's own `request_usage` count, not the file size, as the signal marker), and state that the step-offset proof is secondary to the worker-count-at-kill and positional-pairing checks.

---

**F6 — §3.1 environment-based attribution / `proc_guard._attributed_path` (line 482)**
Severity: minor (hypothesis, traced)
Problem: §3.1 adds "its readable environment carries the run's `HOME` / `XDG_*` values" as an ownership test. `_attributed_path` only reads `p.cwd()` and `_cmdline(p)`; environment attribution needs `p.environ()`, which on macOS is per-process `proc_pidinfo` and is denied for SIP-protected and some same-uid system processes. The spec says "readable environment", so a denied read is simply not attributed — fine — but the cleanup scan runs `_attributed_path` over every same-uid live process each tick and at cleanup; adding `p.environ()` there is a measurable cost on a "normal macOS box" with hundreds of same-uid processes, and a denied `environ()` raises `AccessDenied` which the G1 table routes to an unreadable obligation. The spec does not say env-denied is an obligation or a skip for this path; the implementer could accidentally turn a foreign daemon with a denied environ into `uncertain`.
Scenario: Spotlight's `mdworker_shared` (same uid, denied environ, cwd not under a guard root, foreign session) is scanned at cleanup; `p.environ()` raises `AccessDenied`; if the implementer routes that into `_note_unreadable`, cleanup becomes `uncertain` — the exact D2 false positive the bundle is meant to remove.
Proposed change: specify that an `environ()` denial for a process not otherwise attributed (no tracked ancestry, no path attribution, foreign session) is a skip, not an obligation; only a process already attributed by another criterion whose env read fails becomes an obligation.

---

**F7 — §8.2 HOLD vs the outer `Sequencer.supervise` deadline / `p426_wave2.Sequencer.supervise` (line 1108)**
Severity: minor (hypothesis, traced)
Problem: §8.2 says "the leg's deadline clock is suspended while held". The deadline that writes `OVERRUN_PAUSED` lives in the *outer* `Sequencer.supervise` (`p426_wave2.py:1108–1120`), a separate process from the chain. The chain writes the `.stop` with disposition `hold` and waits on the `HOLD` file; the outer supervisor only polls `ops.alive(handle.pid)` and the watcher. The spec does not define how the outer supervisor learns the chain is holding (the chain process is still alive, so `ops.alive` stays true) and suspends `deadline`. §8.3 lists "a hold" under SPEED-INVALID, so the leg is speed-invalid either way, but if the outer supervisor does not suspend, a long hold also writes `OVERRUN_PAUSED`, doubling the classification and producing an `OVERRUN_PAUSED` file the operator must reconcile with the hold episode.
Scenario: operator pauses at a `done` to kill a side process; the hold lasts longer than the remaining deadline; the outer supervisor writes `OVERRUN_PAUSED` while the chain is legitimately holding; the leg record carries both a hold episode and an overrun.
Proposed change: name `Sequencer.supervise` as a changed site — it must read the hold episode record the chain writes and subtract the held interval from `self.clock() - t0` before the `>= deadline` test, or suspend polling while a hold episode is open.

---

**Scope request S1 — §3.5 residual and §3.3 `foreign_new`**
The §3.5 residual (a `setsid`'d agent process that leaves every guard root and clears its environment) is foreign by §3.1 and, being younger than the guard, goes to `foreign_new` (record only). But §3.3 says `foreign_new` is "RECORD ONLY: never killed". A process the agent spawned (so it was ours at spawn time) that then `setsid`s and escapes is, by the spec's own §3.2, no longer OURS — yet it holds resources (open file descriptors into the work tree, possibly a running build) that the next item's clean-tree check will fail on. The spec records it but does not kill it. Request: confirm the operator accepts that a `setsid`'d escaped agent child is never killed by the harness, even when it holds open handles into the work tree, and that the leg proceeds (the contaminated-tree / protected-path checks catch the consequence, not the cause). No severity — this is a deliberate ruling I want confirmed, not a defect.

---

**Summary.** F1 and F2 are the measurement-bias / proof-weakening risks the request asks for; F3 and F4 are gaps in the consumer/state contract that make §5.2's "rerun once" and "pause" outcomes unimplementable as written; F5–F7 are underspecified seams the implementer must close for the design to be sound on a normal box. Nothing else of substance.
