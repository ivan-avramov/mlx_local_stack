# Test-writer report, delivery 3 — amended frozen tests and tests for the adopted defects

## What changed in `benchmark/bench/tests/s29c_frozen/` (only what the brief names)

Amended (the five invalid tests):
1. **JS docker** (`s29c_support.run_in_container`, `container_script`, `test_s29c_t1_docker`): the JavaScript container now has network access (the other languages stay `--network none`), and a stated `npm install` / `npm ci` runs without my pre-linked `node_modules` (otherwise npm "removes the non-directory"). The case skips with the reason — never passes vacuously — only if the run fails with a network error (`EAI_AGAIN`, `ENOTFOUND`, `ETIMEDOUT`, …) and produced no test summary. On this box the registry was reachable: **the case ran and passed on candidate 1 (not skipped)**.
2–4. **Rust parser** (`s29c_support.rust_tests`): a test, or a `mod` holding tests, under `#[cfg(feature = …)]` (and a file with `#![cfg(feature = …)]`) is not a test of the default run. doubly-linked-list, wordy, xorcism now pass on the candidate.
5. **C++ parser** (`s29c_support.cpp_cases`): joins adjacent string literals across lines — **and**, because that alone did not fix crypto-square, strips comment-only lines. Correction of my delivery-2 diagnosis: the two names were not split literals; a `// clang-format off` / `// clang-format on` line sits between `TEST_CASE(` and the name (inspected in the candidate's prepared tree). crypto-square now passes on the candidate.

Added:
* `test_s29c_adopted_defects.py` (new): (a) the lookups `npx degit` / `tiged exercism/rust`, `npm install` / `npm i github:exercism/rust`, `pnpm add github:exercism/…` (rust and problem-specifications), `yarn add exercism/rust` / `github:exercism/rust`, `npm i exercism`, `npm install exercism`, `curl` of `api.github.com/orgs/exercism/repos` (also with a query) and `/users/exercism`, `gh api orgs/exercism/repos`, `gh api users/exercism`, `gh api /orgs/exercism/repos --paginate` — denied alone in the case forms (as written, Title, UPPER, `eXERCISM`) and chained after each of the four permitted build commands (`&&`, `;`, `| tee … &&`, `cd /tmp &&`, subshell, `||`), under all four readings (last-wins / deny-wins × whole line / per command); ordinary installs and other orgs stay allowed (`npm install`, `npm i`, `npm install jest`, `yarn add jest`, `pnpm add lodash`, `npx degit someone/…`, other-org `gh api` / `curl`); (b) local names `-Dexercism.local=true`, `cat exercism.log`, `ls exercism.local` (and `grep … exercism.local.cfg`, `--features exercism.local`, `tail … exercism.log`, `Exercism.log`, `EXERCISM.LOG`), alone and chained with a build; a guard that the real hosts (`exercism.org`, `.io`, org/user API URLs) stay denied by webfetch and shell next to them; two instrument self-checks for the amended parsers (known positives). <!-- allow-pii-pattern -->
* `test_s29c_k1_kill_boundary.py` (c): `test_k1_a_failed_line_of_another_stream_than_the_final_start_stays_integrity` — the recorded shape with the failed line's `uid` 2 against the final started line's `uid` 1 must stay `integrity` (the fixture asserts the mismatch is really there). The builder gained a `failed_uid` argument; nothing else in that file changed.
* The P4 local `problem-specifications` paths stay as written (unchanged).

New hashes (frozen files changed: `s29c_support.py`, `test_s29c_k1_kill_boundary.py`, `test_s29c_t1_docker.py`; added `test_s29c_adopted_defects.py`; the rest byte-identical to the 22:36Z freeze):
```
6b35d86a52f4424239a0de8cad2b180bb7684e0a38fd1a148267a383164d7b26  s29c_frozen/s29c_support.py
da8a35741bfcbd9ff57fa9c5c0ec8a90b1524092f98c80ee22e7b1938e527c20  s29c_frozen/test_s29c_adopted_defects.py
b3ff029380e98463cf8353b97fdce19e6da0976bb0b0a3d5d3b9245d1c6b76f3  s29c_frozen/test_s29c_k1_kill_boundary.py
aa46931ae2a120cca582aedeb69310866ef2695ca4bfc7ee3c9719dc23cea380  s29c_frozen/test_s29c_t1_docker.py
```

## Outcomes (720 tests; `../fe_test.sh stack bench/tests/s29c_frozen`, docker included, none skipped)

| | passed | failed | skipped | errors |
|---|---|---|---|---|
| **baseline** (candidate diffs reverse-applied; `out/run3-base.xml`, `run3-base.txt`) | 305 | 415 | 0 | 0 |
| **candidate 1** (re-applied; non-docker run `out/run3-cand-nodocker.txt` 696 tests: 48 failed; docker file `out/run3-cand-docker.xml` 24 tests: 24 passed — two runs, the totals are their sum) | 672 | 48 | 0 | 0 |

The working tree is back to candidate 1 (both diffs applied; git status = the candidate's files + my untracked test directory). I used `git apply -R` / `git apply` only; no reset, commit or history change.

### Baseline: the new and amended tests
* (a) lookups: **all pass** (the baseline's broad `*xercism*` deny covers them) — they are guards against the fix opening a hole, as labelled; the "ordinary installs allowed" tests pass too.
* (b) local names: **11 fail** (8 alone, 3 chained) — the baseline denies any shell command containing the word; `test_b_the_real_hosts…` passes.
* (c) K1 uid mismatch: **passes** (baseline class is already integrity).
* JS docker (with network): **passes** on the baseline (canonical `npm test`, pre-linked modules); rust and cpp docker parity fail as before; the amended parsers do not change the baseline's rust/cpp static failures (30 rust, 24 cpp, same as delivery 1) — the rust/cpp failure counts per item are unchanged. <!-- allow-shorthand -->
* The 415 = delivery 1's 404 + the 11 new (b).

### Candidate 1 (for information): 48 failures, all accounted for
* **Adopted defects (41):** (a) 14 alone + 14 chained — the candidate allows, among the listed lookups: `npx degit/tiged exercism/rust`, `npm install/i github:exercism/rust`, `pnpm add github:exercism/rust`, `yarn add exercism/rust` and `github:exercism/rust`, `npm i exercism`, the `api.github.com` orgs/users `curl` forms, `gh api orgs/…` / `users/…` / `/orgs/… --paginate` (still denied: `npm install exercism`, `pnpm add github:exercism/problem-specifications`); (b) 8 local names alone + 3 chained denied by the candidate (`exercism.lo…`); `test_b_the_real_hosts…` fails 2 (the `api.github.com/orgs|users/exercism` URLs are not denied by shell).
* **(c)** the K1 uid-mismatch test **fails on candidate 1**: with the failed line's uid different from the final started line's, candidate 1 still classes the shape `accounting` (its `_trailing_failed_at_kill` checks `lines[-2].kind == "started"` but not the uid).
* **Delivery-2 carry-over (6):** the three `problem-specifications`/`.local` local-path cases, alone and chained, in `test_s29c_t3_t4_permissions.py` (unchanged tests; the designer already ruled on the validity of the other five).
* Everything else passes: T1 static (rust, cpp, js, java, incl. the amended parsers), T1 docker 24/24, T2, T3-stated, T4, tamper, I1, K1 (9 of the 10 K1 tests). <!-- allow-shorthand -->

Not run in this delivery: the existing-module suites (unchanged from delivery 2); a real opencode session (no binary).
