# M76 B4b-2 — the A8 (tg2) consumers: B8, signals, panel (spec v1.0, 2026-11-19, for design review round 1 of 3)

Parent: `docs/specs/m76-b4b-tg2-runner.md` (B4b-1; its scope line names this spec), `docs/specs/m76-tq4-certification.md` §A8 /
§Panel / §Noise floor, `docs/specs/m76-b7-statistics.md`, PLAN M83. Four-eyes STRICT (design review, change review, verify; panel
Sol + GLM + Claude Sonnet; a fresh blind test-writer, not the implementer's model). Implementation and every pytest run start only
after the A8 decider's sequencer exits (S27-P8).

## 1. Goal

From the harvested A8 records alone (`benchmark/results/m76/wave2.tg2/` on `main`, objects on `evidence`), build `axes.A8` in B8,
the A8 section and flags in the signals sheet, and the A8 panel members — the same contract A7 has, read by B7's pre-registered A8
plan. A defect found here is regraded, never rerun (the B4b-1 contract). Every existing output (A1 … A7 in `B8.json`,
`SIGNALS*.md`, the frozen stage-3 panel) is byte-identical for the existing inputs.

## 2. Settled constraints (operator rulings; not reopened)

- C338 / C336 / C339: the decider always runs; A8 is read by `m76_rule.axis_verdict("A8", …)` at α* 0.001 (`alpha_star_fixed`),
  unit items, 80 items (20 per language × rust / javascript / java / cpp), 2 sessions (s1, s2), one look; HOLD = any language's
  point estimate < −20 pp (`m76_rule.a8_hold`), blocking.
- Outcome = `acc_strict@budget`: an item-session scores 1 iff `passed is True and converged is True`; a `p426_dnf` slot scores 0.
- Panel: A8 joins the subjective Holm family when the decider runs (A1, A2, A3, A4, A5, A7 sessions, A8 sessions); members with
  < 5 judged items are reported, not tested; Holm-adjusted p < .05 favouring N16 → flag. Judges per `judges.json`; both orders;
  a judge context never holds both orders of one item (S26-P18).
- KV leak rule (C362): a leak is what reveals the ARM or the BOX; model-family tokens and generic paths are answer content.
- Noise floor (S22-P9): N16's s1-vs-s2 discordance on the same items beside X-vs-N16's; diagnostic only.
- Walls / latency: within-pair only, never against earlier sessions; the launch-latency log is shown beside them (S27-P5).
- C365: the runner's abort-vs-grade race is a residual; no runner edit here. C366: the positives record and its rule are inputs,
  not changed here.
- L9: every new call that grades or validates a tg2 report passes `grader="tg2"`. L16: `row_scores` keeps passing tg2 rows through
  unchanged (no tg1 sidecar).

## 3. B8 (`bench/p426_verify.py`)

1. **Namespaces per axis.** Replace the module-level `WAVE` use on the KV path by an axis table:
   `KV_AXES = {"A7": (namespace "wave2", corpus "tg1", attempt re ^tg1-m76-(n16|x|v)-(pilot|s1|s2|s3|reload)\.a\d+$),
   "A8": ("wave2.tg2", "tg2", ^tg2-m76-(n16|x)-(pilot|s1|s2|reload)\.a\d+$)}`; every reader (`_kv_load_attempt`, `harvest_manifests`,
   `_harvest_reasons_kv`, `_supersede_reasons`, the dossier path, `_sequence_*`) takes the axis' namespace explicitly. A7 calls pass
   "wave2" (outputs unchanged).
2. **`verify_a8_kv(results_root)`** mirrors `verify_a7_kv`: reads `wave2.tg2/run/{v8_base,sequence}.json`; requires `v8.lever == "kv"`
   and `v8.corpus == "tg2"`, the pair `(n16, x)` (`fz.TG2_PAIR`); confirmatory sessions fixed `("s1", "s2")` (never
   `kv_a7_sessions`), diagnostic `("pilot", "reload")`; per session the same rules as A7 (leg state / self-hash, commits = v8,
   HARVEST main under `benchmark/results/m76/`, the dossier `pairs/<s>__n16-a<k>__x-a<k>.json` PASS with only
   `kv_difference_problems`-allowed differences, provenance per `runtime.lang`, equal plan shas, equal seeds, the supersede rules
   of S26-P15 / P15b). Emits `axes.A8` with A7's key set plus `corpus: "tg2"` and `recheck: {s1, s2}` (§5).
3. **Fail closed on an unmatched final tree (fixes a silent trap for both axes).** In `harvest_manifests` / `manifest_sha`: an
   attempt whose HARVEST lists destination-"main" files under the axis namespace but whose pattern matches no final-tree manifest,
   or a row whose `final_tree.manifest` names a path the HARVEST does not publish, is a REASON (the session is rejected), never
   `identical: false` with null shas. A7's existing inputs all match (golden unchanged).
4. **Provenance.** `kv_a7_normalise` / `kv_a7_provenance_reasons` are made corpus-neutral (rename `kv_normalise`, keep the A7 alias)
   and checked on the real tg2 pilot manifests in a test; any tg2-only runtime key that legitimately differs between arms is
   added to the allowed list with a cited reason, nothing else.
5. `verify_all_kv` adds `axes.A8` iff `m76/wave2.tg2/run` exists; its absence leaves `B8.json` byte-identical.

## 4. Signals (`bench/p426_signals.py`)

1. `_kv_a8_section`: every confirmatory session B8-accepted with equal key sets, else "incomplete"; `{item: {session: 0/1}}` per arm
   by `_strict` (DNF = 0); the verdict ONLY from `m76_rule.axis_verdict("A8", look=1, test, ref, languages={item: language})`, the
   language from the id prefix (`<lang>/<slug>`; a prefix outside `TG2_LANGS` refuses).
2. Report beside the verdict (descriptive): per-language point and interval (the B7 per-language helper), the HOLD line, the paired
   session delta (as A7), per-session estimates, the session-interaction flag, the noise floor (N16 s1 vs s2 discordance; X vs N16),
   the reload control (same-seed X reload vs X s1/s2 and N16 reload, discordance only), decode (`_speed` over `items[].totals`),
   per-language walls within the pair with the S27-P5 caveat and the latency-log summary for each leg's window.
3. Flags: A8 joins `kv_flags` (LOSS, UNDECIDED, size warnings, `hold`, `session_interaction`); `KV_BLOCKING` gains `hold`.
4. Headings / tuples that name A7 or tg1 get the A8 / tg2 twin; `render_kv` adds "## A8 tg2" after A7; with no `axes.A8` the sheet
   is byte-identical.

## 5. Re-check labels

`run/recheck-s1.json` / `recheck-s2.json` (sealed by the sequencer; `sequence.json` `rechecks.*.sha256`) are read by B8, re-verified
(seal + sha in `sequence.json`; s1's ack when its verdict was not `inside`), and labelled in the signals sheet as the runner's
interim re-check (descriptive; never a verdict). A missing re-check record for a harvested session refuses.

## 6. Panel (`bench/p426_panel.py`)

1. Members `A8-s1`, `A8-s2` (only sessions B8 accepted; `kv_members()` gains them when `axes.A8` exists); rubric "code" (language-
   neutral). The frozen stage-3 panel (A1 … A7) is not re-exported or re-frozen; A8 members are a separate freeze bound to the B8
   record that carries A8.
2. **Packet (`_a8_packet`)**: selection as A7 (both arms `passed`; identical final trees counted at 0.5, not judged). Task text = the
   exact tg2 prompt bytes the model saw, rebuilt by the runner's own prompt function (`corpus_tg2` `prompt`, E1, incl. the helper
   sentence H; never the inject addendum), and checked against the recorded transcript's first user message (sha equal, else refuse).
   Start tree = the MATERIALISED tree (`tg2_materialize.prepare_tree`; its bytes hashed against `prepared`), never raw polyglot bytes.
   Final tree = the evidence ref at `benchmark/results/m76/wave2.tg2/<att>/evidence/<run>/…`, manifest sha equal to the row's and B8's.
   Diff = every new or changed file; protected = the entry's `tests` ∪ the build files the prompt forbids editing; a changed protected
   file refuses EXCEPT Rust `Cargo.toml` `[dependencies]` additions naming crates in `OFFLINE_CRATES.md` (the prompt permits them).
   Non-UTF-8 files: listed by path and size, not diffed. Tool counts as A7.
3. Leak check: C362's KV list + registry names + the box identity + template tags. A hit refuses the member export and is reported
   per item with the pattern name only (never the text); the designer takes it to the operator (no exclusion, no redaction).
4. Holm family: the A8 members join the existing family; the readout prints A1 … A7 unchanged and the family re-adjusted with A8.

## 7. Acceptance (pre-registered)

1. Goldens: the committed `B8.json`, `SIGNALS.md`, `SIGNALS-partial.md` regenerate byte-identically on `main`'s inputs with the
   change (A8 absent), and with `wave2.tg2` present only `axes.A8` / the A8 sections are added.
2. On the real harvested pilot pair: B8 builds the pilot (diagnostic) pair accepted, the final-tree manifests match (no null sha), the
   provenance passes.
3. Red tests first (blind test-writer): the unmatched-manifest trap (both axes), A8 attempt names / namespace, fixed sessions, HOLD
   wiring (a language at −25 pp → `hold` blocking), DNF = 0, a missing / tampered re-check, the prompt-sha check, the protected-file
   rule incl. the Cargo.toml exception, the leak refusal, A7 unchanged.
4. After the decider: B8 → signals → panel export on the real records, regrade only.

## 8. Out of scope

Runner / sequencer / probe changes (B4b-1, frozen identity); the C365 race; the positives rule (C366); stage 4 (V); any tg1 change
beyond the fail-closed fix of §3.3.

## 9. Questions for the design review

Q1 is §3.3's fail-closed rule right for A7 too (could a legitimate A7 row lack a published manifest)? Q2 is the reload control in §4.2
meaningful as specified (X reload vs X s1/s2)? Q3 should the panel's task text include H (it is what the model saw) — or does H
leak nothing and change nothing? Q4 the Cargo.toml exception: allow only additions of offline crates, or any edit the grader
accepted? Q5 does a both-pass, identical-tree item count 0.5 as in A7, given multi-file trees?
