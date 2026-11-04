P1
- Location: `benchmark/bench/p426_verify.py:1021-1094`, `_w1_smoke_scrub`.
- Severity: major.
- Evidence: confirmed by source trace.
- Problem: excluded smoke legs become mandatory inputs and can refuse the entire run. The contract says they are coverage-only and never scored.
- Failure scenario: the frozen fixture creates smoke receipts without `SCRUB_MANIFEST.json`; every normal `verify_wave1` call refuses. Smoke files also appear in `B8.inputs`, contrary to frozen assertions.
- Proposed change: treat smoke SCRUB verification as optional coverage evidence; record missing/invalid smoke metadata without refusing or adding it to pair inputs.

P2
- Location: `benchmark/bench/p426_verify.py:933-939`, `_w1_equal_reasons`; `p426_signals_wave1.py:150-176`.
- Severity: major.
- Evidence: confirmed by source trace; frozen tests miss compensated swaps and equal non-81920 budgets.
- Problem: thinking budgets are compared as sorted multisets rather than by row key, and the required 81920 budget is never enforced.
- Failure scenario: ON swaps 81920 and 40960 between two items while OFF does not. B8 accepts the pair and the sheet can label a result `acc_strict@81920` although its rows used another budget.
- Proposed change: compare `(key, thinking_budget)` mappings and require 81920 for every A1 row before emitting `acc_strict@81920`.

P3
- Location: `benchmark/bench/p426_verify.py:824-876`, `worker_argv`, `job_argv`, `_w1_argv_reasons`.
- Severity: major.
- Evidence: confirmed by source trace; frozen tests check unrelated worktrees but not swapped arm worktrees.
- Problem: either `stack-p426-s2-off` or `stack-p426-s2-on` is normalized to `ARM` without first verifying that it matches the leg’s arm.
- Failure scenario: an ON receipt names the OFF worktree and still passes rule 2c.
- Proposed change: require the expected arm-specific path component before normalization.

P4
- Location: `benchmark/bench/p426_verify.py:960-1014`, `_identity_sha`.
- Severity: major.
- Evidence: confirmed by source trace; frozen tests cover bad digests, not absent identity fields.
- Problem: missing A1/A2 `content` and `content_sha256` satisfy `None == None`; missing A3/A4 identity text also returns `None` without refusal.
- Failure scenario: structurally incomplete rows enter an accepted pair with unverifiable identity.
- Proposed change: require identity text strings and, for A1/A2, a valid SHA-256 field before comparison.

P5
- Location: `benchmark/bench/p426_verify.py:59-88,747-772`; `benchmark/bench/p426_signals.py:810-833`.
- Severity: major.
- Evidence: confirmed by source trace; frozen traversal tests cover `..`, not symlink escapes.
- Problem: SCRUB and B8 input paths are checked lexically, then `read_bytes()` follows symlinks outside `rows_root`.
- Failure scenario: `rows_root/foo` is a symlink to an external mutable file. B8 accepts and hashes it, violating committed-only inputs and making output environment-dependent.
- Proposed change: resolve every input and refuse unless it remains beneath resolved `rows_root`.

P6
- Location: `benchmark/bench/p426_verify.py:660-695,1055-1064`, `load_w1_leg`.
- Severity: major.
- Evidence: confirmed by source trace.
- Problem: result rows are parsed before SCRUB verification. Parse damage therefore causes a global refusal where rule 1 requires pair rejection.
- Failure scenario: a published JSONL file is truncated or loses its terminal newline. Parsing raises `RefusalError` before its SCRUB mismatch can reject only that pair.
- Proposed change: verify SCRUB first, or convert parse failures associated with a SCRUB mismatch into pair rejection reasons.

P7
- Location: `benchmark/bench/p426_signals_wave1.py:180-216`, `_a1`.
- Severity: major.
- Evidence: confirmed by source trace.
- Problem: `A1.both` omits the required per-arm combined accuracy, strict accuracy, convergence, errors, and non-convergence kinds.
- Failure scenario: the required committed 96/100 result for each arm cannot be read directly from the generated sheet.
- Proposed change: aggregate and render a `both.quality` record for each arm over both planned blocks.

P8
- Location: `benchmark/bench/p426_signals.py:858-873`, `compute_all`.
- Severity: major.
- Evidence: confirmed by source trace; frozen family tests only exercise both blocks accepted.
- Problem: A1 enters the “complete” mechanical family whenever any accepted A1 block produces a permutation p-value.
- Failure scenario: B8 rejects b2, but b1 alone becomes family member `A1`; Holm still reports `m=3` and `complete`.
- Proposed change: admit A1 only when both A1 blocks are accepted; otherwise mark the family incomplete.

P9
- Location: `benchmark/bench/p426_signals_wave1.py:95-137`, `_speed`.
- Severity: major.
- Evidence: confirmed by source trace; frozen tests do not combine key rejection with signal generation.
- Problem: acceptance sums only key-accepted rows, although the contract defines acceptance over all ON rows in each B8-accepted block.
- Failure scenario: one key is rejected for a seed mismatch. Its ON draft counters disappear from both numerator and denominator, changing the reported acceptance and potentially its flag.
- Proposed change: retain accepted keys for paired speed, but calculate acceptance from every ON row in each accepted block.

P10
- Location: `benchmark/bench/p426_signals_wave1.py:101-132`, `_speed`.
- Severity: minor.
- Evidence: confirmed by source trace.
- Problem: bootstrap inputs follow `ids.json` order instead of the required sorted `(block, key)` order.
- Failure scenario: reordering otherwise identical IDs changes finite-bootstrap CI bounds.
- Proposed change: sort keyed ratios before per-block and combined bootstrap calls.

P11
- Location: `benchmark/bench/p426_signals_wave1.py:140-146,420-429`, `_walls`, `compute_wave1`.
- Severity: major.
- Evidence: confirmed by source trace; frozen tests do not reject a pair before checking these sections.
- Problem: wall records and identity totals include rejected B8 pairs, violating the accepted-pairs-only requirement.
- Failure scenario: a rejected A3 pair still contributes both leg timings and its identical-key count to step-3 identity evidence.
- Proposed change: include rejected pair details only in coverage; calculate walls and identity exclusively from accepted pairs.

P12
- Location: `benchmark/bench/p426_signals_wave1.py:439-501`, `flags`.
- Severity: major.
- Evidence: confirmed by source trace.
- Problem: decode, acceptance, M1, and ON-only non-convergence flags omit the triggering items or legs required by the contract.
- Failure scenario: the committed A2/A3 acceptance flags identify only a scope; an A2 ON-only non-convergence does not identify `dom-04`.
- Proposed change: attach per-key/per-leg crosswalks to every Wave 1 flag.

P13
- Location: `benchmark/bench/p426_verify.py:780-876,930-949`; rejection rendering in `p426_signals_wave1.py`.
- Severity: major.
- Evidence: confirmed by source trace; frozen absolute-path checks cover successful output only.
- Problem: rejection reasons serialize raw differing argv, snapshots, served dictionaries, and receipt problems. These may contain absolute paths or PII.
- Failure scenario: an unexpected interpreter/worktree path is copied into `B8.json` and `SIGNALS.md`.
- Proposed change: report sanitized field names and values, masking all path-like tokens.

P14
- Location: `benchmark/bench/p426_verify.py:780-800,933-939`.
- Severity: minor.
- Evidence: confirmed by source trace.
- Problem: several rule-2 rejection messages omit the pair name and both compared values, contrary to the contract.
- Failure scenario: the operator sees only “manifest sampling differs” and cannot determine the OFF and ON values.
- Proposed change: prefix every reason with kind/block and include explicit OFF, ON, and frozen values where applicable.

P15
- Location: `benchmark/bench/p426_verify.py:880-949`, `_drafts`.
- Severity: minor.
- Evidence: confirmed by source trace; candidate behavior exceeds the contract and frozen tests do not exercise missing/zero turn-2 draft telemetry.
- Problem: A3 turn-2 draft state is an additional rejection gate, while the contracted A3 draft/acceptance treatment is turn 1.
- Failure scenario: an otherwise valid ON pair is rejected because turn 2 has no draft object or `draft_n == 0`.
- Proposed change: remove turn-2 gating or record it as non-gating evidence.

P16
- Location: `benchmark/bench/p426_verify.py:44-52,600-614`, `DENY_PATTERNS`.
- Severity: major.
- Evidence: confirmed by regex trace; the frozen test passes accidentally because its S-build file later fails row count.
- Problem: `(^|/)p426-(off|on)-` does not match filenames such as `math500.p426-on-b1.jsonl`, where `p426-` follows a dot.
- Failure scenario: a matching-sized S-build row file can be substituted and accepted.
- Proposed change: match `p426-` after either `/` or `.`, and add a fixture with valid planned IDs.

P17
- Location: `benchmark/bench/p426_signals.py:722-760,907-957`.
- Severity: minor.
- Evidence: confirmed by source trace; frozen `test_cli_equals_in_process` directly exposes it.
- Problem: `render_md(compute_all(...))` raises because `render_md` expects the step-1 A7 shape; the CLI uses a new private `render_all`.
- Failure scenario: the frozen in-process/CLI equivalence test and consumers reusing the existing renderer fail.
- Proposed change: make `render_md` dispatch on `generator_version`, preserving its A7 behavior while supporting all-records.
