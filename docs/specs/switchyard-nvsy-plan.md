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

## 8. 2026-09-23 review: escalation-router mechanics, and a DEFERRED alternative composition

**Escalation-router mechanics as documented upstream** (`docs/routing_algorithms/escalation_router_routing.md`,
`benchmark/routing-profiles/tb21-escalation-opus-glm-deepseek.toml`): every session starts on the
weak tier; after each completed assistant turn the judge sees anchors + the last `recent_turn_window`
(28) messages truncated to `window_message_chars` (500) including the weak reply, and returns an
escalate/continue verdict; `confirmations` (2) consecutive escalate verdicts latch the session on the
strong tier — the buffered weak reply is discarded, the strong tier regenerates that turn from the
FULL context and serves every later turn. **Latching is one-way for the session.** The judge is a
configurable target (NVIDIA's benchmarked run used a cheap judge with thinking off, not the strong
model). Integration facts: the `escalation` block is accepted only at tag `v0.2.0-rc.1`; latching
needs `x-switchyard-session-id` per conversation (an unchanging header makes every session one session,
so the first latch is permanent until restart); an unlatched turn waits weak + judge. Published
figures: ~6 pt below frontier at 7% route share with the co-released weak model; 13.3% cheaper than
Opus-alone with a stronger weak tier on Terminal-Bench 2.1 (most hard sessions latched and paid twice).

**Assessment for software-development work:** escalation is a struggle detector (loops, repeated
errors, drift) with a frontier bailout, not a quality verifier — a clean-looking wrong trajectory
never escalates, so non-latched sessions land at weak-tier quality including its silent errors.
Its unique value is zero-harness-change rescue of runaway sessions. If S1 is ever activated, run
it as the loop bailout inside a local session (cheap judge, Sonnet-class strong tier) and measure
latch share and judge false-accept rate first; never as the quality gate.

**DEFERRED alternative (operator, 2026-09-23): frontier driver + local executor.** Claude Code on
the frontier model (`claude-opus-5`) plans, <!-- allow-shorthand --> delegates bounded implementation tasks through a wrapper around `opencode run` on the
B pick, and reviews the returned artifact (diff, test output, short summary; transcript stays on
disk under `$STACK_WORKDIR`). Judged the better composition for sw-dev on both quality (the
design/ambiguity work never reaches the weak model; frontier review catches silent errors) and cost
(frontier tokens on the compact brief + review, local tokens on the verbose loop; billed to the
subscription, not the API). It also moves the long-lived context off the box: each delegation is
one short session, so no second full-cap KV floor is ever needed (see below). Sketch when
activated: A1 wrapper tool (real subprocess timeout, serialized delegations, fixed return
contract) → A2 terse skill (write/edit tasks go through A1; retry once with a tighter brief, then
the frontier model does it) → A3 five-task pass/fail gate → A4 small matched local-alone / composed /
frontier-alone read. Not queued; revisit after the qwen-thread items below land.

**Same-model subagent roles (explore at reduced effort, build at medium) were REJECTED 2026-09-23 on
memory:** at the shipped native16 floor every subagent conversation is a new session and a new
~16 GB full-cap KV floor; cap 2 is the C85 regime, cap 1 re-prefills the main context on every
return, and a lower-cap second registry entry is a second weight load. Sequential context-saving
subagents only make sense once the long-lived context lives off the box (the deferred
composition above).
