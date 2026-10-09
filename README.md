# mlx_local_stack

Local model serving and evaluation on Apple Silicon: an OpenAI-compatible MLX router, an auxiliary task model, and OpenWebUI. Current measurements use a **64GB M5 Max**; hardware-specific recommendations are provisional.

## Run the stack

Requires macOS on Apple Silicon, [uv](https://docs.astral.sh/uv/) with Python 3.12+, and Docker/OrbStack for OpenWebUI. Configure Hugging Face access in `.env` (`HF_TOKEN`) if needed for model downloads.

```sh
git submodule update --init --recursive
uv sync --frozen
./runserver.sh
```

OpenWebUI runs at `http://localhost:3000`; clients use the router at `http://localhost:8000/v1`. The auxiliary task server uses port 8092. Ctrl+C stops the launched stack. [Serving configuration and operation](docs/serving-path.md).

[main_models.yaml](main_models.yaml) is the registry of record for model paths, MTP, cache settings and sampling. Client configs are generated from it:

```sh
uv run python -m configgen generate
uv run python -m configgen check
```

OpenWebUI startup reconciles the generated model list, parameters and default selection. [Update an existing instance](openwebui-init/README.md).

Keep the committed dependency pins: upstream maintenance follows **parent fork → review/test → push fork → fetch and bump stack submodule**. Do not use `git submodule update --remote` for routine startup. [Maintenance report](docs/upstream-integration-2026-09-13.md).

## Recommended models

Updated **2026-09-14**. B is agentic coding; C is research, brainstorming and design. Orders are operator-approved; evidence includes different historical configurations and incomplete coverage. **Use the registry's complete deployed settings**, including MTP companions and sampling defaults.

### B: agentic coding

| Rank | Model | Best for and supporting evidence |
|---|---|---|
| 1 | Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | **opencode 2.x, current record (M61 re-record, 2026-10-09, `opencode-v2-web`, 48K first-write allowance, audited web, two sessions, draft OFF):** Python **22/22**, 21/22; Go **21/21** twice — 85/86 (`go/counter` excluded as invalid, C145); its one miss a single thinking stream cut by the first-write window (C146); 0 web fetches; ≈ 3.5 h per 44-item session. Head-to-head vs the second pick: Python tie, Go s2 +14.3 pp [+0.00, +0.29] (inconclusive, trend). Superseded M59 (16K window): 80/86. opencode 1.18 medium: Python 22/22, Go 21/21, zero stalls. M55 polyglot (2026-10-04, two sessions, 22 items/language): Rust **19/19**, Java **17/17**, JavaScript 15/19 — leads both comparators on Rust and Java in both sessions, 66-item total 51/55 (s2 +13.6 pp over the second pick, TOST a_better). No contamination-resistant coding decider exists for this model generation (LiveCodeBench v6 ends Apr 2025; C110). AgentBench OS (shell agent, draft OFF, M54 record) 0.592, tied with `Qwen3.8-27B-mlx-uniform-4bit` at half its tokens and a quarter of its runaway share; non-tty run 0.613; clean-box re-sample (chain 4) 0.620, **18.5 s/task**, fastest dense arm, 1.4 % runaway share. Current t0.5, medium, repaired MTP ON, native16 KV with idle retirement; retrieval qualified through128K. |
| 2 | Qwen3.8-27B-mlx-uniform-4bit | Broader coding coverage; favorable Python/JavaScript repeats. **opencode 2.x, current record (M61 re-record, 2026-10-09, `opencode-v2-web`, 48K, audited web, two sessions, draft OFF):** Python **22/22** twice; Go 20/21, 18/21 — 82/86 (C145); every miss a stall (go/alphametics both sessions, one tool loop of 358 identical calls, one 37K-token churn); 0 web fetches; ≈ 4.9–5.5 h per session (1.4–1.6× the first pick). Head-to-head vs the first pick inside every interval. Superseded M59 (16K window): 74/86. opencode 1.18 medium: Python 19/22, Go 15/21 with six stalls. M55 polyglot: Rust 15/14, Java 15/12, JavaScript **18/20** (its one lead over the first pick, consistent across sessions, inconclusive); 31 stall kills over 132 items. AgentBench OS 0.592 (exact tie with the first pick, 2× tokens, 8.5 % runaway share; M54 record); chain 4 re-sample 0.585, **29.6 s/task** (1.6× the first pick). Current t0.6, medium, MTP ON, TQ4. |
| 3 | Ornith-1.0-35B-mlx-uniform-4bit | **Agentic evidence is opencode 1.18-era only — no v2 rows, not comparable with the picks' v2 results (C144: v2 chain owed before any promotion or displacement).** Rust and interactive coding: 17/22 Rust (C37), M55 polyglot Rust 15/17, Java 11/14, JavaScript 15/17 at ~0.6× the picks' wall per item; noisiest across sessions (8–9 discordant items of 22). AgentBench OS 0.535 (−5.6 pp vs the picks, inconclusive; one 81920-budget hit; M54 record); chain 4 re-sample 0.535, **14.2 s/task** (fastest per task; the same task runs away in both chains). t0.4, native routing, certified MTP. |
| 4 | Qwen3.6-27B-Opus-Distill-OptiQ-4bit | Repair-oriented fallback; older repair evidence is stronger than current agentic trends. AgentBench OS 0.620 (nominal best, +2.8 pp inside the interval; two 80-minute runaways, 5× the first pick's tokens; M54 record); chain 4 re-sample 0.613, **35.5 s/task**, the runaways did not recur (tokens 2× the first pick) but 16/142 turn-caps did — runaway cost is session-stochastic, turn-cap share is not. Deployed t0.3, certified MTP. |

### C: research and design

| Status | Model | Best for and supporting evidence |
|---|---|---|
| 1, provisional pick | Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | Everyday research/design; already the B default. Top-pair length-adjusted panel margin +0.25, 95% CI [−0.76,+0.91]; lower token/time cost informed the approved ordering. Shipped native16 vision smoke **20/20 PASS** (C88); retrieval **25/25** through128K and chain-4 tracking **39/39** through156K (C89). |
| 2, provisional pick | Qwen3.8-27B-mlx-uniform-4bit | Longer, more elaborated answers; first on the raw panel, with a length confound. Historical vision gate 19/20. MTP stays ON; its M40 MBPPPlus result remains INCONCLUSIVE. |
| Shortlist only | Ornith-1.0-35B-mlx-uniform-4bit | Fast vision-capable alternative; historical vision gate 20/20, behind both approved picks on the panel. |
| Shortlist only | NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit | Fast text-only tool, no vision tower; last on the panel. AgentBench OS 0.423, clearly last (−17 pp vs the picks, Holm p<0.01; M54 record); chain 4 re-sample 0.394, 12.2 s/task — not a shell-agent model. Deployed t0.5, native routing, predictor OFF. |

The panel used 38 shared items (approximate MDE 20pp). Vision gates establish bounded capability, not a visual-quality ranking. [Per-language/session evidence, intervals and historical comparisons](docs/model-recommendation-evidence.md).

## Latest validation

**C84 runtime integration passes** on MLX-VLM `522671c4`, MLX-Serve `b632280`, MLX/Metal 0.32.2. Both picks pass tool/vision serving screens; the native16 tool-continuation OOM is fixed, with full 262144-token active preallocation retained.

| Evidence | Result and limit |
|---|---|
| AgentBench OS (M54, record = chain 3, 2026-10-02) | 142 upstream `os-std` shell-agent tasks, pty harness faithful to upstream, draft OFF, deployed sampling. acc_strict@81920: `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` **0.620** (2 runaways, 5× tokens), `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` **0.592**, `Qwen3.8-27B-mlx-uniform-4bit` **0.592**, `Ornith-1.0-35B-mlx-uniform-4bit` 0.535, `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` 0.423. Dense Qwen checkpoints tie within ±6 pp (MDE ±11.5 pp); first pick at half the tokens and a quarter of the runaway share. Non-tty chain 1 (sensitivity run) agrees on ranks. [Report](benchmark/results/agentbench_os_compare_chain3.md). **Latency per task (chain 4, quiet box, 2026-10-03, the only citable wall-clock):** first pick **18.5 s**, `Ornith-1.0-35B-mlx-uniform-4bit` 14.2 s, `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` 12.2 s, second pick 29.6 s, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 35.5 s; chain 4 acc re-sample 0.620 / 0.585 / 0.535 / 0.613 / 0.394 (4–6 flips per arm vs chain 3, ranks unchanged). [Chain 4 report](benchmark/results/agentbench_os_compare_chain4.md). | **Seed note (C121, 2026-10-06): AgentBench seeds every item with base 0, so both sessions used the identical seed schedule; sessions differ by server state only. Ranks were stable; no rerun.**
| Polyglot language gap (M55, 2026-10-04) | C37 22-exercise draws for Rust/Java/JavaScript, opencode 1.18.30, draft OFF, deployed sampling, two fresh-instance sessions per model (C109). **Seed note (C121, 2026-10-06): opencode 1.18.30 sessions sent no sampler seed — both sessions ran on the server's default seed; they are repeated draws under different server state, not independent seeded sessions. Ranks were stable; no rerun.** `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` Rust 19/19, Java 17/17, JavaScript 15/19; `Qwen3.8-27B-mlx-uniform-4bit` 15/14, 15/12, 18/20; `Ornith-1.0-35B-mlx-uniform-4bit` 15/17, 11/14, 15/17. Per-language MDE ±27 pp (coverage screen); all-66 s2: first pick +13.6 pp [+3, +24] over the second pick. [Report](benchmark/results/m55_polyglot_gap_report.md). |
| Quality regression screen | All 40 paired answers/reasoning match; all 80 responses converge. Native16 Math500 5/5, HumanEvalPlus 4/5, MBPPPlus 5/5; second pick 5/5 each. Ten reviewed prose ties retain shared factual/methodological weaknesses. |
| Native16 at 261449 prompt tokens (pre-M57 serving, 2026-09-14) | **47.155GB** MLX peak; **1165.33s** prefill; **11.51tok/s** decode. Memory is a rough 48GB target, not a strict cutoff. Shipped serving since M57 (2026-10-05; fork merged with upstream v0.7.6 on 2026-10-06 with byte-identical outputs): **37.97GB** peak and **≈780–830s** prefill at the same rung (one session each; see the M57 row); with M58 (2026-10-06, two sessions) cold-rung decode at 256K **13.0–13.4 → 15.6–16.0tok/s** and sustained decode **+19.7 %** at 240K, **+14.8 %** at 128K (see the M58 row). |
| Shipped-state certification run (M60, 2026-10-06, on the merged fork `b17b12a9`; PROVISIONAL labels retained) | `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, exactly as served (native16 + `fused_v1` + lazy embeddings + `joint_v1`, MTP ON), paired to the M40 rows (TQ4 KV, fork `420c01e1`): Math500 `acc_strict@81920` **0.98 vs 0.99**, −1 pp CI95 [−5, +2] (3 discordant items; vs the predictor-OFF reference +1 pp [−2, +5]) — INCONCLUSIVE under the pre-registered rule (the lower bound sits on −5 pp); judge panel (3 judges, gate PASS 6/6 with the panel of the run): shipped state preferred **0.425 [0.31, 0.54]**, p = 0.19 — no detectable drift at n=40 (MDE ±20 pp). 100/100 and 40/40 converged; decode 45.8 / 35.4 tok/s; acceptance 0.76 / 0.61. Pilot-twice identical. Detail: `docs/campaign-results.md` 2026-10-06 (night). |
| Upstream merge identity gate (C130, 2026-10-06; fork `664c2ead` → `sync/upstream-v0.7.6` `b17b12a9`, upstream v0.7.6) | 23 seeded requests (chat, thinking, code, tool turns, tool-result follow-ups, multi-turn with prior assistant reasoning, vision) × old source / new source / new source after reload: **0 differing fields**; 196K retrieval prompt on the new source 5/5 with no compaction (prefill 469 s). CPU prompt identity 158/158 captured requests. Upstream's chat compaction is OPT-IN (`MLX_VLM_CHAT_COMPACTION`, default off). Fork suite 5828 passed. |
| Joint MTP verification scan (M58, **ADOPTED 2026-10-06, PROVISIONAL**, C126; vision gate in the adopted state: see campaign-results) | `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, `mtp_verify_scan: joint_v1` vs `per_query`, same branch code, two order-balanced sessions in matched state: gate 1 bitwise identity PASSED (0 mismatches over ≈ 170K shadow-compared blocks; 20/20 cross-load replay identical); sustained decode **+14.8 %** at 128K (CI95 [+13.3, +16.1]), **+19.7 %** at 240K, +8.1 % at 64K, 8K within +1 %; prefill, MLX peak (37.97 GB) and MTP acceptance unchanged. Serving optimization — no B/C ladder implication. Detail: `docs/campaign-results.md` 2026-10-06. |
| Fused attention + lazy prompt embeddings (M57, **ADOPTED 2026-10-05, PROVISIONAL**, C115; vision gate 20/20 in the adopted state) | `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, `attention_policy: fused_v1`, two order-balanced sessions against `auto` in matched machine state: prefill −14.6 % at 128K and −24.9 % at 256K; MLX peak −3.21 GB and −6.49 GB; with `lazy_prompt_embeddings` the peak is flat at **37.97GB** to 256K (47.14GB today). Decode, retrieval and MTP acceptance unchanged; humanevalplus/mbppplus strict delta +2 pp / 0 (n=100 per session, within tolerance, not proven equivalent); long-context retrieval and chain-4 reasoning 12/12 in every session. Serving optimization — no B/C ladder implication. Detail: `docs/campaign-results.md` 2026-10-05. |
| Observed timing cost | Native16 task latency +1.2–2.5% per axis; one long-context pair shows +5.95% prefill time and −3.75% decode rate. Repeatability and cause are unmeasured. |
| Shipped first-pick vision smoke | **C88: 20 PASS, 0 FAIL, 0 null** using the existing image → description → ground truth → model verdict recipe. All40 turns converge; registry settings unchanged. |
| Shipped first-pick depth | **C89: retrieval 25/25 (125/125 codes) through128K; chain-4 tracking 39/39 through156K.** All64 converge; separate bounded axes. [Report](docs/native16-depth-qualification-2026-09-14.md). |
| Web search,2026-09-15 | DDGS9.16.0:25/25 at10s spacing,1/8 burst; at5s spacing3/25,0/8 burst. SearXNG alternate DuckDuckGo:25/25,8/8 burst. One-network provider diagnosis, no inference or B/C change. [Report](docs/websearch-ddgs-qualification-2026-09-15.md). |
| Automated checks | MLX-VLM 5372 passed; MLX-Serve 106; stack provenance/comparison 119; generated client config check passes. |

**Retain native16 for the first pick; the second retains TQ4.** Native16 also beat uniform8 on measured capacity/long-context speed in C82. The shipped native16 configuration now passes the full existing vision smoke; retrieval passes all25 prompts through128K and chain-4 tracking all39 through156K. Phase2 qualification is complete at the approved C84/C88/C89 scope; these bounded checks do not establish general native16 equivalence. C84 compares the repaired stack with its initial merged state; the original pre-merge quality comparison remains open. Five items per axis do not establish a 5pp equivalence bound. [Full report, paired intervals and source provenance](docs/stack-certification-2026-09-14.md).

## Documentation

[Published-model audit complete](docs/huggingface-audit-2026-09-14.md): all 13 repositories checked, local cache repaired, cards and evidence refreshed.

- [Current handoff](docs/handoff.md) and [work queue](docs/PLAN.md).
- [Evaluation evidence](docs/model-recommendation-evidence.md), [dated campaign results](docs/campaign-results.md), and [transferable findings](docs/transfer-findings.md).
- [Benchmark guide](benchmark/README.md), [measurement rules](docs/metrics.md), and [model qualification](docs/qualify-a-model.md).
- [Documentation index](docs/README.md) and [contributor/agent rules](AGENTS.md).
