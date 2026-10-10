**T1 — Medium: Amendment 2.6’s terminal recurrent-state execution test is still missing.**  
At [test_prefill_profile.py:562]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_prefill_profile.py:562), the test explicitly substitutes array-identity assertions for execution verification. It proves that the terminal `gdn` mark receives the stored state, but not that it evaluates that state before closing.

Concrete failure scenario: a regression skips evaluation at the terminal `gdn` mark; the later cache-state evaluation executes it under `cache_post`. This test still passes, and final outputs can remain identical while attribution is wrong. **Consequence: test gap and binding spec deviation; not evidence that current runtime attribution is wrong.**

Fix: wrap the terminal cache’s conv/recurrent arrays with execution-sensitive sentinels **after** the real GDN call stores them and before it returns. Assert execution during the `gdn` mark, with a positive control and a mutation that defers evaluation until `cache_post`. This avoids the test’s stated obstacle that projection sentinels execute inside GDN itself.

**T2 — Amendment 2 audit at `50081280`.**

| Item | Assessment |
|---|---|
| 1 | Satisfied: the entry fence includes precomputed position embeddings and reports `entry=`. [language.py:1403]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1403) |
| 2 | Satisfied for timing records: layer counts are averaged per window; undeclared forwards close on cache state before postprocessing. [prefill_profile.py:177]($HOME/ws/mlx-vlm/mlx_vlm/prefill_profile.py:177), [prefill_profile.py:266]($HOME/ws/mlx-vlm/mlx_vlm/prefill_profile.py:266) |
| 3 | Satisfied for the reviewed dense path: executed layer count comes from the actual layer/cache zip; capture kwargs make the terminal layer live. [language.py:1405]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1405), [ar.py:691]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:691) |
| 4 | Satisfied for EpiCache: consumed terminal queries close in preparation; `_scores` closes in `observe`; documentation agrees. [language.py:1002]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1002) |
| 5 | Satisfied: failure before a complete chunk emits the specified abbreviated diagnostic. [prefill_profile.py:228]($HOME/ws/mlx-vlm/mlx_vlm/prefill_profile.py:228) |
| 6 | Partial: T1 remains. |

**T3 — Coverage and runtime conclusion.**  
Dead terminal projections/MLPs, final norm/head, sentinel positive controls, terminal KV execution, and the single-read stderr check have substantive coverage. Terminal recurrent-state closure is only nominally covered. Position-embedding and observation tests primarily verify hook arguments, rather than independently detecting execution timing.

I found no additional concrete runtime defect introduced by the round-2 fix on the planned dense/native-KV/MTP path. The inherited timer synchronizes the current default stream, which is the generation stream inside the enclosing context. MTP chunk kwargs remain empty; its final-step hidden capture does not incorrectly make every prefill terminal layer live.

**T4 — Tests.**

```sh
cd ../mlx-vlm && TMPDIR=$TMPDIR PYTHONPATH=$PWD .venv/bin/python -m pytest mlx_vlm/tests/test_prefill_profile.py mlx_vlm/tests/test_mtp_profile.py -q -p no:cacheprovider
```

**69 passed, 2 warnings in 2.66s.** Initial sandbox execution failed before collection because temporary capture files were unwritable; the authorized retry passed.

**T5 — Verdict: FIX-THEN-SHIP.** Close the binding execution-test gap in T1.