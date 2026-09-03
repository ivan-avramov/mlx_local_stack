# C47 — serving-path tree hash replaces commit-sha refusal (spec, 2026-09-03)

Problem: the fingerprint's `"code"` key is the raw submodule commit sha (`provenance._git_shas`,
`config_fingerprint`, `compare.py` DEPLOYED CODE block). Every fork commit refuses pairing with
earlier rows, including tool-only commits never imported by the server (e.g. `split_mtp.py`, the
MTP checkpoint splitter). Fix: fingerprint the SERVING PATH tree, not the whole commit — commit
shas stay recorded (for audit / a downgraded warning), but stop being the refusal key.

## 1. `serving_path_hash(submodule_dir, commit) -> str | None` (provenance.py)

- Root of the tree to hash: `mlx_vlm` for a `src/mlx-vlm`-named `submodule_dir`, `src` for a
  `src/mlx-serve`-named one (matched on `os.path.basename`). Unknown submodule name -> `None`.
- `git -C <submodule_dir> ls-tree -r <commit> -- <root>`, invoked with an explicit `-C`, never CWD.
- sha256 over the **sorted** `"<path>\t<blob-sha>"` lines (parsed from ls-tree's
  `<mode> <type> <sha>\t<path>` output), after dropping excluded paths.
- Exclusions (mlx-vlm root only) — module-level constants, one line per entry naming why it's
  tool-only: `mlx_vlm/tests/`, `mlx_vlm/evals/`, `mlx_vlm/trainer/` (dirs); `mlx_vlm/lora.py`,
  `mlx_vlm/split_mtp.py`, `mlx_vlm/convert.py`, `mlx_vlm/chat.py`, `mlx_vlm/chat_ui.py`,
  `mlx_vlm/LORA.MD`, `mlx_vlm/speculative/drafters/mtp_split.py` (files); the one-level pattern
  `mlx_vlm/speculative/drafters/<any>/split.py` (per-drafter conversion-time splitters — 2026-09-03
  follow-up, operator-verified: imported only by convert.py/split_mtp.py and each other, nothing
  under server/, generate/, models/, or the speculative RUNTIME); any `*.md` anywhere under the
  root. mlx-serve root has no exclusions. A drafter's OTHER files (e.g. its `model.py`, the
  serving-time drafter head) are NOT excluded.
- FIX-4 (2026-09-03 verifier round, operator-ruled): dependency PINS are output-relevant (the
  pinned mlx version) and must not be hash-inert. Extra ls-tree pathspecs, alongside the root,
  passed as-is (git silently omits one that doesn't exist at `commit`, no pre-check needed):
  `pyproject.toml`, `requirements.txt`, `uv.lock` for `src/mlx-vlm`; `pyproject.toml`, `uv.lock`
  for `src/mlx-serve`. These are top-level, never under `mlx_vlm/`, so no exclusion applies to
  them. An unrelated top-level file (e.g. `README.md`) stays inert — it is simply not requested.
- Never raises: bad commit / not a git dir / git missing -> `None`.

## 2. `_git_shas()` gains `"serving_path"`

`{"src/mlx-vlm": hash|None, "src/mlx-serve": hash|None}`, computed at each submodule's
**currently checked-out worktree HEAD** via a dedicated `git -C <sub> rev-parse HEAD` call, not
by reusing the `submodules` block's `git submodule status` parse. Note: `git submodule status`
ALSO reports the checked-out worktree sha, not the parent's raw recorded pointer (that pointer is
`git ls-tree HEAD -- <sub>` in the parent, which can legitimately differ from a pinned worktree —
the real case this exists for). The dedicated call is for robustness (no dependence on
`submodule status`'s text format, and it still works for a directory that isn't a registered
submodule at all), not because the two sources disagree in the common case.

## 3. `FINGERPRINT_VERSION` 4 -> 5

- v5's `config_fingerprint`: at `version >= 5`, `"code"` is the manifest's native
  `git.serving_path` dict instead of the commit-sha dict. Below v5, unchanged.
- `derive_serving_path(manifest, repo_root=None) -> dict`: for a pre-v5 manifest, recompute the
  hashes from its recorded `git.submodules` commit shas via `serving_path_hash`. `None` per key
  when the commit is absent from the manifest or not present in the local clone.
- `is_compatible`: still negotiates at `min(version)` for every other key. For `"code"`
  specifically, if BOTH sides can produce a serving-path hash for a given submodule key (native
  v5, or derived) — even when the negotiated version is < 5 — that hash decides compatibility for
  that key instead of the commit sha. When NEITHER side can produce a hash, fall back to the
  recorded commit sha (FIX-1, 2026-09-03 verifier round: this closes a hole where two native-v5
  manifests with no hash on either side and DIFFERENT commit shas compared as compatible while
  `compare.py`'s own commit-sha fallback, §4, refuses the same pair). A key where a hash is
  available on exactly ONE side is genuinely asymmetric and stays incompatible.

## 4. `compare.py` DEPLOYED CODE block

Per submodule key: get both sides' serving-path hash (native if `fingerprint_version >= 5`, else
`derive_serving_path`).
- both present, different -> `_refuse`, naming the key and the two short hashes, citing C47.
- both present, equal, but recorded commit shas differ -> `warnings.append("commit shas differ
  (<a> vs <b>) but the serving path is byte-identical — pairable (C47)")`.
- a hash unavailable on either side -> fall back to exactly today's commit-sha refusal/warning.

## 5. Tests

New `bench/tests/test_serving_path.py` (temp git repos, no network, no real submodule mutation):
hash stability + change-on-content-change; exclusion list is a no-op for splitter/tests-only
commits; pinned-worktree HEAD (differs from parent pointer) drives the hash; `derive_serving_path`
on a v3-shaped manifest; compare refuse/warn/fallback matrix; `is_compatible` v5-v5 (equal hash,
different sha -> True) and v5-vs-v3-derived; `serving_path_hash` on a bad commit -> `None`, no
raise. Every existing fingerprint/compare test stays green.

## 6. Live sanity check (read-only, real `src/mlx-vlm`)

`serving_path_hash` on the real submodule for `57177a21` vs `7330d3a6` (the splitter-only bump —
touches only `mlx_vlm/speculative/drafters/mtp_split.py` and `mlx_vlm/tests/test_models.py`, both
excluded) expected EQUAL; `57177a21` vs `ab5708a` (`fix(generate): per-request seeds reach the
cached-path sampler (C26)` — touches `mlx_vlm/generate/ar.py` and `mlx_vlm/server/generation.py`,
real serving files) expected to DIFFER. (FIX-2, 2026-09-03 verifier round: the spec originally
named `f5fff9b5` as the DIFFER example; measured live, that pair is actually EQUAL — the complete
diff between them under `mlx_vlm/` is exactly the same three now-excluded files as the
`7330d3a6` pair, i.e. that whole commit range is splitter/test churn.)
