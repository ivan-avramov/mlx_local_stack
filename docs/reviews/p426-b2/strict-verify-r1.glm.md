## Findings — P426 B2 Wave-2 (round 1 of 3)

I traced the data boundary (§11) and the grading path (§4/§5/§8) in the source. Two defects, both on the §5.3 DNF record (the grading path the brief prioritises); the harvest/scrub/secret gate, locks, idle gap, pair gate and reconcile equalities were traced and held.

---

### F1 — `p426_dnf` record is missing the `load` field required by §16.1
- **Location:** `benchmark/bench/chain_core.py:2610` (the `p426_dnf` record built in `handle_p426_incomplete`).
- **Severity:** major.
- **Evidence:** confirmed. Line 2610 reads `seed=view["seed_base"], arm=self.p426_arm_name(), pick=view["model"],     # the predictor arm (spec 16.8) load=load["idx"],`. The `#` opens a comment that swallows `load=load["idx"],`, so the dict literal never receives a `load` key. `p426_persist` (line 603‑605) only canonicalises paths and `ph.seal` only adds `sha256`, so `load` is never inserted. The sibling legacy incident record at line 2719 writes `load=load["idx"]` correctly, confirming the intended field. The frozen test `test_b2_frozen_s7_locks.py:198` asserts `pick/attempt/session/language/seed/arm/invocation/load_gen/slot/item_record` and the self-hash, but does **not** assert `load`, so the gap is not caught (the self-hash covers the record *as built*, so it passes).
- **Problem:** §16.1 fixes the `p426_dnf` schema as `{slot, item, session, language, seed, arm, pick, load, load_gen, invocation, attempt, abort, …}`; §12 contracts this record to B8/B6. The shipped record omits `load`, so a strict consumer doing `dnf["load"]` raises `KeyError`. (Mitigating: P426 legs are single-load, so the value would always be `0` — no information is lost, but the contract record is malformed.)
- **Scenario:** a transport DNF occurs on any leg; the sidecar `p426_dnf/<slot>.json` and the `chain.json` `p426_dnf` entry are published to `main` without `load`; B8/B6, reading the dossier's DNF records per §12, fail or must special-case the absent field.
- **Proposed change:** move `load=load["idx"],` out of the comment onto its own line in the dict literal (and add a frozen assertion that `dnf["load"] == 0`).

---

### F2 — `p426_dnf.attempt` (and `chain.json` invocation `attempt`) is the chain's per-stem counter, not the out-root's `.a<n>`
- **Location:** `benchmark/bench/chain_core.py:1909, 1994, 2611` (`invocation_paths` → `att["attempt"]` → the DNF record's `attempt`).
- **Severity:** major.
- **Evidence:** confirmed. `invocation_paths` sets `n = self.attempt_no.get(leg["stem"], 0) + 1`; `attempt_no` is initialised to `{}` per chain process (line 363) and never seeded from the out-root name. The CLI validates the out-root name `<leg>.a<n>` (`run_tg1_chain.py:367`) but never parses `n` from it. Each P426 leg is a fresh chain process on a fresh out-root, so the first invocation is always `n=1`. The sequencer's leg record, by contrast, carries the real out-root `n` (`p426_wave2.py:567`, `next_attempt`). So for a `.a1` leg both agree (1); for a `.a2` rerun the leg record says `attempt=2` while the DNF record and `chain.json progress.invocations[].attempt` say `1`.
- **Problem:** §16.1 fixes `attempt` as "the `n` of the out-root's name `<leg>.a<n>`, which the chain requires in P426 mode". The chain records its internal counter instead, so on any rerun the DNF record misidentifies its own attempt and disagrees with the leg record and the pair dossier (§1: a pair is bound by its dossier, which names its two attempts).
- **Scenario:** the operator reruns a leg (`--rerun <LEG> --rerun-reason …`); the sequencer launches the chain on `<leg>.a2`; a transport DNF fires on that leg; the published `p426_dnf` record carries `attempt=1`, so B8/B6 cannot link that DNF to attempt `<leg>.a2` named in the dossier, and the leg record (`attempt=2`) and the DNF record (`attempt=1`) contradict each other in the same `main` harvest.
- **Proposed change:** in P426 mode, derive `attempt` from `self.out_root.name` (parse the trailing `.a<n>`) rather than from `attempt_no`, and use that value for `att["attempt"]`, the invocation record's `attempt`, and the `p426_dnf.attempt`; add a frozen test that runs a `.a2` rerun and asserts the DNF record's `attempt == 2`.

---

### F3 — item record's `ready_sha256` is the ready FILE sha, not the ready record's self-hash (spec wording)
- **Location:** `benchmark/bench/p426_hooks.py:213` (`ready_sha256=self.ready_file_sha256(slot)`) and `benchmark/bench/p426_harvest.py:625‑639` (accepts either).
- **Severity:** minor.
- **Evidence:** confirmed. §4.5 says the item record holds "the ready record's sha256"; §16 defines a record's sha256 as its self-hash. The hook stores the sha256 of the ready file *bytes* (indent=1, sort_keys), and the harvest relaxes the check to accept either `{rdoc["sha256"], _sha(file_bytes)}`. Integrity is preserved (the ready record's self-hash is verified separately, and the file sha is also deterministic), so this is a wording/schema mismatch without material consequence.
- **Proposed change:** store `ready_sha256 = ready_doc["sha256"]` (the self-hash) and tighten the harvest to compare against that single value; or amend §4.5 to say "the ready record's file sha256".

---

No false-VALID path was found in reconciliation/engagement/DNF/speed/pair-gate; the secret/PII/email gate is fail-closed on both original and scrubbed bytes; symlinks are never followed; records are exclusive-created and self-hashed; the idle gap is enforced at both the sequencer and the chain entry; and legacy goldens are untouched.
