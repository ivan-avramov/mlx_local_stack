# Session 25 history scrub — old → new commit map, 2026-11-17 (S25-P7, S25-P9)

The unpushed range above `origin/main` (`3c199587`) was rewritten with `git filter-repo --replace-text` (in a fresh clone, refs moved after
verification) to remove the box username from `docs/reviews/m76-b8-kinds/testwriter-1-report.md` as committed in old `d244005f`. Every commit
after it got a new sha; commit messages were rewritten by the tool; trees are unchanged except that one file. Designer records citing an old
sha were updated forward; verbatim helper reports (`docs/reviews/*/implementer-*`, `testwriter-*`) keep the sha they were written with —
resolve it here.

| old | new | subject |
|---|---|---|
| `0424892c` | `f77c10a2` | docs: C356 — S25-P1 (A5 counter with deployed template kwargs, ids.json regen), S25-P2 (tg |
| `05aff691` | `f3f10f24` | docs: C355 — tg2 grader timeout fix; B8 fix widened to a correct stage-3a readout (rule 2d |
| `1c42bd36` | `f588c617` | fix(bench): M76 B8 kv — a correct stage-3a readout (C354, C355 (2)(3), C356 (1)): planned  |
| `204277e5` | `c493bd24` | docs: M76 B4b-1 change review round 1 of 3 — ledger L1–L18 (Sol + GLM + test-writer delive |
| `25d49376` | `e6ba88f6` | docs: handoff — session 24 → 25 (Wave 1 done; B4b-1 building; B8 readout + tg2 grader fixe |
| `50c61922` | `02917e04` | docs: S25-P1 — A5 frozen-count gap is the offline counter omitting the deployed reasoning_ |
| `53508dd2` | `2a0cc92f` | docs: M76 B4b-1 change review rounds 2–3 of 3 — V1 (re-check resume bound to the current s |
| `59885020` | `c8087c84` | Merge branch 'main' into m76-s25-integration |
| `5f89eb28` | `31bd06ce` | docs: S25-P6 — correct S25-P2's unrun 'checked' claim; old vs new universe + draw diff gat |
| `726a9c5f` | `f6efa228` | docs: S25-P2 — committed tg2 universe refuses on main (freezer closure rotated by P585 / P |
| `7b48a9cb` | `1d61a7c3` | docs: C356 — the proceed-on-recs instruction is scoped to session 25, not standing (S25-P4 |
| `a4ca0f3b` | `05c9d22b` | docs: B8 change review — fix rounds 1–2 (F1–F5, R1), real-data acceptance (10 / 10 pairs,  |
| `addf6d37` | `7fcff531` | docs: S25-P5 — tg2 grader spec erratum v1a: spin-test step timeouts ≥ 3x the slowest quiet |
| `b4209957` | `9446f822` | docs: S25-P7 — unpushed 02ee829d carries the box username (hook gap); rewrite the unpushed |
| `b5f5d832` | `09e23732` | data(bench): tg2 universe re-frozen under grader m65-tg2-v3 (C356 (2), S25-P2 / P6) and dr |
| `c9f6696d` | `4bcd9af9` | feat(bench): M76 B4b-1 — tg2 legs to harvested evidence in P426 lever kv (A8): Tg2Corpus,  |
| `d244005f` | `02ee829d` | docs: B8 planned-kinds change review (Sol ran it on the real harvest) — ledger K1–K8 + S24 |
| `dd8edeec` | `93c2cb8a` | fix(bench): tg2 grader — a timeout kill keeps its start evidence (C355 (1), S24-P22): mark |
| `e4ecdbed` | `c3610bee` | docs: B8 spec erratum v1.1a — verify_all_kv keeps kinds= (F2 closes K2 at the consumer); i |
| `e6186955` | `fc0174c0` | docs: tg2 grader change review round 1 of 3 — ledger G1–G9 (Sol + GLM + test-writer delive |
| `f785efbd` | `1a06e90b` | docs: tg2 grader timeout-evidence spec v1 (C355 (1), S24-P22) — marker + bounded output al |
