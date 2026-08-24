"""Graft a vision tower onto a text-only MLX quantized checkpoint (operator-approved 2026-08-23).

The pick `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` was converted language-model-only (one-image
probe 2026-08-23: BLIND, tower reshape crash). Its parent
`TeichAI/Qwen3.6-27B-Claude-Opus-Reasoning-Distill-v2` ships the bf16 tower. This script:

  1. copies the pick's files VERBATIM (trunk shards byte-identical — verified by md5 in-script;
     mismatch is a hard stop);
  2. extracts the source's `model.visual.*` tensors, renames them `vision_tower.*` (the fork's
     own sanitize mapping, `mlx_vlm/models/qwen3_5/qwen3_5.py`), quantizes tower Linear weights
     to 8-bit affine g64 (operator-approved; conv/norm/bias/pos-embed stay bf16 — mirrors what
     `nn.quantize` would select), and writes them to a new `model-vision.safetensors` shard;
  3. extends `model.safetensors.index.json` and `config.json` (vision_config from the source;
     per-module 8-bit entries added to `quantization` and `quantization_config`);
  4. copies the source's processor files (preprocessor/processor/video_preprocessor configs).

The TEXT TRUNK IS NEVER REWRITTEN — the trunk shards are copied files, and the script fails
loud if their checksums differ. Run under `.venv-bench` (needs mlx).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import mlx.core as mx

TOWER_SRC_PREFIX = "model.visual."
TOWER_DST_PREFIX = "vision_tower."
VISION_SHARD = "model-vision.safetensors"
PROCESSOR_FILES = ("preprocessor_config.json", "processor_config.json",
                   "video_preprocessor_config.json")


def _md5(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_index(d: Path) -> dict:
    return json.loads((d / "model.safetensors.index.json").read_text())


def graft(source: Path, pick: Path, out: Path, bits: int, group_size: int) -> int:
    out.mkdir(parents=True, exist_ok=False)

    # -- 1. copy the pick verbatim ------------------------------------------------
    pick_index = _load_index(pick)
    trunk_shards = sorted(set(pick_index["weight_map"].values()))
    copied: dict[str, str] = {}
    for name in sorted(p.name for p in pick.iterdir() if p.name != "README.md"):
        src_p = pick / name
        if src_p.is_dir():
            shutil.copytree(src_p, out / name)
        else:
            shutil.copy2(src_p, out / name)
        if name in trunk_shards:
            copied[name] = _md5(src_p)

    # -- 2. tower tensors from the source -----------------------------------------
    src_index = _load_index(source)
    tower_keys = {k: v for k, v in src_index["weight_map"].items()
                  if k.startswith(TOWER_SRC_PREFIX)}
    if not tower_keys:
        sys.exit(f"STOP: no {TOWER_SRC_PREFIX}* tensors in {source}")
    tensors: dict[str, mx.array] = {}
    for shard in sorted(set(tower_keys.values())):
        loaded = mx.load(str(source / shard))
        for k in [k for k, s in tower_keys.items() if s == shard]:
            tensors[TOWER_DST_PREFIX + k[len(TOWER_SRC_PREFIX):]] = loaded[k]

    quant_entries: dict[str, dict] = {}
    out_tensors: dict[str, mx.array] = {}
    n_q = 0
    for key, w in sorted(tensors.items()):
        if (key.endswith(".weight") and w.ndim == 2
                and w.shape[0] % group_size == 0 and w.shape[1] % group_size == 0):
            wq, scales, biases = mx.quantize(w, group_size=group_size, bits=bits)
            mod = key[: -len(".weight")]
            out_tensors[key] = wq
            out_tensors[mod + ".scales"] = scales
            out_tensors[mod + ".biases"] = biases
            quant_entries[mod] = {"bits": bits, "group_size": group_size}
            n_q += 1
        else:
            out_tensors[key] = w
    mx.save_safetensors(str(out / VISION_SHARD), out_tensors)

    # -- 3. index + config ---------------------------------------------------------
    new_index = _load_index(out)
    for k in out_tensors:
        new_index["weight_map"][k] = VISION_SHARD
    meta = new_index.setdefault("metadata", {})
    if "total_size" in meta:
        meta["total_size"] += (out / VISION_SHARD).stat().st_size
    (out / "model.safetensors.index.json").write_text(json.dumps(new_index, indent=2))

    cfg = json.loads((out / "config.json").read_text())
    src_cfg = json.loads((source / "config.json").read_text())
    if "vision_config" not in src_cfg:
        sys.exit("STOP: source config has no vision_config")
    cfg["vision_config"] = src_cfg["vision_config"]
    cfg["language_model_only"] = False
    for qkey in ("quantization", "quantization_config"):
        if isinstance(cfg.get(qkey), dict):
            cfg[qkey].update(quant_entries)
    (out / "config.json").write_text(json.dumps(cfg, indent=2))

    for name in PROCESSOR_FILES:
        if (source / name).exists():
            shutil.copy2(source / name, out / name)
        else:
            print(f"note: source has no {name}")

    # -- 4. trunk bit-identity, or stop -------------------------------------------
    bad = [s for s in trunk_shards if _md5(out / s) != copied[s]]
    if bad:
        sys.exit(f"STOP: trunk shard(s) NOT bit-identical after graft: {bad}")
    print(f"OK: {len(trunk_shards)} trunk shards bit-identical (md5) — "
          f"{len(tensors)} tower tensors written ({n_q} modules quantized to "
          f"{bits}-bit g{group_size}), shard {VISION_SHARD} "
          f"{(out / VISION_SHARD).stat().st_size / 1e9:.2f} GB")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, type=Path, help="bf16 parent snapshot dir")
    ap.add_argument("--pick", required=True, type=Path, help="quantized text-only snapshot dir")
    ap.add_argument("--out", required=True, type=Path, help="output dir (must not exist)")
    ap.add_argument("--bits", type=int, default=8)
    ap.add_argument("--group-size", type=int, default=64)
    a = ap.parse_args()
    return graft(a.source.resolve(), a.pick.resolve(), a.out.resolve(), a.bits, a.group_size)


if __name__ == "__main__":
    raise SystemExit(main())
