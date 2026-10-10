# D3 — Tune-encoding migration collision lineage

Analysis-only, read-only. Migration script run in **dry-run mode only** (default; `--apply`
was never passed by this session). No files modified, no commits made.

## Current state (important context before the table)

The 8 collisions this task asks about **have already been resolved and applied**, by earlier
work in this repo's own history — not by this session:

- `2e7dbd3` (feat: D3 tune encoding + migration script): first dry-run against the real tree,
  52 moves, **8 collisions refused**, all under `Ornith-1.0-35B-mlx-uniform-4bit-suffix` vs
  files already at `Ornith-1.0-35B-mlx-uniform-4bit/*.suffixon.*`.
- `fb8e67d` (fix: resolve the 8 migration collisions): relabels the `-suffix` pseudo-dir's tune
  from `suffixon` to `suffixon-phase2` in `PSEUDO_MODEL_DIRS`
  (`benchmark/bench/migrate_tunes.py:48`), reasoning that it's a genuinely different run (July
  Phase-2 validation vs the August OFAT). Dry-run after this fix: 60 moves, 0 collisions.
  `--apply` explicitly NOT run in this commit.
- `42fdaf9` (chore: apply the tune-encoding migration to benchmark/results): executes
  `--apply` — 60 moves, 0 collisions, 4 `suffixon` manifests stamped. This is already in git
  history (operator-approved per the commit message).

Running the dry-run **now**, against the current tree, confirms this:

```
LEFT IN PLACE (not a recognized bench artifact): .../Ornith-1.0-35B-mlx-uniform-4bit-kv4/capacity_ladder.jsonl
LEFT IN PLACE (not a recognized bench artifact): .../Ornith-1.0-35B-mlx-uniform-4bit-kv4/capacity_retrieval.json
KEPT (not fully migrated — see above): .../Ornith-1.0-35B-mlx-uniform-4bit-kv4
LEFT IN PLACE (not a recognized bench artifact): .../Qwen3.6-27B-Opus-Distill-OptiQ-4bit-kv3/capacity_ladder.jsonl
LEFT IN PLACE (not a recognized bench artifact): .../Qwen3.6-27B-Opus-Distill-OptiQ-4bit-kv3/capacity_retrieval.json
KEPT (not fully migrated — see above): .../Qwen3.6-27B-Opus-Distill-OptiQ-4bit-kv3

DRY-RUN: 0 file(s) to move, 0 collision(s) refused, 4 unrecognized file(s) left in place, 0 manifest(s) to stamp.
```

The two remaining dir shells hold only `capacity_ladder.jsonl` / `capacity_retrieval.json` —
fixed-name, non-`<bench>.*` artifacts the script correctly never touches (by design, per its
own docstring). This is expected steady state, not a defect.

Since the collisions no longer exist on disk to observe directly, the table below
**reconstructs the original 8 from git history** (`benchmark/results/` is deliberately
git-tracked, per `.gitignore` comment at line 23) — the pre-migration tree at `42fdaf9^`,
before the label fix and apply — and independently verifies the `fb8e67d` resolution rather
than just restating its commit message.

## Reconstructing the 8 collisions

At `42fdaf9^` (pre-migration), with the *original* label mapping (`-suffix` → `suffixon`,
matching `2e7dbd3`'s code), `Ornith-1.0-35B-mlx-uniform-4bit-suffix/` held 16 bench files; the
already-present `Ornith-1.0-35B-mlx-uniform-4bit/*.suffixon.*` held 8. Running the same
`<bench>.<label><rest>` join the script uses (`_split_bench_file`,
`benchmark/bench/migrate_tunes.py:60-71`) against both listings, exactly 8 of the 16 source
files land on a filename that already exists in the target — the `humanevalplus` and
`mbppplus` artifacts (both benches this run covered), across 4 file kinds each:

| # | source file (`Ornith-1.0-35B-mlx-uniform-4bit-suffix/`) | target filename that already existed (`Ornith-1.0-35B-mlx-uniform-4bit/`) |
|---|---|---|
| 1 | `humanevalplus.jsonl` | `humanevalplus.suffixon.jsonl` |
| 2 | `humanevalplus.manifest.json` | `humanevalplus.suffixon.manifest.json` |
| 3 | `humanevalplus.score.json` | `humanevalplus.suffixon.score.json` |
| 4 | `humanevalplus_samples_eval_results.json` | `humanevalplus.suffixon_samples_eval_results.json` |
| 5 | `mbppplus.jsonl` | `mbppplus.suffixon.jsonl` |
| 6 | `mbppplus.manifest.json` | `mbppplus.suffixon.manifest.json` |
| 7 | `mbppplus.score.json` | `mbppplus.suffixon.score.json` |
| 8 | `mbppplus_samples_eval_results.json` | `mbppplus.suffixon_samples_eval_results.json` |

(The other 8 files in the source dir — `aime.score.json`, `ifeval.score.json`,
`livecodebench.{jsonl,manifest.json,score.json}`, `math500.score.json`,
`humanevalplus_samples.jsonl`, `mbppplus_samples.jsonl` — had no same-named counterpart under
`suffixon.*` in the target and moved cleanly even under the original label; they are not part
of the 8.)

## Lineage evidence, independently verified

Pulled both manifests for each of the two colliding bench/file-kind pairs directly from git
(`git show 42fdaf9^:<path>`), not from the resolution commit's prose:

| field | `-suffix` dir (source) | `Ornith-1.0-35B-mlx-uniform-4bit/*.suffixon.*` (target) |
|---|---|---|
| `model` | `Ornith-1.0-35B-mlx-uniform-4bit-suffix` | `Ornith-1.0-35B-mlx-uniform-4bit` |
| `timestamp` | `1783572841` → **2026-07-08 21:54:01** | `1786740653` → **2026-08-14 13:50:53** |
| `git.submodules.src/mlx-vlm` | `f0d50c90e353680bb11a0cc0a329c38cde88934c` | `0c1c8b1729c62c068cebf4ababf932306b38ab29` |
| `kv.max_kv_cache_size` | `262144` | `131072` |
| `fingerprint_version` | absent (pre-fingerprint) | `2` |
| `sampling_profile` | absent | `deployed` |

Identical across both `humanevalplus` and `mbppplus` manifest pairs — this is not
bench-specific noise, it's the same two distinct runs showing up twice.

Content-level check (not just metadata): row-file md5s differ between source and target for
both benches, with identical row counts (100 each — not a truncated/partial duplicate):

| file | source md5 | target md5 | rows (both) |
|---|---|---|---|
| `humanevalplus.jsonl` | `a6855e1687bfdeaf0ad777e618f3fdf1` | `4cc0c99096813b00c41262e66560ec3d` | 100 |
| `mbppplus.jsonl` | `5e8ccd8bd0e9cf1752e01fea4c9aa00b` | `29905d65d78c2038b1a39cb7759e0324` | 100 |

**Verdict: genuinely distinct runs, not duplicate data.** The `-suffix` pseudo-dir is the
original Phase-2 suffix-decoding validation from 2026-07-09 (`src/mlx-vlm` at `f0d50c90`,
262144 cap, pre-fingerprint scheme — consistent with the "Phase-2 #4, 2026-07-09" suffix note
still in `main_models.yaml:143-149`). The kept `.suffixon.*` files are the 2026-08-14 OFAT
ON-arm comparators (`0c1c8b17`, 131072 cap, fingerprint v2). Same nominal tune (suffix
decoding on) but at different code revisions and a different KV cap — exactly the case the
tune-label grammar is supposed to distinguish, and `compare`'s fingerprint-based refusal
(AGENTS.md's suffix section) would treat these as non-comparable regardless.

## Resolution (already applied; recommendation = confirm, don't re-touch)

`fb8e67d` resolved this by giving the `-suffix` dir its own distinct label —
**`suffixon-phase2`** rather than the colliding `suffixon` — so no source file needs deletion
or a manual rename; both runs are preserved side by side. `42fdaf9` then executed
`--apply` with this fix in place: 60 moves / 0 collisions / 4 stamps, and the two source dir
shells are left holding only the non-bench capacity artifacts, exactly as the script's
docstring says it should.

Per-collision resolution, all identical (same lineage argument applies uniformly to all 8):

| # | resolution | applied? |
|---|---|---|
| 1–8 | **rename target**: migrate under label `suffixon-phase2` instead of colliding on `suffixon` (`aime`/`ifeval`/`livecodebench`/`math500` and the two `_samples.jsonl` files carried no collision and moved under the same corrected label for consistency, hence 60 total moves not 8) | **Yes — `42fdaf9`, already in git history** |

This audit independently re-derived the same lineage the `fb8e67d` commit message claims
(timestamps, src/mlx-vlm shas, KV caps, fingerprint versions, and — going one step further —
content md5s the commit message doesn't cite) and it holds up. **No operator action is needed
on the 8 collisions themselves** — they're resolved and safely applied, with both runs
retrievable under `Ornith-1.0-35B-mlx-uniform-4bit/{humanevalplus,mbppplus}.suffixon.*`
(August OFAT) and `.../{...}.suffixon-phase2.*` (July Phase-2), confirmed present on disk:

```
humanevalplus.suffixon.jsonl              humanevalplus.suffixon-phase2.jsonl
humanevalplus.suffixon.manifest.json      humanevalplus.suffixon-phase2.manifest.json
humanevalplus.suffixon.score.json         humanevalplus.suffixon-phase2.score.json
humanevalplus.suffixon_samples_eval_results.json   humanevalplus.suffixon-phase2_samples_eval_results.json
                                            humanevalplus.suffixon-phase2_samples.jsonl
mbppplus.suffixon.*  (same 4 kinds)        mbppplus.suffixon-phase2.*  (same 4 kinds, +_samples.jsonl)
```

**Only remaining open item, not a collision:** the two dir shells
(`Ornith-1.0-35B-mlx-uniform-4bit-kv4/`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit-kv3/`) still hold
`capacity_ladder.jsonl` + `capacity_retrieval.json`, deliberately left by the script since
they're not `<bench>.*` artifacts. That's a separate, smaller decision (whether/how to fold
per-model capacity artifacts into the tune encoding too) — out of scope for this collision
audit and not one of the 8.

## Sources consulted

- `benchmark/bench/migrate_tunes.py` (current, HEAD) — script logic, `PSEUDO_MODEL_DIRS` table
- `docs/superpowers/specs/2026-08-17-tune-encoding-migration-design.md` — D3 spec
- `git log --oneline -- benchmark/bench/migrate_tunes.py` → `2e7dbd3`, `fb8e67d`
- `git log --oneline -- benchmark/results/Ornith-1.0-35B-mlx-uniform-4bit-suffix` → `42fdaf9`
  (apply), `02f3718`, `6e99d8d`, `9b9394c` (original import)
- `git show 42fdaf9^:<path>` for both source and target manifests/rows (pre-migration state)
- `git show fb8e67d` / `git show 42fdaf9` — resolution + apply commit messages and diffs
- Dry-run output from this session: `PYTHONPATH=benchmark .venv-bench/bin/python -m
  bench.migrate_tunes` (no `--apply`)
