I have enough context from the code review. Let me write up the findings.

---

## B2 design review round 2 — findings

Reviewed `docs/specs/p426-b2-tg1-wave2.md` v2 against the code (`chain_core.py`, `chain_ops.py`, `chain_hooks.py`, `chain_incident.py`, `run_config.py`, `schedules.py`, `tg1_runner.py`, `run_tg1_probe.py`, `run_tg1_chain.py`, `p426_leg.py`, `p426_harvest.py`, `p426_wave1.py`, `local_gate.py`, `arm_opencode.py`), the round-1 reviews and dispositions, and rulings C218–C234 / P481. v2 fixes the round-1 blockers (barrier inert, no DNF path, hook vocabulary, harvest, locks, watcher, arm-equality). Findings below.

---

### F1 — MAJOR — the evidence-policy manifest check is gated by `per_arm` and so is inert for the flat tg1 layout

**Location:** §3 "The chain verifies the manifest's `runtime.evidence_policy` equals `TG1_P426_EVIDENCE` before item one"; `chain_core.py:2294-2297`.

**Problem:** The only manifest-side `evidence_policy` comparison in `verify_manifest` is inside `if self.per_arm:`. `tg1-p426` is the flat (`per_arm=False`) layout — the spec says so ("the serialized `tg1` ChainConfig … byte-identical to golden values"). So the check the spec relies on never fires for P426 legs. The barrier-on switch (`item_barrier_on`, `chain_core.py:2097-2100`) reads the manifest's `runtime.evidence_policy.item_barrier`, so the barrier *will* turn on if the probe writes the right manifest — but nothing *verifies* the probe wrote `TG1_P426_EVIDENCE` and not, say, `TG1_EVIDENCE` (barrier off) or a hand-crafted policy. A probe that silently dropped `--evidence p426` would leave the barrier off, the `done` hook never fires, and the leg exits VALID with zero engagement evidence — exactly the round-1 B1 failure, reached by a different path.

**Scenario:** A probe regression (or a stale probe binary in one worktree's venv) omits `--evidence` from its argv; the manifest carries `item_barrier="off"`; the chain's barrier never arms; no reconciliation or engagement check runs; the leg is VALID; B8 has nothing.

**Change:** State that B2 adds an *unconditional* (not `per_arm`-gated) manifest check for `tg1-p426` that the runtime `evidence_policy` equals `TG1_P426_EVIDENCE`, and name the §13 red test ("probe's `--evidence p426` manifest and its rejection when absent" — already listed, but it must test the *chain-side* refusal, not just the probe's own validation).

---

### F2 — MAJOR — `transport_cause` returns `None` for tg1 today; the DNF stamp path is a probe-code change the spec doesn't name as one

**Location:** §5.4 "The probe stamps the client cause in P426 mode (`adapter.transport_cause`)"; `arm_opencode.py:690-692`.

**Problem:** `OpencodeArm.transport_cause` is `exc.cause if self.m64 and isinstance(exc, TransportFailure) else None`. tg1 is `m64=False`, so the probe stamps `None` today and `classify_incident_cause` returns `None` → `handle_incomplete` returns `"incomplete"` → `abort_restart` archives the load. The spec's `p426_continue` path depends on a stamped cause, but the only line that stamps it is gated on `self.m64`. B2 must widen that gate to P426 mode. That is a change to `arm_opencode.py`, which is in the probe's import closure → `probe_code_sha256` moves. The spec says `probe_code_sha256` "moves once (new epoch, already moved by P476)" and is "equal across arms (v8)" — but it never names *which* probe-code edits move it (`TG1_P426_EVIDENCE` in `tg1_runner.py`, `--evidence` in `run_tg1_probe.py`, **and** `transport_cause` in `arm_opencode.py`). A helper who misses the `transport_cause` edit builds a `p426_continue` policy whose probe never stamps a cause, so every transport incident falls through to `abort_restart` or systemic, and no DNF is ever written.

**Scenario:** Helper implements `p426_continue` in `chain_core` and the `--evidence` flag but leaves `transport_cause` gated on `m64`; item 7 drops the stream; the probe stamps `transport_abort.cause = None`; §5.4 says "a stamp outside the DNF causes, or none, with an incomplete invocation → systemic"; a single dropped stream stops the whole leg instead of DNFing the item.

**Change:** Name `arm_opencode.transport_cause` as a third probe-code edit that moves `probe_code_sha256`, and state the new gate (`m64 or p426`). Add a §13 red test: a `dropped_stream` in P426 mode stamps the cause and DNFs the item, not systemics.

---

### F3 — MAJOR — `p426_continue` has no host in the flat layout's `run_invocation` loop

**Location:** §5.2 "the chain relaunches the probe for the remaining items of the leg in order, on the same loaded instance"; `chain_core.py:1199-1211` (`run_invocation`), `chain_core.py:1920-1950` (`run_block_leg`, per-arm only).

**Problem:** The DNF-and-relaunch loop (`run_block_leg` → `settle_dnf` → re-derive `todo` → `run_invocation`) lives entirely behind the `per_arm`/`blocks` path (M64). The flat tg1 path runs one `run_invocation` per leg and returns; `handle_incomplete` is the only incident branch and it archives the load for `abort_restart`. The spec describes `p426_continue` behaviour ("writes the `p426_dnf` record, then relaunches the probe for the remaining items") but does not say where the relaunch loop lives for the flat layout. A helper could implement the `p426_dnf` *writer* but keep the flat `run_invocation` return-one-shot, so after the first DNF the chain proceeds to the next *leg* (the other language), skipping the remaining items of the DNFed leg — the realized ledger wouldn't match the plan, but `check_realized` compares *leg keys*, not per-item outcomes, so it could pass if the leg is recorded as "done."

**Scenario:** Item 7 of 22 Python DNFs; the chain writes the DNF record, returns from `run_invocation`, moves to the Go leg; items 8–22 of Python never run; the leg's realized ledger has 15 rows + 1 DNF instead of 22 rows + 1 DNF; `check_realized` (leg-key level) passes; the leg is VALID-with-DNF but 7 items are silently missing from the pair.

**Change:** State concretely that `p426_continue` adds a per-item relaunch loop to the flat layout (analogous to `run_block_leg` but for `tg1-p426`), and that the realized ledger gains per-item entries (slot → row | DNF) so `check_realized` refuses a leg whose item count ≠ plan. The §13 test "a DNF continues on the same worker with the remaining items in order" is listed but should explicitly assert the *remaining* items ran, not just that the DNF was recorded.

---

### F4 — MAJOR — make-up leg seed handling is ambiguous across sessions

**Location:** §5.5 "One fresh-load leg per arm (OFF then ON), over the ordered union of every DNF occurrence of both arms and both sessions; each item runs with its original session seed."

**Problem:** A "leg" in the tg1 schedule carries one `seed_base` (per session: s1=1001, s2=2002). The make-up leg's union can contain items that DNFed in s1 (seed 1001) and s2 (seed 2002) at the same time. One invocation has one `--seed-base`. The spec says "each item runs with its original session seed" but does not say the make-up leg splits into one invocation per original session (so seeds stay correct), or whether the make-up leg is itself a new "session" with its own seed (which would break the "original session seed" rule), or whether `--seed-base` becomes per-item. A helper could run the whole union under one seed (say 1001), making s2 DNF items run under the wrong seed — the pair key `(session, language, item, seed)` would then mismatch the original leg's seed, and B8 would either drop the pair or pair the make-up item against the wrong baseline.

**Scenario:** Two DNFs: item X in s1 (seed 1001), item Y in s2 (seed 2002). Helper runs the make-up leg with `--seed-base 1001` for both. Item Y's make-up attempt uses seed 1001, not 2002; its row's `seed_base` field is 1001; B8's pair key for Y is `(makeup, go, Y, 1001)` vs the original `(s2, go, Y, 2002)` — unpaired, or paired against a non-matching seed and silently counted.

**Change:** State that the make-up leg groups DNF items by original session and runs one invocation per (arm, original-session) group with that session's seed, and that the make-up leg's rows carry the *original* session in their pair key (or are explicitly excluded from pairs — which §5.5 already says, but the seed must still be right for the "repeat DNF is a finding" check). Add a §13 test: a make-up leg with DNFs from both sessions runs each group under the correct seed.

---

### F5 — MAJOR (data boundary) — the secret-gate refusal scan reads secrets "from the machine config / token files" but the harvest runs from the *frozen worktree*, not the live box

**Location:** §11.3 "the exact values of the box's configured secrets (read from the machine config / token files, compared in memory, never printed or logged)."

**Problem:** The harvest (`bench.p426_harvest wave2`) runs after the chain exits, from the leg root. The spec says it reads "the box's configured secrets" to scan staged bytes. But the secret material lives in the live machine config (`$STACK_WORKDIR` env, token files under `$HOME`), not in the frozen worktree. The harvest runs in the sequencer's process, which has the live env — so it *can* read them. But the spec does not say *which* files/env keys are the source of truth, how the harvest discovers them, or what happens when a secret value is empty/rotated between the leg and the harvest (a rotated key would not match the leg's transcript, giving a false clean). More concretely: the spec lists common credential *formats* (`hf_…`, `sk-…`, `ghp_…`, …) as a secondary scan, but the *primary* scan (exact configured values) has no named source. A helper would guess (env vars? a config file? `~/.cache/huggingface/token`?) and either miss the box's actual secrets or scan against the wrong values.

**Scenario:** The box's HF token lives in `~/.cache/huggingface/token`; the helper reads `$HF_TOKEN` (unset on this box) as the source of truth; the primary scan compares against nothing; a transcript that contains the real token passes the primary scan (no match), and the format scan (`hf_…`) catches it — *unless* the token is a non-`hf_`-prefixed value (a custom gateway key), in which case it ships to `main`.

**Change:** Name the exact secret sources the harvest reads (the machine config file(s) and/or the specific env keys), and state the rule when a source is absent (fail closed — treat as "no primary scan possible" → refuse the harvest, not "no secrets to match"). The §13 test "each secret pattern quarantines without printing the value" is listed but should also cover the *exact-value* scan, not just the format scan.

---

### F6 — MAJOR — `OVERRUN_PAUSED` holds "both locks" but the gate's `flock(RUNNING)` is held by `local_gate run`, not by the chain or sequencer

**Location:** §10.3 "keeps holding both locks"; §9 "the sequencer holds `SEQUENCER.lock` … a P426 chain takes `LEG.lock`."

**Problem:** §9 names three locks: `gate/RUNNING` (held by `local_gate run`), `SEQUENCER.lock` (held by the sequencer), `LEG.lock` (held by the chain). The sequencer and the chain hold `SEQUENCER.lock` and `LEG.lock` respectively. `gate/RUNNING` is held only by `local_gate run` — the chain *tries* it non-blocking at entry and refuses if held, but never *takes* it for the leg's lifetime. §10.3 says the sequencer "keeps holding both locks" during overrun. "Both" is ambiguous — does it mean `SEQUENCER.lock` + `LEG.lock` (the two the sequencer/chain hold), or does it include `gate/RUNNING`? If it means the two the sequencer holds, then `gate/RUNNING` is not held during overrun, and the operator can start `local_gate run` (which takes `RUNNING`) while the overrun chain is still alive — the gate's busy census (`local_gate.py:75-88`) does not include `run_tg1_chain` in `BUSY`, so the gate sees nothing busy and proceeds, tearing down the box mid-leg. The round-1 B5 finding was about exactly this; v2's §9 says "a P426 chain takes `LEG.lock` … and refuses when `gate/RUNNING` is held" but the *reverse* (gate refuses when leg is running) depends on the gate trying `LEG.lock` or `SEQUENCER.lock` non-blocking. §9 says the sequencer holds `SEQUENCER.lock` and the gate refuses when it's held — but `local_gate.run`'s `busy()` today does not try `SEQUENCER.lock` or `LEG.lock`; it only scans `BUSY` process names and `:8000`.

**Scenario:** Leg overruns; sequencer writes `OVERRUN_PAUSED` and holds `SEQUENCER.lock` + `LEG.lock`; operator, seeing no progress, starts `local_gate run` in a test window; the gate's `busy()` sees no `bench.p426_wave1`/`BUSY`/`:8000` (the chain is paused, the port may be free); the gate takes `RUNNING`, starts cloning/venv/pytest, modifying the worktree the overrun leg's evidence depends on; the chain eventually exits and its harvest reads a contaminated worktree.

**Change:** State that `local_gate.run`'s `busy()` (and the pre-push `check` path) gains a non-blocking `flock` try on `SEQUENCER.lock` and `LEG.lock`, and that "both locks" in §10.3 means `SEQUENCER.lock` + `LEG.lock` (the two the sequencer/chain hold), with `gate/RUNNING` held only by `local_gate run` itself. The §13 test "locks both directions" is listed — confirm it covers the gate→sequencer direction (gate refuses when `SEQUENCER.lock`/`LEG.lock` held), not only the chain→gate direction.

---

### F7 — MAJOR — the `invalidate` disposition and `p426_continue`'s "DNF + continue" share the after-barrier path but the spec doesn't say how the chain distinguishes them

**Location:** §5.2 "The hook vocabulary gains `invalidate(reason)` (after-barrier only) … A legacy tg1 hook returning a non-accept still aborts as today"; `chain_core.py:2143-2144` (`raise ChainAbort` for non-accept after-disposition when not `per_arm`).

**Problem:** The P426 hook runs at the `done` barrier. Two distinct outcomes are both after-barrier, both non-accept, and both must *not* raise `ChainAbort`: (a) a *systemic* failure (engagement missing, reconciliation mismatch) → `invalidate(reason)` → write `.stop`, wait for cleanup, record INVALID, exit rc 2; (b) an *item DNF* → write `p426_dnf`, relaunch remaining items, continue. The spec says `invalidate` is a new *disposition kind* the hook returns, and the DNF is a *transport policy* outcome the chain derives from the probe's abort. But both are after-barrier events in `pump_barrier`. Today `pump_barrier` calls `run_after` and branches on `disp.kind`. For `p426_continue`, the DNF is detected not by the hook's after-disposition but by the probe's transport abort (in `handle_incomplete`), which is a different code path. So the after-barrier hook (`run_after`) is where *engagement/reconciliation* failures become `invalidate`, while *transport* DNFs are detected in `handle_incomplete`. The spec describes both but doesn't state that the P426 hook's `after_attempt` is the *only* place `invalidate` is returned, and that a transport DNF never reaches `after_attempt` (the probe aborted, so the `.done` file may not exist, or the row may be partial). A helper could wire `invalidate` into `handle_incomplete` too, or try to return a DNF disposition from `after_attempt`, conflating the two.

**Scenario:** Item 7's stream drops; the probe aborts with a transport cause; `handle_incomplete` runs. The helper, reading §5.2, has the P426 hook's ``after_attempt` also return `invalidate` on "transport cause" (because the spec says `invalidate` is the after-barrier stop). The chain writes `.stop`, records INVALID, exits rc 2 — the leg stops on a transport incident that should have been a DNF.

**Change:** State explicitly: the P426 hook's `after_attempt` returns `invalidate` only for *engagement/reconciliation* systemic failures (the row is complete, the `.done` file exists, the hook ran its checks); transport DNFs are detected in `handle_incomplete` *before* the hook runs and never reach `after_attempt`. Add a §13 test: a transport DNF does not trigger `invalidate`, and an engagement failure does not trigger a DNF.

---

### F8 — MINOR — "s2 reversed" for one model is ambiguous: picks reversed or languages reversed

**Location:** §7 "s2 reversed"; `schedules.py:123-125` (`_tg1_legs_table`).

**Problem:** `_tg1_legs_table` for s2 is `[(p, l) for p in (p2, p1) for l in langs]` — picks reversed, languages in order. With one model (p1 == p2, the same entry), s2 = `[(entry, python), (entry, go)]` — identical to s1. The spec says "s2 Go first" and "the language order reversed in `schedules.tg1` under `p426=True` only." So B2 must reverse the *language* tuple for s2 in P426 mode. But the spec's §6.1 generic-schedule bullet says "s2 reversed" without saying *what* is reversed — a helper reading §6.1 alone (without §7) could reverse the picks (a no-op for one model) and not the languages, producing s2 == s1. The round-1 B9 finding called this out; v2's §7 is clearer ("the language order reversed in `schedules.tg1` under `p426=True` only") but §6.1 still says only "s2 reversed," and the two sections disagree on what "reversed" means.

**Scenario:** Helper implements §6.1's "s2 reversed" as picks-reversed (the existing `_tg1_legs_table` behaviour) and skips the `p426=True` language reversal in §7; with one model, s2's order is Python-then-Go, same as s1; the seeded-order decorrelation C223 chose is gone; the §13 test "both orders reach the probe's `--items`" passes against the wrong s2 order because the test checks the probe *received* an order, not that s2's order is Go-first.

**Change:** Make §6.1 say "s2 in reversed *language* order (picks unchanged for one entry; see §7)" and add a §13 test that asserts s2's first language is Go, not just that an order reached the probe.

---

### F9 — MINOR — the `--predictor` assertion vs. selector ambiguity is resolved in §6.2 but not in §2's refusal list

**Location:** §2 "refuses … `--pred-s`, `--generation-sha`, `C147_OVERLAY`, `--frozen-date-from`"; §6.2 "`--predictor off|mtp` keeps selecting the out-root family, the tripwire branch and the ON / OFF out-root isolation, and is additionally an assertion."

**Problem:** §2's refusal list says `--p426` refuses `C147_OVERLAY`. But `run_tg1_chain.main` reads `C147_OVERLAY` from the env to build the OFF overlay path (`run_tg1_chain.py:239`). Refusing `C147_OVERLAY` means the OFF arm must discover its overlay another way. §6.2 says the chain "serves `<worktree>/main_models.yaml` verbatim (`MLX_SERVE_CONFIG`), no overlay generation." So in P426 mode, the served config is the worktree's `main_models.yaml`, not an overlay. But `ChainOps` is constructed with an `overlay` path (`make_ops`, `run_tg1_chain.py:228-231`). The spec doesn't say what `overlay` path is passed to `ChainOps` in P426 mode — the worktree's `main_models.yaml`? A new `MLX_SERVE_CONFIG` path? The `ChainOps.overlay` field is read by `worker_metrics` (to find the port) and `overlay_sha` (registry hash). If the helper passes the worktree's `main_models.yaml` as the overlay, `overlay_sha` becomes the registry hash — which is what §3's "registry sha" checkpoint checks. But §6.2 says "no overlay generation" — does that mean the `C147_OVERLAY` *env var* is refused, or that the *overlay generation code* (`ensure_overlay`) is skipped? A helper could read §2's "refuses `C147_OVERLAY`" as "the env var must be unset" and then have no path to pass to `ChainOps`, crashing at construction.

**Scenario:** Helper refuses `C147_OVERLAY` env; in `make_ops`, `overlay` is `None`; `ChainOps.__init__` reads `self.overlay` for the port and the registry hash; `worker_metrics` crashes on `None`; the leg fails at the first `worker_metrics` call with an opaque error.

**Change:** State that in P426 mode `overlay` passed to `ChainOps` is the worktree's `main_models.yaml` (the served config), that `ensure_overlay` is skipped (no generation), and that `C147_OVERLAY` is refused only as a *user override* (the env var), not as the `ChainOps.overlay` field. One sentence in §6.2 would close this.

---

### F10 — MINOR — `request_usage` as the "client-side source" is named but its row field path is not

**Location:** §4.1 "the row's `request_usage` (`token_turn_gate` records `(j, output_tokens, prompt_tokens, budget)` per completed request … the client-side source)"; `p426_leg.py:328-357` (`request_match_problems` reads `row.prompt_tokens` / `row.draft`, not `request_usage`).

**Problem:** The existing Wave-1 reconciliation (`p426_leg.request_match_problems`) matches the server log to `row.prompt_tokens` and `row.draft`, not to a field called `request_usage`. The spec names `request_usage` as the client-side source and says `token_turn_gate` records it. But the spec doesn't say whether `request_usage` is a *new* row field (written by the probe in P426 mode) or an *alias* for the existing `prompt_tokens`/`draft` fields. If it's new, the probe must write it — another probe-code change. If it's an alias, the "two independent sources" claim is weaker (both the row and the log derive from the same opencode stream). The round-1 B12 finding (glm) asked this; v2's §4.1 names `request_usage` and `token_turn_gate` but doesn't say whether the row already carries it or B2 adds it. A helper could reuse `request_match_problems` (matching `row.prompt_tokens`) and never read `request_usage`, collapsing the two sources to one.

**Scenario:** Helper reuses `request_match_problems`; the row's `prompt_tokens` and the server log's `prompt_tokens` both come from opencode's stream; a server-log line is dropped by a logging bug; the row's `prompt_tokens` (client-side) is unaffected and matches the log's other lines; the missing line is not caught because the row's value is the only client-side source and it's compared against a log that's missing a line — the count mismatch (`len(request_usage) != completed lines`) is the catch, but only if `request_usage` is a *separate* list with its own count. If it's just `row.prompt_tokens` (one number), the count check is `1 != 0` which is caught, but the per-request token equality is not (one number vs many). The spec's §4.3 says "their count, per-request `prompt_tokens` and `generated_tokens` … equal `request_usage` in order" — this requires `request_usage` to be a *list*, not a scalar. The existing row has no such list.

**Change:** State whether `request_usage` is a new row field the probe writes in P426 mode (and name the probe-code edit), or whether B2 derives it from `token_turn_gate`'s records (and where those records are stored on the row). The §13 test "every §4.3 equality red (count, tokens, session, backend, failed line, worker delta, A4 window)" is listed but should name the `request_usage` field explicitly so a helper can't pass it with a scalar.

---

### F11 — SCOPE REQUEST — the pilot's own timeout is unspecified

**Location:** §10.2 "Leg deadline, one value for both arms of a session: `T = 1.5 × Σ_lang n_lang × max(w_lang) + 1800 s`, with `w_lang` = the largest per-item wall over both pilots (Python) and, for Go (not piloted), the largest per-item wall of this entry's Go items in the P456 rehearsal and M63 rows."

**Problem:** The formula derives the s1/s2 leg deadline from the pilots' measured walls. But the pilots (legs 1–2) themselves need a timeout to run. The spec says "the leg timeouts derived (§10.2)" is a pilot-gate output, but doesn't say what timeout the pilots run under. A pilot that hangs forever would never reach the gate. The existing `p426_leg` uses `6 * 3600` (6 h) as a default; the existing `run_tg1_chain` has no leg-level timeout (it relies on per-item probe timeouts). The spec's §10.3 overrun mechanism needs a `T` to fire. If the pilots have no `T`, an overrun pilot hangs until the operator notices.

**Change (scope):** state a bootstrap timeout for the pilot legs (e.g. the existing 6 h default, or a derived value from historical walls), recorded in v8's amendment, so the overrun supervisor has a `T` before the s1/s2 deadlines are derived. Not a defect against the goal (the pilots are not paired), but the harness can't start without it.

---

### F12 — MINOR — `probe_code_sha256` "moves once" but the spec doesn't list it as a chain-lifecycle file, so lifecycle drift won't catch a probe-binary divergence between arms

**Location:** §3 "frozen record v8 self-hash + live re-verification"; §6.4 "the resolved `mlx_vlm` / `mlx_serve` import paths (under `<WT>/src/`)"; §6.5 "v8 asserts both [commits]."

**Problem:** §6.4's arm-equality receipt records the resolved `mlx_vlm`/`mlx_serve` import paths and `git status --porcelain` empty for each submodule. But it doesn't record the *probe's* resolved entry-point sha or the probe's import-closure sha per arm. `probe_code_sha256` is asserted *equal across arms* (v8), but the per-leg checkpoint (§3 "Entry") checks `--probe-code-sha <v8>` as an argv assertion, not a live re-derivation from the worktree. If the ON worktree's venv resolves a different `run_tg1_probe.py` (e.g. a stale `.pyc` or a path shadow), the argv assertion passes (the flag is the same) but the running probe differs. The arm-equality receipt (§6.4) records the `mlx_vlm`/`mlx_serve` import paths but not the probe's. The spec says "the chain owns … the probe" but the probe's live identity per arm is not in the receipt.

**Scenario:** ON worktree has a stale `__pycache__` for `run_tg1_probe` from a pre-B2 commit; the probe runs the stale code; `--probe-code-sha` matches v8 (argv flag); the arm-equality receipt records equal `mlx_vlm`/`mlx_serve` paths but not the probe's; the ON probe doesn't pass `--evidence p426` (stale code); the barrier never arms; the leg is VALID with no engagement — the round-1 B1 failure again, via a stale cache.

**Change:** Add the probe entry-point's resolved path and the live `probe_code_sha256` (re-derived from the worktree, not just the argv flag) to the arm-equality receipt (§6.4), and to the entry checkpoint's re-verification (§3). The §13 test "arm-equality receipt mismatch" is listed — confirm it covers a probe-path mismatch.

---

### Summary

The two round-1 blockers (barrier inert, no DNF path) are addressed in v2's design (P426 evidence policy, `p426_continue`, `invalidate`), but the *implementation hooks* have gaps that would let a helper build something that passes the listed tests while the goal silently fails: the evidence-policy manifest check is gated by `per_arm` and won't fire for the flat layout (F1); the `transport_cause` edit that the DNF path depends on is not named as a probe-code change (F2); the `p426_continue` relaunch loop has no host in the flat layout and the realized ledger doesn't track per-item outcomes (F3); the make-up leg's cross-session seed handling is ambiguous (F4). F5 (secret-gate source of truth) and F6 (overrun lock ownership) are data-boundary / exclusion defects. F7 is the `invalidate`-vs-DNF path confusion. F8–F10 are clarity gaps that round 1 already flagged and that v2 partially but not fully closed. F11 is a scope request for the pilot bootstrap timeout. F12 closes a residual arm-divergence hole the arm-equality receipt doesn't cover.

The four-eyes STRICT scope (§13) names "harvest / scrub / secret gate, chain-core policy and disposition, locks" — F1, F2, F3, F5, F6, F7 all fall in those hunks, so they are in scope for the strict review.