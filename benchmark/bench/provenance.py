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


def registry_kv(model: str, registry_path: str):
    """KV + path config for ``model`` from a main_models.yaml-style registry, or None."""
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


def build_manifest(*, model, box, ts, git_shas, kv, quant, sampling) -> dict:
    """Pure assembly of a provenance record from its parts."""
    return {
        "model": model,
        "box": box,
        "timestamp": ts,
        "git": git_shas,
        "kv": kv,
        "quant": quant,
        "sampling": sampling,
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


def gather(model: str, registry_path: str = "main_models.yaml") -> dict:
    """Assemble the real provenance manifest for ``model`` on this box."""
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
        sampling = model_params.params_for(model)
    except Exception:  # noqa: BLE001
        sampling = {}
    return build_manifest(model=model, box=_box(), ts=int(time.time()),
                          git_shas=_git_shas(), kv=kv, quant=quant, sampling=sampling)


def write(model: str, bench: str, registry_path: str = "main_models.yaml") -> dict:
    """Gather + write results/<model>/<bench>.manifest.json. Returns the manifest."""
    man = gather(model, registry_path)
    path = generate.result_path(model, bench).with_suffix(".manifest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(man, indent=2))
    return man
