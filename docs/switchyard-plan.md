# NVSY — the NVIDIA Switchyard system-track plan

**Status: WRITTEN 2026-08-18, PARKED behind the model queue (operator: "I'll get to it
later").** This is the separate plan for the weak/strong router experiment raised in O32.
`docs/PLAN.md` stays the campaign's ordered queue; this file owns the NVSY track's design
so it can start cold. Ledger/queue integration happens when the operator activates it.

## 1. Objective

Compose the local pick (weak/cheap/fast) with a frontier cloud model (strong/expensive)
behind [NVIDIA-NeMo/Switchyard](https://github.com/NVIDIA-NeMo/Switchyard) — a Rust proxy
preserving native OpenAI *and* Anthropic API formats — and measure whether the SYSTEM is a
meaningfully better daily coder at small $ cost. Vendor's self-published headline: ~5%
quality degradation at 50%+ cost savings. Both numbers are theirs, on their workload; we
measure our own. Liveliness caveat to keep in view: an escalated turn pays weak latency +
judge + frontier — *worse* than frontier-alone on exactly the escalated items. The
liveliness win lives entirely in the non-escalated share, so route-share is a liveliness
metric as much as a cost metric.

## 2. Why escalation routing re-weights model selection

The weak tier's job is fast, judgeable, convergent answers; quality sets only the
non-escalated share, because the judge recovers misses at frontier cost. So the decisive
weak-tier axes are the COUNT/RATE ones (convergence, malformed-edit rate, degeneracy,
tool-call validity) — which resolve at n≈30 — not the pass@1 deltas that need n≈100+.
Runaways and malformed retries are what kill liveliness and savings; a 5pp pass@1 gap is
what the judge exists to absorb.

Weak-tier shortlist:

| candidate | case for | open question |
|---|---|---|
| `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` | co-released with Switchyard (judge likely tuned for this family as weak tier); ~2× the winners' speed at 26.0 GB peak; conv 99–100% and acc_strict 0.88/0.81/0.905 at the vendor tune (n=100/100/200) | the 3.75 malformed-edits-per-case aider figure — serving-path-unmatched, unverified; opencode Run B (M4) + first BFCL run settle it |
| the B pick (`Ornith-1.0-35B-mlx-uniform-4bit`) | ladder-certified tune, best standalone capability, 0 malformed edits measured | slower; is its extra capability worth anything once a judge backstops quality? |

The `Qwen3.8-27B` family is excluded from the weak-tier role <!-- allow-shorthand --> on
liveliness (11–24 tok/s decode, ~33 min prefill at 256K) regardless of tune; it remains a
standalone-B candidate only. **So is `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`** (2026-08-18
correction): same qwen3_5 hybrid architecture, measured 23.3 tok/s median suffix-OFF — its
"fast" reputation was a suffix-ON-era impression. The liveliness candidates are
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` and `Ornith-1.0-35B-mlx-uniform-4bit` (76.2
tok/s). A caveat cutting the other way: if M6 proves the native MTP head out (the qwen3_5
checkpoints ship one; ±5pp OFAT gate), the qwen3_5 models' decode could improve — re-check
the shortlist after M6.

## 3. Prerequisite: certified tunes (operator ruling 2026-08-18)

No model enters the pairing until its tune is certified — "I know it's the best I can make
it." Certification, not optimization: at affordable n the harness can certify *no knob
move produces a dramatic gain and the shipped tune has no measured pathology*; it cannot
resolve <12pp quality deltas per knob.

- Winners: DONE (ladders → `Ornith-1.0-35B-mlx-uniform-4bit` t0.4,
  `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` t0.3).
- `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`: the standing ladder recipe triggers on
  non-convergence and there is none (conv 99–100% at vendor temp 1.0), so the vendor tune
  is the certified tune on the measured axes — for free. Two gaps: (a) the tune is
  unexamined on the agentic/edit/tool axes, exactly where the weak-tier role is decided —
  so the tune work lives INSIDE the M3/M4/BFCL block: run at the vendor tune; only if
  edit/tool failure modes reproduce, run a targeted OFAT on the failing axis (temperature
  is the proven knob for format/degeneracy failures) and re-screen at the winning tune;
  (b) its registry `generation_defaults` carries no `top_k`/`min_p` — one-time check
  against the vendor's recommended sampling before certifying, so the certified "vendor
  tune" is actually the vendor's.

## 4. Sequencing (relative to `docs/PLAN.md` §3 — reorder, not queue-jump)

1. Stage-2 `Qwen3.8-27B` screens <!-- allow-shorthand --> — in flight, finish first.
2. **S1 mechanics spike** (cheap, does not need the final weak pick — any resident model).
3. **M3 → M4 → first recorded BFCL run** pulled ahead of M11/M12: dual-purpose — they are
   both the B/C-standing answer and the weak-tier selection + tune-certification input.
4. **Three-arm eval** designed only if S1 is clean, with the weak tier chosen from §2's
   shortlist on the block-3 results.

M11/M12 slide behind; they inform standalone-B, not the pairing.

## 5. S1 spike (entry gate; needs operator go)

Stand Switchyard up in **Escalation Router** mode fronting mlx-serve (:8000) + an
Anthropic frontier arm; point a T1-style n=15 coding smoke at it; record mechanics only.

- Escalation Router for the spike because its escalation rate IS route-share and the
  three-arm instrument answers it directly; recognizing a bad answer is a far easier
  problem than a pre-routing classifier predicting which items the local pick will miss.
  Stage Router (tool-error signals, zero judge overhead) is the follow-up candidate for
  the agentic eval, not the spike.
- Record: route-share, $ per task, added latency per leg, and the JUDGE line — who runs
  the judge, its per-turn cost, and its false-accept rate (a judge that waves through
  wrong-but-plausible weak answers caps the system at local quality). Note the judge may
  be tuned for the co-released family's output style.
- Deliverable: clean/not-clean verdict + the measured mechanics; the three-arm design
  freezes only after it.

**Decisions pending the operator (recommendations standing):** (1) go/no-go; (2) frontier
arm — recommend Sonnet-class (`claude-sonnet-5`); Opus-class is a ceiling arm for the
three-arm eval only if warranted; (3) API budget cap — recommend $10 hard cap for the
spike (worst case ≈15 frontier coding calls), separate approval for the eval (~$15–25,
dominated by the frontier-alone arm); (4) install — recommend a prebuilt pinned release
binary into `$STACK_WORKDIR/switchyard/`, NOT `cargo install` (`~/.cargo` violates the
workdir containment rule; a toolchain needs separate approval).

## 6. Three-arm eval (design sketch; freeze after S1)

Three arms on the same seeded, matched items — **local-alone / router(local+frontier) /
frontier-alone** — n=100 coding to start (guard-clean axes), pilot rule applies.

- Endpoints: quality (+ CI/MDE) with **exclusive-solve sets** (does the composed system
  recover the items the local pick misses?), $/task, route-share, latency per task
  (report the escalated-turn latency distribution separately — see §1 caveat). Rank on
  capability per the standing rule; report cost/throughput beside it.
- Provenance: a router row is a different serving path — `client`/system entry under a
  **(system, config)** extension of the (model, tune) taxonomy, config = routing policy +
  judge + budget. `compare` refuses pooling system rows with model rows. New per-row
  fields: cost-per-task, route-share. Ledger gets a `system` section.
- The vendor 5%/50% figure sits exactly at our ±5pp lossy-lever gate — treat as a claim
  under test, sized with measured discordance (`stats.mde` pilot-first), never a prior.

## 7. Containment

Everything NVSY lives under `$STACK_WORKDIR/switchyard/` (binary, config, logs, spike
artifacts); results rows follow the normal `benchmark/results/` + manifest path with the
system provenance above. No writes outside the workdir without explicit per-item approval
(AGENTS.md Operating rules, 2026-08-18).
