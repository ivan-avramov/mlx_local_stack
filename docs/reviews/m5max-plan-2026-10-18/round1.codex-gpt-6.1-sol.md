# Plan review round 1 — codex gpt-6.1-sol

review-panel member `codex` (runtime codex 0.163.0, model `gpt-6.1-sol` from the output header, provider openai, reasoning effort high, sandbox read-only, ephemeral session `01a152c7-99d1-7ae0-b61f-78d053ac9ece`; context: sealed brief in an empty directory, but `~/.codex/AGENTS.md` exists so user instructions loaded; level L3 against the driver, vendor basis declared+observed). Dispatched 2026-10-19T06:09:35Z, finished 2026-10-19T06:13:19Z, tokens used 18,589 (total-only), money unreported. Mode: converge, 1 round. Driver adjudication is in `README.md` beside this file.

---

**P1 — Major — R2: making an upstream merge a prerequisite for the reranker**

The plan introduces an additional dependency without establishing compatibility or necessity. A fix targeting MLX 0.32.4 does not demonstrate compatibility with the settled 0.32.3 pin, or justify lifting it.

**Failure scenario:** P369 completes qualification, then the 61-commit upstream integration changes numerical behavior or dependency requirements. Qualification must be repeated, and the reranker waits for an unrelated compatibility campaign.

**Proposed change:** Separate upstream integration from reranker scheduling. After P369, use the approved, compatible fork head unless a separately reviewed upstream integration provides a demonstrated benefit. Include any repeated qualification in that integration’s cost.

**P2 — Major — R7: unsupported box restrictions distort the work order**

The brief establishes Cursor as mandatory for P385, not for P369 fix rounds. Branch location is an access constraint; GPU smoke location is a phase constraint. Neither establishes that all P369 development or tg2 steps 3–4 belong exclusively on m5max-128.

**Failure scenario:** m5max-128 spends days on GPU work while this box builds lower-priority adapters, although it could complete box-free P369 fixes or tg2 development. The campaign’s critical path remains unnecessarily serialized.

**Proposed change:** Assign ownership by phase. Consider transferring the approved fork source or required immutable cache artifacts, doing eligible development and Codex review here, and retaining GPU qualification on m5max-128. Preserve one owner for the fork branch. Require a concrete dependency before excluding an entire item.

**P3 — Major — R3 and “Sequencing and conflict control”: local ordering does not coordinate the boxes**

R3 before R4 establishes an order only on this box. It does not prevent m5max-128 from changing the same runner path. Moreover, locally merged, unpushed changes remain invisible to the other box; fetching its changes provides only one direction of coordination.

**Failure scenario:** m5max-128 develops tg2 against the old cleanup behavior while R3 changes it locally. The changes either conflict later or merge cleanly while preserving incompatible assumptions.

**Proposed change:** Establish shared-file ownership and an explicit integration handoff between boxes. Identify which remote phase must consume R3 and arrange its publication approval before that phase starts. Describe R3-first as a local dependency, not evidence that cross-box conflicts are avoided.

**P4 — Major — “Sequencing and conflict control”: the full-suite result can describe the wrong candidate**

The plan runs the full suite, then fetches and rebases before merging, with only targeted tests afterward. Its claim that each merge has a green full suite therefore need not apply to the integrated candidate.

**Failure scenario:** a remote change to shared runner or configuration code combines badly with an otherwise passing local change. The selected targeted tests pass, but another stack component breaks.

**Proposed change:** Fetch, integrate, resolve conflicts, and then run the full suite on the frozen candidate. Schedule that run once at the correct point. Any subsequent candidate change requires verification appropriate to that change.

**P5 — Major — R4: D2 is deferred without a dependency-closing plan**

“OrbStack is stopped” explains why Docker tests currently skip; it does not establish that D2 should follow both adapters. The plan explicitly leaves contract clauses owed but supplies no scheduled owner or completion gate for the shared service.

**Failure scenario:** both adapters pass injected tests, yet neither can complete its required service-backed behavior. Integrating D2 then exposes differences that require revising both adapters, while the box has accumulated partially qualified components.

**Proposed change:** Either prioritize D2 here, or name its owner and freeze the interfaces needed by R4 before implementation. Distinguish adapter unit completion from integration acceptance, and require the relevant Docker-backed checks before declaring the latter complete.

**P6 — Minor — R6b: reopening the settled C181 decision without evidence that its contingency applies**

The plan asks the operator to reconsider an explicit ruling based on a hypothetical multi-day delay. No such delay is established in the situation report.

**Failure scenario:** the operator spends attention revisiting a settled assignment instead of deciding the actual fork-publication gate.

**Proposed change:** Keep C181 as the executable default. Raise an override only when a concrete scheduling obstruction exists, with the expected delay and benefit quantified.
