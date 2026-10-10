# C121 cold review 1 (Claude) — branch `c121-seeded-opencode`

Reviewed snapshot: `b9b4e41` (= `$STACK_WORKDIR/c121/diff_1.patch`, i.e. `git diff 914239f b9b4e41`). The branch moved while this review ran
(`c315e15` merge of main, `d91ac6b` "review round 1" fix). Line numbers are at `b9b4e41` unless marked `@d91ac6b`. The last section
re-checks every finding at `d91ac6b`.

## Verdict

- At `b9b4e41`: **BLOCKING** (B1, B2, B3).
- At `d91ac6b`: **still BLOCKING** on B2 and B3. B1/B4/B5/B6 are fixed by reading the code; B7–B11 remain open.

## Experiments run (CPU only; pinned 1.18.30 binary; my own mock HTTP server; temp HOME/XDG_*; never :8000, never brew v2)

- E0 pytest seeding + run_opencode_probe + m50_entrypoints: 110 passed (at b9b4e41, integration test ran and was not skipped); at d91ac6b, with test_scaffold_policy_compare added: 132 passed.
- E1 Python `Popen(["opencode"], env=...)` looks up the binary on the child env's PATH (a fake `opencode` placed first on PATH ran).
- E2/E3 `shutil.which("opencode", path=_opencode_env(...)["PATH"])` resolves to `/opt/homebrew/bin/opencode` (v2) if `OPENCODE_PROBE_BIN`'s basename is not `opencode`, or if the pinned install is missing.
- E4 `opencode debug config` (v1): output is pure JSON; each call takes 0.34–0.40 s (no plugin). The overlay deep-merges: resolved options = all shipped options + `seed`.
- E5 the model rewrites `opencode.json` through the bash tool in the middle of a session (seed 999, temp 1.9): the file changes, but the later requests in the same `run` still carry seed 111 / temp 0.5. Config is not hot-reloaded.
- E6 non-git item dir under `$HOME/.../scratch/octmp.noindex/x/ex`, with a fake `~/.claude/CLAUDE.md` and `~/AGENTS.md`. With R8 off, both files are in the system prompt. With R8 on, CLAUDE.md is gone, but **`~/AGENTS.md` is still in the system prompt**.
- E7/E8 the model is absent from the global config. With the overlay: the run succeeds, and the request body keys are `max_tokens, model, seed, stream, stream_options, tool_choice` (**no deployed sampling**). Without the overlay: rc=1, 0 requests.
- E9 E6 again with `git init` in the item dir: `~/AGENTS.md` is no longer loaded, and the seed is still forwarded.
- Box facts: `~/.claude/CLAUDE.md` exists (mtime 2026-09-08); `~/AGENTS.md` exists (mtime 2026-09-07) and is the only instruction file among the ancestors of `$STACK_WORKDIR/scratch/octmp.noindex`; `$STACK_WORKDIR` is not a git repo; the pinned `.bin` holds only `opencode`; no `seed_propagation_verified` marker exists. Disclosure: I listed the entries of `~/.config/opencode/` (`opencode.json`, `opencode.jsonc`, `service.json`, …) and read no files there.

## Findings

**B1 — HIGH — seeded rows pool with, and give false provenance to, pre-C121 rows; nothing reads `scaffold_policy_sha256`.**
`benchmark/run_opencode_probe.py:772` (default `--out` = `<model>/opencode.jsonl`, which exists for 9 models with 22–26 unseeded rows each), `:782-790` (an existing manifest is checked only for router config/pid), `:800-807` (the manifest is regenerated, so the new `seed_base`/policy overwrite the old runtime), `:889` (rows are appended). Consumers: the only producer is `:465`. It is absent from `benchmark/bench/compare.py:60` (`_MUST_MATCH_RUNTIME`) and `benchmark/bench/provenance.py:293` (`_FINGERPRINT_RUNTIME`), and `benchmark/m1/scoreboard.py:114` pools every row in a file. A rerun with a different `--seed-base` is not refused either.
Failure: running `run_opencode_probe.py --model X --seed-base 1` appends 22 seeded R8-on rows to 22 unseeded rows, and the manifest then says `seed_base:1, R8 on` for all 44. This contradicts lab-notebook "They never pool with seeded rows" (`docs/lab-notebook.md:4429`) and AC5 "compare refuses".
Fix: when rows exist, refuse unless the existing manifest's runtime `{seed_base, scaffold_policy_sha256, opencode_version, opencode_bin}` match (a missing value counts as pre-C121 and is refused); add the policy hash to compare/`is_compatible`. VERIFIED (code + `ls` of results).

**B2 — HIGH — the overlay turns a loud "model not configured" failure into a silent run without deployed sampling, and the per-item check passes it.**
`:384-392` (the overlay declares `provider.mlx-local.models.<model>`), `:446` (the check only asserts `seed` and baseURL). If `<model>` is missing from the global opencode config (a new candidate, a renamed model, or `~/.config/opencode` lagging the repo), opencode 1.18.30 resolves the model as `{options:{seed}}` and runs it with no temperature/top_p/top_k/min_p/thinking fields and no `limit` (E7). Without the overlay the same run fails rc=1 (E8). It is related that `opencode_config_sha256` hashes the repo file (`:461-468`), while v1 loads `~/.config/opencode/{opencode.json,opencode.jsonc}` (ASSUMPTION: merge of both files; contents unread).
Fix: in `_assert_overlay_resolved`, require that the resolved `models[model].options` minus `seed` equal the deployed sampling fields (`params_for(model, profile="deployed")` mapped to opencode keys), or at least that the model plus every shipped option key is present in the entry discovery call, which runs before any overlay exists. The data is already in hand, so this costs nothing. VERIFIED (E7/E8).

**B3 — HIGH — R8 is incomplete: the operator's private `~/AGENTS.md` enters every probe system prompt and is not recorded.**
`:193` (scratch root `$STACK_WORKDIR/scratch/octmp.noindex`, under `$HOME`). opencode v1 searches upward from a non-git dir to `/` for AGENTS.md. `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT` gates only CLAUDE.md (E6), and 1.18.30 has no AGENTS-specific switch (its `strings` flag list has none; `OPENCODE_DISABLE_PROJECT_CONFIG` would also kill the overlay). `claude_md_present` (`:466`) records only CLAUDE.md.
Failure: every seeded row, the "clean" scaffold epoch, carries 2.5 KB of operator instructions. Edits to `~/AGENTS.md` between sessions silently change the scaffold, against "never pool across scaffold changes". Past rows were also exposed (`docs/lab-notebook.md:4440-4446` omits this).
Fix (pick one): (a) `git init` each item dir, which stops the upward search at the item root while the seed still forwards (E9; this is a scaffold change, already inside the C121 epoch — re-run the AC3 mock test under it); (b) move the scratch root outside `$HOME`, which needs operator approval under the artifact rule. In addition, record the sha256 of every ancestor instruction file in the manifest and refuse if one exists. The mechanism is VERIFIED (E6 simulation mirroring the box layout); the file's presence on the box is VERIFIED; the claim that it loads on the real box is ASSUMPTION (strong).

**B4 — MEDIUM — PATH-first resolution falls back to brew v2, including the pre-M50 discovery call.**
`:361-363` prepends `known.parent`. Spawns use the bare name (`:315`, `:433`, `:475`, `:480`, `benchmark/bench/provenance.py:1481`). `_opencode_version()` (`:763`) checks the absolute path only after discovery (`:737-738`).
Failures: pinned install missing, or a relative override, or an `OPENCODE_PROBE_BIN` basename other than `opencode`. In each case `opencode debug config` runs brew v2 before the router check (E2/E3). Per C123, v2 starts a shared background service and writes `~/.config/opencode/service.json`: a pre-check write outside the C114 exception (ASSUMPTION for the v2 side effects, which I was not permitted to run). Discovery then refuses on v2's schema, but only after the side effect. The test `test_opencode_env_puts_the_pinned_binary_dir_first_on_path` (tests `:60`) passes in the broken case. The integration test spawns `str(b)` (tests `:244`), so it never exercises the bare-name path.
Fix: validate the absolute pinned binary (exists, executable) before discovery, and pass it explicitly to every spawn, `provenance.opencode_router_base` included. VERIFIED (E1–E3 + code).

**B5 — LOW-MED — the `seed_propagation` marker is an unbound claim.**
`:405-426`. The marker content is compared with the constant `PINNED_OPENCODE_VERSION`, not with `oc_version`, the binary hash, or the config hash. It survives `npm install --prefix` reinstalls into the same dir. It proves forwarding for the repo config inside a temp `XDG_CONFIG_HOME`, not for the global config the probe actually loads. With an override bin the marker lands next to that binary. `_record_seed_propagation_verified` silently does nothing when the parent dir is absent (`:413`). P109's "row is flagged" is not implemented.
Fix: write a JSON receipt `{version, exe_sha256, config_sha256, test_sha256}` and compare it field by field at manifest time; or run the mock capture as a post-M50 probe self-test (about 2 s). VERIFIED (code).

**B6 — LOW — overlay-check semantics.**
`:429-447`: `returncode` is ignored and stdout is parsed from the first `{` onward. Failure is fail-closed (`sys.exit("REFUSED")`, `:834`), but a refusal at item k>1 leaves the manifest of items 1..k-1 without the C106 `router_exit` stamp. Each item now makes two `debug config` calls (`:830` via `provenance.py:1481`, then `:832`). That costs about 0.7 s per item in E4, but plugin loading is not covered by `--pure` (ASSUMPTION: possible network fetch per call).
Fix: reject rc≠0; fold both checks into one call that returns the parsed doc; stamp the exit block on refusal. VERIFIED (code, E4).

**B7 — LOW — the overlay sits in the model's edit surface; its rewrite is unrecorded.**
The overlay is written after `_prepare` and before the run (`:823`→`:829`→`:841`, correct). It is excluded from `file_changed` (`:861`, which compares the solution only) and from the tamper check (test file only). The model can rewrite it (E5); this has no effect inside the single `opencode run` (E5). However, `overlay_sha256` (`:887`) is the hash at write time, and `_export_latest_session` (`:852`) runs under the possibly rewritten config.
Fix: re-hash after the run, record `overlay_modified`, and restore the overlay before export. VERIFIED (E5).

**B8 — LOW — test quality.**
These would pass without the fix or test their own stubs: `test_pin_stays_at_1_18_30` (tests `:27`; the constant was unchanged); `test_overlay_overrides_nothing_but_the_seed…` (`:95`), which asserts the semantics of the test's own `_deep_merge` (`:79`), not opencode's; `test_opencode_env_puts…` (`:60`, see B4); the overlay-check tests, which monkeypatch `subprocess.run` globally with ideal JSON; `_oc_probe_setup`, which stubs `_assert_overlay_resolved` in every M50 wiring test (`test_m50_entrypoints.py`, one new ordering test only).
Missing tests: resume / seed-base mismatch / pre-C121 manifest (B1); unregistered model (B2); ancestor instruction files (B3); bare-name fallback (B4); a mid-session overlay rewrite (B7).

**B9 — LOW — docs accuracy.**
- `docs/lab-notebook.md:4428`: "Rows are relabelled 'unseeded (server default seed)'" is false. No result row changed (grep of `benchmark/results`); the labels exist only in README/campaign-results (main `a7cffc8`).
- `:4445` "may have carried": `~/.claude/CLAUDE.md` predates M53/M55 (mtime 2026-09-08), and v1 loads it without R8 (E6). Say "did carry, unless loading failed", and add `~/AGENTS.md` (B3).
- "reload control proved nothing" is overstated. All sessions ran at seed 0, so the reload control was a valid same-seed reload comparison. What is missing is the distinct-seed contrast (ASSUMPTION/interpretation).
- `docs/specs/m55-polyglot-gap.md:13` still says "distinct paired seed schedules" with no annotation (only `:10` is annotated).
- `docs/qualify-a-model.md:694`: the invocation lacks the now-required `--seed-base`.
- AC1 "sha recorded in the … manifest" is not done at `b9b4e41`.
- Seed claims VERIFIED: `DEFAULT_SEED` (fork `mlx_vlm/server/schemas.py:810`, `generate/dispatch.py:108`); AgentBench `benchmark/bench/run_agentbench_os.py:1077` (base 0).

**B10 — INFO — AGENTS.md residuals.**
(a) AgentBench's base-0 schedule violates "distinct paired schedules" for agentic chains. It is documented, but no fix is queued; it needs its own proposal.
(b) `benchmark/bench/session_cache_probe.py:97` spawns bare `opencode`, which is now brew v2 (no `--dir`/`--pure`); it needs its own proposal.
(c) A pre-M50 stat of the pinned binary (the B4 fix) is a read before the check. It is in the same class as resolving `config.sh`, but the operator should ratify it next to C114.
(d) The branch is based on `597f908`. `git diff main..c121` shows main's later commits reversed (C123 entry, PLAN M59, handoff, C115 note). Merge the branch; do not apply the two-dot patch.

**B11 — INFO — M50 ordering (challenge 1).**
`os.environ.setdefault("STACK_WORKDIR")` (`:720`), `_opencode_bin_if_known` and the PATH edit do no I/O. Nothing new is read or written before the check, except which binary the discovery executes (B4). VERIFIED.

**Seeds (challenge 3).**
- `sample_seed(f"{lang}/{name}", 0, base)` (`:827-828`, `benchmark/bench/rowschema.py:63`) is distinct per item and per base, and reproducible: a rerun of an item reuses the same seed. The tests cover this. VERIFIED.
- `sample` is always 0. VERIFIED.
- The same seed is sent on every turn of a session. This is a design property, not a defect.

## Re-check at `d91ac6b` (by reading code, plus 132 passing tests)

- B1 FIXED: `_check_resume` (`run_opencode_probe.py:986` @d91ac6b) checks seed_base, policy, bin and version, refuses pre-C121 manifests and skips recorded keys; `provenance.scaffold_policy_of` is wired into `compare` and `is_compatible`. Residual: `opencode_config_sha256` and `overlay_schema` are not in the resume identity.
- B4 FIXED: `_require_opencode_bin` before discovery (`:778` @d91ac6b); the absolute binary is used on every spawn, provenance included.
- B5 FIXED: the receipt is bound to exe/config/test sha. Residual: it still proves the repo config, not the global config.
- B6 PARTLY FIXED: rc≠0 is now rejected. Still open: two calls per item, no exit stamp on refusal.
- AC1 manifest sha: done (`overlay_sha256_by_item`).
- **OPEN:** B2 (`:488` @d91ac6b still checks only the seed); **B3** (`:201`, `:508` @d91ac6b unchanged); B7 (`:914`); B8 (for B2, B3 and B7); B9 (`docs/lab-notebook.md:4428`, `:4445`; `m55:13`; `qualify-a-model.md:694`; and open-questions C121 now says past exposure is "unobservable" while E6 shows the mechanism is live); B10 (a)–(c).
