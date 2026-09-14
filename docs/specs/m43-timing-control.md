# C78 — Proposed long-context timing control

Status: **PROPOSED, NOT ARMED**. Separate from C77's 80-request quality diagnostic.

Question: does the lower long-context decode throughput observed against historical M41 reproduce in a fresh source comparison? Do not infer that battery power, missing Neural Accelerators, or one particular verifier change caused it.

Model: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, shipped deployed tune and repaired MTP ON. Compare original source `420c01e1` against integrated source `c5a6f97b`, **both on MLX/MLX-Metal 0.32.2** with the same other serving pins. Router sources `0ccc684` and `f8f1df4` have identical serving hashes. This isolates source configuration more narrowly than C77's original-versus-integrated runtime bundle comparison.

Run one nominal 131072 capacity probe per arm, each after a fresh worker and the same single calibration. Two measured requests plus two calibration calls. Preserve TurboQuant KV4, full cap/preallocation 262144, prefill 512, deployed sampling and the existing bounded 256-token capacity limits. Before launch, freeze the exact serialized prompt and an explicit matched seed; verify the seed's effective semantics against the inherited capacity path. Reject prompt/token-count mismatch or provenance drift. Preserve raw responses, server timing fields, wall time and draft counters. Use the reviewed calibration and prompt-attainment guards, derived timeouts, no retries, one resident model and independent five-minute daemon supervision.

Historical first-pick prefills 393.95 seconds and the current 520.05-second observation suggest roughly 15 minutes of measured prefill for the pair, excluding model loading, calibration, decode and other overhead. Allow headroom; this is an estimate, not a hard completion promise.

Decode throughput is server-reported; the existing capacity `prefill_s` metric is HTTP wall time minus server-reported decode time, so it includes other request overhead. Keep these definitions explicit. Compare the actual trajectories/counters rather than assuming equal aggregate counters mean equal per-round work. Report individual observations and uncertainty; one pair cannot estimate reliable repeatability or prove a population speed difference.

If the apparent slowdown reproduces, propose targeted phase profiling before choosing a kernel change. Do not restore old mathematics merely to recover byte-identical traces. This scope authorizes no code modification, quality study, judge call, model promotion or production activation until separately approved.
