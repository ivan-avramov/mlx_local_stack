"""Provenance manifest — stamp every results file with the EXACT config it was produced
under, so results can never be silently compared across boxes / code versions / quant or
KV configs. This enforces the apples-to-apples rule and powers the quality-vs-bits study
(each result is tied to its effective bits-per-weight + KV config + sampling).

Manifests are written next to results (which are gitignored), so the box label here never
reaches the public repo; we still prefer an explicit MLX_BOX label over the raw hostname.
"""
import json
import os
import subprocess
import time

import yaml

from . import generate, model_params, quant_info
from . import paths


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
                "hf_path": e.get("hf_path"),
                "kv_bits": e.get("kv_bits", 0),
                "kv_quant_scheme": e.get("kv_quant_scheme"),
                "quantized_kv_start": e.get("quantized_kv_start"),
                "prefill_step_size": e.get("prefill_step_size"),
                "max_kv_cache_size": e.get("max_kv_cache_size"),
            }
    return None


# The output-determining slice of a manifest. If any of these differ, existing results were
# produced under a different distribution and CANNOT be mixed with new ones via resume.
_FINGERPRINT_SAMPLING = ("temperature", "top_p", "top_k", "min_p", "presence_penalty",
                         "repetition_penalty", "thinking_budget", "max_tokens", "enable_thinking")

# v2 additions: RUNTIME knobs that change results without touching sampling.
#   apc_enabled  — prefix caching (runserver.sh sets it; the AGENTS.md bench recipe does not)
#   draft_kind   — suffix/speculative decoding
#   max_turns / deadline_s / loop_guard / client / edit_format — the agentic-axis knobs
# `samples` is deliberately ABSENT: drawing k samples does not change the distribution each
# sample comes from, and including it would mark every existing single-sample result stale.
_FINGERPRINT_RUNTIME = ("apc_enabled", "draft_kind", "max_turns", "deadline_s", "loop_guard",
                        "client", "edit_format")

FINGERPRINT_VERSION = 2


def config_fingerprint(manifest, version: int | None = None):
    """The comparable slice of a manifest, at fingerprint `version`.

    v1 = sampling profile + key sampling params + KV bits (what the pre-v2 harness compared).
    v2 = v1 + the runtime block.

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


def _runtime_block(runtime: dict = None) -> dict:
    """The v2 runtime block: detected APC state plus whatever knobs the caller declares (the
    agentic axes pass max_turns/deadline_s/loop_guard/client/edit_format through here)."""
    st = apc_state()
    block = {"apc_enabled": st["apc_enabled"], "apc_source": st["source"]}
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
            "fingerprint_version": FINGERPRINT_VERSION,
            "runtime": _runtime_block(runtime)}


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
    return os.environ.get("MLX_BOX") or os.environ.get("HOSTNAME") or "local"


def _git_shas() -> dict:
    def _run(args):
        try:
            return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:  # noqa: BLE001
            return None
    subs = {}
    status = _run(["git", "submodule", "status"]) or ""
    for line in status.splitlines():
        parts = line.strip().lstrip("+-U").split()
        if len(parts) >= 2:
            subs[parts[1]] = parts[0]
    return {"stack_head": _run(["git", "rev-parse", "HEAD"]), "submodules": subs}


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
           profile: str = "production", overrides: dict = None, runtime: dict = None) -> dict:
    """Assemble the real provenance manifest for ``model`` on this box. `overrides` are the
    CLI sampling overrides layered on the profile, recorded so the manifest matches what
    generation actually used."""
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
                         runtime=_runtime_block(runtime))
    man["sampling_profile"] = profile
    return man


def write(model: str, bench: str, registry_path: str | None = None,
          profile: str = "production", overrides: dict = None, runtime: dict = None) -> dict:
    """Gather + write results/<model>/<bench>.manifest.json. Returns the manifest."""
    man = gather(model, registry_path, profile=profile, overrides=overrides,
                 runtime=runtime)
    path = generate.result_path(model, bench).with_suffix(".manifest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(man, indent=2))
    return man
