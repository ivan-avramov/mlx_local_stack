"""Tests for bench.quant_info — extracting the FULL quant numbers from a local MLX
snapshot (footprint, nominal bits, mixed recipe, param-weighted effective bits-per-weight).

The effective-bits math is the quality-relevant number for comparing UD/OptiQ mixed quants
against uniform ones: a per-module nominal-bits average weighted by each module's logical
parameter count, derived from the `.scales` tensor shape ([out, n_groups] -> in = n_groups *
group_size) without loading any tensor data.
"""
import json
import struct

import bench.quant_info as QI


_DT_BYTES = {"U32": 4, "F16": 2, "F32": 4, "I8": 1, "U8": 1}


def _write_safetensors(path, tensors):
    """tensors: {name: {'dtype': str, 'shape': [..]}} -> writes a valid (header + zero-data)
    safetensors file so quant_info can parse shapes from the header and size from the file."""
    header, offset = {}, 0
    for name, t in tensors.items():
        n = 1
        for s in t["shape"]:
            n *= s
        nbytes = n * _DT_BYTES[t["dtype"]]
        header[name] = {"dtype": t["dtype"], "shape": list(t["shape"]),
                        "data_offsets": [offset, offset + nbytes]}
        offset += nbytes
    hj = json.dumps(header).encode()
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(hj)))
        f.write(hj)
        f.write(b"\x00" * offset)


def _make_snapshot(tmp_path):
    # Mixed quant: default 4-bit, group_size 64; modA overridden to 8-bit (OptiQ/UD style).
    cfg = {
        "model_type": "test",
        "quantization": {
            "group_size": 64, "bits": 4, "mode": "affine",
            "modA": {"bits": 8, "group_size": 64},   # override -> 8-bit
            "modB": {"bits": 4, "group_size": 64},   # explicit default
        },
    }
    (tmp_path / "config.json").write_text(json.dumps(cfg))
    # modA: out=10, n_groups=2 -> in=128, params=1280, bits=8
    # modB: out=10, n_groups=4 -> in=256, params=2560, bits=4
    # norm: unquantized (no .scales) -> ignored by the param-weighted bits
    _write_safetensors(str(tmp_path / "model.safetensors"), {
        "modA.scales": {"dtype": "F16", "shape": [10, 2]},
        "modA.biases": {"dtype": "F16", "shape": [10, 2]},
        "modA.weight": {"dtype": "U32", "shape": [10, 32]},
        "modB.scales": {"dtype": "F16", "shape": [10, 4]},
        "modB.biases": {"dtype": "F16", "shape": [10, 4]},
        "modB.weight": {"dtype": "U32", "shape": [10, 32]},
        "norm.weight": {"dtype": "F16", "shape": [10]},
    })
    return tmp_path


def test_quant_info_mixed(tmp_path):
    info = QI.quant_info(str(_make_snapshot(tmp_path)))
    assert info["nominal_bits"] == 4
    assert info["group_size"] == 64
    assert info["mode"] == "affine"
    assert info["mixed"] is True
    assert info["n_quant_modules"] == 2
    assert info["total_quant_params"] == 1280 + 2560
    assert info["bit_histogram"] == {8: 1, 4: 1}
    # param-weighted effective bits = (1280*8 + 2560*4)/3840 = 5.3333...
    assert abs(info["effective_bits"] - (1280 * 8 + 2560 * 4) / 3840) < 1e-6
    assert info["footprint_bytes"] > 0
    assert info["footprint_gb"] >= 0


def test_quant_info_uniform(tmp_path):
    cfg = {"quantization": {"group_size": 64, "bits": 6, "mode": "affine"}}
    (tmp_path / "config.json").write_text(json.dumps(cfg))
    _write_safetensors(str(tmp_path / "model.safetensors"), {
        "x.scales": {"dtype": "F16", "shape": [8, 4]},   # in=256, params=2048, bits=6
        "x.weight": {"dtype": "U32", "shape": [8, 48]},
    })
    info = QI.quant_info(str(tmp_path))
    assert info["nominal_bits"] == 6
    assert info["mixed"] is False        # no per-module override differs from nominal
    assert info["bit_histogram"] == {6: 1}
    assert abs(info["effective_bits"] - 6.0) < 1e-6
