# M76 B4 — change review ledger (four-eyes light; opinion, round 1 of 3), 2026-11-15

Candidate 1 (implementer Claude Opus, `claude -p`, session `07df4029`) on baseline `2da56449`; spec `docs/specs/m76-b4-tg2-legs.md` v1.1.
Panel (cursor-agent, `--mode ask`, context `checkout` snapshot with rule files renamed, user instructions unconfirmed):
Sol `gpt-5.6-sol-high` (returned, 7 findings), GLM `glm-5.2-high` (returned, 11 findings + 2 scope notes). Raw:
`opinion-change-sol.md`, `opinion-change-glm.md`. Test-writer delivery 2 (Claude Sonnet, session `86224b98`, continued; `testwriter-delivery2-report.md`): verdict fix-then-merge; 130 / 131 on the candidate.
Settled for the review: C342 (the tg2 runner is B4b; its absence is not a finding).

| id | raised by | finding | severity (designer) | disposition | why |
|---|---|---|---|---|---|
| L1 | designer S24-P4; GLM F1 | A8 inputs refuse the whole verdict on any DNF; tg1 A7 scores a DNF slot 0 (`_kv_a7_section`), AGENTS.md ranks DNF included; `VALID_WITH_DNF` legs are accepted states | major | adopted | traced; A8 uncomputable on accepted real data |
| L2 | Sol P3, P4 | A8 reads an `item_record` format no pipeline writes; A7's real path is harvested rows → B8 (`p426_verify`) accepted pairs → `_kv_a7_section`; no completeness check (80 items, 20 / language, s1 + s2) | blocker | adopted | traced (`compute_kv`, `_kv_a7_section`, `p426_hooks._item_record`); needs `p426_verify` + `p426_signals` in scope (spec gap) |
| L3 | Sol P1 | tg2 legs bind tg1's scaffold label and generation data (`opencode-v2-web-tg1`, `opencode_bench_v2_web_tg1.json`); M65 spec: `opencode-v2-web-tg2` | blocker | adopted | traced (`CORE_SPECS`, `tg2_config`) |
| L4 | Sol P2; GLM F9 | harvest rules accept only tg1's grade files (`go.stderr`, XML …); tg2 grader outputs would be unclassified → rc 4 | blocker | adopted | traced for the rules; exact files depend on the runner's layout → a real-output fixture |
| L5 | Sol P5 | the tg2 smoke bypasses tg1's strict pilot gate (VALID only, 0 DNF, realised count, speed-valid, pair-gated) | major | adopted (to confirm in the fix brief) | sequencer trace by Sol; not yet re-traced by the designer |
| L6 | Sol P6 | `load_draw` trusts the adjacent sidecar; no independent pin of the committed draw sha / universe sha | major | adopted | cheap; a consistent redraw in an arm commit passes today |
| L7 | GLM F4 | the tg2 amendment's writer and wall keys are unspecified; `verify_amendment` does not check `w_<lang>_s` | major | adopted | the writer is B4b's sizing report (C342 Q2); verify the keys at verify time |
| L8 | GLM F5 | positives' corpus root from `opencode_v2_core._polyglot_root()` (private, a guess) | major | adopted | take the root from B4b's corpus seam; refuse until it exists |
| L9 | Sol P7 | `grade_outcome` maps `storage_cap` to `grader_oom`; real `oom` / `mem_kill` unmapped | minor | adopted | traced (`tg2_grade` 1121, 1189) |
| L10 | GLM F6 | two copies of the C169 positives verdict | minor | adopted | one verdict, imported |
| L11 | GLM F7 | the record's `tg2_tiers` list accepts any listed tier | minor | adapted | the spec states one tier per record |
| L12 | GLM F3 | `acc` 0 while `passed` None for a DNF | minor | adapted | moot once L1 / L2 score from B8 rows |
| L13 | GLM F10 | no fake-ops `Sequencer.run` test through smoke → amendment stop → resume → positives → screen | minor (test gap) | adopted | ordering is asserted only from the leg table |
| L14 | GLM S2 | the first-arm alternation (screen ref, s1 test, s2 ref, reload test) is the implementer's call | scope request | → operator via the spec | spec states it |
| L15 | GLM F8 | positives run before the power / idle checks | minor | declined | CPU-only docker grading, no GPU; the leg's power check and idle wait still precede every launch |
| L16 | GLM F2, F11 | guard ordering / split messages | — | declined | no material consequence |
| L17 | test-writer d2 F1 | the `screen` pair has no dossier name: `p426_receipt.write_kv_dossier` / `PAIRS` accept `r1, pilot, s1, s2, reload, makeup, s3` only → `ValueError` after the screen pair; the decider never scheduled (C338) | blocker | adopted (→ B4b) | red post-reveal test `test_m76_b4_fe_postreveal_pairs.py::…[screen]` |
| L18 | test-writer d2 F3 | no tool writes a tg2 frozen record (`corpus`, `tg2_draw_sha256`, tier) — every tg2 leg refuses | major | adopted (→ B4b) | `p426_freeze` writes none of these |
| L19 | test-writer d2 F2 | tg2 has no make-up legs, tg1 resolves transport DNFs by make-up | major | → B4b spec open question | C343 (3) scores a remaining DNF 0; whether tg2 adds make-up is B4b's call (designer lean: as tg1) |
| L20 | test-writer d2 F5, residual | `--tg2-draw` never parsed (dead `getattr`); one amended refusal case (`bad2`) vacuous | minor | adopted (→ B4b) | name the draw seam in the spec or drop it |

Designer root cause: B4's spec assumed a runnable tg2 (C342) and scoped B4 to the chain / sequencer only, omitting the B8 verifier and
signals path A7 uses — L2, L3, L4, L7, L8 all sit on that boundary. Proposed handling: S24-P5 (docs/open-questions.md).

Test amendments (S24-P1): the 26 world-mismatched v1 tests were amended in delivery 2 (lever kv world; stub probe = the world's fake
probe; draw refusal via a patched repo root). One assertion changed, reported: the screen leg's frozen session label (v1 `{"s1"}` →
one value in `{s1, screen}`; the spec does not fix it). Post-reveal tests: `test_m76_b4_fe_postreveal_{mapping,pairs}.py` (38).
Full-suite comparison: not completed (the copies' empty submodules broke collection on the first run; the rerun was stopped once C343
stopped B4).

## Outcome (C343)

```
[four-eyes 0.7.0] outcome: stopped; mode: light (C325; B4b continues STRICT per C343)
designer, implementer, fixes: Claude Code: Claude Opus 5.5 (designer, sessions 23–24); claude -p: Claude Opus, session 07df4029 (implementer); fixes: none
test-writer: claude -p: Claude Sonnet, session 86224b98; continued; tests frozen 2026-11-15T06:56:54Z, candidate revealed 2026-11-15T06:59:25Z
panel: cold on candidate: Sol cursor-agent gpt-5.6-sol-high, no session id, checkout (user instructions unconfirmed), returned; GLM cursor-agent glm-5.2-high, no session id, checkout (user instructions unconfirmed), returned; verify: none
shared: designer and implementer Anthropic Claude Opus; test-writer Anthropic; not covered: Anthropic-family blind spots outside the two non-Anthropic panel members
go: 2026-11-11 C325 "go" (+ C338 amendment); accept: none; commit: none (candidate 1 not applied; records only); push: none of the candidate
```

Stopped at the change review: candidate 1 has verified blockers (L2–L4, L17) on the boundary with the unbuilt tg2 runner; it and
every finding carry into B4b (PLAN M83). Nothing of the candidate was committed or pushed.
