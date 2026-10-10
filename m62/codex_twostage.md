1. **P1 — BLOCKER: judgment-based reruns change what the benchmark measures.**

   “Inspect the capped attempt, then rerun promising items” measures **model + reviewer selection + retry policy**, not the approved single-sample `acc_strict@budget`. Identical nominal limits across models do not fix unequal opportunities selected from their outputs. Abandoned items must remain failures in the denominator; successful reruns cannot replace them in the original record.

   **Recommendation:** reject discretionary reruns for ranking. They are useful as separately labelled diagnostics. Evidence: [AGENTS.md:43]($STACK_REPO/AGENTS.md:43), [AGENTS.md:46]($STACK_REPO/AGENTS.md:46), [AGENTS.md:57]($STACK_REPO/AGENTS.md:57).

2. **P2 — BLOCKER: mechanical rerunning avoids reviewer discretion, but fresh reruns still introduce second chances.**

   | Policy | Preserves the approved full-gate metric? |
   |---|---|
   | Rerun selected capped items | No: adaptive selection and potentially another sample. |
   | Rerun every capped item with a fresh sample | No: a reproducible retry policy, but a different estimand. |
   | Abandon every capped item | No: a lower per-request budget. It could define another benchmark, but contradicts the standing generous-budget rule. |
   | Rerun every capped item with proven identical execution through the cutoff | Potentially preserves the logical sample’s accuracy; duplicates computation and requires stronger evidence than matching seeds. |

   **Quantifying the bias:** for a fixed item, let \(c\) be the probability of reaching the short cap, \(a\) the probability of passing before it, and \(s\) the probability of eventually passing under the full gate conditional on reaching it. Single-pass success is \(p=a+cs\). An independent full rerun on every capped attempt yields \(a+cp\), a difference of:

   \[
   \Delta=c(p-s).
   \]

   Thus fresh reruns can inflate—or sometimes reduce—the full-gate score. In the familiar special case where all failures reach the cap and all successes finish earlier, success becomes \(1-(1-p)^2\): inflation is \(p(1-p)\), reaching **25 percentage points** at \(p=0.5\), or **9 points** at \(p=0.9\). These are mathematical examples, not estimates from this dataset.

   For the three identified M61 cases, replacement can move two outcomes for `Qwen3.8-27B-mlx-uniform-4bit` and one for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`. That is **2.33 and 1.16 percentage points**, respectively, on descriptive 86-row totals. Actual ranking remains per language/session: one outcome is **4.76 points on Go’s 21 items** or **4.55 on Python’s 22**.

   **Recommendation:** retain one scored trajectory per item/session. If retries are wanted as a product evaluation, preregister a separate policy, charge both attempts, and rerun all model arms under it.

3. **P3 — MAJOR: same seed and same day are necessary controls, not sufficient replay proof.**

   The later evidence qualifies the supplied determinism summary. C137 found byte-identical full-prefill runs, but a cached-prefix run diverged despite the same seeded request. The final diagnosis was deterministic behavior **conditional on cache path**, not universal seed determinism. See [open-questions.md:37]($STACK_REPO/docs/open-questions.md:37) and [lab-notebook.md:4675]($STACK_REPO/docs/lab-notebook.md:4675).

   A credible deterministic replay requires identical prompts, dates, tool outputs, filesystem state, serving configuration, cache execution path and random state, with prefix identity verified through the interruption. Matching token totals is insufficient. Retaining partial solutions or supplying reviewer advice creates an informed continuation, not a replay.

   **Recommendation:** do not treat the proposed same-seed rerun as the same sample by default. Even a proven replay saves no total work: it regenerates the discarded prefix.

4. **P4 — MAJOR: “past 30K is rare” describes observed successes, not the relevant conditional probability.**

   I reproduced the script’s **454 rows, 54 transcript mismatches, 381 identity-matched passes**, and its median/p95/max of **2,303 / 16,466 / 35,771**. Both passes above 30K are `book-store`.

   Two qualifications matter:

   - Seven of those passes are invalid `go/counter` observations. Excluding them gives **374 valid passing observations**; **2/374 = 0.53%** exceeded 30K.
   - Among valid passing `book-store` observations, **2/12 = 16.7%** exceeded 30K. These are descriptive counts across repeated items and differing scaffolds, not independent probability estimates.

   The decision needs:

   \[
   P(\text{strict pass under full gate}\mid
   \text{stream reaches 41K},\ \text{model},\ \text{item class},\ \text{execution history}).
   \]

   That conditional is **unidentified by the available censored data**. Zero observed finishes above 41K cannot demonstrate that such finishes are unlikely when the instrument killed those streams.

   M59 supplies a warning against premature clipping: **13/17 valid reruns passed**. Their successful logged totals actually span **3,016–39,142**, not 12–39K. The notebook also records conversions inside the old window, demonstrating that the rescue count mixes increased allowance with execution variation. See [lab-notebook.md:4722]($STACK_REPO/docs/lab-notebook.md:4722).

   **Recommendation:** describe long successful requests as uncommon in the observed, censored sample. Do not turn that into a probability of failure after 41K.

5. **P5 — MAJOR: rerunning all capped cases costs time; savings from selective abandonment cannot yet be estimated.**

   Verified M61 totals are **17.355 hours summed item wall time** and **1,204,205 logged output tokens**. Server telemetry confirms the three interrupted streams at approximately **40.5K, 41K and 43.5K**, followed by stream-closure errors. Those approximately **125K generated tokens are absent from completed-request totals**—about another 10.4% over the logged count. Evidence: [mlx_vlm.log:79765]($STACK_REPO/logs/mlx_vlm.log:79765), [mlx_vlm.log:82487]($STACK_REPO/logs/mlx_vlm.log:82487), [mlx_vlm.log:87931]($STACK_REPO/logs/mlx_vlm.log:87931).

   For a **three-tail-case chain**, using 18.7–25 tok/s and a 41,000-token cutoff:

   | Conditional scenario | Difference versus single-pass |
   |---|---:|
   | Deterministically replay all three | **Lose 1.37–1.83 h** regenerating the long-stream prefixes, plus repeated earlier work and overhead. Observed original item prefixes total about **1.60 h**. |
   | Abandon all three; each would otherwise run to 81,920 | **Save 1.36–1.82 h**, plus any avoided subsequent work. |
   | Abandon all three; each current request would reach 102,400 | **Save 2.05–2.74 h** on those requests, plus any subsequent work. |
   | Abandon a request that would finish just after 41K | Almost no time saved; a potentially valid solve lost. |

   These are **conditional calculations, not expected savings or hard wall-time bounds**. Later requests, repeated prefixes, tools, grading, passive-gate overshoot and further decode slowdown can increase costs substantially.

   More generally, let \(C_i\) be time already spent at cutoff and \(L_i\) the remaining single-pass time. Deterministic replay loses \(C_i\); abandonment saves \(L_i\). With rerun indicator \(R_i\):

   \[
   \text{chain savings}=\sum_i[(1-R_i)L_i-R_iC_i].
   \]

   The data do not identify \(L_i\), the selection rule, or future tail frequency, so they do not identify expected chain savings. Nor do they establish a finite worst-case wall bound. Even the rev-2 nominal token allowance plus one-request overshoot represents **4.8–6.4 hours of generation per item** at those rates, before tools; its applicability must be re-established for the passive design.

   **Recommendation:** budget from V4 observations. Do not credit the 41K proposal with loop savings already supplied by K/N/T. Also, the 37,550-token, 12-completed-request failing stretch is below T and N: the new gate bounds its continuation, but does not necessarily stop it earlier than M61 did.

6. **P6 — MAJOR: a valid efficiency variant needs either unchanged execution or an explicit new evaluation policy.**

   **Tail queue:** true suspension and exact resumption can preserve the sample and improve scheduling, but does not reduce total compute. Killing and restarting duplicates work; switching models additionally complicates cache state and the one-loaded-instance session requirement. Never rank a partially completed “easy-first” queue.

   **Mechanical abandonment classifier:** preregistration removes discretion, but does not make false abandonment disappear or preserve the original full-gate metric. It needs complete full-budget traces, a separate calibration set, held-out validation, model/item-class coverage, known late-success controls, and a stated acceptable loss in strict accuracy. The observed 31–36K successful streams are necessary controls but cannot validate behavior beyond 41K.

   **Mid-stream repetition detector:** potentially useful, but repeated reasoning does not prove inevitable failure under sampled decoding. It needs attributable incremental observations, frozen thresholds, and shadow-mode comparison against completed full-budget trajectories. The approved passive event tailer presently lacks the required in-flight token visibility.

   A stronger future optimization is stopping once authoritative in-flight usage reaches the **resolved strict-failure threshold**: failure is then already unavoidable under the stated metric. That requires new instrumentation and preserves strict accuracy, while truncating ordinary-pass and latency diagnostics.

   **Recommendation:** build none of these before V4/P214. First collect the tail; then assess whether there is enough recurring cost to justify another instrument.

7. **P7 — MAJOR: V4 is valuable, but it is not a certification of the proposed classifier or the historical counterfactual.**

   V4 specifies three fresh-instance diagnostic runs and explicitly retains M61 as the record. See [m62-token-turn-gate.md:132]($STACK_REPO/docs/specs/m62-token-turn-gate.md:132). Different dates or cache paths mean these runs may not reproduce the original interrupted trajectories.

   Record whether each actually reaches 41K, every completed request’s usage, first-write timing, strict outcome, budget closure, and total wall time. If a rerun finishes below 41K, it supplies no direct observation of the conditional tail. Even three genuine tail failures would be weak evidence: under an idealized independent binomial model, zero successes in three still permits a one-sided 95% upper success probability of about **63%**; these cases are more clustered than that model assumes.

   **Recommendation:** use V4 to discover mechanisms and size further measurement, not to declare the tail safely disposable.

8. **P8 — MAJOR: the written acceptance criteria still describe the rejected proxy design.**

   The operator’s passive-gate ruling is recorded at [open-questions.md:18]($STACK_REPO/docs/open-questions.md:18), but rev 2 still promises admission holds, quiescent grading, authoritative proxy usage and no interrupted requests. Those guarantees do not transfer to a passive tailer.

   Before implementation approval, rev 3 needs explicit rules for event-to-kill delay, partial-request accounting, snapshot consistency, strict failure despite passing partial files, and verified server cancellation. A fixed timeout cannot implement a matched 41K token boundary; changing `max_tokens` can also change the resolved thinking budget through the 0.8 clamp. Evidence: [metrics.md:10]($STACK_REPO/docs/metrics.md:10).

   **Recommendation:** finish the passive design’s acceptance criteria and run V4 under that design. Preserve existing rows, exclusions and scaffold separation. No files were changed during this review.

**Verdict: reject and keep single-pass.**