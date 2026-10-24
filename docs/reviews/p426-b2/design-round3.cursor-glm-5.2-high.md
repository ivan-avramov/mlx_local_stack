I'll review the specification against the code. Let me start by reading the material under review and relevantLet me examine the code referenced by the spec.I have enough context. Let me write up the findings concisely.

---

# B2 design review round 3 of 3 — findings

Reviewed `docs/specs/p426-b2-tg1-wave2.md` v3 against the code (`chain_core.py`, `chain_ops.py`, `chain_hooks.py`, `chain_incident.py`, `run_config.py`, `schedules.py`, `run_tg1_chain.py`, `p426_harvest.py`, `arm_opencode.py`, `main_models.yaml`), rulings C218–C234 / P481, and the round‑1/2 reviews + dispositions. v3 closes the round‑2 implementation gaps (F1 evidence‑policy check, F2 `transport_cause` gate, F3 `p426_continue` host, F4 make‑up seeds, F5 secret sources, F6 lock ownership, F7 invalidate‑vs‑DNF, F8–F12). Findings below.

---

### 1. §5.5 — MAJOR — make‑up leg does not say it filters occurrences by `arm_of_dnf`

**Problem.** The input is "the ordered union of every DNF occurrence of both arms and both sessions" and then "One fresh‑load leg per arm (OFF then ON); inside a leg, one invocation per (session, seed) group … items in their original order." The occurrence record carries `arm_of_dnf`, but the spec never says each make‑up leg runs only the occurrences whose `arm_of_dnf` matches the leg's arm. C220's intent ("DNF items rerun later in a labelled make‑up leg for BOTH arms") is that each arm's DNFs rerun under that arm's predictor.

**Failure scenario.** A helper reads "the ordered union of every DNF occurrence of both arms" as the make‑up leg's input and runs the full union in BOTH legs. The OFF make‑up leg reruns an ON DNF item under the OFF predictor, producing an OFF row for an item whose only original result was an ON DNF. The make‑up row is misattributed (an OFF make‑up row paired against an ON DNF), or the "repeat DNF is a finding" signal is computed across arms.

**Change.** State that each make‑up leg runs only occurrences whose `arm_of_dnf` equals the leg's arm, grouped by `(session, seed)`. Add a §13 test: a make‑up leg with DNFs from both arms runs each arm's DNFs only under that arm.

---

### 2. §4.4 — MAJOR — engagement field source is unnamed (client `request_usage` vs server log vs worker `/metrics`)

**Problem.** §4.4 requires "every completed request with `generated_tokens ≥ 2` carries integer `draft_rounds ≥ 1`, `draft_n ≥ 1`, `0 ≤ draft_n_accepted ≤ draft_n`, `draft_kind=mtp`," with basis in the fork's speculative code. But the draft counters are drafter‑global diffs (B1, server‑side) — they cannot be in `request_usage` (the client stream). §4.3 pairs `request_usage` with the server `Request completed` line on "the pinned field pairing" (count, prompt, generated tokens); `draft_*` are not in that pairing. The spec never says which source each engagement field is read from. A helper could look for `draft_*` in `request_usage` (absent), and either always fail ON or skip the check.

**Failure scenario.** Helper reads `request_usage` for `draft_kind`; it is absent on every request; every ON leg is marked systemic (engagement failure) and stops, or the helper silently skips engagement and a degraded‑drafter ON leg passes VALID with no MTP proof — the round‑1 B1 failure via a different path.

**Change.** State that engagement fields (`draft_kind`, `draft_rounds`, `draft_n`, `draft_n_accepted`) are read from the server `Request completed` line (B1's per‑request `draft_counters`), not from `request_usage`; `generated_tokens` for the ≥2 threshold is the value reconciled in §4.3. Name the §13 red test against the log‑line source.

---

### 3. §4.4 — MINOR — engagement scope (A4 window) is ambiguous

**Problem.** §4.4 says "every completed request with `generated_tokens ≥ 2`" without scoping to item requests. The A4 window (§4.3 last row) is reconciled separately but is not excluded from engagement. An A4 request that generates ≥2 tokens under ON must carry draft counters (the drafter runs during A4 too); the spec does not say whether engagement applies to the A4 window.

**Failure scenario.** Helper applies engagement to A4 requests; A4's `Request completed` lines lack `draft_counters` (B1 only threads them at certain call sites, or A4 uses a non‑streaming path); every ON leg is systemic at load time. Or the helper skips A4 and a real drafter failure during A4 is missed.

**Change.** State explicitly whether engagement applies only to item requests (the A4 window is reconciliation‑only) or to the A4 window as well, and add the corresponding §13 test.

---

### 4. §6.4 — MINOR — "libmlx.dylib and mlx.metallib loaded by the worker" is unobservable as written

**Problem.** The arm‑equality receipt records "the sha256 of `libmlx.dylib` and `mlx.metallib` loaded by the worker." The worker is a subprocess; the *loaded* library's identity is not the same as the on‑disk file at receipt time (the worker may have loaded a cached or translocated copy). The spec gives no mechanism (e.g. `vmmap`/`lsof` of the worker pid, or the worker reporting its own loaded paths). A helper hashes the on‑disk file, which can match across arms while the loaded bytes differ.

**Failure scenario.** One arm's worker loads a different `libmlx.dylib` (a stale DYLD cache, a translocated copy) but the on‑disk file at the canonical path is identical across arms; the receipt records equal hashes; an arm‑dependent Metal‑kernel difference is hidden from the pair gate.

**Change.** Name the mechanism (read the worker's loaded library paths via `vmmap -interleaved <pid>` or have the worker emit them in `/metrics`), and hash the file at the *loaded* path. Add a §13 test that a translocated `libmlx.dylib` is detected.

---

### 5. §5.4 / §12 — MAJOR — the DNF scoring conflict is deferred to the operator but B2's contract to B6 is not pinned

**Problem.** §5.4 defers the DNF scoring decision to the operator at Go and gives a *recommendation* (`acc_strict@budget` over ALL planned slots, DNF = non‑success, labelled `transport_dnf`). §12 contracts "rows, `p426_dnf` records" to B6/B8 but does not say which denominator B6 must use, and §5.4 explicitly says "B2 builds the records either reading needs." B2's own §13 tests do not test the scoring denominator. A helper can build B2 to emit only the records and leave the denominator to B6; B6 then computes `acc_strict@budget` over completed‑only (the smaller denominator), reproducing the round‑2 S2/C2 bias the operator has not yet ruled on.

**Failure scenario.** ON completes 41 stronger items and has 2 DNFs; OFF completes all 43. B6, unconstrained by B2's contract, computes `acc_strict@budget` over completed slots (41/41 vs 43/43, both 100%); the ON−OFF delta is 0 and the signals sheet supports shipping, while AGENTS.md's "DNF included" rule is violated.

**Change.** Either obtain the operator's ruling on the denominator before B2 freezes (the round‑2 disposition said "operator at Go"; that is after B2 is built), or pin in §12 the contract B6 must follow: B6 ranks `acc_strict@budget` over ALL planned slots with a DNF counted as a non‑success, with the make‑up result as a sensitivity line. Without this, B2 can pass its tests while the goal (paired evidence for the ship call) is silently biased.

---

### 6. §10.3 / §8 — MINOR — watcher death detection during overrun is unspecified

**Problem.** §8 says "Watcher death or a missing receipt → speed‑invalid." §10.3 says the sequencer "keeps supervising the chain and the watcher" during overrun but does not say how the sequencer detects watcher death (pid poll? the watcher's receipt file? a heartbeat). The watcher is a separate process bound by `--driver-pid`; if it crashes silently during an overrun, the sequencer must notice to mark speed‑invalid.

**Failure scenario.** Watcher crashes mid‑overrun; the sequencer does not poll its pid; the chain eventually exits; the sequencer harvests with no watcher `exit_state` but also no speed‑invalid flag; B6 reads a missing speed block as "not order‑balanced" instead of invalid.

**Change.** State the supervision mechanism (poll the watcher pid + start‑time each tick; a missing pid → speed‑invalid, recorded in the leg record) and add a §13 test for watcher death during overrun.

---

### 7. §6.4 — MINOR — "router and probe venvs" is ambiguous when both are `.venv-bench`

**Problem.** `ChainOps.py = repo / ".venv-bench/bin/python"` and the probe runs from the same repo; router and probe share one venv. §6.4 says "the installed‑package inventory … of the router and probe venvs," implying two inventories. A helper records two identical inventories (redundant) or one (and the receipt schema is unclear).

**Failure scenario.** Helper records one inventory keyed "venv"; the pair gate compares OFF‑one vs ON‑one and passes; a future change that splits router/probe venvs is not caught because the receipt schema never required both.

**Change.** State that in P426 mode the router and probe share `.venv-bench` and the receipt records one inventory (or, if both are required, name the two paths explicitly).

---

### 8. §1 / §10.2 — MINOR — legs 9–10 (make‑up) are listed as run legs but are operator‑triggered

**Problem.** The legs table lists 9–10 as `tg1-p426-{off,on}-makeup` with `makeup --occurrences <file>`, but §5.5 says make‑up is "the operator's call." §13's "sequencer order" test could be read as requiring the sequencer to run legs 9–10 automatically. A helper could wire the sequencer to auto‑run make‑up after legs 3–8, which is not the intent (the operator decides).

**Failure scenario.** Sequencer auto‑runs make‑up after s1/s2/reload without the operator's call; a make‑up leg runs on a contaminated box (the operator had not paused); its rows enter the harvest and a "repeat DNF" finding is recorded under wrong conditions.

**Change.** Mark legs 9–10 in the table as "operator‑triggered, conditional on DNFs" and state the sequencer stops after legs 3–8 (or after the last paired leg) and waits for the operator's make‑up call.

---

### 9. §11.3 — MINOR (data boundary) — rotated‑secret false‑clean is possible

**Problem.** §11.3 reads secret values from the machine config, `<WT>/.env` of both arms, the sequencer's environment, and the token files. If a token was rotated between the leg and the harvest, the leg's transcript may carry the *old* token, which the harvest's primary scan (current values) does not match; the format scan (`hf_…`, `sk-…`) is the only backstop, and a non‑standard‑format secret (a custom gateway key) ships to `main`.

**Failure scenario.** The box's HF token is rotated between s1 and the harvest; an s1 transcript contains the old token (not `hf_`‑prefixed in the raw bytes, or a gateway bearer token); the primary scan matches nothing; the format scan misses it; the old token ships to `main` as a transcript.

**Change.** Add a rule: a secret source that is unreadable or empty at harvest time fails the harvest (fail closed) rather than scanning against nothing; and record the secret‑source *sha256* (not the values) in `HARVEST.json` so a later rotation is detectable. This is a tightening of the existing §11.3 refusal, not a new scope.

---

### 10. Scope request (no severity) — the arm‑equality receipt could drop the full environment key set

§6.4 records "the full environment key set" plus behaviour‑affecting values. The key *set* alone is not behaviour‑affecting; only the values of the allowlist matter for the pair gate. The full key set could be dropped (keeping only the allowlist values + the `same`/`different` verdict for secret keys) without weakening the gate, reducing the receipt's surface. Not required by the goal; labelled as scope.

---

### Sensitive areas flagged

§11.3 (secret gate / scrub — data boundary), §9 / §10.3 (locks — exclusion), §5.2 / §3 (`p426_continue` policy and `invalidate` disposition — chain‑core change), §6.4–6.5 (arm‑equality receipt / pair gate — data boundary for secret values). All fall within the four‑eyes STRICT hunks named in §13.