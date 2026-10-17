G1 — blocker — `benchmark/bench/tg2_grade.py:416-417`  
Failure: `failing()` ignores failed leaves outside the expected universe. A synthetic initialization/teardown failure can coexist with all expected leaves passing and score zero failures.  
Fix: count every collected failure plus missing expected leaves, excluding only explicitly frozen optional-leaf IDs.

G2 — blocker — `benchmark/bench/tg2_grade.py:128-145`  
Failure: the Jest parser ignores top-level `success` and suite `status`. An `afterAll`/environment failure with passing assertions becomes a false pass.  
Fix: propagate top-level/suite failure onto that suite’s assertions or emit a counted failure event.

G3 — high — `benchmark/bench/tg2_grade.py:138-145,557-563`  
Failure: malformed-but-valid Jest JSON—for example a non-object assertion—raises `AttributeError`, bypassing `ReportError` and becoming infrastructure after the runner marker. This violates P360 and permits retry instead of model failure.  
Fix: validate the complete schema and normalize all report-shape errors to `ReportError`.

G4 — high — `benchmark/bench/tg2_grade.py:247,274-285`  
Failure: `JS_SKIP` rejects `test.skip`, so real `palindrome-products` and `robot-name` trees transport-abort. The spec requires those two optional leaves to be listed and excluded, not both items excluded.  
Fix: restrict refusal to rewritten `xtest`/`xit`/`xdescribe`; carry the two frozen optional IDs as explicit scoring exclusions.

G5 — high — `benchmark/bench/tg2_grade.py:290-310,349-353`  
Failure: deny patterns are case-sensitive while the worktree is on case-insensitive APFS. `Jest.config.js` is accepted as a helper but resolves as `jest.config.js`, allowing a custom runner/setup that spoofs outcomes.  
Fix: case-fold every security-sensitive path component and filename before deny matching; add APFS-case-variant tests.

G6 — medium — `benchmark/bench/tg2_grade.py:444-447,359-390`  
Failure: P360’s strip→tamper→grade ordering is not atomic. `grade()` strips but never tampers; callers following tg1’s tamper→grade pattern reject normal build output, while direct callers can omit tamper entirely. Real Docker tests omit tamper.  
Fix: expose and test one production entry point that strips, performs tamper validation, then grades.

G7 — medium — `benchmark/m65/tg2_image/Dockerfile:24-35`; `benchmark/m65/tg2_image/stage_context.py:41-45`  
Failure: npm caret ranges and Cargo manifests are resolved without committed locks. The pinned local image is verified, but cannot be deterministically rebuilt or recovered by the same digest.  
Fix: use frozen npm/Cargo lock artifacts or publish an OCI image/archive addressable by the committed digest.

G8 — medium — `benchmark/bench/tg2_grade.py:577-580`  
Failure: offline-dependency infrastructure detection covers only Rust/Java compile. Java runtime-only resolution and missing JS/C++ image dependencies can be scored as model compile/crash failures.  
Fix: preflight fixed runners/dependency closures and classify protected-build dependency failures in both phases as infrastructure.

G9 — medium — `benchmark/bench/tests/test_tg2_grade.py:782-800`  
Failure: real-container tests assert only nonempty/all-pass reference output and one stub failure. A parser consistently omitting leaves still passes; exact real-tool leaf IDs/counts and suite-level failures are never asserted.  
Fix: retain real raw-output fixtures with independently verified exact leaf sets, plus production-path tamper and failure fixtures.

Runtime image verification did match `sha256:944ed389…15f2`; `--pull=never`, `--network none`, phase cleanup, and guard registration were otherwise correctly implemented.

VERDICT: NOT CLEAREDAddendum—three additional findings:

G10 — medium — `benchmark/bench/tg2_grade.py:45-49,575-580`  
Model-controlled compiler text matching `OFFLINE_DEP` can convert a Rust compile failure into infrastructure abort. Preflight dependencies separately; never classify from free text alone.

G11 — medium — `benchmark/bench/tg2_grade.py:547-562`  
The marker proves the shell reached the invocation statement, not that the runner executable started. Preflight runner executables before emitting the marker.

G12 — medium — `benchmark/m65/tg2_image/build.sh:6-13`  
Image construction accepts any corpus checkout without recording/verifying `polyglot_sha`. Pin the corpus revision and embed its digest plus staged-context digest in image metadata.

VERDICT: NOT CLEAREDAdditional findings:

G13 — high — `benchmark/bench/tg2_grade.py:540-555`  
Execute timeout/OOM is classified before checking the nonce marker. A container-launch stall becomes model failure. Require the marker first; add a compile-start marker too.

G14 — high — `benchmark/bench/tg2_grade.py:296-347`  
Java package regex accepts package declarations hidden by comments or Unicode escapes, enabling JUnit namespace shadowing. Use Java-aware lexical parsing and enforce path/package agreement.

G15 — high — `benchmark/bench/tg2_grade.py:214-219,478-503`  
Containers lack PID and output-size limits. Fork bombs or unlimited output can exhaust host resources before timeout. Add PID/nofile limits and bounded output/report storage.

G16 — medium — `benchmark/bench/tg2_grade.py:429-469`  
`private` and `keep` may reside under mounted `work`, exposing reports and retained evidence to tested code. Require disjoint resolved paths.

G17 — medium — `benchmark/bench/tg2_grade.py:167-177,499-503`  
Failed OOM inspection is treated as “not OOM.” Make inspection tri-state and abort when container state cannot be verified.

VERDICT: NOT CLEARED
