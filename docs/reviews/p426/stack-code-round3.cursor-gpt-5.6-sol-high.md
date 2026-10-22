K1 — OPEN — HIGH — `benchmark/bench/p426_leg.py:409-414,475-495,621-640`  
The CLI imports `p426_plan` and `ChainOps` and parses arguments before its `BaseException` guard. Additionally, an interrupt during the final power-history check escapes `_speed_from_power()` before the receipt is written. Move the complete lifecycle under an outer guard and ensure final receipt publication occurs after independently guarded cleanup and power checks.

K2 — OPEN — HIGH — `benchmark/bench/p426_leg.py:423-470,508-538,642-657`  
The frozen record remains selected indirectly by caller-controlled `--workdir`, is parsed and hashed in separate reads, and neither repository state nor the frozen-file hash is rechecked at exit. A changed record can therefore yield pins from one version and `frozen_sha` from another; mid-leg source/submodule drift can still receive `VALID`. Resolve the canonical configured workdir, parse/hash one byte snapshot, and recheck build and frozen-record identity at exit.

K3 — OPEN — HIGH — `benchmark/bench/p426_plan.py:40-54`  
The adapter is implemented, but it is not executable at reviewed commit `4a12f62b`: its pinned `src/mlx-vlm` revision `2e66d89d` does not accept `--predictor` or emit top-level `predictor`. Every M1 invocation currently exits at argument parsing and becomes INVALID. The pending reviewed fork candidate contains B7, but the stack artifact needs that submodule bump plus an integration test against the actual script.

K5 — OPEN — HIGH — `benchmark/bench/p426_leg.py:306-338`; `benchmark/bench/p426_plan.py:86-89`  
Row-bearing requests are now reconciled exactly by session ID and counters. The reasoning calibration request remains unidentified: validation accepts any one unclaimed completed session because it checks only `leftover == 1`. Persist and validate the calibration request’s session ID explicitly.

K6 — CLOSED — `benchmark/bench/p426_leg.py:340-362,671-676`  
The history read must succeed, contain at least one syntactically valid timestamped source event, and contain no malformed line naming `Using AC` or `Using Batt`. Parsed-history failures invalidate speed.

L1 — OPEN — MEDIUM — `benchmark/bench/p426_leg.py:368-382,385-388`  
Sequential reruns preserve the original receipt, but publication is still check-then-`os.replace`. Concurrent invocations can both observe an absent target, share the same temporary path, and overwrite the primary receipt. Reserve the run atomically or publish through a no-replace primitive such as an exclusive hard link.

M1 — MEDIUM — `benchmark/bench/client.py:115-116`  
Problem: `probe()` always calls `_post(..., headers=None)` when the prefix is unset, changing the private call contract despite the stated “nothing changes” behavior.  
Failure scenario: existing stack tests and injected transports whose `_post` stubs accept only `(path, payload, timeout)` raise `TypeError`; several current tests use that signature.  
Fix: pass the `headers` keyword only when a session ID exists, or update every supported test seam and caller.

M2 — MEDIUM — `benchmark/bench/p426_leg.py:264-267`  
Problem: the wrapper’s own worker-argv check validates only `--model`. `ChainOps` checks ON comprehensively, but OFF permits unused `--draft-model` or `--mtp-verify-scan` flags when `--draft-kind` is absent/off.  
Failure scenario: a command-builder regression leaves predictor flags on OFF; telemetry remains inactive and the leg can be VALID although the runtime delta is not exactly the planned three-key delta.  
Fix: compare all relevant predictor flags against the selected registry for both arms, requiring their complete absence under OFF.

Operator escalation:

| ID | Context | Recommendation |
|---|---|---|
| K1 | Receipt coverage still excludes import/argument failures and an interrupt during final power inspection. Cleanup handling improved substantially, but the “every path” guarantee remains false. | Keep open and add one outer lifecycle guard. Counterpoint: these paths are uncommon and ordinary driver interrupts are covered. |
| K2 | Entry provenance is recorded, but its source is not uniquely or continuously bound. Separate reads and missing exit checks leave TOCTOU gaps. | Require canonical workdir, one frozen snapshot, and exit verification. Counterpoint: later pair verification may detect differing receipt hashes. |
| K3 | The stack adapter targets a fork interface absent from the reviewed commit. The pending candidate appears compatible but is not part of this artifact. | Accept only conditionally on the B7 submodule bump and a real interface test. Counterpoint: the approved DAG already schedules that bump before Wave 1. |
| K5 | Normal rows now have strong request attribution. Only the non-row calibration request remains fungible. | Persist its exact session ID. Counterpoint: an unrelated concurrent request is unlikely on the gated quiet box. |
| L1 | Normal reruns are immutable, but concurrent publication is not. The wrapper’s run-once invariant should not depend on operator serialization. | Use atomic exclusive reservation/publication. Counterpoint: campaign legs are normally launched serially. |
| M1 | The production transport works, but the no-prefix call ABI changed and breaks existing test doubles. This is likely to make the running full suite fail. | Make the new keyword conditional. Counterpoint: broadening all mocks to accept `**kwargs` would also resolve it. |
| M2 | ON is strongly checked by `ChainOps`; OFF is not exact for all three predictor flags. This weakens the wrapper’s independent runtime proof. | Add symmetric exact argv validation. Counterpoint: pinned registry generation makes such stray flags unlikely absent another bug. |

VERDICT: DISAGREE K1 K2 K3 K5 L1 M1 M2