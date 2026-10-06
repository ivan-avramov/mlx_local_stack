# Proposal: seeded opencode sessions (C121, operator GO 2026-10-06)

Status: APPROVED for build (operator "c121: go", 2026-10-06). Found by the ReviewBench cold review (R1, R8; verified). No rerun of
existing rows; this changes the scaffold for FUTURE opencode rows and corrects the record for past ones.

## The defect (verified)

- `benchmark/run_opencode_probe.py` never sends a seed: the command is `opencode run --dir <cwd> --model mlx-local/<model> [--pure] <prompt>`;
  rows hard-code `"sample": 0`; `opencode_config/opencode.json` model `options` carry sampling fields but no `seed`.
- The fork server normalizes a missing `seed` to `DEFAULT_SEED` (`mlx_vlm/server/generation.py`, O30 comment): every opencode request
  so far ran on the same seed. M53/M55 "two independent sessions" were therefore correlated replays (M54 AgentBench was seeded, base 0, with the same schedule in every session) (same seed, same prompts;
  only the server state differed); k=2 variance is understated; the same-seed reload control proved nothing it was meant to.
- `docs/specs/m55-polyglot-gap.md` says "same seeds as M9/M32" — not what happened. Retract in `docs/lab-notebook.md`; label the
  rows "unseeded (server default seed)"; keep them (ranks were stable across arms; no rerun).
- R8: the probe never sets opencode's Claude-Code-instruction-file switch, so opencode may load `~/.claude/CLAUDE.md` (the file exists on the
  box, dated 2026-09-08; the first draft assumed it absent) into the system prompt. Not observable from transcripts. Fix in the same change; record the switch in the manifest.
- Scaffold: the probe pins opencode 1.18.30, installed outside the repo under `$STACK_WORKDIR` (C123); the brew-installed binary is a
  different major version and is never used. Seeded rows are a NEW scaffold epoch and never pool with earlier rows.

## Design (P107–P110)

- P107 Mechanism: per-item PROJECT config written by the probe into the item's scratch dir — `<cwd>/opencode.json` containing ONLY
  `{"provider": {"mlx-local": {"models": {"<model>": {"options": {"seed": <N>}}}}}}` — merged by opencode over the shipped global config.
  No `OPENCODE_CONFIG*` env (the M50 tripwire refuses those, by design). The probe hashes the overlay and asserts, via
  `opencode debug config --dir <cwd>` on the pre-check item, that the resolved provider baseURL is unchanged and the resolved model
  options contain the seed. The model can see the file in its cwd (one small JSON; harmless, recorded as scaffold).
- P108 Seed schedule: one seed per (session, item): `rowschema.sample_seed(item_id, sample, base=session_seed_base)` with
  `session_seed_base` from `--seed-base` (required, no default; manifests record it). Two sessions use distinct bases; the reload
  control reuses a base. Every row carries `sampler_seed`, `seed_base`, `overlay_sha256`.
- P109 Proof, not assumption: an integration test runs the pinned opencode against a local mock OpenAI-compatible HTTP server (no
  GPU, no router) and asserts the captured request body carries `"seed": N` and every deployed sampling field from the shipped
  config; skipped with a reason when opencode is not installed. The probe's manifest records `seed_propagation: "verified-by-test"`
  only when that test passed in CI for the pinned version; otherwise `"unverified"` and the row is flagged.
- P110 R8 switch: set the opencode environment variable that disables Claude-Code instruction-file loading (verify the exact name for
  1.18.30's binary strings; do not guess), alongside `OPENCODE_DISABLE_EXTERNAL_SKILLS=true`; fold both into the recorded
  skill-policy/config hash so pre- and post-change rows never pool.

## Acceptance criteria

- AC1 Overlay [amended]: for item X and seed base B the probe writes `<cwd>/opencode.json` with exactly the seed key for the served
  model PLUS the session-title switch `agent.title.disable: true` (1.18.30 would otherwise send an un-seeded title request to the task
  provider); sha256 recorded in the row and in the manifest per item; nothing else is overridden.
- AC2 Seeds: distinct per item within a session, reproducible across sessions with the same base, distinct across bases
  (`rowschema.sample_seed`); `--seed-base` required.
- AC3 Propagation [amended]: mock-endpoint integration test, in a git-initialised dir under the bench config home with a hermetic env, captures
  the request body with `seed` and the deployed fields and no title request; skip-with-reason when opencode is absent; version-pinned. The
  receipt (`seed_propagation: verified-by-test`) binds the executable, the bench carrier and the test file.
- AC4 Pre-check [amended 2026-10-06, operator]: the probe runs opencode under a bench-owned `XDG_CONFIG_HOME`
  (`$STACK_WORKDIR/opencode-probe/config-<run-id>/`, a verbatim copy of `benchmark/opencode_bench.json`, nothing else); M50 discovery and the
  per-item `opencode debug config` run under that env; resolved baseURL unchanged and resolved model options == bench block plus the seed (and `limit` == bench `limit`, no `instructions` key),
  else refuse (M50 shape). The personal `~/.config/opencode` is never read.
- AC5 [resolved: the bench config home carries no global `AGENTS.md`; ancestor-chain instruction files and `~/.claude/CLAUDE.md` are an OBSERVED inventory (`instruction_sources_sha256`, manifest only; NOT part of the scaffold-policy hash, the resume identity or the receipt, because git init blocks them); the scaffold-policy hash covers the bench carrier sha, overlay schema, applied switches, `scratch_git_init`, bench-HOME isolation, opencode version + exe sha and the empty `instructions` rule; item dirs are `git init`-ed; 1.18.30 has `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT` and the broad `OPENCODE_DISABLE_CLAUDE_CODE`; `~/.claude/CLAUDE.md` exists on the box; manifest records `claude_md_present`] R8 switch set and recorded; config/skill-policy hash changes; old rows do not pool (compare refuses).
- AC6 [REPLACED by C123, 2026-10-06] Re-pin to 2.0.20 is WRONG: v2.0.20 lacks `--dir`/`--pure` and forwards no model `options` into the request. Keep `PINNED_OPENCODE_VERSION = "1.18.30"`; the probe resolves the binary from `$STACK_WORKDIR/opencode-1.18.30/node_modules/.bin/opencode` (or `OPENCODE_PROBE_BIN`) and records its portable path in the manifest.
- AC7 Record: lab-notebook retraction entry; `docs/specs/m55-polyglot-gap.md` and `m54-agentbench-os.md` annotated "sessions were
  unseeded"; README/campaign-results evidence rows carry the label where they cite k=2 sessions.

Out of scope: rerunning M53/M55; AgentBench OS (`run_agentbench_os.py` talks to the router directly and already seeds per item —
verify and state it in the notebook entry rather than assume).
