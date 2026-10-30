# P541 pre-push level check — code review round 1 of 3: opinion + verify, dispositions

Material: `benchmark/bench/local_gate.py` + `benchmark/bench/tests/test_p541_push_level.py` (the independent tests), spec
`docs/specs/p541-push-levels.md` v1.2 (opinion) / v1.4 (verify). Context: `briefed` (`change.diff`, the module and the tests as `.txt`,
`spec.md`; verify adds `repair.diff`). Budget: one opinion, one verify (review-panel), both used. Landed in stack `e3c70a79`.

| Member | Runtime | Model (reported) | Session | Context | Opinion | Verify |
|---|---|---|---|---|---|---|
| sol | cursor-agent 2026.10.22 | `gpt-5.6-sol-high` (requested; not reported) | not reported | briefed, user instructions unconfirmed | first attempt aborted (`ECONNRESET`), retry: 4 findings | fresh session: all resolved + 1 minor |
| glm | cursor-agent 2026.10.22 | `glm-5.2-high` (requested; not reported) | not reported | briefed, user instructions unconfirmed | 12 items, 3 kept (rest self-withdrawn) | fresh session: NOTHING OF SUBSTANCE |
| sonnet | claude CLI | `claude-sonnet-5-5` | `a9e15a44-8237-4346-a5ca-0573fad77ec3` (resumed for verify) | briefed, user instructions suppressed; same vendor as the driver | 6 findings | NOTHING OF SUBSTANCE |

## Opinion ledger

| # | Finding | Raised by | Disposition |
|---|---|---|---|
| 1 | `_git` strips `-z` output: a sole path ` docs/x.py` classified docs-only (bypass) | sol (major), sonnet (major) | Adopted (v1.3): lossless `_git_raw`, NUL split, nothing stripped; leading / trailing whitespace and newline path tests. |
| 2 | `introduced()` treated commits on `<remote>/evidence` as already pushed: a code branch at an evidence commit was `none-new` (bypass) | sonnet (major) | Adopted (v1.3 / v1.4): `--exclude=<remote>/evidence` for every non-evidence push; code → full, data → data-only tests. |
| 3 | `push_level` returned `data-only` for any evidence push without the orphan check | glm (F6, major), sonnet (minor) | Adopted: `push_level` resolves `^{commit}` and owns the orphan rule; non-orphan → full + the v1.3 problem; `check_lines` relies on it. |
| 4 | A raising `digest_for` crashed the hook without per-ref output | sonnet (minor, hypothesis) | Adopted: any exception → the v1.3 per-ref digest problem; other refs keep their lines. |
| 5 | A ref with a scan problem still printed a `level:` line | sol (minor), sonnet (minor) | Adopted: only refs with no problem at all print one. |
| 6 | Receipt-content checks (wrong digest / sha / verdict inside a correctly named file) untested | sol (minor), sonnet (minor) | Adopted: parametrised test (passes; the code already checked contents). |
| 7 | Fork-tag tests did not pin the tagged commit's sha8 (v1.2) | glm (F1 blocker, F2 major), sol (minor) | Adopted: exact sha8 asserted, and that it differs from the tag object's. |
| 8 | The naming-scan test depends on the `modelnames` list | glm (F10, minor, hypothesis) | Declined: intended dependency; the test passes. |
| 9 | Scope: `push_level` should resolve a short / tag sha itself | glm (F12) | Adopted within 3. |
| 10 | Implementer's calls: stack-tag release and gitlink `digest_for` still propagate an exception (outside the level rules) | implementer | Accepted (refusal, not a bypass; pre-dates P541). The brief's claim that a non-orphan evidence push also gets the naming scan was wrong (glm verify): every evidence push gets PII only, per spec. |

## Verify ledger

All ten resolved or disposed as above (all three members). New:

| # | Finding | Raised by | Disposition |
|---|---|---|---|
| V1 | `_git_raw` used `text=True`: a non-UTF-8 path raises `UnicodeDecodeError` (traceback, no per-ref output) | sol (minor) | Adopted before the commit: bytes, NUL split, `surrogateescape` decode. |

Final: 184 passed (`test_p541_push_level.py`, `test_local_gate.py`, `test_t3_local_gate.py`, `test_p541_impl.py`); two stale
`test_local_gate` expectations replaced by the designer. Pushed through the new hook at level full (C255).
