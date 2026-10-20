# P405 plan review — round 2 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`), plan v2, fork `p400-tq-width2` `ce04439b`

## Round-1 resolution check

- T1: Resolved — T4 now uses `PATCH` and exercises replace restoration.
- T2: Resolved — logging moves to the resolved load path and the misleading environment log is removed.
- T3: Resolved — T2 correctly expects every CLI-written runtime field to fail before F1 and clears ambient variables.
- T4: Partially resolved — class placement is exact, but effective width/mode metadata is not explicitly gated; see T10.
- T5: Resolved — production remains unchanged until candidate qualification completes.
- T6: Resolved — R5 isolates the codec across both main picks and measures throughput and memory at short and long contexts.
- T7: Resolved — R6 uses matched arms, paired seeds, bootstrap uncertainty and multiplicity correction.
- T8: Resolved — R7 qualifies all six entries and falls back to affine per entry.
- T9: Partially resolved — evidence is classified by provenance, but the affine rule lacks an upper defect-window bound; see T12.

F1 is otherwise the right fix. No hidden `RuntimeConfig` alias, memoized getter, APC construction, reload child, or request-time reload path defeats replacing `runtime.config` immediately before `uvicorn.run`. Existing consumers dereference `runtime.config` dynamically, and reload children inherit the finalized environment.

T10 — HIGH — F3 does not fully gate the effective codec metadata required by round-1 T4. The stated `assert_served` comparison names only base bits and scheme, while the exact manifest specifies leaf classes but not split key/value widths and schemes, `TQ_KV_QUANT_MODE`, group size, or the resolved quantization start. A regression could serve TurboQuant classes with 4/4 MSE after argv requested 3/4 Prod; T2 would prove only that the configuration object was populated, and T5 could log the same incorrect constructor values. Change F3/T6 to compare every resolved `ResponseGenerator` KV field with argv and inspect every TurboQuant leaf’s key/value widths and mode. Represent the manifest by ordered layer path, not aggregate class counts, and explicitly test wrong width, mode, start and exempt-layer placement.

T11 — HIGH — MTP exactness is requalified for only one affected main pick. R3 names `Qwen3.8-27B-mlx-uniform-4bit`, while R5 confirms both affected main picks deploy MTP-ON. P400 itself demonstrates that exactness is codec-dependent, so matched benchmark quality or an undefined “M6d predictor re-certification” does not establish bitwise ON/OFF neutrality for `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. Add an explicit MTP exactness/state-neutrality gate on the chosen codec for every affected MTP-enabled main pick, including acceptance criteria and the M63 disposition, or state precisely that M6d supplies that proof for each pick.

T12 — HIGH — R8’s affine classification has no upper defect-window bound. It classifies CLI/router runs on any fork containing `83e2aadb` as affine; the fixed P405 fork also contains that commit. A post-promotion TurboQuant run lacking a leaf census would therefore be relabelled affine. Define the affine window as beginning with stack bump `111bb538` and ending immediately before the first stack bump containing P405. Make resolved-codec logs or leaf manifests authoritative, classify post-fix CLI TurboQuant runs as TurboQuant, and use `unknown` when neither authoritative evidence nor an unambiguous bounded code revision exists.

VERDICT: DISAGREE T10 T11 T12
