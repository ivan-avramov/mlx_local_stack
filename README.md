# evidence (orphan branch)

Raw, irreproducible artifacts behind committed `main` rows, published 2026-10-10 (P229) so the repo
survives loss of the operator's machine. Layout mirrors `$STACK_WORKDIR`; restore with
`git fetch origin evidence && git archive origin/evidence | tar -x -C "$STACK_WORKDIR"`.

- `opencode_transcripts/` — opencode session exports/events behind the M59/M61/M62 rows; the frozen
  M62 replay manifest (`benchmark/m62/replay_manifest.json` on `main`) pins 908 of these by sha256.
- `m54/arms_*/transcripts/` — AgentBench OS sessions behind the M54/M55 rows.
- `aider/model-metadata.local.patch` — the local model-metadata registration the frozen aider rows ran with.
- `upstream/*/quality*` — C82/C84 upstream-parity generations, grades and analysis.
- Serving overlays (`m54`, `m57`, `m58`, `m59`, `queue/m40_mtp`, `queue/m41_ladders`), OptiQ sensitivity
  checkpoints and text-only configs (`optiq_out/`), docs-cited reports, and the operator's milestone
  driver scripts and notes.

Personal data was rewritten before commit (home paths → `$STACK_WORKDIR` / `$STACK_REPO` / `$HOME`,
username → `<user>`, hostname → `localhost`); files were scanned for credentials and none were found.
`SCRUB_MANIFEST.json` lists every file's original and published sha256; files with equal hashes are
byte-identical to the originals.

Excluded: the opencode 1.18.30 transcripts (frozen 1.18 probe, M46–M55 Java/JavaScript/Rust and early
checks). That scaffold loaded the operator's private global instruction file into the model's context and
sessions paraphrase it; the rows on `main` remain, the raw sessions are not published. Model weights are on Hugging Face (`caslca/*`), not here.

## 2026-10-22 backfill (P438 / C211 / C212)

Cited, previously local-only workdir directories: `p400/perf` (P405 R4 / R5), `p415/r7` (R7 256K qualification), `p369/phase2`
(P369 phase 2 E1c / E2), `p422`, `c147`, `c147-smoke`, `c144-base`, `m62/inject`, `reviews/p434` (raw Cursor transcripts).
Staged by `benchmark/bench/evidence_backfill.py` on `main`: scrubbed as above; files over 8 MB published as `<name>.xz` of the
scrubbed text; venvs / caches / `tmp/` skipped. `backfill/2026-10-22-p438/BACKFILL_MANIFEST.json` lists every file's
original, scrubbed and published sha256. The 330 `p369/phase2/**/*.npz` arrays (18.9 GB) are NOT here: they are on the public
Hugging Face dataset `caslca/mlx-local-stack-evidence` at the same paths; `EXTERNAL_MANIFEST.json` pins each one's sha256 and
size (verified equal to the hub's LFS sha256, 330 / 330).

## 2026-10-22 backfill 2 (P450 v3 / C216)

Only the raw files that committed rows / docs on `main` cite and that were local-only: 6,579 opencode transcript files
(`opencode_transcripts/…`: events streams, grade reports, stderr — behind the M59 / M61 / M63 / P223 / c144 tg1 rows and their
web audits), the cited `c144-base.archive/attempt1-guard-residual` directory, and `p441/upload.log` (the HF upload of the
p369 arrays). Exact cited paths, no renames; scrubbed as above; `backfill/2026-10-22-p450/BACKFILL_MANIFEST.json` lists every
file's original, scrubbed and published sha256. Process artifacts (session-gate sandboxes, probe DBs / snapshots / logs,
campaign process logs) were deliberately NOT backed up: they are how the results were produced, not results. 203 cited
transcript paths were absent from the m5max-128 workdir (likely on m5max).
