# Implementer report, fix round 4: M76 B4b-2 T1 / T2 (candidate 5 = candidate 4 + this working-tree diff)

Nothing was committed, pushed, reset or unstaged. No record under `benchmark/results/` was edited. No server, model, GPU or leg was touched.

## Changes

**T1** is in `benchmark/bench/p426_verify.py`:
- New `KV_INVOCATION_PROBE_SESSION_KEYS = ("run_dir", "sid", "started")`.
- `kv_normalise` pops exactly these three keys from a dict `probe_session`. It drops the block only when nothing else is left in it.
- The real block also has `leader`. It stays compared, and so does any other key that might appear later. Every other part of the normaliser is unchanged, so the tg2-only-key refusals still apply.

**T2** is in `benchmark/bench/p426_panel.py`, `a8_prompt_check`:
- The accepted forms are now the exact `prompt`, or `'"' + prompt.replace('"', '\\"') + '"'` (opencode's form of the run argument).
- The rule escapes the rebuilt prompt and compares; it never unescapes the export. Equality must be exact, with no whitespace or case folding.
- For a prompt with no `"`, this is the same as candidate 4's two forms.
- For a prompt with embedded `"`, it is stricter: a quoted but unescaped export now refuses.
- I kept the exact unquoted form because the frozen `fe_packet` default `Scenario` and `impl_panel` (`quoted=False`) require it.

**Tests (implementer-owned):**
- New: `bench/tests/test_m76_b4b2_impl_r4fix.py` (11 tests).
  - T1: `kv_normalise` drops only the three keys (`leader` and other keys are kept, the input is not mutated). A world whose `probe_session` keys differ is accepted. A world whose `leader` differs still rejects, naming only `probe_session.leader`.
  - T2: the escaped, quoted form passes. Six near-forms refuse: unescaped, trailing whitespace, case, inner whitespace, unenclosed, opening quote only. A prompt without quotes keeps both of its forms.
- `test_m76_b4b2_impl_golden.py`, three edits:
  1. **T3** (testwriter's minor): `test_pilot_export_prompt_check` now resolves `origin/evidence^{commit}` with `git rev-parse` before `resolve_commit`. It probes for the new pilot's evidence directory and checks both arms (8 rows).
  2. The docstring and comment now say the pilot is new-identity.
  3. **A stale data assert I found:** `test_pilot_pair_b8_a8_shape` asserted `tampered["n16"] == {"javascript/word-search"}`. That fact belongs to the old pilot; `wave2.tg2/` pilot rows contain no `tamper`. It now asserts that both arms list no tampered rows. This is a test-data change, not a code change; please confirm it is acceptable.

## Red before the fix (candidate 4, one invocation: the r4fix, impl_golden, fe_real, fe_packet and fe_r3 files): 14 failed, 61 passed
- `impl_r4fix`: 5 failed (3 for T1; for T2, the escaped-form test and the `unescaped` case).
- `impl_golden`: 3 failed (`test_pilot_pair_b8_a8_shape` and `test_provenance_passes_on_the_real_tg2_pilot_manifests` from T1; `test_pilot_export_prompt_check` from T2 on `rust/say`, after the T3 fix).
- `fe_real`: 4 failed (the three real-pilot T1 tests and `test_the_real_pilot_exports_pass_the_prompt_check`).
- `fe_packet::test_the_exports_escaped_embedded_quotes_are_the_runners_prompt` and `fe_r3::test_the_new_identity_probe_session_block_is_per_invocation_not_provenance` also failed.

## After the fix
| set | result |
|---|---|
| all `test_m76_b4b2_*` (18 files, one invocation) | **398 passed**, none failed or skipped (7:38) |
| `test_m76_b4b1_*` (12 files) | 480 passed, 1 failed: `fe_golden_tg1::test_b8_regenerates_byte_identical` ("frozen stack_head_on f2b61127… does not resolve") |
| `test_m76_b3_*` (25 files) | 589 passed, 3 failed: `impl_golden_mtp` ×3 (`git show f2b61127…:main_models.yaml` exit 128) |
| `test_p426_*` (13 files) | **207 passed** |

These counts and the four `f2b61127…` failures match what the round-3 report gave for the same families. The commit is absent from this copy; that is not caused by this diff.

The first full B4b-2 run after the source fix gave 397 passed and 1 failed: the stale tampered assert above. I fixed that assert and ran the whole set again; the 398 is from that second run.

The real prompt check passed on all 8 pilot rows across both arms, through both `fe_real` and `impl_golden` (the polyglot checkout and the evidence objects were present; the tests did not skip).

## Not run / questions
- **Not run:** the sweep of the prompt check over the 80 real N16 s1 rows (testwriter §6 caveat, B11). I wrote it as a read-only script, `../scratch/fix4_s1_promptcheck.py`, but running it needs a permission I don't have. Please run it before acceptance: `python3 -I ../scratch/fix4_s1_promptcheck.py .` from the stack directory with the bench venv. If opencode also escapes backslashes, a prompt containing `\` will refuse. That is fail-closed, but the rule would then need widening (one more bounded form).
- **Q1:** Is it acceptable that a quoted but unescaped export of a prompt with embedded `"` now refuses? It is stricter than candidate 4. I believe opencode never writes that form, and the real `rust/say` bytes confirm that.
- **Q2:** `test_m76_b4b2_fe_tmpdump.py` is still an emptied scratch file (testwriter §6). It is a frozen test, so I left it for the test writer to delete.
