I have enough evidence. Let me write up the findings.

## Findings

### F1 — BLOCKER — `load_references` rejects the peaks rows the spec tells you to keep

**Location:** spec S4 ("`dev/p415_reference_peaks.json` keeps its historical rows (open question Q2)") and S4 ("drop the four pruned entries from `dev/p369_phase2/qualify.py` `ENTRIES`"), against `mlx-vlm/dev/p369_phase2/qualify.py:583-590`.

**Problem:** `load_references` iterates every key of `p415_reference_peaks.json` and raises `ValueError("reference for an unknown entry …")` for any key not in `ENTRIES`:

```583:593:mlx-vlm/dev/p369_phase2/qualify.py
def load_references(path, *, table=None, blob_exists=None):
    table = json.loads(Path(path).read_text()) if table is None else table
    for name, ref in table.items():
        if name not in ENTRIES:
            raise ValueError(f"reference for an unknown entry {name!r}")
```

The peaks file has 7 keys; 4 are pruned entries (`Qwen3.8-27B-static-mixed-4bit`, `Qwen3.8-27B-OptiQ-4.5bpw-mixed`, `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`, `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`). S4 drops those four from `ENTRIES` but Q2 keeps their peaks rows. The real qualify run calls `load_references(REFERENCES, blob_exists=…)` (`qualify.py:946`) with no `table=` override, so it reads the real file and raises for the four kept rows.

**Failure scenario:** After implementing S4+Q2 as written, `python -m p369_phase2.qualify …` aborts at reference load with `ValueError: reference for an unknown entry 'Qwen3.8-27B-static-mixed-4bit'`. The P415 R7 dev harness — which reads the registry — no longer works, violating the Goal's "every harness that reads the registry keeps working." Worse, acceptance criterion 5 still passes: every `test_p415_qualify.py` call to `load_references` passes a synthetic `table=` (lines 478, 485, 892, 1037, 1042) or monkeypatches it (557, 954); none loads the real file. So the suite is green while the harness is broken — exactly the "criterion passes while the goal fails" case.

**Proposed change:** Reconcile S4 and Q2. Either drop the four rows from `p415_reference_peaks.json` (and move Q2's "keep" to a non-goal note that they stay in git history), or relax `load_references` to ignore keys absent from `ENTRIES` (treating them as historical). Add a fork test that loads the real `REFERENCES` file against the pruned `ENTRIES` so criterion 5 can detect this regression.

---

### F2 — MAJOR — `test_p415_qualify.py` count/set assertions and STATIC usage are not retargeted <!-- allow-shorthand: verbatim reviewer output -->

**Location:** spec S4 ("`mlx_vlm/tests/test_p415_qualify.py` keeps coverage of the `served` arm with a synthetic or remaining entry"), against `mlx-vlm/mlx_vlm/tests/test_p415_qualify.py:137-149, 832` and ~20 `STATIC` sites (23, 56, 60, 111, 141, 148, 165, 179, 187, 219, 224, 375, 526, 536, 645, 656, 670, 685, 741, 1217, 1249). <!-- allow-shorthand: verbatim reviewer output -->

**Problem:** S4 only mentions preserving served-arm "coverage." It does not mention that `test_t1_the_seven_entries_and_their_arms` asserts `set(qualify.ENTRIES) == {7 entries}` (137-149) and `len(qualify.default_entries()) == 7` (149, 832), nor that `STATIC = "Qwen3.8-27B-static-mixed-4bit"` (a pruned entry) is the file-wide served-arm exemplar, used both as a fixture dict *and* as a name passed through `entry_problems`/`arm_for` (e.g. line 165 `entry_problems([FABLE, STATIC], …) == []`), which require `STATIC ∈ ENTRIES`. <!-- allow-shorthand: verbatim reviewer output -->

**Failure scenario:** Following S4 literally (drop 4 from `ENTRIES`, retarget only "served-arm coverage"), `ENTRIES` becomes 3 entries; `test_t1_the_seven_entries_and_their_arms` fails (`set != {7}`, `len != 7`), and any retargeted served-arm test that routes through `entry_problems`/`arm_for` with the served name fails unless that name is in `ENTRIES`. Criterion 5 ("0 failed") cannot be met by the spec as written.

**Proposed change:** Enumerate in S4: update the `set(qualify.ENTRIES) == {…}` and `len == 7` assertions to the post-prune set; replace `STATIC` throughout (or scope the retarget); and explicitly state whether `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` is added to `ENTRIES` as `"served"` (see F3). <!-- allow-shorthand: verbatim reviewer output -->

---

### F3 — MAJOR — S4 drops served entries from `ENTRIES` but needs one for the served-arm coverage it requires

**Location:** spec S4 ("drop the four pruned entries from `dev/p369_phase2/qualify.py` `ENTRIES`" + "keeps coverage of the `served` arm with a synthetic or remaining entry (`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` is served, non-MTP)"). <!-- allow-shorthand: verbatim reviewer output -->

**Problem:** The served-arm coverage via Nemotron routes through `arm_for`/`entry_problems`, which do `shipped = ENTRIES[name]` and `[n for n in names if n not in ENTRIES]` (`qualify.py:67, 86`). After S4's drop, `ENTRIES` has only the 3 MTP-on entries; Nemotron is not in it. So `arm_for(Nemotron)` raises `KeyError` and `entry_problems([Nemotron])` returns "unknown entry." The spec never says to *add* Nemotron to `ENTRIES`. <!-- allow-shorthand: verbatim reviewer output -->

**Failure scenario:** The implementer retargets the served-arm test to Nemotron (as the spec suggests) but, per S4, only removes from `ENTRIES`. The retargeted test fails with `KeyError`/`unknown entry`, so the served-arm coverage the spec requires is unreachable. <!-- allow-shorthand: verbatim reviewer output -->

**Proposed change:** State explicitly: add `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit: "served"` to `ENTRIES` (making the post-prune set 4), or specify that served-arm coverage uses a synthetic entry dict that bypasses `ENTRIES` (and drop the `entry_problems`/`arm_for` cases that need it). <!-- allow-shorthand: verbatim reviewer output -->

---

### F4 — MAJOR — S2's "`probe_code_sha256`" claim is false and contradicts acceptance criterion 2

**Location:** spec S2 ("The tg1 carrier change moves `probe_code_sha256` (expected; Wave 2 is a new epoch)") and criterion 2 ("every generated-file diff is the removal of pruned entries only (no other line changes)").

**Problem:** `probe_code_sha256` does not exist in the tg1 carrier or any configgen output. It is a *runner manifest* identity field produced by `tg1_runner.identity()` from the import closure of `run_tg1_probe.py` (see `docs/specs/p311-identity-split.md`, `c147-tg1-chain-clearance.md`). Registry pruning does not touch `run_tg1_probe.py`, so `probe_code_sha256` does not move. `rg probe_code_sha256` in `benchmark/opencode_bench_v2_web_tg1.json` and `configgen/emitters/` returns nothing.

**Failure scenario:** An implementer expecting a `probe_code_sha256` line change in the regenerated tg1 carrier either (a) hand-edits the carrier to force one (violating "never hand-edit"), or (b) reads the carrier diff — which is removals-only — and concludes criterion 2 is violated because S2 told them to expect a non-removal change. The two statements conflict, and the premise is wrong.

**Proposed change:** Delete the `probe_code_sha256` sentence from S2. If a new tg1 epoch is actually intended, call it out as a separate runner-side action (code change to `run_tg1_probe.py`, not a configgen output) with its own test; otherwise the regenerated tg1 carrier diff is removals-only, matching criterion 2.

---

### F5 — MINOR — Orphaned historical comment between two pruned blocks is not classified

**Location:** spec S1 ("delete the six entry blocks, each with the comment lines that belong only to it … No other byte changes"), against `mlx_local_stack/main_models.yaml:420-424` (the `# RETIRED 2026-08-26 (C33 …) the M23 reference entry Qwen3.8-27B-4bit …` block).

**Problem:** That comment sits between two pruned entries (`Qwen3.8-27B-static-mixed-4bit` above, `Qwen3.8-27B-OptiQ-4.5bpw-mixed` below) but belongs to neither — it documents an already-removed third entry. S1's rule "comment lines that belong only to it" does not say whether to keep or delete a comment that belongs to no adjacent entry. After pruning, it would lie between two kept entries (`Qwen3.8-27B-mlx-uniform-4bit` and `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`).

**Failure scenario:** Two implementers, both following S1, produce different `main_models.yaml` (one keeps the comment, one deletes it). Both pass criterion 1 ("diff consists only of deleted lines"), but the registry text diverges, making the "byte-identical" guarantee across arms ambiguous.

**Proposed change:** Add an explicit rule for orphaned between-pruned-entries comments (keep historical notes that reference no pruned entry; delete only comments that introduce a pruned block).

---

### F6 — MINOR — New registry-name test is underspecified vs. the task_model block and README historical names

**Location:** spec S3 new test ("the live registry's entry names equal the README-published set above, and no configgen output names an entry absent from the registry").

**Problem:** (a) The registry has a top-level `task_model` block (`mlx-community/Qwen2.5-1.5B-Instruct-4bit`) whose name configgen emits into carriers (opencode `mlx-task` provider). It is not a `models:` entry, so a naive "no configgen output names an entry absent from the registry" check false-positives on it. (b) "the README-published set" is ambiguous: the README's R7 peaks table (`README.md:62`) still lists the four pruned served entries as historical evidence; a test that scrapes README names would include pruned names and fail.

**Failure scenario:** The new test, written literally, fails on the task_model name (flagged as absent from `models:`) or passes/fails inconsistently depending on whether "README-published" means the picks section or any README mention.

**Proposed change:** Scope the test to `models:` entry names (exclude `task_model`), and define the expected set as the explicit five names listed in the Goal (not "scraped from the README").

---

### F7 — MINOR (clarity) — `test_deployed_gemma_is_the_daily_driver_not_the_coding_profile` cannot be retargeted to a remaining entry "keeping what it asserts"

**Location:** spec S3 ("retargeted to a remaining entry or to a fixture registry, keeping what each test asserts"), against `mlx_local_stack/benchmark/bench/tests/test_deployed_profile.py:92-97`.

**Problem:** That test asserts gemma-specific deployed values (`temp 0.7, top_k 64, repetition_penalty 1.08, thinking_budget 16384, max_tokens 32768`). No remaining entry has those values, so retargeting to a remaining entry requires changing the literals, which "keeping what each test asserts" forbids.

**Failure scenario:** The implementer retargets to Ornith (kept) but must change the asserted values, then is unsure whether that violates "keeping what each test asserts." <!-- allow-shorthand: verbatim reviewer output -->

**Proposed change:** Say explicitly that this test must retarget to a fixture registry containing a gemma-like entry (to preserve the literal assertions), or that "keeping what it asserts" means the *property* (deployed == registry block, and differs from coding), allowing the literals to be updated to the remaining entry's block.

---

**Scope request (no severity):** Add a fork test that exercises `qualify.load_references` against the *real* `dev/p415_reference_peaks.json` with the pruned `ENTRIES`, so acceptance criterion 5 can detect the F1 regression instead of passing while the harness is broken. This is beyond the literal request ("prune the registry") but is necessary for the Goal's "every harness that reads the registry keeps working" to be checkable.
