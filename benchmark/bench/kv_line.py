"""P475 (R2, R22): the worker's `KV cache resolved:` log line, parsed and checked against a KV arm.

The fork (`mlx_vlm/server/app.py`) logs once per load: `KV cache resolved: kv_bits=%r kv_key_bits=%r kv_value_bits=%r
kv_key_scheme=%r kv_value_scheme=%r kv_quant_scheme=%r kv_group_size=%r quantized_kv_start=%r TQ_KV_QUANT_MODE=%r`.
Standard library only.
"""
from __future__ import annotations

import ast
import re

MARKER = "KV cache resolved:"
FIELDS = ("kv_bits", "kv_key_bits", "kv_value_bits", "kv_key_scheme", "kv_value_scheme", "kv_quant_scheme", "kv_group_size",
          "quantized_kv_start", "TQ_KV_QUANT_MODE")
SPLIT_FIELDS = ("kv_key_bits", "kv_value_bits", "kv_key_scheme", "kv_value_scheme")
GROUP_SIZE = 64
_PAIR = re.compile(r"(?<!\S)(\w+)=('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|\S+)")

# arm -> (kv_bits, kv_quant_scheme); None bits = native16 (scheme not compared)
ARM_FORMATS = {
    "N16": (0, None),
    "AF8": (8, "uniform"),
    "TQ8": (8, "turboquant"),
    "AF4": (4, "uniform"),
    "TQ4": (4, "turboquant"),
    "TQ4-OFF": (4, "turboquant"),
}


class KVLineError(ValueError):
    """No `KV cache resolved:` line, or a malformed one."""


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def parse_kv_line(text_or_lines) -> dict:
    """The LAST `KV cache resolved:` line of `text_or_lines` (a string or a list of lines), every field as its Python literal.
    Refuses (KVLineError) when no such line exists, a field is missing or duplicated, or a value is not a literal."""
    if isinstance(text_or_lines, (bytes, bytearray)):
        text_or_lines = text_or_lines.decode("utf-8", errors="replace")
    if isinstance(text_or_lines, str):
        lines = text_or_lines.splitlines()
    elif isinstance(text_or_lines, (list, tuple)):
        lines = []
        for item in text_or_lines:
            if not isinstance(item, str):
                raise KVLineError(f"not a log line: {type(item).__name__}")
            lines.extend(item.splitlines() or [item])
    else:
        raise KVLineError(f"not log text: {type(text_or_lines).__name__}")
    hits = [ln for ln in lines if MARKER in ln]
    if not hits:
        raise KVLineError("no `KV cache resolved:` line")
    body = hits[-1].split(MARKER, 1)[1]
    parsed = {}
    for key, raw in _PAIR.findall(body):
        if key not in FIELDS:
            continue
        if key in parsed:
            raise KVLineError(f"field {key} appears twice")
        try:
            parsed[key] = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            raise KVLineError(f"field {key}: {raw!r} is not a Python literal") from None
    missing = [k for k in FIELDS if k not in parsed]
    if missing:
        raise KVLineError(f"malformed `KV cache resolved:` line: missing {missing}")
    return {k: parsed[k] for k in FIELDS}


def expected_kv(arm) -> dict:
    """The resolved KV fields `arm` must show. Native (N16): `kv_bits` None or 0, nothing else compared."""
    if arm not in ARM_FORMATS:
        raise ValueError(f"unknown arm {arm!r}")
    bits, scheme = ARM_FORMATS[arm]
    if not bits:
        return dict(native=True, kv_bits=0)
    want = dict(native=False, kv_bits=bits, kv_quant_scheme=scheme, kv_group_size=GROUP_SIZE, quantized_kv_start=0,
                **{k: None for k in SPLIT_FIELDS})
    if scheme == "turboquant":
        want["TQ_KV_QUANT_MODE"] = "mse"
    return want


def kv_line_problems(parsed, arm) -> list:
    """Every disagreement between a parsed line and `arm`'s expected KV state (empty = engaged as the arm)."""
    if not isinstance(parsed, dict):
        return ["no parsed KV line"]
    want = expected_kv(arm)
    problems = []
    bits = parsed.get("kv_bits")
    if want["native"]:
        if not (bits is None or (_number(bits) and bits == 0)):
            problems.append(f"kv_bits={bits!r} (native: None or 0)")
        return problems
    if not (_number(bits) and bits == want["kv_bits"]):
        problems.append(f"kv_bits={bits!r} != {want['kv_bits']}")
    if parsed.get("kv_quant_scheme") != want["kv_quant_scheme"]:
        problems.append(f"kv_quant_scheme={parsed.get('kv_quant_scheme')!r} != {want['kv_quant_scheme']!r}")
    for k in SPLIT_FIELDS:
        if parsed.get(k) is not None:
            problems.append(f"{k}={parsed.get(k)!r} (a non-split arm: None)")
    gs = parsed.get("kv_group_size")
    if not (_number(gs) and gs == GROUP_SIZE):
        problems.append(f"kv_group_size={gs!r} != {GROUP_SIZE}")
    qs = parsed.get("quantized_kv_start")
    if not (_number(qs) and qs == 0):
        problems.append(f"quantized_kv_start={qs!r} (need numeric 0)")
    if "TQ_KV_QUANT_MODE" in want and parsed.get("TQ_KV_QUANT_MODE") != want["TQ_KV_QUANT_MODE"]:
        problems.append(f"TQ_KV_QUANT_MODE={parsed.get('TQ_KV_QUANT_MODE')!r} != 'mse'")
    return problems
