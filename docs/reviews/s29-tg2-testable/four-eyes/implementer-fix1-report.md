# Implementer report, fix round 1 — S29 tg2 testable (spec `docs/specs/s29-tg2-testable.md` v1.1)

Baseline `cd334f773e6bc6d1e2f9f1344755e4df787b4fef`. Candidate 2: `out/candidate-2.diff` (the brief's export; it now
includes `configgen/`). Nothing committed. The export's `git add -A -- benchmark configgen` also stages the frozen test
dir, which the pathspec then excludes from the diff.

## Findings first (the designer should look at these)

- **F1 — K1 is now inert on real worker logs (P9 consequence).** The fork logs `Request started: endpoint=… model=… stream=…
  in_flight=…` and `Request failed: … error=… in_flight=…` with **no `uid` and no `session`**
  (`src/mlx-vlm/mlx_vlm/server/generation.py:691`, `:760`; the recorded `server_log_slice.log` files agree). The brief says that
  when the binding can't be established, the class stays INTEGRITY. So the real recorded P16 shape (`tg2-m76-n16-s2.a1`) would
  reconcile as **integrity**, not accounting, until the fork logs the request uid on both lines. That is a fork change
  (`../mlx-vlm`) and is out of this brief. The frozen K1 tests still pass because their synthetic lines carry `uid=1`.
  My test `test_a_trailing_failure_not_bound_to_the_items_own_request_stays_integrity[no uid on either line (today's worker log
  format)]` pins this.
- **F2 — the shell deny list grows from 156 to 521 rules** (webfetch unchanged at 59, byte-identical to candidate 1). The
  biggest contributors: the host-position prefixes (7 prefixes × 12 host case forms = 84), the problem-specifications
  fetch-command forms (23 fetchers × 4 case forms = 92), and the package-manager org specs (80). It is generated and opencode
  evaluates it linearly per call. I see no correctness cost, but the file is much bigger.
- **F3 — scoped `@exercism/*` npm packages are allowed (my call).** The JS exercises' `package.json` uses the org's
  babel / eslint tooling packages under that scope. They hold no solutions, and an agent repairing its install may fetch them,
  so the package-manager deny targets only the bare org forms: `exercism`, `exercism/<repo>`, `exercism@…`, `exercism#…` and
  `github:exercism/…`. Tested: `npm install --save-dev @exercism/babel-preset-javascript` is allowed.
- **F4 — what still over-matches (whole-line reading only; not required by the brief, so left alone):**
  - a file name that starts with the full host name, e.g. `cat exercism.org.txt`;
  - `grep -r exercism.io .` (the host in argument position);
  - a line that pairs a package-manager command with a local `exercism/…` path argument, e.g.
    `npm install && cd exercism/rust` (denied whole-line; allowed per command);
  - a line that pairs a fetch tool with a local `problem-specifications` path, e.g. `curl … && ls problem-specifications-x`.
  
  None of the brief's local examples is denied.
- **F5 — what is still not covered:**
  - the Exercism CLI invoked by path (`/usr/local/bin/exercism download`). The CLI is denied at command start and after
    `; | & ( \`` and newline, but not after `/`, because `*/exercism *` would deny `ls ~/exercism`;
  - arbitrary mixed case such as `ExErCiSm` (unchanged from candidate 1, F3 there);
  - a mirror under another host / org whose name does not contain `problem-specifications`.
- **F6 — no real opencode session** (no 2.0.20 binary on this box, as in candidate 1). Every statement here is about the rule set
  under the Python matcher port, read both whole-line and per parsed command.

## What changed

**1 + 2 + 3 (carrier, `configgen/emitters/opencode.py` → `_tg2_shell_lookups`, carrier regenerated; webfetch unchanged):**
- Exercism hosts: in URL / host position only — `*{p}{host}*` with `p` ∈ `//`, `.`, `@`, space, `=`, `'`, `"`. The TLD case forms
  are literal (`org/ORG/Org`, `io/IO/Io`; `_case_forms(..., literal_short=True)`), so `exercism.?o` no longer matches `.lo…`.
  Allowed now: `-Dexercism.local=true`, `cat exercism.log`, `ls exercism.local`. Still denied: `curl exercism.org/x`, <!-- allow-pii-pattern -->
  `api.exercism.org`, `git@exercism.org:`, quoted / `--url=` forms, upper case.
- Org forms (substring, any case) gain `github.com/orgs/exercism`, `github.com/users/exercism` (web + `api.github.com`),
  `github:exercism`, `gh:exercism/`.
- `problem-specifications` (shell) is narrowed to: `*://*ps*`, `*@*:*ps*` (ssh / scp), `github:` / `gh:` shorthand, and
  `*<fetcher> *ps*`, where the fetchers are curl, wget, git clone / submodule / remote / fetch / pull / archive, gh repo / api,
  svn, `urlopen(`, `fetch(`, `requests.get(`, degit / tiged / giget, npm / npx / yarn / bun / bunx.
  Allowed now: `ls problem-specifications-notes`, `cat ~/problem-specifications/README.md`, `grep -rn problem-specifications .`.
- Repository fetchers: `*degit *exercism*`, tiged, giget (any case of the word).
- Package managers (npm also covers pnpm, npx also covers pnpx; yarn, bun, bunx): `*<tool> [* ]exercism{ *,/*,@*,#*}`, plus the
  existing `*install exercism*`.
- GitHub CLI, all `*`-prefixed so they match anywhere: `*gh repo * exercism/*`, `*gh repo list *exercism*`,
  `*gh api *repos/exercism/*`, `*gh api *orgs/exercism*`, `*gh api *users/exercism*`, `*gh search *`.
- Exercism CLI: `exercism *` and `*{sep}exercism *` for each separator in `; ` `;` `| ` `|` `& ` `&` `( ` `(` `` ` `` and newline.
- `bench/tg2_testable.py`: `LOOKUP_SHELL` gains the classes `repo-shorthand`, `github-org-api` and `cli-not-first`, and
  `LOCAL_WORD_COMMANDS` gains the local names above, so the acceptance-6 lookup record covers them.

**4 (K1, `bench/p426_reconcile.py`):** new `_k1_bound(lines, session)`. The window's final `Request started` and `Request failed`
both carry a `uid` and the two are equal; a `session` field on either equals the row's `session_id`; the row has a
`session_id`. Otherwise `_trailing_failed_at_kill` returns None and today's class (integrity) stands. The K1 facts record
`request_uid` and `session`. The membership of the window itself is the hook's item window, as before (see F1).

## Tests (failing first)

| test (new / extended) | red on candidate 1 | green now |
|---|---|---|
| `test_s29c_impl_carrier.py`: lookups denied whole-line AND per command (every `LOOKUP_SHELL` class, incl. the new degit / npm / pnpm / yarn / `github:` / org-user API / `gh repo list` forms); 8 anchored CLI lookups × 8 leading contexts (`&&`, `;`, `||`, `|`, `( … )`, `$( … )`, `&`+newline); local names allowed under both readings (14); host-position forms denied (7); every candidate-1 lookup class still denied | 129 failures (run against the candidate-1 carrier JSON before regenerating; local-name 7 + 7, per-reading 27, every-class 22, not-first 64, record 1, drift 1) | 436 passed |
| `test_s29c_impl_k1.py`: the bound pair records uid / session; mismatched uid, missing uid on either / both lines, foreign session, row without `session_id` → integrity; a matching session field → K1 | run against the staged candidate-1 `p426_reconcile.py` (scratch swap module, not in the diff): the mismatched-uid, missing-uid and foreign-session shapes came out `accounting` (red), and the uid-record test failed with `KeyError` (6 red); the row-without-`session_id` test already held on candidate 1 (it fails elsewhere), so it is a guard, not a red-first test | 23 passed |

Existing K1 tests in that file now build the trailing pair with `uid=41` (the b2 helper lines carry none).

## Commands and results (all via `../fe_test.sh stack …`, cwd = the copy)

| run | result |
|---|---|
| `bench/tests/s29c_frozen` (`out/fix1-frozen.txt`, `out/fix1-frozen.xml`) | **655 tests: 650 passed, 5 failed, 0 skipped.** The 5 are exactly the test-side ones listed: `t1_docker[javascript]` (npm `EAI_AGAIN`, network-less container), `t1_static` rust doubly-linked-list / wordy / xorcism, cpp crypto-square. The six T3 local-name failures of candidate 1 (frozen tests 6–11) now pass. |
| the related set = the test-writer's `out/related-args.txt` (all my `test_s29c_impl_*`, `configgen/tests`, the 91 module files, the `s26/s29/s29b/p586` frozen dirs, `p613s3/s4`), `--basetemp=/private/tmp/s29c-fix1-bt` (`out/fix1-related.txt`, `.xml`) | **4611 tests: 4610 passed, 0 failed, 1 skipped** (configgen schema capture: the bench opencode 2.0.20 binary is not installed). Includes configgen drift (89 configgen tests) and `test_the_tg1_carrier_is_unchanged_from_the_baseline`. |
| tg1 carrier vs baseline | byte-identical (`git diff --cached --quiet cd334f773 -- benchmark/opencode_bench_v2_web_tg1.json`) |

Not run this round: the ~70 other files of my previous 175-file final run that the test-writer's list does not name, and the
`GATE_PUSHED_BASE` arm-closure test (environment, same as round 0).

Scratch helpers (not in the diff): `impl/scratch/red/test_red_fix1_k1.py` (the red check),
`impl/scratch/red/test_regen_tg2.py` (writes only the tg2 target's configgen render; the drift tests confirm there is no drift).
