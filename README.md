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
