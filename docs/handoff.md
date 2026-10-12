# Handoff — 2026-10-12: C154 + P290 + M63 merged and pushed; fresh P223 tg1 chain launching on m5max-128; M63 ON chain pre-approved to follow

THE one handoff. Read this, then `docs/open-questions.md` C154/C155/C147, `docs/specs/m63-mtp-on-tg1-arm.md`,
`docs/specs/c147-tg1-chain-clearance.md` (rev 3 + §9, B12), `benchmark/chains/c147/README.md`, `docs/PLAN.md`
(M62, M63 rows).

## State of the world

- **Box `m5max-128`.** Crashed 2026-10-11 ≈ 23:14 idle (no panic report); OrbStack did not restart (P291; the
  operator turned start-at-login ON 2026-10-12). Docker 29.4.0, `aider-benchmark` image present.
- **Code on `main` (pushed 2026-10-12):** C154 (`client_inactivity`, reviewed ×2), P290 (docker gate before Go legs,
  reviewed), M63 (`--predictor mtp`, own out-root `m63/`, shipped-predictor worker tripwire, reviewed ×4 → cleared).
  Probe sha `8d1b4c84c14f8dd20a8a9f1883b177813130c5057bb09886df61d39cdb116562` (P290/M63 do not touch the probe);
  `scaffold_policy_sha256` `ba86ba16…` (campaign pin). Reviews: `benchmark/chains/c147/reviews/{c154,p290,m63}/`.
- **C154 smoke chain PASS 2026-10-12** (`$STACK_WORKDIR/c147-smoke/`, `chain s1 reload --smoke`, rc 0, attempt 2;
  attempt 1 aborted on docker down, archived `archive.c154-attempt1-docker-down/`). Live `client_inactivity`:
  `Qwen3.8-27B-mlx-uniform-4bit` `python/book-store`, 75,787 tokens (93 % of budget), genuine reasoning, row scored.
- **Archives:** first P223 attempt `c147/archive.p223-attempt1-p280/` (stopped on P280); not reusable (probe sha).

## Queue, in order

1. **P223 tg1 chain (OFF)** — `nohup benchmark/chains/c147/drive_chain.sh chain s1 s2 reload --probe-code-sha
   8d1b4c84… &` + `caffeinate -ims -w <pid>`; `$STACK_WORKDIR/c147/` (≈ 20–24 h). Preflight: 140 W / 28 V,
   `docker info`, :8000 free, no busy procs. Watch `RUNLOG.md`; count `client_inactivity` rows (C154 standing item:
   tokens via the model tokenizer from the export's trailing reasoning). Stop: `touch $STACK_WORKDIR/c147/STOP`.
2. **M63 ON arm — operator pre-approved 2026-10-12 ("go for the run at first opportunity … without asking"):**
   after P223 ends, `nohup benchmark/chains/c147/drive_m63.sh chain s1 reload --smoke --probe-code-sha <sha> &`
   (`$STACK_WORKDIR/m63-smoke/`), then `drive_m63.sh chain s1 s2 reload --probe-code-sha <sha>` (`m63/`, ≈ 10–12 h).
   Same preflight. Stop and report on any abort or pick-relevant result.
3. Analysis per M63 spec (paired ON−OFF, TOST ±5pp, with/without `client_inactivity` items); README/ranking
   changes need the operator. Then C144 candidates under tg1.

## Rules for this session's work

- Never edit the main checkout's runner/`chain_ops`/probe files while a chain runs (`chain.json` re-hashes them per
  write; probe identity files abort the next leg). Build in a worktree under `$STACK_WORKDIR/worktrees/`, merge after.
- Never run the full suite while a chain runs (real-client tests spawn opencode; the chain's checks see them).
- Pushes need operator approval each time (the 2026-10-12 push covered that one push).

## Box facts (m5max-128)

Go grading: `aider-benchmark` + `~/.orbstack/bin` on PATH; `sudo purge` before inject runs (P275); `caffeinate` for long
runs. Load-sensitive real-client tests flake under the full suite (P274/P288: `test_c147_cancel` long-tool-call,
`test_m61_p202` cheat rerun); each passes alone. Open: P275 free-memory metric, README:802 cross-box wording vs C153,
mlx-serve fork golden fixture refresh, C149 awaiting the operator. P290 note: OFF-side tripwires got stricter with
M63 (exact `--model`, strict flag parsing); a refusal there is an early clean abort, never wrong rows.

## Rules learned

- opencode 2.0.20: 60-min inactivity TTL per request (C154); SIGTERM the client first; write/edit input `path`.
- A long think may be a verbatim loop OR genuine reasoning; tokenize the trailing reasoning before calling it either.
- After a reboot, check `docker info` before any Go leg.

Next decision id C156; discussion ids continue from P293 (P286 uncharged tokens, P287 TTL vs "progress", P288 flaky
real-client tests, P289 M63 build, P290 docker gate, P291 OrbStack, P292 merge before P223).
