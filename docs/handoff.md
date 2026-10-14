# Handoff — 2026-10-14: P223 (OFF) and M63 (MTP-ON) tg1 chains COMPLETE on m5max-128; analysis + C158 auditor scoring change + write-up next

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

1. **P223 tg1 chain (OFF) — COMPLETE 2026-10-13T12:40Z, rc 0, 0 INCOMPLETE, clean teardown** (≈ 18.4 h; per-session strict: pick 1 s1 42/43, s2 42/43, reload 5/5; pick 2 s1 41/43, s2 42/43 (43/43 lenient); misses = 4 `client_inactivity` + 1 `looping` stop). Paired analysis + README/campaign-results owed (README ranking changes need the operator). Was: RUNNING since 2026-10-12T18:16Z (driver pid 26034, `caffeinate -ims -w`; suite 4527 passed on the merged `main` before launch; docker gate ok, A4 ok; progress: s1 pick-1 python pilot 5 + full 22/22 passed, 0 nonconv, validated 19:20Z; s1 pick-1 go 20/21 validated 22:04Z, 1 `client_inactivity` (`go/alphametics`, loop, ≈ 96 % of budget); s1 pick-2 python pilot 4/5 (`book-store` `client_inactivity`, genuine, 89 % of budget), full 20/22 validated 01:38Z, 2 `client_inactivity` (`book-store`, `paasio`: genuine/meander, 86–89 % of budget; P293 pick-dependent cap); s1 pick-2 go 21/21 validated 04:03Z. **s1 COMPLETE**: pick 1 42/43, pick 2 41/43, all 3 misses `client_inactivity`, 0 INCOMPLETE; s2 pick-2 python 22/22 passed validated 06:25Z (1 nonconv: `beer-song` `looping`, passed lenient only), s2 pick-2 go 21/21 validated 08:53Z (s2 pick 2: 43/43 passed, 1 looping stop); s2 pick-1 python 21/22 validated 10:58Z (`book-store` `client_inactivity`, genuine, ≈ 96 %); s2 pick-1 go 21/21 validated 12:20Z. **s2 COMPLETE**: pick 2 43/43 (1 looping stop), pick 1 42/43 (1 `client_inactivity`); reload control next; C154 tally 4 rows) — `nohup benchmark/chains/c147/drive_chain.sh chain s1 s2 reload --probe-code-sha
   8d1b4c84… &` + `caffeinate -ims -w <pid>`; `$STACK_WORKDIR/c147/` (≈ 20–24 h). Preflight: 140 W / 28 V,
   `docker info`, :8000 free, no busy procs. Watch `RUNLOG.md`; count `client_inactivity` rows (C154 standing item:
   tokens via the model tokenizer from the export's trailing reasoning). Stop: `touch $STACK_WORKDIR/c147/STOP`.
2. **M63 ON arm — s1 COMPLETE (pick 1 43/43, pick 2 42/43); first chain run ABORTED 2026-10-13T20:55Z in s2 (C157 guard race, vanished mdworker; archived `m63/archive.attempt2-p296-abort/`); RESUMED `chain s2 reload` 2026-10-14T05:41Z (driver pid 24227), probe unchanged `8d1b4c84…`.** Resume progress: s2 pick-2 python 22/22 lenient, 21 strict (`poker` looping stop; OFF s2 also 21 strict), 1.13 h vs 2.2 h OFF, validated 06:51Z; s2 pick-2 go 21/21 (1.58 h vs 2.4 h OFF) validated 08:27Z → s2 pick 2 42/43 strict ON (OFF 42/43); s2 pick-1 python 21/22 strict (0.53 h vs 1.9 h OFF; `book-store` converged ON 149 s / 6K — **4 of 4 OFF `client_inactivity` items converged ON**; new ON miss `python/react` looping, OFF passed it) validated 09:10Z; s2 pick-1 go 21/21 (0.94 h vs 1.3 h OFF) validated 10:07Z → **M63 s2 COMPLETE**: pick 1 42/43 strict (OFF 42/43), pick 2 42/43 (OFF 42/43); reload 5/5 (agreement with s1 5/5) → **M63 COMPLETE 2026-10-14T10:44Z, rc 0, 0 INCOMPLETE, clean teardown**; all ON rows committed (`benchmark/results/<model>/opencode_v2_<lang>.m63.{s1,s2,reload}.jsonl`). First run was: CHAIN RUNNING since 2026-10-13T13:42Z (driver pid 43584, `$STACK_WORKDIR/m63/`, ≈ 10–12 h; first attempt refused at start by the busy-process gate because the launch shell's own command line named watched processes — relaunch from a clean shell; archived `m63/archive.attempt1-busy-self/`). Progress: s1 pick-1 python 22/22 strict (0.68 h vs 1.0 h OFF) validated 14:25Z; s1 pick-1 go 21/21 (0.92 h vs 2.7 h OFF; `go/alphametics` converged in 181 s / 6,455 tokens ON vs a looped 60-min cut OFF) validated 15:20Z → s1 pick 1 43/43 ON vs 42/43 OFF; s1 pick-2 python 22/22 (1.7 h vs 3.4 h OFF; OFF 60-min cuts `book-store` 549 s / 21K and `paasio` 553 s / 17.8K both converged ON) validated 17:14Z; P293: 3 of 4 OFF `client_inactivity` items converged ON so far; s1 pick-2 go 20/21 (2.45 h; `go/alphametics` `stalled` at 83.9K tokens ON — OFF passed it: a discordant pair against ON, token gate, not the clock) validated 19:42Z. **M63 s1 COMPLETE**: pick 1 43/43 (OFF 42/43), pick 2 42/43 (OFF 41/43); s2 next. Smoke PASS 13:39Z (rc 0, ≈ 1 h; pick 2 `python/book-store` converged ON in 10 min / ≈ 21K tokens vs cut at 60 min OFF). Smoke was: RUNNING since 2026-10-13T12:41Z (driver pid 33108, `$STACK_WORKDIR/m63-smoke/`; worker verified `--draft-kind mtp`, drafter, `--mtp-verify-scan joint_v1`; first manifest `draft_kind: mtp`, `registry+worker`, registry sha = ON overlay `dc26891b…`). Operator pre-approved 2026-10-12 ("go for the run at first opportunity … without asking"):**
   after P223 ends, `nohup benchmark/chains/c147/drive_m63.sh chain s1 reload --smoke --probe-code-sha <sha> &`
   (`$STACK_WORKDIR/m63-smoke/`), then `drive_m63.sh chain s1 s2 reload --probe-code-sha <sha>` (`m63/`, ≈ 10–12 h).
   Same preflight. Stop and report on any abort or pick-relevant result.
3. **C158 (P294) RULED: Cursor `gpt-5.6-sol-high` is the P201 auditor here (no codex, can't be installed).** The three denied P223 s1 Python fetches are audited `generic` (`benchmark/web_audit_cursor.py`). After M63: `answer_key` accepts the declared auditor set (probe identity → only between chains), regenerate the P223 report (final), write up P223 in campaign-results + README; `git submodule update --force` to the pushed mlx-serve `86921f0` (new serving identity, C144 boundary). 4. **P293 decision after M63** (operator 2026-10-13: C71 kept; decide on M63's evidence how OFF `client_inactivity` rows count — see C154). Analysis per M63 spec (paired ON−OFF, TOST ±5pp, with/without `client_inactivity` items); README/ranking
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

C156 tokenizer warning closed by measurement (false positive). C157 guard race open (fix owed at next identity boundary; P297 runner workaround parked, not cleared). Next decision id C158; discussion ids continue from P293 (P286 uncharged tokens, P287 TTL vs "progress", P288 flaky
real-client tests, P289 M63 build, P290 docker gate, P291 OrbStack, P292 merge before P223).
