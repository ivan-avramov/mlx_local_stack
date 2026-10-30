I have enough to write up findings. Let me record them now.

---

# Cold design review (round 2 of 3) — P426 B2 tg1 Wave 2 spec v3.2

Scope: the `[o4]` changes, all of §16, and the C238 change (cross-pair credential comparison dropped). Findings only.

---

## F1 — MAJOR — Pair dossier has no defined publication interface or harvest path

**Location:** §6.5, §11.2, §16.2, §16.6.

**Evidence:** confirmed (traced in source and spec).

§6.5 (v3.2) says the sequencer "writes an immutable pair dossier (`pairs/<pair>.json` …), published through the harvest to `benchmark/results/p426/wave2/pairs/<pair>.json` (§11.2)". §11.2 says "The pair dossier is published the same way" (staged publication). §16.6 says "pair dossiers are `<out-base>/pairs/<pair>.json` before their harvest."

But the only harvest interface defined is `bench.p426_harvest.harvest_wave2(leg_root, *, main_root, evidence_stage, scrub, secrets) -> dict` (§16.2), which inventories "every regular file under the attempt's leg root" (§11.2). The dossier lives at `<out-base>/pairs/<pair>.json` — **not under any attempt's leg root**. The sequencer seam is `ops.harvest(leg_root, *, emails) -> rc` (§16.6), again per-leg-root.

**Problem:** There is a hard ordering dependency and no home for the dossier:
- The dossier needs "both legs' `HARVEST.json` sha256" (§6.5). The second leg's `HARVEST.json` is written last, at the end of that leg's harvest (§11.2 "HARVEST.json is written last"). So the dossier is necessarily written *after* the second leg's harvest completes.
- Therefore the dossier cannot be published by either leg's `harvest_wave2` call (the second leg's harvest already finished; the first leg's harvest predates the dossier and lacks the second leg's HARVEST sha).
- No interface in §16 publishes a non-leg-root artifact. There is no `ops.publish_dossier`, no `harvest_wave2` variant that takes the pairs directory, and §16.6's `ops.harvest` is bound to a `leg_root`.

**Failure scenario:** An implementer following §16.2 builds `harvest_wave2(leg_root, …)` to inventory only the leg root; the dossier at `<out-base>/pairs/<pair>.json` is never copied to `benchmark/results/p426/wave2/pairs/`. B8 (the pair verifier) "consumes only attempts a dossier names" (§1) and resolves files only through `HARVEST.json` (§11.2) — but the dossier itself was never harvested, so B8 cannot resolve the pair. The goal's "every citable byte is harvested" is violated for the one artifact that binds the pair.

A second implementer, reading §6.5's "published through the harvest," might extend the second leg's `harvest_wave2` to also walk `<out-base>/pairs/` — but that conflicts with the §11.2 rule that inventory is "under the attempt's leg root" and would race the dossier write (the dossier needs the second leg's HARVEST sha, which that same harvest writes last).

**Proposed change:** Add an explicit sequencer-owned publication step for the dossier in §16, e.g. `bench.p426_harvest.publish_dossier(dossier_path, *, main_root, emails) -> dict` (same staged-publication + `HARVEST.json`-style receipt, idempotent), invoked by the sequencer after the second leg's `harvest_wave2` returns and the dossier is written. State in §11.2 that the dossier is published by this separate step (not by `harvest_wave2`), and that it is the one exception to "inventory = the attempt's leg root." Alternatively, fold the dossier into the second leg's harvest by deferring the dossier write to *within* the second leg's harvest after `HARVEST.json` is computed (then the dossier's own receipt is a second file in that leg's `HARVEST.json`) — but that requires the §16.1 `HARVEST.json` schema to allow a non-leg-root destination, which it currently does not.

---

## F2 — MAJOR — `p426_dnf` record `pick`/`load_gen`/`invocation`/`attempt` are undefined for a leg whose config requires exactly one model and whose attempts are sequencer-assigned

**Location:** §16.1 `p426_dnf` record; §1 attempts; §6.1.

**Evidence:** confirmed.

§16.1 `p426_dnf` record fields: `slot, item, session, language, seed, arm, pick, load, load_gen, invocation, attempt, abort, owned_at_incident, owned_after, settle, item_record, at`.

- `pick`: §6.1 says "P426 mode requires exactly one model." `pick` is singular, but the generic schedule (§6.1) supports ≥1 models and `pick` is per-row in the legacy layout. For P426 with one model, `pick` is always that one model — but the field is unnamed in §16 (no definition). An implementer must guess whether `pick` is the model name or the arm's pick index.
- `load_gen`: §5.2 says a DNF "returns to the loop, which relaunches the probe for the remaining slots of the leg in order on the same loaded instance (no reload)." So a DNF does NOT advance `load_gen`. But `load_gen` is in the record. For a single-load leg (all P426 legs are one load — §1's legs are single-session), `load_gen` is always 0. Its presence is unexplained.
- `invocation` and `attempt`: §1 says attempts are `<leg>.a<n>` assigned by the sequencer, and the chain writes `p426_dnf` (§5.2: "the chain writes the `p426_dnf` record"). But `attempt` is a sequencer-level concept (§1: "each launch of a leg is an attempt"). The chain, mid-leg, does not know its own attempt number — the sequencer assigns it. §16.6 says the sequencer "classifies a leg from the chain's rc, its `chain.json`…" — implying the chain writes `chain.json` without the attempt name. So who fills `attempt` in the `p426_dnf` record the chain writes?

**Problem:** Two implementers diverge: one has the chain write `attempt`/`invocation` as best-effort (leaving them null or wrong), one has the sequencer post-process the chain's `p426_dnf` sidecar to stamp `attempt`. Neither §16.1 nor §5.3 says which. The `p426_dnf` record is "not a row; never graded" (§5.3), but it IS harvested (§11.2 "DNF records") and B8 consumes it (§12 "p426_dnf records"). A missing or null `attempt` field breaks B8's per-attempt binding.

**Failure scenario:** A DNF fires on the second attempt of a leg (`<leg>.a2`). The chain writes `p426_dnf` with `attempt` null (it doesn't know it's a2). The sequencer doesn't post-stamp it. B8, resolving "only attempts a dossier names" (§1), sees a `p426_dnf` with no attempt and either drops it (a DNF occurrence silently lost — breaks C235 G1's "every planned slot as a row or a DNF") or mis-binds it to a1.

**Proposed change:** In §16.1, define each ambiguous field of `p426_dnf`: `pick` = the single model name (P426); `load_gen` = the load generation of the invocation that aborted (0 for P426's single-load legs); `invocation` = the chain's invocation index from `chain.json` `progress.invocations`; `attempt` = stamped by the sequencer when it writes `leg.json` (the chain writes it null/absent and the sequencer fills it post-hoc, like it fills `leg.json.attempt`). State explicitly which actor stamps `attempt`.

---

## F3 — MAJOR — `before_attempt`/`after_attempt` signature change breaks legacy hooks unless `context` has a default; §16.2 omits it

**Location:** §2 (chain-core edits), §16.2 `P426Hooks`.

**Evidence:** confirmed against `benchmark/bench/chain_hooks.py`.

The existing `ChainHooks` signatures are `before_attempt(self, slot)` and `after_attempt(self, slot, done)` (chain_hooks.py:88-94). §2 says "`after_attempt` / `before_attempt` gain a context argument (row, ready record, load context) with legacy hooks unchanged." §16.2 specifies `before_attempt(slot, context)` and `after_attempt(slot, done, context)` — **no default shown**.

The chain calls hooks via `run_before(slot)` / `run_after(slot, done)` (chain_hooks.py:108-112), which call `self.before_attempt(slot)` / `self.after_attempt(slot, done)`. If the chain is changed to pass `context` positionally and a legacy subclass keeps `before_attempt(self, slot)`, the call raises `TypeError: before_attempt() takes 2 positional arguments but 3 were given`. "Legacy hooks unchanged" is only achievable if `context` carries a default (`context=None`) and the chain calls with a keyword, or if the chain signature-probes.

**Problem:** §16.2's signature literally has no default. An implementer following §16.2 writes `def before_attempt(self, slot, context):` (required). The §13 test "legacy policies unchanged" / "legacy hooks unchanged" then fails for any legacy subclass that doesn't add the parameter. Two implementers diverge: one makes `context` required (breaks legacy), one adds `context=None` (matches §2's intent but contradicts §16.2's literal signature).

**Failure scenario:** The §13 red test "legacy policies unchanged" is written against §16.2's literal signature (required `context`); the existing `ChainHooks` subclass used by non-P426 tg1/M64 modes is not edited (§2: "legacy hooks unchanged"); the test fails because the chain now passes `context` to a hook that doesn't accept it — or, if the chain guards with `inspect.signature`, the P426 hook's required `context` is never passed by the legacy call path. Either way the "legacy unchanged" acceptance criterion (§14.1: "legacy tg1 / M63 / M64 goldens byte-identical") is at risk.

**Proposed change:** Write §16.2 signatures as `before_attempt(self, slot, context=None)` and `after_attempt(self, slot, done, context=None)`, and state that the chain passes `context` by keyword (so legacy subclasses accepting only `slot` / `(slot, done)` still work). Alternatively, specify that the chain probes the arity. Pick one and pin it in §13.

---

## F4 — MINOR — §4.3 DNF `completed_unaccounted` table cell says "session == the row's" but a DNF has no row

**Location:** §4.3 failed-line table, DNF `completed_unaccounted` row.

**Evidence:** confirmed.

The §4.3 intro (v3.2) says: "Every line in `C` carries `session=` == the item's session (the row's `session_id`; **for a DNF, which has no row, the abort manifest's session id** [o4])." But the table row for "DNF, a request in flight that the server completed before the client lost it" still reads: "exactly one trailing `C` line absent from `request_usage` (the abort manifest's in-flight message), **its session == the row's**, recorded as `completed_unaccounted` [r3]."

**Problem:** Literal contradiction with the intro clause. A test-writer building the DNF `completed_unaccounted` case from the table cell alone looks up `row.session_id`, which does not exist for a DNF (§5.3: "Not a row"). The intro rescues it, but the cell is wrong.

**Failure scenario:** Test-writer implements `reconcile_dnf` checking `line.session == row["session_id"]`; on the DNF fixture there is no row → `KeyError`/`None` comparison → the case that should be `dnf_completed_unaccounted` is misclassified as systemic. The §13 test "the `completed_unaccounted` DNF case" then fails or, worse, passes against a wrong implementation that synthesizes a fake row.

**Proposed change:** In the DNF `completed_unaccounted` cell, replace "its session == the row's" with "its session == the abort manifest's `session_id`".

---

## F5 — MINOR — `proc_argv` is referenced by §16.4 but absent from the §16.2 "ChainOps seams (`FakeOps` implements them)" list

**Location:** §16.2 ChainOps seams list; §16.4 `arm_receipt`.

**Evidence:** confirmed.

§16.2 lists the ChainOps seams "FakeOps implements them": `server_log_path`, `read_log`, `worker_metrics`, `proc_environ`, `interpreter_inventory`, `loaded_images`, `snapshot_hashes`. §16.4 introduces `ops.proc_argv(pid) -> list[str]` as the way `arm_receipt` obtains argv. `proc_argv` is not in the §16.2 list, and the §16.2 list is presented as the seams FakeOps implements.

**Problem:** A test-writer reading §16.2 as the canonical FakeOps surface builds FakeOps without `proc_argv`; the §16.4 `arm_receipt` test then calls `ops.proc_argv` and gets `AttributeError`. The §16.4 list does add `proc_argv`, but §16.2's "FakeOps implements them" framing is incomplete and misleading.

**Failure scenario:** The hermetic positive `--p426` leg (§16.4: "FakeOps (these seams + §16.2's) + the fake probe") is built from §16.2 only; `arm_receipt` raises `AttributeError` on `proc_argv`; the receipt is never written; the after-load pair-gate comparison fails as systemic on a hermetic positive.

**Proposed change:** Either add `proc_argv(pid) -> list[str]` to the §16.2 list, or state explicitly in §16.2 that the list is the s4/s5 baseline and §16.4–§16.6 extend it (so FakeOps must implement the union). One sentence.

---

## F6 — MINOR — §16.3 "D per item" clarification conflates the aggregate `decode_time` with per-request `decode_elapsed_s`

**Location:** §8 decode-rate estimator; §16.3 clarification 4; §16.2 `decode_time`.

**Evidence:** confirmed.

§8: "per item, `Σ max(generated_tokens_i − 1, 0) / ΔD` over its completed requests … ≤ 1-token requests contribute 0 tokens and the worker's own `D` for them, listed; §16.3 [o4]." §16.3: "`D` per item is the worker's own count: a 1-token request contributes the fork's fallback interval (`_decode_elapsed_from_metrics`), not zero; §8's numerator excludes it."

But §16.2 defines `decode_time(snapshot) -> float` (§4.1) as a function of the `/metrics` **summary** dict, and §4.1 defines `D = generated_tokens_total / avg_decode_tok_s` (aggregate, 0 when `avg_decode_tok_s == 0`). The per-item `ΔD` is `decode_time(after) − decode_time(before)` — an aggregate delta. There is no per-request `D` in the `decode_time` interface. The fork's `_decode_elapsed_from_metrics` fallback is a per-request logged value, not something `decode_time(snapshot)` produces.

**Problem:** §16.3 says "a 1-token request contributes the fork's fallback interval (`_decode_elapsed_from_metrics`), not zero" to "`D` per item." But `ΔD` is an aggregate difference of `decode_time(snapshot)`; the contribution of a single 1-token request to that aggregate is whatever the aggregate formula yields, not a per-request fallback. The clarification names a fork function (`_decode_elapsed_from_metrics`) that is not in the `decode_time` interface (§16.2) and not in the `/metrics` summary (§4.1). An implementer cannot reconcile §16.3 with §16.2's `decode_time`.

**Failure scenario:** Test-writer implements `decode_time(snapshot)` per §4.1 (aggregate ratio, 0 when avg==0). The §13 test "decode estimator with a 0-token request" (and the 1-token case) is written per §16.3 expecting the fork's fallback interval to appear in `ΔD` for a 1-token request; the aggregate implementation yields a different `ΔD`; the test fails or the estimator is silently wrong on the 1-token edge case that the spec explicitly calls out.

**Proposed change:** Reword §16.3 to say what it means in aggregate terms: `ΔD = decode_time(after) − decode_time(before)` already includes the wall time the worker spent decoding every request (including 1-token ones); the numerator `max(generated_tokens_i − 1, 0)` excludes the 1-token request's single token. Drop the reference to `_decode_elapsed_from_metrics` (a per-request fork function) from the `decode_time` clarification, or specify that the per-request `decode_tok_s` in the item record (§16.1 `requests[].decode_tok_s`) is the logged per-request value and `ΔD` is the aggregate — and that the estimator uses `ΔD`, not a sum of per-request fallbacks.

---

## F7 — MINOR — §6.4 "closed list of volatile keys" vs §6.5 "frozen in v8 from R1's diff" — source of the list is ambiguous

**Location:** §6.4, §6.5, §16.1 `v8_base` fields `volatile_env_keys` / `allowed_env_d_env_differences`.

**Evidence:** confirmed.

§6.4 fixes "a closed list of volatile keys (`_`, `OLDPWD`, `PWD`, `SHLVL`, `TERM_SESSION_ID`, `SECURITYSESSIONID`, `__CF*`) recorded as keys only." §6.5 says allowed differences include "the volatile / allowed-difference lists **frozen in v8 from R1's full pair environment diff** (extending them is a specification change)." §16.1 makes `v8_base` carry `volatile_env_keys` and `allowed_env_differences`.

**Problem:** Is the volatile list the §6.4 closed list (hardcoded, just persisted into v8), or is it *derived* from R1's observed diff (so if R1 shows an extra volatile key it gets frozen in)? "Frozen in v8 from R1's diff" reads as R1 being the source; "a closed list" reads as fixed. "Extending them is a specification change" implies you cannot extend even if R1 shows more — so R1 is a *confirmation*, and any extra diff is systemic. But the wording "frozen … from R1's diff" suggests R1 *populates* the list.

**Failure scenario:** R1's pair environment diff shows a key (say `COMMAND_MODE`) differing only in value across arms — neither in §6.4's closed list nor a credential. An implementer reading §6.5 as "R1 populates the allowed list" adds `COMMAND_MODE` to `v8_base.allowed_env_differences` and the pair gate passes; an implementer reading §6.4 as closed refuses the pair as systemic. The same R1 produces a VALID pair in one build and an INVALID pair (systemic) in the other.

**Proposed change:** State unambiguously: the volatile list is exactly the §6.4 closed set (v8 persists it for portability, not to extend it); `allowed_env_differences` is empty by default and may only be populated by a specification change; any non-credential, non-volatile difference R1 reveals is systemic (not auto-allowed). Then R1's role is confirmation, not source.

---

## F8 — MINOR — `invalidate` disposition's membership in "the disposition vocabulary" is ambiguous (slot vs hook vocabulary)

**Location:** §2 chain_hooks edits; `chain_hooks.py` `_SLOT_DISPOSITION`.

**Evidence:** confirmed against `chain_hooks.py:58` (`SLOT_DISPOSITIONS = ("accepted", "cheat", "unclear", "exhausted")`) and `slot_disposition()` (chain_hooks.py:78-83), which raises for any hook kind not in `_SLOT_DISPOSITION`.

§2 says `invalidate` "joins `KINDS`, `BEFORE_KINDS`, `AFTER_KINDS`, `from_dict` and the disposition vocabulary." The existing precedent: `pre_spawn_incident` is in `KINDS`/`BEFORE_KINDS` but deliberately *not* in `_SLOT_DISPOSITION` (it has "no attempt row to classify"). `invalidate` likewise stops the whole leg, not a slot. But "the disposition vocabulary" could be read as `_SLOT_DISPOSITION`, requiring `slot_disposition(invalidate)` to return something — which the current code cannot.

**Problem:** An implementer reading "joins the disposition vocabulary" as "add to `_SLOT_DISPOSITION`" adds a mapping `invalidate → <something>`, but there is no sensible slot disposition (the leg is INVALID, the slot is not "cheat"/"unclear"/"exhausted"). Another implementer follows the `pre_spawn_incident` precedent and leaves `_SLOT_DISPOSITION` alone. The §13 test "`invalidate` round-trips `from_dict`" passes either way, but a test that calls `slot_disposition(Disposition("invalidate", reason="…"))` diverges.

**Failure scenario:** The `after_attempt` hook returns `invalidate(reason)`; the chain's slot-attempt recorder calls `slot_disposition(disp)`; in build A (added to `_SLOT_DISPOSITION`) it returns a string and the attempt is recorded with a bogus slot disposition; in build B it raises `ValueError` and the leg crashes mid-teardown instead of recording `INVALID` cleanly.

**Proposed change:** State that `invalidate` joins the *hook* vocabulary (`KINDS`/`BEFORE_KINDS`/`AFTER_KINDS`/`from_dict`) only, and — like `pre_spawn_incident` — has no `_SLOT_DISPOSITION` entry; the chain handles `invalidate` before any `slot_disposition` call (it writes `.stop`, records the leg INVALID, and does not classify the slot as an attempt row).

---

## Scope requests (no severity)

- **S1.** §16.6 `ops.harvest(leg_root, *, emails) -> rc` returns only an rc; the sequencer needs the `HARVEST.json` path/sha to write the pair dossier (§6.5 needs "both legs' `HARVEST.json` sha256"). Consider returning a handle/dict (rc + `harvest_json_path` + `harvest_json_sha256`) so the sequencer can populate the dossier without re-reading.

- **S2.** §5.5 / §16.6: the occurrences file is "JSON lines of the §5.5 records" with fields `(session, language, item, seed, arm_of_dnf, occurrence)`, but §5.5 says the file IS "the ordered union." It is unspecified whether the operator is responsible for emitting the union in s1-then-s2 / original-language order, or whether the sequencer sorts. §16.5 `makeup_groups(occurrences) -> list[dict]` groups by `(session, seed, language)` and orders "s1-then-s2 and original language order, items in their original order" — so the sequencer orders. State that the occurrences file is an unordered set and the sequencer canonicalizes, so a test-writer knows not to rely on input order.

---

## Summary

Eight findings: F1, F2, F3 are MAJOR (pair-dossier publication has no interface; `p426_dnf` has undefined/actor-unassigned fields; the hook signature change as written breaks legacy hooks). F4–F8 are MINOR (a DNF table cell that contradicts its own intro; a missing `proc_argv` in the FakeOps list; a `decode_time` clarification that names a fork function outside its interface; an ambiguous source for the volatile-key list; an ambiguous `invalidate` vocabulary membership). Two scope requests. The C238 change itself (dropping the cross-pair credential comparison, recording keys only, resuming on sequencer restart) is internally consistent with §6.4–§6.5 and §11.3; no finding against it.
