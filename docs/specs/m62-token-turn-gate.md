# M62 — token/turn progress gate for the v2 probe (C146) + probe hygiene (C138)

Status: REVISION 2, 2026-10-09 — cold re-review (`$STACK_WORKDIR/m62/codex_design_review2.md`) verdict "redesign" again (P15 background jobs break hold quiescence; P16 forced thinking closure unobservable; P17–P27). Lead recommends dropping the proxy for a passive gate with a tool-bounding plugin (operator decision P219); revision 3 follows that ruling. Operator-approved direction (P215 revised, P216, P214: "ideally we should have a gate on
tokens/turns, not on time"). Revision 1 → cold design review (Codex gpt-6-astra, `$STACK_WORKDIR/m62/codex_design_review.md`,
verdict "redesign": a passive event-log tailer cannot stop at request boundaries, account usage completely or classify
silence). Revision 2 answers each finding (R-ids map to review P1–P14). Decisions: `docs/open-questions.md` C146, C138.

## 1. Problem

The v2 probe stops items with the Phase H progress gate (`benchmark/bench/progress_gate.py`): every `tick_s` it snapshots
and grades the workdir; progress = failing count fell, or the solution changed without failures rising; 2 flat ticks →
`stalled`; 3 identical transcript-tail hashes → `looping`; 3600 s → `hard_ceiling`. C136 sets `tick_s` from a token
allowance and a per-model decode-rate table. Measured defects:

1. **Time, not tokens.** "48K" became 1984 s / 1890 s; decode slows inside one stream (rolling 25 → 18.7 tok/s by 40K).
   M61 thinking stalls closed at ≈ 40.5K / ≈ 41K (`Qwen3.8-27B-mlx-uniform-4bit` go/alphametics s1, s2) and ≈ 43.5K
   (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` python/book-store s2): unequal across models, below 48K.
2. **Below the deployed thinking budget** (81,920 per request for both picks): the gate cut single thinks at about half.
3. **Loop detector inert on v2**: the hashed log tail carries timestamps/ids; 0 of 454 v2 rows `looping`; a
   358-repeat loop (go/kindergarten-garden, M61 s2; 8th identical call at request 15) ran 31 min to `stalled`.
4. **Progress is gameable** (R8): grades are binary 0/1, an ungradeable tick or any changed hash (comment edits,
   alternating drafts) counts as progress, and the snapshot path skips the tamper check.
5. **No strict-convergence signal per request** (R7): the probe does not record server length/thinking-budget closures,
   so a forced-closure request that then passes would score strict.
6. **C138:** no memory containment (117 GB incident); opencode's shell spawns detached shells and does not kill
   children; non-atomic manifest/row writes; one-instance-per-leg not enforced.

## 2. Central change — a probe-owned request proxy (answers R1, R2, R3, R4, R7)

A passive tailer sees a request only after it finished, often after the next one started (690 finish→start gaps < 1 s).
Instead the probe runs a **local pass-through HTTP proxy** per item; the generated v2 carrier's provider `baseURL` points
at it; it forwards to the M50-verified router.

- **Transparency.** Request bodies and headers are forwarded byte-identical; responses are streamed through unchanged.
  Verified by a wire-capture identity test (same seed, with and without proxy: identical request bytes and identical
  output). M50: the probe verifies the router before starting the proxy, the proxy's upstream is fixed to that router,
  the proxy's own address is recorded; AGENTS.md M50 text needs an operator-approved amendment (new C-id) naming the
  proxy as the probe's verified provider.
- **Admission control (R2).** When opencode sends request j+1, the proxy HOLDS it and asks the gate. opencode is then
  blocked on the model, and request j's tool calls have completed, so the workspace is quiescent (subagents denied, R4).
  The probe snapshots + grades, the gate decides; admit → forward; stop → the probe terminates the item (no request is
  ever cut). Hold time is wall time only; it changes no counter.
- **Authoritative usage (R1).** Per request the proxy records: completion tokens from the server's final usage (thinking
  included — verified on a real wire capture), finish_reason, streamed-chunk count, first-token latency, duration.
  Missing usage on a forwarded request → abort (never zero). At exit the probe reconciles proxy usage with opencode's
  export by message id; a mismatch beyond a stated tolerance aborts.
- **Per-request convergence (R7).** A request with finish_reason `length`, or with thinking that reached the resolved
  per-request budget (server closure), sets the row's `nonconv_kind: budget_hit` (AGENTS: convergence requires
  `stop`-type finish AND tokens below the resolved budget). Strict scoring therefore fails it even if tests pass.
  Known positive: a mock server that force-closes thinking, then a passing edit → row strict-fails.
- **Silence classification (R3).** The proxy knows whether a request is in flight:
  - in flight, tokens streaming → generating; never killed for time (bounded by server max_tokens);
  - in flight, no first token / no chunk for **900 s** → server wedge → `TransportAbort` (nonzero, unscored, diagnostics);
  - no request in flight for **1800 s** (opencode is executing tools) and a model-spawned descendant is alive →
    model-caused nontermination → `nonconv_kind: exec_timeout` (a scored miss, tax-reported); no descendant alive →
    client wedge → `TransportAbort`. Process-tree and proxy state are written to the row/diagnostics in every case.
- **Subagents (R4).** Denied in the tg1 carrier (task tool permission off; 0 of 454 v2 rows used them). The proxy counts
  every request regardless of session, so any leak is still charged and flagged.

## 3. Gate policy (`TokenTurnGate`, new class; frozen 1.18 probe and `run_dsh_probe.py` keep `ProgressGate`)

Campaign constants (R6), identical for every arm, frozen in the scaffold policy and hashed (not derived per model);
a model whose resolved per-request thinking budget differs from the campaign `B` is refused under tg1 unless the operator
records an override:

| Constant | Value | Basis |
|---|---|---|
| `B` (reference thinking budget) | 81,920 | both picks' resolved per-request budget |
| `T` no-progress tokens | `≥ B` → stop at next admission | one full-budget think without progress is allowed; a forced closure strict-fails anyway (§2), so more cannot earn credit in one request |
| `N` no-progress requests | `≥ 40` → stop | passing max 26 requests total (row metrics) |
| `K` identical consecutive tool calls | `≥ 8` → `looping` | passing max run 2; kindergarten-garden stops at request 15 (onset + 7) |
| item token ceiling | `≥ 4B = 327,680` total → `hard_ceiling` | passing max 39,142 |
| item request ceiling | `≥ 150` → `hard_ceiling` | |

Decisions are made only at admission, with `≥` comparisons, precedence `looping` > `hard_ceiling` > `stalled`. Realized
allowances are soft with bounded overshoot (stated, not hidden): no-progress tokens < T + max_tokens (102,400); total
< 4B + max_tokens. Equal output-token allowances are not equal compute (prefill differs by model); reported as such.

**Progress (R8)** — a strict improvement, gradeable, untampered:
- the grader returns a failing-TEST COUNT (Python: pytest summary; Go: `go test -json` failed tests; a build/collection
  error = all tests failing); other languages are binary and recorded as such;
- progress = the count reaches a new minimum below the stub's baseline count (the first draft that fixes any test
  counts; refactors at equal count, comment edits, alternating drafts and repeated hashes do not);
- an ungradeable snapshot or a modified protected test file is never progress (tamper also flagged on the row);
- grading runs only when the solution hash is new.

## 4. Probe hygiene (C138; answers R9–R12)

- **H1 Process tracking (R9).** A 1 s tracker records every descendant of opencode as (pid, create_time) while ancestry
  exists — including opencode's detached shells; stop = SIGKILL every tracked entry still matching its create_time, plus
  any process with cwd under the scratch; verify zero survivors (re-check twice) before deleting scratch, else abort.
  Grader containers get an item-unique `--name` and are removed by name; zero remaining verified. Inaccessible
  processes → abort with diagnostics.
- **H2 Memory watchdog (R10) — best effort, not a cap.** Host: kill any tracked model-spawned process > 8 GB RSS, and the
  largest when tracked aggregate > 16 GB; recorded as `mem_kills` (the model sees its command fail). Containers: Docker
  `--memory` limit (a real cap in the VM); OOM → that grade counts as failing tests (`grader_oom` recorded). opencode
  itself > 16 GB → `TransportAbort` (`client_resource`, unscored). Tests with lowered thresholds: single burst,
  multi-process aggregate, monitor-thread death (→ abort), grader OOM.
- **H3 Writes (R11).** Rows and manifests are small: whole-file replacement (write tmp, fsync, rename, fsync dir), every
  write/fsync result checked; loader still refuses torn files. Signals deferred (`pthread_sigmask`) during resource
  acquisition and cleanup; fault tests interrupt before/after write, fsync, rename and spawn.
- **H4 Instance identity (R12).** Identity = worker pid + process create_time + model path + registry sha; checked before
  and after every item and at exit; missing → refuse; drift → abort, the item in flight is invalid. Appending to a rows
  file with a different identity is refused. The probe gains `--expect-items` (exact id set): exit nonzero on missing or
  duplicate ids. Workdir chain runners: archive an incomplete leg and rerun from item one on a fresh instance; leg
  timeout derived from items × pilot mean + per-item worst case (§6), no fixed 6 h.

## 5. Provenance and scaffold (R14)

New scaffold **`opencode-v2-web-tg1`**. The policy hash covers gate constants, proxy version, silence limits, memory
limits, grader counting mode and subagent policy; `compare.py` refuses cross-hash comparisons. `--first-write-tokens`
and `--tick-s` are refused under tg1; `decode_rates.json` is not read by the gate (RATE CHECK remains a drift monitor).
The `opencode-v2-web` code path stays byte-for-byte as M61 ran it (no hygiene backport, so it can reproduce M61); there
is no mixed mode.

## 6. Acceptance criteria (pre-registered; answers R5, R13)

- **V1 Unit/integration, failing first (mocked server and opencode):** gate thresholds at exactly T/N/K/ceilings with
  `≥`, precedence; admission hold with immediate next request; slow grading; new-minimum progress, equal-count edits,
  alternating drafts, ungradeable and tampered snapshots; missing usage → abort; usage reconciliation; split JSON/UTF-8
  and duplicate SSE chunks; forced thinking closure → strict fail; silence three ways (server wedge, model tool hang
  with live descendant, client wedge); subagent request charged + flagged; context overflow and provider retry
  behaviour unchanged; proxy byte identity; H1–H4 fault tests; existing `ProgressGate` tests unchanged. Full suite green.
- **V2 Offline replay (false-positive screen only):** an identity-checked, hashed replay manifest of v2 rows whose event
  log `sessionID` matches the row (381 passing; the 54 misattributed rows listed and excluded); charge every request as
  no-progress (conservative): 0 passing rows reach T, N or K; kindergarten-garden M61 s2 → `looping` at request 15. The
  replay cannot reconstruct grades, in-flight streams or scheduling, and says so.
- **V3 Live smoke**, quiet box, lean router, one pick (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`): five
  seeded-random Python items AND two Go items (container grading): all complete with tg1 provenance; proxy usage
  reconciles with the export; zero surviving processes/containers; injected known positives — a model-equivalent
  scratch process allocating > 8 GB (killed, recorded) and a hanging background shell (→ `exec_timeout`).
- **V4 P214** (descriptive): the three M61 thinking-stall items with their M61 seeds, each on a fresh loaded instance:
  `Qwen3.8-27B-mlx-uniform-4bit` go/alphametics (seed bases 1001, 2002), `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
  python/book-store (2002). Report per item: tokens to first write, whether it passed, any budget closure. M61 rows stay
  the record.
- **V5** Cold implementation review (Codex) against V1–V4 before any chain uses tg1.

## 7. Cost (conditional bounds, not promises)

At ≈ 19.5 tok/s late-stream decode, a no-progress stop costs < (T + max_tokens) / 19.5 ≈ 2.6 h of generation plus tools
and grading; a churning item can reach ≈ 6 h before the total ceiling; tool time is bounded only by the 1800 s
no-request limit per idle stretch. V4 expectation ≈ 3–5 h, conditional worst case ≈ 9 h. Chain cost: estimated from the
V3/V4 pilot means plus a heavy-tail allowance before any chain is queued.

## 8. Out of scope / consequences

- Not a gate on thinking content (exact-cycle detection misses varying loops; the budget bounds a think; temperature
  ladder is the knob). `bench/cycles.py` runs on stalled rows' completed thinking as a report diagnostic only.
- Pooling: tg1 never pools with M59/M61. When C144's first new candidate arrives, both picks are re-recorded under tg1
  (≈ 20 h + tail) or the candidate runs on the frozen `opencode-v2-web` path — operator decision then.
- Data hygiene found by the review: 54 of 454 v2 rows reference an event log from a different session (M59 48K re-runs
  and the s1 window558 re-run overwrote transcript paths); listed in the replay manifest, recorded in C140.
- Workflow: this spec → cold re-review → operator approval of the full plan and the M50 amendment → Codex implementer
  (failing tests first; no docs/handoff edits or commits) → lead verification → V1–V3 → cold implementation review (V5)
  → V4 on the box.
