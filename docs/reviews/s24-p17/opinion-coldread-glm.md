I have all the material read. Here are my findings.

---

**F1 — `benchmark/results/*.jsonl` exempts every `.jsonl` under `benchmark/results/`, not just result rows**
- Location: `piicheck.py:102` (`_MODEL_OUTPUT_HOME_EXEMPT_GLOBS` first entry); comment claim at `piicheck.py:98` ("result rows, opencode transcripts and final solution trees").
- Severity: minor.
- Evidence: confirmed. `fnmatch`'s `*` crosses `/` (the comment says so and it is correct — see F3), so `benchmark/results/*.jsonl` matches `benchmark/results/<anything>/<anything>.jsonl` at any depth. The request scopes the suppression to "result rows"; this glob also matches any other `.jsonl` living under `benchmark/results/` — tool logs, receipts, aggregation/summary files, run manifests stored as jsonl. `NOT_MODEL_OUTPUT` in the new test only asserts `.json` (`benchmark/results/m76/ids.json`) and `.md`, so it does not probe this.
- Problem: a non-model-output `.jsonl` under `benchmark/results/` that carries a real `/home/<name>/` leak (e.g. a tool log or receipt capturing a remote Linux host's home path) is no longer blocked for the `/home/` pattern. `/Users/`, dash-flattened, tokens, hostnames still fire.
- Failure scenario: a receipt jsonl `benchmark/results/m76/run-42/receipts.jsonl` records `ssh deploy@buildfarm "scp /home/<name>/artifacts/x"`; `deploy` is a real account on a real Linux build host. The `/home/<name>/` line passes the hook.
- Proposed change: narrow to the actual result-row layout. From the test's `MODEL_OUTPUT`, result rows live one level under a model dir (`benchmark/results/<model>/<bench>.jsonl`) or under `benchmark/results/m76/wave2/<leg>/s1/...`. A glob that fits both without admitting arbitrary depth is e.g. `benchmark/results/*/*.jsonl` and `benchmark/results/*/*/*/*/*.jsonl` (or match the `wave2` shape explicitly). If the harvest truly writes result rows at arbitrary depth, keep the broad glob but accept that "result rows" in the request is wider than the words imply; either way, fix the comment to say "every `.jsonl` under `benchmark/results/`" rather than "result rows".

---

**F2 — `*opencode_transcripts/*` and `*.final_tree/*` match any path containing those segment names, anywhere in the repo**
- Location: `piicheck.py:103–104`.
- Severity: minor.
- Evidence: confirmed. `*` crosses `/`, so `*opencode_transcripts/*` matches `docs/opencode_transcripts/notes.md`, `scripts/opencode_transcripts/cleanup.sh`, and even `Xopencode_transcripts/foo` (the leading `*` matches any prefix including one ending in a non-separator character). Same for `*.final_tree/*`. The exemption is `/home/`-only, so `/Users/`, tokens, hostnames still fire — but the `/home/` suppression reaches any file that happens to sit under a directory named `opencode_transcripts` or `<anything>.final_tree`, not only P426-harvested model output.
- Problem: a documentation or script file placed under such a directory loses `/home/` enforcement. Low risk on macOS (real home is `/Users/`), but it is a scope widening beyond "harvested model output".
- Failure scenario: a developer drops `docs/opencode_transcripts/README.md` describing a Linux setup with a real `/home/<name>/` path; the hook does not flag it.
- Proposed change: anchor the globs to the harvest's actual published/source roots, e.g. `benchmark/legs/*/opencode_transcripts/*` and `benchmark/legs/*/*.final_tree/*` (or whatever the real published prefix is), or pass the harvest a flag the checker can read instead of matching by name. If the harvest genuinely writes these dirs at arbitrary roots, keep the broad glob and note the residual in the comment.

---

**F3 — `fnmatch` comment is correct for the paths the harvest passes, with one caveat on the Wave 2 source-path shape**
- Location: `piicheck.py:100` comment "(`*` crosses `/` in fnmatch)"; `p426_harvest_excerpt_wave2.py:21` calls `piicheck.violations(..., path=e.source, ...)` with `e.source` the leg-relative source path.
- Severity: minor (likely no miss, but worth confirming).
- Evidence: confirmed for `fnmatch`: `fnmatch.fnmatchcase("a/b/c.jsonl", "benchmark/results/*.jsonl")` is False only because of the literal prefix; `*` does match `/`. The new test's `MODEL_OUTPUT[1]` (`benchmark/results/m76/wave2/tg1-m76-x-s1.a1/s1/model.s1.opencode_go.L1.full.a1.jsonl`) is asserted exempt and will be — it matches `benchmark/results/*.jsonl`. The opencode-transcript and final-tree samples (`tg1-m76-x-s1.a1/opencode_transcripts/...`, `evidence/run-1/go__counter.final_tree/...`) match `*opencode_transcripts/*` and `*.final_tree/*` respectively, with or without a `benchmark/...` prefix, because the leading `*` absorbs any prefix.
- Hypothesis (not confirmed from the two excerpts alone): if Wave 2 ever calls `piicheck` with `e.source` for a **result row** (not just evidence), that source is leg-relative and would not start with `benchmark/results/`, so `benchmark/results/*.jsonl` would not match and the `/home/` suppression would not apply — legs would still stop on a model-written `/home/`. The excerpt only shows the `e.dest == "main"` branch using `e.source`; whether any result row takes that branch is not visible. The publish excerpt's `_publish` uses `rel` (repo-relative), which does start with `benchmark/results/`, so result rows going through `_publish` are fine.
- Problem: if any Wave 2 result row is checked via `e.source` (leg-relative) rather than via `_publish`'s `rel`, the new glob misses it.
- Failure scenario: a Wave 2 result row whose leg-relative `e.source` is `tg1-m76-x-s1.a1/s1/model.s1.opencode_go.L1.full.a1.jsonl` and whose content carries `cd /home/<name>/project`; `piicheck.violations(..., path=e.source)` returns the `/home/` violation, the harvest records a problem, the leg stops — the exact stop the operator approved suppressing.
- Proposed change: confirm in `p426_harvest.py` whether Wave 2 result rows are ever checked with `e.source`. If yes, either (a) also pass the published `rel` to `piicheck` for those rows, or (b) add a leg-relative result-row glob (e.g. `*/*.jsonl` is too broad; better `tg1-*/*.jsonl` and `tg1-*/*/*.jsonl` matching the `tg1-.../sN/model...jsonl` shape). The new test does not exercise a leg-relative result-row path, so this gap is untested.

---

**F4 — The adjusted existing test is still meaningful but weaker than before**
- Location: `test_pii_check.py:107–113` (`test_agentbench_os_results_home_exemption_does_not_leak_to_other_files_P17`), changed from `not_agentbench.jsonl` to `not_agentbench.md`.
- Severity: minor.
- Evidence: confirmed. Before the change, the look-alike was `benchmark/results/some-model/not_agentbench.jsonl` — a `.jsonl` under `benchmark/results/` that is NOT an `agentbench_os*` stem; the old narrower glob `benchmark/results/*/agentbench_os*.jsonl` did not match it, so `/home/` was still enforced and the test asserted a violation. After the change, that same path now matches `benchmark/results/*.jsonl` and would be exempt — so the test would fail. The fix changes the look-alike to `not_agentbench.md`, which does not match `benchmark/results/*.jsonl` (wrong extension) and so still asserts a violation.
- Problem: the test no longer proves that a non-result-row `.jsonl` under `benchmark/results/` stays enforced — because the change deliberately exempts all such `.jsonl`. The docstring's parenthetical admits this ("every `benchmark/results/**.jsonl`"), so the test is honest about what it now checks, but the protection claim "the glob match is narrow on purpose" is weaker: the narrowness is now only on extension, not on stem or directory depth. A `.jsonl` look-alike that is not model output (F1) is no longer covered by this test.
- Failure scenario: someone later adds `benchmark/results/tools/session.log.jsonl` (a tool log, not a result row) carrying a real `/home/`; this test does not catch the regression because it only tests `.md`.
- Proposed change: add a parallel assertion that a non-model-output `.jsonl` under `benchmark/results/` (if such a class is meant to stay enforced) still flags `/home/` — i.e. decide whether F1 is intended or not, and encode the decision in a test. If F1 is intended (all `.jsonl` under results is model output by convention), add a test that documents that convention and asserts a `.jsonl` receipt/tool-log path is exempt, so a future narrowing is caught. If F1 is unintended, narrow the glob (F1's proposed change) and restore the `.jsonl` look-alike here.

---

**F5 — Tests miss: dash-flattened `/home/` is asserted only on a placeholder-shaped name; hostname/token interplay with the exemption is not tested at depth**
- Location: `test_s24_p17_pii_model_output_home.py:40–43` (`test_dash_flattened_home_still_fires_in_model_output`).
- Severity: minor.
- Evidence: confirmed. The dash-flattened test uses `x-home-<name>-y` where `dev` is not in `PLACEHOLDER_USERS`, so it fires — correct. But the test does not cover: (a) a flattened form with a placeholder username (`-home-<name>-`) in a model-output file — which should NOT fire (and currently doesn't, because the dash-flattened pattern is not the `_HOME_PATH_WHY` pattern and so is never suppressed by the exemption; this is correct behavior but untested); (b) a flattened `-Users-<name>-` in a model-output file — should fire and does (untested); (c) tokens/hostnames in model-output files at the same line as a `/home/` — the `test_other_patterns_still_fire_in_model_output` covers tokens and `/Users/` but not hostnames (`.local`).
- Problem: the invariant "only the `/home/` slash pattern is suppressed; everything else still fires in these files" is partially untested for hostname and dash-flattened-`/Users/` cases.
- Failure scenario: a future edit accidentally widens the exemption to suppress dash-flattened home or hostnames in model-output files; the existing tests pass.
- Proposed change: add to `test_other_patterns_still_fire_in_model_output` a `.local` hostname assertion, and add a case that `-Users-<name>-` fires in a model-output file.

---

**F6 — `PLACEHOLDER_USERS` interaction with the new exemption is not tested**
- Location: `piicheck.py:55–62` (`PLACEHOLDER_USERS`) vs `test_s24_p17_pii_model_output_home.py`.
- Severity: minor.
- Evidence: confirmed. The exemption skips the `/home/` pattern entirely in matched files (line 139–141: `if home_exempt and why == _HOME_PATH_WHY: continue`), so the `PLACEHOLDER_USERS` whitelist is never consulted for `/home/` in model-output files. That is fine, but no test asserts that a `/home/<name>/` in a model-output file is silent (it is, trivially, because the whole pattern is skipped) and that a `/home/<name>/` in a non-model-output file is also silent (via the whitelist). The two paths to "silent" are different and a refactor could break one.
- Problem: low — behavioral risk only on refactor.
- Proposed change: add one assertion each.

---

**Scope request S1 — The comment at `piicheck.py:98–100` says "result rows" but the glob admits more; either narrow the glob or correct the comment**
See F1. Not a severity; it is a request to make the code's stated scope match the request's stated scope.

---

**Hazard check — does the change introduce a way for `/Users/`, tokens, hostnames, or dash-flattened forms to leak in model-output files?**
No. `piicheck.py:139–141` suppresses only `why == _HOME_PATH_WHY` (the `/home/` slash pattern). The `/Users/` pattern (`why = "absolute home path with a username"`, distinct string), the dash-flattened pattern, tokens, and the mDNS hostname pattern all have different `why` strings and continue to fire. The new test `test_other_patterns_still_fires_in_model_output` and `test_dash_flattened_home_still_fires_in_model_output` confirm this for `/Users/`, `hf_`, and dash-flattened-home. Hostname (`.local`) is not covered (F5). No new hazard to `/Users/` or tokens.

---

**Summary**
The change does suppress only the `/home/` slash pattern, and only via path glob — that part is correct and the `fnmatch` comment is accurate. The deviations from the request are all on the *width* of the model-output globs: `benchmark/results/*.jsonl` exempts every `.jsonl` under results (F1, F4), and `*opencode_transcripts/*` / `*.final_tree/*` match by segment name anywhere (F2). There is one unconfirmed miss risk for Wave 2 result rows checked via leg-relative `e.source` (F3). No blocker; F1/F2 are the material scope questions — if the harvest convention is "every `.jsonl` under `benchmark/results/` is model output" and "those directory names only appear under harvest roots," then F1/F2 are fine and only the comment wording (S1) and test coverage (F4/F5/F6) need tightening. If not, the globs should be anchored.
