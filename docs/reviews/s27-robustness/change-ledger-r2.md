# S27 robustness bundle — change review round 2 of 3 (panel verify of fix round 1, candidate 2): ledger

Candidate 2 = patch `out/candidate-2.patch` (70 files) = candidate 1 + `fix-1.patch` (38 files). Panel: GPT-5.6 Sol High, GLM 5.2
High (cursor-agent, checkout, user instructions unconfirmed), Claude Sonnet 5.5 (fresh `claude -p`, session `c8b6da42…`, shares the
test-writer's model). Sonnet and GLM: X1–X19 resolved (traced), no blocker / major. Sol: four majors. Raw outputs beside this file.

| id | finding (raised by) | disposition | why |
|---|---|---|---|
| Y1 | X2's anchored path does not require the recorded `/metrics` sample to be the integer 0; an absent / malformed `in_flight_at_kill` enters it (Sol P1) | adopted | data validity: the anchored case replaces a sample that READ 0, it never stands in for a missing one. Refuse absent / None / bool / str. |
| Y2 | tg1 Go: a docker launch `OSError` is a plain `TransportAbort`; a failed docker OOM inspection reads as "not OOM" (Sol P2) | adopted | X6's intent (the harness's own docker failure is typed at the source); an unverified OOM state must not score an item. Launch failure → `spawn`; failed inspection → `transport`. |
| Y3 | The chain's second scan claims any process whose sid is the probe's and that started after the probe: a reused sid (an unrelated new session leader after the session died) is killed (Sol P3) | adapted | traced (`chain_ops.py:1030–1042`). The kernel keeps a live session's id from reuse, so a match is the probe's session unless the session died and the pid was reused; the guard is the leader's identity: a process with pid == sid that is not the recorded probe (create time) ⇒ the session was reused ⇒ no session claim (recorded). |
| Y4 | Freeze accepts a sealed accounting sidecar naming no item record; harvest only checks it exists; neither binds slot / rerun / row / disposition (Sol P4) | adopted | traced (`p426_freeze.py` `_accounting_ok`, `p426_harvest.py:739`). One sidecar validator (X4's `accounting_sealed_for` contract) used by the chain, freeze and harvest; "no item record" allowed only with the recorded done-hook failure. |
| Y5 | The abort unwind path drops a returned interim infra fault (`arm_runner.py:958`) (Sonnet P2) | adopted | record it as at `:779`. |
| Y6 | `foreign_new` basename uncapped (title-style argv[0]) (Sonnet P3) | adopted | data boundary; cap at 64 chars. |
| Y7 | v8 cannot tell a real interrupt row sha from a made-up one (Sonnet P1) | declined (residual) | the sealed record's trust model (v8 trusts the writer that verified the row, X12); the record's seal is the protection; stated in the ship recommendation. |
| Y8 | `stage_failure` leaves rc 125 + timed out untyped (GLM M1) | declined (residual) | the harness's own timeout kill does not return 125; the implementer's reading (a stage timeout is the outcome, §5.1) stands; both paths score strict 0. |
| Y9 | Run the full suite before round 3 (Sonnet P4) | covered | S28-P8: the gate is the suite check, compared with the baseline run of this layout. |
| Y10 | Conftest installs the hermetic wrapper via monkeypatch (LIFO), structurally preventing X19's leak class (GLM S1, implementer) | scope request → operator | beyond the request; X19's regression test guards it today. |
