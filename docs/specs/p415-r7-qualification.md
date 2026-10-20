# P415 — R7 256K operational qualification tool (plan v2, 2026-10-20)

Status: v2 = v1 after Cursor plan review round 1 of 3 (`docs/reviews/p415/plan-round1.*`: DISAGREE Q1–Q8, all accepted; §2.1
adds them, §3 / §4 amended). Operator: "p415: go for it" (2026-10-20); "my primary pick across is the
Fable distill though so want to make sure that one is covered". Parent: `docs/specs/p405-kv-scheme-precedence.md` v4 §5 R7.

## 1. What it decides

Per entry, on the final production code (`7207179b` = P400 + P401 + P405) and the registry AS SERVED: does the entry load,
prefill a 256K prompt and decode, with the exact KV leaf layout its argv implies, and what are its prefill peak and rates.
Descriptive + operational, not a quality claim. Peak is reported against the ≈ 48 GB guidance (AGENTS.md: guidance, never a
rejection threshold) and against a recorded reference where one exists. Per-entry outcome feeds the operator's R7 call (P405
v4: a TurboQuant entry that fails or is not run gets `kv_quant_scheme: uniform` at promotion).

Entries (7): the six P405-affected TurboQuant entries — `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, `Qwen3.8-27B-mlx-uniform-4bit`,
`Qwen3.8-27B-static-mixed-4bit`, `Qwen3.8-27B-OptiQ-4.5bpw-mixed`, `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`,
`Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit` — plus `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (native KV, `kv_bits: 0`;
unaffected by P405) as the primary pick's own 256K record on the shipping code and as a native-KV control of the instrument.

## 2. Tool

`dev/p400_perf_probe.py qualify --stack-root . --tree <wt> --ref <sha> --python <fork venv> --out <dir> [--entry NAME ...]`
(fork-only, dev; branch `p369-v13`). Reuses the probe's leg machinery; changes:

- Q1 argv: `orchestrate.worker_argv(stack, <stack>/main_models.yaml, entry)` — mlx-serve's own loader + `_build_command` on the
  LIVE registry, no overlay (every entry runs exactly as served today: MTP-OFF for the four MTP-certified entries per C177 /
  C191). The registry's sha256 and the stack HEAD are recorded; the stack tree must be clean for `main_models.yaml`.
- Q2 served check, generalised from `served_check`: the drafter expectation and the verify policy come from the ARGV
  (`--draft-model` present / `--mtp-verify-scan` or none), not from `PICKS`; every resolved KV field equals `kv_from_argv(argv)`
  (P405 F3); the exact live leaf manifest (`kvmanifest.manifest_problems`) on the request's own cache — native leaves for Fable.
- Q3 request: one prompt sized to 261,120 post-template tokens (the codec long schedule's size; 255 × 1,024 + 64 < the 262,144
  cap), `max_tokens` 32, fixed seed, 0 warmup + 1 measured, must end `finish_reason == "length"` with exactly 32 tokens.
  Recorded: boot wall (s), active memory after load, prefill peak (`mx.reset_peak_memory` before the request,
  `mx.get_peak_memory` at the first streamed chunk — the existing probe hook), decode-phase peak, prefill and decode tok/s.
- Q4 reference peaks: a reviewed pinned file `dev/p415_reference_peaks.json` — per entry the recorded 256K MLX peak (GB), its
  KV codec at measurement and its source (doc path + entry / date), or `null` with "none recorded"; built from README /
  campaign-results / lab-notebook before the run, never from this run. Codec-mismatched references (affine-era, P405 R8) are
  labelled as such and never presented as like-for-like.
- Q5 outcome per entry: `COMPLETED` (loaded, request valid, manifest exact) or `FAILED <reason>` (load error, transport / HTTP
  error, manifest mismatch, invalid request); peak vs guidance and vs reference are reported, never a pass condition.
  Transport / HTTP errors abort that entry nonzero; the run continues to the next entry and exits nonzero if any failed.
- Q6 operations: tree attested clean at `--ref` before every entry; ≥ 600 s idle before every entry after the first;
  `pmset -g ac` 140 W / 28 V and battery > 20 % before every entry (refuse otherwise); no other `mlx_vlm` / `pytest` / bench
  process (the orchestrator's process check); a built-in 5-minute monitor (`orchestrate.Monitor`: entry, ETA vs estimate,
  errors, power, thermal); detached launch, background waiter; atomic `report.json`.

### 2.1 v2 — plan round 1 (Q1–Q8), all accepted

- **Q1 independent expectation (three-way).** A pure parser reads each entry's block from the registry bytes (YAML, the
  entry's own keys) into the EXPECTED served configuration; the argv is checked against it field by field, and the live worker
  against both. Never `kv_from_argv(argv)` alone. Fields: model path (`hf_path` / local path), `kv_bits`,
  `kv_quant_scheme`, `quantized_kv_start`, `kv_group_size` (CLI default when absent), `max_kv_cache_size`,
  `kv_prealloc_tokens`, `prefill_step_size`, `cache_session_shrink`, `attention_policy`, lazy prompt embeddings, MTP flags
  (`draft_kind` / `draft_model` / `mtp_verify_scan`: absent for all seven today) — each mapped to its CLI flag by a reviewed
  table; a registry key the table does not know refuses (no silent pass for a new knob). Keys present in the seven blocks
  today: serving — `hf_path`, `max_kv_cache_size`, `kv_prealloc_tokens`, `kv_bits`, `kv_quant_scheme`, `quantized_kv_start`,
  `prefill_step_size`, and (Fable only) `cache_session_shrink`, `attention_policy`, `lazy_prompt_embeddings`; non-serving,
  an explicit allowlist — `name`, `type`, `on_demand`, `presentation`, `generation_defaults`, `display_name`, `description`
  (the request's sampling comes from the server's own registry defaults and is recorded, not asserted: it cannot move the
  prefill peak).
- **Q2 live attestation of every peak-relevant field.** The worker records the value each of those fields resolves to where it
  is consumed (the `ResponseGenerator` / runtime config attribute and the kwargs captured at the request's generation call:
  `prefill_step_size`, `max_kv_size`, prealloc, attention policy, lazy embeddings) and compares it with the expectation; a
  field that has no observable consumer is listed in the report as `argv-only` (never silently trusted). Mismatch tests per
  field.
- **Q3 the measured prompt.** `Capture` records the measured request's templated ids: count must equal the sized count
  (261,120) and its digest the sizing digest; `cached_tokens == 0`; backend `cached_session`. A mocked-stream sequencing test
  pins the boundaries: `reset_peak_memory` before the request's input preparation, the prefill peak read at the first yielded
  chunk, a second reset, the decode peak at the end.
- **Q4 interference = failure.** Before every entry AND at every monitor tick during it: power 140 W / 28 V and battery > 20 %
  (`pmset`), and a qualification-specific process scan (any other `mlx_vlm` / `mlx-serve` / `mlx_lm` / `pytest` / bench /
  `opencode` process by full command line, including `python -c …` and console-script forms; own pids excluded). Any bad or
  unreadable tick during an entry marks it `INVALID <reason>` (its numbers kept but never reported as a qualification); a
  monitor failure is an entry failure.
- **Q5 lifecycle.** Each entry runs as one supervised job through `orchestrate.supervise` (own process group, deadline, kill
  + extinction check, atomic result file). The driver persists an atomic state per entry (`PENDING` → `RUNNING` →
  `COMPLETED | FAILED | INVALID`), and on interruption (SIGTERM / SIGINT) marks the rest `NOT_RUN`, kills the live job's group,
  verifies extinction and writes the final report; exit nonzero unless every entry is `COMPLETED`. Tests: load failure,
  transport exception, HTTP error, timeout, malformed / missing result, SIGTERM mid-entry, continuation, final status.
- **Q6 executable binding.** Before every entry and at exit: stack HEAD, `main_models.yaml` sha256 (unchanged during the run),
  the `mlx-serve` submodule HEAD equal to the stack's gitlink and clean, and the imported `mlx_serve` module path inside that
  submodule (the argv builder); fork tree attested at `--ref`. Recorded: Python, mlx / mlx-metal versions, each model
  snapshot revision + weight file sha256 (the P369 `check_snapshots` helper).
- **Q7 reference comparability.** `dev/p415_reference_peaks.json` entries carry the source path + line, the source file's git
  blob id, and the fingerprint the source states (prompt tokens, KV codec — with the P405 window flag, MTP state, attention /
  prealloc settings where stated, mlx version, measurement method); a delta is computed ONLY when the fingerprint matches this
  run's on every stated field, otherwise the reference is shown as "non-comparable: <fields>". Known in advance: references
  exist for five of the seven entries; `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` and
  `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit` have none.
- **Q8 deadlines.** Boot ≤ 600 s; the request deadline from the prompt and a floor prefill rate: 261,120 / 150 tok/s + 32 / 2
  tok/s + 600 s ≈ 2,360 s; per-entry job deadline 3,600 s incl. cleanup; worst case 7 × 3,600 + 6 × 600 ≈ 8 h, nominal
  2–2.5 h. Timeouts are entry failures (`FAILED timeout`), never retries.

## 3. Tests (CPU, red first)

T1 default entries are exactly the seven of §1; `--entry` must name one of them. T8 (Q1 / Q2) the registry-parsed expectation:
an unknown registry key refuses; each mapped field's mismatch (registry vs argv, argv vs live) fails the entry. T9 (Q3) prompt
count / digest / cached tokens / backend and the peak-boundary sequencing. T10 (Q4) a bad power tick or an interfering process
(incl. `python -c` and console-script forms) mid-entry marks it INVALID. T11 (Q5) the lifecycle cases listed there. T12 (Q6)
a dirty or mismatched `mlx-serve` submodule, a registry change mid-run, and an `mlx_serve` imported from elsewhere refuse.
T13 (Q7) a delta only for a matching fingerprint. T2 argv comes from the live registry without
overlay (a non-pick entry; no `--draft-model` when the registry has none). T3 the generalised served check refuses a drafter
the argv does not name, a missing one it does, a wrong verify policy, and any KV field off the argv. T4 request validation:
32 tokens, `length`, finite positive metrics. T5 the schedule: idle before every entry after the first; power refusal. T6 the
reference table loads, allows `null`, refuses an entry outside §1 or a missing source. T7 a fake end-to-end qualify on mocked
legs writes the report with per-entry outcome, peaks vs guidance / reference, and a nonzero exit when one entry fails.

## 4. Estimate and order

≈ 7 × (boot ≈ 1 min + 256K prefill ≈ 6–12 min) + 6 × 10 min idle ≈ 2–2.5 h GPU nominal (worst case ≈ 8 h, §2.1 Q8), quiet box, AC. Runs after R4 / R5 (one GPU run
at a time). Build → suites ×2 + 8 audits → Cursor code review (≤ 3 rounds) → smoke `--entry Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
(the native control, one entry) → full run → open-questions / campaign-results / README memory evidence update.

## 5. Out of scope

Quality (R6), MTP-ON memory (the MTP-certified entries are served MTP-OFF; their MTP-ON 256K peak belongs to the router-chain
re-certification), and any registry change (the operator rules per entry from the report).
