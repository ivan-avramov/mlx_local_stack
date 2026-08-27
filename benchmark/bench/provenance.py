"""Provenance manifest — stamp every results file with the EXACT config it was produced
under, so results can never be silently compared across boxes / code versions / quant or
KV configs. This enforces the apples-to-apples rule and powers the quality-vs-bits study
(each result is tied to its effective bits-per-weight + KV config + sampling).

Manifests are written next to results (which are gitignored), so the box label here never
reaches the public repo; we still prefer an explicit MLX_BOX label over the raw hostname.
"""
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


def registry_draft(model: str, registry_path: str | None = None,
                   worker_lookup=_worker_cmdline) -> dict:
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
            # When a live worker is observably serving THIS model (its `--model` carries the
            # entry's hf_path), its cmdline is the truth: a mismatch REFUSES the run rather
            # than record false provenance on either side. A worker for another model, or no
            # worker at all, says nothing — the yaml answer stands, source "registry".
            cmd = worker_lookup() if worker_lookup else None
            hf = e.get("hf_path") or ""
            if cmd and hf and hf in cmd:
                m = re.search(r"--draft-kind\s+(\S+)", cmd)
                served = m.group(1) if m else "off"
                if served != ans["draft_kind"]:
                    raise RuntimeError(
                        f"C35 tripwire: registry {registry_path!r} declares draft_kind="
                        f"{ans['draft_kind']!r} for {model!r} but the live worker serves "
                        f"draft_kind={served!r}. Launch the driver with MLX_SERVE_CONFIG "
                        f"pointed at the served registry/overlay; refusing to record false "
                        f"draft provenance.")
                ans["draft_source"] = "registry+worker"
            return ans
    return {"draft_kind": "unknown", "draft_source": "model-not-in-registry"}


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
_FINGERPRINT_KV_EXTRA = ("hf_path", "kv_quant_scheme", "quantized_kv_start", "prefill_step_size")

# v3 (2026-08-16): draft/suffix state is POPULATED, not merely named. See registry_draft().
# v4 (2026-08-17): the kv_extra slice above joins the resume guard.
FINGERPRINT_VERSION = 4


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
        "code": {k: ((manifest.get("git") or {}).get("submodules") or {}).get(k)
                 for k in ("src/mlx-vlm", "src/mlx-serve")},
    }
    if version >= 2:
        r = manifest.get("runtime") or {}
        fp["runtime"] = {k: r.get(k) for k in _FINGERPRINT_RUNTIME}
    if version >= 4:
        fp["kv_extra"] = {k: kv.get(k) for k in _FINGERPRINT_KV_EXTRA}
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
    if v < 2:
        return a == b
    ra, rb = a.pop("runtime", {}), b.pop("runtime", {})
    return a == b and _runtime_compatible(ra, rb)


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
    if runtime:
        block.update(runtime)
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

    def _run(args):
        try:
            return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL,
                                           cwd=root).strip()
        except Exception:  # noqa: BLE001
            return None
    subs = {}
    status = _run(["git", "submodule", "status"]) or ""
    for line in status.splitlines():
        parts = line.strip().lstrip("+-U").split()
        if len(parts) >= 2:
            subs[parts[1]] = parts[0]
    return {"stack_head": _run(["git", "rev-parse", "HEAD"]), "submodules": subs}


def _registry_state(registry_path: str) -> dict:
    """Hash of the EXACT registry bytes this run resolved against, plus whether they match the
    committed version (operator ruling 5, 2026-08-17). The worker's registry is permanently,
    intentionally dirty (caps), so "which main_models.yaml produced this row" was unanswerable
    from the manifest alone — the same provenance gap the scp era had. RECORD-ONLY: never part
    of the fingerprint, because everything it could change (caps, sampling, kv, draft) is
    fingerprinted directly, and hashing comments/whitespace into the guard would manufacture
    false staleness."""
    import hashlib
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
    """Resolve an hf_path (repo id or local dir) to a local snapshot dir for quant_info."""
    if hf_path and os.path.isdir(hf_path):
        return hf_path
    if not hf_path:
        return None
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
           tune: str | None = None) -> dict:
    """Assemble the real provenance manifest for ``model`` on this box. `overrides` are the
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
    if tune is not None:
        man["tune"] = tune
    return man


def write(model: str, bench: str, registry_path: str | None = None,
          profile: str = "production", overrides: dict = None, runtime: dict = None,
          tune: str | None = None) -> dict:
    """Gather + write results/<model>/<bench>[.tune].manifest.json. Returns the manifest."""
    man = gather(model, registry_path, profile=profile, overrides=overrides,
                 runtime=runtime, tune=tune)
    path = generate.result_path(model, bench, tune=tune).with_suffix(".manifest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(man, indent=2))
    return man
