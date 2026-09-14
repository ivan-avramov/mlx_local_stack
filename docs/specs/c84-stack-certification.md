# C84 — Activated stack certification

Operator scope, 2026-09-14: finish activation through GitHub, test changed paths, and keep working until the updated stack can be certified. This supersedes the earlier activation hold and authorizes repair of failures found in these checks. It does not request a stack push or a new model ranking.

## Required checks

1. Push tested parent fork commits to GitHub before advancing stack gitlinks. Fetch through submodule origins, verify published heads, commit exact pointers and lockfile. Startup must retain committed pointers. Main serving imports must resolve to these submodule checkouts with the intended locked versions.
2. Run full MLX-VLM regression suite after repairs, MLX-Serve tests, and stack startup/provenance/configuration checks. Target cache allocation/restore/rewind, MTP verification, sampling, streaming/tool routing, and multimodal handling explicitly.
3. Run the existing five-case live smoke for both deployed models: arithmetic, constrained Python, exact JSON, native tool continuation and vision. Preserve full-cap preallocation, deployed sampling, predictor ON, APC absent and two retained sessions. A transport failure or Metal OOM blocks certification.
4. Reproduce and resolve C85's native16 continuation failure. Cover its original sequential smoke, fresh tool-pair control and a growing-conversation cache-reuse check. Use failing cache-lifetime and real-MLX trim/retirement regressions before the repairs. Verify the new native16 registry retirement setting at the worker command line; TQ4 policy is unchanged. Do not lower the context/preallocation floor or silently change the default cache mode.
5. Replay the canonical native16 largest-context probe plus calibration with the exact C82 payloads. Record MLX peak, prefill/decode, completion, cache reuse and MTP counters. Rough48GB is descriptive; require successful execution and interpret observed pressure/stability. Repeat on the final fixed revision as needed; preserve pre-fix evidence.
6. Run a bounded fresh before/after-repair quality screen in this actual stack checkout: five frozen C77 tasks on each of Math500, HumanEvalPlus, MBPPPlus and prose for each deployed model (40 pairs/80 requests across the two source states, with the same MLX0.32.2 runtime and deployed native16/TQ4 modes). Use canonical request builders/seeds/grading and separate manifests. Seal identical serialized inputs across phases. Existing C82 native16 rows provide additional context where payloads agree; they do not replace the fresh baseline. The final treatment includes C85 ownership/trim/eager-retirement repairs, newly available upstream9ef622c4/434afb1a, and native16-only idle-cache retirement. Preserve the original registry and metadata-module snapshots; allow only that declared structural-policy change and its provenance recording. All wire requests, sampling, weights, MTP, active cap/preallocation and installed package versions stay matched. This is not the original C77 pre-merge/runtime-bundle comparison. Inspect discordant outcomes before certifying. Prose hashes and lengths do not constitute quality scores; inspect the responses. No external judge calls.

## Evidence and stop conditions

Use independent review, known-positive instrument tests, real five-minute daemon supervision and derived timeouts without retries. Freeze sources/configs throughout each run; unload between models. Never grade infrastructure errors as wrong model answers. New failures require diagnosis and relevant retesting; passing an unrelated capacity request does not clear a continuation failure.

This certifies the specified runtime integration and serving cases. It does not establish universal quality equivalence, a complete native16 vision/reasoning-depth certification, or every newly supported model architecture. Preserve those limits in recommendations and the handoff.

Private instruments and raw evidence: `$STACK_WORKDIR/upstream/2026-09-14-activation`. Public results must redact machine-local paths and distinguish raw numeric memory flags from selection decisions. Commit coherent results; fork publication follows the explicitly authorized GitHub flow, while stack publication remains unrequested.

## Completed outcome,2026-09-14

All required bounded runtime checks completed on522671c4/b632280. C85 is resolved;40 paired outputs and official scores match, native16 largest-context peak47.155GB, with observed +5.95% prefill time and−3.75% decode-rate changes in one pair. Broader quality and original pre-merge effects remain outside this screen. The capacity wrapper's generic daemon had no rate-vs-baseline estimate; preserve its truthful records and correct that reporting gap before reuse. [Final evidence and limits](../stack-certification-2026-09-14.md).
