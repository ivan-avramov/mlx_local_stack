# P426 T3 — strict verify of the candidate (change review, round 1 of 3) — dispositions

Candidate `impl-1` (B0 `1a4187e6` + spec v2.1 → scratch `b3fd6073`). Panel 2026-10-27 23:04–23:08Z, context `checkout` (read-only
copy of the candidate with the frozen set installed, the candidate diff, B0's merge diff, both reports, the S′ fork). Fresh sessions:
cursor-agent cannot continue the design-round sessions. Brief: `change-verify.prompt.md` (it was passed on the command line, as
cursor-agent requires; it contains none of `chain_ops.BUSY`, so the running rehearsal's census was unaffected — P454).

| Member | Runtime | Model | Session | Status |
|---|---|---|---|---|
| sol | cursor-agent `--mode ask` (user instructions unconfirmed) | `gpt-5.6-sol-high` | unreported | returned (2 findings; per-finding resolved list omitted) |
| glm | cursor-agent `--mode ask` (user instructions unconfirmed) | `glm-5.2-high` | unreported | returned (R1 / R2 ledger + B1–B6) |

Claude Sonnet sat out (the T3 implementer). Design findings resolved per glm's ledger, checked by the designer against the source:
all R1 / R2 adopted findings resolved except R2-4 (patch-level restore, below) and R2-7 (the existing test's `--build s`, below).

| # | Finding (raised by) | Disposition | Why |
|---|---|---|---|
| V1 | Seeding-test restore check not patch-exact: comment lines ignored, any ≤ 2 added lines with `joint_v1` / `registry` accepted (sol P1, glm B1, test-writer F1) | **adopted, adapted**: compare whole files with expected bytes derived from OFF | Confirmed `p426_plan.py:240–249`. C218 / R2-4 require exactly the restore. Simpler than hunk matching: expected ON seeding test = OFF with the pinned §11 replacement block, byte-equal (P511: the exact reverse of C177's seeding hunk, `78a730fe` — the two C177 comment lines and the `per_query` assertion → the two original assertions `== "joint_v1"` / `mtp_verify_scan_source == "registry"`). Original. |
| V2 | Registry restore check looser than exact: trailing comments stripped, sorted not positional, any number / placement of notes (glm B2, test-writer F2) | **adopted, adapted**: expected ON registry = the fork's `registry_states.overlay_on(OFF)` (the B4 rule, from the OFF worktree's `src/mlx-vlm`) + exactly one `# PROVISIONAL P426` line as the first child of the entry's `generation_defaults:` (P511: one line, `generation_defaults` child indentation, `# PROVISIONAL P426` then free text), byte-equal otherwise | Same protection as V1; reuses the rule the plan already cross-checks (§2 Arms). Original. |
| V3 | `new_side.py` exception compares the lock sha with itself — vacuous (glm B3, test-writer F3) | **adopted** (lead rec P507): accept only the pinned pair `ecd97da3…` → the committed S′ bench-lock sha; docstring names the exception; operator ask at Accept | Confirmed. Regenerating the goldens is not their procedure: they capture the P371 baseline side. Introduced by the candidate. |
| V4 | `venv_versions` nondeterministic with two dist-infos of one package (glm B4, test-writer F5) | **adopted, adapted**: two dist-infos of a checked package → the venv check fails (refuse / invalidate) | Fail closed; a fresh `uv pip sync` never leaves two, so a correct run is unaffected. Introduced. |
| V5 | Plan §2 still states S-era instructions as active (one serving build S, the S worktree, overlay arms, M1 `<S's fork sha>`) beside the new S′ bullet (sol P2) | **adopted, adapted**: mark the S-era bullets and the M1 row as Wave 1 on S (superseded), pointing to the R11 S′ bullet; the M1 row names the label's reviewed head and labelled out dir | Confirmed `p426-fable-mtp-recert.md:32–45, 93`. An operator following the old Arms bullet builds an overlay arm the S′ sequencer refuses. Original (spec §5 under-specified it). |
| V6 | R2-7 not landed: `test_main_refuses_a_workdir_that_is_not_stack_workdir` lacks `--build s` (glm B6, implementer report) | **adopted**: that one existing test gains `--build s` and keeps its assertion | Spec §4 [r2] directs it; the fix-round brief names the file. Original. |
| V7 | `claim_out` writes `.build` before the record is validated (glm B5, test-writer F6) | **declined** (residual) | No consequence: the marker names the same label, a rerun is allowed, no S byte is involved. |
| — | F4 bench-lock consistency (test-writer) | **closed by measurement** | Designer: `uv pip check` on a fresh `.venv-bench` — no new conflicts, two removed, seven pre-existing bench-tool conflicts. |
