# P613 step 3 — the panel contract (shared by implementer and test-writer)

## Goal (verbatim in every brief)

Decide, with evidence the operator can act on, whether `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` ships with MTP ON (P426; C204:
the operator makes the call from per-axis signals, no automatic pass / fail). The evidence is ONE generated, deterministic
`benchmark/results/p426/SIGNALS.md` built only from B8-accepted ON / OFF pairs: A7 tg1, A1 math500, M1 256K memory, A2 cjudge, A3
vision, A4 reasoning (steps 1–2, committed `71965f0a`), the subjective panel (step 3), then the final sheet + a recommendation (step 4).

Step 3 means: the C161 / C207 two-family blind pairwise panel over the B8-accepted, execution-passing, non-identical ON / OFF pairs —
its packet set and judges frozen before any verdict exists — and the sheet's §4.5 subjective section computed from the admitted
verdicts, so `SIGNALS.md` loses its "subjective panel pending" status.

Specification: `docs/specs/p613-b8-b6-signals.md` v2 §4.5, §5; `docs/specs/p426-fable-mtp-recert.md` v4 §7, §8; the step-2 contract
(`docs/specs/p613-step2-contract.md`; its interfaces stay unchanged except where this file adds). This file wins for step 3.

## Packet set (counted from the committed data, 2026-11-04)

- **Wave 1:** 166 / 166 B8 keys are C217-identical (A1 100, A2 40, A3 20, A4 6) → each scores 0.5, labelled "identical outputs; panel
  not run", not judged; A1 / A2 / A3 members have 0 judged items → reported, not tested. No Wave 1 packet.
- **A7:** per session, the B8-accepted keys with `passed is True` in both arms and `identical` false: **s1 11, s2 10** (both-pass
  41 / 41; identical among them 30 / 31). Packets 21; verdicts planned 21 × 2 judges × 2 orders = **84**.
- Judges: `${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/judges.json` `text` — `claude-opus-5-5` (family anthropic, client
  `claude-code:blind-judge`) and `cursor:gpt-5.6-sol-high` (family openai, client `cursor-agent`); rubric `RUBRICS["code"]`.

## A7 packet (one per item; the two solutions shown as A and B, slots balanced by `make_pairs(..., build="s2")`)

Inputs, all committed or hash-verified, read-only:
- rows / `final_tree` manifests: `benchmark/results/p426/wave2/<attempt>/<session>/*.jsonl` (through `bench.chain_rows`), the item's
  `<attempt>/evidence/<run>/<lang>__<item>.final_tree/manifest.json` on `main`;
- file contents: the `evidence` branch at a recorded commit (`--evidence-ref`, read with `git show <ref>:<path>`, no checkout):
  `…final_tree/objects/<sha256>`, `…<lang>__<item>.events.jsonl`; each object's bytes must hash to its name, the events file to the
  row's `evidence_sha256.events`; else `RefusalError`;
- the exercise start tree: `$POLYGLOT_DIR/<lang>/exercises/practice/<name>/` — every file used must hash to the universe's
  `items[<id>].prepared[<rel>]` (`benchmark/m62/universe.json`); else `RefusalError`.

Text, in this order, identical structure for A and B:
1. **Task** (once, shared): the item's `.docs/instructions.md` (+ `.docs/instructions.append.md` when present) and the solution /
   test file names (`entry["solution"]`, `entry["test"]`).
2. **Solution X**: a unified diff (`difflib.unified_diff`, 3 lines context, paths `a/<rel>` / `b/<rel>`) of every file in the final
   tree that differs from the start tree or is new, sorted by path; test files are protected and never differ (asserted).
3. **Tool use X**: the tool-call names and counts from the events file (`type == "tool_use"`, `part.tool`), sorted by name, e.g.
   `edit 2, read 3, shell 2, write 1`; nothing else from the transcript (no text, timestamps, durations, tokens, session ids).
4. **Grader**: "both solutions pass every test" (both-pass by selection).
`leak_problems` runs on every packet (`LEAK_PATTERNS` + the model names); any hit refuses the export. The judged length for
`length_adjusted` = characters of Solution X's diff.

## Interfaces (`benchmark/bench/p426_panel.py`; existing functions keep their behaviour)

- `a7_select(results_root, b8) -> (items, excluded)`: items `(session, id)` per the rule above from `b8["axes"]["A7"]`; `excluded`
  counts per session: `identical`, `one-arm-pass` (with ids), `neither-pass`, `rejected key`.
- `a7_packet(results_root, b8, item, evidence_ref, polyglot_root, universe_path, repo) -> {"task", "off", "on", "len_off", "len_on"}`.
- `freeze(out_dir, packets_meta, judges, rubric) -> Path` writes `<out_dir>/FROZEN.json`: packet files with sha256, item → (session,
  id, A/B slot), judges (label, family, client, model), rubric sha, `evidence_ref`, B8.json sha, counts (planned verdicts, Wave 1
  identical 166, A7 excluded per kind). Refuses if any verdict file already exists in `out_dir`.
- `check_frozen(out_dir) -> dict`: every packet still hashes as frozen; else `RefusalError` (verdicts are never sealed or ingested
  against a changed packet).
- CLI `python -m bench.p426_panel a7-export --results-root … --b8 … --evidence-ref <sha> --repo <git top> --polyglot-root …
  --universe … --judges <judges.json> --out <dir>` → packets + FROZEN.json; `a7-cursor --out <dir> --judge <label>` → runs
  `run_cursor_judge` for that judge (retries 0); `a7-seal --out <dir> --judge <label> --client-version <v>` → `seal_verdicts` for the
  Claude judge's bare verdicts. The Claude judge itself is the designer's `blind-judge` agent run over the frozen batch directories.
- `bench/p426_signals.py` `all` gains `--panel <dir>` (required; a missing FROZEN.json refuses): §4.5 per member — admitted items
  (`admit`: exactly one valid verdict per judge × order), raw per-item score (`item_scores(..., build="s2")`), permutation p on
  score − 0.5 (step-1 `permutation_p`), `length_adjusted` headline, judged n, missing / excluded counts, one-arm-pass left out,
  "conditional on both-pass", per-verdict provenance summary; Wave 1 members: identical 0.5, judged 0, "reported, not tested".
  Family {A1, A2, A3, A7-s1, A7-s2}; members with < 5 judged items not tested; Holm over the tested members (m fixed by that rule
  before any p is read — expected m = 2). Flag: a tested member Holm p < .05 favouring OFF. Status line:
  `PROVISIONAL — final review pending (step 4)`.
- Outputs committed: `benchmark/results/p426/panel/` (FROZEN.json, packets, verdicts, provenance) and the regenerated sheet.

## Golden (committed data)

A7 items s1 11, s2 10, excluded identical s1 30 / s2 31, one-arm-pass s1 1 (`go/bottle-song`) / s2 2 (`python/pov`, `python/book-store`), neither-pass s1 1 (`go/crypto-square`) / s2 0, 84 planned verdicts;
Wave 1 identical 166; subjective family tested members {A7-s1, A7-s2}, m = 2.

## Tests

Hermetic: a synthetic results root + a tiny git repo holding an `evidence` commit + a fake polyglot tree: selection counts and
exclusions; every hash refusal (object, events, start-tree file); diff text and tool counts on a known case; no timestamp / token /
model name / path in a packet (leak check); A / B balance; freeze refuses with a verdict present; `check_frozen` refuses a changed
packet; §4.5 numbers on hand-computed verdict fixtures (scores, permutation p, Holm m, < 5 rule, missing counted); byte-identical
regeneration. Golden (marked): the counts above. Test dir `benchmark/bench/tests/p613s3/`.
