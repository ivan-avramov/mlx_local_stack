I've finished reading the spec against the Wave-1 tooling and the fork's T3 notes. Here are the findings.

**F1. Leg name, receipt, stdout and session-prefix names are not covered by the label (major, confirmed)**
- Location: §4 "Names under a label"; `p426_wave1.py:49-50`, `:185`, `:218`; `p426_leg.py:487, 705`.
- Problem: The spec relabels tunes, the frozen record, the M1 directory and the dossiers. It never relabels `leg_name()`, which is `{axis}-p426-{arm}-…` and is a separate function from the tune. That name keys `<name>.receipt.json`, `.refused-*`, `.stdout`, `.watch.log`, `.power.json`, the receipt file in `--out/receipts`, and `MLX_BENCH_SESSION_PREFIX=p426-<name>`.
- Failure scenario: An implementer follows the spec literally and leaves `leg_name` alone. If `--out` is reused, or the spec's "same sequencer" is pointed at S's out dir, `read_verdict` finds S's VALID receipt. The sequencer then stops with "VALID receipt but no harvested dossier" for every S′ leg. With a fresh `--out` the run works, but S and S′ receipts and session ids are indistinguishable by name. The "no output of the leg's stem" refusal covers rows only, not receipts.
- Proposed change: Name the leg name (and the session prefix) under the label, e.g. `{axis}-p426s2-…`. State that `--out` must be new, and that the sequencer refuses a non-empty `--out` that holds another label's receipts. Add tests for both.

**F2. The label is only matched against a self-declared field, not against the build (major, confirmed)**
- Location: §4 "The frozen record".
- Problem: The K2 check compares `--build` with a `build` string typed into `frozen.<b>.json`. Nothing ties the label to the actual shas. A missing field means `s`.
- Failure scenario: An S′ record written without `build` (or an S record copied under the wrong name) passes under the default label. The spec's failure path covers only the copy-S-as-s2 case. The reverse case, an S′ record run with no `--build`, gets S names. It then collides with S's outputs (refusal) or, in a clean tree, writes S′ rows as S.
- Proposed change: Pin the expected `mlx_vlm` (and `production_ref`) per label in code. `s` maps to S's recorded shas and `s2` to `c688e722`. Refuse on mismatch, and make `build` mandatory for any non-S record.

**F3. The dependency state is not recorded and the worktree venvs are not verified (major, hypothesis)**
- Location: §2, §4 success path, §7.1; `PIN_KEYS` at `p426_leg.py:292`.
- Problem: The frozen record pins heads and registry shas only. It has no mlx version, `uv.lock` sha, `requirements-bench.lock` sha, or installed versions for `.venv` (the server) and `.venv-bench` (the driver). Acceptance 1 checks a fresh scratch `.venv-bench`, not the frozen worktree's two venvs. The spec does not say how `.venv` is built in the worktree.
- Failure scenario: The worktree venv is copied from S's worktree or synced from an older lock. It runs mlx 0.32.3, and the fork's exact verifier kernels mismatch. That fails loudly in the best case. In the worst case it gives silently different transformers or mlx-audio versions under an `s2` label with nothing recorded.
- Proposed change: Have the frozen record carry the `uv.lock` and bench-lock shas plus the installed mlx, mlx-metal, transformers, mlx-audio, datasets and hf-hub versions of both venvs. The leg re-checks them at entry and exit. Specify `uv sync --frozen` for the worktree `.venv`.

**F4. Consumers that hard-code S names or paths are untouched (major, confirmed for two, hypothesis for the rest)**
- Location: §4, §6, §7.6.
- Problem:
  - `modelnames.py:273` exempts only `benchmark/results/p426/wave1/` for verbatim copies, such as `registry-on.yaml` text. `wave1.s2/` is not exempt, so the naming hook would flag the S′ dossiers at commit time.
  - `p426_panel.py:18` hard-codes `OFF_TUNE, ON_TUNE = "p426-off", "p426-on"` and reads `@p426-on::`. The blind panel (B3, C207) run on S′ rows would pair against S's tunes or find none.
  - `p426_bench_watch` and `p426_watcher` parse tune and stem names (hypothesis).
- Failure scenario: The S′ evidence cannot be committed, or the panel silently pairs S rows. That is exactly the confusion the goal forbids.
- Proposed change: Add these to the label work. Either parametrize them by label, or state explicitly that the panel refuses a non-`s` label until it is built.

**F5. A mismatched frozen record is harvested before it is refused (minor, confirmed)**
- Location: §4 failure path; `p426_wave1.py:208`.
- Problem: The sequencer copies the frozen record and the overlay into `wave1.<b>/run/` before any leg runs. In the failure path, the bad `frozen.s2.json` (the copied S record) is committed-bound as S′ run evidence before the "first leg refuses".
- Proposed change: Check the record's build in the sequencer before the run-file harvest. Alternatively, say that the failure path leaves that file in `wave1.s2/run/`.

**F6. Silent default of `s` (minor)**
- Location: §4 "Label".
- Problem: The default `s` makes a forgotten `--build` run as S. The failure scenario is F2's reverse case.
- Proposed change: Make `--build` required for the sequencer and leg once the code exists. Keep byte-identity for `s` through an explicit `--build s`.

**F7. Fork changes that alter measurement beyond A3 (minor, hypothesis)**
- Location: A3, §3.
- Problem: The fork's #2545 changes Python and CLI generation to follow the checkpoint's `generation_config.json` when no temperature is passed. The in-process M1 qualify leg uses fork Python generation. The spec's A3 only covers the renamed knobs, and §3 relies on stack tests, which may not exercise this.
- Proposed change: Add an assumption or acceptance item. The M1 qualify and the driver paths either pass explicit sampling or are shown unaffected.

**F8. A1 evidence is not on the dependency set that will ship (minor)**
- Location: A1.
- Problem: A1 measured the exactness tests with transformers 5.14.1, while the relocked S′ resolves transformers 5.15.0. Acceptance 3 reruns them in the stack's `.venv`, so this is only a labelling issue.
- Proposed change: Say that A1 is superseded by acceptance 3.

**Scope request (no severity)**
Record the build label and the lock shas in each leg's receipt and manifest. That makes the label visible in the evidence itself, not only in file names.
