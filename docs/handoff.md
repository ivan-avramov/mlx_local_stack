# Handoff — 2026-09-13 ~00:45 PDT (M40 chain LIVE on pick B; pick A CERTIFIED ON)

Rewritten in place. Phase 1 closed (B ladder C57, C ladder C70). Phase 2: **M40 (MTP-ON certification of both
picks) is RUNNING unattended** under the reviewed chain runner. **Pick A `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
is DONE and CERTIFIED ON on all four axes** (entry `docs/campaign-results.md` 2026-09-13; registry comment
`# CERTIFIED M40 2026-09-13`; data commit 018db56). Pick B `Qwen3.8-27B-mlx-uniform-4bit` started 00:28 PDT.

## Resume checklist (do these FIRST, in order)

1. **Runner alive?** `. ${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh; Q=$STACK_WORKDIR/queue/m40_mtp;
   ps -o pid,etime,command -p $(cat $Q/queue.pid)` — expect `run.py` (pid 74875, started 2026-09-12 20:58 PDT).
   If gone: `grep -E 'FATAL|=== M40' $Q/queue.log` — a FATAL preserves state; read the traceback before touching
   anything. NEVER restart the runner while a `run.py generate`, `vision_gate.py` or `bench.run_reasoning` driver
   or an `mlx_vlm.server` worker is alive (`pgrep -fl`). The three `=== M40 … DONE ===` lines stamped 20:52–20:57
   are dry-runs; the live pick A DONE is stamped 2026-09-13 00:28:47.
2. **Progress**: `grep -vE HEARTBEAT $Q/queue.log | tail -20` (grammar: RUN / C35 check / worker cmdline / PILOT /
   END / SUMMARY / SCORE / RESULT / WARN / FATAL / `=== M40 <pick> DONE ===` / `=== M40 MTP QUEUE DONE ===`);
   HEARTBEAT lines with `partial_bytes=0` are normal during a depth arm (the driver writes per completed rung).
   Pick B order: ON overlay → math500 `m40on` (pilot projected 30 min for 100) → cjudge `m40on` → vision_gate
   `m40on` → depth `m40on-d128k` → humanevalplus + mbppplus `m40on` → OFF overlay → depth `m40off-d128k` →
   vision_gate `m40off` → humanevalplus + mbppplus `m40off` → DONE → `=== M40 MTP QUEUE DONE ===`. Verify the exact
   order from the RUN lines, not from this note.
3. **Re-arm supervision** — one event Monitor on `$Q/queue.log` (tail -F + `/usr/bin/grep --line-buffered`
   alternation FATAL/TIMEOUT/WARN/MISMATCH/RESULT/DONE/Traceback/PILOT/`pass count` + a runner-exit loop on the pid
   + a SELFTEST known-positive echo). Never narrate ticks. The `WARN … no reachable draft/speculative-decode counter`
   line after every depth/vision arm is the known limitation, not a fault.
4. `git status`: `main_models.yaml` carries intentional local-path overrides — NEVER stage it from the worktree
   (HEAD-blob technique: `git show HEAD:main_models.yaml` → patch → `git hash-object -w` → `git update-index
   --cacheinfo 100644,<blob>,main_models.yaml`; `docs/qualify-a-model.md`). Pick B rows appear under
   `benchmark/results/Qwen3.8-27B-mlx-uniform-4bit/*m40on*|*m40off*|*d128k*` as they land — commit them as one
   `data(bench)` unit at pick B DONE. Provenance jsons carry the worker cmdline with absolute paths: replace
   `/Users/<u>/…/mlx_local_stack_workdir` → `$STACK_WORKDIR` then `…/mlx_local_stack` → `$STACK_REPO` before staging
   (piicheck blocks otherwise). The modelnames hook false-positives on the judge key `opus` in machine-written <!-- allow-shorthand -->
   `gate.json`; commit judge dirs with `--no-verify` after running piicheck by hand (M38 precedent d7f2d8c). <!-- allow-shorthand -->
5. Unpushed: `git log --oneline origin/main..main`. Push ONLY on explicit in-turn approval.

## Pick B analysis owed at its DONE (pre-registered, PLAN M40 row; mirror the pick A entry)

- `cd benchmark && ../.venv-bench/bin/python -m bench.compare_predictor --model Qwen3.8-27B-mlx-uniform-4bit --bench math500 --tune-a m37med --tune-b m40on`
  — CHECK FIRST which OFF tune holds pick B's matched Math500 row (`ls benchmark/results/Qwen3.8-27B-mlx-uniform-4bit/math500.*`);
  the tool refuses unless only `draft_kind` differs — a refusal is a finding. Coding: `--bench humanevalplus` and
  `--bench mbppplus` with `--tune-a m40off --tune-b m40on`. Read per C72: PASS if CI within ±5pp OR the discordant set
  has zero OFF-only wins; FAIL if CI excludes 0 on the negative side or point < −5pp; else INCONCLUSIVE (report as such).
- cjudge: `run_judge_pairwise --models Qwen3.8-27B-mlx-uniform-4bit --pair-tunes m38 m40on --anchors results/judge_c_v1/pairs.jsonl
  --judges opus sonnet --out results/judge_m40/Qwen3.8-27B-mlx-uniform-4bit --export-packets $STACK_WORKDIR/m40_packets_Qwen3.8-27B-mlx-uniform-4bit --batch-size 20` <!-- allow-shorthand -->
  (**always pass `--out`** — without it the tool overwrites `results/judge_c_v1/pair_manifest.jsonl`); 16 blind
  subagents (one per `<judge>/batchNN`, model = the judge; rules inline: read only own packet, write only the named
  `.verdict.json`, never `manifest.jsonl`); codex in-process in parallel: same command with
  `--judges codex:gpt-5.6-terra:medium --allow-single-family` and no export flag (nohup, ~35 min for 140 calls);
  `--ingest-packets <dir>`; `judge_gate --pairs <out>/pair_manifest.jsonl --verdicts <out>/verdicts.jsonl --judges sonnet opus codex:gpt-5.6-terra:medium --out <out>` <!-- allow-shorthand -->
  (`--out` is a DIRECTORY; it writes `gate.json` + `ranking.json` inside — pass the results dir, not a filename).
  Read: FAIL only if OFF preferred with Holm p<.05; else "no detectable drift at n=40 (MDE ±20pp)".
- vision: `vision_gate.m40on.summary.json` vs `.m40off.` (ON ≥16/20 and ≥OFF−2). depth: `reasoning.m40on-d128k.json`
  vs `m40off-d128k` (strict draws ON ≥ OFF−1 of 3, budget-hits not higher). Perf separately: acceptance from rows'
  `draft` field (math/cjudge/coding rows only), decode_tps, wall; runaway tax in TOKENS.
- Decision rule: all pass → pick B ships ON (registry already ON; add `# CERTIFIED M40 <date>` comment via HEAD blob
  in the SAME commit as the campaign-results entry). Any FAIL → PROPOSE flipping `draft_kind` OFF for pick B; never
  auto-change. Then README evidence (B row 2 + C row 2 + a paragraph under "### C evidence"), PLAN M40 row → done,
  open-questions if a decision arises. Then `=== M40 MTP QUEUE DONE ===` closes M40; next is M41 (needs its own go).

## Pick A result (for reference; full entry in campaign-results 2026-09-13)

Math500 99 % ON vs 97 % OFF (+2pp, CI [0,+5], 0 OFF-only wins → PASS by C72; tool says INCONCLUSIVE at the edge);
judge OFF-pref 0.40 [0.29,0.53] Holm p=.10, gate PASS 6/6; depth 128K 3/3 both; vision 20/20 both. Decode ×1.93
math (acceptance 0.78), ×1.5 prose (0.62), ×2.5 at 128K; wall ratio 0.55; tokens/task 1.00 [0.81,1.27].

## After M40 (Phase 2 queue, PLAN "Phase 2" section)

M41 capacity + depth ladders on pick A predictor-ON (its first long-context evidence; 256K `mx.get_peak_memory`,
reasoning + retrieval ladders, decode/prefill per rung) → M42 KV-lever OFAT (fp16 vs turboquant kv4) → D14 transfer
write-up (zero GPU, parallel). Each arm needs its own explicit go. Candidates screened and dropped 2026-09-13: C73.

## Ladder of record

B (C57): 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 2nd `Qwen3.8-27B-mlx-uniform-4bit`, 3rd
`Ornith-1.0-35B-mlx-uniform-4bit`, 4th `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. C (C70, provisional): 1st
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 2nd `Qwen3.8-27B-mlx-uniform-4bit`; shortlist
`Ornith-1.0-35B-mlx-uniform-4bit`, `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`.

## Bookkeeping

- Next discussion point P354; next C id C74.
- Pre-existing unrelated lint failure: `test_no_bare_distill_shorthand[qualify-a-model.md]` (docs debt, not touched).
