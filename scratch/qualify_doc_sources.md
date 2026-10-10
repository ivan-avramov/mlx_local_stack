# Sources map for docs/qualify-a-model.md (private, reviewer-facing; not committed)

Format: claim -> file:line (or command verified via --help / source read on 2026-09-12).
Paths are absolute on this box; the doc itself uses $STACK_REPO/$STACK_WORKDIR placeholders only.

## Stage 0 — ground rules
- One resident model, unload between: AGENTS.md:34 ("ONE resident model per machine, always...").
- MLX_VLM_CACHE_SESSION_MAX=2 mandatory: AGENTS.md:36.
- MLX_SERVE_CONFIG on driver env / C35: AGENTS.md:64 (C35 bit twice).
- APC off everywhere + verify ps -Eww: AGENTS.md:65; docs/serving-path.md:25-32.
- --sampling-profile deployed required (O36): AGENTS.md:53; benchmark/run.py generate --help (REQUIRED (O36) text).
- Explicit seeds: AGENTS.md:56; docs/metrics.md:55-58 (byte-identical without seed).
- Thinking always ON, budget = external truncation: AGENTS.md:48; docs/metrics.md:8-24.
- converged def + resolved budget clamp 0.8: docs/metrics.md:10,14.
- acc_strict ranks, pass@1|converged demoted: AGENTS.md:51; docs/metrics.md:41-43.
- Four numbers: AGENTS.md:51; docs/metrics.md:32-39.
- MDE table N=15..378: AGENTS.md:52; docs/metrics.md:49.
- Cluster bootstrap: AGENTS.md:52; docs/metrics.md:51-53.
- 5-item seeded pilot before n>=40, size from mean+max: AGENTS.md:63 (banner pitfall); docs/PLAN.md fail-fast funnel note re pilot rule (Standing constraints section, "Items buy power...").
- Client timeouts derived, --probe-timeout: AGENTS.md:66; benchmark/run.py generate --help (--probe-timeout text, C28).
- Transport errors escalate: AGENTS.md:66; benchmark/vision_gate.py --help docstring.
- Daemon watcher every 5 min: AGENTS.md:39; benchmark/m1/bench_watch.py --help.
- C35 provenance check content: queue/c_second_reference/helpers.py run_generate() (the "C35 check" log line + mismatch kill).
- Fingerprint/compare refusals: docs/serving-path.md:34-68 (suffix, fingerprint v3/v5); benchmark/bench/compare.py:39-69 (_FINGERPRINT_RUNTIME/_TUNE_SAMPLING_WARN/_TUNE_KV_WARN).
- Full registry names + hook: AGENTS.md:69; benchmark/bench/modelnames.py:1-42; githooks/pre-commit, githooks/commit-msg.
- PII rule: AGENTS.md:70; scripts/registry_commit.sh header.
- Workdir rule: AGENTS.md (NO FILESYSTEM POLLUTION line) + user memory workdir-artifact-rule.
- Registry of record + caslca insurance clone: AGENTS.md:31 (Mission/PLAN bullet), AGENTS.md Operating rules first bullet.
- Commit conventions: AGENTS.md (Commit prefixes bullet).

## Stage 1 — acquire + register
- main_models.yaml full schema example (Ornith entry): main_models.yaml:128-173.
- generation_defaults / FU-2 precedence: docs/serving-path.md:7-11.
- kv_prealloc_tokens == max_kv_cache_size structural rule: docs/serving-path.md:13-19; AGENTS.md kv_prealloc_tokens bullet.
- mlx_lm.convert flags: verified `uv run python -m mlx_lm.convert --help` 2026-09-12 (uniform 4-bit recipe: -q --q-bits 4 --q-group-size 64).
- mlx_optiq / optiq convert flags: verified `.venv-optiq/bin/optiq convert --help` 2026-09-12; recipe precedent docs/lab-notebook.md:1538-1539, :3705-3710 (optiq convert <bf16> --target-bpw 4.0 --reference auto).
- mlx_optiq cannot co-reside with AI session (quiet window): docs/box-notes.md:23.
- mlx_optiq version/import name (0.4.21, `optiq`), no pip in these venvs: docs/box-notes.md:13.
- MoE fused-expert unsupported in mlx_optiq mixed recipe: docs/box-notes.md:38; docs/lab-notebook.md:3708-3710 (30720 params not in model).
- Vision tower graft: scripts/graft_vision_tower.py --help (verified); docstring lines 1-20 (verbatim steps); scripts/graft_logit_check.py (bit-identical logit check pattern).
- MTP head split: src/mlx-vlm/mlx_vlm/split_mtp.py --help (verified 2026-09-12; --model-type choices incl qwen3_5, qwen3_5_moe, qwen3_next, deepseek_v4, glm4_moe_lite, inkling_mm_model).
- Registry fields to set (max_kv_cache_size, kv_quant_scheme, kv_bits, prefill_step_size, quantized_kv_start, generation_defaults, presentation): main_models.yaml Ornith/Qwen entries throughout (e.g. 128-165, 316-360).
- presentation.role candidate vs main + configgen filtering: configgen/source.py:1-13 (_ROLES, comment on candidate).
- configgen family whitelist {qwen,gemma,nemotron}: configgen/source.py:5; main_models.yaml:290-292 (C64 comment).
- configgen generate/check commands: configgen/__main__.py:44-60 (run() body); verified `python -m configgen generate|check` is the only interface (argv[0] in {"generate","check"}).
- HEAD-blob registry commit technique (swap->commit->restore + git hash-object/update-index pattern): scripts/registry_commit.sh:1-30 (mechanized version); docs/lab-notebook.md "Registry flip without stash" paragraph (2026-08-31 night) describing git show HEAD + git hash-object -w + git update-index --cacheinfo + git commit.
- caslca insurance clone / anonymous download verification via HfApi(token=False): docs/lab-notebook.md "M27 CERTIFICATION EXECUTED" section (HfApi(token=False) listing, sha256 match).
- Full registry model names in registry comments: main_models.yaml header comment lines 1-6.

## Stage 2 — capacity gate
- bench.run_capacity --help (verified); capacity_ladder.py: GATE_GB=46.0, DEFAULT_GRID=(160_000,192_000,224_000,256_000) (benchmark/bench/capacity_ladder.py:9-10).
- Capacity metric = mx.get_peak_memory, prefill spike: AGENTS.md Measurement discipline last bullet ("Capacity metric...").
- Hard gate <=46GB @256K: AGENTS.md Mission & priorities bullet.
- retrieval effective ctx / capacity_retrieval.json: benchmark/bench/run_capacity.py (retrieval_effective_ctx print, capacity_retrieval_scorecard call, lines ~57-90).
- Do not cite peak-memory from short-generation probes: docs/serving-path.md:19 (O15 caveat).
- Example measured capacity table (Nemotron ctx ladder): main_models.yaml:248-260.

## Stage 3 — vision gate
- docs/vision-smoke-m39.md:1-22 (gate protocol, 20 COCO photos, >=16/20 threshold, chain runner path).
- benchmark/probe_vision.py --help (verified) — one-image SEES/BLIND/UNREACHABLE probe.
- benchmark/vision_gate.py --help (verified) — full flags incl. --resume, --limit, --timeout derivation (C28).
- visionqa retained-not-run mechanically graded corpus (optional ranking leg): docs/vision-smoke-m39.md:24-69.

## Stage 4 — coding screens
- Fail-fast funnel stage defs (Stage 0-3, costs, verdicts): docs/PLAN.md lines 134-152 (sed -n '130,169p').
- benchmark/run.py generate/grade/status/compare --help (all verified 2026-09-12).
- Tiers table (light/mid/heavy item counts): benchmark/README.md lines 279-297.
- EvalPlus docker mechanics (ganler/evalplus, -v absolute mount, padding to full set): docs/box-notes.md:12.
- LiveCodeBench grading recipe (.venv-lcbgrade, PYTHONPATH): docs/box-notes.md:10.
- Regrade-vs-rerun decision rule table: docs/regrade-vs-rerun-guideline.md:14-27.

## Stage 5 — temperature ladder
- Full recipe incl. capped fine scan: docs/metrics.md:16-24.
- C48 ladder example table + operator tie-break (t0.5 over t0.3): docs/PLAN.md line 39 (C48 temperature follow-up row); README.md lines 67-77 (C48 table).
- Coarse grid 0.7/0.5/0.3, knee rule: docs/metrics.md:21.

## Stage 6 — reasoning_effort
- --reasoning-effort {xhigh,medium,low}, REQUIRES --tune: benchmark/run.py generate --help.
- M24 recipe + readback gate (42-token-shorter template as behavioral proof): docs/campaign-results.md lines ~938-951 (M24 CLOSED section, "Effort readback passed").
- FU-2 general readback rule (resolved value must differ from default): docs/serving-path.md:11.
- reasoning_effort in registry generation_defaults: main_models.yaml:351,490.
- M24-class compare.py refusal on reasoning_effort mismatch: docs/campaign-results.md line 75,100 (compare.py REFUSES: reasoning_effort differs).

## Stage 7 — reasoning proxies for C
- Math500 matched-id mechanism (queue/resolution/ids.json, --ids): queue/c_second_reference/run.py (sets=json.loads(...ids.json...)['math500']; --ids math500=... construction).
- --ids flag semantics: benchmark/run.py generate --help (--ids section).
- M33 vs M37 item-set warning: README.md line 50 ("Do not directly compare scores across these sets").
- IFEval mechanics + gating: benchmark/README.md lines 94-104.
- BFCL native-FC entry point (current, D1): benchmark/bench/run_bfcl_fc.py --help (verified); docs/PLAN.md D1 row.
- BFCL legacy path: benchmark/README.md lines 106-131; docs/box-notes.md:11.
- GPQA gating (HF_TOKEN + terms): benchmark/README.md lines 76, 194-196.

## Stage 8 — depth ladders
- bench.run_reasoning --help (verified): vartrack ladder, --deep-from/--deep-samples/--early-stop-budget-hits, --sampling-profile required.
- bench.run_retrieval --help (verified).
- >=0.85 effective-context threshold: AGENTS.md Mission & priorities bullet; benchmark/README.md lines 211-213,236-237.
- Derived max prompt per model / 0.8 clamp preflight: docs/box-notes.md:33.
- d64k/d128k cliff-check precedent + --depth-tokens flag: docs/PLAN.md M12 row (sed 130-169 output); benchmark/run.py generate --help (--depth-tokens).

## Stage 9 — agentic legs
- opencode M3 22-item set, O39 protocol, stall-kill/progress gate language: docs/PLAN.md M3/M9/M26/O39 rows; docs/box-notes.md "opencode costs ~18,050 prompt tokens" line 24.
- Progress gate 300/3600/2 dsh: docs/PLAN.md M35 row ("progress gate (300/3600)").
- dsh adapter facts: docs/PLAN.md M35 row full text.
- aider retired: AGENTS.md client table row (aider RETIRED 2026-08-16).
- benchmark/README.md aider/BFCL/SWE-bench sections: benchmark/README.md lines 133-192.
- session_pass vs final non-comparability: docs/box-notes.md:31.
- M1 aider harness non-obvious facts (seeded exercise pinning, APC, RETRY_TIMEOUT, fresh run tag, duplicate router check): benchmark/m1/README.md full file.

## Stage 10 — predictor certification
- m1/mtp_probe.py --help (verified via `cd benchmark && python -m m1.mtp_probe --help`): gate <1.3x language, flags.
- M6a/M6b recipe + decision rule (<1.3x close / >=1.3x continue): docs/PLAN.md M6 row.
- M6b/M6d OFAT n=164 TOST +-5pp certified numbers: main_models.yaml comments lines 136-144 (Ornith M27), 219-224 (Qwen3.6-27B M6b), 333-339 (Qwen3.8-27B M6d).
- draft_kind/draft_model registry fields + measurement stays draft-OFF: main_models.yaml same blocks; docs/serving-path.md:46-54 (fingerprint v3 mechanism).
- split_mtp.py flags: as above (Stage 1 source).
- HF sidecar upload + anonymous verification: docs/lab-notebook.md M27 execution section.
- Suffix decoding OFF and why: docs/serving-path.md:34-54 (saga); one-liner in AGENTS.md pitfalls.
- Penalties vs speculative exclusivity: docs/serving-path.md:56-58; AGENTS.md pitfalls bullet.

## Stage 11 — MoE expert-budget expansion
- Full recipe LS-LE:N:T:D, CLI --moe-expand, fingerprint inclusion: docs/specs/m34-moe-expert-expansion.md (full file read).
- moe_expand.py module docstring (algorithm): src/mlx-vlm/mlx_vlm/models/moe_expand.py:1-40.
- M34 experiment recipe + decision (native retained): docs/specs/m34-moe-expert-expansion.md "Experiment" section; docs/PLAN.md M34a/M34c/M34r rows; README.md lines 30-33.

## Stage 12 — KV-cache options
- kv_quant_scheme uniform vs turboquant, kv_bits semantics: main_models.yaml:12-14 (top Notes block).
- kv_prealloc_tokens rule + OOM history: docs/serving-path.md:13-19.
- Session-cache x prealloc audit (MLX_VLM_CACHE_SESSION_MAX default 8, cap=2 recommendation): docs/PLAN.md D6 row.
- APC OOM history (16384 blocks -> ~33GB, 54.2GB resident, METAL OOM): docs/serving-path.md:31.

## Stage 13 — judge panel C
- docs/judge-panel-c.md full file (corpus, anchors, gate thresholds, ranking units).
- bench.judge_anchors.py --help, bench.run_judge_pairwise.py --help, bench.judge_gate.py --help (all verified 2026-09-12).
- Gate FAIL 2026-09-12 example + two-judge limitation C68: docs/PLAN.md M38 row.
- run_judge.py (older code-quality panel, distinct from M38): benchmark/README.md lines 239-269.

## Stage 14 — promotion & shipping
- Pick = (model, tune, predictor) triple: docs/model-ledger.md:27-32.
- Promotion rule (holistic architect judgement, prune/park/continue): docs/model-ledger.md:175-182; docs/PLAN.md fail-fast funnel Verdicts bullet.
- README B/C ladder format (<=4 entries, Best-for column, evidence tables): README.md lines 1-79 (verbatim structure reused).
- Registry-of-record rule, caslca insurance clone requirement, PROVISIONAL labelling: AGENTS.md Operating rules first bullet.
- Model cards directory + upload receipt pattern: docs/model-cards/ dir listing; docs/PLAN.md D11 row (model_card_upload_manifest json).
- publish_models.py --help (verified): --apply/--prune/--url/--email.
- configgen role=main registration: configgen/source.py (_ROLES, role==main requires family).
- open-questions.md C-item queue format: docs/open-questions.md structural headers (O-number sections).

## Stage 15 — regrade/rerun + landing checklist
- docs/regrade-vs-rerun-guideline.md full file.
- Handoff rewritten in place: docs/PLAN.md file-role table line 17; docs/README.md line 7.

## Appendix A — chain runner template
- Full run.py + helpers.py read verbatim: queue/c_second_reference/run.py, queue/c_second_reference/helpers.py (both full files, 2026-09-12).
- bench_watch.py --help (verified) for the Monitor/daemon pattern.
- Predecessor DONE-wait + idle-driver/worker/router check pattern: same run.py (command_for(), pgrep check, h.listeners()).

## Appendix B — cost table
- Stage costs (minutes/hours) from docs/PLAN.md fail-fast funnel section (Stage 0 minutes, Stage1 ~1h, Stage2 ~1-2h, Stage3 hours).
- M2 Qwen3.8-27B funnel timings: docs/PLAN.md M2 row.
- opencode M3/M4 run costs (~1.7h+0.9h, ~0.7h): docs/PLAN.md M3/M4 rows.
- M6a/M6b MTP timings (~15min smoke; M6b ~1 evening): docs/PLAN.md M6 row.
- M12 depth pilot/full sizing (5-item pilot sizes 16h/model full; n=50 ~5h/model): docs/PLAN.md M12 row.
- M27/M6d OFAT wall times (3.28h/4.65h; 5.16h/10.52h): main_models.yaml comments (136-144, 333-339).
- C63 Math500 wall (21.72h/100 items) vs Nemotron (0.81h/100): docs/PLAN.md C63 row; README.md line 54.
- M38 judge panel call volume (2400+180 calls, judge-time not GPU): docs/judge-panel-c.md:89, docs/PLAN.md M38 row.
- M39 vision gate GPU upper bound (~1h/model): docs/PLAN.md M39 row.
- moe_expand pilot (5-case arms, ~20min observed M34c): docs/PLAN.md M34c row.
- Cost estimates historically wrong 2-18x / 2.5x pitfall: AGENTS.md pitfalls section (n>=40 pilot bullet); docs/PLAN.md line 49-51 (Phase 2 costs re-derived note).

## Appendix C — banned shorthands + hook
- Fragment-detection mechanism (not a fixed blocklist): benchmark/bench/modelnames.py:1-42 (module docstring "WHY NOT A BLOCKLIST").
- ALLOW_MARKER = "allow-shorthand", git grep -n allow-shorthand: benchmark/bench/modelnames.py:41-42.
- Hook install command `git config core.hooksPath githooks`: githooks/pre-commit header comment.
- pre-commit runs bench.modelnames + bench.piicheck on staged ADDED lines; commit-msg runs bench.modelnames --commit-msg: githooks/pre-commit, githooks/commit-msg (both full files read).
- AGENTS.md full-registry-names rule + example banned shorthands list: AGENTS.md "FULL registry model names everywhere" bullet.
