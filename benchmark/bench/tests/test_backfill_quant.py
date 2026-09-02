"""Tests for bench.backfill_quant — recompute the `quant` block of manifests stamped `{}` by the
P8 defect (O34 $HOME-form hf_path never resolved), rewriting ONLY that block, in place."""
import json
import struct

import bench.backfill_quant as B


def _write_min_safetensors(path):
    header = {
        "layers.0.scales": {"dtype": "F16", "shape": [8, 1], "data_offsets": [0, 16]},
        "layers.0.biases": {"dtype": "F16", "shape": [8, 1], "data_offsets": [16, 32]},
        "layers.0.weight": {"dtype": "U32", "shape": [8, 8], "data_offsets": [32, 288]},
    }
    hj = json.dumps(header).encode()
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(hj)))
        f.write(hj)
        f.write(b"\x00" * 288)


def _manifest(model, hf_path, quant):
    # key order mirrors provenance.build_manifest; `tune` last like the real files
    return {"model": model, "box": "m5max", "timestamp": 1, "git": {"stack_head": "x"},
            "kv": {"hf_path": hf_path, "kv_bits": 0}, "quant": quant,
            "sampling": {"temperature": 0.6}, "fingerprint_version": 4, "tune": "t0.6"}


def _tree(tmp_path):
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "config.json").write_text(json.dumps(
        {"model_type": "test", "quantization": {"group_size": 64, "bits": 4}}))
    _write_min_safetensors(str(snap / "model.safetensors"))
    missing = tmp_path / "does-not-exist"
    reg = tmp_path / "reg.yaml"
    reg.write_text(
        "models:\n"
        f"  - name: fixable-4bit\n    hf_path: {snap}\n    kv_bits: 0\n"
        f"  - name: gone-4bit\n    hf_path: {missing}\n    kv_bits: 0\n"
    )
    root = tmp_path / "results"
    (root / "fixable-4bit").mkdir(parents=True)
    (root / "gone-4bit").mkdir(parents=True)
    fixable = root / "fixable-4bit" / "humanevalplus.t0.6.manifest.json"
    gone = root / "gone-4bit" / "humanevalplus.t0.6.manifest.json"
    fixable.write_text(json.dumps(_manifest("fixable-4bit", str(snap), {}), indent=2))
    gone.write_text(json.dumps(_manifest("gone-4bit", str(missing), {}), indent=2))
    return root, reg, fixable, gone


def test_backfill_rewrites_only_the_fixable_manifest_quant_block(tmp_path, capsys):
    root, reg, fixable, gone = _tree(tmp_path)
    gone_before = gone.read_bytes()
    fixable_before = json.loads(fixable.read_text())

    counts = B.run(str(root), str(reg), dry_run=False, only_model=None)

    assert counts == {"skip-ok": 0, "skip-nodir": 1, "fixed": 1, "would-fix": 0}
    assert gone.read_bytes() == gone_before                      # untouched byte-for-byte
    after = json.loads(fixable.read_text())
    assert after["quant"]["nominal_bits"] == 4
    assert after["quant"]["effective_bits"] == 4.0
    assert after["quant"]["mixed"] is False
    assert set(after["quant"]) == {"effective_bits", "footprint_gb", "mixed", "nominal_bits",
                                   "bit_histogram"}
    # every other key/value and the key ORDER are preserved
    assert list(after) == list(fixable_before)
    for k in fixable_before:
        if k != "quant":
            assert after[k] == fixable_before[k]
    assert not fixable.read_text().endswith("\n")                # writer form: no trailing newline
    assert fixable.read_text() == json.dumps(after, indent=2)    # BYTE form matches the live writer (indent=2)
    out = capsys.readouterr().out
    assert "fixed" in out and "skip-nodir" in out and "{} -> (effective_bits=4.000, mixed=False)" in out


def test_backfill_dry_run_writes_nothing(tmp_path):
    root, reg, fixable, gone = _tree(tmp_path)
    before = (fixable.read_bytes(), gone.read_bytes())
    counts = B.run(str(root), str(reg), dry_run=True, only_model=None)
    assert counts["would-fix"] == 1 and counts["fixed"] == 0
    assert (fixable.read_bytes(), gone.read_bytes()) == before


def test_backfill_skips_populated_quant_and_uses_manifest_hf_path_fallback(tmp_path):
    root, reg, fixable, gone = _tree(tmp_path)
    # populated -> skip-ok even though the dir resolves
    fixable.write_text(json.dumps(_manifest("fixable-4bit", "x", {"nominal_bits": 8}), indent=2))
    # a `note` quant for a model NOT in the registry, whose own kv.hf_path is the real dir
    orphan = root / "orphan-4bit" / "mbpp.manifest.json"
    orphan.parent.mkdir()
    orphan.write_text(json.dumps(_manifest("orphan-4bit", str(tmp_path / "snap"),
                                           {"note": "quant_info failed"}), indent=2))
    counts = B.run(str(root), str(reg), dry_run=False, only_model=None)
    assert counts == {"skip-ok": 1, "skip-nodir": 1, "fixed": 1, "would-fix": 0}
    assert json.loads(orphan.read_text())["quant"]["nominal_bits"] == 4
    assert json.loads(fixable.read_text())["quant"] == {"nominal_bits": 8}


def test_backfill_only_model_filters(tmp_path):
    root, reg, fixable, gone = _tree(tmp_path)
    counts = B.run(str(root), str(reg), dry_run=False, only_model="gone-4bit")
    assert counts == {"skip-ok": 0, "skip-nodir": 1, "fixed": 0, "would-fix": 0}
    assert json.loads(fixable.read_text())["quant"] == {}


def test_main_cli_parses_flags(tmp_path, monkeypatch):
    root, reg, fixable, gone = _tree(tmp_path)
    B.main(["--results-root", str(root), "--registry", str(reg), "--dry-run"])
    assert json.loads(fixable.read_text())["quant"] == {}
    B.main(["--results-root", str(root), "--registry", str(reg)])
    assert json.loads(fixable.read_text())["quant"]["nominal_bits"] == 4
