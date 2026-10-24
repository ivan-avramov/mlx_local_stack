I reviewed `p426-b2-tg1-wave2.md` v1 against the code (`run_tg1_chain.py`, `chain_core.py`, `chain_ops.py`, `chain_hooks.py`, `schedules.py`, `chain_incident.py`, `p426_leg.py`, `p426_harvest.py`, `p426_wave1.py`, `local_gate.py`, `m1/bench_watch.py`, `tg1_runner.py`, `arm_runner.py`, `main_models.yaml`) and the rulings (C218–C232). Findings below.

---

## B1 — BLOCKER — the per-item `done`-barrier hook is inert for tg1

**Location:** §2 "Per item, at the `done` barrier (a P426 `ChainHooks`)" and §6.

**Problem:** The chain only runs `pump_barrier`/`run_after` when `item_barrier_on(man, arm)` is true, i.e. the manifest's `runtime.evidence_policy.item_barrier == "on"` (`chain_core.py:2097-2100`). The tg1 probe ships `TG1_EVIDENCE = EvidencePolicy(..., item_barrier="off")` (`tg1_runner.py:42-43`), and `arm_runner.ItemBarrier` is a no-op when `evidence.item_barrier != "on"` (`arm_runner.py:1135`; `barrier.ready/done` return `go`/`continue` without writing files). So for tg1 the probe never emits the `.ready`/`.done` files `pump_barrier` polls for; if the chain reached `pump_barrier` it would hang. The spec places the entire engagement/reconciliation proof at that hook and says "the probe identity is unchanged" / "B2 … changes nothing an earlier chain relied on." Those two are incompatible: enabling the barrier requires editing `tg1_runner.TG1_EVIDENCE` (a probe-code change → `probe_code_sha256` changes → probe identity changes) OR a chain-side override of the manifest's evidence policy (a new chain mechanism the spec doesn't describe).

**Failure scenario:** A helper builds the P426 `ChainHooks` exactly as written; on the first tg1 leg the hook never fires; no per-item reconciliation or engagement proof runs; the leg exits VALID with zero engagement evidence; B8 has nothing to verify; the ship call rests on a run that never proved MTP engagement.

**Proposed change:** Either (a) acknowledge that B2 must flip `tg1_runner.TG1_EVIDENCE.item_barrier` to `"on"` for P426 legs and re-derive `probe_code_sha256`/arm identity (and list the consequence for older tg1 chains that share the probe), or (b) move the per-item reconciliation off the item barrier entirely — e.g. into the chain's per-invocation validation (`validate_leg`) plus a per-item server-log slice keyed by `session_id`, which the chain already has at the invocation boundary. State which.

---

## B2 — BLOCKER — the failure policy cannot be built from the existing tg1 chain as described

**Location:** §3 "Reuses the chain's `chain_incident` classification / `transport_dnf` rows (M64) without its in-leg retry"; §2 "Chain modes P426 does not use (… `incident_retry` retries, smoke) are refused."

**Problem:** Three concrete mismatches:
1. The tg1 chain runs `transport_policy="abort_restart"` (`run_tg1_chain.py:88`). On a transport incident `handle_incomplete` archives the **whole load**, reruns it once, then aborts (`chain_core.py:1999-2001`) — the opposite of "the item gets a `transport_dnf` record … the leg continues with the remaining items on the same loaded instance; retries 0."
2. The `transport_dnf` row machinery (`settle_dnf`, `run_block_leg`) lives **only** in the `per_arm`/`blocks` (M64) path (`chain_core.py:1921-1980`, gated by `self.per_arm`). tg1 uses `run_invocation` (`chain_core.py:1199-1211`), which has no `transport_dnf` writer. So there is nothing to "reuse" for tg1.
3. "Without its in-leg retry" contradicts the M64 design: `MAX_INCIDENTS = 2` (`chain_incident.py:17`) — the `transport_dnf` row is the row written **after** the in-leg retry fails. Removing the retry changes `MAX_INCIDENTS` to 1 (or adds a new policy), which is a new chain-core behaviour, not a reuse.

**Failure scenario:** A helper leaves `abort_restart` in place (the spec never says what policy replaces it for tg1). Item 3 of 22 hits a client timeout; the chain archives all 22 items' rows and reruns the whole load; the second attempt also aborts; the leg ends INVALID with no items scored and no `transport_dnf` rows — the "isolated item incident → DNF + continue" guarantee never exists, and the make-up leg has no DNF list to rerun.

**Proposed change:** Specify the new P426 transport policy concretely: a third policy (e.g. `transport_dnf_continue`) that on a classified incident writes one `transport_dnf` row for the slot, does not retry, and re-derives the remaining items into a fresh invocation on the same loaded instance — and say it is a chain-core change (already flagged architectural in §10). Drop the "reuses … without its in-leg retry" wording, which is self-contradictory.

---

## B3 — MAJOR — `block` disposition cannot express "systemic INVALID stop after that item"

**Location:** §2 "a missing engagement on ON or drafter activity on OFF is systemic (stop after that item)"; §3 systemic → "stop the leg at once, INVALID."

**Problem:** `ChainHooks.after_attempt` may return only `accept | rerun_same_slot | block` (`chain_hooks.py:7-9, 100`). `block(reason)` is the P201 "unclear — stop for the operator" disposition, not "systemic INVALID." Worse, for a non-`per_arm` chain (tg1) any non-`accept` after-disposition raises `ChainAbort` unconditionally (`chain_core.py:2143-2144`), so the hook cannot express "INVALID leg with a receipt and continue to the next leg" — it can only hard-abort the chain (rc 2, `write_json("aborted")`), which the spec's "thin outer step" would have to reinterpret as INVALID. The vocabulary has no systemic-INVALID disposition.

**Failure scenario:** ON leg, item 7 has no drafter counters. The P426 hook returns `block("engagement missing")`; the chain raises `ChainAbort`; the leg is recorded `aborted`, not `INVALID`; B8/B6 read "aborted" and either drop the leg or flag it inconsistently; the operator's ship call sees an aborted leg with no INVALID verdict.

**Proposed change:** Add a `systemic_invalid` disposition (or a documented mapping from a P426 hook exception → a per-leg INVALID receipt written by the thin outer step), and state how the chain distinguishes "stop for the operator" (P201) from "systemic INVALID" (C220) for the same after-barrier signal.

---

## B4 — MAJOR — `bench_watch` does not read `chain.json` and cannot assess a tg1 leg

**Location:** §7 "it reads progress from the chain's `chain.json` progress inventory."

**Problem:** `m1/bench_watch.py` reads a single `--rows-file` (one file) and counts rows in it (`bench_watch.py:254-285`). The tg1 chain writes rows across many files (`<stem>.L<leg>.<phase>.a<n>.jsonl`) and records progress in `chain.json.progress.invocations`. The watcher has no `chain.json` reader. C224 says it is "extended to read progress from the chain's `chain.json` progress inventory" — the extension is unbuilt and the spec gives no mapping from `chain.json`'s per-invocation inventory to the per-model `assess(model, bench, total, …)` shape the watcher expects (one cumulative rows file + a total).

**Failure scenario:** The watcher is launched with `--rows-file` pointing at one leg file; it undercounts (exactly the P469 symptom) or misattributes rows; its power receipt disagrees with the chain's WATCH lines; per §7 "the independent receipt decides," so a leg that the chain saw healthy is marked speed-invalid on a watcher undercount, or vice-versa.

**Proposed change:** Specify the `chain.json` → watcher contract: which fields feed `assess` (e.g. `progress.invocations[].accepted_slots` against the leg's `expected_ids`), and how the `--total` and per-model state are derived for a multi-leg session. Until that exists, §7's "independent receipt decides" rests on a reader that does not exist.

---

## B5 — MAJOR — gate ↔ sequencer mutual exclusion is one-sided in code

**Location:** §8 "the gate and a second sequencer refuse."

**Problem:** `local_gate.run` refuses only on `busy()` — a process census for `bench.p426_wave1`, `chain_ops.BUSY`, and a `:8000` listener (`local_gate.py:75-88`, `busy_problems`). A Wave-2 leg is `run_tg1_chain.py`, which is not in `BUSY` and is not `bench.p426_wave1`; the Wave-2 sequencer holds `p426/SEQUENCER.lock` but the gate never tries that lock. So during a PAUSE/test window the operator can start `local_gate run` while a Wave-2 leg (or the sequencer) is alive — the gate's census sees nothing busy, acquires `gate/RUNNING`, and tears down the box mid-leg. The spec asserts mutual exclusion in both directions but only the leg→gate direction (gate/RUNNING non-blocking try at leg entry) is described; the gate→sequencer direction is not implemented or specified.

**Failure scenario:** Operator opens a test window during the 600 s idle; `local_gate run` starts, sees no `bench.p426_wave1`/BUSY process, proceeds to clone+venv+pytest while the sequencer holds SEQUENCER.lock; the next leg's pre-check sees `gate/RUNNING` held and refuses, but the gate is already modifying the worktree/venv the leg depends on.

**Proposed change:** Add a non-blocking `flock(SEQUENCER.lock)` try to `local_gate.run`'s `busy()` (and to the pre-push `check` path if relevant), and state it in §8. Confirm the sequencer holds SEQUENCER.lock for its whole lifetime (including idle gaps and PAUSE), not just around launches.

---

## B6 — MAJOR (data boundary) — the Wave-2 harvest path is undescribed and the existing harvester cannot consume chain legs

**Location:** §9 "Harvest (C228) (`p426_harvest`, P437 rules, scrubbed), completeness-checked."

**Problem:** `p426_harvest.harvest` takes a `plan` produced by `p426_plan.plan_leg` for Wave-1 axes — it reads `plan["stem"]`, `plan["results_dir"]`, globs `{stem}.*`, and copies a fixed source set (`p426_harvest.py:80-99`). A Wave-2 leg's artifacts are `chain.json`, `RUNLOG.md`, `schedule.json`, per-leg rows/manifests/sidecars, A4 receipts, per-item log slices — a different shape with no `p426_plan` stem. The spec lists the Wave-2 layout but not the code that produces it. "Completeness-checked — every file a row/manifest cites lands on `main` or `evidence` with its sha256, else the leg's harvest fails" is a new check with no existing implementation. This is the data-boundary surface that triggers four-eyes STRICT (§10), yet the mechanism is the part left unsaid.

**Failure scenario:** A helper reuses `p426_harvest.harvest` with a chain-leg plan; it globs `{stem}.*` against a directory that has no such stem, copies nothing, writes an empty SCRUB_MANIFEST, and the leg is declared "harvested" with zero evidence on `main`; B8 later finds no per-item slices; the ship call has no citable bytes.

**Proposed change:** Specify the Wave-2 harvester (or a `harvest_wave2` entry point): the source set it walks, how it learns of every cited file from `chain.json`/rows/manifests (the completeness check), and how per-item server-log slices (§6, "B2 persists the per-item slice") are produced and staged. Mark this as part of the four-eyes STRICT scope.

---

## B7 — MAJOR — "every leg provably differs from its pair only in the entry's MTP state" is under-proven for the worker

**Location:** §4 "Worker tripwire: the argv mlx-serve builds from that entry — ON the three predictor flags exactly, OFF none"; Goal "every leg provably differs from its pair only in the entry's MTP state."

**Problem:** `ChainOps.require_shipped_predictor` reads the served file (`self.overlay`) and checks the worker argv against it (`chain_ops.py:505-535`). In P426 mode the served file is the worktree's `main_models.yaml`. That proves the worker matches the registry. It does **not** prove the two arms' workers differ *only* in the three flags: a worker is built from `src/mlx-vlm` + `src/mlx-serve` at the gitlinks. v8 asserts the gitlinks are identical, so the binary is the same — but the spec does not state that the worker **binary** (mlx-serve/mlx-vlm code) is asserted identical across arms, only that the gitlinks are. A gitlink pin is a commit hash; the built artifact is only identical if the build is deterministic and the venvs are synced to the same locks (§9 lists venv sync as a freeze precondition, good). But the per-leg check at §2 ("serving pins") must re-verify the *loaded* worker is the one the gitlink describes, not just that the argv matches the registry. The current `worker_env_check`/`require_shipped_predictor` checks argv + env, not the worker binary's identity. If the ON worktree's venv drifted (e.g. a stale build), the worker could differ in more than MTP and pass the argv check.

**Failure scenario:** ON worktree's `.venv` has a stale mlx-vlm with a different sampler; the worker argv still matches the registry (the three flags); the leg passes; ON and OFF differ in sampling behaviour, not just MTP; the ship call misattributes a sampling effect to MTP.

**Proposed change:** Add to v8 and to the per-leg pre-check a worker-binary identity assertion (e.g. the mlx-serve/mlx-vlm import-path sha or the installed wheel sha, recorded in the frozen record and re-verified after `load`), so "differs only in MTP" is proven on the running worker, not just on the argv.

---

## B8 — MAJOR — `--predictor` as an "assertion" is incompatible with the current `predictor` semantics, and the transition is unspecified

**Location:** §4 "`--predictor off|mtp` is an assertion of the entry's committed state, refused on mismatch"; `run_tg1_chain.py:88` uses `predictor` to choose `out_root_family` and `ChainOps` behaviour.

**Problem:** Today `--predictor` is a *selector*: it picks the overlay, the `out_root_family` (`m63` vs `c147`), and `ChainOps(predictor=...)` which drives `ensure_overlay` and `require_shipped_predictor`. The spec repurposes it as an *assertion* of the worktree's committed state. But the flag still has to drive `out_root_family` (ON and OFF must not share an out-root) and the tripwire branch. So it is both selector and assertion. The spec doesn't say which behaviours stay (out-root family, tripwire branch) and which become assertions (registry content). A helper reading §4 literally would make `--predictor` pure assertion and lose the out-root isolation (ON/OFF writing into the same dir) — which `inside_other_arm` exists to prevent (`run_tg1_chain.py:206-218`).

**Failure scenario:** Helper makes `--predictor` a pure assertion; ON and OFF legs both resolve to the default `c147` out-root; `inside_other_arm` refuses on the second leg; the run stops.

**Proposed change:** State explicitly which `predictor`-keyed behaviours survive (out-root family, tripwire branch, env) and which become assertions (registry content), and that the assertion is a new check layered on top, not a replacement of the selector.

---

## B9 — MINOR — §5 "s2 runs Go before Python" is not what `schedules.tg1` produces today

**Location:** §5 "s2 runs Go before Python"; `schedules.py:128-131`.

**Problem:** `_tg1_legs_table` for s2 is `[(p, l) for p in (p2## B9 — MINOR — §5 "s2 runs Go before Python" is not what `schedules.tg1` produces today

**Location:** §5; `schedules.py:128-131`.

**Problem:** `_tg1_legs_table` for s2 is `[(p, l) for p in ( (p2, p1) for l in ("python","go")]` — picks reversed, but languages still Python-then-Go within each pick. With one entry, s2 = (entry,python),(entry,go) → Python first. The spec's "s2 runs Go before Python" needs the language tuple reversed for s2, which the spec calls "implemented and tested in B2" (C223) but doesn't state as a `schedules.tg1` change. A helper could read §5 as "already true" and not change the builder.

**Failure scenario:** Helper leaves `schedules.tg1` as-is; s2 runs Python before Go; the test "s2 order reaches the probe" passes against the wrong order; the run completes with s1 and s2 using the same language order, defeating the decorrelation C223 chose.

**Proposed change:** State the concrete `schedules.tg1` edit (reverse `langs` for s2, or reverse the inner loop), and that it is a behaviour change to the shared builder that the M64/inject callers don't use (verify).

---

## B10 — MINOR — "parsed registries differ in exactly the entry's three keys" vs the §11 seeding-test change

**Location:** §4 / §9 vs §11.

**Problem:** §11 restore edits `main_models.yaml` (3 entry lines + a `PROVISIONAL P426` comment in `generation_defaults`) AND `tests/test_opencode_probe_seeding.py`. The registry comment is not a parsed key, so "parsed registries differ in exactly three keys" holds. But §4 says the v8 diff is "exactly the §11 restore (three lines, PROVISIONAL P426 note, the seeding test)" — i.e. the **commit** diff includes the test file. The Goal says "every leg provably differs from its pair only in the entry's MTP state"; the test file is not MTP state but is in the commit. The two phrasings are reconcilable (served state vs commit) but a helper could assert the diff is only `main_models.yaml` and miss the test file, or assert the test file is a difference "beyond MTP" and reject the arm.

**Failure scenario:** v8 check rejects the ON arm because the diff includes a test file the helper didn't expect; or v8 passes but B8 later flags "arms differ in a test file" as a non-MTP difference.

**Proposed change:** Separate "commit diff" (3 lines + comment + test file) from "served-state diff" (3 entry keys) in §4/§9, and state the test file is not on the serving path.

---

## B11 — MINOR — P469 is asserted as fixed but is OPEN and its fix is undescribed

**Location:** §7 "the chain's own WATCH lines (P469 fixed)."

**Problem:** P469 is OPEN in `open-questions.md` ("Not root-caused yet"); C228 puts the fix inside B2's scope. The spec lists it as a precondition ("P469 fixed") without describing the fix. The undercount is in `watch_rows` (`chain_core.py:2494-2503`), which sums `leg["prior_files"]` + `leg["out"]`; if the fix changes that, it touches the shared chain-core watch path older chains use.

**Failure scenario:** Helper treats P469 as already fixed and doesn't change `watch_rows`; the chain's WATCH lines undercount; §7 says those are "informational" so it doesn't block, but the operator's ETA during the run is wrong.

**Proposed change:** Either describe the P469 fix and list it as a chain-core change in §10, or drop "P469 fixed" from §7 and say the independent receipt (B4) is the authority, making the in-chain WATCH undercount moot.

---

## B12 — MINOR — `request_usage` as the "second independent source" is ambiguous against the existing reconciliation

**Location:** §6 "equal its client-side `request_usage` request for request (completion / prompt tokens, count)."

**Problem:** `p426_leg.request_match_problems` matches the server log to the **row's** `prompt_tokens`/`draft` fields (`p426_leg.py:328-357`), not a field called `request_usage`. The spec names `request_usage` (opencode's field) as the second source. It's unclear whether `row.prompt_tokens` IS `request_usage` or a separate field. If separate, the existing reconciliation matches the wrong field and the spec's "two independent sources" collapses to one (server log vs server-derived row).

**Failure scenario:** Helper reuses `request_match_problems` (row.prompt_tokens); the spec's "request_usage" field is never read; the two sources are not independent (both derive from the same opencode client call); a server-log omission that also corrupts the row passes.

**Proposed change:** Name the exact row field(s) that carry `request_usage` and confirm they are independent of the server log (different code path), or redefine the second source as the row's recorded counters with the independence argument.

---

## B13 — MINOR — "rows == the planned items in the planned order" is not checked today

**Location:** §2 Exit; `chain_ops.validate_leg:864-868`.

**Problem:** `validate_leg` checks `sorted(ids) == sorted(leg["expected_ids"])` (membership), not order. The spec wants the planned **order** verified. The order reaches the probe via `--items` (`chain_core.py:217`), but nothing verifies the rows came back in that order. A helper could pass the spec's tests with order-agnostic validation while the goal ("planned order") silently fails.

**Failure scenario:** A probe reorders items internally; `validate_leg` passes; the run is VALID but the seeded order C223 chose never reached the model in that order; the decorrelation claim is false.

**Proposed change:** Add an order check to the P426 exit (rows' `id` sequence == schedule order), or state that order is enforced only at `--items` and the probe's order is trusted.

---

## B14 — SCOPE REQUEST — a single `--models` list for one entry vs the Goal's "top picks, starting with this one"

The operator's request is to "re-certify MTP for the top picks, starting with this one." The spec runs one entry only. C221's `--models a[,b…]` (≥1) supports more, and C218's added goal is "keep going until MTP is re-certified across the board (all four MTP-certified entries)." The spec scopes Wave 2 to one entry and defers the rest to §11 ("per entry: … reusing B1–B12"). That matches the operator's "starting with this one," but the spec does not state whether the harness built here is reusable for the next entries without another B2-style change (e.g. the hard-coded `P426_ON` dict in `p426_leg.py:55-59` is single-entry). **Proposed:** state that the harness is general (the `--models` list, the v8 freeze, and the tripwire are entry-agnostic) and that only `P426_ON` and the §11 restore are per-entry, so the next picks need no B2 re-review.

---

## B15 — SCOPE REQUEST — the make-up leg is in the failure policy but not in the sequencer

§3 describes a labelled make-up leg for DNF items for both arms, but §1's leg table and §10's sequencer tests don't include it. **Proposed:** add the make-up leg to the sequencer's schedule (or state it is operator-launched out-of-band) and state how its evidence is kept out of the per-session pairs (B8/B6).

---

## Summary

The two blockers (B1, B2) mean a helper following the spec literally would build a run whose central guarantees are inert: the per-item engagement/reconciliation hook never fires for tg1 (B1), and the "DNF + continue" failure policy has no implementation path in the existing tg1 chain (B2). B3–B8 are major defects that either let the run pass while the goal fails (B7, B8, B13), lose/misattribute evidence (B6, B12), or break mutual exclusion (B5). B9–B13 are clarity/economy. The spec's strongest claims — "the chain-core change is architecture" and "the probe identity is unchanged" — are in tension with B1/B2/B3; resolving them is where the design work still is.
