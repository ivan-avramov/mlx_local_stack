# S29 — host changes and unknown evidence files are recorded, never blocking (C384, S29-P6)

v1.0, 2026-11-22. four-eyes light (data boundary: the harvest; not security / architecture).

## Goal (verbatim in every brief)

The bench box is not a sandbox: Homebrew and other updates happen while a campaign runs. The operator's rule (C384): note and
record the versions of what we care about, never be blocked when an update occurs. Today a host-fingerprint change refuses the
next launch, makes a leg in flight INVALID and stops the run (C360), and the harvest refuses a whole leg when it meets a file it
has no rule for (S29-P6: a 34-byte grader `execute.marker`). Solving it means: a host change and an unrecognised evidence file
are recorded where a reader of the run's records sees them, and the run continues; nothing that decides a grade or a leg's
validity on its own facts changes.

## Scope

1. `benchmark/bench/p426_wave2.py` (sequencer) — C360 refusals become records.
2. The tg2 positives host check (same file, the positives record) — a host change is recorded, not a problem.
3. `benchmark/bench/p426_harvest.py` — `.marker` harvested; an unrecognised file and a reference to it are recorded, not refused.
4. Recorded legs already INVALID only by the host change (today: `tg2-m76-x-s1.a3`) take the state their recorded facts give.
5. Tests for all of the above.

The designer (not a helper) updates `AGENTS.md`, `docs/open-questions.md` and the handoff.

## Settled constraints

- (operator, C384) A host change never refuses a launch, never makes a leg INVALID or a positives record fail by itself, never stops a run.
- (operator, C384) The versions we care about stay recorded: `bench/host_env.py` `fingerprint()` / `diff()` are unchanged.
- (designer) The run's baseline (`<out-base>/host_env.json`) stays the first-check baseline; it is not rewritten.
- (AGENTS) No hand-edited records; sealed records stay verifiable; transport failures still abort; PII scrubbing unchanged.
- (designer) Every other harvest refusal (scrub / PII, symlinks, non-regular files, self-hash, missing leg.json, state checks,
  references outside the inventoried roots) is unchanged.

## Required behaviour (intent; mechanisms free unless stated)

**H1 — before a launch.** The diff against the run baseline is logged and recorded with the leg's sequence entry; the leg
launches.
**H2 — during a leg.** The diff between the host at the leg's launch and at its end is recorded in the leg's sealed record
(`leg.json`) and logged; the leg's `state` / `reason` / `class` come only from `classify_leg` (+ the existing OVERRUN rule).
A reader of `leg.json` alone can tell (a) what differed from the run baseline at launch and (b) what changed during the leg.
**H3 — run entry / exit / exception.** `host_env_start`, `host_env_final` and the exception log record and log; none stops.
`after_leg` no longer stops on a host reason.
**H4 — positives.** A host change before / after the positives session is recorded in the positives record, not appended to
its problems.
**H5 — legs already recorded INVALID by the host change.** On resume, a leg whose latest entry is INVALID with a reason that
starts `host environment changed during the leg` and carries no `(prior: …)` classification, and which is NOT yet harvested,
gets the state `classify_leg(root, recorded chain_rc, arm)` gives (OVERRUN rule with the recorded `overrun`). Invariants:
the original sealed `leg.json` is kept byte-identical and harvested; the record every consumer reads for the state (the
sequencer, harvest, `p426_freeze`, `p426_signals`, B8 `p426_verify`) shows the new state, the host changes and the C384
supersession with the original's sha256; its seal verifies. A leg with a `(prior: …)` reason, or already harvested, is left
as recorded (logged).
**P6a — `.marker`.** A `<step>.marker` directly in a tg2 `<item>.grades/seq-NNNN/` is evidence, harvested and scrubbed like
the other grade outputs at that boundary only.
**P6b — unrecognised files.** A regular file no harvest rule matches is not copied; it is listed in the harvest's own record
(source path in portable form, size, sha256) and logged; the harvest continues. A row reference to such a file is listed
there, not refused.

## Interfaces / traces

- Success: host Cellar gains `vim/9.2.1380` before s2 → sequencer logs `host environment differs from the baseline before
  tg2-m76-x-s2: …`, launches, s2's `leg.json` carries the before-diff; an upgrade mid-leg → `leg.json` carries the during-diff,
  `state` VALID when `classify_leg` says VALID.
- Resume trace: `--rerun` NOT given; latest `tg2-m76-x-s1.a3` INVALID (host reason, no prior), unharvested → state re-derived
  (VALID on its records) → harvested (marker included) → `after_leg` → pair dossier for s1 → s2 launches.
- Failure path kept: `classify_leg` INVALID (e.g. crashed chain) stays INVALID with its own reason, host changes recorded
  beside it; a harvest scrub failure still refuses.

## Acceptance criteria

1. Scenarios H1–H5, P6a, P6b each pass as tests on the data formats the code emits (real `fingerprint()`/`diff()` shapes,
   real `leg.json` / `sequence.json` / grade-dir layouts; the a3 shape: reason without prior, chain_rc 0, `.grades/seq-0002/`
   with `execute.marker` + `execute.out` + `execute-readback.*`).
2. Existing tests that pin the old refusals are changed to the new outcome, each listed with why; no other existing test changes.
3. The named test modules of the sequencer, harvest, freeze, signals and verify pass; nothing else fails that passed on the baseline.

## Non-goals

Changing the fingerprint's content, the classifier, the scrub, the tg1 paths, the arms' trees, the census bound.

## Open questions

None blocking. The full stack gate runs after the decider (it locks out legs); resuming on Accept with the named modules passing
is the designer's call (C353 / C383).
