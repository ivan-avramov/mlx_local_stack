# Round 2 (verify) — review of spec v1.2

I am GLM; I read `your-r1-opinion-glm.md` (my r1) and the v1.1→v1.2 diff, traced the code and the harvested pilot records. Read-only; no files changed.

## Resolution of my round-1 findings

- **F1 (blocker, Holm re-adjustment breaks the "only A8 added" golden): RESOLVED.** L8 rewrote §6.4 + §7.2: A1–A7 raw statistics stay identical, Holm-adjusted p are recomputed over the family incl. A8, and the golden is the projection (A8 section, header shas/counts, flags, Holm column may differ). `kv_panel_family`/`stats.holm` semantics (`p426_signals.py:1507,1591`) match; the projection is testable.
- **F2 (major, protected set underspecified → silent accept of build-file edits): RESOLVED.** L11/§6.2 now asserts no path in `structured_grade.protected_manifest(prepared, solutions)` other than a grader-accepted `Cargo.toml` is new/changed. `protected_manifest` (`structured_grade.py:90`) is `{p: h for p,h in prepared if p not in solutions and not p.startswith(".docs/")}` — tests + all build/scaffold files. Confirmed.
- **F3 (major, reload control not same-seed for s2): RESOLVED.** L9/§4.2 now reads "X reload vs X s1 and N16 reload vs N16 s1 on the 20 shared items with per-item equal `sampler_seed` asserted (else 'refused: seeds differ')… no s2". Matches `TG2_P426_LEGS` (`schedules.py:57-61`: reload/s1 seed 1001, s2 seed 2002).
- **F4 (major, Cargo.toml exception diverges from grader): RESOLVED.** L11/§6.2 reuses the grader: the final tree is `accepted_files` (`corpus_tg2.py:370-393`), so a protected file the grader rejected never enters; a changed `Cargo.toml` is diffed as content (grader accepted it via `cargo_manifest_reasons`, `tg2_grade.py:262`). No second rule.
- **F5 (minor, parameterisation list wrong): RESOLVED.** L12/§3.1 now lists `_kv_load_attempt`, `harvest_manifests`, `pair_keys`, `_supersede_reasons`, the dossier reader, `verify_all_kv`'s existence check, and `_kv_path_re` (worktree prefix); `_harvest_reasons_kv` and `_sequence_*` stay namespace-free. Matches the code (`p426_verify.py:2201,500,565` are namespace-free).
- **F6 (minor, A8 sessions hardcoded): RESOLVED.** L13/§3.2 `kv_a8_sessions()` from `m76_rule.axis_plan("A8")`.
- **F7 (minor, re-check ambiguity for pilot/reload): RESOLVED.** L7/§5 "Required for s1 and s2 only (pilot and reload have none)."
- **F8 (minor, `kv_members` signature unspecified): RESOLVED.** L14/§6.1 `kv_members(sessions=None, a8_sessions=None)`; every caller passes `a8_sessions` from `B8-A8.json` when present, None otherwise.
- **F9 (scope request, provenance "legitimately differs" undefined): RESOLVED.** L15/§3.4 "per-invocation (already normalised) or already in the documented KV-mode allowance; any other difference rejects. Tests … assert … no tg2-only key is allowed."
- **Q1–Q5:** all RESOLVED per the ledger (L5 per-row §3.3 for A7 too; L9 drop s2; L3/§6.2 include H; L11 reuse grader; L5/L11 keep 0.5 for identical multi-file manifests).

All nine findings and five questions are resolved; v1.2 implements the dispositions soundly on those points.

## New findings from the v1.1→v1.2 diff (§3.6 / §3.7 + ledger ref)

**N1 — Major — §3.7 eligibility (a) lets `npm install <pkg>` through, contradicting C368 (1)'s "shell-only protected-path edits stay tampered and are listed".**
- Location: §3.7 (a) "a package-manager install (`npm install` / `npm i` / `npm ci`) in a shell call", (c) "no shell call whose command names such a path except as an argument to a read-only or test-runner command".
- Evidence: confirmed. The events carry shell commands as `part.state.input.command` strings (traced in `tg1` events on `origin/evidence`: `{"tool":"shell","state":{"input":{"command":"…"}}}`). `protected_manifest(prepared, solutions)` (`structured_grade.py:90`) includes `package.json` for javascript items (it is in `prepared`, not in `solutions`, not under `.docs/`). `tg2_grade.tamper_reasons` (`tg2_grade.py:958-989`) flags any protected file whose hash differs, so an `npm install <pkg>` that adds a dependency → `package.json` changed → grade `tampered`. Criterion (a) is satisfied by any token sequence beginning `npm install`/`npm i`/`npm ci` (the wording does not exclude a positional package argument). Criterion (c) only catches a shell call that *names a protected path as an argument*; `npm install <pkg>` names `<pkg>`, not `package.json` (the edit is a side effect), so (c) does not catch it. (b) only covers `write`/`edit`/`patch` *tool* calls, not shell side effects. So an `npm install <pkg>` row passes (a)(b)(c) and is deemed eligible.
- Problem: the regrade then runs `tg2_grade.grade_item` on the materialised prepared tree + the final tree's `accepted_files` (`corpus_tg2.py:370-393`). `accepted_files` excludes every changed protected file other than a grader-accepted Rust `Cargo.toml`, so the changed `package.json` is dropped and the regrade tree carries the *prepared* `package.json`. `tamper_reasons` passes (protected files match prepared); the tests run; if the model's solution does not depend on the added dep, the regrade flips `tampered` → `passed=True`. C368 (1) explicitly rules that "shell-only protected-path edits stay tampered and are listed" — `npm install <pkg>` is exactly such an edit.
- Failure scenario: a both-arm javascript item where the agent runs `npm install <pkg>` to add a helper dependency; the in-run grade is `tampered` (package.json + package-lock.json changed); the row is marked eligible, regraded on the prepared tree, tests pass without the dep, `passed` flips to True; the A8 readout scores the item and the HOLD sees javascript — the ruling's "stay tampered and are listed" protection is silently lost.
- Proposed change: restrict (a) to an install with **no positional package argument** — `npm install`/`npm i`/`npm ci` followed only by flags (the install target is the existing `package.json`). Equivalently add a criterion: an `npm install`/`npm i`/`npm ci` with a positional non-flag token fails eligibility (it edits `package.json`). Add a red test: a both-pass javascript row whose agent ran `npm install <some-crate>` stays `tampered` and is listed, not regraded.

**N2 — Major — §3.7 (c) "names such a path" is fragile to shell parsing; the spec gives no parser, so shell-only protected-path edits via redirects/pipes/heredocs slip through.**
- Location: §3.7 (c).
- Evidence: confirmed (hypothesis on the implementer's parser). The events store the raw command string. (c) says "no shell call whose command names such a path except as an argument to a read-only or test-runner command (`cat`, `head`, `tail`, `ls`, `npx jest`, `npm test`)". A naive argv-token parser misses `echo … > package.json` (redirect target, not an argument), `sed … | tee package.json`, `cat <<EOF > babel.config.js`, `$(printf … > package.json)` in a subshell, and `npm install <pkg>` (N1). The spec does not define what "names" means, whether redirect targets count, how to tokenise, or how to handle env-var expansion.
- Problem: the ruling's protection ("shell-only protected-path edits stay tampered and are listed") depends entirely on (c); an implementer who tokenises argv only will accept rows that edited a protected file via a redirect/pipe. The same regrade path as N1 then flips them to `passed`.
- Failure scenario: an agent runs `echo '{"type":"module"}' > package.json` (or `sed -i.bak 's/…/' package.json` where the path is a redirect target of a `tee`); the row is `tampered`; (c) as naively implemented sees no protected path in argv position to a non-allowlisted command → eligible → regraded → flipped. The ruling is contradicted and the two implementers diverge.
- Proposed change: specify the parser conservatively — a shell call is ineligible if any protected path appears anywhere in the command (argv tokens, redirect targets, heredoc bodies, command substitutions), except as an explicit argument to one of the allowlisted read-only/test-runner commands; AND any `npm install`/`npm i`/`npm ci` with a positional package token is ineligible (N1). Require the red test to plant a redirect/pipe edit on `package.json` and assert it stays `tampered`.

**N3 — Minor — §3.7 conflates the final-tree manifest (on `main`) with the objects (on `evidence`).**
- Location: §3.7 "the materialised prepared tree + its final tree's accepted files (from the evidence ref)".
- Evidence: confirmed. `accepted_files` is the list derived from the final-tree `manifest.json` (`files: {rel: sha}`, `missing`), which §3.3 binds on `main`; the file *contents* are the `objects/<sha>` blobs on `evidence` (per HARVEST: `destination: main` for the manifest, `destination: evidence` for objects). The wording "accepted files (from the evidence ref)" reads as if the list itself comes from evidence.
- Problem: an implementer could look for the accepted-files list on the evidence ref and refuse when it is absent there (it is on `main`).
- Proposed change: "the accepted-files set is read from the B8-verified final-tree `manifest.json` on `main`; each file's bytes are fetched from the matching `objects/<sha>` blob on the `evidence` ref."

**N4 — Minor — §3.7 "`passed` / `converged` unchanged from the row except `passed`" is self-contradictory on its face.**
- Location: §3.7 regrade record fields.
- Evidence: confirmed (wording). The regrade recomputes `passed` from the re-run; `converged` cannot be recomputed (the agent is not re-run) and is taken from the row. The sentence as written says both are unchanged except `passed`, which is unreadable.
- Proposed change: "`converged` is copied from the row; `passed` is the regrade's value (potentially flipped from the row's `tampered` → `False`)."

**N5 — Minor — §3.7 "print both counts (in-run tampered vs regraded) per arm" does not define the regraded count.**
- Location: §3.7 last sentence.
- Evidence: confirmed (wording). "Both counts" is ambiguous: regraded = number of eligible rows, or number that flipped to `passed`? The operator needs the latter to read the axis.
- Proposed change: "per arm, the in-run `tampered` count and the regraded-`passed` count (eligible rows whose regrade flipped `passed` to True), with the eligible-but-not-flipped rows listed."

**N6 — Minor — §1 undercounts the recorded inputs; the pinned draw is a third.**
- Location: §1 ("plus two recorded inputs — the pinned polyglot checkout … and the sealed launch-latency record") vs §3.6 ("`schedules.check_tg2_p426` on its `schedule.json` against the pinned draw").
- Evidence: confirmed. `check_tg2_p426(schedule, draw_doc, leg)` (`schedules.py:416`) requires `draw_doc`; the pinned draw is `benchmark/m65/tg2_draw.json`, pinned by `TG2_DRAW_SHA256` (`schedules.py:53`) and by `v8_base.json`'s `tg2_draw_sha256`. B8 must read and hash it; §3.2's `inputs` ("every file read, with its sha") would capture it, but §1's prose names only two inputs.
- Problem: minor — an implementer reading §1 alone might not add the draw to `B8-A8.inputs`, weakening the provenance binding; the §3.2 catch-all covers it, but the §1 list is misleading.
- Proposed change: add the pinned draw (`benchmark/m65/tg2_draw.json`, sha = `v8.tg2_draw_sha256` = `schedules.TG2_DRAW_SHA256`) to §1's recorded inputs, or state in §3.6 that the draw is read from `main`, hashed, and bound in `B8-A8.inputs`.

**N7 — Minor — §3.6 leaves a missing `schedule.json` for a harvested attempt unclassified (incomplete vs refuse).**
- Location: §3.6 "Per A8 attempt: `schedules.check_tg2_p426` on its `schedule.json` … Any mismatch rejects the session" vs §3.2 "A session without its pair record or its harvested legs is `status: incomplete` … only corrupted or contradictory records refuse."
- Evidence: confirmed (wording). §3.6 covers *mismatches* (refuse) but not a *missing* `schedule.json` for an attempt that is otherwise harvested. §3.2 sends missing records to `incomplete`, but a harvested attempt with no schedule is corrupted, not merely incomplete.
- Problem: a partial decider that harvested an attempt but failed to commit its `schedule.json` would be labelled `incomplete` and silently omitted, when it is contradictory and should refuse.
- Proposed change: §3.6 should say a missing `schedule.json` (or `chain.json`) for a harvested attempt is a contradictory record and refuses the session, distinct from a missing *attempt* (incomplete).

---

The two majors (N1, N2) are the same root issue — the eligibility criteria do not robustly enforce C368 (1)'s "shell-only protected-path edits stay tampered and are listed" — and both must be fixed before the red tests in §7.4 ("the protected-path assertion incl. a grader-accepted `Cargo.toml`") can honestly cover the javascript regrade path. N3–N7 are minor wording/provenance gaps. Nothing else in the diff breaks an existing output or contradicts A7's guarantees.
