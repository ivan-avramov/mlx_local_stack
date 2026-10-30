# Delivery 1b (same session): the specification changed — complete and revise the first delivery

The designer has revised the specification to v3.2 in response to a design review and to your gaps G1–G15. The copy's `docs/specs/p426-b2-tg1-wave2.md` is now v3.2; the change is `.b2-spec-v3.1-to-v3.2.diff` in this directory (and the slice plan is `.b2-slices.md`). New: §16 names the record schemas, module APIs and ChainOps seams; §16.3 resolves your §4 items 2, 4, 5, 6 and the §14.5 / C236 question; §4.1 / §4.3 now state the positional pairing and the per-outcome equalities (your item 3); §1 adds attempts `<leg>.a<n>`; §6.4–6.5 replace the in-memory credential comparison by an HMAC under a per-pair key; §11 adds the probe's run / evidence directories to the harvest roots, staged publication and the harvested pair dossier; §5.5 limits the make-up union to VALID-with-DNF legs.

Do, in your existing files and fixtures:

1. Write the s4, s5 and s8 tests (§13 lists what they owe) against §16's seams, with fakes implementing the §16.2 ChainOps seams on `FakeOps` where the chain is involved. Unit-level tests through the named module APIs are expected where a chain-level test would need a real process.
2. Revise every other test where v3.2 changed a behaviour or named a seam you had guessed (e.g. `--evidence p426` passed by the chain, the refusal format `REFUSED: …` and rc 2, the record kinds and self-hash, `slot_file`, the harvest CLI `--leg-root --main-root --evidence-stage`, the symlink rule inside final trees, attempts and pairs, the generic prediction, `bench_watch.main(argv, power=…)`).
3. s0 stays a fixture check on the baseline (a record, not part of the committed suite); keep every fixture validated there.
4. Same rules as the first delivery (behaviour not structure, real formats with cited sources, hermetic, no placeholder skips, no process command line containing `mlx_vlm.server`, `mlx-serve start`, `opencode run`, `run.py generate`, `run_tg1_probe` or `runserver.sh`).

Run all your files on the baseline and report as before: per file each test, class, baseline outcome and first failure line; the commands and summary lines verbatim; remaining gaps; anything in v3.2 you believe is wrong or contradictory.
