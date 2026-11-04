**Verdict: merge.** I found no push-safety hole. The one behaviour change against today's gate (P3) is low severity. <!-- allow-shorthand: the word "low", not a model -->

## Setup

- `git apply .p624-material/candidate.diff` applied cleanly. I left it applied in the copy.
- `benchmark/bench/tests/test_local_gate_ran_skips.py` is byte-identical to `.p624-material/frozen-d1/` (checked with `cmp`).
- The same tests ran on both trees: 26 in the new file plus 52 in `test_local_gate.py`, 78 in total on each.

## Test outcomes

| Class | Tests | Baseline | Candidate |
|---|---|---|---|
| reproduces-failure | 1 | fail | pass |
| new-behaviour | 16 | fail | pass |
| invariant | 9 | pass | pass |
| existing `test_local_gate.py` | 52 | pass | pass |

Per-test names and classes are in my delivery-1 report.

Summary lines, verbatim:
- Baseline: `17 failed, 61 passed in 34.00s`
- Candidate: `78 passed in 20.96s`

## Probes against the candidate

I ran these through `G.run` with the delivery-1 fakes, in a throwaway script outside the repo.

| Case | Result |
|---|---|
| Baseline lists a line twice, junit skips it once | PASS, `baseline_skips_ran == []` |
| Baseline lists a line twice, test ran and passed | PASS, entry listed once |
| S−W non-empty and a different W−S entry absent | FAIL with both problems, `-[…]` lists the absent entry |
| An earlier step (ruff check) fails | FAIL, `baseline_skips_ran` key absent |
| Baseline line has a leading space, test ran and passed | FAIL, new problem lists `' tests.test_a::test_one'` |
| Same id both skipped and passed in the junit | PASS, `baseline_skips_ran == []` |

## Findings

**F1 (low): duplicate baseline lines, the implementer's P3.** <!-- allow-shorthand: the word "low", not a model -->
- Where: `benchmark/bench/local_gate.py`, the `run` block after the steps loop, which now compares sets.
- Reproduce: a baseline with `tests.test_a::test_one` on two lines and a junit that skips it once. Today `skipped != want` gives FAIL. The candidate gives PASS.
- Impact: it is the only case that passes now and failed before. It needs a hand-edited, committed baseline that is also part of the policy digest, and it lets through no extra skip. I read set semantics as correct, since the spec is written in sets.
- Suggestion: if exact parity is wanted, add a duplicate-line problem. Otherwise add a pinning test. My frozen tests do not cover this case.

**F2 (info): `baseline_skips_ran` is missing on receipts where an earlier step failed.**
- Where: the key is set only after the pytest step succeeded.
- Why it is fine: that matches the spec's "after the pytest step succeeded". A FAIL receipt carries no usable list in any case, and I did not test the key on FAIL receipts.

**F3 (info): the path-padded baseline line is refused, not trimmed.**
- Where: the `want` list filters blank lines but does not strip whitespace.
- Why it is fine: this is today's behaviour. The candidate fails closed with the new problem.

## Safety review

- **What the candidate lets through:** only a baseline entry that has a `<testcase>` with the exact `classname::name` and no `<skipped>`, `<failure>` or `<error>` child.
- **What still fails:**
  - Any skip not in the baseline.
  - An entry that was not collected, renamed, failed or errored.
  - An xfail, which pytest writes as `<skipped>`.
  - A baseline file that does not exist.
  - A missing junit file with a non-empty baseline, because P is then empty.
- **No new hole:** a test that ran and passed was by definition not skipped, so accepting it adds no unrecorded skip, and the receipt now names each such entry.
- **Digest:** the gate source is part of the digest, so the change supersedes older receipts as the spec says.
