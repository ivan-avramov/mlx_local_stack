# P405 code review — round 2 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`), fork `p405-kv-scheme` `fbefe877..4e2f864c` (a first launch died on ECONNRESET with no output; rerun)

P1 — The production-pin check is clean: `git diff 7207179b 4e2f864c -- mlx_vlm ':!mlx_vlm/tests'` exited 0 with no output. I’m now checking the harness paths against the exact served/cache and probe behavior; the named P405 spec path is not present in `4e2f864c`, so I’m using the committed code, tests, and any available plan records rather than assuming the inline summary is the entire contract.Production pin verified: `7207179b..4e2f864c` has no non-test production changes.

K1 — Fixed. Batch variants are classified and rejected without crashing.

K2 — Contest accepted. The cached-session path uses `generate_step` → `maybe_quantize_kv_cache`; the live manifests support that conclusion.

K3 — Fixed. The drafter’s live cache is recorded, compared against its template, and required by the smoke gate.

K4 — Accepted disposition. The third pick belongs to the later P369 v13 harness series.

K5 — Core probe implemented, but not cleared because K7 and K9 make its arm evidence unreliable.

K6 — Fixed. The absent environment variable is logged as the effective `"mse"` default and tested.

K7 — High — `dev/p400_perf_probe.py:267-286`  
Problem: `served_check()` verifies only resolved `ResponseGenerator` configuration fields. It never verifies the live cache leaves produced by a measured request, despite claiming each leg asserts the served codec. This is the same distinction exposed by P405: configuration can say TurboQuant while the cache actually uses affine storage.  
Failure scenario: Arms A and B report `uniform` and `turboquant` respectively but instantiate the same cache codec. All requests and statistics remain valid-looking, producing decision-invalid ABBA evidence.  
Fix: Capture each request’s live target-cache manifest before releasing its session and validate it against the arm’s argv and model template using the F3 manifest logic. Store that manifest in the leg result and add a test where resolved configuration and live leaves disagree.

K8 — Medium — `dev/p369_phase2/orchestrate.py:899-943`, `dev/p369_phase2/orchestrate.py:1635-1643`, `dev/p369_phase2/orchestrate.py:2354-2362`  
Problem: C193 is broader than its documented ruling. The authorization path does not require `fits` to be false, and the ruling does not require or establish a finite `--wall-limit-s`, although its comment says the total-wall watchdog remains the cap. Existing tests cover failed evidence, wrong picks, tampering, and wrong exit codes, but not either missing invariant.  
Failure scenario: A fitting smoke relabelled `SMOKE_NOT_PASS`/2 authorizes under C193; more importantly, an over-budget smoke can authorize a full run without `--wall-limit-s`, giving `campaign_deadline()` infinity rather than the operator-accepted cap.  
Fix: Require `not fits` when applying C193. Encode the ruling as structured data containing its pick and wall cap, then enforce or supply that cap for the full run. Test both a fitting smoke and omission/mismatch of the required wall limit.

K9 — Medium — `dev/p400_perf_probe.py:509-518`, `dev/p369_phase2/orchestrate.py:32-37`  
Problem: Codec mode defaults to every orchestration pick, including Fable, whose registered campaign codec is `native16`. Changing only `kv_quant_scheme` cannot create affine and TurboQuant arms when `kv_bits` is absent. The synthetic overlay tests do not exercise the default pick list or generated argv.  
Failure scenario: The documented command without `--pick` either aborts because Fable lacks the expected scheme line or spends an ABBA run comparing native KV against native KV while labelling the arms affine and TurboQuant.  
Fix: Default codec mode only to the pre-registered quantized P405 pick, or explicitly set and validate `kv_bits` per arm. Add a test constructing default arm argv and asserting A/B resolve to affine/TurboQuant, backed by K7’s live manifests.

VERDICT: NOT CLEARED K7 K8 K9
