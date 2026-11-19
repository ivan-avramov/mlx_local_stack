# M76 B4b-2 — the A8 (tg2) consumers: B8, signals, panel (spec v1.3, 2026-11-19; r1 + r2 applied, ledgers L1–L18, M1–M12; C368)

Parent: `docs/specs/m76-b4b-tg2-runner.md` (B4b-1), `docs/specs/m76-tq4-certification.md` §A8 / §Panel / §Noise floor,
`docs/specs/m76-b7-statistics.md`, PLAN M83. Four-eyes STRICT (design review, change review, verify; panel Sol + GLM + Claude Sonnet;
a fresh blind test-writer, not the implementer's model). Implementation and every pytest run start only after the A8 decider's
sequencer exits (S27-P8). Ledger: `docs/reviews/m76-b4b2/design-ledger-r1.md`.

## 1. Goal

From the harvested A8 records (`benchmark/results/m76/wave2.tg2/` on `main`, objects on `evidence`) plus recorded inputs — the
pinned polyglot checkout (`kv-export --polyglot-root`, as A7), the pinned tg2 draw (`benchmark/m65/tg2_draw.json`, sha =
`v8.tg2_draw_sha256` = `schedules.TG2_DRAW_SHA256`), the evidence ref (`--evidence-ref`, for events and final-tree objects), the
grader image (`v8.tg2_image_id`) and the sealed launch-latency record (§4.2) — build a separate B8 record
`B8-A8.json`, the A8 section and flags of the signals sheet, and the A8 panel members, read by B7's pre-registered A8 plan. A
defect found here is regraded, never rerun. `B8.json` is byte-identical in every state; with no A8 record the signals sheet and the
frozen stage-3 panel are byte-identical too (§7).

## 2. Settled constraints (operator rulings; not reopened)

- C338 / C336 / C339: the decider always runs; A8 = `m76_rule.axis_verdict("A8", …)`: α* 0.001 (`alpha_star_fixed`), unit items, 80
  items (20 per language × rust / javascript / java / cpp), 2 sessions, one look; HOLD = any language's point estimate < −20 pp
  (`m76_rule.a8_hold`), blocking.
- Outcome = `acc_strict@budget`: 1 iff `passed is True and converged is True`; a `p426_dnf` slot = 0.
- Panel: A8 sessions join the subjective Holm family (A1, A2, A3, A4, A5, A7 sessions, A8 sessions); < 5 judged items → reported, not
  tested; Holm-adjusted p < .05 favouring N16 → flag; judges per `judges.json`; both orders; a judge context never holds both orders
  of one item (S26-P18).
- C362 leak rule: a leak reveals the ARM or the BOX; model-family tokens and generic paths are answer content.
- Noise floor (S22-P9), walls within the pair only (S27-P5), C365 residual (no runner edit), C366 positives (an input, unchanged).
- L9: every new call that grades or validates a tg2 report passes `grader="tg2"`. L16: `row_scores` passes tg2 rows through unchanged.

## 3. B8 (`bench/p426_verify.py`)

1. **Axis table.** `KV_AXES = {"A7": dict(namespace="wave2", corpus="tg1", attempt_re=^tg1-m76-(n16|x|v)-(pilot|s1|s2|s3|reload)\.a\d+$,
   worktrees=m76-f45|m76-q), "A8": dict(namespace="wave2.tg2", corpus="tg2", attempt_re=^tg2-m76-(n16|x)-(pilot|s1|s2|reload)\.a\d+$,
   worktrees=m76-g2)}`. The namespace is passed explicitly to `_kv_load_attempt`, `harvest_manifests`, `pair_keys`,
   `_supersede_reasons`, the dossier reader and `verify_all_kv`'s existence check; `_kv_path_re` (foreign-worktree guard) takes the axis'
   worktree prefix. `_harvest_reasons_kv` and `_sequence_*` stay unchanged (namespace-free). A7 calls pass "wave2" (outputs unchanged).
2. **`verify_a8_kv(results_root) → B8-A8 document`.** Built only when `m76/wave2.tg2/run` exists AND v8's pair is `fz.TG2_PAIR`
   (`(n16, x)`), `v8.lever == "kv"`, `v8.corpus == "tg2"`. Confirmatory sessions `kv_a8_sessions()` (from `m76_rule.axis_plan("A8")`;
   `("s1", "s2")` today), diagnostic `("pilot", "reload")`. Per session the A7 rules (leg state / self-hash, commits = v8, HARVEST main
   under `benchmark/results/m76/`, the dossier PASS with only `kv_difference_problems`-allowed differences, provenance per
   `runtime.lang`, equal plan shas, equal seeds, the S26-P15 / P15b supersede rules). A session without its pair record or its harvested
   legs is `status: incomplete` with its reasons (the decider may be mid-run or stopped); only corrupted or contradictory records
   refuse. Output keys = A7's plus `corpus: "tg2"`, `status`, `recheck` (§5), `latency` (§4.2), `base_b8_sha256` (the sha of the
   `B8.json` it accompanies) and `inputs` (every file read, with its sha).
3. **Final-tree identity, per row, fail-closed (both axes).** For every non-DNF row: `final_tree.manifest` (a path) and
   `final_tree.manifest_sha256` present; exactly one HARVEST destination-main final-tree manifest for that row's run id and item; its
   `published_sha256` equal to the row's. A missing block, no match, or several matches → a REASON (the session is rejected), never
   `identical: false` with null shas; a published manifest for an item that has a row in that attempt but names another run id is
   an orphan → a REASON, unless the chain records that run id as a discarded DNF / rerun slot. DNF slots are exempt; an all-DNF
   attempt passes.
   A7's committed `B8.json` has no null manifest sha (unchanged).
4. **Provenance.** `kv_a7_normalise` / `kv_a7_provenance_reasons` become corpus-neutral (`kv_normalise`, A7 aliases kept). A key may
   differ between arms only if it is per-invocation (already normalised) or already in the documented KV-mode allowance; any other
   difference rejects. Tests on the real tg2 pilot manifests assert pass and that no tg2-only key is allowed.
5. `B8.json` (`verify_all_kv`) never includes A8. The CLI writes `B8-A8.json` beside it when §3.2 applies.
6. **Plan binding (C368 S1).** Per A8 attempt: `schedules.check_tg2_p426` on its `schedule.json` against the pinned draw for that
   session (its `TransportAbort` caught → a REASON); `chain.tg2_leg == session`; `chain.frozen_record.sha256 == v8.sha256`;
   `v8.arms == ["n16", "x"]`; the reload's key set = the first 5 items per language of s1 (C368 S2). Any mismatch rejects the session.
   A harvested attempt missing its `schedule.json` or `chain.json` is contradictory → refuse (a missing attempt is `incomplete`).
7. **Javascript lock-file regrade (C368 (1), S27-P10).** The tamper receipt records no reasons, so eligibility is proven from the
   HARVEST-bound events or the row stays `tampered`. One pure function `a8_regrade_eligibility(row, events, final_manifest, entry)`
   (shared by the regrade tool and B8-A8) returns `eligible` or `stays_tampered` with the failed condition:
   a. every `write` / `edit` / `patch` tool path (normalised work-relative) is a path of the B8-verified final-tree manifest (the
      accepted files);
   b. every shell call parses (`shlex`, punctuation chars) into simple commands joined only by `&&`, `||`, `;`, `|`, with no `$(`,
      backtick, heredoc, subshell, variable or assignment, and redirections only `>/dev/null`, `2>/dev/null`, `2>&1`; each simple
      command is one of: `cd <path inside the work tree>`; `ls`, `cat`, `head`, `tail`, `wc`, `grep`, `echo` (no redirection to a file);
      `node <accepted file>`; `npx jest` / `npm test` without `-u`, `--updateSnapshot`, `--ci=false` or extra script arguments; and
      the bare install `npm install` / `npm i` / `npm ci` with flags only (no positional package);
   c. at least one shell call is such a bare install (the lock file's cause).
   Anything outside (b) → `stays_tampered` (listed, never regraded). An eligible row is regraded: the materialised prepared tree +
   the accepted files (the set from the B8-verified final-tree manifest on `main`; each file's bytes from its `objects/<sha>` blob on
   the evidence ref) → `tg2_grade.grade_item` in the pinned grader image (`grader="tg2"` validation, L9), on a quiet box after the
   decider. A non-scored regrade outcome (timeout, transport, image error) aborts the regrade tool; it is never a grade. The tool
   writes, for EVERY final-`tampered` javascript row, `wave2.tg2/regrade/<attempt>/<lang>__<item>.json` (sealed with `ph.seal`:
   input shas, the eligibility result and facts, and for eligible rows the grade report and `regraded_passed`; `converged` is the
   row's), committed on `main`. B8-A8 enumerates the final-`tampered` javascript rows (`grade_reports[-1]` final, outcome
   `tampered`), requires exactly one sealed record per row (else the session is `incomplete`), re-derives eligibility from the events
   on the evidence ref with the same function (a mismatch refuses), and binds every record's sha in `inputs`. **Effective passed:**
   one accessor `a8_passed(row, regrade)` = `regraded_passed` for eligible rows, else the row's `passed` — used by signals, B8-A8
   counts, panel selection and packets alike. The sheet prints per arm: final-`tampered` javascript rows, eligible, regraded to
   passed, stays-tampered (each listed with its failed condition).

## 4. Signals (`bench/p426_signals.py`)

1. **`_kv_a8_section(b8_a8)`**: `status` must be complete with every confirmatory session accepted and equal key sets, else the axis
   is "incomplete" (no verdict); `{item: {session: 0/1}}` per arm by `_strict`; the verdict ONLY from
   `m76_rule.axis_verdict("A8", look=1, test, ref, languages={item: lang})`, the language from the id prefix (outside `TG2_LANGS` →
   refuse).
2. **Descriptive beside the verdict:** per-language `m76_rule.loss_bound` at `PER_SESSION_ALPHA` (0.025; labelled descriptive,
   unadjusted, no verdict); the HOLD line (exact point estimates); the paired session delta and per-session estimates (as A7); the
   session-interaction flag; the noise floor (N16 s1 vs s2 discordance; X vs N16); the reload control — X reload vs X s1 and N16 reload
   vs N16 s1 on the 20 shared items with per-item equal `sampler_seed` asserted (else the control prints "refused: seeds differ"), and
   X vs N16 within reload; decode (`_speed` over `items[].totals`); per-language walls within the pair; the launch-latency summary per
   leg window from `B8-A8.latency` — `wave2.tg2/run/exec_latency.json` (rows `{t, fresh_ms, repeat_ms, true_ms, threatlocker_cpu}`
   over the campaign, sealed with `ph.seal`, published by the designer after the decider; its sha in `B8-A8.inputs`); absent →
   `latency: incomplete` (descriptive only; never a refusal).
4. **Inputs:** `compute_kv(b8, b8_sha256, b8_a8=None, b8_a8_sha256=None)`; with `b8_a8` the signals verify
   `b8_a8.base_b8_sha256 == b8_sha256` and re-hash every `b8_a8.inputs` file (as `_kv_check_b8_inputs` does for B8); a mismatch
   refuses.
3. **Flags:** `kv_flags` gains A8 (LOSS, UNDECIDED, size warnings, `session_interaction`) and a `hold` flag (`blocking=True`) from
   `final["hold"]`; `render_kv`'s decode loop gets an explicit A8 case; heading "## A8 tg2" after A7. With no `B8-A8.json` the sheet is
   byte-identical (A8 omitted, never "pending").

## 5. Re-check labels

B8-A8 reads `run/recheck-s1.json` and `run/recheck-s2.json` and checks each with the sequencer's own `check_recheck_doc` against
B8-A8's selected attempts (gate, axis, sessions, ref, test, attempts), the seal, the sha recorded in `sequence.json`, the simulation
report sha, and for s1 the ack rule (`not inside or operator_review` → `rechecks.s1.ack` present). `check_recheck_doc` is a sequencer
method: B8-A8 re-implements the same field comparison (no runner edit), tested against the sequencer's own sealed document shape.
Required for s1 and s2 only (pilot and reload have none); a missing `recheck-s2` (sealed after the reload leg) makes only the
re-check label `incomplete`. The sheet labels each as the runner's interim re-check (descriptive, never a verdict).

## 6. Panel (`bench/p426_panel.py`)

1. **Members.** `kv_members(sessions=None, a8_sessions=None)`: `A8-<s>` for each accepted confirmatory session; every caller
   (`kv_export`, `kv_panel_members`, `kv_expected_members`, `kv_panel_completeness`, `kv_panel_family`) passes `a8_sessions` from
   `B8-A8.json` when present, None otherwise (unchanged output). `kv_rubric("A8-…") = "code"`. `KV_INPUT_SOURCE["A8"]`,
   `kv_a8_context(b8_a8)` (the A7 analogue). A8 members are frozen against `B8-A8.json`'s sha; A1–A7 stay bound to `B8.json`;
   ingestion checks each member against its own record; the panel, like the signals, verifies `b8_a8.base_b8_sha256` and B8-A8's
   inputs before using it.
2. **Packet `_a8_packet`** (never `_StartTree`): selection as A7 with the effective `a8_passed` (§3.7) (both arms pass; identical
   final-tree manifests count 0.5, not judged). Task text = the runner's prompt (`corpus_tg2.prompt`, E1, incl. the helper sentence H, no inject addendum) rebuilt from the
   pinned polyglot root (its sha = the universe's `polyglot_sha`; each blob against `inputs_sha256`) and required equal to the first
   user message of the HARVEST-bound evidence export (else refuse; checked on the pilot export before the freeze). Final-tree reads
   use the `wave2.tg2` namespace (`benchmark/results/m76/wave2.tg2/<att>/evidence/<run>/…`). Start tree =
   `tg2_materialize.prepare_tree` from the same root, hashed against `prepared`. Final tree: the manifest from `main` (B8-verified),
   objects and events from the evidence ref, each bound by HARVEST and the row. Diff = every new or changed file. The final tree is the
   grader's `accepted_files`: assert that no path in `structured_grade.protected_manifest(prepared, solutions)` other than a Rust
   `Cargo.toml` is new or changed (else refuse); a changed `Cargo.toml` is diffed as content (the grader accepted it). Non-UTF-8 files:
   listed by path and size. Tool counts as A7.
3. **Leak check:** C362's KV list + registry names + the box identity + template tags. A hit refuses that member's export and is
   reported per item with the pattern name only; the designer takes it to the operator (no exclusion, no redaction).
4. **Holm:** the family over all members with a frozen record (A1–A7 against `B8.json`, A8 against `B8-A8.json`); raw A1–A7
   statistics unchanged, adjusted p recomputed.

## 7. Acceptance (pre-registered)

1. With no `B8-A8.json`: `B8.json`, `SIGNALS.md`, `SIGNALS-partial.md` regenerate byte-identically from `main`'s inputs.
2. With `B8-A8.json`: `B8.json` byte-identical; the sheet's A1–A7 sections and raw panel statistics identical; only the A8 section,
   the header shas / counts, the flags and the Holm-adjusted column may differ — tested as that projection.
3. On the real harvested pilot pair (decider absent): `B8-A8.json` builds with the pilot accepted, s1 / s2 `incomplete`, final-tree
   identities matched (no null sha), provenance passing; the prompt check passes on the pilot export.
4. Red tests first (blind test-writer): the per-row final-tree rule (missing block, no match, two matches, orphan, all-DNF) on both
   axes; A8 names / namespace / worktree guard; a partial decider → incomplete, not a refusal; HOLD (a language at −25 pp → `hold`
   blocking); DNF = 0; the re-check binding (a superseded attempt, a missing ack); the reload seed assert; the prompt check; the
   protected-path assertion incl. a grader-accepted `Cargo.toml`; the leak refusal; the A7 / no-A8 goldens.
5. After the decider, in order: publish `run/exec_latency.json`; the javascript regrade tool (§3.7); B8-A8 → signals → panel export
   on the real records (regrade only, never a rerun).
6. Regrade eligibility tests on real-shaped events: the pilot's two commands → eligible; `npm install lodash` → stays tampered;
   a write to `babel.config.js` → stays; `echo x > package.json` → stays; `npx jest -u` → stays; an eligible row with no regrade
   record → `incomplete`; a record whose re-derived eligibility differs → refuse; the effective-passed accessor in panel selection.

## 8. Out of scope

Runner / sequencer / probe changes (B4b-1, frozen identity); the C365 race; the positives rule (C366); stage 4 (V); tg1 changes
beyond §3.3; the forward lock-file fix in the tg2 view (C368 (1): a separate change after the decider).
