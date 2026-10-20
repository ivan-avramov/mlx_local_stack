# P405 code review — round 1 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`), fork `p405-kv-scheme` `abbbfc84..fbefe877`

K1 — High — `dev/p369_phase2/kvmanifest.py:73-98`, `dev/p369_phase2/worker.py:1146-1149`  
Problem: The manifest supports unbatched cache classes, but the served continuous-batching path creates `BatchTurboQuantKVCache`, `BatchQuantizedKVCache`, and `BatchKVCache`. A batch TurboQuant leaf is recognized as TQ, then `_record()` accesses nonexistent `_kv_quant_mode`; batch affine/native leaves are misclassified by class name. Tests only use unbatched variants.  
Failure scenario: R2’s first real TurboQuant request raises `AttributeError` while producing evidence. Native smoke also reports every `BatchKVCache` as differing from `native`.  
Fix: Support all batch variants, expose/copy `_kv_quant_mode` onto `BatchTurboQuantKVCache`, and test manifests produced through the real `_make_cache()` path.

K2 — High — `dev/p369_phase2/kvmanifest.py:131-178`  
Problem: Expected manifests model `maybe_quantize_kv_cache`, but the server path uses `generate/ar.py::_make_cache`. These policies differ: `_make_cache` exempts the final layer for uniform quantization too, whereas F3 expects it affine. For a final `CacheList`, `_make_cache` also drops the parent’s `quantize=False` while recursing, whereas F3 exempts all children.  
Failure scenario: An affine fallback selected by R6 cannot pass its required R3 rerun; nested-cache models can also be rejected despite matching the actual served path.  
Fix: Base F3 on one shared policy used by `_make_cache` and the checker. Propagate `quantize` through `CacheList` recursion and add uniform-last-layer plus nested-final-`CacheList` tests.

K3 — Medium — `dev/p369_phase2/worker.py:1140-1149`  
Problem: The “exact live cache” evidence covers only the target `prompt_cache` captured from `generate_step`. The MTP drafter’s independent `rg.draft_model._cache` and its template are absent.  
Failure scenario: The smoke gate can pass while the MTP drafter has missing, extra, or unexpected cache leaves—the exact served MTP state requested by the review remains unproven.  
Fix: Record and gate a separate drafter manifest against `draft_model.make_cache()`, or explicitly narrow F3 to target KV and add independent fail-closed drafter-cache evidence.

K4 — High — `dev/p369_phase2/orchestrate.py:31-37`  
Problem: The plan says R3 adds `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, but `PICKS` still contains only Fable and Qwen3.8. The existing overlay logic also expects commented C177 lines, while Opus’s MTP tuple is already enabled.  
Failure scenario: R3 and default R5 runs omit the second affected main pick; explicitly requesting it causes a `PICKS` lookup/overlay failure.  
Fix: Add the Opus tuple, support already-enabled MTP registry entries, and test its `verify_policy=None`/per-query default and job construction.

K5 — High — `dev/p400_perf_probe.py:1-35`, `dev/p400_perf_probe.py:135-158`, `dev/p400_perf_probe.py:297-350`  
Problem: The probe cannot execute plan R5. It requires distinct trees and commit IDs, constructs one identical argv for both arms, measures only fixed 8K/256 decode throughput and decode peak, and applies P400’s gating bounds. R5 requires same final code with affine versus TurboQuant argv, plus prefill throughput/peak and a 256K leg.  
Failure scenario: The proposed codec-only ABBA either refuses identical code refs or compares the same codec in both arms; required R5 evidence is never produced.  
Fix: Add a codec-comparison mode or separate probe supporting per-arm overlays on the same attested commit and both prescribed measurement schedules.

K6 — Low — `mlx_vlm/server/app.py:948-962`, `mlx_vlm/tests/test_p405_cli_runtime_config.py:145-162`  
Problem: F2 logs raw `TQ_KV_QUANT_MODE`; when absent it prints `None`, although `TurboQuantKVCache` resolves the effective mode to `"mse"`. The test checks only that the field name exists.  
Failure scenario: Programmatic/non-CLI loading emits misleading authoritative codec evidence.  
Fix: Resolve the default to `"mse"` before logging, preferably pass that snapshot into cache construction, and assert its exact logged value.

VERDICT: NOT CLEARED K1 K2 K3 K4 K5 K6
