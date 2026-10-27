I have enough to write the review. Let me verify one more detail about the `--out` marker and the `s` path before finalizing.I have enough to write the review now. Let me record the findings.

# Cold design review (round 2 of 3) — `docs/specs/p426-t3-serving-build.md` v2, [o1] parts

I reviewed the [o1] changes against the current code (`bench.local_gate`, `bench.p426_wave1`, `bench.p426_leg`, `bench.p426_harvest`, `bench.modelnames`, `bench.p426_panel`), the fork at S′ (`review_material/fork-main-c688e722/dev/ci.py`, `.upstream-sync-ref`, `.github/workflows/`), and the P426 plan. Findings below.

---

## F1 — MAJOR (confirmed): the local gate cannot produce a PASS receipt for `c688e722` with the current code; the spec describes the target state but does not direct the change

**Location:** `docs/specs/p426-t3-serving-build.md` §3, "**The local gate on S′** [o1]" (lines ~63–66); acceptance 5 (line ~145); code `benchmark/bench/local_gate.py:228–229` (`current_parity`), `:34–35` (`AUDITS`).

**Evidence (confirmed):**
- At S′ (`c688e722`) the fork has no `.github/workflows/upstream-parity.yml` — only `pr-contributor-reminder.yml`, `python-publish.yml`, `tests.yml` — and `.upstream-sync-ref` holds `2ceff4c1` (verified on disk). The fork `AGENTS.md` states the workflow "is gone with hosted CI."
- `local_gate.current_parity` is:
  ```
  228:229:benchmark/bench/local_gate.py
  def current_parity(repo, live, sha):
      if repo != "mlx-vlm":
          return None
      return parity_ref(_git(live, "show", f"{sha}:.github/workflows/upstream-parity.yml"))
  ```
  `_git(..., check=True)` raises `GateError` when the path is absent. `digest_for` calls `current_parity`, so `run(...)` raises before any step. No PASS receipt is writable for `c688e722`.
- The spec's §3 [o1] paragraph is phrased descriptively ("`bench.local_gate` runs, for a fork sha, exactly the audits ... against the upstream ref that sha records (`.upstream-sync-ref` when present; the workflow file only for older shas)"). It states a property of the gate, not a change directive, and §3's lead ("Whatever the stack suite shows broken by the new dependencies is fixed in the stack") does not cover this — the gap is the fork's `dev/ci.py` having evolved, not a dependency break.

**Problem:** Acceptance 5 (`bench.local_gate` PASS receipts for the candidate stack commit, `c688e722` and `e6a7a5a`) is unattainable without editing `local_gate.py`. An implementer reading the [o1] paragraph as a description of (new) existing behavior could miss that `current_parity` and `AUDITS` must change, and the spec does not say "change `local_gate.py`" or specify the fallback mechanism (read `.upstream-sync-ref` first, then the workflow file).

**Failure scenario:** Implementer cuts S′, runs `bench.local_gate run --repo mlx-vlm --sha c688e722` to satisfy acceptance 5; `current_parity` raises `GateError("upstream-parity.yml: no UPSTREAM_SYNC_REF")`; no receipt; acceptance 5 fails; the build is blocked.

**Proposed change:** Add an explicit bullet to §3 directing the `local_gate.py` change: "`current_parity` reads `.upstream-sync-ref` at the sha when present, falling back to `.github/workflows/upstream-parity.yml` only for older shas; `AUDITS` is the fork `dev/ci.py`'s audit list at that sha (S′: nine, incl. `check_upstream_test_copies.py`)." State that this is a code change, not a description of current behavior.

---

## F2 — MAJOR (confirmed): hypothesis): `AUDITS` is stale (8 vs 9); "exactly the audits at that sha" is not realizable by the static list

**Location:** §3 [o1] ("exactly the audits the fork's own `dev/ci.py` runs at that sha (S′: nine, incl. `check_upstream_test_copies.py`)"); §6 test ("The local gate's audit list and upstream ref per fork sha (fixtures of both layouts)"); code `local_gate.py:34–35`.

**Evidence (confirmed):**
- `local_gate.AUDITS` has 8 entries and omits `check_upstream_test_copies.py`:
  ```
  34:35:benchmark/bench/local_gate.py
  AUDITS = ("check_upstream_parity.py", "check_upstream_symbols.py", "check_upstream_deletions.py", "check_fork_markers.py",
            "check_dead_helpers.py", "check_body_divergence.py", "check_upstream_registries.py", "check_call_arguments.py")
  ```
- The fork's `dev/ci.py` `AUDITS` at S′ has 9, the ninth being `("check_upstream_test_copies.py", ())` (verified). The fork `AGENTS.md` documents this audit as gating ("the ninth direction").

**Problem:** "Exactly the audits ... at that sha" is sha‑dependent, but `AUDITS` is a module‑level tuple. The spec leaves the mechanism unspecified: an implementer could hardcode 9 (satisfies S′, breaks the "at that sha" claim for older shas the §6 test also fixtures) or derive dynamically from the fork's `dev/ci.py` (the only way to honor "at that sha" for both layouts). The §6 test "fixtures of both layouts" implies sha‑dependence that a static list cannot provide.

**Failure scenario:** Implementer adds `check_upstream_test_copies.py` to `AUDITS` and stops. The §6 test for "both layouts" then needs an older sha with 8 audits; the static 9‑list runs the ninth against an older fork that lacks it → audit fails or errors → the gate refuses a correct older‑sha run.

**Proposed change:** Specify the mechanism: derive the audit list from the fork's `dev/ci.py` `AUDITS` at the sha (parse the module in the clone), and have `audit_argvs` use that list. If a static fallback is kept for robustness, state which shas it covers and that the §6 "both layouts" test uses derived lists.

---

## F3 — MAJOR (confirmed): hypothesis): the naming‑hook exemption claim is false against current `modelnames.py`, and the change is not directed

**Location:** §4 "Names under a label `b` ≠ `s`" — "the naming‑hook exemption for harvested Wave‑1 evidence (`bench.modelnames`) covers `wave1.<b>/` as it covers `wave1/` [o1]"; §6 ("harvest paths per label and the naming exemption"); code `benchmark/bench/modelnames.py:270–278`.

**Evidence (confirmed):**
- The exemption is a prefix test with a trailing slash:
  ```
  270:278:benchmark/bench/modelnames.py
  is_result_rows = path.startswith("benchmark/results/p426/wave1/") or path.startswith("benchmark/results/") and (
      path.endswith(".jsonl")
      or path.endswith("_samples_eval_results.json")
      or ("/result/" in path and path.endswith("_result.json"))
  )
  ```
  `benchmark/results/p426/wave1.s2/<leg>/<leg>.receipt.json` does NOT match `startswith("benchmark/results/p426/wave1/")` (the next char is `.`, not `/`), and `.receipt.json` / `.log` / `leg.stdout` / `SCRUB_MANIFEST.json` match none of the other clauses.
- Harvested dossiers under `wave1.s2/` contain the drafter hub path `caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mtp-drafter` (in receipts, the server‑log slice, the run‑files copy of `frozen.s2.json`). The basename is not a registry `name`, so its fragments (e.g. `Fable-Distill`, `OptiQ-4.5bpw`) are in the `fragments` index and are flagged as shorthands. The `data(bench)` commit of `wave1.s2/` evidence would be refused by the pre‑commit naming hook.
- The spec states this as a property ("covers `wave1.<b>/` as it covers `wave1/`"), not as a directed edit to `modelnames.py`; §3 ("Stack code on S′") scopes fixes to "broken by the new dependencies," which this is not.

**Problem:** The claim is false against the code an implementer starts from, and the required edit to `modelnames.py` is implied but not directed. A literal reader could treat the sentence as descriptive and ship without extending the exemption, after which the first `data(bench)` commit of S′ evidence is blocked by the repo's own hook.

**Failure scenario:** Wave‑1 rerun on S′ produces `wave1.s2/` dossiers; `git commit` of the harvest triggers `modelnames.diff_violations`; receipts / logs are flagged for `Fable-Distill` etc.; the commit is refused; S′ evidence cannot land without a `--no-verify` bypass (which the spec does not authorize).

**Proposed change:** Add an explicit §3/§4 bullet: "extend `modelnames.diff_violations`'s Wave‑1 exemption from `benchmark/results/p426/wave1/` to also cover `benchmark/results/p426/wave1.<b>/` for any label `b` (e.g. match `benchmark/results/p426/wave1[.][a-z0-9]+/`)." Add the §6 test that a `wave1.s2/.../<leg>.receipt.json` added line is exempt.

---

## F4 — MINOR (confirmed): hypothesis): `--build` required on the sequencer erodes an existing test's intent while keeping it green

**Location:** §4 "Label" ("`bench.p426_wave1` requires it [o1]"); §4 ("Under `s` ... the existing tests pass unchanged"); code `benchmark/bench/tests/test_p426_wave1.py:182–188`.

**Evidence (confirmed):**
- `test_main_refuses_a_workdir_that_is_not_stack_workdir` calls `W.main([...])` without `--build` and asserts `rc == 2`:
  ```
  182:188:benchmark/bench/tests/test_p426_wave1.py
  def test_main_refuses_a_workdir_that_is_not_stack_workdir(tmp_path, monkeypatch):
      monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "elsewhere"))
      rc = W.main(["--stack-root", str(tmp_path), "--main-root", str(tmp_path / "main"), "--workdir", str(tmp_path), "--registry-on", str(tmp_path / "on.yaml"),
                   "--out", str(tmp_path / "out")])
      assert rc == 2
  ```
  If `--build` becomes `required=True`, argparse exits 2 on the missing flag before the `STACK_WORKDIR` check runs. The assertion still holds (rc 2) but the test no longer exercises the workdir refusal.

**Problem:** "The existing tests pass unchanged" is literally true but misleading — coverage of the workdir guard silently moves to argparse. A later refactor that makes `--build` optional would let this test pass without the guard it claims to test.

**Failure scenario:** Not a runtime failure; a coverage regression that the spec's "pass unchanged" wording hides.

**Proposed change:** Either keep `--build` required and update this one test to pass `--build s` (then it still asserts the workdir refusal), or state in §6 that this test is amended to add `--build s` while keeping its assertion. Clarify that "existing tests pass unchanged" means "tests that exercise `s` behavior," not "every existing test's argv is untouched."

---

## F5 — MINOR (hypothesis): the frozen‑record head field is named per‑arm under `b` but `pin_problems` / `PIN_KEYS` are not directed to select by arm

**Location:** §4 "The frozen record under `b`" ("both heads (`stack_head_off`, `stack_head_on`) ... Every K2 check compares the live state with it at leg entry and exit"); code `benchmark/bench/p426_leg.py:296–303` (`PIN_KEYS`, `pin_problems`).

**Evidence (confirmed):**
- `PIN_KEYS = ("stack_head", "stack_clean", "mlx_vlm", "mlx_serve", "frozen_sha")` and `pin_problems` compares `state.get("stack_head")` to `pins.get("stack_head")`. Under `b`, the record has `stack_head_off`/`stack_head_on`, not `stack_head`. The spec does not say how `pin_problems` selects the head per arm (OFF → `stack_head_off`, ON → `stack_head_on`), nor how `repo_state` is taken from the leg's own arm worktree rather than a single `--stack-root`.

**Problem:** An implementer following §4 literally knows the leg "runs from its arm's worktree" but the K2 field selection and the `repo_state` root are left to inference. A wrong guess (e.g. always compare `stack_head` which is absent under `b`) refuses every leg NOT_STARTED.

**Failure scenario:** Implementer keeps `PIN_KEYS` as is; under `s2`, `state.get("stack_head")` is `None` and `pins.get("stack_head")` is `None` → `None == None` passes the head check vacuously, so a wrong worktree HEAD would NOT be refused — the opposite of the spec's "both heads equal to the record before the first leg."

**Proposed change:** Spell out in §4: under `b`, `pin_problems` compares the live head of the leg's arm worktree against `stack_head_off` (OFF) / `stack_head_on` (ON), and `repo_state` reads from the arm worktree selected by `--stack-root-off` / `--stack-root-on`. Add the §6 test that an ON leg against a `WT_on` whose HEAD differs from `stack_head_on` refuses NOT_STARTED.

---

## Scope requests (no severity)

- **S1:** The spec's §3 [o1] local‑gate paragraph and §4 [o1] naming‑exemption sentence are the only places that direct edits to `local_gate.py` and `modelnames.py`. Both are phrased as descriptions of behavior. Consider adding a short "Stack code changes" list in §3 naming the files (`bench.local_gate`, `bench.modelnames`, `bench.p426_wave1`, `bench.p426_leg`, `bench.p426_panel`) so an implementer does not have to infer which files the [o1] properties touch.

---

Nothing else of substance: the `s` byte‑identity claim is otherwise consistent with the existing sequencer/leg/harvest tests (the `--build`‑only‑when‑not‑`s` rule keeps `leg_argv` green under `test_leg_argv_is_exact`), the `--out` `.build` marker is correctly scoped to `b ≠ s`, the isolation/resume rules are per‑label and do not touch `s` paths, and the panel tune change (`p426<b>-off`/`p426<b>-on`) leaves `OFF_TUNE`/`ON_TUNE` unchanged under `s`.
