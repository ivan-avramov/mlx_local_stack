# M77 (= M76 B0) — change review (four-eyes light, opinion) — ledger

Panel: Sol (`cursor-agent --mode ask`, `gpt-5.6-sol-high`, session unreported) and GLM (`glm-5.2-high`), read-only snapshot of
both forks with the candidate applied + spec + both helper reports + frozen tests; user instructions unconfirmed (Cursor). Both
exit 0, valid. Raw: `opinion-change-{sol,glm}.md`. GLM traced the three protection questions (MTP ON keeps `joint_v1`; OFF never
serves a drafter or a verify stamp; mlx-serve and the worker agree on every accepted / refused configuration) and found them holding.

| # | raised by | finding | disposition |
|---|---|---|---|
| 1 | Sol P1 (major) | an inherited `MLX_VLM_DRAFT_KIND` / `MLX_VLM_DRAFT_MODEL` in mlx-serve's environment reaches the worker (the CLI writes them only when the flags are present), so an OFF entry may load a drafter | **decline — pre-existing residual**: the same inheritance applies today to every MTP-OFF entry (the P426 / P475 OFF arms); no launcher sets these variables (grep of `chain_ops`, `p426_secrets`, `p475_kv`, `scripts/`, `runserver.sh`); with a mode the new checks fail closed (refusal, never a served drafter). Recorded for B1: the leg's worker-environment check also requires both names absent on OFF arms |
| 2 | Sol P2 (minor) | `--tq4-attention` help still says `joint_v1` is always required | **adopt** (fix round) |
| 3 | Sol P3, GLM F1 / F2 (minor) | `draft_kind` has a sentinel default and the MTP-ON apply call omits it; the spec shows it required and "the same value" passed | **decline**: behaviourally identical (sentinel ≡ `mtp`); it keeps the existing fakes in `test_tq4_impl_wiring.py` unchanged as criterion 5 requires; spec erratum records it |
| 4 | GLM F3 (minor) | mlx-serve's message for other drafter kinds says "requires joint_v1" | **decline**: the spec kept today's messages on purpose (criterion 1); the fork has the kind-specific message |
| 5 | GLM F4 (minor) | OFF + `MLX_VLM_MTP_VERIFY_AB=1` through `_initialize_model` untested | **adopt** (fix round: one test) |
| 6 | GLM F5 (minor) | OFF + stray drafter path + `MLX_VLM_DRAFT_ALLOW_FALLBACK=1` + incompatibility serves OFF silently | **decline — residual**: the served state is the intended OFF state; the fallback flag is a deliberate degraded start |
| 7 | designer | the frozen mlx-serve test file fails the gate's `ruff format --check tests/` (18 C408, one reformat) | at Accept: `ruff format` on that file only (the gate lints `src/` and format-checks `tests/`; C408 in tests is not gated), AST-identical checked, the file rerun |
