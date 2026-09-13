# Qualifying a new model — the agent-facing playbook

Agent-facing. States the rule, the command, the threshold. Rationale and history live in the
linked docs — do not re-derive it here. Run every command from `$STACK_REPO` unless noted.
`$STACK_REPO` = this repo's checkout root; `$STACK_WORKDIR` = the dedicated out-of-repo workdir
(`${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh` sets both on this box — never
hardcode an absolute path in anything committed).

Read `AGENTS.md` in full before starting. This doc sequences its rules into stages; it does not
replace it. When this doc and `AGENTS.md` disagree, `AGENTS.md` wins — file a correction here.

---

## Role gate — which stages apply

Not every candidate runs every stage. Determine the target role(s) FIRST, then use this table
to scope the work; Stages 1, 2, 3 (F0–F2), 13 and 14 are the only universal ones.

| Role | Mandatory | Conditional (run on trigger) | Not applicable |
|---|---|---|---|
| **B — agentic coding** | 1, 2, 3 (F0–F2), 8, 13, 14 | 3-vision (only if this pick must also serve a vision-required slot), 4 (temperature ladder, triggered by F1/F2 non-convergence), 5 (family exposes `reasoning_effort`), 9 (native MTP head present), 10 (native MoE architecture) | 6 (Math500/IFEval/GPQA — role C's proxy), 12 (judge panel — role C only) |
| **C — research/design** | 1, 2, 3 (F0–F2), 6, 12, 13, 14 | 3-vision (only for the vision-gated C slot), 4, 5, 9, 10, 8 (agentic legs — informative for C, not required) | 7 (depth ladders — role B's long-context axis) |
| **Vision-required daily-driver slot** (either role, when the SLOT itself requires sight) | 3-vision becomes MANDATORY, not conditional | — | — |
| **Native MoE architecture** (`qwen3_5_moe` / `nemotron_h`) | — | 10 (attempt the pilot; a CLOSE verdict is a valid, complete outcome — see Stage 10), 9 (many MoE checkpoints also ship a native MTP head) | — |

Stage 11 (KV-cache options) is reference material folded into Stage 1's registration and Stage
2's capacity gate, not a separate GPU-time stage — read it once per new architecture, not once
per candidate.

---

## 0. Ground rules that apply to every stage

Full derivations: `docs/metrics.md`, `docs/serving-path.md`, `AGENTS.md`.

- **One resident model, always.** Before loading the candidate: `POST /v1/models/unload` +
  `pkill -f bench.run_*` if anything is resident. Verify with
  `lsof -nP -iTCP:8000 -sTCP:LISTEN` (listener count, not `pgrep -f "mlx-serve start"` — that
  counts the `uv run` wrapper too).
- **Router start:** `set -a; . ./.env 2>/dev/null; set +a; MLX_VLM_CACHE_SESSION_MAX=2
  MLX_SERVE_CONFIG=<overlay-or-main_models.yaml> nohup uv run mlx-serve start
  >logs/main_model.log 2>&1 </dev/null &`. `MLX_VLM_CACHE_SESSION_MAX=2` is MANDATORY (unset
  defaults to 8 retained sessions → OOM risk under benchmark traffic).
- **APC must be absent** from both router and worker env. Verify on the router PID AND the
  worker PID (worker inherits): `ps -Eww -p <pid>` must show no `APC_ENABLED`.
- **Every driver launch carries `MLX_SERVE_CONFIG` in its own env** (C35), pointing at the
  exact overlay being served. `paths.registry_path()` reads it for the fingerprint; without it,
  manifests record the registry-of-record's config while the worker may be serving something
  else. Verify the FIRST manifest of every arm: `runtime.draft_kind` and `registry.sha256`
  must match what the worker is actually running (`ps -o command=` on the worker PID). See
  Appendix A for the check in code.
- **`--sampling-profile deployed` is REQUIRED on every `generate`/`run_reasoning` invocation**
  (O36). `deployed` reads `main_models.yaml` `generation_defaults`; `production` is a frozen
  legacy table for old rows only — never use it for a new model.
- **Every draw carries an explicit seed** (`rowschema.sample_seed(item_id, sample)`, automatic
  in `run.py`). Without an explicit seed, unseeded HTTP requests are byte-identical within a
  server session — `--samples k>1` collapses to k copies. Seeds are NOT guaranteed identical
  across a router restart — a cross-restart A/B needs in-process logit comparison
  (`scripts/graft_logit_check.py` pattern), not an HTTP byte-diff.
- **Thinking is ON for every test, always.** A budget-hit is a FAIL signal to investigate, never
  fixed by lowering the budget. Set `thinking_budget` as generous fixed headroom (81920 for the
  Qwen-family convention in this registry); never compare two runs that differ only in budget.
- **`converged = (finish_reason=="stop" AND completion_tokens < resolved_thinking_budget)`.**
  The resolved budget is `min(declared_thinking_budget, int(min(max_tokens, max_kv_cache_size -
  prompt_tokens) * 0.8))` — a SILENT clamp inside the fork. Before spending worker time on any
  arm, check `max_tokens <= max_kv_cache_size - <your longest prompt>`; if not, you are
  measuring a budget you did not choose. `run.py grade` applies this correction automatically
  (`convergence.resolved_thinking_budget`); never quote "% of budget" without naming which one.
- **`acc_strict@<budget>` is the ranking key** at a matched budget (DNF counts as failure in the
  denominator). `pass@1|converged` is a DIAGNOSTIC ONLY — never rank on it (it conditions on a
  model-dependent, easier subset).
- **Report the four numbers, never a composite:** (1) capability ceiling (`acc`/`acc_strict` +
  CI + exclusive-solve sets), (2) edit competence (well-formed/malformed/context-exhaustion
  rate, agentic legs only), (3) latency per task (mean/median/p95), (4) runaway tax (rate +
  wall-clock share). Never rank on `successes_per_hour`.
- **MDE table (paired, α=.05, power=.80, default p_d=0.20):** N=15→±32pp, N=40→±20pp,
  N=100→±12.5pp, N=164→±9.8pp, N=378→±6.4pp. Never print a delta without its CI and the axis
  MDE. "Inconclusive" is a valid, complete finding on its own axis — it is never by itself a
  reason to drop or promote a candidate; still report effect size, trend and sample size, and
  make the best-evidence recommendation explicitly labelled provisional.
- **Intervals come from `stats.cluster_bootstrap`** (resample items, then resample that item's
  draws) — never a pooled Wilson interval.
- **No job at n≥40 without a 5-item SEEDED RANDOM SAMPLE pilot** drawn across the whole corpus
  (never the first N items — corpora are ordered easy-first). Size the full run from the
  pilot's MEAN and MAX, treat it as a LOWER BOUND, and budget known heavy-tail mechanisms
  (runaways, multi-turn items) explicitly on top.
- **Client/probe timeouts are DERIVED** (max generation ÷ floor decode rate + headroom,
  retries=0) — never an SDK default (O41, landed `ede38e6`: derived timeout + retries=0 +
  fail-loud escalation + grader poison guard). `run.py generate --probe-timeout` documents its
  own derivation (C28); pass a value only to override it.
- **Transport/HTTP failures ESCALATE** (abort, nonzero exit) — they are NEVER graded as wrong
  answers. The worker does not cancel an abandoned request, so a client that times out and
  retries multiplies worker load and starves the next item.
- **Every benchmark run ≥5 minutes is watched by a DAEMON**, never conversational polling:
  `PYTHONPATH=$STACK_REPO/benchmark uv run python benchmark/m1/bench_watch.py --models <M>
  --bench <B> --tune <T> --total <N> --driver-pattern "run.py generate" --out <path>
  --interval 300`. It answers: progressing? rate vs. prediction (from the MEAN)? output sane?
  needs correction?
- **Verify the C35 provenance check** on the first manifest of every arm before trusting any
  later row (see Appendix A `run_generate()`): `runtime.draft_kind` matches what you intended,
  `registry.sha256` matches the overlay you launched with, worker cmdline confirms
  `--draft-kind`/`--moe-expand` presence or absence.
- **`compare.py` and `--clean-stale` REFUSE across output-determining mismatches**: thinking
  budget, max_tokens, draft/predictor state, `moe_expand`, APC state, `max_kv_cache_size`,
  serving-path tree hash. Sampling knobs (temperature, top_p, top_k, min_p, presence_penalty)
  and KV tune knobs (`kv_bits`, `kv_quant_scheme`, `quantized_kv_start`, `prefill_step_size`)
  WARN only — a `(model, tune)` pair legitimately differs there.
- **Full registry model names everywhere** — chat prose, commits, docs, this doc's own output.
  No bare `Nemotron`, `Ornith`, `the distill`, `the OptiQ`, `qat-6bit`, `8bit`, etc. <!-- allow-shorthand -->
  The pre-commit/commit-msg hooks enforce this on added lines (Appendix C); it is NOT enforced on
  your chat responses — hold yourself to it there.
- **No PII in the repo.** No absolute home paths, hostnames, usernames, tokens, emails, in
  content OR history. Machine-local values live in
  `${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh`; committed files use
  `$STACK_REPO`/`$STACK_WORKDIR` placeholders. `scripts/registry_commit.sh` mechanizes
  committing a registry change without leaking local `hf_path` overrides.
- **No filesystem writes outside `$STACK_WORKDIR`** except the pre-approved caches
  (`~/.cache/huggingface`, `~/.cache/livecodebench`, uv/venv caches,
  `$TMPDIR/mlx-manager-logs`). Verify a redirecting env var actually landed before launching
  anything that writes.
- **Registry of record + insurance clone**: `main_models.yaml` is the source of truth for the
  campaign's current B/C picks; every pick must be publicly downloadable from HF with a
  `caslca/<full-registry-name>` insurance clone. Not-yet-uploaded checkpoints commit as the
  `caslca/` placeholder + a NOT-YET-UPLOADED note, never as a local path.
- **Commit prefixes**: `chore(stack): bump src/mlx-vlm -> <sha> (<summary>)`,
  `feat(bench)`/`fix`/`docs`/`data(bench)`. Propose before fixing/committing/pushing; commit
  when the work calls for it; **never `git push` without in-turn explicit approval.**

---

## 1. Acquire + register

**Purpose:** get the checkpoint downloaded, converted if needed, and servable at `:8000`.

**Prerequisites:** `HF_TOKEN` in `.env` if the source repo is gated; a quiet box for any
conversion (Stage 1 runs box-free, but `mlx_optiq` conversions cannot co-reside with a live
session — schedule them in a quiet window).

### 1a. Download

Use the normal `huggingface_hub` cache flow (`hf_sync.py` patterns in this repo manage cache
housekeeping, not the initial pull). For a gated repo, accept its terms on the Hub first.

### 1b. Convert

Pick the recipe that matches what you're producing:

- **Uniform 4-bit (the default, proven recipe — `gs64`):**
  ```
  uv run mlx_lm.convert --hf-path <source> --mlx-path <out> -q --q-bits 4 --q-group-size 64
  ```
  MLX uniform 4-bit quantization at a given group size is deterministic — two independently
  converted copies of the same bf16 base are tensor-identical (verified by full-tensor md5
  sweep, `docs/model-ledger.md` `Qwen3.8-27B-mlx-uniform-4bit` entry). `--quant-predicate
  mixed_2_6|mixed_3_4|mixed_3_6|mixed_4_6` is `mlx_lm`'s own mixed-bit recipe (distinct from
  `mlx_optiq` below); `--dtype`/`--upload-repo` as needed.
- **`mlx_optiq` mixed-sensitivity conversion (KL-divergence-driven mixed precision):**
  ```
  .venv-optiq/bin/optiq convert <source-bf16-or-hub-id> --target-bpw 4.0 --reference auto [--candidate-bits 2,3,4,8] [--group-size 64] [-o <out>]  # allow-shorthand: the optiq CLI binary path
  ```
  `--reference auto` tries bf16 first, falls back to a uniform-4-bit-baseline reference +
  streamed bf16 probes when the bf16 base won't fit in RAM. **Cite the manifest's
  `effective_bits`, never the bit count in a name you chose** — public `oQ*`/`omlx` builds
  and this repo's own `mlx_optiq` names are both known to be off from their nominal bit count.
  **Does NOT support the fused-expert MoE layout** (`qwen3_5_moe`/similar): expect
  `Static mixed recipe failed: N params not in model` (N = experts × layers × proj-count) <!-- allow-shorthand -->
  — a broken artifact whose config claims 4-bit but whose weights are ~8-bit. Uniform 4-bit is
  the only working recipe for a fused-expert MoE today.
- **QAT:** no in-repo conversion step — QAT checkpoints (e.g. `*-qat-*`) are consumed as
  published; register them like any other MLX checkpoint.
- **Vision-tower graft** (when the checkpoint's own conversion dropped the vision tower but a
  sibling/parent ships one in bf16):
  ```
  .venv-bench/bin/python scripts/graft_vision_tower.py \
      --source <bf16-parent-with-tower> --pick <your-quantized-text-only-snapshot> \
      --out <new-dir> [--bits 8] [--group-size 64]
  ```
  Never touches the text trunk (hard md5 stop if trunk shards differ). Then verify text-path
  equivalence before trusting anything downstream:
  ```
  .venv-bench/bin/python scripts/graft_logit_check.py <original-dir> <grafted-dir>
  ```
  Must print `LOGITS BIT-IDENTICAL: True`. Then run the vision-gate sub-stage (Stage 3, right
  after F1) on the grafted copy.
- **MTP head split** (extract a native multi-token-prediction head into a standalone drafter,
  for Stage 9):
  ```
  uv run python -m mlx_vlm.split_mtp --model <source> --output <out> \
      [--model-type qwen3_5|qwen3_5_moe|qwen3_next|deepseek_v4|glm4_moe_lite|inkling_mm_model] \
      [--block-size N] [--q-bits N] [--q-group-size N]
  ```
  Run from `src/mlx-vlm`. `--model-type` auto-detects; force it only if detection guesses wrong.

### 1c. Register in `main_models.yaml`

Add an entry under `models:`. Required/likely fields (mirror an existing `qwen3_5`-family entry,
e.g. the `Ornith-1.0-35B-mlx-uniform-4bit` block):

| field | rule |
|---|---|
| `type` | `vision` is the backend selector for this fork's server path, not a claim the model sees — text-only models register `type: vision` too. |
| `hf_path` | `caslca/<name>` once uploaded; a local absolute path is a Stage-0/1 INTERIM only — swap to the hub path before any Stage-2 row (the current fingerprint (v5) includes `hf_path`, so the swap deliberately stales screening rows) — see `scripts/registry_commit.sh` to commit without leaking the local override. |
| `max_kv_cache_size` | set from the capacity gate (Stage 2), not assumed. |
| `kv_prealloc_tokens` | **MUST equal `max_kv_cache_size`** — full-cap prealloc is what makes the cap reachable without a realloc double-buffer OOM. Never lower it on a throughput argument alone (see `docs/serving-path.md`). |
| `kv_quant_scheme` / `kv_bits` | `uniform`+integer bits = standard `QuantizedKVCache`; `turboquant`+integer bits = TurboQuant (only engages for `scheme=turboquant` or fractional `kv_bits`); `kv_bits: 0` = fp16 KV, no quantization. Measure at the EXPECTED DEPLOYMENT convention only — no bf16-KV arms (bf16 floor cost 16 GB/session on a sibling, measured 51 GB footprint). → Stage 11 |
| `prefill_step_size` | must be threaded through (512 is this registry's convention) — the mlx-vlm default of 2048 causes a 4× QK² scratch blow-up at 256K. |
| `generation_defaults` | vendor-verbatim sampling to start (an omitted key falls through to the checkpoint under FU-2 precedence); `presence_penalty: 0.0` unless you have a specific reason (a nonzero value disables suffix decoding — moot while suffix stays OFF campaign-wide, but keep it for future-proofing); `max_tokens`/`thinking_budget` should MATCH the two current winners' values (81920/102400 convention) so `compare` does not refuse the pairing on an incidental mismatch. |
| `presentation.role` | `candidate` = registered for benchmarking, never advertised to any client (bench carriers only). `main` = promoted, all five client configs pick it up. `task` = the summarization task model only. Promote `candidate` → `main` only via the Stage 13 promotion rule. |
| `presentation.family` | one of `qwen`, `gemma`, `nemotron` (configgen whitelist) <!-- allow-shorthand: enumerating the whitelist itself -->. `role: main` REQUIRES a family. |
| `presentation.{display_name,context,output,capabilities}` | required by configgen for any entry with a `presentation` block at all — no `presentation` block = router-only entry, not exposed to clients. |

Then check the emitted client configs before committing:
```
uv run python -m configgen check     # non-zero exit + `drift: <target> -> <path>` lines on ANY drift
uv run python -m configgen generate  # writes the five client configs + bench carriers from the registry
```
`generate` must be re-run (and its output committed alongside the registry change) whenever
`presentation` changes — `check` only detects drift, it never fixes it.

**Committing a registry change without leaking local overrides:**
```
scripts/registry_commit.sh --dry-run "commit message"   # preview
scripts/registry_commit.sh "commit message"              # swap local hf_path -> HEAD's -> commit -> restore local
```
It replaces every `hf_path` line that is a local absolute path with that model's committed
counterpart from `HEAD`. A local-path model with NO committed counterpart is a REFUSAL — add
its `caslca/<name>` placeholder (+ NOT-YET-UPLOADED note) first, in a normal edit, then rely on
the script for subsequent changes.

**When the script itself refuses** (e.g. a genuinely new certification hunk that must land
alongside a still-local override elsewhere), fall back to the underlying HEAD-blob mechanic by
hand: `git show HEAD:main_models.yaml` → apply your hunk to that clean copy → `git hash-object -w
<patched-file>` → `git update-index --cacheinfo 100644 <blob-sha> main_models.yaml` → `git
commit` — this stages a clean-of-local-overrides blob directly into the index without ever
writing it to the worktree, which keeps your worktree's local overrides untouched on disk.

**What to record:** the registry diff, the `configgen check` pass, and (if converted) the exact
convert command + `effective_bits`/manifest facts.

**Decision rule:** the model must load, `GET /v1/models` must list it, and `configgen check`
must be clean before Stage 2 starts.

**Cost:** download dominated by network/disk (tens of GB); uniform 4-bit convert is minutes;
`mlx_optiq` mixed conversion runs tens of minutes to hours depending on size and needs a quiet
box; vision graft + logit check is minutes.

**Pitfalls:**
- `mlx_optiq` conversions cannot co-reside with an active AI session on this box (measured: 24
  min elapsed for 1:49 CPU-time, swap 2→8 GB, while the KL phase hadn't even started).
- `mlx_optiq`'s mixed recipe silently produces a broken artifact on fused-expert MoEs (config
  says 4-bit, weights are ~8-bit) — check `effective_bits` before trusting a name.
- Public `oQ*`/`omlx` quant families are a DIFFERENT quantizer from this repo's `mlx_optiq` —
  do not read one as if it were ours.
- A `role: main` entry with no `family` fails `configgen check` loudly; a `presentation` block
  missing any of `role/display_name/context/output` does too.

---

## 2. Capacity gate

**Purpose:** confirm the model fits the memory budget at full context before spending any more
GPU time on it.

**Prerequisites:** Stage 1 registry entry servable; quiet box (capacity numbers are corrupted
by concurrent processes — record the concurrent-process baseline with every peak row, and
suspect co-residency before blaming the model).

**Command:**
```
cd benchmark && uv run python -m bench.run_capacity --model <full-registry-name> --sampling-profile deployed \
    [--grid 160000,192000,224000,256000] [--gate-gb 46.0] [--out-tag <tag>] [--request-timeout 7200]
```
(`--sampling-profile` is REQUIRED since 2026-09-13 (O36; M41 tooling) — `deployed` for every new axis; `--out-tag`
writes `capacity_retrieval.<tag>.json` and friends; `--request-timeout` is the DERIVED per-request bound, O41.)
Grid defaults to `160_000, 192_000, 224_000, 256_000`; gate defaults to `46.0` GB. Writes
`results/<model>/capacity_retrieval.json`.

**What to record:** MLX peak memory (`mx.get_peak_memory` — the PREFILL SPIKE, never RSS) per
rung, plus prefill/decode timing and the co-signal retrieval score at each rung (a 256-token
thinking-starved probe — NOT the real retrieval-depth ladder, see Stage 7).

**Decision rule:** ≤46 GB MLX-peak at every rung up to the target context (256K target; a
lower context that still gates PASS is fine — this is a gate, not an axis to optimize). FAIL at
any rung stops the model here; `park`, don't discard, if the failure is memory-config-fixable
(e.g. narrower KV bits).

**Cost:** capacity ladders on this stack have run overnight for a family of models; budget
tens of minutes per rung, more at 256K (prefill can run into the tens of minutes per rung for a
dense/hybrid architecture).

**Pitfalls:**
- **Never cite peak-memory from a short-generation probe for anything memory-related** — a short
  probe cannot see the real prefill spike (mechanism + O15: `docs/serving-path.md`).
- Footprint is a GATE, not a ranking advantage — a small peak or flat ladder buys co-residency
  comfort on the shared box, not a quality edge. Do not let one candidate's smaller footprint
  bias downstream stage comparisons.
- Bare-process MLX runs (any probe outside `mlx_vlm.server`) MUST call `mx.set_cache_limit`
  (≤4 GB) and `mx.set_memory_limit` first — MLX's default cache limit is 65 GB on a 64 GB box.

---

## 3. Coding screens, vision gate, and the fail-fast funnel

Full funnel definition: `docs/PLAN.md` "The fail-fast funnel" section. Internal rungs are
labelled **F0–F3** (never "Stage 0–3") so they never collide with this doc's own Stage 1–14
numbering.

- **F0 (minutes):** load smoke + Stage 2 capacity gate above (this doc's Stage 2 IS F0).
- **F1 (~1 h): convergence screen at the default tune, n=15.**
  ```
  uv run python benchmark/run.py generate --models <M> --benches humanevalplus \
      --limit humanevalplus=15 --sampling-profile deployed --order model --chunks all
  uv run python benchmark/run.py grade --models <M> --benches humanevalplus
  ```
  Temperature ladder (Stage 4) triggers ONLY on non-convergence here, and only selects a tune
  on a DRAMATIC knee — n=15 cannot see a <32pp pass@1 regression, so "no knee" means "keep the
  default tune," not "inconclusive, investigate more."

### Vision gate (conditional — vision-required roles/picks only; run here, right after F1)

**Purpose:** for a vision-capable checkpoint, confirm it can actually see — PASS/FAIL, not a
ranking. Spec of record: `docs/vision-smoke-m39.md`. Skip entirely for a text-only architecture
or a candidate that is not competing for a vision-gated slot.

**Prerequisites:** router serving the candidate; a one-image smoke first.

**Step 1 — one-image smoke (does it see at all):**
```
cd benchmark && uv run python probe_vision.py --model <full-registry-name> \
    [--url http://localhost:8000] [--color red] [--timeout 600]
```
Outcomes: SEES / BLIND / UNREACHABLE. Run this BEFORE any vision surgery (Stage 1 graft) to
confirm tower absence, and AFTER as the one-image post-graft smoke.

**Step 2 — the 20-image gate:**
```
cd benchmark && uv run python vision_gate.py --model <full-registry-name> \
    [--url http://localhost:8000] [--corpus benchmark/corpora/vision_gate_v1.jsonl] \
    [--out <path>] [--limit N] [--timeout SECONDS] [--resume]
```
Two chat turns per image at the deployed tune, thinking ON: (1) "Describe this image in
detail." with the image; (2) show the human reference captions, ask for a one-word PASS/FAIL
self-verdict. `--resume` skips ids already in `--out`; a non-empty `--out` without `--resume`
is refused (never silently duplicated). A completed row is only written after BOTH turns
succeed — a transport failure aborts the whole run with nonzero exit before any partial row
lands (rerun with `--resume`).

**What to record:** pass count /20, fail count, null (unparseable) count, plus a by-eye read of
five raw descriptions (self-grades are lenient by construction — the by-eye read catches a
model that says PASS on a wrong description).

**Decision rule:** "can do some vision" at **≥16/20 self-PASS with no contradicted PASS in the
by-eye read**. Below that, flag to the operator — this is a gate, not a stage that ranks vision
quality. (A mechanically graded, ranking-capable `visionqa` corpus/loader/grader exists as a
REGISTERED bench — `benchmark/corpora/visionqa_v1.jsonl`, ChartQA/RICO-ScreenQA/AI2D/TextVQA, 40
items — but is RETAINED, NOT RUN, per current operator scope. Only run it on explicit
instruction; if you do, the invocation is the standard `generate`/`grade` pair:
```
uv run python benchmark/run.py generate --models <M> --benches visionqa \
    --limit visionqa=5 --seed 0 --sampling-profile deployed --tune <t>   # pilot first
uv run python benchmark/run.py grade --models <M> --benches visionqa --tune <t>
```
then the full 40 once the pilot clears; follow `docs/vision-smoke-m39.md`'s retained section for
per-source grading rules and the chain-runner pattern.)

**Cost:** ~1 h GPU upper bound per model for the 20-image gate (two turns × 20 images at
deployed sampling).

**Pitfalls (vision gate):**
- A text-only architecture (no vision tower to graft) is excluded by construction — do not
  attempt this stage on it, and do not let it compete for a vision-gated pick slot.
- Self-grading is lenient — always pair the pass count with the five-description by-eye read
  before trusting a borderline (e.g. 15–17/20) score.

### Back to the funnel: F2 and F3

- **F2 (~1–2 h): paired screen vs the current leader on GUARD-CLEAN axes only**
  (today: `humanevalplus`/`mbppplus`, n=100, suffix-OFF, cap matching the leader's row). These
  are COUNT/RATE endpoints (budget-hit rate, degeneracy counts, malformed-edit rate) that
  resolve at n≈30; `pass@1` itself only prunes at n≥50 for a ~20pp deficit. The between-models
  `p_d≈0.20` default applies to sizing here — do not import a within-model smaller-`p_d` argument
  from an OFAT context (e.g. the suffix/MTP OFATs).
  ```
  uv run python benchmark/run.py generate --models <M> --benches humanevalplus,mbppplus \
      --limit humanevalplus=100,mbppplus=100 --sampling-profile deployed --order model \
      --chunks all --tune <label-if-non-deployed>
  uv run python benchmark/run.py grade --models <M> --benches humanevalplus,mbppplus
  uv run python benchmark/run.py compare --models <leader>,<M> --benches humanevalplus,mbppplus
  ```
- **F3 (hours): full n=100+ axes + agentic, for survivors only** — this is Stages
  4–12 of this doc.

**EvalPlus grading mechanics** (HumanEvalPlus/MBPPPlus): the OFFICIAL evaluator runs IN DOCKER
(`ganler/evalplus`, `--platform linux/amd64` — evalplus's `reliability_guard` crashes natively
on macOS). `-v` host mounts MUST be absolute (a relative path silently becomes an empty
named volume). evalplus requires the FULL dataset present, so a small-N subset generation is
padded with failing dummies before grading; read `acc`/`acc_strict` for only the generated
subset from the per-problem `*_eval_results.json`. Headline `acc` = the stricter `plus` status.

**LiveCodeBench grading:** `uv venv --python 3.11 .venv-lcbgrade && .venv-lcbgrade/bin/pip
install 'datasets<3' json_repair requests numpy`, then
`PYTHONPATH=$HOME/.cache/livecodebench/LiveCodeBench .venv-lcbgrade/bin/python
benchmark/run.py grade --models <M> --benches livecodebench`.

**What to record:** per rung, `(acc, acc_strict@budget, conv%, nonconv_kinds)`, exclusive-solve
sets vs the leader, and the funnel verdict; for the vision gate, its own record above.

**Decision rule (Verdicts, per `docs/PLAN.md`):** *prune* (paired-delta CI upper bound <
−5pp vs leader), *park* (partial/resumable, ambiguous point estimate), *continue*. Holm
correction per candidate-per-stage. **Promotion past F2 is a holistic architect
judgement, never a single-metric trigger** (Stage 13 covers promotion itself).

**Cost:** F0/F1 ~1–2 h total per candidate (observed on the `Qwen3.8-27B-mlx-uniform-4bit`
funnel family); F2 paired n=100 screens ~1–2 h GPU per bench per model; vision gate ~1 h GPU
upper bound (above).

**Pitfalls (funnel + the standing regrade rule):**
- Suffix decoding OFF for ALL measurement — verify at the WORKER CMDLINE (`ps -o command=`),
  never trust the yaml alone (a registry `draft_kind: suffix` line can be commented out but a
  stale worker process can still be running with it).
- A defect found AFTER generation may only need a RE-GRADE, not a re-run — see the decision
  rule in Stage 14 / `docs/regrade-vs-rerun-guideline.md` before spending worker time
  re-generating anything.
- `timeout`/`gtimeout` do not exist on macOS — any custom runner needs Python `subprocess`
  timeouts, never a shelled-out `timeout`.

---

## 4. Temperature ladder

Full recipe + all watch-points: `docs/metrics.md` "The temperature-ladder recipe".

**Purpose:** find the model's own operating temperature when Stage 3's F1 screen shows
non-convergence at the default tune. **THE KNOB FOR NON-CONVERGENCE IS TEMPERATURE, NEVER
BUDGET.**

**Prerequisites:** an F1 (n=15) or F2 non-convergence result identifying at least one
persistently-runaway item.

**Procedure (coarse OFAT, per-model, never globalized from a sibling):**
1. Coarse grid 0.7 → 0.5 → 0.3 on the SAME items, fixed generous budget headroom, via
   `--temp`:
   ```
   uv run python benchmark/run.py generate --models <M> --benches humanevalplus \
       --limit humanevalplus=15 --sampling-profile deployed --temp 0.5 --tune t0.5 \
       --order model --chunks all
   ```
2. Add ONE intermediate rung only if a big jump appears between two rungs.
3. Per rung, record: median reasoning tokens, convergence rate, pass@1 — on the SAME items.

**Capped fine scan (when an item runs away >1 h with no self-termination — do not spend an
hour per rung):**
```
uv run python benchmark/run.py generate --models <M> --benches humanevalplus \
    --ids humanevalplus=<the-runaway-item-id> --max-tokens 8192 --temp <t> \
    --sampling-profile deployed --tune <probe-tag>
```
Scan temp in 0.1 steps on the failing item only, one draw per temp (~7 min/probe worst case).
Verdict is clamp-aware: `converged == (finish=="stop" AND completion_tokens <
int(0.8 × min(max_tokens, cap − prompt)))` — never `finish=="stop"` alone. This is a PROBE that
selects which official n=15 rung to run next — it is NEVER a scored result and never replaces
the rung itself.

**What to record:** the full grid table (median tokens / conv% / pass@1 per rung), plus the
capped-scan candidate knee if used.

**Decision rule:** pick the HIGHEST temperature that (a) clears the convergence bar and (b)
holds pass@1 vs the baseline temperature. Quality (pass@1) is the HARD constraint — never trade
it for convergence. No dramatic knee → keep the default/highest-reliable temp as-is; do not
over-read a subtle (~±13pp) difference at n=15.

**Cost:** ~25 min capped scan + ~15 min official n=15 rung, per PLAN precedent (`M19`); add
~1–2 extra re-screen arms if the knee moves the corpus (e.g. `M20` conditional ladder).

**Pitfalls:**
- Reliability is often NON-MONOTONIC — too-low temperature reintroduces greedy repetition
  loops. Check both ends of the grid, not just "lower is always better."
- The result is MODEL/QUANT-SPECIFIC. Never re-use one model's certified temperature on a
  sibling quant/finetune without re-running its own ladder (the `M19`/`M20` history in
  `docs/PLAN.md` is the canonical cautionary tale: a "knee" that looked like a temperature
  effect was actually a retired-production-profile artifact).
- Verify you are on `--sampling-profile deployed` explicitly on every ladder rung — an implicit
  profile default has silently drifted before (O36).

---

## 5. `reasoning_effort` axis (families that expose it)

Recipe precedent: `docs/PLAN.md` M24 row; readback mechanics: `docs/serving-path.md` FU-2.

**Purpose:** for families exposing a native reasoning-effort template knob (e.g.
`Qwen3.8-27B-mlx-uniform-4bit` and its siblings), find whether `medium` or a lower effort
setting matches `xhigh` quality at a fraction of the tokens.

**Prerequisites:** the family must template-support `reasoning_effort`; confirm from the
checkpoint's chat template / vendor docs before spending GPU time.

**Command:**
```
uv run python benchmark/run.py generate --models <M> --benches humanevalplus \
    --limit humanevalplus=164 --sampling-profile deployed --reasoning-effort medium \
    --tune effmed --order model --chunks all
```
`--reasoning-effort` REQUIRES `--tune` — effort rows must never pool with the template-default
corpus. Register a distinguishing companion entry (`role: candidate`, mirroring the registry's
own medium-effort naming precedent in campaign history) with `reasoning_effort: medium` in
`generation_defaults` if you want every client on that entry to measure medium by default, OR
pass `--reasoning-effort` directly per the command above for a one-off arm.

**Readback gate (do this BEFORE spending the full arm):** confirm the effort knob actually
reached the template — e.g. compare prompt-token counts between the `medium` and `xhigh`
(or default) arms on the SAME items; a real effort change measurably shortens/lengthens the
rendered prompt template (precedent: 42 fewer prompt tokens per item on the `medium` template
in the `M24` run). No observable prompt difference means you are not measuring what you think
you are — this is the same "resolved value must differ from the registry default" readback
rule as FU-2, applied to this specific axis.

**What to record:** paired `acc`/`acc_strict` at n=164 (or pooled with `mbppplus` for n=214),
tokens-per-task ratio + CI, non-convergence counts both arms, and the agentic-leg pass count
(Stage 8) at the new effort level.

**Decision rule (pre-registered, M24 pattern):** promote `medium` (or a lower effort setting)
to a candidate operating point iff: strict `acc_strict` EQUIVALENT to the default effort (TOST ±5pp) AND
tokens-per-task ratio CI entirely < 1 AND the agentic leg holds ≥18/22 with ≤3 stall-kills.
**`compare.py` REFUSES to compare rows with differing `reasoning_effort`** (M24-class fatal
mismatch, like a differing `enable_thinking`) — a same-item `stats.paired_delta` fallback is
DIAGNOSTIC ONLY across effort levels, never a ranking input.

**Cost:** ~1 h GPU for a paired n=164 humanevalplus arm at a new effort level (observed:
1.3 h at medium vs 10.6 h at xhigh on one family member — effort mostly buys TIME back, not
just tokens).

**Pitfalls:**
- Effort is a DIFFERENT REGIME, not a tune to pool across in any comparison — always treat an
  effort mismatch exactly like a thinking-enabled/disabled mismatch.
- A certified MTP predictor certified at one effort level (e.g. `xhigh`) must be RE-PROBED at
  a new effort level before the triple can carry it — acceptance rate is effort-sensitive.

---

## 6. Reasoning proxies for role C (Math500, IFEval, BFCL, GPQA)

**Purpose:** role C (everyday research/design driver) uses Math500 as a cheap reasoning proxy
pending the judge panel (Stage 12); IFEval/BFCL/GPQA fill in instruction-following and
tool-calling.

### Math500 on a pre-registered, matched item set

Use a FIXED id set across every model under comparison — never a fresh seeded draw per model.
```
uv run python benchmark/run.py generate --models <M> --benches math500 \
    --limit math500=0 --ids math500=<id1>:<id2>:...:<idN> \
    --sampling-profile deployed --tune <label> --order model --chunks all \
    --probe-timeout <derived>
```
`--ids` restricts to NAMED items and must be a subset of the seeded shuffle's `--limit` prefix —
an unknown id fails LOUDLY. The current campaign's canonical matched set lives at
`$STACK_WORKDIR/queue/resolution/ids.json`, which carries THREE benches, each `{"ids": [...100
ids...], "pilot": [...5 ids, subset of ids...]}`: `humanevalplus`, `mbppplus`, AND `math500` —
so the coding screens can be item-matched the same way as Math500, not just the C-role proxy.
Reuse it (or generate your own via the same `prepare_resolution.py`-style pattern) rather than
inventing a new draw, so your new model's row is directly matched against every existing row on
the SAME 100 items per bench. **Different
Math500 item-set "generations" (e.g. the `M33` set vs the newer `M37`/`C48`/`C63` set) do NOT
pool — always confirm which set an existing comparison row used before matching against it.**

### IFEval

```
uv run python benchmark/run.py generate --models <M> --benches ifeval \
    --tier mid --sampling-profile deployed --chunks all   # tier mid = 30 sampled; heavy = all 541
uv run python benchmark/run.py grade --models <M> --benches ifeval
```
Reports four numbers: `prompt_strict` (headline `acc`), `inst_strict`, `prompt_loose`,
`inst_loose`. Optional lazy deps (`absl-py`, `langdetect`, `nltk`+punkt, `immutabledict`) —
install `benchmark/requirements.txt` where you grade, or it degrades to `acc: null` + a note.
~0.2% of items are graded against a criterion the vendored verifier INVENTED (an instruction
with an absent kwarg) — a known, accepted, deterministic quirk, not a bug to chase.

### BFCL (tool-calling)

Current entry point (D1, native function-calling passthrough — prefer this over the legacy
prompt-mode shim unless you have a specific reason):
```
cd benchmark && ../.venv-bench/bin/python -m bench.run_bfcl_fc \
    --model <full-registry-name> --test-category simple_python,multiple \
    --limit 5 --out $STACK_WORKDIR/scratch/bfcl_fc_smoke        # smoke first
```
Drop `--limit`/point `--out` at `benchmark/results/<model>/` for a kept run. `bfcl-eval` is an
optional dependency (`pip install bfcl-eval==2025.12.17` in whichever venv runs it). NEVER run
against a router that may be serving another job (one resident model, always).

### GPQA

Gated — `HF_TOKEN` in `.env` + accept dataset terms once on the Hub
(`huggingface.co/datasets/Idavidrein/gpqa`), else `run.py list` shows it UNAVAILABLE and it is
skipped automatically. `--tier heavy` runs the full 198.

**What to record:** the four numbers per bench, the item-set identity/provenance (which ids,
which generation), and for Math500 specifically — token ratio vs the models it's matched
against, and wall-clock per 100 items (this has been the deciding usability axis more than once
in this campaign; a runaway-tax-heavy model can still be quality-tied and lose on this).

**Decision rule:** `compare.py`/`--intersect` for a same-item-set comparison; a mismatched item
set or budget REFUSES — fall back to `stats.paired_delta` directly only as a labelled
DIAGNOSTIC, never a ranking.

**Cost:** Math500 n=100 has run anywhere from 0.81 h/100 items (`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`, the fastest measured) to ~21.7 h/100
items (a runaway-tax-heavy model at high temperature) — size your probe-timeout and expect a
wide spread; always run the 5-item pilot first.

**Pitfalls:**
- IFEval cross-model comparisons are ABSOLUTE-ONLY if the models being compared ran at
  different `max_kv_cache_size` caps (no three-way re-run available) — check the cap on each
  side before citing a delta.
- Math500 scoring HAD a LaTeX-parsing undercount bug (fixed 2026-09-09 via saved-answer
  regrade, no regeneration needed) — if a Math500 number looks anomalously small relative to
  `ordinary` scoring, check whether the row predates the scorer fix before re-running anything
  (regrade-vs-rerun rule, Stage 14).

---

## 7. Reasoning-depth and retrieval-depth ladders

**Purpose:** separate curves — retrieval depth (can it find a planted fact at depth X) and
reasoning depth (can it REASON over content at depth X) never conflate into one "effective
context" number.

### Retrieval-depth ladder

```
cd benchmark && uv run python -m bench.run_retrieval --model <full-registry-name> --sampling-profile deployed \
    [--grid <ctx-list>] [--samples N] [--threshold 0.85] [--out-tag <tag>] [--request-timeout 9600] \
    [--max-tokens N] [--thinking-budget N] [--no-preload]
```
(`--sampling-profile` REQUIRED since 2026-09-13, O36; `--request-timeout` default 9600 s, DERIVED, O41.)
Five distinct codes planted at depths {0.1, 0.3, 0.5, 0.7, 0.9}; the model must list all of
them; accuracy = fraction returned, with per-depth breakdown. This is a full CURVE, not a
climb-to-cliff — a mid-context dip does not stop the ladder. CORRECTED 2026-09-13 (O41, M41 tooling): a transport failure (timeout/refused/OOM-disconnect) at any trial ABORTS the whole run with a traceback and writes no output — it is never graded as a miss; re-run after fixing the cause. Writes
`results/<model>/retrieval.json` with a headline `retrieval_effective_ctx`.

### Reasoning-depth ladder (vartrack — variable-tracking multi-hop)

```
cd benchmark && uv run python -m bench.run_reasoning --model <full-registry-name> \
    --sampling-profile deployed [--grid <ctx-list>] [--samples N] [--chain-len N] \
    [--threshold 0.85] [--out-tag <tag>] [--deep-from <ctx>] [--deep-samples N] \
    [--early-stop-budget-hits N] [--resume]
```
`--sampling-profile` is REQUIRED here too. `--deep-from`/`--deep-samples` apply a deep-rung
design at high context (more samples where they're expensive to get); `--early-stop-budget-hits
N` stops a deep rung early (scoring from the first N samples) if ALL of them hit the thinking
budget — a cost control for a rung you already expect to be a wash. `--resume` reuses rungs
persisted by an earlier attempt of the SAME design (grid/profile/samples/chain/threshold key).

**What to record:** per-rung accuracy, the headline `*_effective_ctx` (largest context with
accuracy ≥ threshold), and — separately — retrieval vs reasoning curves; never merge them into
one "effective context" figure (that conflation is exactly what an early "effective context
length" definition on this campaign was critiqued for).

**Decision rule:** effective-context threshold = accuracy ≥ **0.85**. Retrieval-depth and
reasoning-depth curves stay SEPARATE reporting axes always.

**Preflight (per model, before spending a deep-rung's worker time):** compute the DERIVED MAX
PROMPT — with `max_tokens` and the 0.8 clamp, this is roughly `max_kv_cache_size × 0.8 -
declared_thinking_budget`-adjacent territory per model (varies with each model's
`thinking_budget`; e.g. ~159,744 tokens for one campaign model at its shipped config). Above it
the model silently gets less room to think. Check per model, record it, and keep every rung's
longest prompt inside the no-clamp window before spending worker time.

**Cost:** a 5-item pilot at the deepest rung sizes the full run (per the standing pilot rule);
observed campaign depth pilots have run minutes per item at shallow depth, growing to many
minutes per item at the deepest rungs (prefill-bound at very long depths — expect several
minutes of prefill alone per item near 128–256K).

**Pitfalls:**
- A depth "cliff check" is a PER-MODEL test against that SAME model's own shallower rung — never
  a cross-model ranking comparison at depth.
- Depth items embedded via `--depth-tokens` (coding-at-depth) require `--tune` explicitly
  (provenance-tracked, so depth rows never silently pool with shallow rows).

---

## 8. Agentic legs (opencode primary, dsh secondary, aider retired)

**Purpose:** measure agentic multi-turn tool-use coding competence — the axis Math500/HumanEval+
cannot see (edit protocol fidelity, tool-call round-tripping, multi-turn session behavior).

**Prerequisites:** router serving the candidate at its certified/screened tune; opencode CLI
pinned version recorded; `opencode_bench.json` (bench-only carrier — a bench harness that
mounts a CLIENT config silently EXCLUDES `role: candidate` models, so bench carriers exist
separately from the daily-driver configs for exactly this reason).

### opencode (primary harness)

```
uv run python benchmark/run_opencode_probe.py --model <full-registry-name> \
    --items <comma-list-of-exercise-names> [--lang <lang>] [--tick-s 300] \
    [--hard-ceiling-s 3600] [--stall-ticks 2] [--loop-repeats 3] [--out <path>] \
    [--allow-version-drift]
```
No `--tune` flag — opencode rows are tagged by `--lang`/`--out`, not a harness tune label. Pin
opencode **1.18.15** (drift is recorded, not silently tolerated — pass `--allow-version-drift`
only when you mean it). Use the M3 22-item python set (or the matching per-language set) named
by exercise, per the O39 protocol: record the version per row + in the manifest (`deployed`
profile, polyglot sha, `edit_format: tools`); `.meta/` (reference solutions) excluded from the
scratch copy; a model that rewrites the test file itself is scored as a FAILURE (contamination
control). Progress gate (`--tick-s`/`--hard-ceiling-s`/`--stall-ticks`): a session with no
forward progress for 300s inside a 3600s ceiling is a stall-kill (2 consecutive stalls = kill,
per the shared progress-gate design, `300/3600/2`).

**What to record:** pass count /22 (or /N for your item set), stall-kill count, session wall
time, and — critically — this is a SINGLE SESSION unless you explicitly power it (session
variance on a 22-item arm has been measured to swing ±5–6 items run-to-run; a single session is
directional evidence, not a certified result).

### dsh (secondary scaffold, built but not the primary harness)

```
uv run python benchmark/run_dsh_probe.py --model <full-registry-name> --tune <label> \
    --items <comma-list-of-exercise-names> [--lang <lang>] [--base-url <url>] \
    [--dsh-home <dir>] [--tick-s 300] [--hard-ceiling-s 3600] [--stall-ticks 2] \
    [--loop-repeats N] [--out <path>] [--allow-version-drift]
```
`--tune` and `--items` are REQUIRED here (unlike opencode) — `--tune` folds into the default
output path `benchmark/results/<model>/dsh.<tune>.jsonl` per the M35 spec. Use only if opencode
itself is suspected of scaffold-sensitivity bias for this candidate — the campaign's operator
ruling (2026-09-08) is to keep opencode primary and not routinely run dsh in parallel.

### aider — RETIRED as a harness (2026-08-16)

`aider_config/` rows are kept for historical reference; `benchmark/run_aider_docker.sh` is
frozen. Do not add new arms. If you need the historical mechanics (seeded-exercise pinning via
keyword filter, APC-off requirement, 24 h `RETRY_TIMEOUT` trap, run-tag hygiene), read
`benchmark/m1/README.md` in full before touching anything aider-shaped.

### SWE-bench-Verified (agentic, optional)

```
cd benchmark && uv run python -m bench.run_swebench --model <full-registry-name> --n 2   # start small
```
Requires `pip install swebench` + a running docker daemon; standalone probe, not part of
`generate`/`grade`. Writes `results/<model>/swebench.json`.

**Decision rule:** no fixed accept/reject threshold here — this axis feeds the Stage 13
holistic promotion judgement alongside the coding screens and Math500. A pre-registered
EXTENSION rule (more languages/sessions) fires only on a genuinely surprising inversion vs the
existing evidence — decide and record the trigger BEFORE looking at the result, not after.

**Cost:** ~1.5–2 h per 22-item opencode session (observed range across the campaign, varies
with stall-kill rate); ~0.7–2.2 h for a dsh smoke + one paired leg.

**Pitfalls:**
- **`--num-tests N`-style unseeded random sampling is a trap** — if any harness under you does
  `shuffle → [:N]` with no seed, two invocations pick DIFFERENT items. Pin the item set by NAME.
- `opencode` costs ~18,050 prompt tokens for a four-word request — budget prefill accordingly.
- `session_pass` (opencode) is NOT comparable to aider's `final` (which allows a second,
  test-informed attempt) — score the session outcome, never an intermediate.
- A single opencode session is not a reliable point estimate — treat a lone 22-item run as
  directional, and say so explicitly in any report.

---

## 9. Predictor certification (MTP / draft speculative decoding)

Full saga: `docs/serving-path.md` (suffix section); registry mechanics: `main_models.yaml`
certified-triple comments (e.g. the `Ornith-1.0-35B-mlx-uniform-4bit` / `M27` block).

**Purpose:** certify (or reject) a native MTP head as a SERVING-ONLY speed lever. Measurement
of QUALITY always stays predictor-OFF, forever — this stage only certifies whether the
predictor is safe to SERVE.

**Prerequisites:** the checkpoint ships (or can be split into) a native MTP sidecar. Confirm
before probing: does `config.json` declare `mtp_num_hidden_layers` or a similar native head?

### Step 0 — split the head (if not already a standalone sidecar)

```
uv run python -m mlx_vlm.split_mtp --model <source> --output <sidecar-dir> \
    --model-type <arch> [--block-size N] [--q-bits N] [--q-group-size N]
```

### Step 1 — M6a speed probe (gate <1.3×)

```
cd benchmark && uv run python -m m1.mtp_probe --model <full-registry-name> \
    [--arm off|on|both] [--draft-model <sidecar-dir>] [--items <jsonl>] \
    [--gate-threshold 1.3] [--session-max 2] [--json-out <path>]
```
Verify `--draft-kind mtp` (and `--draft-model` if external) actually landed at the WORKER
CMDLINE — a registry flip with no server-side sidecar discovery serves plain decode and looks
like a false negative.

**Decision rule (M6a):** decode speedup <~1.3× → CLOSE the lever (do not proceed to M6b, per
the O25 precedent that "MTP is a net slowdown" on bolt-on heads elsewhere does NOT pre-decide a
native trained head — measure it, don't assume). ≥1.3× → proceed to M6b.

### Step 2 — M6b/M6d quality OFAT (only if M6a passed)

Paired ON/OFF `humanevalplus` at n=164, or a powered n≥60 sized from measured `p_d` (M6b
certified at n=63) — suffix-like speculative decoding on this stack has shown `p_d` far below
the between-models default of 0.20, so pass@1 IS an admissible OFAT endpoint at the measured
`p_d`, per `benchmark/m1/suffix_ofat.py` machinery reused for MTP:
```
uv run python benchmark/run.py generate --models <M> --benches humanevalplus \
    --limit humanevalplus=164 --sampling-profile deployed --tune mtpon --order model \
    --chunks all
# then an OFF arm on the same items via a draft-stripped overlay
```
Certification standard (precedent): `acc` TOST ±5pp EQUIVALENT at n=164, 100% engagement
(every row shows nonzero draft acceptance), acceptance rate + decode-speedup ratio recorded,
zero degeneracy introduced in either arm.

**Registry on PASS:** add `draft_kind: mtp` + `draft_model: <path>` to the entry, with a comment
recording the certification run's numbers (mirror the existing certified-triple comments in
`main_models.yaml`). **Measurement stays draft-OFF forever** — the current fingerprint (v5) + `compare`
refusal police this boundary; never generate a quality row against a draft-ON worker again
after certification.

**HF sidecar publication:** upload the drafter dir to `caslca/<full-registry-name>-mtp-drafter`
publicly; verify anonymous download and per-file SHA256 against the locally tested artifact
(pattern: `HfApi(token=False)` listing + hash compare, `docs/lab-notebook.md` M27 execution
entry) before citing the upload as done. Write a model card in `docs/model-cards/` with the
certification numbers and provenance (which shards/layers were split, quantization).

**What to record:** M6a acceptance/tok-s/peak-mem-delta; M6b/M6d paired acc + CI + TOST verdict,
p_d, engagement rate, mean acceptance, decode ratio, corpus wall both arms.

**Decision rule (overall):** GO to certify iff M6a ≥1.3× AND M6b/M6d TOST ±5pp EQUIVALENT AND
100% engagement. A borderline acceptance rate (observed precedent: ~0.78 against an informal
~0.8 "worth investigating further" trigger) is a note, not itself a blocker.

**Cost:** M6a smoke ~15 min; M6b/M6d paired n=164 OFAT has run ~3.3–5.2 h per arm (ON) and
~4.6–10.5 h per arm (OFF) depending on the model's base decode speed.

**Pitfalls:**
- `--draft-kind mtp` with NO `--draft-model` serves PLAIN DECODE, not the native head — a past
  M6a "close" on this campaign was voided entirely by this exact instrument failure. Always
  verify the worker cmdline.
- Suffix and MTP/draft decoding are DIFFERENT LEVERS with different registry fields
  (`draft_kind: suffix` vs `draft_kind: mtp`) — suffix decoding is OFF for every model
  campaign-wide (proven inherently non-lossless on bf16, and the ±5pp gate was never
  demonstrated for it at n=100); do not conflate a suffix return-condition question with an
  MTP certification.
- Any nonzero `presence_penalty`/`repetition_penalty`/logit_bias/structured output on a request
  falls back the whole request to plain decode when suffix would otherwise engage —
  `presence_penalty: 0.0` is load-bearing while suffix is anywhere in the picture.
- `thinking_budget` + a drafter combination has previously hard-500'd the server — confirm the
  fork version you're running has this fixed (O40) before trusting a "the request errored"
  signal as a model problem.

---

## 10. MoE expert-budget expansion (native MoE models only)

Full spec: `docs/specs/m34-moe-expert-expansion.md`.

**Purpose:** for a sparse-MoE checkpoint (`qwen3_5_moe` or `nemotron_h` architectures today),
test whether widening the per-token expert budget on late layers buys quality at a token/speed
cost — an inference-only, training-free lever.

**Prerequisites:** confirm the architecture is one of the two supported (`qwen3_5_moe` /
`nemotron_h`) and identify its ACTUAL layer count, native top-K, and MoE layer indices from its
own config — never copy another architecture's layer range blindly.

**Recipe string:** `LS-LE:N:T:D` — inclusive 0-based decoder-layer range `[LS, LE]`, target
rank budget `N` (must be ≥ native `K`), threshold `T ∈ [0,1]`, decay floor `D ∈ (0,1]`. This
campaign's own OFAT on `Ornith-1.0-35B-mlx-uniform-4bit` used the paper's config verbatim,
0-based, on that model's last 13 layers: `27-39:20:0.8:0.5` (`docs/specs/m34-moe-expert-expansion.md`
"Experiment"). `N == K`, or a layer outside `[LS,LE]`, or expansion unset → BYTE-IDENTICAL to the
native path (a hard spec requirement — verify this on your model before trusting any non-N==K
result).

**Registering it:** `moe_expand: "<LS-LE:N:T:D>"` in the model's `main_models.yaml` entry.
It is OUTPUT-DETERMINING and lives in the provenance fingerprint (`compare`/`--clean-stale` see
it) — never compare a `moe_expand`-set row against a native row without treating that as the
axis under test.

**Pilot (5 seeded items/dataset, before any full run):**
```
uv run python benchmark/run.py generate --models <M> --benches mbppplus,math500 \
    --limit mbppplus=5,math500=5 --sampling-profile deployed --order model --chunks all \
    --tune expand-pilot
```
with the `moe_expand` registry entry set for the "expanded" arm and unset for the "native" arm
(two separate overlays/router sessions).

**What to record:** paired strict accuracy delta + CI, tokens-per-task ratio + CI, decode
tok/s, non-convergence, per the standard four numbers.

**Decision rule (M34 pattern):** strict EQUIVALENT (TOST ±5pp) AND tokens-per-task ratio CI
entirely < 1 → promote to a second, larger OFAT (held-out config probe). Ratio CI containing 1
with no strict gain → CLOSE and record native as the retained default. **On this campaign's own
MoE models, native routing was retained on every axis tested** (coding); a math-oriented
directional gain was kept as a candidate configuration for operator review, not shipped as a
routing change — treat any positive expansion result as provisional pending operator review,
never auto-promote it.

**Cost:** a 5-item-per-dataset pilot (4 arms: native/expanded × 2 datasets) has completed in
under 20 minutes on this box; a full n=100 resolution run costs proportionally to Stage 3's F2
coding-screen costs, doubled for the two arms.

**Pitfalls:**
- Compute is WASTED (not saved) in gated layers when using this lever — always pass `N`
  indices to the kernel regardless of how many are actually kept; the lever's value proposition
  is tokens-per-task or quality, never raw throughput.
- The MTP target-verify path (if the model also carries a certified predictor) must NOT be
  expanded — expansion applies to the TARGET model only, never the drafter.

---

## 11. KV-cache options

**Purpose:** choose the KV quantization convention for the registry entry (Stage 1 already sets
this from measurement — this stage is the reference for HOW to choose it).

**Options** (`kv_quant_scheme` + `kv_bits` in the registry):
- `kv_bits: 0` → fp16 KV, no quantization (highest memory cost, used where the capacity gate
  has ample headroom — e.g. a very sparse MoE with tiny per-token KV).
- `kv_quant_scheme: uniform` + integer `kv_bits` (e.g. 4) → standard `QuantizedKVCache`.
- `kv_quant_scheme: turboquant` + integer `kv_bits` (e.g. 4) → TurboQuant engages (it activates
  ONLY for `scheme: turboquant` or a fractional `kv_bits` — an integer `kv_bits` under
  `uniform` never engages it, a common mis-registration to check for).
- `quantized_kv_start`: token offset before KV quantization begins (0 = quantize from the
  start).

**The prealloc rule (structural, not a KV-quality choice):** `kv_prealloc_tokens` MUST equal
`max_kv_cache_size` — full mechanism and the OFAT that retracted the throughput objection:
`docs/serving-path.md`.

**Session-cache interaction:** `MLX_VLM_CACHE_SESSION_MAX` (default 8 if unset) multiplies the
full-cap KV floor by the number of retained sessions and can blow the 46 GB gate on floors alone
— why `MLX_VLM_CACHE_SESSION_MAX=2` is mandatory everywhere (Stage 0); full audit:
`docs/PLAN.md` D6.

**What to record:** the chosen `kv_quant_scheme`/`kv_bits`/`quantized_kv_start` combination and
the capacity-gate numbers (Stage 2) that justify it; if you tried a bf16-KV arm for
comparison, label it clearly as OFF the deployment convention (never register it as the
shipped tune — measure at the expected deployment only, no bf16-KV arms as a standing rule).

**Decision rule:** pick the narrowest KV width that clears the capacity gate with comfortable
headroom — the one registry observation on record is `Ornith-1.0-35B-mlx-uniform-4bit` at fp16
KV, 13.6 GB below the 46 GB gate (`main_models.yaml:134`); there is no campaign-wide norm beyond
that single data point. Narrower buys headroom for co-residency and future context growth, not a
quality claim by itself (KV bit-width is a `compare`-WARN tune axis, not a REFUSE axis, so
document it but don't treat a narrower choice as free).

**Cost:** folded into Stage 2's capacity-gate runs — no separate GPU time needed if Stage 2 was
run across the KV-width candidates you're choosing between.

**Pitfalls:**
- APC (`APC_ENABLED`) is a COMPLETELY SEPARATE cache from KV/session caching and must stay OFF
  everywhere (Stage 0) — a stale `APC_NUM_BLOCKS=16384` export has cost ~33 GB and produced a
  hard Metal OOM in this campaign's history; it is not a KV-cache tuning knob at all.
- `prefill_step_size` defaulting to 2048 (instead of this registry's 512 convention) causes a
  4× QK² scratch blow-up at 256K — always set it explicitly.

---

## 12. Judge panel for role C (subjective research/design quality)

Spec of record: `docs/judge-panel-c.md`. This is the ONLY axis that measures role C's actual
target (research/design quality) rather than a proxy (Math500).

**Purpose:** rank C contenders (including your new candidate, once it's a serious C contender)
on blind, mixed-family, pairwise-judged research/design quality, gated by a pre-registered
reliability check.

**Prerequisites:** the candidate must already be a plausible C contender (passed Stages 1–8 at
minimum, ideally 9); this stage is expensive in judge-API calls, not GPU, but still not free.

### Generation (the only GPU stage)

Follow the `queue/c_second_reference/run.py` chain-runner pattern (Appendix A): fresh
draft-OFF overlay, router with mandatory env, C35 check, seeded 5-item pilot
(`--limit cjudge=5 --seed 0`), then the full 40-item `cjudge` corpus
(`benchmark/corpora/cjudge_v1.jsonl`), tune label `m38` (or your own).

### Anchors

```
cd benchmark && uv run python -m bench.judge_anchors --models <M1> <M2> ... \
    [--tune <T>] [--results-dir <dir>] [--seed 38] [--out <pairs.jsonl>]
```
Builds 30 seeded anchor pairs (10 `degrade`, 10 `verbosity`, 10 `identity`) from the generated
outputs.

### Panel

```
cd benchmark && uv run python -m bench.run_judge_pairwise --models <M1> <M2> ... \
    [--tune <T>] --anchors <pairs.jsonl> [--results-dir <dir>] [--corpus <cjudge.jsonl>] \
    [--judges <list>] [--out <verdicts.jsonl>] [--seed N] [--limit-pairs N] \
    [--retries N] [--backoff N] [--dry-run] [--allow-single-family] \
    [--export-packets <dir>] [--ingest-packets <dir>] [--batch-size N]
```
Mixed judge family is mandatory (`--allow-single-family` overrides it — only use this
deliberately, e.g. a cost-constrained partial run, and say so in the report). Blind, forced
choice A/B/tie, both orders, every judge. `--export-packets`/`--ingest-packets` support a
subagent-judge path (blind markdown packets in, verdict JSON back) when API judge calls are
constrained. **The codex judge's model id and effort are PINNED IN CODE**
(`judge_pairwise.CODEX_MODEL`/`CODEX_EFFORT`, overridable only via `M38_CODEX_MODEL`/
`M38_CODEX_EFFORT` env vars), keyed in verdicts as `codex:<model>:<effort>` — record this exact
key alongside the gate table as provenance (the M38 run used `codex:gpt-5.6-terra:medium`).

### Gate + ranking

```
cd benchmark && uv run python -m bench.judge_gate --pairs <pairs.jsonl> \
    --verdicts <verdicts.jsonl> [--judges <list>] [--out <gate.json+ranking.json>] \
    [--seed N] [--models <list>] [--tune <T>] [--results-dir <dir>]
```

**Decision rule (pre-registered reliability gate; FAIL → NO ranking is written, by
construction):**
- Anchor accuracy on `degrade` ≥ 0.85.
- Per-judge order-flip rate ≤ 0.30; panel Cohen's kappa between orders ≥ 0.6.
- Krippendorff's alpha across judges on anchors ≥ 0.5.
- `verbosity`: rate of preferring the padded (longer) copy ≤ 0.10.
- `identity`: tie rate ≥ 0.80.

On FAIL, `bench/judge_gate.py` refuses to write `ranking.json` — revise the rubric or panel and
re-run the GATE only (anchors cost judge calls, not GPU, so this is cheap to retry). Record the
gate result in `docs/campaign-results.md` regardless of outcome.

On PASS, endpoint = paired preference rate per pair with `stats.cluster_bootstrap` over items,
Holm across all pairs, TOST ±5pp for `equivalent`. Report tokens/task, latency and runaway
share alongside (the four numbers, again).

**What to record:** the gate table (all five thresholds, pass/fail each), and — if the gate
passes — the ranking with CIs and Holm-adjusted significance.

**Cost:** for a 5-contender, 40-item corpus: 40 items × 10 pairs × 2 orders × 3 judges = 2,400
verdict calls + 180 anchor calls — judge-API cost and wall-clock, NOT GPU time (generation is
the only GPU leg, already counted in Stage 3/6's cost). MDE at n=40 ≈ ±20pp — state it in every
ranking claim.

**Pitfalls:**
- A TWO-judge panel (one judge dropped for cost) changes the majority-tiebreak arithmetic in a
  way that can fail the gate even when every OTHER metric passes — this has happened on this
  campaign (a two-judge majority-else-tie rule collapsed split-order ties straight to panel
  ties, dragging `degrade` accuracy below 0.85). Prefer three judges; if you must drop to two,
  expect the gate to be harder to clear, not easier.
- A rubric correction found AFTER a failed gate run does NOT retroactively rescue that run —
  the correction applies to the NEXT gate attempt only.
- Do not conflate this panel with `benchmark/README.md`'s older `run_judge.py` (a DIFFERENT,
  code-quality-only panel over execution-PASSING coding outputs) — they measure different
  things with different corpora.

---

## 13. Promotion & shipping

Full taxonomy: `docs/model-ledger.md` §0.

**Purpose:** turn a candidate that has survived Stages 1–13 into either a shipped pick or a
recorded, reasoned non-promotion.

**What a "pick" is:** a **(model, tune, predictor) TRIPLE**, per goal (B and C separately).
MODEL = weights + quantization + quant algorithm (a fine-tune is a SEPARATE model by this
taxonomy). TUNE = sampling + KV width + cache cap + thinking budget + reasoning_effort.
PREDICTOR = `off` / `suffix` / `mtp` / `draft`, certified by Stage 9 — quality measurement
stays predictor-OFF forever regardless of what ships.

**Promotion is a HOLISTIC ARCHITECT JUDGEMENT across every stage's evidence together — never a
single-metric trigger.** Record the reasoning in `docs/model-ledger.md`, not just the numbers.
**Rank changes require operator approval; result/evidence updates alone do not.**

### On promotion (or on any completed test, promoted or not)

1. **`main_models.yaml`**: flip `presentation.role` from `candidate` to `main` (requires
   `family` to already be set correctly), add/update the certification comments (mirror the
   existing `# CERTIFIED <milestone> <date>` style), commit via `scripts/registry_commit.sh` if
   local `hf_path` overrides are present.
2. **`uv run python -m configgen generate`** — regenerate and commit all five client configs +
   bench carriers from the updated registry. A per-model sampling/thinking change must hit ALL
   FOUR full-sampling carriers (`opencode_config/opencode.json`, `aider_config/` — rows kept,
   no new arms — `openwebui-init/models_config.json` then `uv run python
   openwebui-init/publish_models.py [--apply] [--prune] [--url ...] [--email ...]`, and
   `main_models.yaml` `generation_defaults`); a new model/context/capability change touches all
   five configs + the registry. Then audit for drift with `configgen check`.
3. **The root `README.md`** (NOT `docs/README.md`, which is only the docs index) B/C ladder
   tables — update on EVERY completed test result or regrade, not just on a rank change. Format
   to mirror exactly the live example: a `Rank | Model | Recommended configuration | Best for —
   and why` table capped at **4 entries** for B and **2 approved picks + up to 2 shortlist
   entries** for C, plus an "evidence" table below it with per-axis numbers, CIs and explicit
   caveats (missing coverage, provisional scores, session variance). Rank changes still need
   operator approval; the evidence tables do not.
4. **`docs/campaign-results.md`**: append a dated entry with the full numbers, CIs, mechanism,
   and an explicit recommendation (or explicit non-recommendation) — this file is the living
   results record and the generated scoreboard's sole owner.
5. **`docs/PLAN.md`**: close or update the row that tracked this work; move narrative to
   `docs/lab-notebook.md`, ledger updates to `docs/model-ledger.md`. `PLAN.md` never grows a
   narrative — keep it CURRENT and short.
6. **`docs/open-questions.md`**: if the promotion decision itself involves any judgement call an
   operator should weigh in on (a reorder, a provisional-to-certified transition, a shortlist
   admission), file it as a new `C<n>`/`O<n>` item the MOMENT the judgement call is identified —
   never delete a closed item later.
7. **HF model card**: write/update `docs/model-cards/<full-registry-name>.md` with per-number
   source citations (mirror the existing cards' style — capacity gate + retrieval ladder,
   F1/F2 convergence + pass@1 with MDE, recommended tune, honest serving caveats). If the
   checkpoint isn't uploaded yet, upload FIRST (`caslca/<full-registry-name>`), verify anonymous
   download + tensor SHA256, THEN write the card citing the verified upload.
8. **`docs/handoff.md`**: rewrite in place (it is THE one handoff — never a second one) with
   what's live, what's next, and any process state (router up/down, in-flight arms).

**Decision rule:** never auto-promote or auto-change a B/C pick. Surface the proposed change and
its rationale for operator approval FIRST — this applies even when every measured axis looks
favorable.

**Cost:** driver-side, minutes, once the underlying measurement stages are done — this is
bookkeeping, not GPU time.

**Pitfalls:**
- A `presentation` block missing `family` on a `role: main` entry fails `configgen check`
  loudly — do this flip and the `check` pass together, not separately.
- Committing a registry change with an uncommitted local `hf_path` override leaks PII (a home
  path) — always route through `scripts/registry_commit.sh` or manually verify no absolute path
  survives in the diff before committing.
- The daily-client configs (opencode/aider/OWUI) can silently omit a `candidate`-role model
  even after strong evidence — that is BY DESIGN (candidates never reach clients) and is a
  SEPARATE follow-up (registration) from the promotion decision itself; don't conflate "the
  evidence supports promotion" with "the client configs already show it."

---

## 14. Regrade vs rerun; result-landing checklist; handoff

Full decision rule: `docs/regrade-vs-rerun-guideline.md`.

**Before re-running ANYTHING** that this doc's earlier stages already measured (e.g. a grader
fix lands after your Stage 3 rows exist):

1. Is the defect in GRADING (re-grade, free) or GENERATION (re-run, hours)? Full decision table
   incl. "does the persisted row carry the new metric's inputs" and "do the raw rows still
   exist" (they're TRACKED — check `git log` first): `docs/regrade-vs-rerun-guideline.md`.
2. Is the number DECISION-RELEVANT and RESOLVABLE at the n you have? Check the MDE first.
3. If a re-run IS warranted, change ONE thing (OFAT) — never a fresh full re-characterization
   when only one axis moved.

**Result-landing checklist (every stage, every completed arm):**
- [ ] Raw `.jsonl` + `.manifest.json` + `.score.json` files committed — `benchmark/results/` is
      DELIBERATELY TRACKED (`.gitignore`; only `results/scores*.json`, `**/.file_locks/`,
      `**/__pycache__/` are ignored).
- [ ] `acc`, `acc_strict@budget`, `conv%`, `nonconv_kinds`, tokens/task, wall-clock recorded with
      CI + MDE.
- [ ] C35 provenance check passed on the first manifest of the arm.
- [ ] `docs/campaign-results.md` dated entry written.
- [ ] `docs/PLAN.md` row updated/closed.
- [ ] The root `README.md` B/C evidence table updated (even if no rank change) — NOT
      `docs/README.md`, which is only the docs index (see below for the separate index update).
- [ ] `docs/handoff.md` rewritten in place with current process state.
- [ ] Any judgement call surfaced as a new `docs/open-questions.md` item.
- [ ] If this is the FIRST qualification pass with this doc: confirm `docs/qualify-a-model.md`
      is indexed in `docs/README.md`.

**Cost:** re-grading is always ~zero GPU time; re-running is always hours — this asymmetry is
the entire point of the two-phase `generate`/`grade` harness split. Default to re-grading first.

**Pitfalls:**
- ~20 historical rows are labelled `INVALID` under a RETIRED run-level convergence-invalidation
  rule — that label is void BY POLICY, not by re-measurement; `acc_strict` is the correct
  replacement metric for what that flag was reaching for. Don't re-measure to "confirm" a
  retired label; just stop trusting the label.
- A verdict of "DNF-MEANDER" predates the `meander`/`degenerate_repetition` mechanism split —
  treat any pre-split label as UNKNOWN mechanism, not as evidence for either specific mechanism,
  unless `reasoning_stats` was persisted for that row (most old rows lack it).

---

## Appendix A — chain-runner template

Every multi-arm, multi-hour piece of work in this campaign runs as a small `run.py` +
`helpers.py` pair under `$STACK_WORKDIR/queue/<name>/`, launched detached
(`nohup ... </dev/null &`) and monitored via `bench_watch.py`. Copy an existing pair (e.g.
`$STACK_WORKDIR/queue/c_second_reference/`) rather than writing one from scratch. The pattern:

**`run.py`** (the orchestrator):
```python
import os, sys, json, time, subprocess, fcntl
from pathlib import Path
import yaml
import helpers as h

R = Path(os.environ['STACK_REPO']); Q = Path(os.environ['STACK_WORKDIR']) / 'queue'
D = Q / '<this-run-name>'
MODELS = ['<full-registry-name>']

def command_for(pid):
    p = subprocess.run(['ps', '-o', 'command=', '-p', str(pid)], capture_output=True, text=True)
    if p.stderr.strip(): raise RuntimeError(p.stderr)
    return p.stdout.strip()

def main():
    # 1. Exclusive lock — refuse to double-launch this chain.
    lock = (D / 'queue.lock').open('w'); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    (D / 'queue.pid').write_text(str(os.getpid()))

    # 2. Wait for the PREDECESSOR's DONE marker (never assume it finished — poll its own pid).
    pid = int((Q / '<predecessor>/queue.pid').read_text())
    while '<predecessor>/run.py' in command_for(pid):
        time.sleep(60)
    if '=== <PREDECESSOR> DONE ===' not in (Q / '<predecessor>/queue.log').read_text():
        raise RuntimeError('Predecessor exited without DONE; preserve state and inspect')

    # 3. Verify an IDLE driver/worker/router before touching anything.
    p = subprocess.run(['pgrep', '-f', '[r]un.py generate|[m]lx_vlm.server'],
                        capture_output=True, text=True)
    if p.stderr.strip() or p.stdout.strip() or h.listeners():
        raise RuntimeError('Expected idle driver/worker/router after predecessor completion')

    # 4. Build a FRESH overlay from the committed registry (strip local draft_*/moe_expand,
    #    assert the tune fields you expect), write it, and use ONLY the overlay from here on.
    data = yaml.safe_load((R / 'main_models.yaml').read_text())
    for entry in data['models']:
        for key in list(entry):
            if key.startswith('draft_') or key == 'moe_expand':
                entry.pop(key)
    overlay = D / 'overlay.yaml'
    overlay.write_text(yaml.safe_dump(data, sort_keys=False))

    # 5. Per model: router up on the overlay, pilot, full, grade, RESULT log line, unload.
    for model in MODELS:
        h.ensure_router(str(overlay))
        tune = '<tune-label>'
        if h.run_generate(model, '<bench>', tune, <n>, model + '_pilot', str(overlay),
                           extra=['--limit', '<bench>=5'], bound_h=4):
            raise RuntimeError('pilot generation failed')
        summary = h.summarize(model, '<bench>', tune, <n>, model + '_pilot')
        # size the full arm from summary['wall_mean_s'] and summary['wall_max_s'] here
        if h.run_generate(model, '<bench>', tune, <n>, model + '_full', str(overlay),
                           bound_h=<derived>):
            raise RuntimeError('full generation failed')
        h.grade(model, '<bench>', tune, model + '_full')
        h.log('ASSESSMENT OWED: <what a human/operator should read this against>')
        h.unload()

    h.stop_router()
    h.log('=== <THIS RUN> DONE ===')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        h.log('FATAL ' + repr(e))
        raise
```

**`helpers.py`** provides (copy, don't reinvent): `listeners()` (lsof-based :8000 listener PIDs
— never `pgrep -f "mlx-serve start"`, which double-counts the wrapper), `ensure_router(overlay)`
/ `start_router(overlay)` / `stop_router()` (env: `APC_ENABLED` popped, `MLX_VLM_CACHE_SESSION_MAX=2`,
`MLX_SERVE_CONFIG=<overlay>` — verified on the router PID's `ps -Eww` output before proceeding),
`unload()` (`POST /v1/models/unload` + `pgrep`-verified worker exit), `worker_cmdline()`,
`make_overlay(name, edits)` (surgical per-model overlay edits, sha-named, YAML-validated),
`run_generate(...)` — launches `run.py generate` detached, launches `bench_watch.py` alongside,
polls the manifest for **the C35 check** (`runtime.draft_kind` matches `expect_draft`,
`registry.sha256` matches the overlay's sha, `kv.moe_expand` matches expectation, sampling
matches the overlay) and KILLS the driver + watcher immediately on mismatch — never let a
mismatched arm keep generating rows — and separately checks the worker cmdline agrees on
draft-on/off state; `summarize(...)` (wall mean/max/sum, token mean/max, draft acceptance,
error list) and `grade(...)` (drives `run.py grade`, logs the score line).

**Monitor pattern:** `PYTHONPATH=$STACK_REPO/benchmark bench_watch.py --models <M> --bench <B>
--tune <T> --total <N> --driver-pattern "run.py generate" --out <path> --interval 300` runs
alongside every
`run_generate` call, self-evaluating every 5 minutes per the Stage 0 daemon-watcher rule.

**Never** use a bare `grep`/`tail`/`cut`/`head` pipeline as a monitor — these silently buffer
inside a `Monitor`-style pipeline. Use `tail -F` + `grep --line-buffered` + `awk` with explicit
flushing, and always include a known-positive self-test line so a monitor that stops reporting
is distinguishable from a monitor that has nothing to report.

---

## Appendix B — cost table (hours per stage, from measured history)

All figures are single-model, single-box (M5 Max 64 GB) observations from this campaign — they
are lower bounds for a new candidate of similar size/architecture, not guarantees. Cost
estimates on this campaign have been wrong by 2–18× more than once — always run the 5-item pilot
and size from ITS mean and max, never from a table like this one alone.

| stage | observed cost |
|---|---|
| 1. Acquire + register | download: network/disk-bound (tens of GB); uniform 4-bit convert: minutes; `mlx_optiq` mixed convert: tens of minutes–hours, quiet box only; vision graft + logit check: minutes |
| 2. Capacity gate | tens of minutes per rung; a 4-rung ladder to 256K has run overnight for a 3-model family |
| 3. F0–F1 (load smoke + n=15 convergence) | ~1–2 h total (observed on a 3-model family funnel) |
| 3. Vision gate (conditional) | ~1 h GPU upper bound per model (20 images × 2 turns) |
| 3. F2 (n=100 paired coding screen) | ~1–2 h GPU per bench per model |
| 4. Temperature ladder | ~25 min capped scan + ~15 min official n=15 rung; +hours if the knee triggers a re-screen |
| 5. `reasoning_effort` arm | ~1.3 h (medium) vs ~10.6 h (xhigh) for a paired n=164 humanevalplus arm, one observed family member |
| 6. Math500 n=100 | 0.81 h floor (`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`) to 21.7 h ceiling (runaway-tax-heavy model), same 100-item set |
| 7. Depth ladder pilot (5 items, deepest rung) | minutes/item shallow, growing to several minutes/item prefill alone near 128–256K |
| 8. opencode 22-item session | ~1.5–2 h, varies with stall-kill rate |
| 9. MTP: M6a smoke | ~15 min |
| 9. MTP: M6b/M6d paired n=164 OFAT | ~3.3–5.2 h (ON arm) + ~4.6–10.5 h (OFF arm) |
| 10. MoE expansion pilot (4 arms × 5 items) | <20 min observed |
| 10. MoE expansion full resolution | proportional to Stage 3's F2 coding-screen cost, doubled for native+expanded arms |
| 12. Judge panel (5 contenders, 40 items) | 2,400 verdict calls + 180 anchor calls — judge-API cost/wall-clock, not GPU (generation already counted in Stage 3/6) |
| 13. Promotion bookkeeping | driver-side, minutes |

---

## Appendix C — banned shorthands and the hook

**The rule (AGENTS.md):** full registry model names everywhere — reports, results, docs,
commits, AND chat prose. First use in every message and commit body. No bare `Nemotron`, <!-- allow-shorthand -->
`Ornith`, `the distill`, `gemma`, `the MoE`, `the OptiQ`, `qat-6bit`, `8bit`, etc. <!-- allow-shorthand -->

**Mechanism (`benchmark/bench/modelnames.py`):** NOT a fixed blocklist — it tokenizes every
registered model name in `main_models.yaml` into fragments (e.g. `A3B`, `OptiQ`, `4.5bpw`) <!-- allow-shorthand -->
and flags any of those fragments appearing standalone in an ADDED line without the model's full
name nearby. A line that must legitimately NAME a shorthand (e.g. explaining the rule itself, or
quoting someone else's shorthand) gets the `<!-- allow-shorthand -->` marker; find every marked
line with `git grep -n allow-shorthand`.

**Enforcement:**
```
git config core.hooksPath githooks     # once per clone
```
- `githooks/pre-commit` runs `PYTHONPATH=benchmark .venv-bench/bin/python -m bench.modelnames`
  AND `-m bench.piicheck` on staged ADDED lines (both checks run before either can fail the
  commit, so one attempt reports every problem). Fails OPEN if `.venv-bench` is missing (a
  broken hook on a fresh clone must not block committing).
- `githooks/commit-msg` runs `bench.modelnames --commit-msg "$1"` against the commit message
  itself — the rule explicitly covers commit messages, which is where it was actually caught
  failing.
- Bypass once (only when you have a specific reason): `git commit --no-verify` — this repo's
  standing rule is never to skip hooks without explicit user request; do not do this on your own
  initiative.

**This hook does NOT cover your chat responses to the operator** — hold yourself to the same
full-name rule there manually; it is graded on you, not enforced by tooling.
