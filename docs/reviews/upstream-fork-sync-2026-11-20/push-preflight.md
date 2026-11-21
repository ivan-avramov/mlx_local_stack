# Upstream history push preflight

The current published stack gate at `9abef6a6` scans the MLX-VLM push range from the fork's published `babb0c9d` to the verified upstream tip `fd6404fb`. There are 335 incoming upstream commits. The scan found 119 model naming matches in diffs and 13 in commit messages. It reported 19 PII-pattern matches in one upstream commit, for 37 flagged commits in all. The first 29-commit batch alone has 34 naming matches.

The PII-pattern matches all occur in upstream `3d58bac9`. Seven come from absolute paths in a distributed-serving example explicitly marked for replacement by the reader. Twelve come from Python attribute expressions parsed as mDNS hostnames. The scan reported no token-shaped findings.

A conventional merge preserves all incoming upstream commit identities. A fixup to the merge result cannot alter findings on an ancestor. The pre-push gate needs a separately approved, test-first exception for the reviewed immutable findings before this sync can be published. Bind the exceptions to the exact fork, commit, source and finding content. Preserve the existing scans for every other match and every fork-authored change, and retain exact-tip gate requirements.

## Preserved work

- MLX-Serve moved locally by fast-forward to published `0555b2f`. This history contains upstream `754d8d5`. Its full gate passed with 543 tests passed and one expected skip.
- The independent baseline suite passed 919 tests with one optional skip. It includes 146 real sibling cases and nine new default-chat and preload boundary checks. Candidate tests are pending.
- The first MLX-VLM merge batch through `bf02cd02` is staged in an isolated fork clone with the merge parent recorded. The pinned formatter and all eight audits that inspect source passed. The first runtime copy audit used an environment without the supplemental cryptography dependency. Retry uses the ordinary gate packages and records its result separately.
- The corrected copy run identified three exact assertions for the fork's documented opt-in chat compaction and snapshot-based hybrid rewind. Their behavioral counterparts passed alongside the chat contracts (68 passed). After recording those exact cases in the audit baseline, the upstream-copy audit passed with 50 known and zero new failures.
- The first full suite attempt was interrupted after the environmental dependency omission was found (1,223 tests passed at interruption). Full-suite verification with the corrected isolated environment remains required before the first batch commit. The fork index has no unstaged changes. The stack's tracked pins and all GitHub branches are at their prior tips.

## First exact fork pair

Commit `50556bf2` paired with `0555b2f`: every gate step exited zero. The suite passed 11,796 cases with 20 skips and 22 expected failures. All 146 cases that require the MLX-Serve sibling passed. The receipt refused five new opt-in tests. Both checkpoint card tests and the audio checkpoint test require explicitly configured local model paths. Two real compaction cases require an explicitly configured inference model. Added those five exact cases to the tracked skip baseline. The final fork tip still requires a new full gate receipt.

The first exact run inherited the default pre-commit cache location. The launch script now sets the pre-commit cache under scratch before any subsequent gate.

## Recorded merge batches and prepared source

| Range | Evidence |
| --- | --- |
| Through `ff788e98` | Isolated merge `bade43a7`. The full staged run passed 12,148 tests and exposed three fixable failures plus the merge-ancestry assertion. Focused fixes passed 391 cases, the real merge passed its ancestry check, and the upstream-copy audit had zero new failures. Move the discovery class to its upstream-relative position and annotate exact protocol fixture values for the naming check. Its AST and 1,244 collected server test IDs are preserved, and the complete history scan is clear. |
| Through `0dcee78f` | Isolated merge `ddede0bd`. Early focused run passed 385 cases. The full staged run passed 12,527; 206 focused cases checked subsequent fixture repairs and the latent-cache round-trip on the existing adapter. The real merge ancestry and 135-commit history scan are clear. Four new dropped-content leads reduce to the preserved discovery-test AST and the adapted tool envelope. |
| Through `d3a16c34` | The actual merge stage preserves ordinary inline routing, cancellation and sampling. Separate compatible continuation groups use the same worker, and shared speculative MTP retains the fork's ordinary decoding fallback. Focused run passed 386 cases with 32 skips. The APC queue fixture was adapted to a valid prefill/completion width and the six direct admission tests passed. The raw upstream cases preserve their exact adapted or unsupported-contract dispositions. |
| Through `72309403` | Prepared tree `8c3ca31671d404177353f59f84dba68eb5ac109f`. The bounded prefill path retains constrained yields, zero-budget terminals, per-request seeds and existing speculative admission decisions. |
| Through `7fbe49ce` | Prepared tree `b86110c58430ef9b99a1ae946ac5d68c0eb2c004`. Preserve the verified unsharded projection dispatch, transactional MTP and existing rotating-cache behavior. New explicit projection paths and compatible new drafter paths have focused verification queued. |
| Through `cad00fff` | Prepared tree `07277114d102a5f4d90d90b1c68cb5b165ac17a0`. Primary startup still waits for model load and exits on primary load failure. Optional failure retains diagnostics. The normal route keeps cache arguments and the bound worker owns execution. HTTPX is promoted to a direct declaration with the same resolved version and all package records preserved. |

The independent managed-boundary, normal-chat and preload suite passed 11 cases on both the published baseline and the prepared `cad00fff` tree. Before the final comparison, the author added the stub's explicit teardown method and moved identical session assertions into the live request lifetime. The original failure came from the missing teardown method and post-shutdown cache clearing. The final frozen normal-chat test SHA-256 is `ed697050bd6edd4c9cd54b679fe476546556288043028d3aa30e10ce1fb790f8`. Mocked startup and ordinary chat showed no unexpected peer, subprocess or state-write activity.

## Combined fork candidate

Isolated merge `928ff0cb` records the fourth range. The remaining four reviewed ranges were replayed in their recorded order under the final merge parent `fd6404fb3261102600541127d59103dac65c2756`. The combined candidate retains the prior warm-peer APC and reranker repairs. The next independent full suite applies to the combined candidate, and the exact-tip official receipt follows the merge commit.

- The full manifest has the same resolved package records as the published fork, including MLX and MLX-Metal 0.32.4 and HTTPX 0.28.1. HTTPX is declared directly. The stack lockfiles are unchanged.
- Focused verification on the final pinned preview passed all 11 frozen readiness, normal-chat and managed-boundary cases. The combined candidate's initial focused run passed 2,408 cases and found ten failures. Exact fix runs covered 47 cache, stream and diffusion cases, five drafter-refusal and health cases, 119 audit self-tests, 151 upstream-copy counterparts, and the subword progress event. A legacy batch cache restored from serialized state now initializes its implicit allocation floor and empty pending padding before its next append.
- The final raw upstream-copy audit passed with zero unclassified failures. It records 211 specific failures under 183 narrow entries. One old APC refusal case now passes and 36 old parameter IDs were superseded by upstream's expanded matrices. Existing ordinary generation and cache controls remain exercised by the fork's own tests.
- The wide dropped-content pass added 15 lead groups relative to the fourth range. The startup progress change preserves the original router boundary. The local and distributed worker loops retain their separate admission and drafter semantics. Default-thinking and DeepSeek prompt rendering obey the explicit request and registry fields, and stream resolution remains local to the worker. Unsharded quantized verification keeps the validated dispatch, and the new projection kernels retain their direct tests. Other groups trace to fixture adjustments, bounded prefill and resumable diffusion routing, normalized greedy selection, or caller-owned MTP and DSpark adaptations. All of those dispositions retain a named targeted regression.

The combined suite's JUnit file recorded all 42 previously known skip or expected-failure IDs and 39 exact additional opt-in skips. The additions require explicit real-model continuation endpoints, reference dependencies or checkpoints for image-to-3D parity, full training, a newer optional document processor, or a warm local tokenizer cache. The gate still requires every mandatory case and rejects any other unexpected skip. A listed skip that runs successfully remains acceptable.

## Exact candidate

The complete staged JUnit run passed 14,752 tests and identified 95 failing or error results, including the pre-merge ancestry check. The retained checks were repaired in targeted groups. The legacy MTP stream accessor now resolves lazily through the same worker stream as production. The existing production-numerics and synthetic loopback tests passed in a 103-case run. A 55-case run covered every changed loader and shutdown fixture and both queue-timeout cases. Another 28 cases passed across token telemetry and the kept normal-chat, readiness and managed-boundary checks.

The first exact receipt for the combined merge stopped on two false scope matches in the call-argument audit when a standalone timeout test moved into an existing class. Keeping the test at its verified module scope, with the unused `self` removed, preserved both cases and cleared the audit. The refreshed exact candidate is `427a517a28b422085c8634f82fd36d32d9ae2fbc`. It contains the published fork baseline and all 335 reviewed upstream commits. The scan clears all 340 introduced commits under the P8 policy. All nine audits and pinned pre-commit checks passed on the corrected source.

The three GitHub main refs and both upstream main refs matched the recorded inputs at the final preflight. MLX-Serve's exact policy receipt remains current at `0555b2fe9637f6b01b2bd5acc834add79841aab7`. Operator acceptance and explicit authority are required before publication. The stack pins are updated after the new fork commit is reachable from GitHub.

## Publication readiness

| Repository | Exact tip | Official result |
| --- | --- | --- |
| MLX-VLM | `427a517a28b422085c8634f82fd36d32d9ae2fbc` | PASS. 14,845 passed, 58 skipped and 22 expected failures. All 147 cases requiring the exact MLX-Serve sibling passed. |
| MLX-Serve | `0555b2fe9637f6b01b2bd5acc834add79841aab7` | PASS under the current policy. 543 passed and one skipped. This tip already contains its upstream main. |

The official MLX-VLM receipt uses policy digest prefix `f4254f6b326b`. The installed hook preflight fetched the fork's public refs, accepted the exact proposed update to its main branch at level full, and performed only a check. One previously listed case ran and passed under the official gate. The exact reviewed upstream and public fork bases are unchanged.

The isolated gate and review branch records the accepted test inputs. Publication follows operator acceptance and in-turn push approval. Publish the verified fork, confirm GitHub reachability for both fork SHAs, then update the stack pins and run the stack gate on its exact commit before publication.
