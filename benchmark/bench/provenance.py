"""Provenance manifest — stamp every results file with the EXACT config it was produced
under, so results can never be silently compared across boxes / code versions / quant or
KV configs. This enforces the apples-to-apples rule and powers the quality-vs-bits study
(each result is tied to its effective bits-per-weight + KV config + sampling).

Manifests are written next to results (which are gitignored), so the box label here never
reaches the public repo; we still prefer an explicit MLX_BOX label over the raw hostname.
"""
import hashlib
import json
import os
import re
import subprocess
import time

import yaml

from . import generate, model_params, quant_info
from . import paths


def _home_normalized(path):
    """O34: emit hf_path in $HOME-form so manifests carry no absolute home path.

    The committed corpus manifests are $HOME-form (hand-sanitized, pre-O34); the writer must
    produce the same string, or every resume of a local-hf_path model restamps the absolute
    path back in — a PII leak the pre-commit hook has to catch, and a false STALE (2026-08-20:
    a byte-identical relaunch was flagged as a config change purely on path form)."""
    if not isinstance(path, str):
        return path
    home = os.path.expanduser("~")
    if path == home or path.startswith(home + os.sep):
        return "$HOME" + path[len(home):]
    return path


def registry_kv(model: str, registry_path: str | None = None):
    """KV + path config for ``model`` from a main_models.yaml-style registry, or None.

    ``registry_path=None`` resolves to the repo's `main_models.yaml` independent of the CWD.
    Resolved HERE so every caller — including the three public entry points that now default to
    None — gets it. A bare "main_models.yaml" default meant provenance was silently SKIPPED from
    any CWD but the repo root, so rows carried no sampling/APC fingerprint and --clean-stale could
    not detect config drift. See bench/paths.py.
    """
    registry_path = str(paths.registry_path()) if registry_path is None else registry_path
    with open(registry_path) as f:
        doc = yaml.safe_load(f)
    entries = doc.get("models", doc) if isinstance(doc, dict) else doc
    for e in entries or []:
        if isinstance(e, dict) and e.get("name") == model:
            return {
                "hf_path": _home_normalized(e.get("hf_path")),
                "kv_bits": e.get("kv_bits", 0),
                "kv_quant_scheme": e.get("kv_quant_scheme"),
                "quantized_kv_start": e.get("quantized_kv_start"),
                "prefill_step_size": e.get("prefill_step_size"),
                "max_kv_cache_size": e.get("max_kv_cache_size"),
                # RECORDED, never resume-fingerprinted: prealloc moved wall-clock measurably
                # (24.7 vs 27.8 s in the 2026-08-14 OFAT) but is text-invariant, so `compare`
                # refuses HARDWARE metrics across it while a prealloc change must not let
                # --clean-stale delete quality rows.
                "kv_prealloc_tokens": e.get("kv_prealloc_tokens"),
                # Retirement changes resource use, not stored KV values: record it for
                # hardware comparisons without invalidating resumable quality rows.
                "cache_session_shrink": e.get("cache_session_shrink"),
                # "" (an operator may write it to document 'off' explicitly -- it's also
                # ModelConfig's own mlx-serve default) normalizes to None, matching an absent
                # key, so a documented-off entry fingerprints identically to an undeclared one.
                "moe_expand": e.get("moe_expand") or None,
            }
    return None


def _worker_cmdline() -> str | None:
    """Best-effort cmdline of the live `mlx_vlm.server` worker — the SERVING truth for draft
    flags (AGENTS.md: verify at the worker cmdline, never the yaml alone). None when no worker
    is observable or the platform/permissions refuse."""
    try:
        import psutil
        for p in psutil.process_iter(["pid", "cmdline"]):
            cmd = " ".join(p.info.get("cmdline") or [])
            if "mlx_vlm.server" in cmd:
                return cmd
    except Exception:  # noqa: BLE001 — best-effort; absent psutil / AccessDenied / gone
        return None
    return None


_DEFAULT_LOOKUP = object()   # sentinel: identify the worker by the mlx_port listener (_worker_argvs)


def registry_draft(model: str, registry_path: str | None = None,
                   worker_lookup=_DEFAULT_LOOKUP) -> dict:
    """Speculative-decoding state for ``model``, NORMALISED so that "off" is an OBSERVATION.

    That normalisation is the whole point of v3. `draft_kind` was already named in
    _FINGERPRINT_RUNTIME from v2 on, and it was inert: nothing populated it, so every manifest
    carried it as absent -> None, and `_runtime_compatible` treats None as an unobserved wildcard.
    Measured 2026-08-16 across the 50 manifests on disk: 37 had no runtime block and 13 carried
    exactly {apc_enabled, apc_source}. NONE carried draft_kind. Meanwhile suffix decoding was ON
    for exactly the two winners and OFF for every other candidate, so every cross-model comparison
    was a (model x serving-path) composite that nothing refused. A declared-but-never-populated
    fingerprint key is worse than an absent one, because it reads as covered.

    So: a registry entry with no `draft_kind` returns "off", never None. "unknown" is reserved for
    genuine ignorance (model absent from the registry, or the registry unreadable), which stays a
    wildcard on the same "never condemn on ignorance" grounds as APC detection.

    `draft_block_size` / `suffix_min_match` are RECORDED for audit but deliberately NOT
    fingerprinted: they are inert when draft_kind is "off", nothing in the campaign has ever varied
    them, and adding them would widen the refusal surface with no measured lever behind it.
    """
    registry_path = str(paths.registry_path()) if registry_path is None else registry_path
    try:
        with open(registry_path) as f:
            doc = yaml.safe_load(f)
    except Exception:  # noqa: BLE001 — never block a run on provenance
        return {"draft_kind": "unknown", "draft_source": "unreadable-registry"}
    entries = doc.get("models", doc) if isinstance(doc, dict) else doc
    for e in entries or []:
        if isinstance(e, dict) and e.get("name") == model:
            ans = {"draft_kind": e.get("draft_kind") or "off",
                   "draft_block_size": e.get("draft_block_size"),
                   "suffix_min_match": e.get("suffix_min_match"),
                   "draft_source": "registry"}
            # C35 tripwire (2026-08-26): the registry of record and the SERVED config can
            # legitimately diverge (bench routers run a draft-stripped overlay), and recording
            # the yaml answer alone stamped `draft_kind: mtp` on a verified draft-OFF run.
            # When a live worker is observably serving THIS model (its `--model` EQUALS the
            # entry's hf_path), its cmdline is the truth: a mismatch REFUSES the run rather
            # than record false provenance on either side. A worker for another model, or no
            # worker at all, says nothing — the yaml answer stands, source "registry".
            argv = _worker_for(e, worker_lookup, doc)    # exact `--model`, mlx_port listener
            if argv is not None:
                served = _flag_value(argv, "--draft-kind") or "off"
                if served != ans["draft_kind"]:
                    raise ServingStateError(
                        f"C35 tripwire: registry {registry_path!r} declares draft_kind="
                        f"{ans['draft_kind']!r} for {model!r} but the live worker serves "
                        f"draft_kind={served!r}. Launch the driver with MLX_SERVE_CONFIG "
                        f"pointed at the served registry/overlay; refusing to record false "
                        f"draft provenance.")
                ans["draft_source"] = "registry+worker"
            return ans
    return {"draft_kind": "unknown", "draft_source": "model-not-in-registry"}


# --------------------------------------------------------- C47: serving-path tree hash (2026-09-03)
# WHY THIS EXISTS. The fingerprint used to refuse on the raw submodule COMMIT sha (_git_shas below),
# so every fork commit — including tool-only ones never imported by the server, e.g. the MTP
# checkpoint splitter `split_mtp.py` — refused pairing with every earlier row. The fix hashes the
# TREE of the paths the server actually imports, excluding the tool-only ones; the commit sha is
# still recorded (compare.py downgrades a sha-only difference to a warning when the tree hash
# matches).
_SERVING_ROOTS = {"mlx-vlm": "mlx_vlm", "mlx-serve": "src"}

# FIX-4 (2026-09-03 verifier round, operator-ruled): dependency PINS are output-relevant (e.g. the
# pinned mlx version changes numerics/behavior exactly like a src change does) and must not be
# hash-inert. Extra top-level ls-tree pathspecs per submodule, alongside its root above — passed
# as-is; `git ls-tree` silently yields no line for one that doesn't exist at `commit`, so no
# existence pre-check is needed. No exclusions apply to these (they are never under `mlx_vlm/`).
_SERVING_EXTRA_PATHS = {
    "mlx-vlm": ("pyproject.toml", "requirements.txt", "uv.lock"),
    "mlx-serve": ("pyproject.toml", "uv.lock"),
}

# Excluded from the mlx-vlm hash — one line each, mechanism-first. mlx-serve has no exclusions.
_SERVING_PATH_EXCLUDE_DIRS = (
    "mlx_vlm/tests/",     # pytest suite; not imported by the server
    "mlx_vlm/evals/",     # offline eval harness (math_vista, mmmu, ...); not imported by the server
    "mlx_vlm/trainer/",   # LoRA/DoRA training code; not imported by the server
)
_SERVING_PATH_EXCLUDE_FILES = (
    "mlx_vlm/lora.py",              # LoRA fine-tuning CLI entry point; not imported by the server
    "mlx_vlm/split_mtp.py",         # MTP-checkpoint splitter tool; not imported by the server (the C47 trigger)
    "mlx_vlm/convert.py",           # weight-conversion CLI; not imported by the server
    "mlx_vlm/chat.py",              # interactive CLI chat tool; not imported by the server
    "mlx_vlm/chat_ui.py",           # gradio chat UI tool; not imported by the server
    "mlx_vlm/LORA.MD",              # docs, not code
    # C47 follow-up (2026-09-03, operator-verified): conversion-time MTP splitter; imported only
    # by convert.py/split_mtp.py (both already excluded above) and by each other — nothing under
    # server/, generate/, models/, or the speculative RUNTIME imports it.
    "mlx_vlm/speculative/drafters/mtp_split.py",
)


def _is_drafter_split_tool(path: str) -> bool:
    """`mlx_vlm/speculative/drafters/<any-one-level>/split.py` — the per-drafter conversion-time
    MTP splitter; imported only by convert.py/split_mtp.py, same as `drafters/mtp_split.py`
    above (C47 follow-up, 2026-09-03, operator-verified). One level only: the drafter's other
    files (e.g. its model.py) ARE the serving-time drafter head and must still move the hash."""
    parts = path.split("/")
    return (len(parts) == 5 and parts[0] == "mlx_vlm" and parts[1] == "speculative"
            and parts[2] == "drafters" and parts[4] == "split.py")


def _serving_path_excluded(path: str) -> bool:
    """True for a path that is present in the submodule tree but never imported by the deployed
    server — docs and mlx-vlm's own tool/eval/train surface. Any `*.md` is excluded too (docs),
    everywhere under the root, not just the explicitly-named `LORA.MD`."""
    if path.endswith(".md"):
        return True
    if path in _SERVING_PATH_EXCLUDE_FILES:
        return True
    if any(path.startswith(d) for d in _SERVING_PATH_EXCLUDE_DIRS):
        return True
    return _is_drafter_split_tool(path)


def serving_path_hash(submodule_dir, commit) -> str | None:
    """sha256 over the sorted `"<path>\\t<blob-sha>"` lines of the SERVING tree at `commit` —
    `mlx_vlm/` for a `.../mlx-vlm` submodule_dir, `src/` for a `.../mlx-serve` one (matched on
    `os.path.basename`; unknown name -> None), excluding the tool-only paths above, PLUS each
    submodule's dependency-pin files (`_SERVING_EXTRA_PATHS`, FIX-4) — a pinned mlx version is
    output-relevant exactly like a source change.

    Invoked with an explicit `git -C <submodule_dir>`, never CWD (the caller may be running from
    anywhere). Never raises: an unreadable submodule_dir, a missing/unknown `commit`, or no git on
    PATH all return None — provenance gathering must not block a run.
    """
    name = os.path.basename(os.path.normpath(str(submodule_dir)))
    root = _SERVING_ROOTS.get(name)
    if root is None or not commit:
        return None
    pathspecs = [root, *_SERVING_EXTRA_PATHS.get(name, ())]
    try:
        # `git -C <dir>` happily WALKS UP to an enclosing repo when <dir> has no `.git` of its own
        # (an uninitialized submodule directory) — silently resolving `commit`/pathspecs against
        # the WRONG repo root instead of failing. Refuse that: submodule_dir must be its own
        # top-level, exactly like a real (initialized) mlx-vlm/mlx-serve submodule always is.
        top = subprocess.check_output(
            ["git", "-C", str(submodule_dir), "rev-parse", "--show-toplevel"],
            text=True, stderr=subprocess.DEVNULL).strip()
        if os.path.realpath(top) != os.path.realpath(str(submodule_dir)):
            return None
        out = subprocess.check_output(
            ["git", "-C", str(submodule_dir), "ls-tree", "-r", commit, "--", *pathspecs],
            text=True, stderr=subprocess.DEVNULL)
    except Exception:  # noqa: BLE001 — bad commit / not a git dir / no git: never raise
        return None
    lines = []
    for entry in out.splitlines():
        meta, sep, path = entry.partition("\t")
        if not sep or not path:
            continue
        if root == "mlx_vlm" and _serving_path_excluded(path):
            continue
        blob_sha = meta.split()[-1]
        lines.append(f"{path}\t{blob_sha}")
    lines.sort()
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def derive_serving_path(manifest, repo_root=None) -> dict:
    """Serving-path hashes for a manifest whose `git` block predates v5 (no native
    `git.serving_path`), recomputed from its recorded `git.submodules` commit shas.

    `{key: hash|None}` for `src/mlx-vlm` and `src/mlx-serve`. A key is None when the manifest
    never recorded a commit for it, or when `serving_path_hash` cannot resolve it locally (the
    commit is not present in the local clone) — never raises.
    """
    root = str(paths.repo_root()) if repo_root is None else str(repo_root)
    subs = ((manifest or {}).get("git") or {}).get("submodules") or {}
    out = {}
    for key in ("src/mlx-vlm", "src/mlx-serve"):
        commit = subs.get(key)
        out[key] = serving_path_hash(os.path.join(root, key), commit) if commit else None
    return out


# The output-determining slice of a manifest. If any of these differ, existing results were
# produced under a different distribution and CANNOT be mixed with new ones via resume.
_FINGERPRINT_SAMPLING = ("temperature", "top_p", "top_k", "min_p", "presence_penalty",
                         "repetition_penalty", "thinking_budget", "max_tokens", "enable_thinking",
                         # depth_tokens (D9, 2026-08-18) is prompt-side, not a server knob, but it
                         # is OUTPUT-DETERMINING in the strongest sense: it changes what we asked.
                         "depth_tokens",
                         # reasoning_effort (M24, 2026-08-23): the Qwen3.8-27B family's chat
                         # template injects an effort instruction from it — it changes what we
                         # asked, exactly like depth_tokens. Absent = the template's own default
                         # (xhigh there), which is every pre-M24 row, so absent-on-both compares
                         # equal and the corpus is not condemned (the depth_tokens precedent; no
                         # version bump needed).
                         "reasoning_effort")

# v2 additions: RUNTIME knobs that change results without touching sampling.
#   apc_enabled  — prefix caching (runserver.sh sets it; the AGENTS.md bench recipe does not)
#   draft_kind   — suffix/speculative decoding
#   max_turns / deadline_s / loop_guard / client / edit_format — the agentic-axis knobs
# `samples` is deliberately ABSENT: drawing k samples does not change the distribution each
# sample comes from, and including it would mark every existing single-sample result stale.
_FINGERPRINT_RUNTIME = ("apc_enabled", "draft_kind", "max_turns", "deadline_s", "loop_guard",
                        "client", "edit_format")

# v4 additions (2026-08-17, V3 guard parity): the kv/identity knobs the verifier's audit found
# recorded-but-unfingerprinted. All resolve from the registry entry / manifest kv block:
#   hf_path            — WEIGHTS IDENTITY. A changed path means changed weights; a same-weights
#                        local->hub migration (the Qwen3.8-27B interim) deliberately reads stale,
#                        which is the cheap direction (screening rows re-run in minutes).
#   kv_quant_scheme    — uniform vs turboquant are different KV numerics -> different text.
#   quantized_kv_start — same mechanism.
#   prefill_step_size  — chunked-prefill numerics on Metal are not proven text-invariant (the
#                        suffix lesson: kernel batch shape flips bf16 argmaxes), so resume is
#                        strict about it; `compare` only WARNS for quality across it.
# `kv_prealloc_tokens` is deliberately ABSENT (text-invariant; see registry_kv).
# moe_expand — MoE routing expansion (M34) changes the text.
_FINGERPRINT_KV_EXTRA = ("hf_path", "kv_quant_scheme", "quantized_kv_start", "prefill_step_size",
                         "moe_expand")

# v3 (2026-08-16): draft/suffix state is POPULATED, not merely named. See registry_draft().
# v4 (2026-08-17): the kv_extra slice above joins the resume guard.
# v5 (C47, 2026-09-03): the "code" key becomes the serving-path TREE hash (serving_path_hash)
# instead of the raw submodule commit sha — a tool-only fork commit (never imported by the
# server) no longer refuses pairing with earlier rows. See is_compatible for the cross-version
# override that lets this apply even when the negotiated version is < 5.
# v6 (M48, 2026-09-28): the served session-retention state (`--cache-session-retain-prompt-end`)
# joins the runtime slice. Prompt-end retention + canonical assistant retire changes WHICH prefix is
# served from cache vs re-prefilled; bf16 prefill-from-cache vs re-prefill is not proven
# text-invariant (the prefill_step_size lesson), so rows at different states never pool. Observed
# from the worker cmdline, else the fork's own default (same src/mlx-vlm the worker serves), else
# "unknown" (wildcard). See session_retention_state().
# v7 (M57, 2026-10-04): the fused-attention dispatch policy (`--attention-policy`, registry
# `attention_policy`) joins the runtime slice. It selects WHICH attention kernel runs, so rows at
# different policies never pool and never compare. Observed from the worker cmdline (flag absent
# = "auto"), else the registry; a worker/registry disagreement refuses (registry_attention_policy).
# Manifests < v7 compare as "auto" (attention_policy_of), so a v7 `fused_v1` row never resumes
# onto a pre-v7 row even though the negotiated min-version slice omits the key.
# v8 (M58, 2026-10-06): the MTP verification-scan policy (`--mtp-verify-scan` [+ `--mtp-verify-ab`],
# registry `mtp_verify_scan`) joins the runtime slice with the values `per_query`, `joint_v1`,
# `joint_v1+ab` (AB is a distinct served mode: gate rows only, never from the registry). It selects
# WHICH attention call the verifier makes, so rows at different values never pool and never compare.
# Controls carry PER-CONTROL introduction versions (_SERVING_CONTROLS): a pre-v8 manifest reads
# `per_query` / "default-pre-v8" for it, so the v7 (M57) rows on disk stay compatible with a v8
# `per_query` row and incompatible with a v8 `joint_v1` row. A v8 manifest with a missing or
# unrecognised value reads "unknown" and refuses everywhere.
FINGERPRINT_VERSION = 8


def config_fingerprint(manifest, version: int | None = None):
    """The comparable slice of a manifest, at fingerprint `version`.

    v1 = sampling profile + key sampling params + KV bits (what the pre-v2 harness compared).
    v2 = v1 + the runtime block.
    v3 = v2, with the runtime block's `draft_kind` actually populated from the registry (it was
         declared in v2 and never written, which made it a wildcard on every row).

    `version=None` means "this manifest's own version". Returns None for a missing manifest
    (unknown provenance).
    """
    if not manifest:
        return None
    if version is None:
        version = manifest.get("fingerprint_version", 1)
    s = manifest.get("sampling") or {}
    kv = manifest.get("kv") or {}
    fp = {
        "sampling_profile": manifest.get("sampling_profile"),
        "sampling": {k: s.get(k) for k in _FINGERPRINT_SAMPLING},
        "kv_bits": kv.get("kv_bits"),
        # max_kv_cache_size is OUTPUT-DETERMINING, proven twice on 2026-08-14:
        #  - it sets the effective thinking budget. The server clamps thinking_budget to
        #    0.8 * (max_kv_cache_size - prompt), so at 65536 a declared 81920 budget was really
        #    ~52390 and reasoning was externally cut short. Same request, different length limit.
        #  - it changed throughput catastrophically (zero completions in 19.5 min at a 262144
        #    prealloc vs ~107 tok/s at 131072, same box/model/sampling).
        # Without it here, `--clean-stale` could not see a cap change and `done_ids` resume would
        # silently POOL rows generated under different effective budgets. Absent on both sides
        # (pre-manifest-era rows) compares equal, so no historical result is condemned.
        "max_kv_cache_size": kv.get("max_kv_cache_size"),
        # The DEPLOYED CODE is output-determining, proven 2026-08-14: bumping src/mlx-vlm
        # 8b7100b8 -> 0c1c8b17 (an upstream merge) changed a matched item's generation from 2475 to
        # 3526 completion tokens with an IDENTICAL prompt and sampling, deterministically (3/3). The
        # model implementation and the sampler were byte-unchanged; server/generation.py,
        # models/cache.py and utils.py were not.
        #
        # Without this, `--clean-stale` judged pre-bump rows compatible, done_ids skipped every item,
        # and a re-baseline job reported DONE having generated nothing — while any partial run would
        # have pooled two code versions silently. mlx-serve counts too: it builds the worker command
        # line (kv flags, generation-defaults, draft-kind), so a change there alters what the worker
        # is asked to do. Absent on both sides (pre-provenance rows) compares equal, so no historical
        # result is condemned.
        #
        # v5 (C47): at version >= 5 this becomes the serving-path TREE hash (below) instead of the
        # raw commit sha — a tool-only fork commit (e.g. the MTP splitter) no longer differs here.
        "code": {k: ((manifest.get("git") or {}).get("submodules") or {}).get(k)
                 for k in ("src/mlx-vlm", "src/mlx-serve")},
    }
    if version >= 2:
        r = manifest.get("runtime") or {}
        fp["runtime"] = {k: r.get(k) for k in _FINGERPRINT_RUNTIME}
    if version >= 4:
        fp["kv_extra"] = {k: kv.get(k) for k in _FINGERPRINT_KV_EXTRA}
    if version >= 5:
        gsp = (manifest.get("git") or {}).get("serving_path") or {}
        fp["code"] = {k: gsp.get(k) for k in ("src/mlx-vlm", "src/mlx-serve")}
    if version >= 6:
        fp.setdefault("runtime", {})["session_retain_prompt_end"] = r.get("session_retain_prompt_end")
    for k, (intro, _default) in _SERVING_CONTROLS.items():
        if version >= intro:
            fp.setdefault("runtime", {})[k] = control_of(manifest, k)[0]
    return fp


def is_compatible(existing, current) -> bool:
    """True iff `existing` results were produced under the same output-determining config as
    `current`. A missing/unparseable existing manifest is incompatible (unknown provenance must
    not be silently resumed).

    Comparison happens at the LOWEST version the two manifests both declare. That is what keeps
    v2 from being destructive: every result already on disk is v1 (no runtime block), so a v2
    harness compares them on the v1 slice — bit-for-bit the old behaviour — instead of finding a
    universal mismatch and letting `--clean-stale` delete the lot. Two v2 manifests compare on
    the full set, so the guard is strictly stronger for everything produced from here on.
    """
    if existing is None:
        return False
    v = min(existing.get("fingerprint_version", 1), current.get("fingerprint_version", 1))
    a, b = config_fingerprint(existing, v), config_fingerprint(current, v)
    _overlay_serving_path_code(existing, current, a, b)
    # Serving controls (M57 S1/S2, M58 per-control versions): the negotiated slice may omit them
    # (v below a control's introduction), but a row older than that IS the default, so they are
    # compared on EVERY path (incl. the v1 early return) and STRICTLY: an unresolved
    # ("unknown"/absent/unrecognised) value on a row new enough to carry it never pools with
    # anything, itself included (T2: nothing verifies run identity, so there is no same-run
    # exception).
    for k in _SERVING_CONTROLS:
        va, vb = control_of(existing, k)[0], control_of(current, k)[0]
        if va != vb or va == "unknown":     # T2: unresolved is incompatible with EVERYTHING
            return False
    if v < 2:
        return a == b
    ra, rb = a.pop("runtime", {}), b.pop("runtime", {})
    for k in _SERVING_CONTROLS:
        ra.pop(k, None)
        rb.pop(k, None)
    return a == b and _runtime_compatible(ra, rb)


def serving_path_for(manifest: dict) -> dict:
    """Native `git.serving_path` for a v5 manifest, else derived from its recorded commit shas."""
    if (manifest.get("fingerprint_version") or 1) >= 5:
        return (manifest.get("git") or {}).get("serving_path") or {}
    return derive_serving_path(manifest)


def _overlay_serving_path_code(existing: dict, current: dict, a: dict, b: dict) -> None:
    """C47: prefer the serving-path hash for the `"code"` key whenever BOTH sides can produce
    one for a given submodule (native v5, or derived from a recorded commit sha) — even when the
    negotiated fingerprint version `v` above is < 5, which is exactly the mixed-version case an
    old-vs-new comparison hits every day right after the bump. Mutates `a["code"]`/`b["code"]`
    in place, per key.

    When NEITHER side can produce a hash for a key, fall back to the raw recorded commit sha
    (spec §3 last sentence; FIX-1, 2026-09-03 verifier round). Measured hole this closes: two
    native v5 manifests with no hash on either side and DIFFERENT commit shas used to compare
    "code" as None==None -> equal, while `compare.py`'s DEPLOYED CODE block refuses that exact
    same pair via its own commit-sha fallback (spec §4) — the two seams disagreed on one manifest
    pair. A key where exactly ONE side has a hash is left as `config_fingerprint` already set it
    (genuinely asymmetric information, already incompatible there)."""
    sa, sb = serving_path_for(existing), serving_path_for(current)
    suba = ((existing.get("git") or {}).get("submodules") or {})
    subb = ((current.get("git") or {}).get("submodules") or {})
    for key in ("src/mlx-vlm", "src/mlx-serve"):
        ha, hb = sa.get(key), sb.get(key)
        if ha is not None and hb is not None:
            a["code"][key] = ha
            b["code"][key] = hb
        elif ha is None and hb is None:
            a["code"][key] = suba.get(key)
            b["code"][key] = subb.get(key)


def _unobserved(value) -> bool:
    """True for a runtime value that was never observed: "unknown" (detection failed) or None
    (knob not applicable to this axis)."""
    return value is None or value == "unknown"


def _runtime_compatible(a: dict, b: dict) -> bool:
    """Runtime-slice comparison where an UNOBSERVED value on either side is a wildcard.

    This asymmetry with the sampling slice is deliberate and load-bearing. APC state is detected
    best-effort by scanning the router process, so it can legitimately come back "unknown" on one
    run and "1" on the next. Under strict equality that flip would make an existing results file
    report STALE, and `--clean-stale` would DELETE it — losing real generation to a detection
    failure. Results are gitignored and unversioned, so that is unrecoverable.

    Refusing to condemn on ignorance is the safe direction: the worst case is resuming across a
    knob we could not observe, and the manifest still records `apc_source: "unknown"` so the row
    is auditable and reporting can flag it. Two OBSERVED, DIFFERING values are still incompatible.
    """
    for k in set(a) | set(b):
        va, vb = a.get(k), b.get(k)
        if _unobserved(va) or _unobserved(vb):
            continue
        if va != vb:
            return False
    return True


# --------------------------------------------------------------- APC state (recorded, not measured)
def _router_env() -> dict | None:
    """Best-effort read of the live router process's environment. APC is a serving-layer knob
    set on the ROUTER, not in the harness process, so it cannot be read from our own env.
    Returns None when no router is found or the platform/permissions refuse."""
    try:
        import psutil
        for p in psutil.process_iter(["pid", "cmdline"]):
            cmd = " ".join(p.info.get("cmdline") or [])
            if "mlx-serve" in cmd or "mlx_vlm.server" in cmd:
                return p.environ()
    except Exception:  # noqa: BLE001 — best-effort; absent psutil / AccessDenied / gone
        return None
    return None


def apc_state(process_env_lookup=_router_env) -> dict:
    """Whether prefix caching was on for this run: {"apc_enabled": "1"|"0"|"unknown", "source"}.

    APC is a serving-layer cache, NOT a model capability, so it is never benchmarked — but it
    must be recorded, because `runserver.sh` enables it while the AGENTS.md benchmarking recipe
    does not, which silently made benchmark runs differ from the daily driver on a knob worth
    34-147x on TTFT.

    Precedence: an explicit `MLX_BENCH_APC` declaration by the operator, else the router
    process's own env (absent APC_ENABLED there means OFF), else "unknown" — reported honestly
    rather than guessed.
    """
    declared = os.environ.get("MLX_BENCH_APC")
    if declared is not None:
        return {"apc_enabled": str(declared), "source": "env"}
    try:
        env = process_env_lookup()
    except Exception:  # noqa: BLE001 — never block a run on provenance
        env = None
    if isinstance(env, dict):
        return {"apc_enabled": str(env.get("APC_ENABLED", "0")), "source": "process"}
    return {"apc_enabled": "unknown", "source": "unknown"}


def session_retention_state(worker_lookup=_worker_cmdline) -> dict:
    """M48 served state: {"session_retain_prompt_end": "on"|"off"|"unknown", "session_retain_source"}.

    Precedence: the live worker's `--cache-session-retain-prompt-end` flag (the SERVING truth),
    else — when a worker is observable but carries no flag — the fork's own default, read from
    the very src/mlx-vlm the driver imports (the worker serves the same tree), else "unknown".
    """
    try:
        cmd = worker_lookup() if worker_lookup else None
    except Exception:  # noqa: BLE001 — never block a run on provenance
        cmd = None
    if not cmd:
        return {"session_retain_prompt_end": "unknown", "session_retain_source": "unknown"}
    m = re.search(r"--cache-session-retain-prompt-end\s+(\S+)", cmd)
    if m:
        return {"session_retain_prompt_end": m.group(1).lower(), "session_retain_source": "worker"}
    try:
        from mlx_vlm.generate.common import session_retain_prompt_end
    except Exception:  # noqa: BLE001 — a fork without the feature serves the old path
        return {"session_retain_prompt_end": "off", "session_retain_source": "fork-without-feature"}
    return {"session_retain_prompt_end": "on" if session_retain_prompt_end() else "off",
            "session_retain_source": "fork-default"}


# name -> (introduction fingerprint version, default value). A manifest older than the control's
# introduction version predates the key and every such row ran the default.
_SERVING_CONTROLS = {"attention_policy": (7, "auto"), "lazy_prompt_embeddings": (7, False),
                     "mtp_verify_scan": (8, "per_query")}

# Closed value sets (M58): a recorded value outside the set is unrecognised and reads "unknown".
_CONTROL_VALUES = {"mtp_verify_scan": ("per_query", "joint_v1", "joint_v1+ab")}


def control_of(manifest: dict, key: str):
    """(value, source) a manifest stands for on a serving control. A manifest whose
    fingerprint_version is below the control's introduction version predates the key and every
    such row ran the default, so it reads (default, "default-pre-v<N>") — a KNOWN value regardless
    of anything its runtime block claims. A newer manifest reports what it recorded; an absent or
    unrecognised value reads "unknown" (unresolved: never pools, never compares)."""
    intro, default = _SERVING_CONTROLS[key]
    if (manifest.get("fingerprint_version") or 1) < intro:
        return default, f"default-pre-v{intro}"
    r = manifest.get("runtime") or {}
    v = r.get(key)
    allowed = _CONTROL_VALUES.get(key)
    if v is not None and allowed is not None and v not in allowed:
        return "unknown", f"unrecognised:{v}"
    return ("unknown" if v is None else v), r.get(key + "_source")


def attention_policy_of(manifest: dict) -> tuple[str, str]:
    return control_of(manifest, "attention_policy")


class ServedConfigError(RuntimeError):
    """M50 refusal. FATAL by contract: entry points exit nonzero; `generate`'s per-item error handler
    re-raises it instead of recording an error row (a refusal after an auto-restart must stop the
    run, not become one more row)."""



class ServingStateError(ServedConfigError):
    """M57: the served attention/lazy-embedding state cannot be established or contradicts the
    registry. A ServedConfigError subclass, so `generate` and the drivers that re-raise
    ServedConfigError REFUSE the run instead of treating it as best-effort provenance."""


class ProvenancePreflightError(RuntimeError):
    """`preflight_gather` could not assemble a manifest at ENTRY: the run is refused before any
    model request rather than discovering at exit that its result cannot be published."""


def preflight_gather(model: str, *, profile: str, router: dict, label: str,
                     registry_path: str | None = None) -> dict:
    """Operator ruling 2026-10-06 (on Codex review 10 B1): an end-of-run gather failure now leaves
    the ladder STAGED and exits nonzero; to not waste a multi-hour ladder on a provenance problem
    that was already present at entry, run the same gather once here, right after the M50 /
    serving-state checks and before the first measured request. A ServedConfigError propagates
    (it is a refusal in its own right); any other failure becomes ProvenancePreflightError."""
    try:
        return gather(model, registry_path, profile=profile, router=router,
                      runtime={"probe": label, "preflight": True})
    except ServedConfigError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ProvenancePreflightError(
            f"provenance preflight for {label!r} failed: {type(e).__name__}: {e} — the end-of-run "
            f"gather would fail the same way; nothing was requested or created.") from e


def _flag_value(argv, flag):
    """Value of `--flag value` / `--flag=value` in an argv list (last wins); None if absent."""
    val = None
    for i, tok in enumerate(argv):
        if tok == flag and i + 1 < len(argv):
            val = argv[i + 1]
        elif tok.startswith(flag + "="):
            val = tok[len(flag) + 1:]
    return val


def _listeners_via_psutil(port: int):
    """Pids listening on `port` per the per-process walk, or None when the observation is
    INCOMPLETE (psutil missing, or some process refused inspection — it could be the listener).
    Gone/zombie processes are benign."""
    try:
        import psutil
    except Exception:  # noqa: BLE001
        return None
    benign = tuple(c for c in (getattr(psutil, "NoSuchProcess", None),
                               getattr(psutil, "ZombieProcess", None)) if c)
    pids, complete = set(), True
    try:
        for p in psutil.process_iter(["pid"]):
            try:
                conns = getattr(p, "net_connections", None) or getattr(p, "connections")
                for c in conns(kind="inet"):
                    if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == port:
                        pids.add(p.pid)
            except benign:
                continue
            except Exception:  # noqa: BLE001 — AccessDenied etc.: this process stays uninspected
                complete = False
    except Exception:  # noqa: BLE001
        return None
    return sorted(pids) if complete else None


def _listeners_via_lsof(port: int):
    """Pids listening on `port` per `lsof`, or None when lsof is unavailable or reported anything
    other than a clean result. macOS lsof exits 1 both for "no match" and for errors: only
    exit 1 with EMPTY stdout AND EMPTY stderr is a clean "nobody listens"."""
    try:
        r = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"],
                           capture_output=True, text=True, timeout=20)
    except Exception:  # noqa: BLE001 — missing binary, timeout, permission
        return None
    if r.stderr.strip() or r.returncode not in (0, 1):
        return None
    pids = sorted({int(l[1:]) for l in r.stdout.splitlines() if l.startswith("p") and l[1:].isdigit()})
    if r.returncode == 1 and (pids or r.stdout.strip()):
        return None
    return pids


def _port_listener_pids(port: int) -> list[int]:
    """Sorted pids with a LISTEN socket on `port`. Each backend (psutil walk, lsof) reports a
    COMPLETE observation or nothing; a completed backend is authoritative and two completed
    backends are united. When NEITHER can establish the state this RAISES ("router/worker state
    unknown") — "could not look" is never "nothing listens"."""
    seen = [r for r in (_listeners_via_psutil(port), _listeners_via_lsof(port)) if r is not None]
    if not seen:
        raise OSError(f"router/worker state unknown: neither the psutil walk nor lsof could "
                      f"establish who listens on :{port}")
    return sorted(set().union(*seen))


def result_digest(path: str) -> str:
    """sha256 hex of a result file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_matches_result(manifest_path: str, result_path: str):
    """True iff the manifest's recorded `result_sha256` (and `result_file` basename, when
    present) describe `result_path`; None when a well-formed manifest carries no digest (an older
    manifest beside an existing result — a legacy pair this helper cannot judge); False for a
    mismatch, a non-object manifest, an unreadable manifest/result or a missing result (a mixed
    or damaged pair). Content equality is NOT run identity: two runs with different provenance
    but byte-identical results also return True (Codex review 10, B1)."""
    try:
        with open(manifest_path) as f:
            man = json.load(f)
    except Exception:  # noqa: BLE001
        return False
    if not isinstance(man, dict):
        return False                                    # B2: `[]` / `"x"` is damage, not legacy
    want = man.get("result_sha256")
    if want is None:                                    # legacy: judge only that a result is readable
        return None if os.path.isfile(result_path) and os.access(result_path, os.R_OK) else False
    if man.get("result_file") not in (None, os.path.basename(result_path)):
        return False
    try:
        return result_digest(result_path) == want
    except Exception:  # noqa: BLE001
        return False


def publish_pair(result_stage: str, result_final: str, manifest_stage, manifest_final) -> None:
    """Publish a staged result and (when given) its staged manifest back to back — result
    first, manifest second, nothing in between. A tear after the first replace leaves the OLD
    manifest beside the NEW result; `manifest_matches_result` reports that as False when the old
    manifest carries a digest and the bytes differ, None for a digestless legacy manifest (B1:
    the tear is detectable, not always provably mixed). Callers must not reach this function
    with `manifest_stage=None` after a failed gather — see run_retrieval / run_reasoning."""
    os.replace(result_stage, result_final)
    if manifest_stage:
        os.replace(manifest_stage, manifest_final)


def set_aside_refused(path: str, name: str | None = None) -> str:
    """Rename a file produced by a REFUSED run to `<path>.refused-<utc timestamp>` (never deleted,
    never left under its normal name). `name` (default `path`) is the base the marker is appended
    to. Returns the new path; a missing file is a no-op ("")."""
    if not os.path.exists(path):
        return ""
    base = name or path
    ts = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    dest, n = f"{base}.refused-{ts}", 0
    while os.path.exists(dest):
        n += 1
        dest = f"{base}.refused-{ts}-{n}"
    os.replace(path, dest)
    return dest


def _ppid(pid: int):
    """Parent pid of `pid` (None at the root); raises when unreadable."""
    import psutil
    return psutil.Process(pid).ppid() or None


def _is_mlx_vlm_server(argv) -> bool:
    return any(t == "mlx_vlm.server" or t.endswith("/mlx_vlm.server") for t in argv)


def _descends_from(pid: int, ancestors: set) -> bool:
    seen = set()
    while pid and pid not in seen:
        if pid in ancestors:
            return True
        seen.add(pid)
        pid = _ppid(pid)
    return False


def _worker_argvs(doc) -> list[list[str]]:
    """argv list of THE worker: the process listening on the registry's `mlx_port` (the port the
    router's worker subprocess serves), identified independently of any all-process argv scan.
    [] when nothing listens (no worker) or no stack is up. Refuses (ServingStateError) when the
    listener's argv is unreadable, more than one process listens, the lookup fails while a router
    (`manager_port` owner) is up."""
    doc = doc if isinstance(doc, dict) else {}
    mlx_port, manager_port = doc.get("mlx_port"), doc.get("manager_port", 8000)

    if mlx_port is None:
        return []           # registry names no worker port: nothing to identify, registry stands
    try:
        pids = _port_listener_pids(int(mlx_port))
    except Exception as e:  # noqa: BLE001
        try:
            router_up = bool(_port_listener_pids(manager_port))
        except Exception:  # noqa: BLE001 — cannot tell either: refuse, never assume absent
            router_up = True
        if not router_up:
            return []
        raise ServingStateError(f"C35 tripwire: router/worker state unknown — cannot observe the "
                                f"listener on mlx_port {mlx_port} ({type(e).__name__}: "
                                f"{str(e)[:80]}) while a router is up; refusing to fall back to "
                                f"the registry on ignorance.") from e
    if not pids:
        return []
    if len(pids) > 1:
        raise ServingStateError(f"C35 tripwire: more than one process listens on mlx_port "
                                f"{mlx_port} (pids {pids}) — worker attribution is ambiguous.")
    argv = _process_facts(pids[0]).get("argv")
    if not argv:
        raise ServingStateError(f"C35 tripwire: the worker (pid {pids[0]}, mlx_port {mlx_port}) "
                                f"has an unreadable argv; cannot establish its served state.")
    if not _is_mlx_vlm_server(argv):
        raise ServingStateError(f"C35 tripwire: the process listening on mlx_port {mlx_port} "
                                f"(pid {pids[0]}) is not an mlx_vlm.server process — it is "
                                f"squatting the worker port; no measurement here is trustworthy.")
    try:
        routers = set(_port_listener_pids(manager_port))
        if routers and not _descends_from(pids[0], routers):
            raise ServingStateError(f"C35 tripwire: the listener on mlx_port {mlx_port} (pid "
                                    f"{pids[0]}) does not descend from the router on "
                                    f"manager_port {manager_port} (pids {sorted(routers)}); it is "
                                    f"squatting the worker port.")
    except ServingStateError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ServingStateError(f"C35 tripwire: router/worker state unknown — cannot verify the "
                                f"worker's parentage ({type(e).__name__}: {str(e)[:80]}).") from e
    return [list(argv)]


def _worker_for(entry: dict, worker_lookup, doc=None):
    """The ONE live worker argv whose `--model` argument EXACTLY equals the entry's hf_path, else
    None ("no worker for this model" -> registry fallback). A failed observation or more than one
    match raises ServingStateError. `worker_lookup` returns None, an argv list, a cmdline string
    (whitespace-split) or a list of those."""
    try:
        got = _worker_argvs(doc) if worker_lookup is _DEFAULT_LOOKUP else (
            worker_lookup() if worker_lookup else None)
    except ServingStateError:
        raise
    except Exception as e:  # noqa: BLE001 — re-raised as a refusal, never swallowed
        raise ServingStateError(f"C35 tripwire: cannot observe the live workers "
                                f"({type(e).__name__}: {str(e)[:80]}); refusing to fall back to "
                                f"the registry on ignorance.") from e
    if isinstance(got, str):
        got = [got.split()]
    argvs = [a.split() if isinstance(a, str) else list(a) for a in (got or [])]
    hf = entry.get("hf_path") or ""
    hits = [a for a in argvs if hf and _flag_value(a, "--model") == hf]
    if len(hits) > 1:
        raise ServingStateError(f"C35 tripwire: more than one live worker serves {hf!r} "
                                f"({len(hits)} matches) — worker attribution is ambiguous; "
                                f"refusing to record serving provenance.")
    return hits[0] if hits else None


def _resolve_control(model, registry_path, worker_lookup, key, parse_worker, parse_registry,
                     compare_value=None):
    registry_path = str(paths.registry_path()) if registry_path is None else registry_path
    try:
        with open(registry_path) as f:
            doc = yaml.safe_load(f)
    except Exception:  # noqa: BLE001 — never block a run on provenance
        return {key: "unknown", key + "_source": "unreadable-registry"}
    entries = doc.get("models", doc) if isinstance(doc, dict) else doc
    for e in entries or []:
        if isinstance(e, dict) and e.get("name") == model:
            declared = parse_registry(e.get(key))
            compared = compare_value(e) if compare_value else declared
            cmd = _worker_for(e, worker_lookup, doc)
            if cmd is not None:
                served = parse_worker(cmd)
                if served != compared:
                    raise ServingStateError(
                        f"C35 tripwire: registry {registry_path!r} declares {key}="
                        f"{compared!r} for {model!r} but the live worker serves "
                        f"{key}={served!r}. Launch the driver with MLX_SERVE_CONFIG "
                        f"pointed at the served registry/overlay; refusing to record false "
                        f"{key} provenance.")
                return {key: served, key + "_source": "worker"}
            return {key: compared, key + "_source": "registry"}
    return {key: "unknown", key + "_source": "model-not-in-registry"}


def assert_serving_state(model: str, registry_path: str | None = None, expect: dict | None = None) -> dict:
    """Resolve the serving controls (M57 attention policy and lazy embeddings, M58 verification
    scan) for `model` and let any ServingStateError propagate (worker/registry disagreement,
    ambiguity, failed observation). The M58 scan additionally REFUSES when it cannot be resolved
    ("unknown": unreadable registry / model absent): a v8 row with an unresolved value could never
    pool or compare. Drivers call this before their first model request and once more after the
    model is loaded."""
    out = dict(registry_attention_policy(model, registry_path))
    out.update(registry_lazy_prompt_embeddings(model, registry_path))
    out.update(registry_mtp_verify_scan(model, registry_path))
    if out["mtp_verify_scan"] == "unknown":
        raise ServingStateError(
            f"M58: mtp_verify_scan is UNRESOLVED for {model!r} "
            f"({out['mtp_verify_scan_source']}); refusing — a v8 row without a known scan value "
            f"could never pool or compare.")
    if expect is not None and expect.get("mtp_verify_scan") != out["mtp_verify_scan"]:
        raise ServingStateError(
            f"M58: mtp_verify_scan changed for {model!r} between entry "
            f"({expect.get('mtp_verify_scan')!r}) and the loaded worker "
            f"({out['mtp_verify_scan']!r}); refusing — the manifest would stamp the wrong mode "
            f"(an AB gate row must never pool with a latency row).")
    return out


def registry_attention_policy(model: str, registry_path: str | None = None,
                              worker_lookup=_DEFAULT_LOOKUP) -> dict:
    """M57 served attention policy: {"attention_policy", "attention_policy_source"}.

    The live worker whose `--model` argument exactly equals the entry's hf_path is the SERVING
    truth: its `--attention-policy <v>` flag (absent = "auto"), source "worker". Otherwise the
    registry entry's `attention_policy` (absent/empty = "auto"), source "registry". Both
    available and disagreeing REFUSES the run (C35 shape); two matching workers refuse too.
    "unknown" is reserved for an unreadable registry or a model absent from it, and is
    UNRESOLVED: it never pools and never compares (S1)."""
    def from_worker(argv):
        return _flag_value(argv, "--attention-policy") or "auto"
    return _resolve_control(model, registry_path, worker_lookup, "attention_policy",
                            from_worker, lambda v: v or "auto")


def registry_lazy_prompt_embeddings(model: str, registry_path: str | None = None,
                                        worker_lookup=_DEFAULT_LOOKUP) -> dict:
    """M57 served lazy-prompt-embeddings state: bare worker flag `--lazy-prompt-embeddings`
    present -> True, absent -> False (source "worker"); else the registry entry's boolean
    (absent -> False, source "registry"). Same attribution, refusal and "unknown" rules as
    registry_attention_policy."""
    def from_worker(argv):
        return "--lazy-prompt-embeddings" in argv
    return _resolve_control(model, registry_path, worker_lookup, "lazy_prompt_embeddings",
                            from_worker, bool)


def check_mtp_verify_scan_value(value, where: str) -> str:
    """The ONE closed-set check for `mtp_verify_scan` (`per_query`, `joint_v1`, `joint_v1+ab`),
    called on every production path (resolver, runtime block, manifest construction, parity
    replay). "unknown" is the UNRESOLVED outcome and passes here (the callers that require a
    resolved value refuse it themselves); anything else outside the set refuses."""
    if value != "unknown" and value not in _CONTROL_VALUES["mtp_verify_scan"]:
        raise ServingStateError(
            f"M58: mtp_verify_scan {value!r} ({where}) is not one of "
            f"{_CONTROL_VALUES['mtp_verify_scan']}; refusing.")
    return value


def registry_mtp_verify_scan(model: str, registry_path: str | None = None,
                             worker_lookup=_DEFAULT_LOOKUP) -> dict:
    """M58 served verification scan: {"mtp_verify_scan", "mtp_verify_scan_source"}.

    The live worker whose `--model` equals the entry's hf_path is the SERVING truth:
    `--mtp-verify-scan <v>` (flag absent = "per_query") plus the bare `--mtp-verify-ab` flag
    ("joint_v1+ab"), source "worker". Otherwise the registry/overlay entry: `mtp_verify_scan`
    (absent or empty = "per_query"), with `mtp_verify_ab: true` giving "joint_v1+ab", source
    "registry" — an AB overlay must never stamp a plain `joint_v1` before the worker is up. A
    worker that disagrees with the registry REFUSES (C35 shape). A value outside the closed set
    refuses; "unknown" is reserved for an unreadable registry or a model absent from it."""
    def from_worker(argv):
        scan = _flag_value(argv, "--mtp-verify-scan") or "per_query"
        return scan + "+ab" if "--mtp-verify-ab" in argv else scan

    def declared_with_ab(entry):
        scan = entry.get("mtp_verify_scan") or "per_query"
        return scan + "+ab" if entry.get("mtp_verify_ab") else scan
    out = _resolve_control(model, registry_path, worker_lookup, "mtp_verify_scan",
                           from_worker, lambda v: v or "per_query", declared_with_ab)
    check_mtp_verify_scan_value(out["mtp_verify_scan"], out["mtp_verify_scan_source"])
    return out


def worker_serving_facts(model: str, registry_path: str | None = None,
                         worker_lookup=_DEFAULT_LOOKUP) -> dict | None:
    """The live worker's `--model` / `--draft-kind` / `--mtp-verify-scan` / `--mtp-verify-ab` flags
    for `model`, or None when no worker serves it (or the registry is unreadable / lacks the model).
    Same attribution as the serving controls: the ONE worker whose `--model` equals the entry's
    hf_path; ambiguity or a failed observation raises ServingStateError."""
    registry_path = str(paths.registry_path()) if registry_path is None else registry_path
    try:
        with open(registry_path) as f:
            doc = yaml.safe_load(f)
    except Exception:  # noqa: BLE001 — provenance is best-effort when the registry is unreadable
        return None
    entries = doc.get("models", doc) if isinstance(doc, dict) else doc
    for e in entries or []:
        if isinstance(e, dict) and e.get("name") == model:
            argv = _worker_for(e, worker_lookup, doc)
            if argv is None:
                return None
            return {"model": _flag_value(argv, "--model"),
                    "draft_kind": _flag_value(argv, "--draft-kind"),
                    "mtp_verify_scan": _flag_value(argv, "--mtp-verify-scan"),
                    "mtp_verify_ab": "--mtp-verify-ab" in argv}
    return None


# ----------------------------------------------------- M50 served-config tripwire (2026-09-28)
# The process that OWNS the router port is the serving truth for WHICH registry is live. C35 only
# checks draft_kind, and only when a worker for the requested model is already up; on 2026-09-28 a
# lean overlay router failed to bind, the daily driver kept :8000, and a parity arm ran against it
# with the overlay stamped as provenance. Every driver/probe now calls `assert_served_config()`
# before anything is read, written or requested and REFUSES (RuntimeError -> nonzero exit) unless
# the owner is an mlx-serve router whose MLX_SERVE_CONFIG, resolved against ITS cwd/HOME exactly as
# mlx-serve resolves it, is the same existing file as the driver's `paths.registry_path()`.
# `gather()` records the verified block best-effort as `manifest["router"]` (outside the
# fingerprint: a pid change across restarts is not a config change). No env/flag bypass exists.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "::"}
_WILDCARDS = {"0.0.0.0", "::", "*"}
_LAST_VERIFIED: dict = {}   # port -> block from the most recent assert_served_config in this process




def _is_router_argv(argv) -> bool:
    """The owner must BE the mlx-serve router, judged by the PROGRAM position only: argv[0] is the
    `mlx-serve` console script, or argv[0] is a python interpreter whose first positional is that
    script or whose `-m` module is `mlx_serve[...]`. Application arguments are never identity
    (`python -m http.server 8000 --directory /opt/mlx-serve` is not a router)."""
    argv = list(argv or [])
    if not argv:
        return False
    if os.path.basename(argv[0]) == "mlx-serve":
        return True
    if not os.path.basename(argv[0]).startswith("python"):
        return False
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "-m":
            return i + 1 < len(argv) and argv[i + 1].split(".")[0] == "mlx_serve"
        if a in ("-X", "-W"):          # interpreter flag with a SEPARATE value
            i += 2
            continue
        if a.startswith("-"):          # interpreter flag (-u, -Xdev, -Wignore, ...)
            i += 1
            continue
        return os.path.basename(a) == "mlx-serve"   # first positional = the script
    return False


def _covers(dest_host: str, bound_ips) -> bool:
    """Does some listener bound address serve a connection to `dest_host`? `0.0.0.0` covers v4
    only; `::` covers v6 and (dual-stack) v4; `*`/unknown (lsof could not tell) count as covering
    because the pid was found; `localhost` may resolve either way so any loopback covers it; an
    explicit v4/v6 destination needs a listener of its family."""
    ips = set(bound_ips or [])
    if not ips or "*" in ips or None in ips:
        return True
    v4_dest = dest_host == "localhost" or ":" not in dest_host
    v6_dest = dest_host == "localhost" or ":" in dest_host
    if v4_dest and (ips & {"0.0.0.0", "::"} or dest_host in ips or (dest_host == "localhost" and "127.0.0.1" in ips)):
        return True
    if v6_dest and ("::" in ips or dest_host in ips or (dest_host == "localhost" and "::1" in ips)):
        return True
    return False


def _split_base(base_url: str | None) -> tuple[str, str, int]:
    """(scheme, host, port) from ONE parse of a CANONICAL base URL. Anything non-canonical (leading
    or trailing whitespace, a scheme other than http/https, no host) refuses: the cold review showed
    `' https://…'` parsed as https by urllib but read as http by a `startswith` — the proxy check
    then looked at the wrong variable while the client tunnelled through the proxy."""
    from urllib.parse import urlsplit
    raw = base_url if base_url is not None else "http://localhost:8000"
    if not isinstance(raw, str) or raw != raw.strip() or not raw:
        raise ServedConfigError(f"M50 tripwire: non-canonical base URL {raw!r} (whitespace/empty); "
                                f"refusing to guess how the client will parse it.")
    u = urlsplit(raw)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ServedConfigError(f"M50 tripwire: base URL {raw!r} is not an http(s) URL with a host.")
    port = int(u.port) if u.port else (443 if u.scheme == "https" else 80)
    return u.scheme, u.hostname.lower(), port


def _env_proxies(env: dict) -> dict:
    """EXACTLY CPython's `urllib.request.getproxies_environment`, over an arbitrary env: every
    `*_proxy` (any case) with a value is collected, then the LOWERCASE names win — a lowercase
    value overrides an uppercase one and an EMPTY lowercase value clears the entry. (Reproduced by
    the cold review: `http_proxy=X NO_PROXY=* no_proxy=` proxies everything under urllib.)"""
    proxies = {}
    for name, value in env.items():
        lname = name.lower()
        if value and lname[-6:] == "_proxy":
            proxies[lname[:-6]] = value
    if "REQUEST_METHOD" in env:
        proxies.pop("http", None)
    for name, value in env.items():
        if name[-6:] == "_proxy":
            if value:
                proxies[name[:-6]] = value
            else:
                proxies.pop(name[:-6], None)
    return proxies


def _proxy_for(base_url: str, env: dict | None = None, strict: bool = False) -> str | None:
    """The proxy an env-honouring client would route `base_url` through under `env`, or None for a
    direct connection — decided on the SAME inputs urllib's ProxyHandler uses: `Request(url).type`
    picks the `<scheme>_proxy`, and `Request(url).host` (the authority exactly as spelled:
    `localhost:08000`, `[::1]:8000`, no port when omitted) is what no_proxy is matched against.
    Nothing is reconstructed. `strict` (the opencode CHILD, whose runtime has its own precedence
    rules): any lower/upper-case pair of the same variable with DIFFERENT values is ambiguous and
    counts as proxied, so the guard never guesses which one the child will honour."""
    from urllib.request import Request, proxy_bypass_environment
    env = dict(os.environ if env is None else env)
    if strict:
        by_key = {}
        for name, value in env.items():
            if name.lower().endswith("_proxy"):
                by_key.setdefault(name.lower(), set()).add(value or "")
        for k, vals in by_key.items():
            if len(vals) > 1:
                return f"ambiguous {k} ({sorted(vals)})"
    req = Request(base_url)
    proxies = _env_proxies(env)
    chosen = proxies.get(req.type)
    if not chosen:
        return None
    if req.host and proxy_bypass_environment(req.host, proxies):
        return None
    return chosen


def _port_from_base(base_url: str | None) -> int:
    return _split_base(base_url)[2]


def _psutil_listeners(port: int) -> list[tuple[int, str]]:
    """[(pid, bound_ip)] for every LISTEN socket on `port`, via the per-process walk (the
    system-wide table is AccessDenied for a non-root user on macOS; per-process works for our
    own processes, which is what we launch). psutil<6 spells the accessor `connections`."""
    try:
        import psutil
    except Exception:  # noqa: BLE001
        return []
    found = []
    for p in psutil.process_iter(["pid"]):
        try:
            conns = getattr(p, "net_connections", None) or getattr(p, "connections")
            for c in conns(kind="inet"):
                if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == port:
                    found.append((p.pid, c.laddr.ip))
        except Exception:  # noqa: BLE001 — AccessDenied / gone / zombie
            continue
    return found


def _lsof_listeners(port: int) -> list[tuple[int, str | None]]:
    """[(pid, bound_ip)] from `lsof -Fpn`: a `p<pid>` line, then one `n<addr>:<port>` line per
    socket (`*` = wildcard, `[::1]` = v6 loopback). A pid with no `n` line yields (pid, None)."""
    try:
        out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fpn"],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:  # noqa: BLE001
        return []
    found, pid, seen_addr = [], None, False
    for line in out.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            if pid is not None and not seen_addr:
                found.append((pid, None))
            pid, seen_addr = int(line[1:]), False
        elif line.startswith("n") and pid is not None:
            addr = line[1:].rsplit(":", 1)[0]
            found.append((pid, "*" if addr == "*" else addr.strip("[]")))
            seen_addr = True
    if pid is not None and not seen_addr:
        found.append((pid, None))
    return found


def _lsof_listener_pids(port: int) -> list[int]:
    return sorted({pid for pid, _ in _lsof_listeners(port)})


def _process_facts(pid: int) -> dict:
    """{pid, cmdline, cwd, env, env_error}; each fact read independently so one refusal does not
    blank the others. `env` is None when the environ is unreadable (another user's process)."""
    facts = {"pid": pid, "argv": None, "cmdline": None, "cwd": None, "env": None, "env_error": None}
    try:
        import psutil
        p = psutil.Process(pid)
    except Exception as e:  # noqa: BLE001
        facts["env_error"] = f"{type(e).__name__}: {e}"
        return facts
    for key, fn in (("argv", lambda: list(p.cmdline())), ("cwd", p.cwd),
                    ("env", lambda: dict(p.environ()))):
        try:
            facts[key] = fn()
        except Exception as e:  # noqa: BLE001
            if key == "env":
                facts["env_error"] = f"{type(e).__name__}: {e}"
    if facts["argv"] is not None:
        facts["cmdline"] = " ".join(facts["argv"])
    return facts


def router_owner(port: int = 8000) -> dict | None:
    """Facts about THE process listening on `port`; None when nothing does. Two DIFFERENT pids
    listening (e.g. a stale router on IPv4 and a new one on IPv6) is ambiguous and refuses."""
    listeners = list(_psutil_listeners(port)) + list(_lsof_listeners(port))
    pids = sorted({pid for pid, _ in listeners})
    if not pids:
        return None
    if len(pids) > 1:
        raise ServedConfigError(f"M50 tripwire: {len(pids)} different processes listen on :{port} "
                                f"(pids {pids}); the owner is ambiguous — stop the stale one "
                                f"(scripts/stack_stop.sh) and relaunch.")
    facts = _process_facts(pids[0])
    facts["bound_ips"] = sorted({ip for _, ip in listeners if ip is not None}, key=str)
    return facts


def _served_config_path(owner: dict, port: int) -> tuple[str | None, str | None]:
    """(raw MLX_SERVE_CONFIG, realpath the ROUTER resolves it to). Mirrors mlx-serve `config.py`
    `_find_config`: `Path(env).expanduser()` — with the ROUTER's HOME — relative to the ROUTER's
    cwd; the file must exist (mlx-serve raises on a missing explicit path; a router whose file
    was deleted after start is serving something we can no longer identify). Absent -> (None, None)."""
    env = owner.get("env") or {}
    raw = env.get("MLX_SERVE_CONFIG")
    pid = owner.get("pid")
    if not raw:
        return None, None
    p = raw
    if p == "~" or p.startswith("~/"):
        home = env.get("HOME")
        if not home:
            raise ServedConfigError(f"M50 tripwire: pid {pid} serves MLX_SERVE_CONFIG={raw!r} but its "
                               f"environ has no HOME to expand it with; unverifiable.")
        p = home + p[1:]
    elif p.startswith("~"):
        raise ServedConfigError(f"M50 tripwire: pid {pid} serves MLX_SERVE_CONFIG={raw!r} (~user form); "
                           f"cannot resolve another user's home; unverifiable.")
    if not os.path.isabs(p):
        cwd = owner.get("cwd")
        if not cwd:
            raise ServedConfigError(f"M50 tripwire: pid {pid} serves relative MLX_SERVE_CONFIG={raw!r} "
                               f"but its cwd is unreadable; unverifiable.")
        p = os.path.join(cwd, p)
    resolved = os.path.realpath(p)
    if not os.path.isfile(resolved):
        raise ServedConfigError(f"M50 tripwire: pid {pid} (owner of :{port}) was started with "
                           f"MLX_SERVE_CONFIG={raw!r} -> {resolved!r}, which no longer exists; the "
                           f"served config cannot be identified. Restart the router.")
    return raw, resolved


def _scrub(v, extra_homes=()):
    """Every occurrence of the driver's $HOME AND the router's HOME (they can differ) in every
    persisted string — a cmdline holds several absolute paths, not just a leading one."""
    if not isinstance(v, str):
        return v
    for home in sorted({os.path.expanduser("~"), *[h for h in extra_homes if h]}, key=len, reverse=True):
        if home and home != "/":
            v = v.replace(home, "$HOME")
    return v


def _placeholder_roots(*, for_write: bool = False) -> list[tuple[str, str]]:
    """(placeholder, absolute root) pairs, longest root first: `$STACK_WORKDIR` nests under
    `$HOME`, so it must be tried before `$HOME` or every workdir path would come out as
    `$HOME/ws/...` (a real path shape, just not a portable one). `for_write=True` resolves the
    workdir through the trapped `paths.stack_workdir` (the result will be used as a filesystem
    path); display-only callers use the untrapped resolver."""
    roots = []
    try:
        wd = (paths.stack_workdir(required=False) if for_write
              else paths.resolve_stack_workdir(required=False))
    except Exception:  # noqa: BLE001 — a malformed config.sh must not break manifest writing
        wd = None
    if wd:
        roots.append(("$STACK_WORKDIR", str(wd)))
    home = os.path.expanduser("~")
    if home and home != "/":
        roots.append(("$HOME", home))
    return sorted(roots, key=lambda r: len(r[1]), reverse=True)


# A root is replaced only as a whole path component: not inside a word or a longer path
# (`/backup/Users/x`, `/Users/xy`), but after a separator-like character, a URL scheme or `//`.
_PATH_BOUNDARY_BEFORE = r"(?<![\w.\-~$])(?<![\w.\-~$]/)"
_PATH_BOUNDARY_AFTER = r"(?=/|$|\.(?!\w)|[\s'\":,;)\]}])"


def portable_path(v, _roots=None):
    """Placeholder form of a persisted string: each BOUNDED occurrence of the resolved
    `$STACK_WORKDIR` or `$HOME` root becomes its placeholder (handoff 2026-10-06 item 4:
    `vision_gate` wrote an absolute `corpus` path into a committed manifest — the public-repo PII
    hook caught it; this is the one place every driver's `runtime` strings pass through).
    PathLike values are converted; other non-strings pass through."""
    if hasattr(v, "__fspath__"):
        v = os.fspath(v)
    if not isinstance(v, str):
        return v
    for placeholder, root in (_roots if _roots is not None else _placeholder_roots()):
        v = re.sub(_PATH_BOUNDARY_BEFORE + re.escape(root) + _PATH_BOUNDARY_AFTER,
                   lambda m, ph=placeholder: ph, v)
    return v


class UnresolvedPlaceholderError(ValueError):
    """`expand_portable(strict=True)` found a placeholder it could not resolve (no workdir
    configured): the string must not be used as a filesystem path."""


def expand_portable(v, *, strict: bool = False):
    """Inverse of `portable_path` for readers that turn a manifest path back into a filesystem
    path (e.g. an AgentBench resume reading `runtime.transcripts_dir`). Only a BOUNDED placeholder
    expands: a literal `$HOME` inside a longer path (`.../runs/$HOME/x`) or a word (`$HOMEwork`)
    stays as written (cold review 1, B1). The workdir is resolved through the trapped writer
    resolver. `strict=True` raises when a bounded placeholder survives (e.g. `$STACK_WORKDIR` with
    no workdir configured) instead of handing back a relative path that would land under the cwd."""
    if not isinstance(v, str):
        return v
    for placeholder, root in _placeholder_roots(for_write=True):
        v = re.sub(_PATH_BOUNDARY_BEFORE + re.escape(placeholder) + _PATH_BOUNDARY_AFTER,
                   lambda m: root, v)
    if strict:
        for placeholder in ("$STACK_WORKDIR", "$HOME"):
            if re.search(_PATH_BOUNDARY_BEFORE + re.escape(placeholder) + _PATH_BOUNDARY_AFTER, v):
                raise UnresolvedPlaceholderError(
                    f"{placeholder} in {v!r} cannot be expanded (not configured); refusing to use it as a path")
    return v


def _portable_deep(v, _roots=None):
    roots = _placeholder_roots() if _roots is None else _roots
    if isinstance(v, dict):
        return {portable_path(k, roots): _portable_deep(x, roots) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_portable_deep(x, roots) for x in v]
    return portable_path(v, roots)


def assert_served_config(base_url: str | None = None, *, port: int | None = None,
                         lookup=None, env: dict | None = None) -> dict:
    """M50 tripwire. Returns {"pid", "config" ($HOME-form), "config_raw", "port", "cmdline"} for
    the mlx-serve router that owns the port when it serves exactly `paths.registry_path()`;
    raises ServedConfigError otherwise. Call BEFORE anything is read, written or requested and let
    the error escalate (nonzero exit). Only a LOCAL, UNPROXIED destination can be verified (single
    box). `env` is the environment whose proxy settings apply (a child's); default: this process."""
    lookup = lookup or router_owner
    scheme, host, url_port = _split_base(base_url)
    port = int(port or url_port)
    expected = os.path.realpath(str(paths.registry_path()))
    hint = ("Start the router you mean to measure with MLX_SERVE_CONFIG=<that file> (and the "
            "driver with the same value), verify it OWNS the port (lsof -nP -iTCP:%d -sTCP:LISTEN), "
            "then relaunch." % port)
    if host not in _LOCAL_HOSTS:
        raise ServedConfigError(f"M50 tripwire: destination host {host!r} is not this box; the served "
                           f"config of a remote router cannot be verified (SINGLE BOX since "
                           f"2026-08-17). Point the driver at localhost.")
    proxy = _proxy_for(base_url if base_url is not None else "http://localhost:8000", env,
                       strict=env is not None)
    if proxy:
        raise ServedConfigError(f"M50 tripwire: {scheme}_proxy {proxy!r} applies to {host!r} in the "
                                f"{'child' if env is not None else 'driver'} environment; requests would "
                                f"go to the proxy, not the verified router. Add {host} to no_proxy (same "
                                f"case as the proxy variable) or unset the proxy.")
    owner = lookup(port)
    if owner is None:
        raise ServedConfigError(f"M50 tripwire: no process owns :{port} — refusing to run against a "
                           f"router that is not there (driver registry {expected!r}). {hint}")
    pid = owner.get("pid")
    cmd = owner.get("cmdline") or ""
    argv = owner.get("argv") if owner.get("argv") is not None else cmd.split()
    if not _is_router_argv(argv):
        raise ServedConfigError(f"M50 tripwire: pid {pid} owns :{port} but is not an mlx-serve router "
                                f"(cmdline {cmd!r}); refusing to trust its environ. {hint}")
    if not _covers(host, owner.get("bound_ips")):
        raise ServedConfigError(f"M50 tripwire: pid {pid} listens on :{port} at {owner.get('bound_ips')} "
                                f"which does not answer {host!r}; the driver would connect elsewhere "
                                f"(or fail). Point the driver at an address the router is bound to.")
    if owner.get("env") is None:
        raise ServedConfigError(f"M50 tripwire: cannot read the environ of pid {pid} (owner of :{port}, "
                           f"{owner.get('env_error')}); the served config is unverifiable. {hint}")
    raw, served = _served_config_path(owner, port)
    if served is None:
        raise ServedConfigError(f"M50 tripwire: pid {pid} owns :{port} but carries no MLX_SERVE_CONFIG "
                           f"(mlx-serve then reads ./models.yaml, ~/.mlx-serve/models.yaml or its "
                           f"bundled default — not this driver's registry {expected!r}). {hint}")
    if served != expected:
        raise ServedConfigError(f"M50 tripwire: pid {pid} owns :{port} and serves MLX_SERVE_CONFIG="
                           f"{raw!r} -> {served!r}, but this driver's registry is {expected!r}. "
                           f"Every request would be measured against the wrong served config. {hint}")
    homes = ((owner.get("env") or {}).get("HOME"),)
    block = {"pid": pid, "config": _scrub(served, homes), "config_raw": _scrub(raw, homes),
             "port": port, "cmdline": _scrub(cmd, homes),
             # C106 (2026-09-29): content identity of the served file at verification time. The
             # router reads its registry ONCE at start; a path comparison cannot see an in-place
             # edit or a symlink retarget afterwards. Compared again at exit (assert_served_config_unchanged).
             "config_sha256": _file_sha256(served)}
    _LAST_VERIFIED[port] = dict(block)
    return block


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def assert_served_config_unchanged(entry: dict, base_url: str | None = None, *, port: int | None = None,
                                   lookup=None, env: dict | None = None) -> dict:
    """C106 driver-side belt (operator 2026-09-29): re-run the M50 verification at EXIT and refuse
    to declare a run complete if the served file's content or the router pid differs from `entry`
    (the block verified at entry). Rows written in between stay on disk but must not be graded or
    marked clean: the runtime they were produced under is not the one the manifest names. Returns
    the exit block (same shape as `entry`, plus `verified_at: "exit"`). Catches only what a driver
    can see from outside — an edited/retargeted registry or a restarted router; the operator rule
    "never change serving config during a live run" still stands for everything else."""
    exit_blk = assert_served_config(base_url, port=port, lookup=lookup, env=env)
    problems = []
    if entry.get("pid") is not None and exit_blk["pid"] != entry.get("pid"):
        problems.append(f"router pid changed {entry.get('pid')} -> {exit_blk['pid']} (restart during the run)")
    if entry.get("config_sha256") and exit_blk["config_sha256"] != entry["config_sha256"]:
        problems.append(f"served file content changed: entry sha256 {entry['config_sha256'][:12]}… -> "
                        f"exit sha256 {exit_blk['config_sha256'][:12]}… ({exit_blk['config']})")
    if problems:
        raise ServedConfigError("C106 exit check: the served runtime changed during this run — "
                                + "; ".join(problems) + ". Rows written since entry cannot be attributed "
                                "to the manifest's registry: do not grade or pool them; restart the router "
                                "on the intended config and rerun.")
    exit_blk["verified_at"] = "exit"
    return exit_blk


def served_config_drift_record(entry: dict, base_url: str | None, error) -> dict:
    """The `served_config_drift` stamp every driver records when its C106 exit check refuses:
    entry and (best-effort) exit content hashes plus the refusal text."""
    try:
        exit_sha = assert_served_config(base_url).get("config_sha256")
    except Exception:  # noqa: BLE001 — forensic only
        exit_sha = None
    return {"entry_sha256": entry.get("config_sha256"), "exit_sha256": exit_sha, "error": str(error)}


class ExitGuard:
    """Shared exit protocol for the ladder drivers (capacity / retrieval / reasoning).

    Wrap everything AFTER the M50 entry check in `with ExitGuard(entry, base_url) as g:`.
      * `g.track(path, name=None)` registers an artifact that must never stand under its canonical
        name after a refused run (`name` is the base the `.refused-<utc>` marker is appended to).
      * `g.verify()` is the C106 exit re-verification; call it right before publication. A drift
        records `g.drift` (the `served_config_drift` stamp) and raises ServedConfigError.
      * On ANY exception the guard runs the verification best-effort (so a drift is stamped even
        when the run died earlier). If the exception is a ServedConfigError or a drift was found,
        every tracked artifact is stamped with `served_config_drift` (when drift is known) and set
        aside as `.refused-<utc>`. The ORIGINAL exception always propagates: failures while
        verifying or quarantining are printed, never raised in its place.
      * A clean body that never called `verify()` is verified here (and refused on drift)."""

    def __init__(self, entry: dict, base_url: str | None = None, *, label: str = "driver"):
        self.entry, self.base_url, self.label = entry, base_url, label
        self.artifacts: list = []
        self.exit_blk = None
        self.drift = None
        self._verified = False

    def track(self, path, name=None) -> None:
        self.artifacts.append((str(path), str(name) if name else None))

    def verify(self) -> dict:
        try:
            self.exit_blk = assert_served_config_unchanged(self.entry, self.base_url)
        except ServedConfigError as e:
            self.drift = served_config_drift_record(self.entry, self.base_url, e)
            raise
        self._verified = True
        return self.exit_blk

    def _say(self, msg: str) -> None:
        """Diagnostics inside the guard never throw: a closed or broken stdout must not replace
        the original exception."""
        try:
            print(f"[{self.label}] {msg}", flush=True)
        except (OSError, ValueError):
            pass

    def _stamp(self, path: str) -> None:
        if path.endswith(".jsonl"):
            with open(path, "a") as f:
                f.write(json.dumps({"event": "served_config_drift",
                                    "served_config_drift": self.drift}) + "\n")
        elif ".json" in os.path.basename(path):
            with open(path) as f:
                doc = json.load(f)
            if isinstance(doc, dict):
                doc["served_config_drift"] = self.drift
                with open(path, "w") as f:
                    json.dump(doc, f, indent=2)

    def _quarantine(self) -> None:
        for path, name in self.artifacts:
            stamp_error = None
            try:
                if not os.path.exists(path):
                    continue
                if self.drift is not None:
                    try:
                        self._stamp(path)
                    except Exception as e:  # noqa: BLE001 — the rename below does NOT depend on this
                        stamp_error = f"{type(e).__name__}: {e}"
                dest = set_aside_refused(path, name)
            except Exception as e:  # noqa: BLE001 — never replace the original exception
                self._say(f"WARNING: could not quarantine {path}: {type(e).__name__}: {e}")
                continue
            if stamp_error:
                try:
                    with open(dest + ".stamp-error", "w") as f:
                        f.write(f"served_config_drift could not be stamped into this artifact: "
                                f"{stamp_error}\ndrift: {json.dumps(self.drift)}\n")
                except Exception:  # noqa: BLE001
                    pass
                self._say(f"WARNING: drift stamp failed for {os.path.basename(path)}: {stamp_error}")
            self._say(f"REFUSED: {os.path.basename(path)} set aside at {dest}")

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        err, raised_here = ev, False
        if err is None:
            if not self._verified:
                try:
                    self.verify()
                except ServedConfigError as e:
                    err, raised_here = e, True
        elif not self._verified and self.drift is None:
            try:
                self.verify()
            except ServedConfigError:
                pass
            except Exception as e:  # noqa: BLE001
                self._say(f"WARNING: exit verification failed: {type(e).__name__}: {e}")
        if err is not None and (isinstance(err, ServedConfigError) or self.drift is not None):
            self._quarantine()
        if raised_here:
            raise err
        return False


def router_block(base_url: str | None = None) -> dict:
    """Best-effort manifest block for gather(): the block verified at this process's entry for
    that port (no second process walk per manifest), else a fresh check, else {pid: None, error}."""
    try:
        port = _port_from_base(base_url)
    except Exception as e:  # noqa: BLE001
        return {"pid": None, "config": None, "port": None,
                "error": _scrub(f"{type(e).__name__}: {str(e)[:300]}")}
    if port in _LAST_VERIFIED:
        return dict(_LAST_VERIFIED[port])
    try:
        return assert_served_config(base_url)
    except Exception as e:  # noqa: BLE001 — never block a run on provenance; entry points refuse
        return {"pid": None, "config": None, "port": port,
                "error": _scrub(f"{type(e).__name__}: {str(e)[:300]}")}


def opencode_router_base(cwd=None, env=None, provider: str = "mlx-local") -> str:
    """The base URL opencode will ACTUALLY send to, from `opencode debug config` run in the child's
    cwd with the child's env — i.e. every source opencode merges (global json/jsonc, config dir,
    ancestor project configs, inline content) resolved by opencode itself, not by us. The three
    override variables are refused outright: the probes record the SHIPPED config's hash as
    scaffold identity, so a run under an override would carry false scaffold provenance."""
    env = dict(env if env is not None else os.environ)
    for var in ("OPENCODE_CONFIG_CONTENT", "OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR"):
        if env.get(var):
            raise ServedConfigError(f"M50 tripwire: {var} is set; opencode would load a config override "
                                    f"that the recorded scaffold identity does not describe. Unset it "
                                    f"(probes run the shipped/global scaffold only).")
    try:
        r = subprocess.run(["opencode", "debug", "config"], cwd=str(cwd) if cwd else None, env=env,
                           capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    except Exception as e:  # noqa: BLE001
        raise ServedConfigError(f"M50 tripwire: cannot run `opencode debug config`: {type(e).__name__}: {e}")
    out = r.stdout or ""
    try:
        data = json.loads(out[out.index("{"):])
        base = data["provider"][provider]["options"]["baseURL"]
    except Exception as e:  # noqa: BLE001
        raise ServedConfigError(f"M50 tripwire: `opencode debug config` (rc={r.returncode}) gave no "
                                f"{provider!r} baseURL: {type(e).__name__}: {e}; stderr {r.stderr[-300:]!r}")
    # An empty/non-string baseURL is NOT "default 8000": opencode then falls back to the model's
    # `api.url` — a destination this tripwire does not resolve. Refuse rather than guess.
    if not isinstance(base, str) or not base.lower().startswith(("http://", "https://")):
        raise ServedConfigError(f"M50 tripwire: opencode's resolved {provider!r} baseURL is {base!r} "
                                f"(empty/non-http); its effective destination would come from a model "
                                f"`api.url` fallback the tripwire cannot bind. Fix the opencode config.")
    return base


def assert_opencode_destination(cwd, env, expected_pid: int) -> str:
    """Per opencode invocation: the destination opencode resolves in THIS cwd/env must be owned by
    the router verified at entry (`expected_pid`). Returns the base URL."""
    base = opencode_router_base(cwd, env)
    blk = assert_served_config(base, env=env)           # the CHILD's proxy settings apply
    if blk["pid"] != expected_pid:
        raise ServedConfigError(f"M50 tripwire: opencode in {str(cwd)!r} resolves {base!r}, owned by pid "
                                f"{blk['pid']}, not the router verified at entry (pid {expected_pid}).")
    return base


def _runtime_block(runtime: dict = None, model: str = None,
                   registry_path: str | None = None) -> dict:
    """The runtime block: detected APC state, the registry's draft/suffix state, plus whatever knobs
    the caller declares (the agentic axes pass max_turns/deadline_s/loop_guard/client/edit_format).

    `model` is required to read the draft state and is threaded from every caller. A caller that
    passes no model gets draft_kind "unknown" — honest, and a wildcard — rather than a guessed "off",
    because guessing here would re-create exactly the silent-exoneration bug v3 fixes.
    """
    st = apc_state()
    block = {"apc_enabled": st["apc_enabled"], "apc_source": st["source"]}
    block.update(registry_draft(model, registry_path) if model
                 else {"draft_kind": "unknown", "draft_source": "no-model-given"})
    block.update(session_retention_state())
    for key, fn in (("attention_policy", registry_attention_policy),
                    ("lazy_prompt_embeddings", registry_lazy_prompt_embeddings),
                    ("mtp_verify_scan", registry_mtp_verify_scan)):
        block.update(fn(model, registry_path) if model
                     else {key: "unknown", key + "_source": "no-model-given"})
    if runtime:
        clash = sorted(k for k in runtime
                       if k in _SERVING_CONTROLS or (k.endswith("_source")
                                                     and k[:-len("_source")] in _SERVING_CONTROLS))
        if clash:  # D3: an observed serving control is never overridable by a caller
            raise ServingStateError(f"M58: runtime override of observed serving control(s) {clash}; "
                                    f"refusing — those values come only from the worker/registry.")
        block.update(_portable_deep(runtime))   # no absolute home/workdir path reaches a manifest
    return block


def current_manifest_lite(model: str, profile: str = "production",
                          registry_path: str | None = None,
                          overrides: dict = None, runtime: dict = None) -> dict:
    """A cheap manifest (sampling + KV only, no quant_info snapshot scan) for the resume
    compatibility check — same shape config_fingerprint consumes. `overrides` are the CLI
    sampling overrides (e.g. --temperature) layered on the profile; they MUST be applied here
    so the fingerprint reflects the ACTUAL config (else an OFAT sweep silently resumes results
    produced at a different temperature/budget)."""
    sampling = model_params.params_for(model, profile=profile)
    if overrides:
        sampling.update(overrides)
    return {"sampling_profile": profile,
            "sampling": sampling,
            "kv": registry_kv(model, registry_path) or {},
            # The git block is REQUIRED here, not optional: the fingerprint now compares the deployed
            # code sha, so a `current` manifest without it reads None and makes every existing row
            # look stale forever — `--clean-stale` would delete the corpus on every run.
            "git": _git_shas(),
            "fingerprint_version": FINGERPRINT_VERSION,
            "runtime": _runtime_block(runtime, model=model, registry_path=registry_path)}


def build_manifest(*, model, box, ts, git_shas, kv, quant, sampling, runtime=None) -> dict:
    """Pure assembly of a provenance record from its parts."""
    scan = (runtime or {}).get("mtp_verify_scan")
    if scan is None or scan == "unknown":  # D3: a manifest never stamps an unresolved scan
        raise ServingStateError("M58: build_manifest needs a RESOLVED mtp_verify_scan in the "
                                "runtime block (missing or 'unknown'); refusing.")
    check_mtp_verify_scan_value(scan, "manifest runtime block")
    return {
        "model": model,
        "box": box,
        "timestamp": ts,
        "git": git_shas,
        "kv": kv,
        "quant": quant,
        "sampling": sampling,
        "fingerprint_version": FINGERPRINT_VERSION,
        "runtime": runtime if runtime is not None else {},
    }


# --------------------------------------------------------------- real gatherers
def _box() -> str:
    """Box label for the manifest. Env wins; else the machine-local config.sh is parsed directly.

    The fallback exists because the box guard was ANTI-CORRELATED for the entire campaign:
    50 of 54 manifests said "local" — MLX_BOX only existed in shells that happened to source
    config.sh, so the one guard built for the apples-to-apples rule never fired. A bare
    `nohup python run.py` must still stamp the right box.
    """
    env = os.environ.get("MLX_BOX") or os.environ.get("HOSTNAME")
    if env:
        return env
    cfg = os.path.join(os.environ.get("XDG_CONFIG_HOME")
                       or os.path.expanduser("~/.config"), "mlx_local_stack", "config.sh")
    try:
        with open(cfg) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export MLX_BOX=") or line.startswith("MLX_BOX="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
    except OSError:
        pass
    return "local"


def _git_shas() -> dict:
    """Stack HEAD + submodule shas, resolved from the REPO ROOT rather than the CWD.

    CWD-independent for the same reason bench/paths.py exists: run from `benchmark/` these commands
    silently returned None, so the git block went missing and — now that the deployed code sha is part
    of the fingerprint — every row would have compared as stale and `--clean-stale` would delete the
    corpus.
    """
    root = str(paths.repo_root())

    def _run(args, cwd=None):
        try:
            return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL,
                                           cwd=cwd or root).strip()
        except Exception:  # noqa: BLE001
            return None
    subs = {}
    status = _run(["git", "submodule", "status"]) or ""
    for line in status.splitlines():
        parts = line.strip().lstrip("+-U").split()
        if len(parts) >= 2:
            subs[parts[1]] = parts[0]

    # C47 (2026-09-03): serving_path hashes the tree at each submodule's CHECKED-OUT worktree
    # commit, read via a dedicated `git -C <sub> rev-parse HEAD` rather than reusing the `subs`
    # dict above. `git submodule status` ALSO reports the checked-out worktree sha (not, as an
    # earlier draft of this comment claimed, the parent's recorded pointer — that pointer is
    # `git ls-tree HEAD -- <sub>` in the PARENT, a different, genuinely stale value when a
    # worktree is pinned without a matching `git submodule update`). The dedicated call exists so
    # this does not depend on `submodule status`'s prefix-char text format, and keeps working
    # unchanged if a submodule is ever addressed without being a REGISTERED submodule of the
    # parent (`submodule status` would report nothing for it at all).
    serving_path = {}
    for sub in ("src/mlx-vlm", "src/mlx-serve"):
        sub_dir = os.path.join(root, sub)
        head = _run(["git", "rev-parse", "HEAD"], cwd=sub_dir)
        serving_path[sub] = serving_path_hash(sub_dir, head) if head else None

    return {"stack_head": _run(["git", "rev-parse", "HEAD"]), "submodules": subs,
            "serving_path": serving_path}


def _registry_state(registry_path: str) -> dict:
    """Hash of the EXACT registry bytes this run resolved against, plus whether they match the
    committed version (operator ruling 5, 2026-08-17). The worker's registry is permanently,
    intentionally dirty (caps), so "which main_models.yaml produced this row" was unanswerable
    from the manifest alone — the same provenance gap the scp era had. RECORD-ONLY: never part
    of the fingerprint, because everything it could change (caps, sampling, kv, draft) is
    fingerprinted directly, and hashing comments/whitespace into the guard would manufacture
    false staleness."""
    try:
        sha = hashlib.sha256(open(registry_path, "rb").read()).hexdigest()
    except OSError:
        return {"sha256": None, "dirty": "unknown"}
    dirty = "unknown"
    try:
        root = str(paths.repo_root())
        if os.path.realpath(registry_path) == os.path.realpath(os.path.join(root, "main_models.yaml")):
            rc = subprocess.run(["git", "diff", "--quiet", "--", "main_models.yaml"],
                                cwd=root, stderr=subprocess.DEVNULL).returncode
            dirty = bool(rc)
    except Exception:  # noqa: BLE001 — never block a run on provenance
        pass
    return {"sha256": sha, "dirty": dirty}


def _resolve_snapshot(hf_path):
    """Resolve an hf_path (repo id or local dir) to a local snapshot dir for quant_info.

    P8 (2026-09-02): registry_kv() hands us the O34 `$HOME/...` form; expand it (and `~`)
    before the isdir test, else every local-path model resolves to None and is stamped
    `quant: {}`. The manifest's WRITTEN hf_path stays $HOME-form — only the lookup expands."""
    if not hf_path:
        return None
    local = os.path.expandvars(os.path.expanduser(hf_path))
    if os.path.isdir(local):
        return local
    import glob
    cache = os.path.expanduser(
        "~/.cache/huggingface/hub/models--" + hf_path.replace("/", "--"))
    snaps = sorted(glob.glob(os.path.join(cache, "snapshots", "*")))
    for s in snaps:
        if os.path.exists(os.path.join(s, "config.json")):
            return s
    return None


def gather(model: str, registry_path: str | None = None,
           profile: str = "production", overrides: dict = None, runtime: dict = None,
           tune: str | None = None, router: dict | None = None) -> dict:
    """Assemble the real provenance manifest for ``model`` on this box. `router` is the M50 block
    the caller verified for ITS destination (opencode's baseURL, not `client.BASE`); absent, the
    block verified in this process for `client.BASE` is used. `overrides` are the
    CLI sampling overrides layered on the profile, recorded so the manifest matches what
    generation actually used. `tune` (docs/superpowers/specs/2026-08-17-tune-encoding-migration-
    design.md) is stamped as a top-level `tune` field when given; absent (None, the default)
    means the `deployed` tune and the field is OMITTED entirely, rather than written as null, so
    existing readers see no new key. `tune` is a KEY, never provenance: it is NOT part of the
    fingerprint (config_fingerprint reads a fixed set of keys that does not include it) — the
    resolved config it names a delta from is already fingerprinted."""
    kv = registry_kv(model, registry_path) or {}
    quant = {}
    snap = _resolve_snapshot(kv.get("hf_path"))
    if snap:
        try:
            qi = quant_info.quant_info(snap)
            quant = {k: qi[k] for k in ("effective_bits", "footprint_gb", "mixed",
                                        "nominal_bits", "bit_histogram") if k in qi}
        except Exception:  # noqa: BLE001 — never block a run on provenance
            quant = {"note": "quant_info failed"}
    try:
        sampling = model_params.params_for(model, profile=profile)
    except Exception:  # noqa: BLE001
        sampling = {}
    if overrides:
        sampling.update(overrides)
    man = build_manifest(model=model, box=_box(), ts=int(time.time()),
                         git_shas=_git_shas(), kv=kv, quant=quant, sampling=sampling,
                         runtime=_runtime_block(runtime, model=model,
                                                registry_path=registry_path))
    man["sampling_profile"] = profile
    man["registry"] = _registry_state(str(paths.registry_path())
                                      if registry_path is None else registry_path)
    from . import client as _client
    man["router"] = dict(router) if router is not None else router_block(_client.BASE)
    if tune is not None:
        man["tune"] = tune
    return man


def write(model: str, bench: str, registry_path: str | None = None,
          profile: str = "production", overrides: dict = None, runtime: dict = None,
          tune: str | None = None, router: dict | None = None) -> dict:
    """Gather + write results/<model>/<bench>[.tune].manifest.json. Returns the manifest."""
    man = gather(model, registry_path, profile=profile, overrides=overrides,
                 runtime=runtime, tune=tune, router=router)
    path = generate.result_path(model, bench, tune=tune).with_suffix(".manifest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(man, indent=2))
    return man
