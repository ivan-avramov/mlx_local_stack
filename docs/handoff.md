# Handoff — 2026-10-12: P223 chain STOPPED on P280 (opencode 60-min inactivity interrupt); C154 ruled A, probe fix in progress; box crashed idle afterwards

THE one handoff. Read this, then `docs/open-questions.md` C154/C155/C147, `docs/specs/c147-tg1-chain-clearance.md`
(rev 3 + §9), `benchmark/chains/c147/README.md`, `docs/PLAN.md` (M62 row) and `benchmark/chains/README.md`.

## State of the world

- **Box `m5max-128`.** Crashed 2026-10-11 ≈ 23:14 local while idle (no panic report); nothing was running. :8000
  free, no mlx-serve/opencode/chain processes. `main` is ahead of origin (unpushed).
- **P223 chain STOPPED, exit 3** (`$STACK_WORKDIR/c147/`, `chain.rc` = 3, 2026-10-12T03:25Z). s1 pick 1
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`: Python leg 22/22 passed; Go leg aborted on `go/alphametics`
  (`error event / Step.Failed`). Block archived under `c147/s1/incomplete/…20261012T032320`. The archive cannot be
  reused: the probe sha changes with the C154 fix, so the chain restarts from scratch.
- **Cause (P280, C154):** opencode 2.0.20 interrupts any request running 60 min without a durable session event
  (hard-coded TTL; streamed deltas don't count). The request was ≈ 5K tokens of reasoning, then a verbatim loop
  (`S, ` × 37,211) up to ≈ 79.5K tokens, i.e. a runaway the budget would have cut ≈ 2.4K tokens later.
- **C154 RULED A (operator 2026-10-12):** record that exact shape as `nonconv_kind: client_inactivity`, scored
  row, leg continues. TTL topic stays OPEN: re-check on every opencode release.
- **C155 OPEN:** MTP-ON tg1 arm for the agentic axis (M40 never paired it). Needs operator go.

## Queue, in order

1. **C154 probe fix (P282)**, test-first: fixture = the real `go__alphametics` events + export
   (`$STACK_WORKDIR/opencode_transcripts/…s1.opencode_go.20261011T192210-3b124bfe2244/`). Predicate: exactly one
   native error `{"type":"aborted","message":"Session interrupted: inactivity"}`, rc 1, not our own stop,
   trailing export assistant = the live active message with `finish: "error"`, `error.type == "aborted"`,
   `tokens: null`. Any other interrupt reason still aborts. Add `client_inactivity` to `PRECEDENCE`
   (no `POLICY` change → `scaffold_policy_sha256` unchanged). Evidence: trailing reasoning/text chars and
   streamed seconds, labelled uncharged. Update `fake_probe.py`, chain validation and the M62 spec/metrics docs if
   they enumerate kinds. Full suite, then Cursor `gpt-5.6-sol-high` cold review (`cursor-agent -p --output-format
   text --model gpt-5.6-sol-high --mode plan --sandbox enabled --force --trust --workspace <repo>`), records
   under `benchmark/chains/c147/reviews/c154/`.
2. **Smoke chain** (`drive_chain.sh chain s1 reload --smoke`, own out-root `c147-smoke/`) with the new probe sha.
3. **Fresh P223 chain:** `--print-identity` → new `probe_code_sha256`; archive the stopped `c147/` contents;
   `sudo purge`; 140 W / 28 V; `nohup benchmark/chains/c147/drive_chain.sh chain s1 s2 reload --probe-code-sha
   <sha> &`; `caffeinate -ims -w <chain pid>`; watch `RUNLOG.md` (`WATCH`, `ALARM`, `CORRECTION?`). Stop with
   `touch $STACK_WORKDIR/c147/STOP`. Never pool tg1 with M61 `opencode-v2-web` rows.
4. C155 (if approved), then C144 candidates under tg1; README/ranking updates need the operator.

## Box facts (m5max-128)

Go grading needs `aider-benchmark:latest` (P271) and `~/.orbstack/bin` on PATH (config.sh); `sudo purge` before
inject runs (P275); hold `caffeinate` for long runs. Open: P274 load-sensitive real-client tests, P275
free-memory metric, README:802 cross-box wording vs C153 (reconcile). mlx-serve fork golden fixture refresh
owed (fork-only). C149 (worker-side `requests_cancelled` receipt) awaits the operator.

## Rules learned

- opencode 2.0.20: SIGTERM the client first (SIGKILL loses the in-flight message). Write/edit input is `path`;
  shell is `{command, workdir[, timeout, background]}`.
- opencode 2.0.20 `run`: a non-`user` execution interrupt sets exit 1 and emits
  `{"type":"aborted","message":"Session interrupted: <reason>"}`; the interrupted message carries no usage, and
  the worker counts no tokens for a closed stream. The persisted reasoning text is the only size evidence.
- A long "think" can be a verbatim loop; inspect the trailing message text before calling it reasoning.
- Lowering a per-process memory limit below ≈ 400 MiB kills opencode's own server child.

Next decision id C156; discussion ids continue from P286 (P281–P284 this session: A approved, build, docs,
restart precautions; P285 = C155 MTP-ON arm).
