# Handoff — 2026-11-03 (session 15 END: Wave 2c complete + pushed; P613 step 1 (B8 + B6 for A7) accepted, gated, pushed; next: P613 step 2)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C275, P617, P616, P615, C274, C273, C272, P613,
P611, P610, P609, C271, P608, P607, C270, …), then `docs/specs/p613-b8-b6-signals.md` v2 (the B8 / B6 contract; §8 choices ruled C274)
and `docs/specs/p613-step1-contract.md` (the step-1 interfaces, the model for step 2's contract), `docs/specs/p426-fable-mtp-recert.md`
v4 §1, §3, §5, §7, §8. Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: "i trust you - keep going
towards certifying MTP for the picks"; updates every 15–20 min; ask only at Go / Accept / pushes / scope changes; lead calls filed in
open-questions as they land.

## THE GOAL (what every step converges on)

Decide, with evidence the operator can act on, whether `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` ships with MTP ON (P426; C204:
the operator makes the call from per-axis signals, no automatic pass / fail). The evidence is ONE generated, deterministic
`benchmark/results/p426/SIGNALS.md` built only from B8-accepted ON / OFF pairs: A7 tg1 (done, provisional), A1 math500, M1 256K memory,
A2 cjudge, A3 vision, A4 reasoning (step 2), the subjective panel (step 3), then the final sheet + a recommendation (step 4). After
that, the same certification for `Qwen3.8-27B-mlx-uniform-4bit` (KV choice, then its MTP re-certification; PLAN). Project goal behind it:
the best local LLMs for 256K agentic coding on this M5 Max, quality over speed.

## FIRST — verify (each "no" is a blocker)

1. Nothing running: no `p426_wave2` / `opencode run` / `mlx-serve` / `local_gate` processes; :8000 free.
2. `main` == `origin/main` `afd6d3e9` + this handoff's docs commit (push it docs-only with the next push); `evidence` == `origin/evidence`
   `b6ec7819`; `git status` clean.
3. `benchmark/results/p426/SIGNALS.md` regenerates byte-identically: `cd benchmark && PYTHONPATH=. ../.venv-bench/bin/python -m
   bench.p426_verify a7 --results-root results/p426 --out <tmp>/B8.json && PYTHONPATH=. ../.venv-bench/bin/python -m bench.p426_signals a7
   --results-root results/p426 --b8 <tmp>/B8.json --out-md <tmp>/S.md --out-json <tmp>/S.json` → `cmp` with the committed three files.

## Next, in order

1. **P613 step 2 (four-eyes light, spec v2 §2 / §3 rules 1–4, 6, 7 / §4 for A1, M1, A2, A3, A4).** Write `docs/specs/p613-step2-contract.md`
   in the step-1 contract's form: the goal paragraph (above, verbatim), the Wave 1 data formats read from the committed files
   (`benchmark/results/p426/wave1.s2/<leg>/<leg>.receipt.json` `verdict` / `speed_valid`; `run/frozen.s2.json` `stack_head_off` /
   `stack_head_on` / `registry_{off,on}_sha`; rows `benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/{math500,cjudge,
   vision_gate}.p426s2-{off,on}-b{1,2}.jsonl`, `math500.*.score.json`, `reasoning.p426s2-*.json`, `wave1.s2/m1-*/m1/<entry>/result.json`),
   exact interfaces extending `p426_verify` / `p426_signals` with Wave 1 subcommands (or one `all` command), the rule-6 cross-wave diff
   (`git diff <frozen.s2 stack_head_off> <v8_base off_commit>` limited to `main_models.yaml`, the `src/*` gitlinks and the
   `identity_closure.python_closure` of `benchmark/run.py`, `benchmark/vision_gate.py`, `benchmark/bench/run_reasoning.py`, M1 `qualify`;
   non-empty → a flag + operator before Wave 1 enters the sheet, C274 Q3), the mechanical family {A1 (both blocks), A7-s1, A7-s2} now
   complete (Holm m = 3), golden numbers (count them from the committed rows first). Wave 1 rows read through `bench.chain_rows` where
   it applies (P617). Go to the operator (cast, below), then implement + test in two worktrees at `main`'s tip, panel, fix, Accept,
   commit, gate the tip (full suite — it caught P617), push with approval.
2. **P613 step 3:** the panel run (spec §5): extend B3 `bench/p426_panel.py` (`build="s2"`; A7 key mapping + packet builder; C217 identity
   gate first — the S build had 166 / 166 Wave 1 pairs identical, so Wave 1 may contribute ≈ 0 packets); freeze the packet set + judges
   from `judges.json` before any verdict; Claude `blind-judge` + GPT-5.6 Sol High via `cursor-agent` (Gemini 3.1 Pro for A3 images).
3. **P613 step 4:** the final sheet; then the MTP certification call to the operator: per-axis signals, flags with their item
   crosswalks, a recommendation (registry change only with approval; certified triple per PLAN M6d; client configs per AGENTS).
4. Quiet windows: the Wave 1 ON head `f2b61127` (local branch `archive/p426-wave1-s2-on`) — gate it, then push with approval;
   **P602 = build P383 per plan v4**; C258 crossover (P577 (a)); P503 fixes (C261); P576; opencode 2.2.5 re-pin (C269 B′); M65 pilot
   universe rebuild under v3 (P607 follow-up).

**Four-eyes cast on this box** (`~/.config/review-panel/panel.toml`: sol, glm, sonnet; no codex): the auto-mode classifier DENIES a
write-capable `cursor-agent --force` run (P615), so implementer = a fresh Claude Opus 5.5 session (`claude -p --model opus <!-- allow-shorthand: CLI alias -->
--setting-sources "project,local" --tools "Read,Edit,Write,Grep,Glob,Bash" --permission-mode acceptEdits`), test-writer = Claude Sonnet
5.5 (`claude -p`, resumable with `--resume <session_id>`), panel = GPT-5.6 Sol High (`cursor-agent -p --trust --mode ask --model
gpt-5.6-sol-high`, read-only — allowed). Helpers read only inside their worktree: copy material into `<worktree>/.p613-material/`.
Briefs are built with Python, never an unquoted heredoc (backticks run).

## State — 2026-11-03

- **Wave 2c** (v8 `353ff506…`, arms `4adb596a` OFF / `46ca41b9` ON): 8 legs VALID, dossiers pilot / s1 / s2 / reload PASS; harvested
  `main` `d23d019d`, `evidence` `b6ec7819`; pushed.
- **Provisional A7 sheet** (`5dd19e23`, regenerated unchanged after P617): strict s1 OFF 42/43 vs ON 41/43 (−2.3 pp [−7.0, 0.0], WASH,
  loss bound 7.0 pp ≤ 10), s2 41/43 vs 42/43 (+2.3 pp [0.0, +7.0], WASH); decode ON / OFF 1.65× (s1 [1.63, 1.68], s2 [1.63, 1.67]);
  ON acceptance 0.775 / 0.770; leg wall OFF 13,654 / 14,464 s vs ON 8,763 / 9,633 s; noise floor 0 / 5 both arms (same epoch), OFF 0 / 48
  and ON 1 / 48 (cross epoch); flags = cut-off differences + the P611 flip (P616 crosswalk). Holm family PROVISIONAL (A1 pending).
- **P613 step 1** code `369831ed` + P617 `afd6d3e9` (full gate PASS 10,238); reviews / dispositions `docs/reviews/p613-step1/`.
- **P606 done:** ON archives pushed (`archive/p426-wave2.v8-af0711cf-on` `2a173f8b`, `…-4104c7fc-on` `7a0817d3`, `archive/p426-wave2-on`
  `46ca41b9`), each level full on its own receipt. Every Wave 2 arm commit resolves publicly; the rehearsal arms stay local (C271).
- **C273:** the tool-visible wall clock stays (P611 (A)); 49 / 49 diverged items first differ in a tool output (timestamps 47, ASLR 2).

## Worktrees / scratch (each with its resolution)

- `stack-p426-off`, `stack-p426-on` (`p426-off` / `p426-on`, both pushed as archives): remove after step 2 (rule 6 needs only the commits).
- `stack-c258x-off` (`c258x-off`): keep for P577; remove after.
- Local branches: `archive/p426-wave1-s2-on` (`f2b61127`, gate + push pending), `archive/p426-rehearsal.20261102a-{off,on}` (stay
  local, C271), `archive/p426-wave2*` (pushed).
- `$STACK_WORKDIR/p426/wave2/`, `p426/wave2b/`, `p426/wave2c/` (all harvested), `p426/rehearsal/*` (`20261102a` cited by the Wave 2c v8):
  delete after an inventory table. `$STACK_WORKDIR/scratch/superseded-wave2*-untracked*/`, `evstage-*` (committed), `p586-4eyes/`,
  `p602-review/` (the shelved minimal patch), `p603-p604-review/`, `p604-universe/`, `harvest-v8b-*.txt`, `gate-*.txt`: delete after the
  inventory. `scratch/p594-opencode-2.2.5/`: keep for the re-pin. `$STACK_WORKDIR/c258x/` (scrub the charger serial before any harvest).

## Rules learned (session 15)

- The full suite gates every accepted change before its push — targeted suites missed P607's pins and P617's R7 invariant.
- A push needs a PASS receipt on the exact pushed sha; push the gated sha (`<sha>:main`), then later docs / data commits on their own.
- Each push's introduced commits must be all-docs, all-data or gated (P541): push a mixed run in homogeneous slices.
- An ON arm (one commit on its OFF arm) needs its own receipt (P606); a commit on no branch is lost to `git gc` — branch it at once.
- A recorded hash of a verdict is not a verdict: a precondition opens what it cites (P609).
- Same seeds do not reproduce a long agentic item: tool outputs leak the clock (P611 / C273); compare transcripts, never trust a rerun.
- A pre-registered flag can fire on a cut-off asymmetry: every flag carries its items and both arms' endings (P616).
- A golden number in a contract is counted from the data with the contract's own definition before it is written (strict ≠ lenient).

## Rules learned (session 14, carried)

- A guard's "fails safe" claim must hold for the largest gap the mechanism allows (DST hides exactly 3600 s; sol r2 P1).
- A default argument binds at import (`run=subprocess.run` defeated the test fakes; the "stall").
- Never put backticks in an unquoted heredoc that builds a brief (the shell runs them); a re-cut runs under `set -e`, never `;`-chained.
- File names can look like addresses (`compile@go1.27.3-…count`); a main-bound index must not list private names (P599).
- Dry-run the harvest over every real tree before relaunch (found P599).
- A piped capture of a client that exits can lose its tail at the pipe buffer: capture large outputs to files (P603).
- A grader's "infrastructure" class must be attributable: protected inputs failing = infra; the model's own files failing = a scored
  fail (P604 review).
- A planned fix may never have been built: check the code, not the ruling (C180 / P383 → P602; B6 / B8 → P613).

Next decision id C276; discussion ids continue from P619.
