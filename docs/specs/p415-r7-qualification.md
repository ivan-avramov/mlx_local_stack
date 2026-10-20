# P415 — R7 256K operational qualification tool (plan v1, 2026-10-20)

Status: v1, before Cursor plan review round 1 of 3. Operator: "p415: go for it" (2026-10-20); "my primary pick across is the
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

## 3. Tests (CPU, red first)

T1 default entries are exactly the seven of §1; `--entry` must name one of them. T2 argv comes from the live registry without
overlay (a non-pick entry; no `--draft-model` when the registry has none). T3 the generalised served check refuses a drafter
the argv does not name, a missing one it does, a wrong verify policy, and any KV field off the argv. T4 request validation:
32 tokens, `length`, finite positive metrics. T5 the schedule: idle before every entry after the first; power refusal. T6 the
reference table loads, allows `null`, refuses an entry outside §1 or a missing source. T7 a fake end-to-end qualify on mocked
legs writes the report with per-entry outcome, peaks vs guidance / reference, and a nonzero exit when one entry fails.

## 4. Estimate and order

≈ 7 × (boot ≈ 1 min + 256K prefill ≈ 6–12 min) + 6 × 10 min idle ≈ 2–2.5 h GPU, quiet box, AC. Runs after R4 / R5 (one GPU run
at a time). Build → suites ×2 + 8 audits → Cursor code review (≤ 3 rounds) → smoke `--entry Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
(the native control, one entry) → full run → open-questions / campaign-results / README memory evidence update.

## 5. Out of scope

Quality (R6), MTP-ON memory (the MTP-certified entries are served MTP-OFF; their MTP-ON 256K peak belongs to the router-chain
re-certification), and any registry change (the operator rules per entry from the report).
