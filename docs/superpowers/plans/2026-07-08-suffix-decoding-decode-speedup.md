# Suffix (Prompt-Lookahead) Decoding — Decode Speedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine whether drafter-free suffix decoding gives distill a net decode speedup while preserving coding quality, and ship it if so.

**Architecture:** Suffix decoding is already implemented in the mlx-vlm fork (`--draft-kind suffix`) and exposed through the mlx-serve registry (`draft_kind:` field). This plan is a measure-and-gate campaign: enable it via a variant registry entry, audit the verify path for sampler-correctness (fix if needed), then gate quality (LCB pass@1 + convergence, OFAT) and measure speed (tok/s + acceptance), on M5.

**Tech Stack:** mlx-vlm (`generate/ar.py`), mlx-serve router (`main_models.yaml`), `benchmark/bench/run.py` (generate/grade), `.venv-lcbgrade` (M5 LCB grader), evalplus docker (not used here). All runs on **M5** (deploy target; distill cached; single-box for speed apples-to-apples).

## Global Constraints

- **Subject: distill (`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`) primary; Ornith spot-check only.** Ornith is MoE → block-verify activates the union of experts → expected net-negative; measure, don't pre-discard.
- **Config: the shipped daily-driver one** — temp 0.3 (distill) / 0.4 (Ornith), top_p 0.95, top_k 20, min_p 0.0, **no penalties** (so suffix engages, no fallback). Thinking ON, budget 81920. THINKING IS NEVER DISABLED.
- **Quality gate = A (quality preserved):** aggregate LCB pass@1 + convergence within noise of suffix-off, same items, OFAT. Ship only if quality-neutral AND net-faster.
- **Convergence rule:** `converged = finish_reason=="stop" AND completion_tokens < thinking_budget`.
- **Apples-to-apples:** all speed/tok-s numbers same-box (M5), same session, baseline re-measured alongside.
- **Registry variants are UNCOMMITTED** (mark `do NOT commit`); never commit local hf_paths or variant entries.
- **M5 access:** non-interactive ssh has a bare PATH — prepend `export PATH=/opt/homebrew/bin:$HOME/.local/bin:$PATH`. Repo: `$(find ~ -maxdepth 6 -name main_models.yaml -path '*mlx_local_stack*')`'s dir. Long runs: `nohup … </dev/null &` + local poller.

---

### Task 1: Enable suffix via a variant registry entry + smoke

**Files:**
- Modify (uncommitted, M5): `main_models.yaml` — add `Qwen3.6-27B-Opus-Distill-OptiQ-4bit-suffix`.

**Interfaces:**
- Produces: a served model `Qwen3.6-27B-Opus-Distill-OptiQ-4bit-suffix` (draft_kind=suffix), used by all later tasks as the "suffix-ON" arm; `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (existing) is the "suffix-OFF" baseline arm.

- [ ] **Step 1: Append the suffix variant entry** to `main_models.yaml` (after the existing distill entry). Same `hf_path`/KV/params; only `draft_kind` added:

```yaml
  # [PHASE2 #4 VARIANT — uncommitted, do NOT commit] suffix (drafter-free n-gram) decoding
  - name: Qwen3.6-27B-Opus-Distill-OptiQ-4bit-suffix
    type: vision
    on_demand: true
    hf_path: caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit
    max_kv_cache_size: 262144
    kv_quant_scheme: turboquant
    kv_bits: 4
    prefill_step_size: 512
    quantized_kv_start: 0
    enable_thinking: true
    draft_kind: suffix
    suffix_min_match: 2
```

- [ ] **Step 2: Add the name→QWEN params mapping** in `benchmark/bench/model_params.py` PARAMS dict (so the harness resolves sampling params; the `-suffix` name contains "qwen" so the fallback also works, but be explicit):

```python
    "Qwen3.6-27B-Opus-Distill-OptiQ-4bit-suffix": QWEN,
```

- [ ] **Step 3: Restart the M5 router** to pick up the entry (APC off for a clean speed baseline):

Run (on M5): `pkill -f "mlx-serve start"; sleep 3; pkill -f mlx_vlm.server; sleep 2; MLX_SERVE_CONFIG=main_models.yaml nohup uv run mlx-serve start >logs/main_model.log 2>&1 </dev/null &`
Expected: `curl -s localhost:8000/v1/models` lists `…-4bit-suffix`.

- [ ] **Step 4: Smoke — confirm suffix engages** with a high-reuse prompt (echo a code block):

Run: send a chat request to `…-suffix` whose user message asks to "repeat the following function verbatim, then add a docstring" with a ~40-line function; `grep -iE "draft-kind suffix|suffix" logs/main_model.log` shows the worker spawned with `--draft-kind suffix`.
Expected: worker spawn line contains `--draft-kind suffix --suffix-min-match 2`; response completes.

- [ ] **Step 5: Commit** — N/A (registry variant is uncommitted). Record in the run log that the variant is live.

---

### Task 2: Correctness audit — does the verify path apply the sampler?

**Files:**
- Read: `../mlx-vlm/mlx_vlm/generate/ar.py` (suffix draft+verify+accept; entry ~595–611, n-gram seed ~345–356, verify/accept loop).
- Create (throwaway): `/tmp/suffix_dist_check.py` (distribution spot-check).

**Interfaces:**
- Produces: a verdict `SAMPLER_APPLIED = Y|N` used by Task 3 (fix only if N).

- [ ] **Step 1: Read the verify/accept code** and answer: at each drafted position, are `temperature`/`top_p`/`top_k`/`min_p` applied to the target logits before the accept/reject decision, or are raw logits used? Locate the accept comparison (drafted-id vs target sample) and the miss-path sampling.

- [ ] **Step 2: Distribution spot-check** — with a fixed seed and temp 0.3, generate the same short continuation (a) suffix-OFF and (b) suffix-ON on distill over an identical high-reuse prompt; capture per-position top-1/top-5 target probabilities on the accepted span. If suffix-ON's accepted tokens are consistent with the temp-0.3 sampler (not hotter/raw), `SAMPLER_APPLIED=Y`.

Run: `PYTHONPATH=../mlx-vlm python /tmp/suffix_dist_check.py`
Expected: prints `SAMPLER_APPLIED=Y` or `=N` with the evidence (e.g., accepted-token ranks under the sampler).

- [ ] **Step 3: Record the verdict** in the run log. If `Y` → skip Task 3. If `N` → Task 3 is required before the quality gate.

---

### Task 3 (ONLY IF Task 2 verdict = N): apply the sampler inside block-verify

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/generate/ar.py` (block-verify accept path — apply temp/top_p/top_k/min_p per drafted position).
- Test: `../mlx-vlm/mlx_vlm/tests/test_speculative.py` (add a sampler-application test).

**Interfaces:**
- Consumes: the verify loop identified in Task 2.
- Produces: verify path that samples from the same (temp/top_p/top_k/min_p) distribution as plain decode.

- [ ] **Step 1: Write the failing test** — a suffix block-verify over a crafted logits tensor at temp 0.3 must reject a drafted token that the temp-0.3 sampler would not produce (and accept one it would):

```python
def test_suffix_verify_applies_sampler():
    # temp 0.3 concentrates mass on the top token; a drafted low-prob token must be rejected.
    logits = mx.array([[[2.0, 1.9, 0.0]]])  # position with two near-tied tops
    accepted = suffix_block_verify(logits, drafted_ids=[2], temperature=0.3, top_k=20, top_p=0.95, min_p=0.0)
    assert accepted == []  # token 2 (low prob) rejected under temp 0.3
```

- [ ] **Step 2: Run it, verify it fails** — `PYTHONPATH=../mlx-vlm pytest ../mlx-vlm/mlx_vlm/tests/test_speculative.py::test_suffix_verify_applies_sampler -v` → FAIL (raw logits accept token 2).

- [ ] **Step 3: Implement** — apply the same sampler transform used by plain decode to the target logits at each drafted position before the accept decision (reuse the existing sampler builder; stateless transforms only — temp/top_p/top_k/min_p).

- [ ] **Step 4: Run it, verify it passes** — same pytest → PASS. Also run the existing suffix tests to confirm no regression: `PYTHONPATH=../mlx-vlm pytest ../mlx-vlm/mlx_vlm/tests/test_speculative.py -q` → all PASS.

- [ ] **Step 5: Commit the fork fix** (parent fork `../mlx-vlm`, then bump the stack submodule per AGENTS.md):

```bash
cd ../mlx-vlm && git add mlx_vlm/generate/ar.py mlx_vlm/tests/test_speculative.py && git commit -m "fix(suffix): apply sampler (temp/top_p/top_k/min_p) in block-verify for distribution-preserving decode"
```
Then scp the changed `ar.py` into M5's submodule for the run (temporary), or bump + `git submodule update --force` on M5.

---

### Task 4: Quality gate A — LCB pass@1 + convergence, suffix ON vs OFF

**Files:**
- Read/append: `benchmark/results/*/livecodebench.jsonl` (per-item, resumable).

**Interfaces:**
- Consumes: `…-suffix` (Task 1) + baseline `…` model names.
- Produces: `PASS|FAIL` quality verdict (aggregate pass@1 + convergence within noise).

- [ ] **Step 1: Generate LCB (N=15) suffix-OFF baseline** (distill @t0.3), on M5:

Run: `uv run python benchmark/run.py generate --models Qwen3.6-27B-Opus-Distill-OptiQ-4bit --benches livecodebench --limit livecodebench=15 --temp 0.3 --thinking-budget 81920 --order model`
Expected: 15 items written to `benchmark/results/Qwen3.6-27B-Opus-Distill-OptiQ-4bit/livecodebench.jsonl`.

- [ ] **Step 2: Generate LCB (N=15) suffix-ON** (same 15 items):

Run: `uv run python benchmark/run.py generate --models Qwen3.6-27B-Opus-Distill-OptiQ-4bit-suffix --benches livecodebench --limit livecodebench=15 --temp 0.3 --thinking-budget 81920 --order model`
Expected: 15 items for the `-suffix` model.

- [ ] **Step 3: Grade both** with the LCB grader (M5):

Run: `PYTHONPATH=$HOME/.cache/livecodebench/LiveCodeBench .venv-lcbgrade/bin/python benchmark/run.py grade --models Qwen3.6-27B-Opus-Distill-OptiQ-4bit,Qwen3.6-27B-Opus-Distill-OptiQ-4bit-suffix --benches livecodebench`
Expected: two rows with `acc` + `conv%`.

- [ ] **Step 4: Decide** — record pass@1 + conv% for both. Reference: distill LCB kv4 = 80% (E100/M86/H60), 100% conv. **PASS if** suffix-ON pass@1 is within noise of suffix-OFF (no dramatic drop) AND convergence is not worse. **FAIL if** a clear pass@1 drop or convergence collapse → the bf16 verify-numerics issue bites qwen-arch → keep suffix off (log it, stop here, go to Task 8-negative).

- [ ] **Step 5: Commit** — N/A (results jsonl). Record the two-row scoreboard in the run log.

---

### Task 5: Speed measurement — tok/s + acceptance, two workloads

**Files:**
- Create: `benchmark/suffix_edit_probe.py` (edit-heavy speed probe).

**Interfaces:**
- Consumes: `…-suffix` + baseline model names.
- Produces: `{off_tps, on_tps, acceptance_rate, mean_block_len}` per workload.

- [ ] **Step 1: Write the edit-heavy probe** `benchmark/suffix_edit_probe.py`:

```python
#!/usr/bin/env python3
"""Edit-heavy suffix-decode speed probe: give a file, ask for the file back with a
small edit (high verbatim reuse). Times ON vs OFF and reports tok/s."""
import sys, time, json, urllib.request
BASE = "http://localhost:8000/v1/chat/completions"
FILE = ("def add(a, b):\n    return a + b\n\n" * 40)  # ~ a few hundred tokens of reusable code
def run(model):
    body = json.dumps({"model": model,
        "messages": [{"role": "user", "content":
            "Return this file verbatim, but rename `add` to `sum2` everywhere:\n\n" + FILE}],
        "max_tokens": 800, "temperature": 0.3, "top_p": 0.95, "top_k": 20, "min_p": 0.0,
        "thinking_budget": 1}).encode()
    req = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=1800) as r: d = json.load(r)
    dt = time.perf_counter() - t0
    ct = (d.get("usage") or {}).get("completion_tokens", 0)
    return dt, ct, ct / dt if dt else 0
for m in (sys.argv[1], sys.argv[2]):   # off_model on_model
    dt, ct, tps = run(m); print(f"{m}: {ct} tok in {dt:.1f}s = {tps:.1f} tok/s", flush=True)
```

- [ ] **Step 2: Run the edit-heavy probe** OFF vs ON (M5):

Run: `python benchmark/suffix_edit_probe.py Qwen3.6-27B-Opus-Distill-OptiQ-4bit Qwen3.6-27B-Opus-Distill-OptiQ-4bit-suffix`
Expected: two `tok/s` lines; ON should be meaningfully higher on this high-reuse task.

- [ ] **Step 3: Capture acceptance stats** — the suffix decoder logs acceptance; `grep -iE "accept|block|suffix" logs/main_model.log` (or the worker log) after the ON run. Record acceptance_rate + mean accepted block length.

- [ ] **Step 4: Generation-heavy point** — reuse the Task 4 LCB ON run's per-item timing (novel code, lower reuse) as the conservative speed point; record its effective tok/s + acceptance from the worker log.

- [ ] **Step 5: Commit** the probe script (it's a reusable harness, committable — no PII):

```bash
git add benchmark/suffix_edit_probe.py && git commit -m "feat(bench): edit-heavy suffix-decode speed probe (#4)"
```

---

### Task 6: Light param sweep (only if Task 4 PASS and Task 5 shows a win)

**Files:**
- Modify (uncommitted, M5): `main_models.yaml` — vary `suffix_min_match` / `draft_block_size` on the variant.

**Interfaces:**
- Produces: the best `{suffix_min_match, draft_block_size}` for net tok/s.

- [ ] **Step 1: Sweep `suffix_min_match` ∈ {2,3}** — edit `main_models.yaml`, restart router, re-run the Task-5 edit probe for each; record tok/s + acceptance.
- [ ] **Step 2: Sweep `draft_block_size`** (worker default vs e.g. 8, 16) similarly.
- [ ] **Step 3: Pick the setting** with the highest net tok/s that does not reduce acceptance quality; record it. (No commit — uncommitted variant.)

---

### Task 7: Ornith spot-check (verify before discarding)

**Files:**
- Modify (uncommitted, M5): `main_models.yaml` — add `Ornith-1.0-35B-mlx-uniform-4bit-suffix` (draft_kind: suffix; fp16 KV as shipped) + `model_params.py` mapping `"Ornith-…-suffix": QWEN`.

**Interfaces:**
- Produces: a net-effect verdict for Ornith (expected net-neutral/negative due to MoE verify cost).

- [ ] **Step 1: Add the Ornith suffix variant** entry + params mapping (Ornith name lacks "qwen" → the mapping is REQUIRED). Restart router.
- [ ] **Step 2: Run the edit-heavy probe** OFF vs ON on Ornith: `python benchmark/suffix_edit_probe.py Ornith-1.0-35B-mlx-uniform-4bit Ornith-1.0-35B-mlx-uniform-4bit-suffix`. Record tok/s + acceptance (from worker log).
- [ ] **Step 3: Verdict** — if ON ≥ OFF net tok/s with acceptance > 0, Ornith benefits (unexpected — investigate/keep). If ON ≤ OFF (expected, MoE verify tax), record the negative result so MoE-suffix is not re-chased. No quality gate needed unless it's a net win.

---

### Task 8: Decision & ship (or documented keep-off)

**Files:**
- Modify: `docs/campaign-results.md` (Phase-2 #4 row), `docs/campaign-queue.md` (#4 status).
- Modify (if SHIP, uncommitted then propose to commit): distill entry in `main_models.yaml` + `opencode_config/opencode.json` (add `draft_kind: suffix` to the real distill config).

- [ ] **Step 1: Synthesize** — record in `campaign-results.md`: quality (Task 4 pass@1+conv ON vs OFF), speed (Task 5 tok/s + acceptance, both workloads), best params (Task 6), Ornith verdict (Task 7), correctness verdict (Task 2/3).
- [ ] **Step 2: Decide** — SHIP for distill IFF Task 4 = PASS AND Task 5 shows net speedup. Otherwise keep-off with the negative result logged (so it isn't re-chased).
- [ ] **Step 3 (if SHIP): propose the production change** — add `draft_kind: suffix` (+ tuned params) to distill's `main_models.yaml` entry and its `opencode.json` block; present the diff for the user's commit approval (per propose-before-committing). Note the workload caveat (win scales with context reuse).
- [ ] **Step 4: Update `campaign-queue.md`** #4 status to DONE (SHIP or keep-off).

---

## Self-Review

**Spec coverage:** spec §Enable → Task 1; §1 audit → Task 2 (+ Task 3 fix); §2 quality gate → Task 4; §3 speed → Task 5; §4 sweep → Task 6; Ornith spot-check → Task 7; §5 decision/ship → Task 8. All covered.

**Placeholder scan:** no TBD/TODO; the conditional Task 3 is gated on Task 2's verdict (explicit), with concrete test+fix; `<N>`/example values in the sweep are the actual knobs. OK.

**Type consistency:** model names used consistently — `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (OFF), `…-4bit-suffix` (ON), `Ornith-1.0-35B-mlx-uniform-4bit[-suffix]`. `suffix_block_verify` (Task 3 test) is illustrative of the accept fn identified in Task 2 — rename to the real symbol found there.

**Note:** Task 3 is conditional (executed only if Task 2 = N). If Task 4 FAILs, stop at Task 8-negative (skip 5–7 unless a speed-only curiosity run is wanted).
