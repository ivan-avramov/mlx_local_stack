"""Extract the FULL quantization numbers from a local MLX model snapshot.

Reports footprint, nominal bits/group_size/mode, whether the quant is MIXED (UD/OptiQ
style), the per-bit module histogram, and — the quality-relevant number — the
PARAM-WEIGHTED effective bits-per-weight, for comparing mixed quants (UD/OptiQ) against
uniform ones at the same nominal label.

Per-module logical parameter counts are derived from each quantized module's ``.scales``
tensor shape (``[out, n_groups]`` -> ``in_features = n_groups * group_size``), read from
the safetensors header only (no tensor data is loaded). Modules without a ``.scales``
tensor (norms, unquantized embeddings, etc.) are excluded from the bits average.
"""
import glob
import json
import os
import struct


def _read_st_header(path: str) -> dict:
    """Parse a safetensors header (the leading u64 length + JSON), no tensor data."""
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        hdr = json.loads(f.read(n))
    hdr.pop("__metadata__", None)
    return hdr


def quant_info(model_dir: str) -> dict:
    """Full quant numbers for a local MLX snapshot directory.

    Returns: footprint_gb, nominal_bits, group_size, mode, mixed,
    bit_histogram {bits: module_count}, effective_bits (param-weighted),
    n_quant_modules, total_quant_params.
    """
    with open(os.path.join(model_dir, "config.json")) as f:
        cfg = json.load(f)
    q = cfg.get("quantization") or {}
    nominal = q.get("bits")
    group_size = q.get("group_size")
    mode = q.get("mode")
    per_mod = {k: v for k, v in q.items() if isinstance(v, dict)}

    sts = sorted(glob.glob(os.path.join(model_dir, "*.safetensors")))
    footprint = sum(os.path.getsize(p) for p in sts)

    shapes: dict = {}
    for p in sts:
        shapes.update(_read_st_header(p))

    total_p = 0
    total_bits_p = 0
    hist: dict = {}
    n_mods = 0
    for name, meta in shapes.items():
        if not name.endswith(".scales"):
            continue
        shape = meta.get("shape") or []
        if len(shape) < 2:
            continue
        mod = name[: -len(".scales")]
        out, n_groups = shape[0], shape[1]
        mcfg = per_mod.get(mod, {})
        gs = mcfg.get("group_size", group_size)
        bits = mcfg.get("bits", nominal)
        if gs is None or bits is None:
            continue
        params = out * n_groups * gs
        total_p += params
        total_bits_p += params * bits
        hist[bits] = hist.get(bits, 0) + 1
        n_mods += 1

    return {
        "footprint_bytes": footprint,
        "footprint_gb": round(footprint / 1e9, 2),
        "nominal_bits": nominal,
        "group_size": group_size,
        "mode": mode,
        "mixed": len(hist) > 1,
        "bit_histogram": dict(sorted(hist.items(), reverse=True)),
        "effective_bits": (total_bits_p / total_p) if total_p else None,
        "n_quant_modules": n_mods,
        "total_quant_params": total_p,
    }
