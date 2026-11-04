# P613 step 4 — the final sheet contract (shared by implementer and test-writer)

## Goal (verbatim in every brief)

Decide, with evidence the operator can act on, whether `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` ships with MTP ON (P426; C204:
the operator makes the call from per-axis signals, no automatic pass / fail). The evidence is ONE generated, deterministic
`benchmark/results/p426/SIGNALS.md` built only from B8-accepted ON / OFF pairs: A7 tg1, A1 math500, M1 256K memory, A2 cjudge, A3
vision, A4 reasoning and the subjective panel are in it (steps 1–3). Step 4 means: the sheet gains the generated A7 first-divergence
section (C284 / P629) and becomes FINAL — every pre-registered section present, its status line no longer provisional — so the
operator's MTP call rests on one generated artifact.

Authority: C284 (P629's rule, adopted); `docs/specs/p613-b8-b6-signals.md` v2; step-2 / step-3 contracts (interfaces unchanged except
as added here). This file wins for step 4.

## The divergence section (C284)

- Pairs: B8-accepted A7 pairs only (s1, s2), every planned key; the `evidence` branch at a RECORDED ref (`--evidence-ref`, read with
  `git show <ref>:<path>`; no checkout), the attempt's `<attempt>/evidence/<run>/<lang>__<item>.events.jsonl`; the events file bound
  through the attempt's `HARVEST.json` as step 3's erratum E2 (raw `sha256` == the row's `evidence_sha256.events`, `published_sha256` ==
  the bytes read); else `RefusalError`.
- Per item: parse both arms' events; keep `type` `text` and `tool_use`; group by `part.messageID` in order of first appearance. For each
  message: `gen` = the sorted multiset of (`text`, the text) and (`tool`, tool name, JSON of `state.input` with sorted keys); `env` = the
  sorted multiset of (tool name, input JSON, `str(state.output)`). Walk both message lists in step: the first index `k` where the pair
  differs. Kind: `identical` (no difference, equal length); `cutoff` (one list a strict prefix of the other); `generation` (message `k`'s
  `gen` differs); `environment` (message `k`'s `gen` equal, `env` differs). Record `k` and, for `environment`, the first differing tool
  name.
- Output: per session the counts per kind and every item with its kind and `k`, sorted by id; a session total and both; a FLAG when any
  item's kind is `generation` (with the items). Labels: "visible text and tool calls only (reasoning tokens are not exported)".
- Golden (designer's exploratory count, the same rule, `evidence` `b6ec7819`): s1 identical 18, environment 24, cutoff 1, generation 0;
  s2 identical 17, environment 25, cutoff 1, generation 0 (86 items).

## Final status

- `p426_signals all --panel <dir> --evidence-ref <sha>` (the new flag required for the divergence section; absent → the step-3 record
  unchanged) writes status `FINAL — P426 certification evidence` when B8, every Wave 1 axis, A7-s1 / s2, the panel and the divergence
  section are present; otherwise the step-3 statuses as today.
- The header records the evidence ref.

## Interfaces

- `bench/p426_signals.py` (or a new `bench/p426_signals_divergence.py`; verify the name is unused first; never `p426_wave1.py`):
  `a7_divergence(results_root, b8, evidence_ref, repo) -> dict`, rendered as `## A7 first divergence (C284; \`divergence\`)` after §4.5.
- The inputs it reads enter `SIGNALS.json` `inputs` (repo-relative evidence paths prefixed `evidence:<ref>:`).

## Tests

Hermetic: a tiny git repo with an evidence commit and synthetic events for every kind (incl. parallel tool calls in a different
completion order → identical, a tool output differing → environment, a text / tool input differing → generation, a strict prefix →
cutoff), the HARVEST binding refusals, the flag raised / not raised, byte-identical regeneration, the `--evidence-ref` absent path
unchanged; golden (marker `p613s4_golden`) the counts above on the committed data. Test dir `benchmark/bench/tests/p613s4/`.
