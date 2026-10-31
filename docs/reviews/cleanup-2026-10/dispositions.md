# `$STACK_WORKDIR` cleanup (P556–P561, C260) — verification rounds 1–2 of 3, dispositions and the final table

Operator: "approved but run this table by cursor + GPT-Sol to verify". Member: sol (cursor-agent 2026.10.22, `gpt-5.6-sol-high` requested,
not reported; read-only `--mode ask`; context `briefed`: the workdir file list, the `evidence` trees, the backfill manifests, the HF dataset
listing with sha256, the citations, the rulings). Round 3 not used: the two open items after round 2 are preconditions checked mechanically.

## Round 1 → round 2

| # | Finding | Sev. | Disposition | Round 2 |
|---|---|---|---|---|
| P1 | Deleting `reviews/` destroys this verification | blocker | Adopted: filed here; `reviews/` deleted only after this directory is on `origin/main` | open → precondition 4 |
| P2 | `parked/` holds later P475 / P475a review rounds and test-writer reports with no filed copy | blocker | Adopted: 30 texts → `docs/reviews/parked/` (`33879e32`), 23 byte-duplicates skipped; the parked code → `evidence` `parked/` (`05161ba0`) | resolved |
| P3 | 132 arrays under `.venv/**` of `p542/fork/mlx-vlm` and `p369/fork-*` are on neither the dataset nor the upload list | minor | Adopted as an exemption: package test fixtures, regenerable from the locks | resolved (full enumeration: 702 = 330 on HF + 240 pending + 132 fixtures; sha256 samples matched) |
| P4 | The "except …" lists were incomplete (and "56" was 51 pairs) | minor | Adopted: enumerated in the table below | resolved (full path comparison) |
| P5 | The deletion gate omitted the pending `main` push | major | Adopted: precondition 1 | new in round 2 |

## Final table (operator-approved, as verified)

| Row | What | Lost on deletion (never on GitHub / HF) |
|---|---|---|
| 1 | `p369/phase2` | nothing (reports + raw on `evidence`; arrays on the HF dataset — 330 since C212, 240 at this push, C260) |
| 2 | `p426/` | 9 suite-log files (`stack-suite/**`), 1 rehearsal transcript (scanner false positive), 6 temporary manager logs, 5 `uv` lock copies |
| 3 | `opencode_transcripts/`, `m62`, `m63`, `m65*`, `c102a`, `c144-smoke`, `c151`, `c152`, `c154`, `m63-smoke`, `p452`, `p476`, top-level `*.txt` | 1,202 scratch files under `tmp/` |
| 4 | `b2/`, `p541/`, `p542/` | the copies' virtual environments (33 package-fixture arrays); everything else landed or filed |
| 5 | `p438/`, `p450/` | nothing (published backfill stages) |
| 6 | `p369/fork-*` | regenerable fork roots (99 package-fixture arrays in their venvs) |
| 7 | `session_gate/` | 51 opencode DB / snapshot-index pairs (PII-bearing, never publishable), 918 generated scratch `.git` files |
| 8 | `opencode-probe-v2/` | the 128 probe working directories + `tmp/` (rows / transcripts already on GitHub) |
| 9 | (in row 2) | — |
| 10 | `parked/` | nothing (texts on `main`, code on `evidence`) |
| 11 | `c147/`, `c144-base*`, `p400`, `p415`, `p422`, `p441`, `m61`, `.cache`, `downloads`, `control` | 332 HF-cache metadata files, 8 download files, 6 trivial `c147` scratch files |
| 12 | worktrees `stack-c249`, `stack-c249-off`, `stack-p369-full-off`, `stack-p426-s2-{off,on}`; branches stack `p369-full-off` (`7081c7af`), `p426-on-s2` (`f2b61127`), fork `p537-rebuilt`, `p537-straddle-offsets`, `p542-qualify-any` | nothing (results byte-identical on `main`; branches merged or superseded) |
| Keep | `nltk_data`, `polyglot-benchmark`, `opencode-2.0.20`, `vision_gate_images`, `gate/`, `locks/` | — |
| Last | `reviews/` | after precondition 4 |

## Deletion preconditions (all checked mechanically before the first `rm`)

1. `main` == `origin/main` (the push of this session's commits).
2. `evidence` == `origin/evidence`.
3. Each of the 240 arrays in the upload list is on the HF dataset with the sha256 of the stage's `EXTERNAL_MANIFEST.json`.
4. `docs/reviews/cleanup-2026-10/` is on `origin/main`.
