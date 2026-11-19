Of the 16 round-2 items, 13 are resolved, 2 are partly resolved (G1, G4) and 1 is a literal mismatch (G7). The v1.3 regrade eligibility (§3.7) still has gaps. I found 1 major defect and 3 minor ones. I could only read files, so none of this was run.

I could not check §3.7 against the pilot's real javascript events. They are only on the evidence branch, which is not in this checkout (HARVEST lists `javascript__word-search.events.jsonl` as destination "evidence"). What I could read:
- The row (`word-search.js` is the only accepted final-tree file).
- The grade sequence: `parsed`, `parsed`, then a final `tampered`.
- `test_modified: true`, which is what a tamper receipt requires (`structured_grade.py:513`).
- Six tool_use events.
- S27-P10's own wording, "`npm install … && npx jest`", which elides the arguments.

## Round-2 status

| Round-2 finding | Status | Why |
|---|---|---|
| G1 eligibility cannot prove the cause | Partly resolved | Closed shell grammar, bare install, tool paths limited to accepted files, and a `stays_tampered` default. The residual holes are H1–H3. |
| G2 regrade not re-derivable, silent missing record | Resolved | Sealed record for every final-tampered javascript row, enumeration from `grade_reports[-1]`, re-derivation on the evidence ref, abort on non-scored outcomes, order in §7.5, and the evidence ref and image added to §1 inputs. |
| G3 effective `passed` | Resolved | `a8_passed` is used by signals, counts, panel selection and packets. |
| G4 orphan rule | Partly resolved | Scoped to items that have a row and name another run id. The exempting chain field is unnamed (see H4). |
| G5 `check_recheck_doc` | Resolved | Re-implemented over the same fields, with a missing recheck-s2 degrading only the label. |
| G6 draw input | Resolved | `v8.tg2_draw_sha256` and `v8.tg2_image_id` exist in `v8_base.json`. `TransportAbort` is caught and `v8.arms` is checked. |
| G7 plumbing | Resolved with a literal mismatch | Base-sha and input re-hash, latency sealed and `incomplete` when absent, and the `wave2.tg2` stem are specified (see H4). |

## New findings

**H1. §3.7(b) — the test-runner clause is a denylist, so a real non-lock tamper can be classed eligible. Major, confirmed from the grammar and the tamper code.**
- **Problem:** `npx jest` / `npm test` are allowed "without `-u`, `--updateSnapshot`, `--ci=false` or extra script arguments". Any other jest flag passes. `npx jest --coverage` writes `coverage/` into the work root. `STRIP_TOP_LEVEL` strips only `build`, `target`, `node_modules` and `.gradle` (`tg2_grade.py:58`), and `_new_file_reason` accepts only a non-test `.js` helper beside the solution (`tg2_grade.py:946-949`). So `coverage/*` is a new file and the tree is tampered. Likewise `--json --outputFile=...`, `--cacheDirectory=...` and `--outputFile`.
- **Scenario:** A row where the agent ran `npm install && npx jest --coverage` is tampered because of `coverage/` plus the lock file. It satisfies (a), (b) and (c), is regraded on the accepted files alone, and flips to pass. That is not a lock-file-only case, which is what C368 (1) rules.
- **Change:** Make the runner clause an allowlist. Allow no arguments, or only an explicit set of read-only flags such as `--silent`, `--verbose`, `--runInBand` and `--no-cache`, plus at most a positional test path that is itself a prepared file. Add a red test: `npx jest --coverage` stays tampered.

**H2. §3.7(a) — the file-writing tools are an open list. Minor, hypothesis.**
- **Problem:** The condition names `write`, `edit` and `patch`. I could not see the carrier's full tool inventory (the carrier JSON lists permissions, not tools). Any other write-capable tool, for example a multi-edit or apply-patch variant, is unchecked.
- **Scenario:** A file written through an unnamed tool never reaches (a), so a real tamper is classed eligible.
- **Change:** Invert the rule. Allow only named read-only tools (`read`, `glob`, `grep`, `list`, `shell`, `webfetch`, todo-style) and treat any other tool name as `stays_tampered`.

**H3. §3.7(b) / §7.6 — the grammar may refuse the very case C368 exists for, and the pilot test is not anchored to a quoted command. Minor, hypothesis.**
- **Problem:**
  - Common benign forms fail (b): `CI=true npx jest` (assignment), `npx jest <file>` or `npm test -- --verbose` ("extra script arguments" is undefined), and `cd <abs work path>` when the evidence export is scrubbed (the work root and path normalisation are not named).
  - §7.6 asserts "the pilot's two commands → eligible" without quoting them, and S27-P10 elides the install's arguments.
- **Scenario:** If the pilot's `npm install` carried a positional package or a flag value, the pilot's own javascript item becomes `stays_tampered`. That contradicts C368's motivating case, and the javascript HOLD signal stays blind.
- **Change:**
  - Quote the pilot's exact command strings for both arms in the spec or test, and run the function against them before freezing.
  - Define "extra script arguments" explicitly.
  - Name how the work root is learned from the scrubbed events.
  - State that each command executes model-authored code (`node <file>`, jest, package scripts), so the allowlist is conservative evidence, not proof. Treat a documented residual as acceptable.

**H4. Literal mismatches in v1.3. Minor, confirmed.**
- `compute_kv(b8, b8_sha256, b8_a8=None, b8_a8_sha256=None)` in §4 omits the real parameters `rows_root`, `panel` and `partial` (`p426_signals.py:1607`). It should read `compute_kv(rows_root, b8, b8_sha256=None, panel=None, partial=False, b8_a8=None, b8_a8_sha256=None)`.
- §3.3 exempts a "discarded DNF / rerun slot" run id but does not name the chain field. Name `slot_attempts` dispositions and `seen_run_ids`.
- Item 4 ("Inputs") is placed before item 3 ("Flags") in §4.
- `ph.seal` has no definition in the spec. It is `p426_hooks.seal` (`p426_hooks.py:44`).
