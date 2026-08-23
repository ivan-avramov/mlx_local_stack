# ARCHIVED: two-box era procedures (M4 Pro driver + M5 Max worker, ended 2026-08-17)

**Status: HISTORICAL.** Since 2026-08-17 the M5 Max 64 GB is the sole box (driver + worker) and
none of the procedures below are live. This file preserves them verbatim from AGENTS.md
(moved 2026-08-23, token-budget cleanup) because (a) the git-only-transport rule and its
paid-for rationale become live again the moment a second box joins, and (b) pre-2026-08-11
results in the corpus were produced under these topologies and their caveats.

## Topology history

- **BOX TOPOLOGY CHANGED 2026-08-11 — the M2 Max 64GB laptop is GONE.** Local became an **M4 Pro, 48GB**. Every `M2` reference in older docs predates that swap and is HISTORICAL.
- M4 Pro = local 48GB **DRIVER** laptop (repo `$STACK_REPO`). Co-resident with the AI session (~22GB) it had ~26GB headroom, so it hosted **NO campaign models at all**. Driver-only work: harness dev, grading (`grade`/`grade_evalplus`), orchestration, docs. Also a different chip class (far less memory bandwidth than any Max part), so **NEVER** a valid speed-comparison box even ignoring RAM.
- Pre-2026-08-11 `M2` results are HISTORICAL and NOT re-measurable: the apples-to-apples rule bars cross-box baselines and that box no longer exists.
- M5 Max = remote 64GB **WORKER** box (all model runs). `ssh $REMOTE_HOST` (user `$REMOTE_USER`, repo `$REMOTE_REPO`). Non-interactive ssh has a bare PATH (`/usr/bin:/bin:/usr/sbin:/sbin`) — prepend every remote cmd with `export PATH=/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH`. **`/usr/local/bin` is required**: docker/OrbStack lives there, and omitting it makes `docker` look MISSING when it is installed and running. M5 has no `.env`, but an `HF_TOKEN` is exported in `~/.zshrc` — non-interactive ssh does NOT source `.zshrc`, so cached models load fine token-less BUT downloading a new/ungated model unauthenticated hits HF rate limits; load it first with `export HF_TOKEN="$(zsh -ic 'print -rn -- $HF_TOKEN' 2>/dev/null)"` (export it, don't pass via argv; never print/commit the value). Docker on M5 = 29.4.0, aarch64 server, with working `linux/amd64` emulation → `grade_evalplus` can run on EITHER box.
- **The 2026-08-13 "single worker" consequence:** ALL model runs went to M5 — the old parallel "M2 quality + M5 speed" box-split died with the M2.

## GIT IS THE ONLY CROSS-BOX TRANSPORT (operator instruction 2026-08-13)

Any code, script, config or doc that must exist on more than one box travels **commit → push →
`git fetch` + `git merge --ff-only`**, never `scp`. Rationale, paid for twice: a whole Tier-0
grid launch died `rc=2` on every cell because 14 local commits were not on M5, and the box then
accumulated ~12 scp'd files that made "what is actually running here?" unanswerable — including
a stray `benchmark/bench/test_convergence.py` scp'd to the wrong directory, a same-basename
duplicate that can break pytest collection. scp leaves no provenance, no history, and no way to
diff a box against a known state.

- **The one sanctioned exception** is a THROWAWAY diagnostic that will never be relied on twice (a one-off probe script under `/tmp`). It must live in `/tmp`, never in the repo tree, so it cannot masquerade as committed code. Anything that produces a recorded result gets committed first.
- **The dirty-registry case is not an obstacle** (verified 2026-08-13, used 4×): because incoming commits do not touch `main_models.yaml`, `git fetch && git merge --ff-only` succeeds with the registry permanently modified. Do NOT `git checkout` it.
- **Procedure when a box has drifted:** (1) `cp -p main_models.yaml /tmp/…` to back up the intentional dirt; (2) **checksum every locally-modified file against the committed version** (`git show HEAD:<path> | md5 -q` vs the box's `md5 -q`) and only discard those that match — never `git checkout -- .` on faith, or unique work is destroyed silently; (3) remove untracked files the merge will deliver; (4) `git merge --ff-only`; (5) restore the registry backup and verify by md5; (6) `git submodule update --force` only if the pointers actually moved.
- ⚠️ **A TOOL/SSH TIMEOUT KILLS THE LOCAL CLIENT, NOT THE REMOTE JOB.** A `run.py generate` probe whose ssh call timed out at 2 min kept running remotely for ~13 more minutes, appending rows unmonitored and presenting as an orphaned generation. Never infer that remote work stopped — verify with `pgrep` and kill BY PID. Launch anything that may outlive the call with `nohup … &`. And `--chunks 0` is NOT a dry run: it generates. To inspect resume state, read `done_ids` from the jsonl.
- ⚠️ zsh does NOT word-split unquoted variables, so `for f in $FILES` runs ONCE with the whole string. Iterate with `while IFS= read -r f; do … done < file`, and use `ssh -n` inside loops.
- Syncing M5 (verified 2026-08-11): its `main_models.yaml` was CLEAN and committed, so a sync was just `git fetch origin main && git merge --ff-only origin/main`, plus `git submodule update --force` when the submodule pointers actually moved. (HISTORICAL hazard: M5 once carried an UNCOMMITTED local registry entry, and with `pull.rebase=true` a plain `git pull` ABORTED on the dirty registry. If a box ever re-adds a local `hf_path`, that hazard returns — and never commit local paths.)

## Two-box shell/ssh traps

- **Single quotes inside a single-quoted ssh command terminate the quote.** `a['x']` breaks; two heredocs were mangled this way. **Pipe the program to the remote interpreter over ssh stdin** (`ssh HOST 'cd REPO && ./.venv-bench/bin/python -' <<'PY'`) rather than writing a file first — verified 2026-08-16 after a heredoc transferred as **0 bytes** and the "prep" silently did nothing.
- **The tool sandbox loses mDNS, and the worker alias resolves via `.local`.** `DNSServiceQueryRecord failed -65563` reads like a worker outage and is not. Use `dangerouslyDisableSandbox: true` for ssh calls.
