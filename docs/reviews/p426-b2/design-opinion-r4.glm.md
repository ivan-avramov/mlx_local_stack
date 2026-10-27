Now let me examine the key code files referenced in the spec to verify claims.Let me verify some specific claims in the fork.I have enough to write up the findings. Let me verify two more specific claims, then deliver# Cold design review — `docs/specs/p426-b2-tg1-wave2.md` v3.1

I read the spec, the P426 plan, the cited rulings in `docs/open-questions.md`, the round-3 reviews and dispositions, and verified the load-bearing code claims (`chain_core.py`, `chain_hooks.py`, `chain_ops.py`, `tg1_runner.py`, `arm_opencode.py`, `arm_runner.py`, `run_tg1_probe.py`, `p426_harvest.py`, and the fork `server/generation.py`, `speculative/common.py`, `mtp.py`). The fork claims in §4.1/§4.4 (draft counters on the `Request completed` line via `_build_metrics_envelope`/`_format_verify_counters`; `emitted = 1`; `speculative_stats_since` returns null when no round ran) are all confirmed. Findings below.

---

### F1 — §4.2 settle bound — MAJOR — Go items can blow a Python-pilot-derived settle bound (false systemic)

**Problem.** The timeout amendment raises the settle bound to `max(900 s, 2 × the largest single-request elapsed over both pilots)` (round-3 C-F7, adopted). But legs 1–2 (the pilots) run only the first 5 of s1's **Python** order (§1, §7). Go items are never piloted (§15 residual acknowledges this for the *deadline*). The settle bound therefore has no Go prefill input. A Go item can have a longer single-request prefill than any Python pilot request; the spec's own rationale for raising the bound ("a disconnect during a long prefill is noticed only when prefill ends") applies equally to Go.

**Failure scenario.** A Go item in leg 3/5 has a 256K-token prompt whose prefill takes ~1100 s. The client disconnects mid-prefill; the server does not emit a terminal `Request completed` until prefill ends. The settle bound is `2 × max_python_pilot_request ≈ 2 × 700 s = 1400 s` — or, if the largest pilot request was small, just the 900 s floor. The Go prefill+drain exceeds the bound; settle times out; the leg is marked systemic (§5.1 "settle timeout") and stops, INVALID, when the worker was healthy and the item would have been a legitimate DNF-and-continue.

**Change.** Derive the settle bound from the largest single-request elapsed over the pilots **and** the historical Go rehearsal/M63 walls (the same source §10.2 uses for `w_go`), or state that the 900 s floor is sized to cover the largest expected Go prefill with evidence. Add a §13 test that a Go prefill longer than the Python-pilot max does not trigger a false settle timeout.

---

### F2 — §11.2 symlinks — MAJOR (data boundary) — model output can fail the harvest

**Problem.** "Every file is examined with `lstat`; a symlink or non-regular file (anywhere, incl. final trees) is never followed or copied — it is recorded (path, link target string) and the harvest fails for the operator." Round-3 S11 adopted this to stop editable-install symlinks escaping the root. But the rule is applied to the **final trees** — the solution repos the model produces. opencode has shell access; a coding-task solution can legitimately contain a symlink (a `bin/` script, a `src` symlink, a `.git`-style pointer, a node_modules link). The spec fails the whole leg's harvest for any such symlink.

**Failure scenario.** Item 17's solution repo contains `package/bin -> ../src/main.py`. The harvest's `lstat` sweep finds it, records it, and fails the harvest "for the operator." The leg's evidence is not staged; every citable byte of that leg is held until the operator manually overrides. With 43 items × 2 arms × 2 sessions, the probability that no item ever produces a symlink is low; the rule can block multiple harvests for reasons unrelated to the harness or the data boundary.

**Change.** Distinguish a symlink that **resolves inside the leg root** (record the target, exclude it from the copy with reason `symlink`, continue) from one that **escapes the root or is dangling** (fail). Only fail when a symlink is referenced by a required artifact and cannot be excluded. Keep the fail-closed behavior for the editable-install case (which is what S11 was about) by applying the strict rule to the leg root's own files, not to the model's final tree.

---

### F3 — §5.1 / §5.5 — MAJOR — the "> 2 DNF → systemic" leg's DNFs are not excluded from make-up, and the make-up leg itself can exceed 2 DNFs

**Problem.** §5.1 makes a leg systemic at the 3rd DNF. §5.5's make-up input is "the ordered union of every DNF occurrence of both arms and both sessions" with no qualifier that the leg was VALID. So the 3 DNFs that triggered the systemic stop are still in the make-up union. The make-up leg then reruns them. But the make-up leg is itself subject to §5.1: if a make-up leg hits 3 DNFs (plausible — it is rerunning items that already DNF'd once), it too goes systemic and stops mid-make-up, leaving the make-up incomplete with no defined disposition for the un-run occurrences.

**Failure scenario.** Leg 4 (on-s1) DNFs 3 items → systemic, INVALID. Those 3 occurrences enter the make-up union. In the ON make-up leg, 2 of them DNF again (transport is genuinely flaky) and a 3rd new item DNFs → the make-up leg is systemic at the 3rd DNF and stops. The remaining occurrences in the union never run. §5.5 says "a repeat DNF is a finding" but does not say what to do when the make-up leg itself is stopped by the > 2 DNF rule: there is no make-up-of-the-make-up, and the sensitivity line is incomplete with no recorded reason for the missing items.

**Change.** Either (a) exclude a systemic leg's DNFs from the make-up union (only a VALID-with-DNF leg's DNFs are made up — the systemic leg is reported as-is, DNFs counted as non-successes, no sensitivity rerun), or (b) state that the > 2 DNF rule does not apply to make-up legs (a make-up leg runs to completion regardless of DNF count, since its purpose is to produce the sensitivity line), or (c) define a disposition for a make-up leg that stops early. Pick one and add a §13 test.

---

### F4 — §6.5 / §11.4 — MAJOR — a sequencer restart between paired legs leaves an orphaned, already-harvested first leg with no pair dossier

**Problem.** Round-3 S15 (adopted): "a sequencer restart between the two legs of a pair voids the pair — both legs run again on fresh roots." §11.3 harvests "right after each leg ends"; §11.4 lets the operator approve a push of `main`/`evidence` per leg. The spec does not quarantine or mark an already-harvested first leg whose pair was voided. B6/B8 resolve pairs through the pair dossier (§12); a voided first leg has no dossier, but its `HARVEST.json` and rows are already on `main` if the operator pushed it.

**Failure scenario.** Leg 3 (off-s1) completes and is harvested; the operator approves a push of its `main` artifacts (the spec does not forbid pushing a single leg). The sequencer crashes before leg 4. On restart, the pair is voided; legs 3 and 4 both rerun on fresh roots. The original leg-3 harvest is now an unpaired orphan on `main`. B6/B8, consuming `HARVEST.json` per leg, may treat the orphan as a valid unpaired leg or, worse, pair it with the rerun leg 4 (same leg id, same arm) and emit a bogus "identical outputs" panel-skip. The signals sheet carries a phantom session.

**Change.** State that a voided first leg's harvest is quarantined (moved to a `voided/` namespace or marked `pair_voided` in its `HARVEST.json`) before the rerun, and that B6/B8 ignore `pair_voided` legs; and forbid a single-leg push before the pair dossier exists (the push approval is per-pair, not per-leg). Add a §13 test that a voided leg's harvest is not consumed by B6/B8.

---

### F5 — §4.3 / §4.1 — MINOR — the `request_usage` ↔ log-line pairing key is not specified

**Problem.** §4.3 requires "`C` equals `request_usage` in count and order on the pinned field pairing" and the `completed_unaccounted` DNF row needs "exactly one trailing `C` line absent from `request_usage`." §4.1 names the field pairing only as "the one the P456 rehearsal matched 17 / 17; a test pins it on a committed rehearsal row + log-slice fixture." The `Request completed` log line carries `session=` (one per session, not per request) and no message id; `request_usage` carries `[message_id, output_tokens, prompt_tokens, budget]`. A literal implementer without the fixture cannot derive the pairing; an implementer with the fixture can, but the spec never says the pairing is **positional in completion order** (the only reading consistent with "in count and order" and the trailing-C rule).

**Failure scenario.** An implementer infers the pairing is by `(prompt_tokens, generated_tokens)` (the fields present on both sides). Two requests in a session produce the same token counts; the pairing becomes ambiguous; the "exactly one trailing C absent" check misidentifies which C is unaccounted, or a real mismatch is masked by an accidental count match. The §13 red test passes against the fixture (which has no duplicate counts) but a real session with duplicate counts misreconciles.

**Change.** State explicitly that the pairing is positional in `Request completed` order against `request_usage` order, and that the per-request equality is on `(prompt_tokens, generated_tokens)` (or whatever the 17/17 fields are). Name the fields. The fixture test then pins the field set, not the existence of a pairing.

---

### F6 — §8 decode-rate estimator — MINOR — the literal `D = generated_tokens_total / avg_decode_tok_s` divides by zero when no tokens

**Problem.** §8 defines `D = generated_tokens_total / avg_decode_tok_s` and parenthetically equates it to `Σ decode_elapsed_s` (0 when no tokens). In the fork (`generation.py:713`), `avg_decode_tok_s = generated_tokens_total / decode_time_total_s` when `decode_time_total_s > 0`, else `0.0`. So when no tokens decoded, `avg_decode_tok_s = 0` and the literal formula `generated_tokens_total / avg_decode_tok_s` is a ZeroDivisionError (or `inf`), not 0.

**Failure scenario.** An implementer codes the literal formula. An item whose every request generated ≤ 1 token (all immediate stops) yields `avg_decode_tok_s = 0`; the decode-rate estimator divides by zero and either crashes the watcher or writes `inf`/`nan` into the receipt, which B6 then drops or mis-averages. The parenthetical "0 when no tokens" is the intent but not what the formula computes.

**Change.** Define `D` directly as the worker's `Σ decode_elapsed_s` (read from `/metrics` deltas), and drop the `generated_tokens_total / avg_decode_tok_s` formulation, or add an explicit "0 when `avg_decode_tok_s == 0`" guard. The §13 test for the 0-token request already exists; pin `D = 0` there.

---

### F7 — §6.4 — MINOR — "vmmap / lsof" is named loosely for loaded-dylib enumeration

**Problem.** The receipt records "the native libraries the worker actually loaded (`vmmap` / `lsof -p <worker>`)." `lsof -p` lists file descriptors, not loaded dylibs; on macOS the reliable tool for loaded libraries is `vmmap -interleaved <pid>` (or `task_for_pid`-based inspection). Naming `lsof` as an alternative invites an implementer to use it and record nothing useful (or the wrong paths).

**Failure scenario.** An implementer uses `lsof -p <worker>`, which does not list `libmlx.dylib`/`mlx.metallib` as loaded images; the receipt records `libmlx` paths as absent; the pair gate either always passes (absent == absent) or always refuses.

**Change.** Name `vmmap` as the mechanism (e.g. `vmmap -interleaved <pid>` filtered for `libmlx.dylib` / `mlx.metallib`); drop `lsof` or restrict it to a fallback that explicitly notes its limitation.

---

### F8 — §2 — MINOR — the pilot-mean fallback to "a recorded generic default" does not name the default or where it is recorded

**Problem.** §2/C221 retires `chain_core.PRED_S` from the tg1 path and says per-model predictions come from "the pilot mean else a recorded generic default." The code (`chain_core.py:2520`) falls back to `self.pred.get(key, 250)` — the PRED_S table — when `n < PILOT_N`. An implementer must replace that with a single recorded generic default, but the spec does not say what the value is, where it is recorded (ChainConfig? `chain.json`?), or whether it is per-leg or global.

**Failure scenario.** Two implementers pick different generic defaults (one keeps 250 s, another uses the P456 rehearsal mean); both pass §13 (which does not test the fallback value) while producing different leg deadlines and ETAs, and one deadline is too tight and triggers false `OVERRUN_PAUSED`.

**Change.** Name the generic default (e.g., "the P456 rehearsal's mean per-item wall, 250 s, recorded in `chain.json` as `generic_pred_s`") and add a §13 test that a leg with no pilot rows uses exactly that value.

---

### Scope requests (no severity)

**SR1.** §6.4 records "the full environment of the router, the worker and the probe" plus a closed volatile-key list. The full key *set* (keys only, no values) is recorded for volatile keys. The key set alone is not behaviour-affecting; only the allowlisted values and the secret `same`/`different` verdicts enter the pair gate. The full key set could be dropped (keeping only the non-secret values + the secret verdicts) without weakening the gate, reducing the receipt's PII surface. Not required by the goal.

**SR2.** §4.3 keeps two independent token-sum comparisons (`Δprompt_tokens_total`/`Δgenerated_tokens_total` against both the log sums and the `request_usage` sums). Round-3 C-F9 noted the log sums already equal the client sums via the count+order equality, so one comparison suffices. The duplicate is cheap but adds a second failure mode (a log parse bug fails the leg on a redundant check). Dropping it would not weaken the goal.

---

### Sensitive areas flagged

§11.3 (secret gate / scrub — data boundary), §11.2 (symlink handling — data boundary), §9 / §10.3 (locks — exclusion), §5.2 / §3 (`p426_continue` policy and `invalidate` disposition — chain-core change), §6.4–§6.5 (arm-equality receipt / pair gate — data boundary for secret values). All fall within the four-eyes STRICT hunks named in §13.

---

The spec's load-bearing claims against the fork and the existing chain are accurate. The defects above are in the v3.1 additions and in the interaction between settled constraints (C220's > 2 DNF rule and the make-up leg; C228's pilot-derived bounds and the unpiloted Go items; S11's symlink rule and the model's own output). F1, F2, F3, and F4 would, under conditions the spec supports, either stop a run that should continue or leave harvested evidence in a state B6/B8 could misread; F5–F8 are literal-implementation hazards.
